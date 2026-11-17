"""Usual levels, current status, short-horizon forecast and early warning.

Usual level ("baseline")
------------------------
For each site, day type (weekday / weekend-or-holiday) and time slot, the
median count over the baseline days (pooling the neighbouring slots within
``neighbour_minutes``, 15 min by default, so each usual level rests on three
times as many readings), and a robust spread::

    sigma = max(1.4826 * MAD, sqrt(median), 1)

The ``sqrt(median)`` floor stops a very regular site from turning small wobbles
into alerts. When a slot has too few days of history, it falls back to the
same hour (slots pooled), then to the same slot on all days. Otherwise there is
no baseline and the status is "not enough history".

Status
------
``ratio = observed / median`` and ``z = (observed - median) / sigma``.

* overcrowding alert: ratio >= 1.6 and z >= 4 and observed >= 10, with a usual
  level of at least 5; or the count is at or above an operator-set threshold
  (full-count sources only).
* elevated: ratio >= 1.3 and z >= 2 and observed >= 5. An alert-sized jump on a
  usual level below 5 is capped here because the numbers are too small to judge.

Early warning: only when the current window is elevated on a usual level of at
least 5, the previous window was also above usual, the ratio is rising, and the
forecast reaches an alert within the next hour.
* normal otherwise.

Forecast
--------
A damped-trend model on the ratio to usual over the last few windows: it
assumes the current departure from usual continues, with its growth fading
each step. The forecast count is that ratio times the usual level of the target
window. It cannot foresee a surge that has not started yet.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .config import DAY_TYPE_WORDS, Calendar, WarningConfig
from .sources import ObservationSet, SiteInfo

BASES = ("site_daytype_slot", "site_daytype_hour", "site_slot_all_days")


@dataclass(frozen=True)
class BaselineCell:
    median: float
    sigma: float
    support_days: int
    basis: str
    quality: str

    @property
    def low(self) -> float:
        return max(0.0, self.median - self.sigma)

    @property
    def high(self) -> float:
        return self.median + self.sigma


@dataclass
class Assessment:
    site_id: str
    window_start: datetime
    window_end: datetime
    observed: int | None
    baseline: BaselineCell | None
    ratio: float | None
    z: float | None
    status: str
    triggers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class ForecastPoint:
    horizon_min: int
    window_start: datetime
    predicted: float | None
    low: float | None
    high: float | None
    usual: float | None
    status: str


@dataclass
class Warning:
    expected_at: datetime
    lead_min: int
    predicted: float
    summary: str


def _sigma(values: list[float], median: float) -> float:
    mad = statistics.median(abs(v - median) for v in values)
    return max(1.4826 * mad, math.sqrt(max(median, 0.0)), 1.0)


def _cell(values: list[float], days: int, basis: str, cfg: WarningConfig) -> BaselineCell | None:
    if days < cfg.baseline_min_days or not values:
        return None
    median = statistics.median(values)
    if basis == "site_daytype_slot":
        quality = "high" if days >= 8 else "medium"
    elif basis == "site_daytype_hour":
        quality = "medium" if days >= 8 else "low"
    else:
        quality = "low"
    return BaselineCell(round(median, 2), round(_sigma(values, median), 2), days, basis, quality)


class Baselines:
    def __init__(self, cells: dict[tuple, BaselineCell] | None = None) -> None:
        self.cells: dict[tuple, BaselineCell] = cells or {}

    @classmethod
    def build(cls, obs: ObservationSet, baseline_days: list[date], calendar: Calendar, cfg: WarningConfig) -> Baselines:
        per_slot: dict[tuple, dict[date, float]] = defaultdict(dict)
        per_hour: dict[tuple, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))
        per_all: dict[tuple, list[float]] = defaultdict(list)
        slots_per_hour = max(1, 60 // obs.spec.window_minutes)
        for sid in obs.sites:
            for day in baseline_days:
                day_type = calendar.day_type(day)
                for slot in range(obs.slots_per_day):
                    value = obs.value(sid, day, slot)
                    if value is None:
                        continue
                    per_slot[(sid, day_type, slot)][day] = value
                    per_hour[(sid, day_type, slot // slots_per_hour)][day].append(value)
                    per_all[(sid, slot)].append(value)
        cells: dict[tuple, BaselineCell] = {}
        reach = cfg.neighbour_minutes // obs.spec.window_minutes
        for sid, day_type, slot in list(per_slot):
            values: list[float] = []
            days_seen: set[date] = set()
            for neighbour in range(slot - reach, slot + reach + 1):
                for day, value in per_slot.get((sid, day_type, neighbour), {}).items():
                    values.append(value)
                    days_seen.add(day)
            cell = _cell(values, len(days_seen), BASES[0], cfg)
            if cell:
                cells[(BASES[0], sid, day_type, slot)] = cell
        for (sid, day_type, hour), by_day in per_hour.items():
            values = [v for vs in by_day.values() for v in vs]
            cell = _cell(values, len(by_day), BASES[1], cfg)
            if cell:
                cells[(BASES[1], sid, day_type, hour)] = cell
        for (sid, slot), values in per_all.items():
            cell = _cell(values, len(values), BASES[2], cfg)
            if cell:
                cells[(BASES[2], sid, slot)] = cell
        return cls(cells)

    def lookup(self, site_id: str, day_type: str, slot: int, slots_per_hour: int) -> BaselineCell | None:
        return (
            self.cells.get((BASES[0], site_id, day_type, slot))
            or self.cells.get((BASES[1], site_id, day_type, slot // slots_per_hour))
            or self.cells.get((BASES[2], site_id, slot))
        )

    def to_json(self) -> list:
        return [[*key, c.median, c.sigma, c.support_days, c.quality] for key, c in sorted(self.cells.items())]

    @classmethod
    def from_json(cls, rows: list) -> Baselines:
        cells = {}
        for row in rows:
            basis = row[0]
            width = 4 if basis in BASES[:2] else 3
            key = tuple(row[:width])
            median, sigma, days, quality = row[width:]
            cells[key] = BaselineCell(median, sigma, days, basis, quality)
        return cls(cells)


def _fmt(value: float) -> str:
    return f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}"


class Detector:
    def __init__(
        self,
        obs: ObservationSet,
        baselines: Baselines,
        calendar: Calendar,
        cfg: WarningConfig | None = None,
    ) -> None:
        self.obs = obs
        self.baselines = baselines
        self.calendar = calendar
        self.cfg = cfg or WarningConfig()
        self.window = timedelta(minutes=obs.spec.window_minutes)
        self.slots_per_hour = max(1, 60 // obs.spec.window_minutes)

    # -- classification ---------------------------------------------------
    def classify(
        self, site: SiteInfo, count: float, base: BaselineCell | None
    ) -> tuple[str, list[str], float | None, float | None, bool]:
        """Return (status, triggers, ratio, z, capped_small)."""
        cfg = self.cfg
        triggers: list[str] = []
        threshold_hit = (
            site.coverage == "full_count" and site.alert_threshold is not None and count >= site.alert_threshold
        )
        if base is None:
            return ("overcrowding_alert" if threshold_hit else "insufficient_evidence",
                    ["threshold"] if threshold_hit else [], None, None, False)  # fmt: skip
        ratio = count / base.median if base.median > 0 else None
        z = (count - base.median) / base.sigma
        big = ratio is not None and ratio >= cfg.alert_ratio and z >= cfg.alert_z
        busy = (
            (ratio is None or ratio >= cfg.elevated_ratio)
            and z >= cfg.elevated_z
            and count >= cfg.min_observed_for_elevated
        )
        capped = False
        if big and count >= cfg.min_observed_for_alert and base.median >= cfg.min_expected:
            triggers.append("relative")
        elif big or (busy and base.median < cfg.min_expected and z >= cfg.alert_z):
            capped = base.median < cfg.min_expected
        if threshold_hit:
            triggers.append("threshold")
        if triggers:
            status = "overcrowding_alert"
        elif busy:
            status = "elevated"
        else:
            status = "normal"
        return status, triggers, ratio, z, capped

    def baseline_for(self, site_id: str, moment: datetime) -> BaselineCell | None:
        slot = self.obs.slot_of(moment)
        if slot is None:
            return None
        return self.baselines.lookup(site_id, self.calendar.day_type(moment.date()), slot, self.slots_per_hour)

    def assess(self, site_id: str, moment: datetime) -> Assessment:
        site = self.obs.sites[site_id]
        day, slot = moment.date(), self.obs.slot_of(moment)
        start = self.obs.window_start(day, slot) if slot is not None else moment
        end = start + self.window
        base = self.baseline_for(site_id, start) if slot is not None else None
        observed = self.obs.value(site_id, day, slot) if slot is not None else None
        clock = start.strftime("%H:%M")
        day_word = DAY_TYPE_WORDS[self.calendar.day_type(day)]
        if observed is None:
            reason = ("No usable count for this window (sensor gap or a reading excluded for low confidence)."
                      if slot is not None else "Outside the hours this source covers.")  # fmt: skip
            return Assessment(site_id, start, end, None, base, None, None, "no_data", [], [reason])
        status, triggers, ratio, z, capped = self.classify(site, observed, base)
        reasons: list[str] = []
        if base is None:
            reasons.append(
                f"{observed} {site.unit}. Not enough history for a {day_word} at {clock} "
                f"(needs {self.cfg.baseline_min_days} days)."
            )
        else:
            times = f"; {ratio:.1f}x usual" if ratio is not None else ""
            reasons.append(
                f"{observed} {site.unit} vs usually {_fmt(base.median)} (usual range {_fmt(base.low)}-"
                f"{_fmt(base.high)}) for a {day_word} at {clock}{times}."
            )
            if base.basis != BASES[0]:
                pooled = "the same hour" if base.basis == BASES[1] else "all days at this time"
                reasons.append(f"Usual level pooled over {pooled} because this exact slot has little history.")
        if "relative" in triggers:
            reasons.append("Far above this place's own history for this time.")
        if "threshold" in triggers:
            reasons.append(
                f"At or above the operator-set threshold of {site.alert_threshold} "
                "(a setting, not a verified capacity)."
            )
        if capped:
            reasons.append(
                f"Large relative jump, but the usual level is below {_fmt(self.cfg.min_expected)}: too few to call "
                "an alert."
            )
        if site.coverage == "sample":
            reasons.append("Ticket records are a sample of passengers, not a headcount.")
        return Assessment(
            site_id,
            start,
            end,
            observed,
            base,
            round(ratio, 2) if ratio is not None else None,
            round(z, 2) if base is not None else None,
            status,
            triggers,
            reasons,
        )

    # -- forecasting ------------------------------------------------------
    def recent_ratios(self, site_id: str, moment: datetime) -> list[float]:
        ratios: list[float] = []
        for back in range(self.cfg.recent_windows - 1, -1, -1):
            t = moment - back * self.window
            if t.date() != moment.date():
                continue
            slot = self.obs.slot_of(t)
            if slot is None:
                continue
            value = self.obs.value(site_id, t.date(), slot)
            base = self.baseline_for(site_id, t)
            if value is None or base is None:
                continue
            ratios.append(value / max(base.median, 1.0))
        return ratios

    def forecast(self, site_id: str, moment: datetime) -> list[ForecastPoint]:
        cfg = self.cfg
        site = self.obs.sites[site_id]
        ratios = self.recent_ratios(site_id, moment)
        slot = self.obs.slot_of(moment)
        if slot is None:
            return []
        now = self.obs.window_start(moment.date(), slot)
        level = trend = 0.0
        if ratios:
            level = ratios[0]
            for r in ratios[1:]:
                previous = level
                level = cfg.level_alpha * r + (1 - cfg.level_alpha) * (level + trend)
                trend = cfg.trend_beta * (level - previous) + (1 - cfg.trend_beta) * trend
        points: list[ForecastPoint] = []
        for step in range(1, max(1, cfg.max_horizon_min // self.obs.spec.window_minutes) + 1):
            target = now + step * self.window
            if target.date() != now.date() or self.obs.slot_of(target) is None:
                break
            base = self.baseline_for(site_id, target)
            horizon = step * self.obs.spec.window_minutes
            if not ratios or base is None:
                points.append(ForecastPoint(horizon, target, None, None, None,
                                            base.median if base else None, "insufficient_evidence"))  # fmt: skip
                continue
            damping = sum(cfg.trend_damping**i for i in range(1, step + 1))
            ratio = max(0.0, level + trend * damping)
            usual = max(base.median, 1.0)
            predicted = ratio * usual
            spread = base.sigma * (1 + 0.25 * step) + abs(trend) * damping * usual
            status, _triggers, _r, _z, _capped = self.classify(site, round(predicted), base)
            points.append(
                ForecastPoint(
                    horizon,
                    target,
                    round(predicted, 1),
                    round(max(0.0, predicted - spread), 1),
                    round(predicted + spread, 1),
                    base.median,
                    status,
                )
            )
        return points

    def early_warning(self, current: Assessment, forecasts: list[ForecastPoint]) -> Warning | None:
        """Warn only when a rise has already started and is still climbing.

        Requires the current window to be "elevated", the window before it to be
        above usual as well, and the ratio to be rising. One noisy window in an
        otherwise normal day cannot trigger a warning.
        """
        if current.status != "elevated" or current.baseline is None or current.baseline.median < self.cfg.min_expected:
            return None
        ratios = self.recent_ratios(current.site_id, current.window_start)
        if len(ratios) < 2 or ratios[-1] <= ratios[-2] or ratios[-2] < self.cfg.warning_previous_ratio:
            return None
        for point in forecasts:
            if point.status == "overcrowding_alert" and point.predicted is not None:
                clock = point.window_start.strftime("%H:%M")
                return Warning(
                    point.window_start,
                    point.horizon_min,
                    point.predicted,
                    f"If the current rise continues, an overcrowding alert is expected around {clock} "
                    f"(in {point.horizon_min} min). This is a forecast, not an observation.",
                )
        return None
