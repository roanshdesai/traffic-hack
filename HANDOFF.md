# Handoff

State of the repo after the pivot to **early detection of overcrowding**
(17 Nov 2026). Written for the next person or agent.

## 1. What changed in the pivot

* **Main product** is now the overcrowding monitor: per-site status against the
  site's usual level, a one-hour forecast and an early warning. API at `/api/*`,
  UI "Overcrowding monitor" (default page).
* **Route planning is secondary.** Its code is untouched apart from paths: API
  moved to `/api/planner/*`, UI moved to `frontend/src/planner/` behind the
  "Journey planner (secondary)" tab. It still works and its tests still pass.
* **Reused, not rewritten:** the ticket importer (now feeds per-stop boardings),
  the issue log and data-quality report pattern, the road-traffic boundary,
  the simulated-data banner, disclaimers and data-quality panel, the Makefile
  and test guards.

## 2. Setup

```bash
make setup             # python venv + npm ci
make data              # both simulated datasets
make test              # backend + frontend tests
make demo              # build UI + data, serve on http://127.0.0.1:8000
make data-real-tickets # real Oct 2026 ticket file -> early-warning dataset (needs data/raw/2026-10/)
make api-real          # serve that dataset
```

Verified on Python 3.13 and Node 22: `make lint`, `make test` (132 backend
tests, 48 frontend tests), `make data`, `make data-real-tickets`, `make demo`.
The built UI was driven in a 390 px headless browser against both the simulated
and the real-ticket datasets: monitor, site detail with chart and forecast,
simulated banner present only for simulated data, no console errors, no
horizontal overflow.

## 3. What was added

| Path | What |
| --- | --- |
| `backend/busplanner/earlywarning/` | `config`, `schemas`, `sources`, `model`, `evaluate`, `pipeline`, `dataset`, `api`, `synthetic` |
| `backend/busplanner/api.py`, `cli.py` | Early-warning router mounted at `/api`; planner moved to `/api/planner`; `warn-*` CLI commands |
| `backend/tests/test_ew_*.py` | Import paths, model, backtest, API contract, fixture labelling |
| `fixtures/synthetic/earlywarning/` | SIMULATED: 5 sites, 3 weeks of 15-min counts, 5 injected events, planted defects |
| `frontend/src/components/monitor/`, `src/App.tsx`, `src/api/warning*.ts`, `src/lib/warningFormat.ts` | Monitor UI, replay control, site detail, SVG timeline, forecast table, alerts, evaluation panel |
| `frontend/src/planner/` | The former planner app (secondary) |
| `docs/METHOD.md` | Technical note: method, results, weaknesses |
| `docs/API.md` / `docs/API-planner.md` | New main contract / the planner's contract |
| `Makefile` | `data` builds both; `data-real-tickets`, `api-real` |

## 4. What works

* **Camera-count import** (CSV + sites file + column mapping) with validation,
  a privacy guard against identifying columns, and gap reporting.
* **Ticket-sample import**: real Oct 2026 Delhi e-tickets aggregate into hourly
  boardings for 1,275 boarding stops.
* **Usual levels** per site, day type and time, with fallbacks and an evidence grade.
* **Statuses** with plain-language reasons; operator thresholds for full-count sources.
* **Forecast** (60 min) with a likely range, and an **early warning** for
  sustained rises.
* **Backtest** on simulated events, and descriptive statistics plus a
  week-to-week stability check on real data.
* **UI**: replay time control, status summary, site list sorted by urgency,
  site detail with chart, alerts per day, evaluation and data-quality panels,
  separate road-traffic box, secondary planner tab.

Results (details in `docs/METHOD.md`):

* Simulated (test data, not evidence of real accuracy): 4/4 events detected,
  0 false alert episodes, both gradual build-ups warned 30 min before the alert,
  sudden events not warned (by design).
* Real tickets (no ground truth): 151 alert episodes at 114 of 1,275 stops over
  22 to 31 Oct; clustered on two Saturdays, partly a baseline effect; ticket-based
  warnings are weak (52 issued, 1 ahead of an alert).

Demo replay times (simulated): **18 Nov 17:00** Sim Stadium Stop (early warning,
then an alert from 17:30); **17 Nov 08:00** Sim Central Bus Terminal (sudden
spike, threshold alert); **19 Nov 11:00** Sim College Stop (sensor outage shown
as no data); **21 Nov 11:30** Sim Market Stop (build-up warned 30 min before the
12:00 alert); **20 Nov 07:45** Sim Metro Interchange Stop (fast surge, no warning).

## 5. Blocked

| Item | Why | To unblock |
| --- | --- | --- |
| Real camera counts | No source; needs an agreement with a camera owner and the owner's go-ahead; counts only | Provide an aggregated export (site, window, count); write a mapping |
| Google road traffic | No API key or billing; not requested | Owner decision. Boundary: `backend/busplanner/traffic.py` |
| Ground truth | No observed crowding or incident logs | Manual counts at a few stops, or operator incident records |
| Static GTFS | Needs a Delhi Transport Stack account | A team member signs up and requests it |
| Hackathon registration / submission | Owner's decision; closes 20 Nov 23:59 IST | See `docs/HACKATHON.md` |

Nothing was registered, submitted, deployed or connected.

## 6. Known limitations

* No real camera data, no ground truth: no result is validated.
* Thresholds are uncalibrated and were tuned while looking at the simulated data.
* Ticket counts measure e-ticket use, not people; stops are merged by name.
* Static baselines per build; a lasting change keeps alerting until rebuilt.
* Holidays are listed by hand (`--holiday`). Only 3 Saturdays of history in the real data.
* Forecast extends an existing trend only; it cannot predict a surge before it starts.
* Real-data dataset files are large (about 13 MB JSON) and load in a few seconds.
* The package is still named `busplanner`.
* No CI; no `main` branch yet, so no pull request.

## 7. Next tasks

The split is the **proposed** one from `AGENTS.md`, not an agreed assignment.

### Frontend and demo visuals (proposed: Aashu)

1. Design pass on the monitor and site detail; keep every rule in `AGENTS.md` section 1.
2. A map of sites coloured by status (sites have `lat`/`lon` for camera data; ticket sites need GTFS).
3. A "play" control that steps the replay automatically for the demo video.
4. An operator view: sites x hours heat map of alert and busier windows.
5. Commit a Playwright end-to-end test (monitor, detail, replay stepping).

### Data, modelling and backend (proposed: Roansh)

1. Find any ground truth (manual counts, incident logs) and score the real-data alerts.
2. Rolling baselines (last N weeks) and a proper holiday calendar.
3. Calibrate thresholds on a held-out simulated seed and, later, on real labels.
4. Per-site minimum sizes for ticket data; investigate the Saturday clusters.
5. If a camera source appears: map its export, check counting confidence, add per-site thresholds with the operator.
6. If road traffic is approved: add it as a separate context panel first; test it as a leading indicator in a separate study.

### Both

1. Decide the hackathon framing (`docs/HACKATHON.md`, "Pivot and the hackathon").
2. Create `main`, open a PR for this branch, agree the ownership split.
3. CI once the owner agrees; contract test between `schemas.py` and `warningTypes.ts`.
