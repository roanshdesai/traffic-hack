/**
 * API contract types.
 *
 * Mirrors `backend/busplanner/schemas.py` one to one (see also `docs/API.md`).
 * Change all three in the same PR.
 */

export type CrowdingLevel = "lower" | "typical" | "higher" | "insufficient_evidence";
export type EvidenceQuality = "high" | "medium" | "low" | "insufficient";
export type EvidenceBasis =
  | "segment_period_daytype"
  | "segment_period"
  | "segment_all_day"
  | "none";
export type OptionKind = "fastest" | "balanced" | "less_crowded";
export type OptionStatus = "ok" | "insufficient_evidence" | "no_journey";
export type DataSource = "synthetic" | "real" | "none";

export interface Provenance {
  gtfs_source: DataSource;
  tickets_source: DataSource;
  /** True when any input is synthetic. The UI must show a banner. */
  simulated: boolean;
  label: string;
  built_at: string;
}

export interface StopRef {
  stop_id: string;
  name: string;
  lat: number;
  lon: number;
}

/** A searchable origin/destination: same-named stops that sit close together. */
export interface Place {
  place_id: string;
  name: string;
  stop_ids: string[];
  lat: number;
  lon: number;
  /** Short names of routes serving the place. */
  routes: string[];
}

export interface StopSearchResponse {
  query: string;
  places: Place[];
}

export interface Evidence {
  quality: EvidenceQuality;
  /** Which pooling level produced the estimate; "none" means no usable fallback. */
  basis: EvidenceBasis;
  /** Ticket records supporting the estimate (support count). */
  ticket_count: number;
  rider_count: number;
  /** Distinct service days that contributed samples. */
  service_days: number;
  /** Scheduled trips through the segment over the sampled days. */
  scheduled_trips: number;
  min_tickets_required: number;
}

export interface SegmentCrowding {
  level: CrowdingLevel;
  /**
   * 0..1 rank among supported segment-periods in the dataset.
   * A rank, NOT occupancy and NOT a percentage full. Never render it as a percentage.
   */
  relative_rank: number | null;
  evidence: Evidence;
}

export interface Segment {
  from_stop_id: string;
  to_stop_id: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  scheduled_min: number;
  crowding: SegmentCrowding;
}

export interface LegStop {
  stop_id: string;
  name: string;
  lat: number;
  lon: number;
  sequence: number;
  scheduled_arrival: string;
  scheduled_departure: string;
}

export interface RouteRef {
  route_id: string;
  short_name: string;
  long_name: string;
}

export interface BusLeg {
  type: "bus";
  route: RouteRef;
  trip_id: string;
  headsign: string;
  direction_id: string;
  board_stop: StopRef;
  alight_stop: StopRef;
  scheduled_departure: string;
  scheduled_arrival: string;
  scheduled_min: number;
  /** Ordered stops from boarding to alighting, inclusive. */
  stops: LegStop[];
  /** stops.length - 1 entries; segments[i] runs stops[i] -> stops[i + 1]. */
  segments: Segment[];
}

export interface TransferLeg {
  type: "transfer";
  from_stop: StopRef;
  to_stop: StopRef;
  /** Scheduled gap between arriving and the next departure. */
  scheduled_min: number;
  walk_m: number;
}

export type Leg = BusLeg | TransferLeg;

export interface CrowdingSummary {
  level: CrowdingLevel;
  relative_rank: number | null;
  evidence_quality: EvidenceQuality;
  /** Share of scheduled in-vehicle minutes that has evidence (0..1). */
  coverage: number;
  covered_min: number;
  in_vehicle_min: number;
  min_segment_ticket_count: number;
  segment_counts: Record<string, number>;
}

export interface Journey {
  journey_id: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  /** First boarding to final alighting, scheduled. */
  scheduled_travel_min: number;
  /** Requested time to first scheduled departure. */
  initial_wait_min: number;
  /** Requested time to scheduled arrival. */
  total_min: number;
  transfers: number;
  legs: Leg[];
  crowding: CrowdingSummary;
}

export interface Reason {
  summary: string;
  details: string[];
  /** Informational; keys may grow. Do not build layout on them. */
  metrics: Record<string, unknown>;
}

export interface JourneyOption {
  kind: OptionKind;
  label: string;
  status: OptionStatus;
  journey: Journey | null;
  reason: Reason;
  same_journey_as: OptionKind | null;
}

export interface JourneyRequestEcho {
  origin: Place;
  destination: Place;
  date: string;
  time: string;
  day_type: string;
  period: string;
}

/** Road traffic is deliberately a separate object from passenger crowding. */
export interface RoadTraffic {
  status: "not_configured" | "unavailable" | "ok";
  note: string;
}

export interface JourneyResponse {
  request: JourneyRequestEcho;
  status: "ok" | "no_journey";
  message: string;
  /** Always fastest, balanced, less_crowded in order. */
  options: JourneyOption[];
  candidates_considered: number;
  provenance: Provenance;
  disclaimers: string[];
  road_traffic: RoadTraffic;
}

export interface PeriodInfo {
  id: string;
  label: string;
  start: string;
  end: string;
}

export interface FallbackInfo {
  basis?: string;
  description?: string;
  quality_cap?: string;
  [key: string]: string | undefined;
}

export interface MetaResponse {
  provenance: Provenance;
  counts: Record<string, number>;
  service_date_range: { start?: string | null; end?: string | null };
  /** A date/time inside the feed's service range, for UI defaults. */
  suggested_query: { date?: string; time?: string } | null;
  periods: PeriodInfo[];
  day_types: string[];
  settings: Record<string, unknown>;
  fallbacks: FallbackInfo[];
  disclaimers: string[];
  road_traffic: RoadTraffic;
}

export interface HealthResponse {
  status: "ok" | "no_dataset";
  dataset_dir: string;
  detail: string | null;
}

export interface ErrorDetail {
  code: string;
  message: string;
}

/* ------------------------------------------------------------------ */
/* Data-quality report. Typed loosely on purpose: the pipeline owns    */
/* this document and may add fields (see docs/DATA.md).                */
/* ------------------------------------------------------------------ */

export type IssueSeverity = "error" | "warning" | "info";

export interface QualityIssue {
  code: string;
  severity: IssueSeverity;
  file?: string | null;
  count: number;
  message: string;
  samples?: unknown[];
}

export interface QualitySummary {
  errors: number;
  warnings: number;
  infos: number;
}

export interface QualitySection {
  summary?: QualitySummary;
  issues?: QualityIssue[];
  [key: string]: unknown;
}

export interface MatchingReport {
  total?: number;
  by_status?: Record<string, number>;
  /** Share of ticket records matched, 0..1. */
  match_rate?: number | null;
  [key: string]: unknown;
}

export type BlockedItem = string | { code?: string; title?: string; message?: string; [key: string]: unknown };

export interface DataQualityReport {
  generated_at?: string;
  provenance?: Provenance;
  gtfs?: QualitySection;
  tickets?: QualitySection;
  matching?: MatchingReport;
  crowding?: Record<string, unknown>;
  blocked?: BlockedItem[];
}
