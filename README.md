# Delhi bus crowding-aware journey planner (prototype)

Search an origin and a destination and compare three bus journeys:

* **Fastest**: earliest scheduled arrival.
* **Balanced**: best mix of scheduled time and relative crowding.
* **Less crowded**: lowest relative crowding among journeys with enough evidence.

Each result shows the scheduled travel time, the ordered stops, a relative
crowding level for every stop-to-stop segment, the reason for the ranking and
the quality of the evidence behind it. When there are too few ticket samples to
say anything, the result is an explicit **insufficient evidence** state.

> **This repository currently runs on SIMULATED data only.** The routes, stops,
> timetables and ticket samples under `fixtures/synthetic/` are invented. Nothing
> the app shows describes real Delhi bus services or real crowding.

## What the numbers mean

* **Times are scheduled** (static GTFS). They are not live arrivals.
* **Crowding is relative and estimated from ticket samples.** Ticket samples are
  not verified occupancy. The app does not know seats available or how full a bus is.
* **Insufficient evidence means unknown**, not quiet.
* **Road traffic is a separate signal** and is not connected. It is never mixed into crowding.

## Quick start

Needs Python 3.11+, Node 20+ and `make`.

```bash
make setup     # backend virtualenv (.venv) + frontend node_modules
make demo      # build the simulated dataset and the UI, serve both
```

Open http://127.0.0.1:8000. Try **Sim Terminal** to **Sim Depot** (three different
options) and **Sim Stadium** to **Sim South End** (insufficient evidence).

For development, run the two servers separately:

```bash
make data      # build data/processed/synthetic from the simulated fixtures
make api       # API on http://127.0.0.1:8000 (auto-reload), OpenAPI at /docs
make ui        # UI on http://localhost:5173, proxies /api to the API
```

```bash
make test      # 92 backend tests (pytest) + 26 frontend tests (vitest)
make lint      # ruff + TypeScript typecheck
make fixtures  # regenerate the simulated fixtures (deterministic)
```

## Layout

```
backend/busplanner/   data pipeline, crowding model, planner, API (Python, FastAPI)
backend/tests/        pytest suite (uses the simulated fixtures)
frontend/             mobile-first UI (Vite, React, TypeScript)
fixtures/synthetic/   SIMULATED GTFS feed and ticket samples (generated; tracked)
data/                 real inputs and all pipeline output (git-ignored; never commit)
docs/                 architecture, API contract, data and method notes
```

## Documentation

| File | Contents |
| --- | --- |
| [`HANDOFF.md`](HANDOFF.md) | Current state, what works, known limitations, next tasks. Start here. |
| [`AGENTS.md`](AGENTS.md) | Working agreement: ownership proposal, contract changes, branches. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Stack, data flow, decisions, milestones. |
| [`docs/API.md`](docs/API.md) | HTTP contract. |
| [`docs/HACKATHON.md`](docs/HACKATHON.md) | Problem 2 brief, rules, dates, real data profile, gaps, open decisions. |
| [`docs/DATA.md`](docs/DATA.md) | Import paths, validation, matching, crowding method, fallbacks, what is blocked. |
| [`frontend/README.md`](frontend/README.md) | Frontend commands and structure. |

## Using real data

Built for Problem 2 of the Transport Stack Hackathon 2026 (`docs/HACKATHON.md`).
The real October 2026 ticket file validates through the import path; the real
static GTFS is still needed before journeys can use it. `docs/DATA.md` section 1
has the commands. Keep real data under `data/` and out of git.

## Credits

Built with FastAPI, Pydantic, uvicorn, React, Vite, TypeScript, Vitest and
Testing Library. Code was written with the help of an AI coding assistant
(Claude Code); the hackathon rules allow this when credited.

## Status

Prototype. Not deployed, not registered with any data provider, not validated
against observed crowding.
