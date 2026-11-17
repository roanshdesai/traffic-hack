# Frontend: Overcrowding Early Warning (prototype UI)

Mobile-first React UI. The **main product is the overcrowding monitor**: for each
monitored site it shows the status at a replay time, a short forecast and any
early warning. The **journey planner is a secondary view**, kept working on its
own endpoints under `/api/planner`.

The UI renders what the API returns and adds no numbers of its own.

Stack: Vite 8, React 19, TypeScript 7, Vitest 5 with Testing Library (jsdom).
Plain CSS, no UI framework, no router, no chart or map library (the day chart
is inline SVG).

## Commands

Run from `frontend/`.

| Command | What it does |
| --- | --- |
| `npm install` | Install dependencies. |
| `npm run dev` | Dev server on http://localhost:5173. Proxies `/api` to http://localhost:8000. |
| `npm test` | Unit and component tests (Vitest, run once). |
| `npm run typecheck` | `tsc --noEmit`. |
| `npm run build` | Typecheck, then production build into `dist/` (not committed). |
| `npm run preview` | Serve the production build locally. |

Without a processed dataset the API answers `503 no_dataset` and the UI says so.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE` | empty (same origin) | Base URL of the API, e.g. `http://localhost:8000`. See `.env.example`. |

## Structure

```
src/
  App.tsx                 Shell: title, nav (monitor | planner), simulated banner, replay note.
  api/warningTypes.ts     Main contract. Mirrors backend/busplanner/earlywarning/schemas.py 1:1.
  api/warningClient.ts    /api/meta, /overview, /sites, /sites/{id}/timeline, /alerts, /evaluation, /data-quality.
  api/types.ts            Planner contract (docs/API-planner.md).
  api/client.ts           Planner client (/api/planner/*) and the shared getJson + ApiError.
  lib/warningFormat.ts    Status wording, icons, replay-time arithmetic, reading text.
  lib/format.ts           Planner wording and helpers.
  components/monitor/
    MonitorView           Replay control, status chips, site list or site detail, alerts, evaluation, data quality.
    ReplayControl         Date + time + "-15 min" / "+15 min", bounded by the replay period.
    StatusChips           Sites per status at the replay time.
    SiteList              Sites in API order (most urgent first), name filter, "only alerts and warnings".
    SiteDetail            Reading, reasons, triggers, forecast, day chart, alert episodes.
    TimelineChart         Inline SVG: counts, usual range and median, alerts, gaps, replay line, forecast,
                          operator threshold, simulated test events (synthetic data only), data table.
    ForecastTable         "Forecast (estimate)".
    AlertEpisodes         Alert episodes for a day, with forecast lead time and simulated-event match.
    EvaluationPanel       Backtest metrics, or "No ground truth for this data".
    StatusBadge           Status pill (icon + text + colour) and the early-warning pill.
  components/             Shared: SimulatedBanner, DataQualityPanel (planner and warning reports),
                          Disclaimers (with the separate road-traffic box), ErrorState; plus planner components.
  planner/PlannerView.tsx Secondary journey planner (unchanged apart from API paths).
  test/warningFixtures.ts MOCK data for monitor tests. Not real, not from the backend.
  test/fixtures.ts        MOCK data for planner tests.
  styles.css              All styles. Colours are CSS variables (light + dark).
```

## Rules for the UI

The contract is `docs/API.md` and `backend/busplanner/earlywarning/schemas.py`.
If either changes, update `src/api/warningTypes.ts` in the same PR.

* **Show the simulated-data banner** whenever `provenance.simulated` is true.
* **Say it is a replay.** All data is recorded; never call anything live or real-time.
* **Readings are estimates.** Camera counts come from counting software; ticket
  data is a sample. Never show seats, capacity percentages, "% full" or
  "verified" for a reading. A ratio may be shown as "1.9× usual".
* **An operator threshold is a setting, not a verified capacity.** Say so wherever it appears.
* **"Not enough history" and "No data" are unknown states.** They are neutral,
  dashed and hatched, never styled like "Usual for this time".
* **Status never relies on colour alone.** Every status has an icon and text.
* **Simulated test events are drawn only for simulated data**, labelled as such.
* **Road traffic stays in its own footer box**, never inside a status card.
* Times are wall-clock strings (`YYYY-MM-DDTHH:MM`, Asia/Kolkata). Do arithmetic
  with the helpers in `lib/warningFormat.ts`, never with the viewer's local time zone.

`src/App.test.tsx` scans the rendered monitor for forbidden words.
