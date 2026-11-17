# Working agreement for agents (and humans)

Two people, each with their own coding agent, work in this repo. This file is how
they avoid stepping on each other. Read it before you edit anything.

**Product focus (since 17 Nov 2026): early detection of overcrowding.** The
journey planner is a secondary feature. Do not grow it unless asked.

## 1. Product rules that no change may break

1. **Estimates are labelled as estimates.** Never present a status, forecast or
   count as a verified real-world condition. Never say "live" or "real-time":
   all data is recorded and replayed.
2. **Simulated data is always labelled.** Synthetic records carry `SIM_`/`Sim `
   names and `data_label=SIMULATED`; the UI shows the simulated-data banner when
   `provenance.simulated` is true. Never present fixtures as real.
3. **Ticket samples are not a headcount or occupancy.** From tickets, say
   "unusual activity", never seats, capacity or "% full".
4. **Camera data means aggregated counts only.** No images, video, faces,
   track ids, plates or anything that identifies a person enters this repo or
   the pipeline. Identifying columns are ignored and reported.
5. **Operator thresholds are settings, not capacities.** Label them that way.
6. **Unknown is a state.** "Not enough history" and "no data" are never shown
   as "usual"; sensor gaps are never filled with zeros or guesses.
7. **Flag, never guess.** Bad records are rejected and reported, not repaired.
8. **Road traffic stays separate** from people counts: its own module
   (`traffic.py`) and response field, never inside a status, threshold or forecast.
9. **No raw data, secrets or credentials in git.** Real inputs and all build
   output live under `data/` (ignored). Only `fixtures/synthetic/**` is tracked.
10. **No registering, submitting, deploying or connecting external services**
    (camera feeds, Google APIs, data portals) without the owner saying so.

`backend/tests/test_ew_api.py`, `test_ew_fixtures.py` and `test_fixtures.py`
enforce parts of this. Do not weaken them to get green.

## 2. Proposed ownership (a suggestion, not an agreed assignment)

Roansh and Aashu have not confirmed this split. Treat it as the default until
they say otherwise, and ask before working in the other person's area.

| Area | Paths | Proposed owner |
| --- | --- | --- |
| People-count import, validation, fixtures | `backend/busplanner/earlywarning/{sources,synthetic}.py`, `backend/busplanner/{tickets,quality,textnorm}.py`, `fixtures/`, `config/` | Roansh |
| Detection, forecast, evaluation | `backend/busplanner/earlywarning/{model,evaluate,pipeline,config}.py` | Roansh |
| API server | `backend/busplanner/earlywarning/{api,dataset}.py`, `backend/busplanner/{api,cli,traffic}.py` | Roansh |
| Frontend and demo visuals | `frontend/` (main: `src/components/monitor/`) | Aashu |
| API contract | `backend/busplanner/earlywarning/schemas.py`, `docs/API.md`, `frontend/src/api/warningTypes.ts` | Both (section 3) |
| Integration and tests | `backend/tests/`, `frontend/src/**/*.test.*`, `Makefile` | Both |
| Secondary planner | `backend/busplanner/{gtfs,network,matching,crowding,planner,dataset,schemas,pipeline,synthetic}.py`, `frontend/src/planner/` | Frozen unless asked |
| Docs | `README.md`, `HANDOFF.md`, `AGENTS.md`, `docs/` | Whoever changes behaviour updates the doc |

## 3. Changing the API contract

The early-warning contract lives in three files that must agree:
`backend/busplanner/earlywarning/schemas.py` (source of truth), `docs/API.md`,
`frontend/src/api/warningTypes.ts`. (The planner has its own trio:
`schemas.py`, `docs/API-planner.md`, `frontend/src/api/types.ts`.)

* **Additive** (new optional field or endpoint): update all three in one PR.
* **Breaking** (rename, removal, type change, new status value): draft PR, tag
  the other owner, merge only after they update or approve the other side.
* The UI ignores unknown fields and renders `evaluation.metrics` generically.
* The frontend can be built against `frontend/src/test/warningFixtures.ts`
  (mock data) without a running backend.

## 4. Branches and commits

* Never push to `main` directly. All work goes through a feature branch and a PR.
* Branch names: `feat/<area>-<topic>`, `fix/<area>-<topic>`, `docs/<topic>`;
  `<area>` is `data`, `model`, `api`, `ui` or `infra`. Example: `feat/model-holiday-calendar`.
* One concern per branch, inside one ownership area where possible. A branch
  touching both `backend/` and `frontend/` is a contract change (section 3).
* Commit messages: `type(scope): summary`, e.g. `feat(model): separate Saturday baseline`.
* Before pushing: `make lint && make test`.

## 5. Files with special handling

| Path | Rule |
| --- | --- |
| `fixtures/synthetic/**` | Generated. Change the generator (`earlywarning/synthetic.py` or `synthetic.py`), run `make fixtures`, commit both. Tests count fixture rows. |
| `backend/busplanner/earlywarning/config.py` | Thresholds change every result. One change per PR, with before/after evaluation numbers from `make data`. |
| `frontend/package-lock.json` | Only changes with `package.json`, via `npm install <pkg>`. |
| `data/**`, `.env` | Ignored. Never force-add. |
| `frontend/dist/`, `node_modules/`, `.venv/` | Build output. Ignored. |

## 6. Commands

```
make setup | data | data-real-tickets | test | lint | api | api-real | ui | demo | fixtures
```

## 7. Where to look first

`HANDOFF.md` (state and next tasks), `docs/METHOD.md` (how detection works and
how well), `docs/API.md` (contract), `docs/ARCHITECTURE.md` (structure).
