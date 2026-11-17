# Working agreement for agents (and humans)

Two people, each with their own coding agent, work in this repo. This file is how
they avoid stepping on each other. Read it before you edit anything.

## 1. Product rules that no change may break

1. **Ticket samples are not verified occupancy.** Never output or display seats
   available, a percentage full, passenger counts on board, or anything that
   reads like one. `relative_rank` is a rank and is never shown as a percentage.
2. **GTFS times are scheduled.** Never label a time as live, real-time, ETA or delay.
3. **Simulated data is always labelled.** When `provenance.simulated` is true the
   UI shows the simulated-data notice. Never present fixtures as real Delhi data.
4. **Insufficient evidence is a state, not a value.** It is never styled or
   worded as low crowding and never silently replaced by a guess.
5. **Flag, never guess.** Ambiguous or invalid records are reported for review.
   Fuzzy matches are suggestions only; a human turns them into aliases.
6. **Road traffic stays separate from passenger crowding.** Different module,
   different response field, never one blended number.
7. **No raw data, secrets or credentials in git.** Real feeds and ticket extracts
   live under `data/` (ignored). Only `fixtures/synthetic/` is tracked.
8. **No registering, submitting or deploying** without the owner saying so.

`backend/tests/test_api.py` and `backend/tests/test_fixtures.py` enforce parts of
this. Do not weaken those tests to get green.

## 2. Proposed ownership (a suggestion, not an agreed assignment)

Roansh and Aashu have not confirmed this split. Treat it as the default until
they say otherwise, and ask before working in the other person's area.

| Area | Paths | Proposed owner |
| --- | --- | --- |
| Data import, validation, matching | `backend/busplanner/{gtfs,tickets,matching,quality,textnorm,pipeline,synthetic}.py`, `fixtures/` | Roansh |
| Crowding model, planner, rankings | `backend/busplanner/{crowding,planner,network,config}.py` | Roansh |
| API server | `backend/busplanner/{api,dataset,traffic,cli}.py` | Roansh |
| Frontend and demo visuals | `frontend/` | Aashu |
| API contract | `backend/busplanner/schemas.py`, `docs/API.md`, `frontend/src/api/types.ts` | Both (see section 3) |
| Integration and tests | `backend/tests/`, `frontend/src/**/*.test.*`, `Makefile` | Both |
| Docs | `README.md`, `HANDOFF.md`, `AGENTS.md`, `docs/` | Both; whoever changes behaviour updates the doc |

## 3. Changing the API contract

The contract lives in three files that must agree:

* `backend/busplanner/schemas.py` (source of truth)
* `docs/API.md`
* `frontend/src/api/types.ts`

Rules:

* **Additive changes** (a new optional field, a new endpoint): the author updates
  all three files in one PR and mentions it in the PR description.
* **Breaking changes** (rename, removal, type change, new enum value the UI must
  handle): open the PR as a draft, tag the other owner, and do not merge until
  they have updated or approved the other side.
* The UI must ignore fields it does not know, and treat `reason.metrics` as
  informational only.
* The frontend can be built against `frontend/src/test/fixtures.ts` (mock data)
  without a running backend, so UI work never has to wait for backend work.

## 4. Branches and commits

* Never push to `main` directly. All work goes through a feature branch and a pull request.
* Branch names: `feat/<area>-<topic>`, `fix/<area>-<topic>`, `docs/<topic>`, where
  `<area>` is `data`, `model`, `api`, `ui` or `infra`. Example: `feat/ui-route-map`.
* One concern per branch. Keep a branch inside one ownership area where possible;
  a branch that touches both `backend/` and `frontend/` is a contract change and
  follows section 3.
* Rebase or merge `main` before opening the PR; do not rewrite someone else's branch.
* Commit messages: `type(scope): summary`, for example `feat(model): pool cells by corridor`.
* Before pushing: `make lint && make test`.

## 5. Files with special handling

| Path | Rule |
| --- | --- |
| `fixtures/synthetic/**` | Generated. Do not hand-edit. Change `backend/busplanner/synthetic.py`, run `make fixtures`, commit both. Expect to update test expectations that count fixture rows. |
| `frontend/package-lock.json` | Only changes together with `package.json`. Use `npm install <pkg>`, never edit by hand. |
| `backend/busplanner/config.py` | Thresholds change results everywhere. Change one value per PR and say why. |
| `data/**`, `.env` | Ignored. Never force-add. |
| `frontend/dist/`, `node_modules/`, `.venv/` | Build output. Ignored. |

## 6. Commands

```
make setup     # once
make data      # build the dataset from the SIMULATED fixtures
make test      # backend (pytest) + frontend (vitest)
make lint      # ruff + tsc
make api       # API on :8000 with reload
make ui        # Vite dev server on :5173, proxies /api to :8000
make demo      # build everything and serve UI + API on :8000
```

## 7. Where to look first

* `HANDOFF.md`: current state, known limitations, next tasks per owner.
* `docs/ARCHITECTURE.md`: stack, data flow, milestones.
* `docs/API.md`: the HTTP contract.
* `docs/DATA.md`: import paths, validation and matching rules, the crowding method and its fallbacks.
