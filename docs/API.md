# API contract (v1): overcrowding early warning

Base path `/api`. JSON only. No authentication in the prototype.

Source of truth: `backend/busplanner/earlywarning/schemas.py`. The running
server publishes OpenAPI at `/docs`. `frontend/src/api/warningTypes.ts` mirrors
it. **Change all three in one PR.**

The secondary journey planner keeps its own contract under `/api/planner/*`
(see `docs/API-planner.md`; its paths moved from `/api/*` to `/api/planner/*`).

## Time

All data is **recorded**, and the API replays it. `at` is the replay time:
only observations up to `at` are used for the current status and the
forecast. Times are local Asia/Kolkata wall-clock strings without an offset,
`YYYY-MM-DDTHH:MM`. Nothing is live.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | `{status: "ok" | "no_dataset", dataset_dir, detail}` |
| GET | `/api/meta` | `WarningMeta`: provenance, default replay time, thresholds, status definitions, disclaimers |
| GET | `/api/overview?at=` | `OverviewResponse`: every site's status at `at`, most urgent first |
| GET | `/api/sites?q=&limit=` | `SiteListResponse`: search sites by name |
| GET | `/api/sites/{site_id}/timeline?date=` | `TimelineResponse`: every window of one day for one site |
| GET | `/api/alerts?date=` | `AlertsResponse`: alert episodes (all replay days if `date` omitted) |
| GET | `/api/evaluation` | `EvaluationResponse`: backtest metrics, or "no ground truth" for real data |
| GET | `/api/data-quality` | Data-quality report from the last build |

`at` defaults to `meta.default_at`; `date` defaults to the date of `default_at`.
Both must fall inside `provenance.replay_period`, otherwise 400 `out_of_range`.

## Statuses

| `status` | Meaning | UI wording |
| --- | --- | --- |
| `normal` | Within the usual range for this place, day type and time | "Usual for this time" |
| `elevated` | Clearly busier than usual | "Busier than usual" |
| `overcrowding_alert` | Far above usual, or at/above an operator-set threshold | "Overcrowding alert" |
| `insufficient_evidence` | Not enough history to judge | "Not enough history" |
| `no_data` | No usable observation (sensor gap, excluded reading) | "No data" |

`insufficient_evidence` and `no_data` must never be styled like `normal`.

`triggers` says why: `relative` (far above this site's own history) and/or
`threshold` (count at or above `site.alert_threshold`, an operator setting,
not a verified capacity; only for `coverage: full_count`).

## Key objects

```jsonc
// Site
{ "site_id": "SIM_SITE_04", "name": "Sim Stadium Stop", "kind": "bus_stop",
  "lat": 28.598, "lon": 77.192,
  "source": "camera_count",          // camera_count | ticket_sample | manual_count
  "coverage": "full_count",          // full_count | sample
  "window_minutes": 15,
  "unit": "people counted",          // or "e-ticket boardings"
  "alert_threshold": 150 }           // null when not set

// WindowAssessment
{ "window_start": "2026-11-18T17:45", "window_end": "2026-11-18T18:00",
  "observed": 182,                   // null when status is no_data
  "baseline": { "median": 95, "low": 82, "high": 108, "support_days": 8,
                "basis": "site_daytype_slot", "quality": "high" },  // null if none
  "ratio": 1.92, "z": 6.7,
  "status": "overcrowding_alert", "triggers": ["relative", "threshold"],
  "reasons": ["182 people counted vs usually 95 (usual range 82-108) for a weekday at 17:45.", "..."] }

// Forecast (one per horizon: 1..4 windows ahead)
{ "horizon_min": 30, "window_start": "2026-11-18T18:15",
  "predicted": 171.3, "low": 150.0, "high": 192.6, "usual": 101,
  "status": "overcrowding_alert" }

// EarlyWarning (present only when current status is not already an alert
// and a forecast reaches overcrowding_alert)
{ "expected_at": "2026-11-18T18:15", "lead_min": 30, "predicted": 171.3,
  "summary": "If the current rise continues, an overcrowding alert is expected around 18:15 (in 30 min)." }

// SiteStatus
{ "site": {}, "at": "2026-11-18T17:45", "current": {}, "forecasts": [], "early_warning": null }

// AlertEpisode: consecutive alert windows merged
{ "site_id": "SIM_SITE_04", "site_name": "Sim Stadium Stop",
  "start": "2026-11-18T17:45", "end": "2026-11-18T19:15",
  "peak_observed": 246, "peak_ratio": 2.6, "triggers": ["relative", "threshold"],
  "first_warning_at": "2026-11-18T17:15", "lead_min": 30,
  "matched_event": true }            // synthetic only; null for real data

// SimulatedEvent: ground truth injected into synthetic data (empty for real data)
{ "site_id": "SIM_SITE_04", "start": "2026-11-18T17:15", "onset": "2026-11-18T17:45",
  "end": "2026-11-18T19:15", "kind": "event_crowd", "description": "..." }
```

`OverviewResponse`: `{at, provenance, counts, sites: SiteStatus[], total_sites, disclaimers, road_traffic}`.
`counts` has one key per status plus `early_warning`. `sites` is sorted: alerts,
then early warnings, then elevated, then the rest; at most 200 sites.

`TimelineResponse`: `{site, date, windows: WindowAssessment[], episodes, simulated_events, provenance}`.

`EvaluationResponse`: `{provenance, ground_truth: "simulated_events" | "none", caveat, metrics, notes}`.
`metrics` is a free-form object of numbers; render key/value pairs.

`WarningProvenance`:
`{origin: "synthetic" | "real", simulated, label, source_kinds, built_at,
baseline_period: {start, end}, replay_period: {start, end}}`.
When `simulated` is true the UI shows the simulated-data banner on every screen.

`WarningMeta`: `{product, provenance, default_at, counts: {sites, ...}, settings,
status_definitions, disclaimers, road_traffic, planner_available}`.

## Errors

`{"detail": {"code": "...", "message": "..."}}` with
400 `bad_time` / `bad_date` / `out_of_range`, 404 `unknown_site`, 503 `no_dataset`.

## Road traffic

`road_traffic` (`{status: "not_configured" | "unavailable" | "ok", note}`) is a
separate context object. It never changes a status, threshold or forecast.
The prototype makes no Google calls.
