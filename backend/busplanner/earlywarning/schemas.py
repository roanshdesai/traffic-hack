"""API contract for the early-warning product.

Source of truth for ``docs/API.md`` and ``frontend/src/api/warningTypes.ts``.
Change all three together.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import RoadTraffic

Status = Literal["normal", "elevated", "overcrowding_alert", "insufficient_evidence", "no_data"]
SourceKind = Literal["camera_count", "ticket_sample", "manual_count"]
Coverage = Literal["full_count", "sample"]
BaselineBasis = Literal["site_daytype_slot", "site_daytype_hour", "site_slot_all_days", "none"]
Quality = Literal["high", "medium", "low", "insufficient"]
Trigger = Literal["relative", "threshold"]
Origin = Literal["synthetic", "real"]


class WarningProvenance(BaseModel):
    origin: Origin
    simulated: bool = Field(description="True for synthetic data. The UI must show a banner.")
    label: str
    source_kinds: list[SourceKind]
    built_at: str
    baseline_period: dict[str, str] = Field(description="{start, end} dates used to learn usual levels.")
    replay_period: dict[str, str] = Field(description="{start, end} dates that can be replayed and assessed.")


class Site(BaseModel):
    site_id: str
    name: str
    kind: str = Field(description="bus_stop | terminal | station | other")
    lat: float | None = None
    lon: float | None = None
    source: SourceKind
    coverage: Coverage = Field(description="full_count: every person is meant to be counted. sample: a subset.")
    window_minutes: int
    unit: str = Field(description="What the count measures, e.g. 'people counted' or 'e-ticket boardings'.")
    alert_threshold: int | None = Field(
        default=None, description="Operator-set count threshold (full_count sources only). Not verified capacity."
    )


class Baseline(BaseModel):
    median: float
    low: float = Field(description="Lower edge of the usual range.")
    high: float = Field(description="Upper edge of the usual range.")
    support_days: int
    basis: BaselineBasis
    quality: Quality


class WindowAssessment(BaseModel):
    window_start: str
    window_end: str
    observed: int | None
    baseline: Baseline | None
    ratio: float | None = Field(default=None, description="observed / usual median.")
    z: float | None = Field(default=None, description="Robust distance from usual, in usual-variation units.")
    status: Status
    triggers: list[Trigger] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class Forecast(BaseModel):
    horizon_min: int
    window_start: str
    predicted: float | None
    low: float | None
    high: float | None
    usual: float | None
    status: Status


class EarlyWarning(BaseModel):
    expected_at: str = Field(description="Start of the first window forecast to reach an alert.")
    lead_min: int
    predicted: float
    summary: str


class SiteStatus(BaseModel):
    site: Site
    at: str
    current: WindowAssessment
    forecasts: list[Forecast]
    early_warning: EarlyWarning | None = None


class OverviewResponse(BaseModel):
    at: str = Field(description="Replay time. Only data up to this time is used.")
    provenance: WarningProvenance
    counts: dict[str, int] = Field(description="Sites per current status, plus 'early_warning'.")
    sites: list[SiteStatus] = Field(description="Most urgent first.")
    total_sites: int
    disclaimers: list[str]
    road_traffic: RoadTraffic


class SimulatedEvent(BaseModel):
    """Ground truth injected into synthetic data. Never present for real data."""

    site_id: str
    start: str
    onset: str
    end: str
    kind: str
    description: str


class AlertEpisode(BaseModel):
    site_id: str
    site_name: str
    start: str
    end: str
    peak_observed: int
    peak_ratio: float | None
    triggers: list[Trigger]
    first_warning_at: str | None = Field(default=None, description="When a forecast first predicted it.")
    lead_min: int | None = None
    matched_event: bool | None = Field(
        default=None, description="Synthetic data only: overlaps an injected event. Null for real data."
    )


class TimelineResponse(BaseModel):
    site: Site
    date: str
    windows: list[WindowAssessment]
    episodes: list[AlertEpisode]
    simulated_events: list[SimulatedEvent]
    provenance: WarningProvenance


class AlertsResponse(BaseModel):
    date: str | None
    episodes: list[AlertEpisode]
    provenance: WarningProvenance


class SiteListResponse(BaseModel):
    query: str
    sites: list[Site]
    total: int


class EvaluationResponse(BaseModel):
    provenance: WarningProvenance
    ground_truth: Literal["simulated_events", "none"]
    caveat: str
    metrics: dict
    notes: list[str]


class WarningMeta(BaseModel):
    product: str
    provenance: WarningProvenance
    default_at: str
    counts: dict[str, int]
    settings: dict
    status_definitions: dict[str, str]
    disclaimers: list[str]
    road_traffic: RoadTraffic
    planner_available: bool
