"""Relative crowding estimate from matched ticket samples.

What is estimated
-----------------
For every route segment (route, from_stop -> to_stop) and time bucket we count
the sampled riders whose ticket covers that segment and divide by the number of
*scheduled* trips through the segment on the sampled service days::

    index = sampled riders through segment / scheduled trips through segment

The index is then ranked against every other supported segment-bucket in the
same dataset. Only that **relative rank** is reported, as lower / typical /
higher.

What is NOT estimated
---------------------
Ticket samples are not verified occupancy. The index is not passengers on
board, not seats available and not a percentage full. Riders without a ticket
row (passes, missing extracts, unmatched records) are invisible, and a segment
with few samples is reported as "insufficient evidence", never as "low".

Fallbacks (in order; each step lowers the evidence grade)
---------------------------------------------------------
1. ``segment_period_daytype``  this segment, this period, this day type
2. ``segment_period``          this segment, this period, day types pooled
3. ``segment_all_day``         this segment, all periods and day types pooled
4. ``none``                    insufficient evidence
"""

from __future__ import annotations

import bisect
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from .config import CrowdingConfig, day_type_for_weekday, period_for_minute
from .matching import MATCHED, TicketMatch
from .network import Network

FALLBACKS: tuple[dict[str, str], ...] = (
    {
        "basis": "segment_period_daytype",
        "description": "Samples for this segment in the same time period and day type.",
        "quality_cap": "high",
    },
    {
        "basis": "segment_period",
        "description": "Samples for this segment in the same time period, weekdays and weekends pooled.",
        "quality_cap": "medium",
    },
    {
        "basis": "segment_all_day",
        "description": "All samples for this segment, every period and day type pooled.",
        "quality_cap": "low",
    },
    {
        "basis": "none",
        "description": "Too few samples at every level: reported as insufficient evidence.",
        "quality_cap": "insufficient",
    },
)

# cell value layout: (ticket_count, rider_count, service_days, scheduled_trips)
Cell = tuple[int, int, int, int]


@dataclass(frozen=True)
class SegmentEstimate:
    level: str
    relative_rank: float | None
    quality: str
    basis: str
    ticket_count: int
    rider_count: int
    service_days: int
    scheduled_trips: int


class CrowdingModel:
    def __init__(
        self,
        config: CrowdingConfig,
        l1: dict[tuple[str, str, str, str, str], Cell],
        l2: dict[tuple[str, str, str, str], Cell],
        l3: dict[tuple[str, str, str], Cell],
        stats: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.l1, self.l2, self.l3 = l1, l2, l3
        self.reference = sorted(c[1] / c[3] for c in l1.values() if self._supported(c))
        self.stats = stats or {}

    @classmethod
    def empty(cls, config: CrowdingConfig | None = None) -> CrowdingModel:
        return cls(config or CrowdingConfig(), {}, {}, {})

    @property
    def usable(self) -> bool:
        return len(self.reference) >= self.config.min_reference_cells

    def _supported(self, cell: Cell) -> bool:
        return cell[0] >= self.config.min_tickets and cell[2] >= self.config.min_service_days and cell[3] > 0

    def _strong(self, cell: Cell) -> bool:
        return cell[0] >= self.config.strong_tickets and cell[2] >= self.config.strong_service_days

    def rank(self, index: float) -> float:
        """Mid-rank of ``index`` within the reference distribution, 0..1."""
        ref = self.reference
        below = bisect.bisect_left(ref, index)
        equal = bisect.bisect_right(ref, index) - below
        return (below + 0.5 * equal) / len(ref) if equal else below / len(ref)

    def level_for_rank(self, rank: float) -> str:
        if rank < self.config.lower_cut:
            return "lower"
        if rank >= self.config.higher_cut:
            return "higher"
        return "typical"

    def lookup(self, route_id: str, from_stop: str, to_stop: str, day_type: str, period: str) -> SegmentEstimate:
        seg = (route_id, from_stop, to_stop)
        candidates = (
            ("segment_period_daytype", self.l1.get((*seg, day_type, period)), ("high", "medium")),
            ("segment_period", self.l2.get((*seg, period)), ("medium", "low")),
            ("segment_all_day", self.l3.get(seg), ("low", "low")),
        )
        if self.usable:
            for basis, cell, (strong_grade, adequate_grade) in candidates:
                if cell is None or not self._supported(cell):
                    continue
                rank = self.rank(cell[1] / cell[3])
                quality = strong_grade if self._strong(cell) else adequate_grade
                return SegmentEstimate(self.level_for_rank(rank), round(rank, 4), quality, basis, *cell)
        widest = self.l3.get(seg, (0, 0, 0, 0))
        return SegmentEstimate("insufficient_evidence", None, "insufficient", "none", *widest)

    # -- persistence ------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "stats": self.stats,
            "l1": [[*k, *v] for k, v in sorted(self.l1.items())],
            "l2": [[*k, *v] for k, v in sorted(self.l2.items())],
            "l3": [[*k, *v] for k, v in sorted(self.l3.items())],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CrowdingModel:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            CrowdingConfig(**raw["config"]),
            {tuple(r[:5]): tuple(r[5:]) for r in raw["l1"]},
            {tuple(r[:4]): tuple(r[4:]) for r in raw["l2"]},
            {tuple(r[:3]): tuple(r[3:]) for r in raw["l3"]},
            raw.get("stats"),
        )


