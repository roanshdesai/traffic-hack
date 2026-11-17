"""API contract (Pydantic models).

This file is the single source of truth for the HTTP contract. ``docs/API.md``
describes it for humans and ``frontend/src/api/types.ts`` mirrors it for the UI.
Change all three together.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CrowdingLevel = Literal["lower", "typical", "higher", "insufficient_evidence"]
EvidenceQuality = Literal["high", "medium", "low", "insufficient"]
EvidenceBasis = Literal["segment_period_daytype", "segment_period", "segment_all_day", "none"]
OptionKind = Literal["fastest", "balanced", "less_crowded"]
OptionStatus = Literal["ok", "insufficient_evidence", "no_journey"]
DataSource = Literal["synthetic", "real", "none"]


class Provenance(BaseModel):
    gtfs_source: DataSource
    tickets_source: DataSource
    simulated: bool = Field(description="True when any input is synthetic. UI must show a banner.")
    label: str = Field(description="Human-readable dataset label.")
    built_at: str


class StopRef(BaseModel):
    stop_id: str
    name: str
    lat: float
    lon: float


class Place(BaseModel):
    """A searchable origin/destination: same-named stops that sit close together."""

    place_id: str
    name: str
    stop_ids: list[str]
    lat: float
    lon: float
    routes: list[str] = Field(description="Short names of routes serving the place.")


class StopSearchResponse(BaseModel):
    query: str
    places: list[Place]


class Evidence(BaseModel):
    quality: EvidenceQuality
    basis: EvidenceBasis = Field(
        description="Which pooling level produced the estimate; 'none' means no usable fallback."
    )
    ticket_count: int = Field(description="Ticket records supporting the estimate (support count).")
    rider_count: int = Field(description="Sum of passenger counts on those tickets.")
    service_days: int = Field(description="Distinct service days that contributed samples.")
    scheduled_trips: int = Field(
        description="Scheduled trips through the segment over the sampled days (the denominator)."
    )
    min_tickets_required: int


class SegmentCrowding(BaseModel):
    level: CrowdingLevel
    relative_rank: float | None = Field(
        default=None,
        description=(
            "0..1 rank of this segment-period among supported segment-periods in the dataset. "
            "A rank, NOT occupancy and NOT a percentage full. Null when evidence is insufficient."
        ),
    )
    evidence: Evidence


class Segment(BaseModel):
    from_stop_id: str
    to_stop_id: str
    scheduled_departure: str
    scheduled_arrival: str
    scheduled_min: float
    crowding: SegmentCrowding


class LegStop(BaseModel):
    stop_id: str
    name: str
    lat: float
    lon: float
    sequence: int
    scheduled_arrival: str
    scheduled_departure: str


class RouteRef(BaseModel):
    route_id: str
    short_name: str
    long_name: str


class BusLeg(BaseModel):
    type: Literal["bus"] = "bus"
    route: RouteRef
    trip_id: str
    headsign: str
    direction_id: str
    board_stop: StopRef
    alight_stop: StopRef
    scheduled_departure: str
    scheduled_arrival: str
    scheduled_min: float
    stops: list[LegStop] = Field(description="Ordered stops from boarding to alighting, inclusive.")
    segments: list[Segment] = Field(description="len(stops) - 1 consecutive stop-to-stop segments.")


class TransferLeg(BaseModel):
    type: Literal["transfer"] = "transfer"
    from_stop: StopRef
    to_stop: StopRef
    scheduled_min: float = Field(description="Scheduled gap between arriving and the next departure.")
    walk_m: float


class CrowdingSummary(BaseModel):
    level: CrowdingLevel
    relative_rank: float | None = Field(
        default=None, description="Time-weighted mean of segment ranks over segments with evidence."
    )
    evidence_quality: EvidenceQuality
    coverage: float = Field(description="Share of scheduled in-vehicle minutes that has evidence (0..1).")
    covered_min: float
    in_vehicle_min: float
    min_segment_ticket_count: int = Field(
        description="Smallest support count among the segments that have evidence (0 if none)."
    )
    segment_counts: dict[str, int] = Field(description="Number of segments at each crowding level.")


class Journey(BaseModel):
    journey_id: str
    scheduled_departure: str
    scheduled_arrival: str
    scheduled_travel_min: float = Field(description="First boarding to final alighting, scheduled.")
    initial_wait_min: float = Field(description="Requested time to first scheduled departure.")
    total_min: float = Field(description="Requested time to scheduled arrival.")
    transfers: int
    legs: list[BusLeg | TransferLeg]
    crowding: CrowdingSummary


class Reason(BaseModel):
    summary: str = Field(description="One sentence explaining why this journey got this ranking.")
    details: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class JourneyOption(BaseModel):
    kind: OptionKind
    label: str
    status: OptionStatus
    journey: Journey | None = None
    reason: Reason
    same_journey_as: OptionKind | None = Field(
        default=None, description="Set when this option picked the same journey as an earlier one."
    )


class JourneyRequestEcho(BaseModel):
    origin: Place
    destination: Place
    date: str
    time: str
    day_type: str
    period: str


class RoadTraffic(BaseModel):
    """Road traffic is deliberately a separate object from passenger crowding."""

    status: Literal["not_configured", "unavailable", "ok"] = "not_configured"
    note: str


class JourneyResponse(BaseModel):
    request: JourneyRequestEcho
    status: Literal["ok", "no_journey"]
    message: str
    options: list[JourneyOption] = Field(description="Always fastest, balanced, less_crowded in order.")
    candidates_considered: int
    provenance: Provenance
    disclaimers: list[str]
    road_traffic: RoadTraffic


class PeriodInfo(BaseModel):
    id: str
    label: str
    start: str
    end: str


class MetaResponse(BaseModel):
    provenance: Provenance
    counts: dict[str, int]
    service_date_range: dict[str, str | None]
    suggested_query: dict[str, str] | None = Field(
        default=None, description="A date/time inside the feed's service range, for UI defaults."
    )
    periods: list[PeriodInfo]
    day_types: list[str]
    settings: dict[str, Any]
    fallbacks: list[dict[str, str]]
    disclaimers: list[str]
    road_traffic: RoadTraffic


class HealthResponse(BaseModel):
    status: Literal["ok", "no_dataset"]
    dataset_dir: str
    detail: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
