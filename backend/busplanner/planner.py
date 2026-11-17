"""Schedule-based journey search and the three rankings.

Search: direct trips and one-change journeys departing within a window after
the requested time, using scheduled GTFS times only.

Rankings
--------
* **Fastest**       earliest scheduled arrival. Timetable only; crowding is ignored.
* **Balanced**      lowest ``total_min + transfer_penalty + crowding_weight * in_vehicle_min * rank``.
* **Less crowded**  lowest time-weighted relative crowding rank.

Balanced and Less crowded only consider journeys that (a) have ticket evidence
for at least ``min_evidence_coverage`` of their scheduled in-vehicle time and
(b) arrive within a slack envelope of the fastest journey. If no journey
qualifies they return the explicit ``insufficient_evidence`` status instead of
a pick, so a missing estimate is never presented as low crowding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise

from .config import LOCAL_UTC_OFFSET, Settings, day_type_for_weekday, period_for_minute
from .crowding import CrowdingModel
from .gtfs import Stop, Trip
from .network import Network, Pattern, PlaceGroup
from .schemas import (
    BusLeg,
    CrowdingSummary,
    Evidence,
    Journey,
    JourneyOption,
    LegStop,
    Reason,
    RouteRef,
    Segment,
    SegmentCrowding,
    StopRef,
    TransferLeg,
)

WALK_SPEED_M_S = 1.2
MAX_CANDIDATES = 200
QUALITY_GRADE = {"high": 3, "medium": 2, "low": 1, "insufficient": 0}
LEVEL_WORDS = {
    "lower": "relatively less crowded",
    "typical": "about typical",
    "higher": "relatively more crowded",
    "insufficient_evidence": "not enough evidence",
}
OPTION_LABELS = {"fastest": "Fastest", "balanced": "Balanced", "less_crowded": "Less crowded"}


@dataclass(slots=True)
class LegSpec:
    trip: Trip
    pattern: Pattern
    board: int
    alight: int


@dataclass(slots=True)
class Candidate:
    legs: list[LegSpec]
    #: one entry per change: (walk metres, scheduled gap seconds)
    changes: list[tuple[float, int]]

    @property
    def departure(self) -> int:
        leg = self.legs[0]
        return leg.trip.stop_times[leg.board].departure

    @property
    def arrival(self) -> int:
        leg = self.legs[-1]
        return leg.trip.stop_times[leg.alight].arrival

    @property
    def key(self) -> str:
        return "|".join(
            f"{leg.trip.trip_id}:{leg.pattern.stop_ids[leg.board]}:{leg.pattern.stop_ids[leg.alight]}"
            for leg in self.legs
        )


@dataclass
class PlanResult:
    options: list[JourneyOption]
    candidates_considered: int


def _hm(seconds: int) -> str:
    minutes = (seconds // 60) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _mins(seconds: float) -> float:
    return round(seconds / 60, 1)


def _after_fastest(minutes: float) -> str:
    if minutes <= 0:
        return "scheduled to arrive at the same time as Fastest"
    return f"scheduled to arrive {minutes:g} min after Fastest"


class Planner:
    def __init__(self, network: Network, model: CrowdingModel, settings: Settings | None = None) -> None:
        self.network = network
        self.model = model
        self.settings = settings or Settings()
        self.cfg = self.settings.planner

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    def search(self, origin_stops: list[str], dest_stops: list[str], day: date, t0: int) -> list[Candidate]:
        """Scheduled journeys departing in [t0, t0 + window], at most one change."""
        net, cfg = self.network, self.cfg
        services = net.feed.active_services(day)
        if not services:
            return []
        window_end = t0 + cfg.search_window_min * 60
        dest_set = set(dest_stops)
        dest_idx: dict[str, list[int]] = {}
        for stop_id in dest_stops:
            for pattern, i in net.stop_patterns.get(stop_id, ()):
                dest_idx.setdefault(pattern.pattern_id, []).append(i)
        for idxs in dest_idx.values():
            idxs.sort()

        best: dict[tuple[str, ...], Candidate] = {}
        first_legs: list[tuple[Pattern, int, Trip]] = []
        seen_boardings: set[tuple[str, int]] = set()
        for stop_id in origin_stops:
            for pattern, i in net.stop_patterns.get(stop_id, ()):
                if i >= len(pattern.stop_ids) - 1 or (pattern.pattern_id, i) in seen_boardings:
                    continue
                seen_boardings.add((pattern.pattern_id, i))
                j = next((d for d in dest_idx.get(pattern.pattern_id, ()) if d > i), None)
                for trip in pattern.trips:
                    if trip.service_id not in services:
                        continue
                    if not t0 <= trip.stop_times[i].departure <= window_end:
                        continue
                    first_legs.append((pattern, i, trip))
                    if j is not None:
                        # Several origin stops on one trip: keep the latest boarding.
                        key = (trip.trip_id,)
                        current = best.get(key)
                        if current is None or current.legs[0].board < i:
                            best[key] = Candidate([LegSpec(trip, pattern, i, j)], [])

        if cfg.max_transfers >= 1:
            min_gap = cfg.min_transfer_min * 60
            max_wait = cfg.max_transfer_wait_min * 60
            for p1, i, trip1 in first_legs:
                for k in range(i + 1, len(p1.stop_ids)):
                    at_stop = p1.stop_ids[k]
                    if at_stop in dest_set:
                        break  # already there; changing later cannot help
                    arrive = trip1.stop_times[k].arrival
                    for next_stop, dist in net.transfer_links.get(at_stop, ()):
                        ready = arrive + min_gap + dist / WALK_SPEED_M_S
                        for p2, i2 in net.stop_patterns.get(next_stop, ()):
                            if p2.route_id == p1.route_id:
                                continue
                            j2 = next((d for d in dest_idx.get(p2.pattern_id, ()) if d > i2), None)
                            if j2 is None:
                                continue
                            trip2, dep2 = None, 0
                            for t in p2.trips:
                                if t.service_id not in services:
                                    continue
                                d = t.stop_times[i2].departure
                                if d >= ready and (trip2 is None or d < dep2):
                                    trip2, dep2 = t, d
                            if trip2 is None or dep2 - arrive > max_wait:
                                continue
                            gap = dep2 - arrive
                            key = (trip1.trip_id, trip2.trip_id)
                            current = best.get(key)
                            # Same pair of buses: prefer the change with the most slack.
                            if current is None or gap > current.changes[0][1]:
                                best[key] = Candidate(
                                    [LegSpec(trip1, p1, i, k), LegSpec(trip2, p2, i2, j2)], [(dist, gap)]
                                )
        candidates = sorted(best.values(), key=lambda c: (c.arrival, len(c.legs), -c.departure, c.key))
        return candidates[:MAX_CANDIDATES]

    # ------------------------------------------------------------------
    # journey assembly
    # ------------------------------------------------------------------
    def _iso(self, day: date, seconds: int) -> str:
        return (datetime.combine(day, time()) + timedelta(seconds=seconds)).isoformat() + LOCAL_UTC_OFFSET

    def _stop_ref(self, stop: Stop) -> StopRef:
        return StopRef(stop_id=stop.stop_id, name=stop.name or stop.stop_id, lat=stop.lat, lon=stop.lon)

    def build_journey(self, cand: Candidate, day: date, t0: int) -> Journey:
        feed, model = self.network.feed, self.model
        day_type = day_type_for_weekday(day.weekday())
        legs: list[BusLeg | TransferLeg] = []
        weight_total = weight_covered = rank_sum = grade_sum = 0.0
        in_vehicle = covered = 0.0
        level_counts = {"lower": 0, "typical": 0, "higher": 0, "insufficient_evidence": 0}
        supports: list[int] = []

        for n, leg in enumerate(cand.legs):
            if n > 0:
                prev = cand.legs[n - 1]
                walk_m, gap = cand.changes[n - 1]
                legs.append(
                    TransferLeg(
                        from_stop=self._stop_ref(feed.stops[prev.pattern.stop_ids[prev.alight]]),
                        to_stop=self._stop_ref(feed.stops[leg.pattern.stop_ids[leg.board]]),
                        scheduled_min=_mins(gap),
                        walk_m=round(walk_m),
                    )
                )
            route = feed.routes[leg.trip.route_id]
            sts = leg.trip.stop_times[leg.board : leg.alight + 1]
            stops = [
                LegStop(
                    stop_id=st.stop_id,
                    name=feed.stops[st.stop_id].name or st.stop_id,
                    lat=feed.stops[st.stop_id].lat,
                    lon=feed.stops[st.stop_id].lon,
                    sequence=st.sequence,
                    scheduled_arrival=self._iso(day, st.arrival),
                    scheduled_departure=self._iso(day, st.departure),
                )
                for st in sts
            ]
            segments: list[Segment] = []
            for a, b in pairwise(sts):
                est = model.lookup(route.route_id, a.stop_id, b.stop_id, day_type, period_for_minute(a.departure // 60))
                seconds = b.arrival - a.departure
                weight = max(seconds, 30) / 60
                weight_total += weight
                in_vehicle += seconds / 60
                grade_sum += weight * QUALITY_GRADE[est.quality]
                level_counts[est.level] += 1
                if est.relative_rank is not None:
                    weight_covered += weight
                    covered += seconds / 60
                    rank_sum += weight * est.relative_rank
                    supports.append(est.ticket_count)
                segments.append(
                    Segment(
                        from_stop_id=a.stop_id,
                        to_stop_id=b.stop_id,
                        scheduled_departure=self._iso(day, a.departure),
                        scheduled_arrival=self._iso(day, b.arrival),
                        scheduled_min=_mins(seconds),
                        crowding=SegmentCrowding(
                            level=est.level,
                            relative_rank=est.relative_rank,
                            evidence=Evidence(
                                quality=est.quality,
                                basis=est.basis,
                                ticket_count=est.ticket_count,
                                rider_count=est.rider_count,
                                service_days=est.service_days,
                                scheduled_trips=est.scheduled_trips,
                                min_tickets_required=model.config.min_tickets,
                            ),
                        ),
                    )
                )
            legs.append(
                BusLeg(
                    route=RouteRef(route_id=route.route_id, short_name=route.display_name, long_name=route.long_name),
                    trip_id=leg.trip.trip_id,
                    headsign=leg.trip.headsign or (feed.stops[leg.pattern.stop_ids[-1]].name),
                    direction_id=leg.trip.direction_id,
                    board_stop=self._stop_ref(feed.stops[sts[0].stop_id]),
                    alight_stop=self._stop_ref(feed.stops[sts[-1].stop_id]),
                    scheduled_departure=self._iso(day, sts[0].departure),
                    scheduled_arrival=self._iso(day, sts[-1].arrival),
                    scheduled_min=_mins(sts[-1].arrival - sts[0].departure),
                    stops=stops,
                    segments=segments,
                )
            )

        coverage = weight_covered / weight_total if weight_total else 0.0
        if coverage >= self.cfg.min_evidence_coverage and weight_covered > 0:
            rank = rank_sum / weight_covered
            grade = grade_sum / weight_total
            level = model.level_for_rank(rank)
            quality = "high" if grade >= 2.5 else "medium" if grade >= 1.5 else "low"
            rank_out: float | None = round(rank, 4)
        else:
            level, quality, rank_out = "insufficient_evidence", "insufficient", None
        return Journey(
            journey_id=cand.key,
            scheduled_departure=self._iso(day, cand.departure),
            scheduled_arrival=self._iso(day, cand.arrival),
            scheduled_travel_min=_mins(cand.arrival - cand.departure),
            initial_wait_min=_mins(cand.departure - t0),
            total_min=_mins(cand.arrival - t0),
            transfers=len(cand.legs) - 1,
            legs=legs,
            crowding=CrowdingSummary(
                level=level,
                relative_rank=rank_out,
                evidence_quality=quality,
                coverage=round(coverage, 3),
                covered_min=round(covered, 1),
                in_vehicle_min=round(in_vehicle, 1),
                min_segment_ticket_count=min(supports) if supports else 0,
                segment_counts=level_counts,
            ),
        )

    # ------------------------------------------------------------------
    # ranking
    # ------------------------------------------------------------------
    def plan(self, origin: PlaceGroup, destination: PlaceGroup, day: date, t0: int) -> PlanResult:
        candidates = self.search(origin.stop_ids, destination.stop_ids, day, t0)
        journeys = [self.build_journey(c, day, t0) for c in candidates]
        return PlanResult(self.rank(journeys, t0), len(journeys))

    def balanced_cost(self, journey: Journey) -> dict[str, float]:
        cfg = self.cfg
        rank = journey.crowding.relative_rank or 0.0
        transfer_penalty = cfg.transfer_penalty_min * journey.transfers
        crowding_penalty = cfg.crowding_weight * journey.crowding.in_vehicle_min * rank
        return {
            "total_min": journey.total_min,
            "transfer_penalty_min": round(transfer_penalty, 1),
            "crowding_penalty_min": round(crowding_penalty, 1),
            "cost": round(journey.total_min + transfer_penalty + crowding_penalty, 2),
        }

    def rank(self, journeys: list[Journey], t0: int) -> list[JourneyOption]:
        cfg = self.cfg
        if not journeys:
            reason = Reason(
                summary=f"No scheduled bus journey departs within {cfg.search_window_min} min of {_hm(t0)}.",
                details=[
                    "Searched direct buses and journeys with one change.",
                    "Try another time or a nearby stop.",
                ],
            )
            return [
                JourneyOption(kind=kind, label=OPTION_LABELS[kind], status="no_journey", reason=reason)
                for kind in ("fastest", "balanced", "less_crowded")
            ]

        fastest = min(journeys, key=lambda j: (j.scheduled_arrival, j.transfers, j.scheduled_travel_min, j.journey_id))
        limit = fastest.total_min + max(cfg.slack_min, cfg.slack_ratio * fastest.total_min)
        in_envelope = [j for j in journeys if j.total_min <= limit]
        eligible = [j for j in in_envelope if j.crowding.level != "insufficient_evidence"]

        options = [
            JourneyOption(
                kind="fastest",
                label=OPTION_LABELS["fastest"],
                status="ok",
                journey=fastest,
                reason=self._fastest_reason(fastest, len(journeys), t0),
            )
        ]
        if not eligible:
            for kind in ("balanced", "less_crowded"):
                options.append(
                    JourneyOption(
                        kind=kind,
                        label=OPTION_LABELS[kind],
                        status="insufficient_evidence",
                        reason=self._insufficient_reason(in_envelope, len(journeys)),
                    )
                )
            return options

        balanced = min(eligible, key=lambda j: (self.balanced_cost(j)["cost"], j.scheduled_arrival, j.journey_id))
        calm = min(eligible, key=lambda j: (j.crowding.relative_rank, j.total_min, j.journey_id))
        options.append(
            JourneyOption(
                kind="balanced",
                label=OPTION_LABELS["balanced"],
                status="ok",
                journey=balanced,
                reason=self._balanced_reason(balanced, fastest, len(eligible), len(journeys)),
                same_journey_as="fastest" if balanced.journey_id == fastest.journey_id else None,
            )
        )
        same: str | None = None
        if calm.journey_id == fastest.journey_id:
            same = "fastest"
        elif calm.journey_id == balanced.journey_id:
            same = "balanced"
        options.append(
            JourneyOption(
                kind="less_crowded",
                label=OPTION_LABELS["less_crowded"],
                status="ok",
                journey=calm,
                reason=self._less_crowded_reason(calm, fastest, len(eligible), len(journeys), limit),
                same_journey_as=same,
            )
        )
        return options

    # -- reasons ----------------------------------------------------------
    @staticmethod
    def _describe_route(journey: Journey) -> str:
        buses = [leg for leg in journey.legs if isinstance(leg, BusLeg)]
        if len(buses) == 1:
            return f"Direct on route {buses[0].route.short_name} towards {buses[0].headsign}."
        change = buses[0].alight_stop.name
        names = " then ".join(f"route {b.route.short_name}" for b in buses)
        return f"One change: {names}, changing at {change}."

    @staticmethod
    def _describe_crowding(journey: Journey) -> str:
        c = journey.crowding
        if c.level == "insufficient_evidence":
            return (
                f"Crowding: not enough ticket evidence (samples cover {c.covered_min:g} of "
                f"{c.in_vehicle_min:g} scheduled in-vehicle min)."
            )
        return (
            f"Relative crowding: {LEVEL_WORDS[c.level]}; evidence {c.evidence_quality}, covering "
            f"{c.covered_min:g} of {c.in_vehicle_min:g} scheduled in-vehicle min."
        )

    def _fastest_reason(self, journey: Journey, n: int, t0: int) -> Reason:
        arrival = journey.scheduled_arrival[11:16]
        return Reason(
            summary=(
                f"Earliest scheduled arrival ({arrival}) of {n} scheduled "
                f"journey{'s' if n != 1 else ''} departing within {self.cfg.search_window_min} min of {_hm(t0)}."
            ),
            details=[
                self._describe_route(journey),
                f"Scheduled travel time {journey.scheduled_travel_min:g} min after a "
                f"{journey.initial_wait_min:g} min wait.",
                "Ranked on the timetable only; crowding is not used for Fastest.",
                self._describe_crowding(journey),
            ],
            metrics={"total_min": journey.total_min, "journeys_compared": n},
        )

    def _insufficient_reason(self, in_envelope: list[Journey], n: int) -> Reason:
        cfg, ccfg = self.cfg, self.model.config
        best_cov = max((j.crowding.coverage for j in in_envelope), default=0.0)
        return Reason(
            summary=(
                f"Insufficient evidence: none of the {n} scheduled journey{'s' if n != 1 else ''} has ticket "
                f"samples for at least {cfg.min_evidence_coverage:.0%} of its scheduled in-vehicle time, "
                "so they cannot be ranked on crowding."
            ),
            details=[
                "This means crowding is unknown here. It does not mean these buses are quiet.",
                f"Best evidence coverage found: {best_cov:.0%} of scheduled in-vehicle time.",
                f"A segment needs at least {ccfg.min_tickets} ticket samples from {ccfg.min_service_days} "
                "or more service days before a relative level is shown.",
                "Use Fastest for a timetable-only option.",
            ],
            metrics={
                "journeys_compared": n,
                "best_coverage": round(best_cov, 3),
                "min_evidence_coverage": cfg.min_evidence_coverage,
                "min_tickets": ccfg.min_tickets,
            },
        )

    def _balanced_reason(self, journey: Journey, fastest: Journey, eligible: int, n: int) -> Reason:
        cost = self.balanced_cost(journey)
        slower = round(journey.total_min - fastest.total_min, 1)
        if journey.journey_id == fastest.journey_id:
            summary = (
                f"The fastest journey also has the best mix of scheduled time and relative crowding "
                f"among {eligible} journey{'s' if eligible != 1 else ''} with enough ticket evidence."
            )
        else:
            summary = (
                f"Best mix of scheduled time and relative crowding among {eligible} "
                f"journey{'s' if eligible != 1 else ''} with enough ticket evidence; {_after_fastest(slower)}."
            )
        details = [
            self._describe_route(journey),
            self._describe_crowding(journey),
            (
                f"Score {cost['cost']:g} = {cost['total_min']:g} min door-to-arrival + "
                f"{cost['transfer_penalty_min']:g} min change penalty + "
                f"{cost['crowding_penalty_min']:g} min crowding penalty (lower is better)."
            ),
        ]
        if eligible < n:
            details.append(
                f"{n - eligible} of {n} scheduled journeys were left out for lacking evidence or arriving too late."
            )
        return Reason(
            summary=summary,
            details=details,
            metrics={**cost, "minutes_slower_than_fastest": slower, "journeys_with_evidence": eligible},
        )

    def _less_crowded_reason(self, journey: Journey, fastest: Journey, eligible: int, n: int, limit: float) -> Reason:
        slower = round(journey.total_min - fastest.total_min, 1)
        allowed = round(limit - fastest.total_min)
        if journey.journey_id == fastest.journey_id:
            summary = (
                f"The fastest journey also has the lowest relative crowding among {eligible} "
                f"journey{'s' if eligible != 1 else ''} with enough ticket evidence."
            )
        else:
            summary = (
                f"Lowest relative crowding among {eligible} journey{'s' if eligible != 1 else ''} with enough "
                f"ticket evidence; {_after_fastest(slower)}."
            )
        details = [
            self._describe_route(journey),
            self._describe_crowding(journey),
            f"Only journeys arriving within {allowed} min of Fastest were considered.",
        ]
        if fastest.crowding.level == "insufficient_evidence" and journey.journey_id != fastest.journey_id:
            details.append("Fastest could not be compared on crowding: it lacks ticket evidence.")
        if eligible < n:
            details.append(
                f"{n - eligible} of {n} scheduled journeys were left out for lacking evidence or arriving too late."
            )
        return Reason(
            summary=summary,
            details=details,
            metrics={
                "relative_rank": journey.crowding.relative_rank,
                "minutes_slower_than_fastest": slower,
                "journeys_with_evidence": eligible,
                "max_minutes_after_fastest": allowed,
            },
        )