def build_crowding_model(
    network: Network,
    matches: list[TicketMatch],
    observed_dates: list[date],
    config: CrowdingConfig | None = None,
) -> CrowdingModel:
    """Aggregate matched tickets into segment cells.

    ``observed_dates`` are the service days covered by the ticket sample; they
    define how many scheduled trips the samples are spread over.
    """
    config = config or CrowdingConfig()
    feed = network.feed

    # --- numerator: sampled riders per segment-bucket ---------------------
    acc: list[dict[tuple, list]] = [defaultdict(lambda: [0, 0, set()]) for _ in range(3)]
    tickets_used = 0
    segment_samples = 0
    for match in matches:
        if match.status != MATCHED:
            continue
        ticket = match.ticket
        tickets_used += 1
        service_day = ticket.service_date
        day_type = day_type_for_weekday(service_day.weekday())
        for k in range(len(match.path) - 1):
            # The rider reaches segment k some scheduled minutes after boarding.
            when = ticket.issued_at + timedelta(seconds=match.offsets[k])
            period = period_for_minute(when.hour * 60 + when.minute)
            seg = (match.route_id, match.path[k], match.path[k + 1])
            for level, key in enumerate(((*seg, day_type, period), (*seg, period), seg)):
                slot = acc[level][key]
                slot[0] += 1
                slot[1] += ticket.passengers
                slot[2].add(service_day)
            segment_samples += 1

    # --- denominator: scheduled trips over the sampled service days -------
    signatures: dict[frozenset[str], Counter[str]] = defaultdict(Counter)
    for day in observed_dates:
        signatures[feed.active_services(day)][day_type_for_weekday(day.weekday())] += 1
    exposure: list[Counter[tuple]] = [Counter(), Counter(), Counter()]
    for services, day_counts in signatures.items():
        if not services:
            continue
        for trip in feed.trips.values():
            if trip.service_id not in services:
                continue
            sts = trip.stop_times
            for prev, cur in pairwise(sts):
                period = period_for_minute(prev.departure // 60)
                seg = (trip.route_id, prev.stop_id, cur.stop_id)
                for day_type, n in day_counts.items():
                    exposure[0][(*seg, day_type, period)] += n
                    exposure[1][(*seg, period)] += n
                    exposure[2][seg] += n

    levels: list[dict[tuple, Cell]] = []
    for level in range(3):
        levels.append(
            {key: (slot[0], slot[1], len(slot[2]), exposure[level].get(key, 0)) for key, slot in acc[level].items()}
        )
    model = CrowdingModel(config, levels[0], levels[1], levels[2])

    all_segments = {(p.route_id, a, b) for p in network.patterns.values() for a, b in pairwise(p.stop_ids)}
    off_schedule = [c for c in model.l1.values() if c[3] == 0]
    ref = model.reference
    model.stats = {
        "tickets_used": tickets_used,
        "ticket_segment_samples": segment_samples,
        "sampled_service_days": len(observed_dates),
        "route_segments_total": len(all_segments),
        "route_segments_with_any_sample": len(model.l3),
        "route_segments_with_usable_evidence": sum(1 for c in model.l3.values() if model._supported(c)),
        "cells_with_samples": len(model.l1),
        "cells_supported": len(ref),
        "cells_strong": sum(1 for c in model.l1.values() if model._supported(c) and model._strong(c)),
        "cells_outside_schedule": len(off_schedule),
        "ticket_samples_outside_schedule": sum(c[0] for c in off_schedule),
        "reference_cells": len(ref),
        "min_reference_cells": config.min_reference_cells,
        "usable": model.usable,
        "index_definition": "sampled riders through a segment per scheduled trip (not occupancy)",
        "reference_index_median": round(ref[len(ref) // 2], 4) if ref else None,
    }
    return model
