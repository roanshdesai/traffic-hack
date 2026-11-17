# Overcrowding early warning (prototype)

Detect, and where possible forecast, **unusual crowding at transit sites**
(stops, terminals, stations) from people-count signals:

* **camera counts**: aggregated people counts per 15 minutes from camera
  counting software (no images, no identities);
* **ticket samples**: ticket records per boarding stop per hour;
* **road traffic** (Google), as a separate context signal: not connected.

For every site the app shows the current count against the site's usual level,
a status (usual, busier than usual, overcrowding alert, not enough history, no
data), a forecast for the next hour and an **early warning** when a sustained
rise is heading for an alert. It replays recorded data; nothing is live.

> **Read this before trusting any output.**
> * The camera data in this repo is **SIMULATED** (`fixtures/synthetic/earlywarning/`).
>   The app shows a simulated-data banner whenever it is used.
> * The real data used so far is the Oct 2026 Delhi e-ticket file: a **sample**
>   of passengers. It can show unusual activity, not how full a place is.
> * Statuses and forecasts are **estimates**, not verified real-world conditions.
>   No ground truth exists for the real data.

The earlier **journey planner** is kept as a secondary page (`/api/planner/*`,
"Journey planner (secondary)" in the UI). It is no longer the main product.

## Quick start

Needs Python 3.11+, Node 20+ and `make`.

```bash
make setup     # backend virtualenv (.venv) + frontend node_modules
make demo      # build the simulated datasets and the UI, serve on http://127.0.0.1:8000
```

The monitor opens at the first early warning in the simulated replay (Sim
Stadium Stop, 18 Nov). Step the replay time forward to watch it turn into an
alert.

Real ticket data (download the hackathon file into `data/raw/2026-10/` first;
see `docs/HACKATHON.md`):

```bash
make data-real-tickets   # about 1 minute
make build-ui api-real   # serve it on http://127.0.0.1:8000
```

Other commands:

```bash
make data      # build both simulated datasets
make api       # API with auto-reload; OpenAPI at /docs
make ui        # Vite dev server on http://localhost:5173 (proxies /api)
make test      # backend (pytest) + frontend (vitest)
make lint      # ruff + TypeScript typecheck
make fixtures  # regenerate the simulated fixtures (deterministic)
```

## Layout

```
backend/busplanner/earlywarning/  MAIN: sources, baseline + detection + forecast, backtest, API
backend/busplanner/               shared pieces (tickets, quality log, traffic boundary) and the
                                  secondary planner (gtfs, matching, crowding, planner)
backend/tests/                    pytest suite (test_ew_* for the main product)
frontend/src/components/monitor/  MAIN UI: monitor, site detail, timeline chart, evaluation
frontend/src/planner/             secondary journey planner UI
fixtures/synthetic/earlywarning/  SIMULATED camera counts, sites and test events
fixtures/synthetic/               SIMULATED GTFS + tickets for the planner
config/ticket_mappings/           column mapping for the real ticket file
data/                             real inputs and all build output (git-ignored; never commit)
```

The Python package is still called `busplanner` to avoid churn; renaming it is a
cheap follow-up.

## Documentation

| File | Contents |
| --- | --- |
| [`HANDOFF.md`](HANDOFF.md) | Current state, what works, limitations, next tasks. Start here. |
| [`docs/METHOD.md`](docs/METHOD.md) | Technical note: inputs, rules, forecast, results, weaknesses. |
| [`docs/API.md`](docs/API.md) | HTTP contract of the early-warning API. |
| [`AGENTS.md`](AGENTS.md) | Working agreement: product rules, ownership proposal, branches. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Stack, data flow, milestones. |
| [`docs/HACKATHON.md`](docs/HACKATHON.md) | Transport Stack Hackathon 2026: rules, data, and how the pivot fits. |
| [`docs/DATA.md`](docs/DATA.md), [`docs/API-planner.md`](docs/API-planner.md) | The secondary planner's data method and API. |

## Credits

Built with FastAPI, Pydantic, uvicorn, React, Vite, TypeScript, Vitest and
Testing Library. Code was written with the help of an AI coding assistant
(Claude Code); the hackathon rules allow this when credited.

## Status

Prototype. Not deployed, not registered with any data provider, not validated
against observed crowding.
