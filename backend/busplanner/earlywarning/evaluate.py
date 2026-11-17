"""Replay the detector over recorded days, merge alerts into episodes and score them.

On synthetic data the injected events are the ground truth. On real data there
is no ground truth, so only descriptive statistics and stability checks are
reported; nothing there measures accuracy.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .model import Assessment, Detector, ForecastPoint, Warning

GREY_ZONE = timedelta(minutes=30)  # after an event ends, alerts are neither right nor wrong
#: A warning that expected the alert up to this much too early still counts as warning of it.
WARNING_SLACK = timedelta(minutes=30)


@dataclass
class Event:
    site_id: str
    start: datetime
    onset: datetime
    end: datetime
    kind: str
    description: str

    def to_dict(self) -> dict[str, str]:
        f = "%Y-%m-%dT%H:%M"
        return {"site_id": self.site_id, "start": self.start.strftime(f), "onset": self.onset.strftime(f),
                "end": self.end.strftime(f), "kind": self.kind, "description": self.description}  # fmt: skip


@dataclass
class Episode:
    site_id: str
    start: datetime
    end: datetime
    peak_observed: int
    peak_ratio: float | None
    triggers: set[str] = field(default_factory=set)
    first_warning_at: datetime | None = None
    matched_event: bool | None = None

    @property
    def lead_min(self) -> int | None:
        if self.first_warning_at is None:
            return None
        return int((self.start - self.first_warning_at).total_seconds() // 60)


@dataclass
class SiteDay:
    site_id: str
    day: date
    assessments: list[Assessment]
    forecasts: list[list[ForecastPoint]]
    warnings: list[Warning | None]


def load_events(path: str | Path) -> list[Event]:
    events = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            parse = lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M")  # noqa: E731
            events.append(Event(row["site_id"], parse(row["start"]), parse(row["onset"]), parse(row["end"]),
                                row["kind"], row["description"]))  # fmt: skip
    return events


def replay_site_day(detector: Detector, site_id: str, day: date) -> SiteDay:
    obs = detector.obs
    result = SiteDay(site_id, day, [], [], [])
    for slot in range(obs.slots_per_day):
        moment = obs.window_start(day, slot)
        current = detector.assess(site_id, moment)
        points = detector.forecast(site_id, moment) if current.observed is not None else []
        result.assessments.append(current)
        result.forecasts.append(points)
        result.warnings.append(detector.early_warning(current, points))
    return result


def episodes_for(site_day: SiteDay) -> list[Episode]:
    episodes: list[Episode] = []
    current: Episode | None = None
    for a in site_day.assessments:
        if a.status == "overcrowding_alert":
            if current is None:
                current = Episode(a.site_id, a.window_start, a.window_end, a.observed or 0, a.ratio)
                episodes.append(current)
            current.end = a.window_end
            if (a.observed or 0) > current.peak_observed:
                current.peak_observed = a.observed or 0
                current.peak_ratio = a.ratio
            current.triggers.update(a.triggers)
        else:
            current = None
    for ep in episodes:
        for a, w in zip(site_day.assessments, site_day.warnings, strict=True):
            if a.window_start >= ep.start:
                break
            # A warning counts for this episode if it was still "live" (its expected time not yet passed
            # before the episode began) and it pointed into the episode or just before it.
            if w is not None and w.expected_at < ep.end and w.expected_at + WARNING_SLACK >= ep.start:
                ep.first_warning_at = a.window_start
                break
    return episodes


def replay(detector: Detector, days: list[date]) -> tuple[list[SiteDay], list[Episode]]:
    site_days: list[SiteDay] = []
    episodes: list[Episode] = []
    for site_id in sorted(detector.obs.sites):
        for day in days:
            sd = replay_site_day(detector, site_id, day)
            site_days.append(sd)
            episodes.extend(episodes_for(sd))
    return site_days, episodes


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _status_shares(site_days: list[SiteDay]) -> dict[str, float]:
    counts = Counter(a.status for sd in site_days for a in sd.assessments)
    total = sum(counts.values()) or 1
    return {k: round(v / total, 4) for k, v in sorted(counts.items())}


def evaluate_against_events(
    site_days: list[SiteDay], episodes: list[Episode], events: list[Event], replay_days: list[date]
) -> dict[str, Any]:
    in_replay = [e for e in events if e.onset.date() in replay_days]
    by_site: dict[str, list[Event]] = defaultdict(list)
    for e in in_replay:
        by_site[e.site_id].append(e)

    def truth(site_id: str, t: datetime) -> bool:
        return any(e.onset <= t < e.end for e in by_site[site_id])

    def grey(site_id: str, t: datetime) -> bool:
        return any(e.start <= t < e.end + GREY_ZONE for e in by_site[site_id]) and not truth(site_id, t)

    tp = fp = fn = 0
    warnings_issued = warnings_on_event = 0
    for sd in site_days:
        for a, w in zip(sd.assessments, sd.warnings, strict=True):
            is_truth, is_grey = truth(sd.site_id, a.window_start), grey(sd.site_id, a.window_start)
            alert = a.status == "overcrowding_alert"
            if alert and is_truth:
                tp += 1
            elif alert and not is_grey:
                fp += 1
            elif is_truth and not alert:
                fn += 1
            if w is not None:
                warnings_issued += 1
                if any(e.start <= w.expected_at < e.end + GREY_ZONE for e in by_site[sd.site_id]):
                    warnings_on_event += 1

    detected, delays, warned, leads = 0, [], 0, []
    warned_before_alert, alert_leads = 0, []
    per_event = []
    lookup = {(sd.site_id, sd.day): sd for sd in site_days}
    for e in in_replay:
        sd = lookup.get((e.site_id, e.onset.date()))
        alerts = [a.window_start for a in sd.assessments if a.status == "overcrowding_alert"]
        first_alert = next((t for t in alerts if e.start <= t < e.end), None)
        first_warn = None
        for a, w in zip(sd.assessments, sd.warnings, strict=True):
            if a.window_start >= e.onset:
                break
            if w is not None and e.start <= w.expected_at < e.end:
                first_warn = a.window_start
                break
        warn_before_alert = None
        if first_alert is not None:
            for a, w in zip(sd.assessments, sd.warnings, strict=True):
                if a.window_start >= first_alert:
                    break
                if w is not None and e.start <= w.expected_at < e.end:
                    warn_before_alert = a.window_start
                    break
        if warn_before_alert is not None:
            warned_before_alert += 1
            alert_leads.append((first_alert - warn_before_alert).total_seconds() / 60)
        if first_alert is not None:
            detected += 1
            delays.append((first_alert - e.onset).total_seconds() / 60)
        if first_warn is not None:
            warned += 1
            leads.append((e.onset - first_warn).total_seconds() / 60)
        per_event.append({
            "site_id": e.site_id, "kind": e.kind, "onset": e.onset.strftime("%Y-%m-%dT%H:%M"),
            "detected": first_alert is not None,
            "detection_delay_min": None if first_alert is None else int((first_alert - e.onset).total_seconds() // 60),
            "warned_before_onset": first_warn is not None,
            "warning_lead_min": None if first_warn is None else int((e.onset - first_warn).total_seconds() // 60),
            "warned_before_alert": warn_before_alert is not None,
            "warning_lead_before_alert_min": None if warn_before_alert is None
            else int((first_alert - warn_before_alert).total_seconds() // 60),
        })  # fmt: skip

    def overlaps(ep: Episode) -> bool:
        return any(ep.start < e.end + GREY_ZONE and e.start < ep.end for e in by_site[ep.site_id])

    for ep in episodes:
        ep.matched_event = overlaps(ep)
    false_episodes = [ep for ep in episodes if not ep.matched_event]
    site_day_count = len(site_days) or 1
    return {
        "events_in_replay": len(in_replay),
        "events_detected": detected,
        "event_recall": round(detected / len(in_replay), 3) if in_replay else None,
        "median_detection_delay_min": _median(delays),
        "events_warned_before_onset": warned,
        "median_warning_lead_min": _median(leads),
        "events_warned_before_first_alert": warned_before_alert,
        "median_warning_lead_before_alert_min": _median(alert_leads),
        "window_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "window_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "alert_episodes": len(episodes),
        "false_alert_episodes": len(false_episodes),
        "false_alert_episodes_per_site_day": round(len(false_episodes) / site_day_count, 3),
        "early_warnings_issued": warnings_issued,
        "early_warning_precision": round(warnings_on_event / warnings_issued, 3) if warnings_issued else None,
        "status_share": _status_shares(site_days),
        "per_event": per_event,
    }


def describe_without_truth(
    site_days: list[SiteDay], episodes: list[Episode], detector: Detector, baseline_days: list[date]
) -> dict[str, Any]:
    obs = detector.obs
    alert_windows: Counter[str] = Counter()
    for sd in site_days:
        alert_windows[sd.site_id] += sum(a.status == "overcrowding_alert" for a in sd.assessments)
    per_day: Counter[str] = Counter()
    for sd in site_days:
        per_day[sd.day.isoformat()] += sum(a.observed or 0 for a in sd.assessments)
    site_day_count = len(site_days) or 1
    return {
        "sites_assessed": len(obs.sites),
        "windows_assessed": sum(len(sd.assessments) for sd in site_days),
        "status_share": _status_shares(site_days),
        "alert_episodes": len(episodes),
        "alert_episodes_per_site_day": round(len(episodes) / site_day_count, 4),
        "sites_with_any_alert": sum(1 for v in alert_windows.values() if v),
        "early_warnings_issued": sum(w is not None for sd in site_days for w in sd.warnings),
        "top_alert_sites": [
            {"site_id": sid, "name": obs.sites[sid].name, "alert_windows": n}
            for sid, n in alert_windows.most_common(10)
            if n
        ],
        "observed_total_per_replay_day": dict(sorted(per_day.items())),
        "week_to_week_profile_correlation": week_to_week_stability(detector, baseline_days),
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def week_to_week_stability(detector: Detector, baseline_days: list[date]) -> dict[str, Any]:
    """Correlate each site's weekday time-of-day profile between the first two baseline weeks."""
    obs, calendar = detector.obs, detector.calendar
    if len(baseline_days) < 14:
        return {"note": "Needs at least two baseline weeks."}
    first, second = baseline_days[:7], baseline_days[7:14]
    values = []
    for sid in obs.sites:
        profiles = []
        for week in (first, second):
            days = [d for d in week if calendar.day_type(d) == "weekday"]
            profile = []
            for slot in range(obs.slots_per_day):
                vals = [obs.value(sid, d, slot) for d in days]
                vals = [v for v in vals if v is not None]
                profile.append(statistics.fmean(vals) if vals else 0.0)
            profiles.append(profile)
        r = _pearson(*profiles)
        if r is not None:
            values.append(r)
    if not values:
        return {"note": "No site had enough data in both weeks."}
    values.sort()
    return {
        "sites": len(values),
        "median": round(statistics.median(values), 3),
        "p10": round(values[len(values) // 10], 3),
        "note": "Pearson correlation of each site's weekday profile, baseline week 1 vs week 2. "
        "High values mean the usual pattern repeats; low values mean the baseline is less trustworthy there.",
    }
