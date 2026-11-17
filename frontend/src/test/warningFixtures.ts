/**
 * MOCK / SIMULATED test data for the overcrowding monitor. Hand-written to exercise
 * the UI; it does not come from the backend and does not describe any real place or crowd.
 */
import type {
  AlertsResponse,
  Baseline,
  EvaluationResponse,
  OverviewResponse,
  SiteStatus,
  TimelineResponse,
  WarningDataQualityReport,
  WarningMeta,
  WarningProvenance,
  WindowAssessment,
} from "../api/warningTypes";
import type { RoadTraffic } from "../api/types";

const DAY = "2026-11-18";
const at = (hhmm: string) => `${DAY}T${hhmm}`;

export const mockWarningProvenance: WarningProvenance = {
  origin: "synthetic",
  simulated: true,
  label: "SIMULATED camera counts (mock)",
  source_kinds: ["camera_count"],
  built_at: "2026-11-17T09:00:00+05:30",
  baseline_period: { start: "2026-11-02", end: "2026-11-15" },
  replay_period: { start: "2026-11-16", end: "2026-11-22" },
};

export const mockRoadTraffic: RoadTraffic = {
  status: "not_configured",
  note: "Road traffic is not connected in this prototype and no Google API is called.",
};

export const mockWarningDisclaimers = [
  "Replay of recorded data, not a live feed.",
  "Statuses compare a count with this place's own history. They are estimates, not verified real-world conditions.",
  "Road traffic is a separate context signal and is not part of any crowding status.",
];

export const mockWarningMeta: WarningMeta = {
  product: "Overcrowding early warning (prototype)",
  provenance: mockWarningProvenance,
  default_at: at("17:45"),
  counts: { sites: 4 },
  settings: { alert_ratio: 1.6 },
  status_definitions: {},
  disclaimers: mockWarningDisclaimers,
  road_traffic: mockRoadTraffic,
  planner_available: true,
};

const baseline = (median: number, quality: Baseline["quality"] = "high"): Baseline => ({
  median,
  low: median * 0.85,
  high: median * 1.15,
  support_days: 8,
  basis: "site_daytype_slot",
  quality,
});

const stadium: SiteStatus = {
  site: {
    site_id: "MOCK_SITE_04",
    name: "Mock Stadium Stop",
    kind: "bus_stop",
    lat: 28.598,
    lon: 77.192,
    source: "camera_count",
    coverage: "full_count",
    window_minutes: 15,
    unit: "people counted",
    alert_threshold: 150,
  },
  at: at("17:45"),
  current: {
    window_start: at("17:45"),
    window_end: at("18:00"),
    observed: 182,
    baseline: baseline(95),
    ratio: 1.92,
    z: 6.7,
    status: "overcrowding_alert",
    triggers: ["relative", "threshold"],
    reasons: ["182 people counted vs usually 95 (usual range 81-109) for a weekday at 17:45."],
  },
  forecasts: [
    { horizon_min: 15, window_start: at("18:00"), predicted: 190.2, low: 170, high: 210, usual: 98, status: "overcrowding_alert" },
    { horizon_min: 30, window_start: at("18:15"), predicted: 171.3, low: 150, high: 192.6, usual: 101, status: "overcrowding_alert" },
  ],
  early_warning: null,
};

const interchange: SiteStatus = {
  site: {
    site_id: "MOCK_SITE_02",
    name: "Mock Interchange Stop",
    kind: "bus_stop",
    lat: 28.6,
    lon: 77.18,
    source: "camera_count",
    coverage: "full_count",
    window_minutes: 15,
    unit: "people counted",
    alert_threshold: 160,
  },
  at: at("17:45"),
  current: {
    window_start: at("17:45"),
    window_end: at("18:00"),
    observed: 120,
    baseline: baseline(100),
    ratio: 1.2,
    z: 1.4,
    status: "normal",
    triggers: [],
    reasons: ["120 people counted vs usually 100 for a weekday at 17:45."],
  },
  forecasts: [
    { horizon_min: 30, window_start: at("18:15"), predicted: 168, low: 140, high: 196, usual: 102, status: "overcrowding_alert" },
  ],
  early_warning: {
    expected_at: at("18:15"),
    lead_min: 30,
    predicted: 168,
    summary: "If the current rise continues, an overcrowding alert is expected around 18:15 (in 30 min).",
  },
};

