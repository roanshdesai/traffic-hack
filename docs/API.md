# API contract (v0)

Base path `/api`. JSON only. No authentication in the prototype.

The source of truth is `backend/busplanner/schemas.py` (Pydantic). The running
server publishes the same contract as OpenAPI at `/docs` and `/openapi.json`.
`frontend/src/api/types.ts` mirrors it. **Change all three in one PR.**

All timestamps are ISO 8601 local times with the `+05:30` offset, e.g.
`2026-11-16T08:12:00+05:30`. Every time is a **scheduled** GTFS time.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness, and whether a dataset is loaded. |
| GET | `/api/meta` | Provenance, counts, thresholds, period definitions, disclaimers. |
| GET | `/api/stops?q=&limit=` | Search origin/destination places by name. |
| GET | `/api/journeys?from=&to=&date=&time=` | Fastest / Balanced / Less crowded options. |
| GET | `/api/data-quality` | The data-quality report produced by the last pipeline build. |

### `GET /api/stops`

`q` (string, may be empty: returns the first `limit` places alphabetically),
`limit` (1 to 50, default 10).

A **place** groups stops that share a normalised name and sit within 250 m of
each other (typically the two sides of a road). Use `place_id` in journey requests.

```json
{
  "query": "ghat",
  "places": [
    {
      "place_id": "place:SIM_S03A",
      "name": "Sim Ghat Road",
      "stop_ids": ["SIM_S03A", "SIM_S03B"],
      "lat": 28.6412, "lon": 77.2101,
      "routes": ["S1", "S2"]
    }
  ]
}
```

### `GET /api/journeys`

| Param | Required | Notes |
| --- | --- | --- |
| `from` | yes | `place_id` or a single `stop_id`. |
| `to` | yes | `place_id` or a single `stop_id`. |
| `date` | no | `YYYY-MM-DD`. Defaults to today in Asia/Kolkata. |
| `time` | no | `HH:MM` departure-after time. Defaults to now in Asia/Kolkata. |

Response (`JourneyResponse`):

```jsonc
{
  "request": { "origin": {/* Place */}, "destination": {/* Place */},
               "date": "2026-11-16", "time": "08:00",
               "day_type": "weekday", "period": "am_peak" },
  "status": "ok",                 // "ok" | "no_journey"
  "message": "3 options from 14 scheduled journeys.",
  "candidates_considered": 14,
  "options": [                    // always exactly 3, in this order
    { "kind": "fastest",      "label": "Fastest",      "status": "ok", "journey": {/* Journey */}, "reason": {/* Reason */}, "same_journey_as": null },
    { "kind": "balanced",     "label": "Balanced",     "status": "ok", "journey": {/* Journey */}, "reason": {/* Reason */}, "same_journey_as": null },
    { "kind": "less_crowded", "label": "Less crowded", "status": "insufficient_evidence", "journey": null, "reason": {/* Reason */}, "same_journey_as": null }
  ],
  "provenance": { "gtfs_source": "synthetic", "tickets_source": "synthetic", "simulated": true,
                  "label": "SIMULATED demo fixtures", "built_at": "2026-11-17T09:00:00+05:30" },
  "disclaimers": ["Times are scheduled times from static GTFS. They are not live arrivals.", "..."],
  "road_traffic": { "status": "not_configured", "note": "..." }
}
```

#### Option status

| `status` | Meaning | `journey` |
| --- | --- | --- |
| `ok` | A journey was selected. | present |
| `insufficient_evidence` | Scheduled journeys exist, but none has enough ticket evidence to be ranked on crowding. **Render this as an explicit state, not as an error and not as "low crowding".** | `null` |
| `no_journey` | No scheduled journey in the search window. | `null` |

`fastest` never returns `insufficient_evidence`: it uses the timetable only.
`same_journey_as` is set (for example to `"fastest"`) when an option selected a
journey already shown by an earlier option.

#### `Journey`

```jsonc
{
  "journey_id": "T_S1_0_0810",
  "scheduled_departure": "2026-11-16T08:10:00+05:30",
  "scheduled_arrival":   "2026-11-16T08:46:00+05:30",
  "scheduled_travel_min": 36,     // first boarding -> final alighting
  "initial_wait_min": 10,         // requested time -> first departure
  "total_min": 46,                // requested time -> arrival
  "transfers": 0,
  "legs": [ /* BusLeg | TransferLeg, discriminated by "type" */ ],
  "crowding": {
    "level": "typical",           // "lower" | "typical" | "higher" | "insufficient_evidence"
    "relative_rank": 0.52,        // see below; null when insufficient
    "evidence_quality": "medium", // "high" | "medium" | "low" | "insufficient"
    "coverage": 0.83,             // share of in-vehicle minutes with evidence
    "covered_min": 30, "in_vehicle_min": 36,
    "min_segment_ticket_count": 12,
    "segment_counts": { "lower": 1, "typical": 3, "higher": 1, "insufficient_evidence": 1 }
  }
}
```

