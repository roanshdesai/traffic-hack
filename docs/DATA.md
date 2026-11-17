# Data: import paths, validation, matching and the crowding method

## 1. What is real and what is blocked

| Input | State |
| --- | --- |
| Static GTFS | **Simulated only.** The Delhi feed is available through a Delhi Transport Stack platform account and dataset request. No account has been registered. |
| Ticket data | **Real file received, not yet matched.** The hackathon's October 2026 ONDC e-ticketing file (2.56 million rows) validates through the import path with `config/ticket_mappings/ondc_2026_10.json`. It cannot be matched to stops or used for crowding until the static GTFS is available. See `docs/HACKATHON.md`. |
| Google road traffic | **Not connected.** No API key, no calls. Kept separate from crowding by design. |

The GTFS import path is built and tested on simulated data only. The ticket
import path has also run on the real October 2026 file (validation only).

### Running real data when it is available

Put files under `data/raw/` (git-ignored). Never commit them.

```
# 1. Check the feed on its own
.venv/bin/busplanner validate-gtfs --gtfs data/raw/delhi_gtfs.zip

# 2. Write a column mapping for the ticket extract (copy fixtures/synthetic/ticket_mapping.json)
.venv/bin/busplanner validate-tickets --tickets data/raw/tickets.csv --mapping data/raw/ticket_mapping.json

# 3. Build
.venv/bin/busplanner build \
  --gtfs data/raw/delhi_gtfs.zip --gtfs-source real \
  --tickets data/raw/tickets.csv --tickets-source real \
  --mapping data/raw/ticket_mapping.json \
  --aliases data/raw/aliases.json \
  --label "Delhi static GTFS + ticket sample" \
  --out data/processed/delhi

# 4. Read data/processed/delhi/quality_report.md, then serve
.venv/bin/busplanner serve --dataset data/processed/delhi
```

Both `--gtfs-source` and `--tickets-source` are required so nothing is labelled
real by accident. A GTFS-only build works: journeys are planned and every
crowding field reports insufficient evidence.

## 2. Static GTFS

Accepted: a folder or a `.zip` (files may sit in a subfolder). Required:
`stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, and `calendar.txt`
and/or `calendar_dates.txt`. Times are **scheduled**.

A record that fails validation is dropped and reported. A trip with any invalid
stop time is dropped **whole**, because a trip with a hole would yield wrong
segments and travel times.

| Code | Severity | Effect |
| --- | --- | --- |
| `missing_file`, `missing_column`, `no_services`, `no_usable_trips` | error | Feed unusable; build fails. |
| `duplicate_id`, `missing_id` | error | Later / id-less rows dropped. |
| `invalid_coordinates` | error | Stop dropped (and trips using it). |
| `unknown_route`, `unknown_service` | error | Trip dropped. |
| `unknown_stop`, `unknown_trip` | error | Trip dropped / row ignored. |
| `missing_time`, `invalid_time`, `invalid_stop_sequence` | error | Trip dropped. Untimed stops are **not** interpolated. |
| `duplicate_stop_sequence`, `time_goes_backwards`, `consecutive_duplicate_stop` | error | Trip dropped. |
| `trip_too_short` | warning | Trip dropped. |
| `trips_dropped` | warning | Count of trips removed, by reason. |
| `stop_outside_region` | warning | Stop outside a loose Delhi NCR bounding box; kept. |
| `duplicate_route_short_name` | warning | Tickets quoting that name will be ambiguous. |
| `missing_route_name`, `missing_stop_name` | warning | Kept; can only match by id. |
| `unused_stop`, `route_without_trips`, `shared_stop_name`, `zero_duration_segment`, `service_without_days` | info | Kept. |

## 3. Ticket samples

The source file is mapped to canonical fields by a JSON mapping:

```json
{
  "columns": {
    "ticket_id": "ticket_no",
    "issued_at": "issue_time",
    "route": "route_no",
    "board_stop": "from_stop",
    "alight_stop": "to_stop",
    "passengers": "pax",
    "direction": null
  },
  "timestamp_formats": ["%Y-%m-%d %H:%M:%S"],
  "delimiter": ",",
  "encoding": "utf-8-sig"
}
```

| Canonical field | Required | Notes |
| --- | --- | --- |
| `issued_at` | yes | Naive timestamps are read as Asia/Kolkata. Taken as the boarding time. |
| `route` | yes | Route number/name as printed. |
| `board_stop` | yes | Stop name, stop code or `stop_id`. |
| `alight_stop` | no | Without it the ticket is a boarding only and cannot feed segment loads. |
| `passengers` | no | Positive integer. If the column does not exist, each row counts as one rider. |
| `ticket_id` | no | Used to reject duplicates. |
| `vehicle_id` | no | Bus registration. Kept for per-trip running counts (not used by the model yet). |
| `direction` | no | Only used when it equals a GTFS `direction_id`. |

Tickets issued before 04:00 belong to the previous service day. Timestamps with a
UTC offset are converted to IST; `NULL`, `None`, `NA` and similar mean "no value".

| Code | Severity | Effect |
| --- | --- | --- |
| `missing_column`, `empty_file`, `source_not_found` | error | File unusable. |
| `invalid_timestamp`, `missing_route`, `missing_board_stop` | error | Row rejected. |
| `invalid_passenger_count` | error | Row rejected (not defaulted to 1). |
| `implausible_passenger_count` (more than 20) | error | Row rejected pending review (not capped). |
| `duplicate_ticket_id`, `same_board_alight` | error | Row rejected. |
| `no_alight_column` | warning | All tickets are boardings only; every segment will be insufficient. |
| `missing_alight_stop`, `no_passenger_column` | info | Kept. |

**What tickets cannot tell us.** A ticket is a sample of ticketed boardings. Pass
holders, riders without a ticket row, rows missing from the extract and rows we
could not match are invisible. The estimate is therefore a relative signal, not occupancy.

## 4. Route and stop matching

Normalisation is limited to case, spacing and punctuation (`"s-1 "` equals `"S1"`).
Abbreviations are not expanded and spelling is not corrected.

1. **Route.** The reference must equal exactly one GTFS route by `route_id`,
   short name or long name after normalisation, or have a reviewed alias.
2. **Stops.** On the matched route, the boarding and alighting references must
   resolve (by `stop_id`, `stop_code` or exact normalised name) to exactly one
   ordered run of stops. Same-named stops on opposite sides of the road are
   resolved by which direction has them in boarding-then-alighting order.

| Status | Used for crowding | Meaning |
| --- | --- | --- |
| `matched` | yes | One route, one ordered run of stops. |
| `matched_board_only` | no | No alighting stop on the ticket. |
| `unmatched_route` | no | No GTFS route matches. |
| `ambiguous_route` | no | More than one GTFS route matches. |
| `unmatched_board_stop` / `unmatched_alight_stop` | no | Stop is not on the matched route. |
| `ambiguous_path` | no | Stops fit more than one distinct run (route variants, loops). |
| `invalid_stop_order` | no | Both stops are on the route but never in that order. |

Unmatched references are listed in the report with close matches under
`suggestions_not_applied`. To accept one, a person adds it to an aliases file:

```json
{ "routes": { "Express-1": "SIM_R1" }, "stops": { "Sim Markt": "SIM_S03A" } }
```

`flagged_tickets.csv` in the dataset folder lists every rejected, unmatched or
ambiguous row with its reason. It is derived from raw data: keep it out of git.

## 5. Relative crowding estimate

For each **cell** `(route, from_stop, to_stop, day type, period)`:

```
index = sampled riders whose ticket covers the segment
        ---------------------------------------------------------
        scheduled trips through the segment on the sampled service days
