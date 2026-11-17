"""Thresholds for detection and forecasting.

All values are uncalibrated prototype defaults chosen to be explainable. They
are published through ``GET /api/meta`` so every result can be traced back.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from ..config import REPO_ROOT

FIXTURE_DIR = REPO_ROOT / "fixtures" / "synthetic" / "earlywarning"
DEFAULT_DATASET_DIR = REPO_ROOT / "data" / "processed" / "earlywarning-synthetic"


@dataclass(frozen=True)
class WarningConfig:
    #: Slots within this many minutes either side are pooled into a slot's usual level.
    neighbour_minutes: int = 15
    #: A baseline cell needs data from at least this many days.
    baseline_min_days: int = 3
    #: Below this usual count, relative changes are too noisy to call an alert;
    #: the status is capped at "elevated".
    min_expected: float = 5.0
    #: Never raise an alert on fewer people/records than this.
    min_observed_for_alert: int = 10
    #: Never call a window "busier than usual" on fewer people/records than this.
    min_observed_for_elevated: int = 5
    #: "Busier than usual": both conditions must hold.
    elevated_ratio: float = 1.3
    elevated_z: float = 2.0
    #: "Overcrowding alert" (relative): both conditions must hold.
    alert_ratio: float = 1.6
    alert_z: float = 4.0
    #: Camera windows with detector confidence below this are excluded and reported.
    min_confidence: float = 0.5
    #: How far ahead to forecast. Steps are whole windows: 4 x 15 min for cameras, 1 x 60 min for tickets.
    max_horizon_min: int = 60
    #: Damped-trend forecast: smoothing of the recent ratio and its slope, and damping per step.
    level_alpha: float = 0.6
    trend_beta: float = 0.4
    trend_damping: float = 0.8
    #: Early warning needs the previous window at least this far above usual as well (a sustained rise).
    warning_previous_ratio: float = 1.15
    #: Recent windows considered by the forecast.
    recent_windows: int = 4

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceSpec:
    """How one input source is turned into observations."""

    kind: str  # camera_count | ticket_sample | manual_count
    coverage: str  # full_count | sample
    window_minutes: int
    service_start_min: int  # first window start, minutes after midnight
    service_end_min: int  # last window end
    #: For samples, a missing window inside service hours means zero records.
    #: For counters, it means no data (sensor gap).
    missing_means_zero: bool


CAMERA_SOURCE = SourceSpec("camera_count", "full_count", 15, 6 * 60, 22 * 60, False)
TICKET_SOURCE = SourceSpec("ticket_sample", "sample", 60, 5 * 60, 23 * 60, True)


DAY_TYPE_WORDS = {
    "weekday": "weekday",
    "weekend_or_holiday": "weekend or holiday",
    "saturday": "Saturday",
    "sunday_or_holiday": "Sunday or holiday",
}


@dataclass(frozen=True)
class Calendar:
    """Day typing. Holidays are treated like Sundays.

    ``split_saturday`` gives Saturday its own usual levels. Use it when Saturday
    behaves like neither a weekday nor a Sunday (true of the Oct 2026 Delhi
    ticket data, where Saturday volume sits between the two).
    """

    holidays: frozenset[date] = field(default_factory=frozenset)
    split_saturday: bool = False

    def day_type(self, day: date) -> str:
        if self.split_saturday:
            if day in self.holidays or day.weekday() == 6:
                return "sunday_or_holiday"
            return "saturday" if day.weekday() == 5 else "weekday"
        return "weekend_or_holiday" if day.weekday() >= 5 or day in self.holidays else "weekday"


def dataset_dir_from_env() -> Path:
    return Path(os.environ.get("EARLYWARNING_DATASET_DIR", str(DEFAULT_DATASET_DIR)))


STATUS_DEFINITIONS: dict[str, str] = {
    "normal": "Within the usual range for this place, day type and time.",
    "elevated": "Clearly busier than usual for this place and time.",
    "overcrowding_alert": "Far above the usual level for this place and time, or at or above an "
    "operator-set count threshold.",
    "insufficient_evidence": "Not enough history for this place and time to judge.",
    "no_data": "No usable observation for this window (sensor gap, excluded reading or outside coverage).",
}

DISCLAIMERS: tuple[str, ...] = (
    "Replay of recorded data, not a live feed.",
    "Statuses compare a count with this place's own history. They are estimates, not verified real-world conditions.",
    "Camera counts are produced by counting software and are estimates. No images or identities are stored or used.",
    "Ticket records are a sample of passengers, not a headcount: they can show unusual activity, not "
    "how full a place is.",
    "Road traffic is a separate context signal and is not part of any crowding status.",
)

SIMULATED_DISCLAIMER = (
    "SIMULATED DATA: the sites, counts and events in this dataset are synthetic test fixtures. "
    "Nothing shown describes real places or real crowds."
)
