"""Tunable defaults for the pipeline and planner.

Every number here is a prototype default chosen for explainability, not a
calibrated value. They are surfaced through ``GET /api/meta`` so the UI and
reviewers can see exactly which thresholds produced a result.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FIXTURE_DIR = REPO_ROOT / "fixtures" / "synthetic"
DEFAULT_DATASET_DIR = REPO_ROOT / "data" / "processed" / "synthetic"

#: Naive timestamps in ticket files are interpreted in this zone.
LOCAL_TZ = "Asia/Kolkata"
LOCAL_UTC_OFFSET = "+05:30"

#: Loose bounding box around the Delhi NCR, used only to *warn* about stops
#: that are probably mis-geocoded. (min_lat, max_lat, min_lon, max_lon)
DELHI_BBOX = (28.20, 29.00, 76.70, 77.70)

#: Time-of-day periods used to bucket ticket samples. (id, label, start, end)
#: as minutes after midnight, end exclusive. ``late`` wraps past midnight.
PERIODS: tuple[tuple[str, str, int, int], ...] = (
    ("early", "Early morning", 4 * 60, 7 * 60),
    ("am_peak", "Morning peak", 7 * 60, 11 * 60),
    ("midday", "Midday", 11 * 60, 16 * 60),
    ("pm_peak", "Evening peak", 16 * 60, 21 * 60),
    ("late", "Late evening / night", 21 * 60, 28 * 60),
)

DAY_TYPES = ("weekday", "weekend")


def period_for_minute(minute_of_day: int) -> str:
    """Return the period id for a time expressed as minutes after midnight.

    GTFS times may exceed 24:00; they are folded onto the clock first.
    """
    m = minute_of_day % (24 * 60)
    for pid, _label, start, end in PERIODS:
        if start <= m < end or start <= m + 24 * 60 < end:
            return pid
    return "late"


def day_type_for_weekday(weekday: int) -> str:
    """``weekday`` follows ``datetime.date.weekday()`` (Monday == 0)."""
    return "weekend" if weekday >= 5 else "weekday"


@dataclass(frozen=True)
class CrowdingConfig:
    #: Minimum ticket records in a (pooled) cell before any level is reported.
    min_tickets: int = 10
    #: Minimum distinct service days contributing samples to the cell.
    min_service_days: int = 2
    #: Support needed for the top evidence grade.
    strong_tickets: int = 30
    strong_service_days: int = 4
    #: Minimum number of supported cells needed to form a reference distribution.
    min_reference_cells: int = 10
    #: Relative-rank cut-offs. rank < lower_cut -> "lower"; rank >= higher_cut -> "higher".
    lower_cut: float = 1 / 3
    higher_cut: float = 2 / 3


@dataclass(frozen=True)
class PlannerConfig:
    #: How long after the requested time we look for departures.
    search_window_min: int = 60
    max_transfers: int = 1
    #: Minimum scheduled gap required to change buses at the same place.
    min_transfer_min: int = 4
    #: Do not wait longer than this for a connecting bus.
    max_transfer_wait_min: int = 30
    #: Stops with the same normalised name within this radius form one "place".
    place_radius_m: float = 250.0
    #: Share of scheduled in-vehicle minutes that must have crowding evidence
    #: before a journey may be ranked on crowding at all.
    min_evidence_coverage: float = 0.6
    #: Balanced / Less crowded never pick a journey arriving later than
    #: fastest + max(slack_min, slack_ratio * fastest total minutes).
    slack_min: int = 20
    slack_ratio: float = 0.5
    #: Balanced cost = total_min + transfer_penalty * transfers
    #:               + crowding_weight * in_vehicle_min * relative_rank
    transfer_penalty_min: float = 5.0
    crowding_weight: float = 0.6


@dataclass(frozen=True)
class Settings:
    crowding: CrowdingConfig = field(default_factory=CrowdingConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)

    def to_dict(self) -> dict:
        return asdict(self)


def dataset_dir_from_env() -> Path:
    return Path(os.environ.get("BUSPLANNER_DATASET_DIR", str(DEFAULT_DATASET_DIR)))


DISCLAIMERS: tuple[str, ...] = (
    "Times are scheduled times from static GTFS. They are not live arrivals.",
    "Relative crowding is estimated from ticket samples. Ticket samples are not verified "
    "occupancy: this is not a seat count and not a percentage full.",
    "Crowding levels compare a route segment with other segments in the same dataset; they are relative, not absolute.",
    "Road traffic is a separate signal from passenger crowding and is not part of these estimates.",
)

SIMULATED_DISCLAIMER = (
    "SIMULATED DATA: routes, stops, timetables and ticket samples in this dataset are synthetic "
    "fixtures. Nothing shown reflects real Delhi bus services or real crowding."
)
