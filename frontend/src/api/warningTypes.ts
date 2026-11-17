/**
 * API contract types for the overcrowding early warning (the main product).
 *
 * Mirrors `backend/busplanner/earlywarning/schemas.py` one to one (see also
 * `docs/API.md`). Change all three in the same PR.
 *
 * Times are local Asia/Kolkata wall-clock strings without an offset, `YYYY-MM-DDTHH:MM`.
 * All data is recorded and replayed; nothing is a live feed.
 */
import type { IssueSeverity, QualitySummary, RoadTraffic } from "./types";

export type Status = "normal" | "elevated" | "overcrowding_alert" | "insufficient_evidence" | "no_data";
export type SourceKind = "camera_count" | "ticket_sample" | "manual_count";
export type Coverage = "full_count" | "sample";
export type BaselineBasis = "site_daytype_slot" | "site_daytype_hour" | "site_slot_all_days" | "none";
export type Quality = "high" | "medium" | "low" | "insufficient";
export type Trigger = "relative" | "threshold";
export type Origin = "synthetic" | "real";

export interface DateRange {
  start: string;
  end: string;
}

export interface WarningProvenance {
  origin: Origin;
  /** True for synthetic data. The UI must show a banner. */
  simulated: boolean;
  label: string;
  source_kinds: SourceKind[];
  built_at: string;
  /** Dates used to learn usual levels. */
  baseline_period: DateRange;
  /** Dates that can be replayed and assessed. */
  replay_period: DateRange;
}

export interface Site {
  site_id: string;
  name: string;
  /** bus_stop | terminal | station | other */
  kind: string;
  lat: number | null;
  lon: number | null;
  source: SourceKind;
  /** full_count: every person is meant to be counted. sample: a subset. */
  coverage: Coverage;
  window_minutes: number;
  /** What the count measures, e.g. "people counted" or "e-ticket boardings". */
  unit: string;
  /** Operator-set count threshold (full_count sources only). Not a verified capacity. */
  alert_threshold: number | null;
}

export interface Baseline {
  median: number;
  /** Lower edge of the usual range. */
  low: number;
  /** Upper edge of the usual range. */
  high: number;
  support_days: number;
  basis: BaselineBasis;
  quality: Quality;
}

export interface WindowAssessment {
  window_start: string;
  window_end: string;
  observed: number | null;
  baseline: Baseline | null;
  /** observed / usual median. */
  ratio: number | null;
  /** Robust distance from usual, in usual-variation units. */
  z: number | null;
  status: Status;
  triggers: Trigger[];
  reasons: string[];
}

export interface Forecast {
  horizon_min: number;
  window_start: string;
  predicted: number | null;
  low: number | null;
  high: number | null;
  usual: number | null;
  status: Status;
}

export interface EarlyWarning {
  /** Start of the first window forecast to reach an alert. */
  expected_at: string;
  lead_min: number;
  predicted: number;
  summary: string;
}

export interface SiteStatus {
  site: Site;
  at: string;
  current: WindowAssessment;
  forecasts: Forecast[];
  early_warning: EarlyWarning | null;
}

export interface OverviewResponse {
  /** Replay time. Only data up to this time is used. */
  at: string;
  provenance: WarningProvenance;
  /** Sites per current status, plus "early_warning". */
  counts: Record<string, number>;
  /** Most urgent first. */
  sites: SiteStatus[];
  total_sites: number;
  disclaimers: string[];
  road_traffic: RoadTraffic;
}

/** Ground truth injected into synthetic data. Never present for real data. */
export interface SimulatedEvent {
  site_id: string;
  start: string;
  onset: string;
  end: string;
  kind: string;
  description: string;
}

export interface AlertEpisode {
  site_id: string;
  site_name: string;
  start: string;
  end: string;
  peak_observed: number;
  peak_ratio: number | null;
  triggers: Trigger[];
  /** When a forecast first predicted it. */
  first_warning_at: string | null;
  lead_min: number | null;
  /** Synthetic data only: overlaps an injected event. Null for real data. */
  matched_event: boolean | null;
}

export interface TimelineResponse {
  site: Site;
  date: string;
  windows: WindowAssessment[];
  episodes: AlertEpisode[];
  simulated_events: SimulatedEvent[];
  provenance: WarningProvenance;
}

export interface AlertsResponse {
  date: string | null;
  episodes: AlertEpisode[];
  provenance: WarningProvenance;
}

export interface SiteListResponse {
  query: string;
  sites: Site[];
  total: number;
}

export interface EvaluationResponse {
  provenance: WarningProvenance;
  ground_truth: "simulated_events" | "none";
  caveat: string;
  /** Free-form numbers; render key/value pairs. */
  metrics: Record<string, unknown>;
  notes: string[];
}

export interface WarningMeta {
  product: string;
  provenance: WarningProvenance;
  default_at: string;
  counts: Record<string, number>;
  settings: Record<string, unknown>;
  status_definitions: Record<string, string>;
  disclaimers: string[];
  road_traffic: RoadTraffic;
  planner_available: boolean;
}

/* ---- Data-quality report of the warning build (typed loosely; read defensively). ---- */

export interface WarningQualityIssue {
  code: string;
  severity: IssueSeverity;
  file?: string | null;
  count: number;
  message: string;
  samples?: unknown[];
}

export interface WarningQualitySource {
  name?: string;
  kind?: string;
  summary?: QualitySummary;
  issues?: WarningQualityIssue[];
  rows_total?: number;
  rows_valid?: number;
  [key: string]: unknown;
}

export interface WarningDataQualityReport {
  generated_at?: string;
  provenance?: Partial<WarningProvenance>;
  sources: WarningQualitySource[];
  model?: Record<string, unknown>;
  blocked?: Array<string | Record<string, unknown>>;
  [key: string]: unknown;
}