const newSite: SiteStatus = {
  site: {
    site_id: "MOCK_SITE_06",
    name: "Mock New Stop",
    kind: "bus_stop",
    lat: null,
    lon: null,
    source: "ticket_sample",
    coverage: "sample",
    window_minutes: 60,
    unit: "e-ticket boardings",
    alert_threshold: null,
  },
  at: at("17:45"),
  current: {
    window_start: at("17:00"),
    window_end: at("18:00"),
    observed: 3,
    baseline: null,
    ratio: null,
    z: null,
    status: "insufficient_evidence",
    triggers: [],
    reasons: ["Fewer than 3 days of history for this time."],
  },
  forecasts: [],
  early_warning: null,
};

const gapSite: SiteStatus = {
  site: {
    site_id: "MOCK_SITE_05",
    name: "Mock College Stop",
    kind: "bus_stop",
    lat: null,
    lon: null,
    source: "camera_count",
    coverage: "full_count",
    window_minutes: 15,
    unit: "people counted",
    alert_threshold: 90,
  },
  at: at("17:45"),
  current: {
    window_start: at("17:45"),
    window_end: at("18:00"),
    observed: null,
    baseline: baseline(40),
    ratio: null,
    z: null,
    status: "no_data",
    triggers: [],
    reasons: ["No usable reading for this window."],
  },
  forecasts: [],
  early_warning: null,
};

export const mockOverview: OverviewResponse = {
  at: at("17:45"),
  provenance: mockWarningProvenance,
  counts: { overcrowding_alert: 1, early_warning: 1, elevated: 0, normal: 1, insufficient_evidence: 1, no_data: 1 },
  sites: [stadium, interchange, newSite, gapSite],
  total_sites: 4,
  disclaimers: mockWarningDisclaimers,
  road_traffic: mockRoadTraffic,
};

function windowsFor(): WindowAssessment[] {
  const out: WindowAssessment[] = [];
  for (let m = 17 * 60; m < 19 * 60; m += 15) {
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    const end = m + 15;
    const ehh = String(Math.floor(end / 60)).padStart(2, "0");
    const emm = String(end % 60).padStart(2, "0");
    const isGap = m === 18 * 60 + 30;
    const observed = isGap ? null : m >= 17 * 60 + 45 ? 180 : 100;
    out.push({
      window_start: at(`${hh}:${mm}`),
      window_end: at(`${ehh}:${emm}`),
      observed,
      baseline: baseline(95),
      ratio: observed === null ? null : observed / 95,
      z: null,
      status: isGap ? "no_data" : observed! >= 180 ? "overcrowding_alert" : "normal",
      triggers: observed !== null && observed >= 180 ? ["relative"] : [],
      reasons: [],
    });
  }
  return out;
}

export const mockTimeline: TimelineResponse = {
  site: stadium.site,
  date: DAY,
  windows: windowsFor(),
  episodes: [
    {
      site_id: "MOCK_SITE_04",
      site_name: "Mock Stadium Stop",
      start: at("17:45"),
      end: at("18:30"),
      peak_observed: 180,
      peak_ratio: 1.9,
      triggers: ["relative"],
      first_warning_at: at("17:15"),
      lead_min: 30,
      matched_event: true,
    },
  ],
  simulated_events: [
    {
      site_id: "MOCK_SITE_04",
      start: at("17:15"),
      onset: at("17:45"),
      end: at("18:45"),
      kind: "event_crowd",
      description: "Mock simulated event crowd.",
    },
  ],
  provenance: mockWarningProvenance,
};

export const mockAlerts: AlertsResponse = {
  date: DAY,
  episodes: [
    mockTimeline.episodes[0],
    {
      site_id: "MOCK_SITE_02",
      site_name: "Mock Interchange Stop",
      start: at("08:00"),
      end: at("08:15"),
      peak_observed: 170,
      peak_ratio: 1.7,
      triggers: ["threshold"],
      first_warning_at: null,
      lead_min: null,
      matched_event: false,
    },
  ],
  provenance: mockWarningProvenance,
};

export const mockEvaluation: EvaluationResponse = {
  provenance: mockWarningProvenance,
  ground_truth: "simulated_events",
  caveat: "Measured on SIMULATED events. Says nothing about accuracy on real places.",
  metrics: { events: 4, events_detected: 4, window_precision: 0.81, early_warning: { median_lead_min: 30 } },
  notes: ["Mock note."],
};

export const mockWarningDataQuality: WarningDataQualityReport = {
  generated_at: "2026-11-17T09:00:00+05:30",
  sources: [
    {
      name: "simulated_camera_counts.csv",
      kind: "camera_count",
      rows_total: 6720,
      rows_valid: 6712,
      summary: { errors: 6, warnings: 1, infos: 2 },
      issues: [
        { code: "duplicate_window", severity: "error", file: "simulated_camera_counts.csv", count: 2, message: "Mock duplicate." },
      ],
    },
  ],
  model: { sites: 5, baseline_cells: 640 },
  blocked: ["Mock: real camera feed not connected."],
};
