# Architecture, stack and milestones

Status: prototype. Main product: **early detection of overcrowding** at transit
sites from people-count signals. Secondary: the earlier journey planner.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Pipeline + API | Python 3.11+, FastAPI, Pydantic v2, uvicorn | One language for data and serving; Pydantic models are the contract and generate OpenAPI. |
| Model | Standard library only (medians, MAD, damped trend) | Explainable, no training infrastructure, every number traceable. |
| Storage | Files: inputs under `data/raw/`, built JSON datasets under `data/processed/<name>/` | Nothing to provision; any dataset can be rebuilt from its inputs. |
| Frontend | Vite, React, TypeScript, plain CSS, inline SVG chart | No chart or UI library to fight when visuals are designed. |
| Tests | pytest, Vitest + Testing Library | |

No database, queue, auth, map tiles, camera feed or third-party API. Nothing is deployed.

## Data flow (main product)

```
camera counts CSV + sites.csv ─► sources.load_camera_counts ─┐
ticket CSV + mapping ─► tickets.load_tickets ─► sources.tickets_to_observations ─┤
                                                                 ObservationSet (site x day x window)
                                                                                 │
                     pipeline.build_warning_dataset: split baseline / replay days
                        model.Baselines.build (baseline days only)
                        evaluate.replay (each replay window: assess, forecast, warn)
                        evaluate.evaluate_against_events (synthetic) | describe_without_truth (real)
                                                                                 │
                 data/processed/<name>/ manifest, sites, baselines, replay, episodes,
                                        events, evaluation, quality_report.{json,md}
                                                                                 │
                 dataset.WarningDataset ─► earlywarning/api.py (/api/*) ◄── frontend monitor
                 traffic.py ─► separate road_traffic field (not connected)
```

The planner keeps its own flow (GTFS + tickets ─► matching ─► segment crowding ─►
journeys) under `/api/planner/*`; see `docs/DATA.md`.

## Backend modules (main)

| Module | Responsibility |
| --- | --- |
| `earlywarning/config.py` | Thresholds, source specs (window length, hours), calendar, disclaimers |
| `earlywarning/schemas.py` | API contract |
| `earlywarning/sources.py` | Camera-count and ticket import paths, validation, privacy guard |
| `earlywarning/model.py` | Usual levels, status rules, damped-trend forecast, early-warning rule |
| `earlywarning/evaluate.py` | Replay, alert episodes, backtest vs simulated events, real-data statistics |
| `earlywarning/pipeline.py` | Build orchestration, data-quality report |
| `earlywarning/dataset.py` | Load a built dataset, overview / timeline queries |
| `earlywarning/api.py` | HTTP routes |
| `earlywarning/synthetic.py` | Generator for the simulated camera fixtures |
| `tickets.py`, `quality.py`, `textnorm.py`, `traffic.py` | Shared with the planner |

## Key decisions

1. **Compare each site with its own history.** No absolute crowding claims
   without a full-count source; operator thresholds are optional settings.
2. **Replay, not live.** All endpoints take a replay time and use only data up to it.
3. **Baseline and replay periods never overlap**, so evaluation is out-of-sample in time.
4. **Unknown stays unknown:** "not enough history" and "no data" are first-class statuses.
5. **Warnings need a sustained, rising departure** from usual; one noisy window cannot raise one.
6. **Counts only from cameras**; identifying fields are dropped at import.
7. **Road traffic is context, not a feature**, until a separate study shows it helps.
8. **Ticket sites are stop names** until static GTFS is available.

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| M0 to M6 | Planner prototype (GTFS/ticket import, matching, segment crowding, planner, API, UI) | Done; now secondary |
| E1 | Pivot: early-warning contract, people-count import paths, simulated camera fixtures | Done |
| E2 | Baseline, status rules, forecast, early warning, backtest | Done (simulated + real tickets) |
| E3 | Early-warning API and monitor UI | Done |
| E4 | Real camera counts | **Blocked**: no source, needs owner agreement and go-ahead |
| E5 | Road traffic as context, then as a tested leading indicator | **Blocked**: no API key; owner decision |
| E6 | Ground truth (manual counts, operator incident logs) to validate alerts | Not started |
| E7 | Static GTFS to separate same-named stops and add map positions | **Blocked**: platform account |
| E8 | Rolling baselines, holiday calendar, calibration | Not started |
| E9 | CI and hosting | Not started; needs the owner's go-ahead |