`BusLeg`:

```jsonc
{
  "type": "bus",
  "route": { "route_id": "SIM_R1", "short_name": "S1", "long_name": "Sim Terminal - Sim Depot" },
  "trip_id": "SIM_R1_0_wk_0810", "headsign": "Sim Depot", "direction_id": "0",
  "board_stop":  { "stop_id": "SIM_S01A", "name": "Sim Terminal", "lat": 28.63, "lon": 77.20 },
  "alight_stop": { "stop_id": "SIM_S06A", "name": "Sim Depot",    "lat": 28.66, "lon": 77.25 },
  "scheduled_departure": "2026-11-16T08:10:00+05:30",
  "scheduled_arrival":   "2026-11-16T08:46:00+05:30",
  "scheduled_min": 36,
  "stops": [   // ordered, boarding stop first, alighting stop last
    { "stop_id": "SIM_S01A", "name": "Sim Terminal", "lat": 28.63, "lon": 77.20, "sequence": 1,
      "scheduled_arrival": "2026-11-16T08:10:00+05:30", "scheduled_departure": "2026-11-16T08:10:00+05:30" }
  ],
  "segments": [ // exactly stops.length - 1 entries; segments[i] runs stops[i] -> stops[i+1]
    {
      "from_stop_id": "SIM_S01A", "to_stop_id": "SIM_S02A",
      "scheduled_departure": "2026-11-16T08:10:00+05:30",
      "scheduled_arrival":   "2026-11-16T08:17:00+05:30",
      "scheduled_min": 7,
      "crowding": {
        "level": "higher",
        "relative_rank": 0.81,
        "evidence": {
          "quality": "medium",
          "basis": "segment_period_daytype", // | "segment_period" | "segment_all_day" | "none"
          "ticket_count": 18, "rider_count": 23, "service_days": 5,
          "scheduled_trips": 40, "min_tickets_required": 10
        }
      }
    }
  ]
}
```

`TransferLeg`:

```jsonc
{ "type": "transfer",
  "from_stop": {/* StopRef */}, "to_stop": {/* StopRef */},
  "scheduled_min": 6,   // gap between scheduled arrival and next scheduled departure
  "walk_m": 40 }
```

`Reason`:

```jsonc
{ "summary": "Earliest scheduled arrival (08:46) of 14 journeys departing within 60 min.",
  "details": ["Direct on route S1.", "Scheduled travel time 36 min after a 10 min wait."],
  "metrics": { "total_min": 46, "minutes_slower_than_fastest": 0 } }
```

`metrics` keys are informational and may grow; do not build layout on them.

#### What the crowding fields mean (and do not mean)

* `level` is **relative**: it places a segment against other supported
  segment-periods in the same dataset. `lower` / `typical` / `higher` are the
  bottom, middle and top thirds of that ranking.
* `relative_rank` is a 0 to 1 rank. **It is not occupancy and not a percentage
  full.** Do not render it as a percentage or as seats.
* `evidence.ticket_count` is the support count. `evidence.basis` says which
  pooling level was used (see `docs/DATA.md`, "Fallbacks").
* `insufficient_evidence` means "we do not know". It must never be styled as
  low crowding.
* When `provenance.simulated` is `true`, the UI must show a visible
  "simulated data" notice on every screen that shows results.

### `GET /api/meta`

Returns `provenance`, `counts` (`stops`, `places`, `routes`, `trips`,
`patterns`), `service_date_range` (`start`, `end`), `suggested_query`
(`{date, time}` inside the feed's service range, or `null`), `periods`,
`day_types`, `settings` (all thresholds from `config.py`), `fallbacks`
(ordered list of `{basis, description, quality_cap}`), `disclaimers` and
`road_traffic`.

### `GET /api/data-quality`

Returns the JSON report written by `busplanner build`. Top-level keys:
`generated_at`, `provenance`, `gtfs`, `tickets`, `matching`, `crowding`,
`blocked`. Each of `gtfs` and `tickets` has `summary` (`errors`, `warnings`,
`infos`) and `issues`: a list of
`{code, severity, file, count, message, samples}`. `matching` has `total`,
`by_status`, `match_rate` and review lists. See `docs/DATA.md` for the fields.

### Errors

Errors use HTTP status codes with a body of
`{"detail": {"code": "...", "message": "..."}}`.

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `same_place` | `from` and `to` resolve to the same place. |
| 400 | `bad_date` / `bad_time` | Unparseable `date` or `time`. |
| 404 | `unknown_place` | `from` or `to` does not match a place or stop. |
| 503 | `no_dataset` | No processed dataset is loaded. Run `make data`. |

A search that finds no scheduled journey is **not** an error: it returns 200
with `status: "no_journey"`.

## Road traffic

`road_traffic` is a separate object on purpose. Road traffic (for example the
Google Routes API) describes vehicles on roads; passenger crowding describes
people on buses. They are never combined into one number. The prototype ships
with `status: "not_configured"` and makes no calls to Google.
