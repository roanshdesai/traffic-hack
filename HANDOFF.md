# Handoff

State of the repo after the first slice. Written for the next person or agent.

## 1. Setup

```bash
make setup     # python venv + pip install -e backend[dev]; npm ci in frontend
make data      # build data/processed/synthetic from fixtures/synthetic
make test      # backend + frontend tests
make demo      # build UI + data, serve both on http://127.0.0.1:8000
```

Dev loop: `make api` in one terminal, `make ui` in another (http://localhost:5173).

Verified on Python 3.13 and Node 22 from a clean checkout: `make setup`,
`make data`, `make lint`, `make test` (92 backend + 26 frontend tests pass),
`make demo`. The real October 2026 ticket file also validates through the
import path (`docs/HACKATHON.md`). The built UI was also driven in a 390 px wide headless browser
against the real API: search, all three tabs, and the insufficient-evidence
state rendered with no console errors and no horizontal overflow.

## 2. What was added

Everything; the repo started empty.

| Path | What |
| --- | --- |
| `.gitignore`, `.env.example`, `Makefile` | Ignore rules for data and secrets, env names, dev commands |
| `README.md`, `HANDOFF.md`, `AGENTS.md`, `CLAUDE.md` | Overview, this file, working agreement |
| `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATA.md` | Stack and milestones, API contract, data and method |
| `backend/pyproject.toml` | Package `busplanner`, CLI entry point, dev tools |
| `backend/busplanner/config.py` | All thresholds, periods, disclaimers |
| `backend/busplanner/schemas.py` | API contract (Pydantic) |
| `backend/busplanner/{gtfs,tickets,quality,textnorm}.py` | Import paths and validation |
| `backend/busplanner/{network,matching}.py` | Stop patterns, places, route/stop matching |
| `backend/busplanner/crowding.py` | Relative crowding model and fallbacks |
| `backend/busplanner/planner.py` | Journey search and the three rankings |
| `backend/busplanner/{pipeline,dataset,api,cli,traffic}.py` | Build, load, serve, CLI, road-traffic boundary |
| `backend/busplanner/synthetic.py` | Generator for the simulated fixtures |
| `backend/tests/*.py` | 92 tests |
| `config/ticket_mappings/ondc_2026_10.json` | Column mapping for the real hackathon ticket file |
| `docs/HACKATHON.md` | Problem 2 brief, rules, dates, data profile, gaps, open decision |
| `fixtures/synthetic/**` | SIMULATED GTFS (903 usable trips, 16 places) and 1,787 ticket rows |
| `frontend/**` | Vite + React + TypeScript UI, 26 tests |

## 3. What works

* **GTFS import** from a folder or zip with validation; bad trips are dropped whole and reported.
* **Ticket import** through a column-mapping file with validation; bad rows are rejected and reported.
* **Data-quality report** as JSON (served at `/api/data-quality`) and Markdown, plus a
  `flagged_tickets.csv` listing every rejected, unmatched or ambiguous row.
* **Matching** that never guesses: ambiguous routes, ambiguous stop runs, unknown
  and misspelt references are flagged, with close matches offered as suggestions only.
* **Relative crowding** per route segment, period and day type, with support
  counts, three documented fallback levels and an evidence grade.
* **Journey search**: direct and one-change journeys on scheduled times.
* **Three rankings with reasons**, including the explicit `insufficient_evidence` status.
* **API**: `/api/health`, `/api/meta`, `/api/stops`, `/api/journeys`, `/api/data-quality`; OpenAPI at `/docs`.
* **UI**: search with autocomplete, three option tabs, journey card, stop timeline
  with per-segment crowding and support counts, insufficient-evidence / no-journey /
  error states, simulated-data banner, data-quality panel, separate road-traffic note.
* **Guards**: simulated inputs cannot be labelled real; tests fail if raw data,
  secrets or occupancy-style fields are introduced.

Demo searches on the simulated data (date 2026-11-13, 08:00):

| From | To | Shows |
| --- | --- | --- |
| Sim Terminal | Sim Depot | Three different journeys; Fastest has no crowding evidence |
| Sim Stadium | Sim South End | Balanced and Less crowded are "insufficient evidence" |
| Sim North Gate | Sim Depot | One-change journeys; fallback evidence on one segment |

## 4. What is blocked

| Item | Why | To unblock |
| --- | --- | --- |
| Real static GTFS | Needs a Delhi Transport Stack platform account and a dataset request; no account was registered | A team member signs up, requests the static bus GTFS, puts it in `data/raw/` and runs the build (`docs/DATA.md` section 1) |
| Hackathon registration | Team registration on Where U Elevate closes 20 Nov 2026, 23:59 IST | A team member registers (`docs/HACKATHON.md`) |
| Real ticket data | Received and validated (`docs/HACKATHON.md`), but cannot be matched without GTFS | Unblocked by the GTFS row above |
| Google road traffic | No API key or billing; not requested | Owner decision. Boundary is `backend/busplanner/traffic.py` |
| Pull request for this branch | The repo has no `main` yet, and nothing was pushed to `main` | Owner creates `main` (ideally from this branch's first commit), then the PR can be opened |

Nothing was registered, submitted or deployed.

## 5. Known limitations

**Data and method**

* Only simulated data has been through the pipeline. Real feeds will raise issues the fixtures do not.
* The crowding estimate is unvalidated: there is no ground truth, and every threshold in `config.py` is an uncalibrated default.
* A quiet segment and an unsampled segment are indistinguishable; both report insufficient evidence.
* Different ticket capture rates between routes would bias the relative ranking. No correction exists.
* Exposure is scheduled trips, not trips actually run; vehicle capacity is ignored.
* Route variants make some tickets ambiguous (`ambiguous_path`, 66 rows in the fixtures). Trip or vehicle ids on tickets could resolve this; they are not used yet.
* Stop-name matching is exact after normalisation. Real data will likely need a reviewed alias table.
* Untimed GTFS stops are not interpolated: a trip with a blank time is dropped.

**Planner**

* At most one change. Changes only between stops within 250 m, at a fixed 1.2 m/s walk and 4 min minimum.
* No walking to or from the origin and destination, no fares, no accessibility data.
* Trips from the previous service day that run past midnight are not considered for early-morning searches.
* Search is a pattern scan in pure Python. Fine for the fixtures; untested at full-city scale.
* The feed is parsed from CSV on every server start; a large feed will make startup slow.

**Frontend**

* Baseline visuals only; no map. Arrivals after midnight show the time without a "+1 day" marker.
* No end-to-end test is committed (the browser check was run by hand).

**Process**

* No CI. No `main` branch yet, so no pull request.

## 6. Next tasks

Hackathon Phase 1 closes **24 Nov 2026, 18:29 IST**. `docs/HACKATHON.md` lists
the gaps between this prototype and the Problem 2 brief, and one open decision
(absolute crowding labels) that the team has to make.

The split below is the **proposed** one from `AGENTS.md`; it is not an agreed assignment.

### Frontend and demo visuals (proposed: Aashu)

Work in `frontend/` only, against `docs/API.md`. The mock data in
`frontend/src/test/fixtures.ts` lets you work without the backend.

1. Design pass on the journey card and timeline; keep every rule in `AGENTS.md` section 1.
2. Side-by-side comparison of the three options (time, changes, crowding, evidence).
3. Route map from the `lat`/`lon` on each leg stop, coloured by segment level, with a distinct style for insufficient evidence.
4. Demo script: a guided path through the three demo searches above.
5. Add a "+1 day" marker for arrivals after midnight and a "now" shortcut for date/time.
6. Commit a Playwright end-to-end test for search, tabs and the insufficient-evidence state.

### Data, modelling and backend (proposed: Roansh)

1. Obtain the real static GTFS, run `validate-gtfs`, and fix what the report shows.
2. Obtain the ticket extract and its schema; write the mapping; review the match report and build the alias table.
3. Decide how to handle `ambiguous_path` (use trip/vehicle id or time if the tickets carry them).
4. Calibrate thresholds on real volumes; consider hourly buckets and corridor-level pooling.
5. Find any ground truth (counts, surveys) to validate the relative ranking.
6. Performance for a full feed: cache the parsed network, index departures per stop.
7. Previous-service-day trips after midnight; walking legs at the ends.

### Integration and testing (both)

1. Create `main`, open the PR for this branch, agree the ownership split.
2. Add CI (lint + tests on pull requests) once the owner agrees to enable it.
3. Contract test that fails when `schemas.py` and `frontend/src/api/types.ts` drift.
4. Decide whether and where to host a demo. Nothing is deployed today.