```

* A rider is counted in the period in which they *reach* the segment: boarding
  time plus the scheduled running time from their boarding stop.
* Day types: `weekday`, `weekend`. Periods: early 04-07, morning peak 07-11,
  midday 11-16, evening peak 16-21, late 21-04.
* The index is ranked against all supported cells in the dataset (mid-rank, 0 to 1).
  Bottom third is `lower`, middle `typical`, top third `higher`.

Only the level, the rank and the support counts are exposed. **The rank is not
occupancy and not a percentage full.**

### Support and evidence grade

A cell is supported with at least **10 tickets** from at least **2 service days**
and at least one scheduled trip. It is strong with 30 tickets from 4 days.

### Fallbacks

Tried in order. Each step pools more data and caps the evidence grade lower.

| Order | `basis` | Pool | Grade if strong / adequate |
| --- | --- | --- | --- |
| 1 | `segment_period_daytype` | This segment, this period, this day type | high / medium |
| 2 | `segment_period` | This segment, this period, weekdays and weekends pooled | medium / low |
| 3 | `segment_all_day` | This segment, all periods and day types pooled | low / low |
| 4 | `none` | Nothing has enough support | insufficient |

At `none` the level is `insufficient_evidence` and the rank is null. The support
counts of the widest pool are still returned so the UI can say "3 tickets, needs 10".

There is deliberately no fallback to route-level or network-level averages: they
would put a level on a segment we have no samples for.

If fewer than 10 supported cells exist in the whole dataset, no reference
distribution is formed and every segment is insufficient.

### Journey level

* **Coverage** is the share of scheduled in-vehicle time with a supported segment.
* Below 60% coverage the journey's crowding is `insufficient_evidence`.
* Otherwise the journey rank is the time-weighted mean of segment ranks over
  covered segments, and the evidence grade is the time-weighted mean grade
  (uncovered time counts as zero).

### Rankings

| Option | Rule |
| --- | --- |
| Fastest | Earliest scheduled arrival. Crowding not used. Always available if any journey exists. |
| Balanced | Lowest `total_min + 5 x changes + 0.6 x in_vehicle_min x rank`. |
| Less crowded | Lowest journey rank. |

Balanced and Less crowded only consider journeys with at least 60% evidence
coverage that arrive no later than Fastest plus `max(20 min, 50% of Fastest's total)`.
If none qualifies they return `insufficient_evidence` and no journey.

## 6. Known weaknesses of the method

* **A quiet segment and an unsampled segment look the same.** Both have few
  tickets, so both are "insufficient evidence". The model cannot say "empty".
* **Sampling rate may differ by route.** If one route's tickets are captured more
  completely, it will rank as more crowded. There is no correction for this yet.
* **Per scheduled trip, not per actual trip.** Cancelled or bunched buses are invisible.
* **Bus size is ignored.** The index does not know vehicle capacity.
* **All thresholds are uncalibrated defaults** (`backend/busplanner/config.py`).
* **Nothing has been validated against observed crowding.** There is no ground truth yet.

## 7. Simulated fixtures

`fixtures/synthetic/` is generated by `backend/busplanner/synthetic.py`
(`make fixtures`). Stops are named `Sim ...`, ids start `SIM`, the agency is
`SIMULATED Transit`, every ticket row carries `data_label=SIMULATED`. The data
contains deliberate defects so the validators and matcher are exercised. The
pipeline refuses to label these inputs as real.
