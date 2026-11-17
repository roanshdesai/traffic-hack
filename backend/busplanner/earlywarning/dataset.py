"""Load a built early-warning dataset and answer the API's questions."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import Calendar, SourceSpec, WarningConfig
from .evaluate import episodes_for, replay_site_day
from .model import Assessment, Baselines, Detector, ForecastPoint, Warning
from .sources import ObservationSet, SiteInfo

FMT = "%Y-%m-%dT%H:%M"
URGENCY = {"overcrowding_alert": 0, "warning": 1, "elevated": 2, "normal": 3, "insufficient_evidence": 4, "no_data": 5}
OVERVIEW_LIMIT = 200


class WarningDatasetError(RuntimeError):
    pass


@dataclass
class SiteSnapshot:
    site: SiteInfo
    at: datetime
    current: Assessment
    forecasts: list[ForecastPoint]
    warning: Warning | None


class WarningDataset:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        manifest_path = self.directory / "manifest.json"
        if not manifest_path.is_file():
            raise WarningDatasetError(f"No early-warning dataset at {self.directory}. Run `make data` first.")

        def read(name: str) -> Any:
            return json.loads((self.directory / name).read_text(encoding="utf-8"))

        manifest = read("manifest.json")
        self.provenance: dict[str, Any] = manifest["provenance"]
        self.cfg = WarningConfig(**{k: tuple(v) if isinstance(v, list) else v for k, v in manifest["settings"].items()})
        self.calendar = Calendar(
            frozenset(date.fromisoformat(d) for d in manifest["holidays"]), manifest.get("split_saturday", False)
        )
        spec = SourceSpec(**manifest["spec"])
        obs = ObservationSet(spec=spec)
        obs.sites = {s["site_id"]: SiteInfo(**s) for s in read("sites.json")}
        obs.days = {date.fromisoformat(d) for d in manifest["days"]}
        counts: dict[str, dict] = defaultdict(dict)
        for sid, rows in read("replay.json").items():
            for day, slot, value in rows:
                counts[sid][(date.fromisoformat(day), slot)] = value
        obs.counts = counts
        self.obs = obs
        self.detector = Detector(obs, Baselines.from_json(read("baselines.json")), self.calendar, self.cfg)
        self.episodes: list[dict[str, Any]] = read("episodes.json")
        self.events: list[dict[str, str]] = read("events.json")
        self.evaluation: dict[str, Any] = read("evaluation.json")
        self.quality_report: dict[str, Any] = read("quality_report.json")
        rp = self.provenance["replay_period"]
        self.replay_start, self.replay_end = date.fromisoformat(rp["start"]), date.fromisoformat(rp["end"])

    # -- time helpers -----------------------------------------------------
    def in_replay(self, day: date) -> bool:
        return self.replay_start <= day <= self.replay_end

    def clamp_to_service(self, moment: datetime) -> datetime:
        """Snap a replay time down to the start of its window, within service hours."""
        spec = self.obs.spec
        minute = moment.hour * 60 + moment.minute
        minute = min(max(minute, spec.service_start_min), spec.service_end_min - spec.window_minutes)
        minute -= (minute - spec.service_start_min) % spec.window_minutes
        return datetime.combine(moment.date(), datetime.min.time()).replace(hour=minute // 60, minute=minute % 60)

    def default_at(self) -> datetime:
        """The first alert or early warning in the replay period, else the first replay morning."""
        candidates = [datetime.strptime(e["first_warning_at"] or e["start"], FMT) for e in self.episodes]
        matched = [
            datetime.strptime(e["first_warning_at"] or e["start"], FMT)
            for e in self.episodes
            if e.get("matched_event") is not False and e["first_warning_at"]
        ]
        if matched or candidates:
            return min(matched or candidates)
        return self.clamp_to_service(datetime.combine(self.replay_start, datetime.min.time()).replace(hour=8))

    # -- queries ----------------------------------------------------------
    def snapshot(self, site_id: str, at: datetime) -> SiteSnapshot:
        current = self.detector.assess(site_id, at)
        forecasts = self.detector.forecast(site_id, at) if current.observed is not None else []
        return SiteSnapshot(self.obs.sites[site_id], at, current, forecasts,
                            self.detector.early_warning(current, forecasts))  # fmt: skip

    def overview(self, at: datetime) -> tuple[list[SiteSnapshot], dict[str, int]]:
        snaps = [self.snapshot(sid, at) for sid in self.obs.sites]
        counts = {k: 0 for k in URGENCY if k != "warning"}
        counts["early_warning"] = 0
        for s in snaps:
            counts[s.current.status] += 1
            counts["early_warning"] += s.warning is not None

        def rank(s: SiteSnapshot) -> tuple:
            key = "warning" if s.warning and s.current.status != "overcrowding_alert" else s.current.status
            return (URGENCY[key], -(s.current.ratio or 0), s.site.name)

        snaps.sort(key=rank)
        return snaps, counts

    def timeline(self, site_id: str, day: date) -> list[Assessment]:
        return replay_site_day(self.detector, site_id, day).assessments

    def episodes_on(self, day: date | None, site_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for ep in self.episodes:
            if day is not None and ep["start"][:10] != day.isoformat():
                continue
            if site_id is not None and ep["site_id"] != site_id:
                continue
            out.append(ep)
        return out

    def events_on(self, site_id: str, day: date) -> list[dict[str, str]]:
        return [e for e in self.events if e["site_id"] == site_id and e["onset"][:10] == day.isoformat()]

    def search(self, q: str, limit: int) -> list[SiteInfo]:
        q = q.strip().lower()
        sites = sorted(self.obs.sites.values(), key=lambda s: s.name.lower())
        if q:
            sites = [s for s in sites if q in s.name.lower() or q in s.site_id.lower()]
        return sites[:limit]


__all__ = ["WarningDataset", "WarningDatasetError", "episodes_for", "OVERVIEW_LIMIT"]
