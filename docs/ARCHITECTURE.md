# Architecture, stack and milestones

Status: first runnable slice. Everything runs locally on **simulated** fixtures.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Pipeline + API | Python 3.11+, FastAPI, Pydantic v2, uvicorn | One language for data work and serving; Pydantic models double as the API contract and generate OpenAPI. |
| Data handling | Standard library `csv` / `zipfile`, plain dataclasses | No pandas yet: fewer moving parts, and every dropped row goes through one explicit validation path. Revisit at real-feed scale (see limitations). |
| Storage | Files. Input: GTFS folder or zip + ticket CSV. Output: JSON artefacts under `data/processed/<name>/` | Nothing to provision; the built dataset is a folder that can be rebuilt from inputs at any time. |
| Frontend | Vite, React, TypeScript, plain CSS | Standard, fast to iterate, no UI framework to fight when the demo visuals are designed. |
| Tests | pytest (backend), Vitest + Testing Library (frontend) | |
| Tooling | `make`, ruff, tsc | |

No database, queue, auth, map tiles or third-party API is used. Nothing is deployed.

## Data flow

```
 static GTFS (folder/zip) ─┐
                           ├─► gtfs.py      validate, drop bad trips ──► Feed
 ticket CSV + mapping ─────┼─► tickets.py   validate, reject bad rows ─► Ticket[]
 aliases.json (reviewed) ──┘
                                Feed ─► network.py   stop patterns, places, transfer links
                    Ticket[] + Network ─► matching.py  matched / ambiguous / unmatched (flag, never guess)
                  matches + Network ─► crowding.py   segment cells, reference ranks, fallbacks
                                          │
            pipeline.py writes  data/processed/<name>/
              manifest.json  quality_report.{json,md}  crowding_model.json  flagged_tickets.csv
                                          │
                     dataset.py loads it ─► planner.py  search + Fastest / Balanced / Less crowded
                                          │
                                   api.py (FastAPI)  /api/*   ◄── frontend (React)
                                          │
                                   traffic.py  separate road-traffic boundary (not connected)
```

## Backend modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Every threshold and period definition, plus the disclaimers. |
| `schemas.py` | The API contract. |
| `quality.py` | Issue log shared by the importers. |
| `gtfs.py` | Static GTFS import and validation. |
| `tickets.py` | Ticket import through a column mapping, and validation. |
| `textnorm.py` | Deterministic normalisation for matching (case, spacing, punctuation only). |
| `network.py` | Stop patterns, places (same-named nearby stops), walking transfer links. |
| `matching.py` | Ticket route/stop matching with explicit statuses and review lists. |
| `crowding.py` | Relative crowding cells, ranks, fallbacks, evidence grades. |
| `planner.py` | Scheduled journey search (direct + one change) and the three rankings with reasons. |
| `pipeline.py` | Build orchestration and the data-quality report. |
| `dataset.py` | Loads a built dataset for serving. |
| `api.py` | HTTP endpoints; also serves `frontend/dist` when it exists. |
| `traffic.py` | Road-traffic boundary. Returns "not configured". |
| `synthetic.py` | Deterministic generator for the simulated fixtures. |
| `cli.py` | `busplanner build | build-synthetic | validate-gtfs | validate-tickets | generate-fixtures | serve`. |

## Key decisions

1. **The contract is the seam.** Backend and frontend only meet at `schemas.py` /
   `docs/API.md` / `frontend/src/api/types.ts`. The UI can be developed against
   mock data with no backend running.
2. **Crowding is keyed by route segment, not by trip.** A cell is
   `(route, from_stop, to_stop, day type, period)`. This survives route variants
   and needs no trip id on the ticket.
3. **Only a relative rank leaves the model.** The internal index (sampled riders
   per scheduled trip) is never exposed as a number a rider could read as occupancy.
4. **Insufficient evidence is a first-class result** at segment, journey and option level.
5. **Provenance is forced, not trusted.** `--gtfs-source` and `--tickets-source`
   are mandatory, and fixtures marked `SIMULATED` cannot be relabelled as real.
6. **Periods, not hours.** Five time-of-day periods and two day types keep cells
   large enough to have support. Hourly buckets are a config change once real volumes are known.
7. **Fastest ignores crowding entirely**, so there is always a timetable-only answer.

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| M0 | Repo bootstrap, ignore rules, stack and contract proposal | Done |
| M1 | GTFS and ticket import paths with validation and a data-quality report | Done (simulated data) |
| M2 | Route and stop matching with review lists | Done |
| M3 | Relative crowding model with support counts and fallbacks | Done |
| M4 | Journey search and Fastest / Balanced / Less crowded with reasons | Done |
| M5 | Journey API | Done |
| M6 | Mobile-friendly UI on the API | Done (baseline; visuals to be designed) |
| M7 | Real static GTFS through the import path | **Blocked**: no feed available here (see `docs/DATA.md`) |
| M8 | Real ticket data through the import path | **Blocked**: no file and no schema provided |
| M9 | Calibrate thresholds and validate the estimate against any ground truth | Not started; needs M7 and M8 |
| M10 | Demo visuals: route map, crowding strip, comparison view | Not started |
| M11 | CI (lint + tests on pull requests) | Not started; needs the owner's go-ahead to enable Actions |
| M12 | Hosting / demo deployment | Not started; needs the owner's go-ahead |

## Branch workflow

See `AGENTS.md`, section 4. Work so far sits on the feature branch
`claude/delhi-bus-planner-prototype-khz0w4`. Its first commit is a minimal
bootstrap commit on purpose, so `main` can be created from it and the rest
reviewed as a pull request.
