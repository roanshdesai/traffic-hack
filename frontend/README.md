# Frontend: Delhi bus journey planner (prototype UI)

Mobile-first React UI for the journey API. It renders what the API returns and
adds no numbers of its own.

Stack: Vite 8, React 19, TypeScript 7, Vitest 5 with Testing Library (jsdom).
Plain CSS, no UI framework, no router, no map library.

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

The UI needs the backend running with a processed dataset (`make data` in the
repo root). Without one the API answers `503 no_dataset` and the UI says so.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE` | empty (same origin) | Base URL of the API, e.g. `http://localhost:8000`. See `.env.example`. |

## Structure

```
src/
  api/types.ts        Contract types. Mirrors backend/busplanner/schemas.py 1:1.
  api/client.ts       fetch wrappers + ApiError ({code, message} from `detail`).
  lib/format.ts       Time, duration and wording helpers (all fixed wording lives here).
  components/
    SimulatedBanner   Persistent notice when provenance.simulated is true.
    SearchForm        Origin, destination, date, time.
    PlaceInput        Debounced autocomplete over GET /api/stops (ARIA combobox).
    Results           Request summary, OptionTabs and the selected option.
    OptionTabs        Fastest / Balanced / Less crowded (ARIA tabs).
    JourneyCard       A selected journey: times, reason, crowding summary, legs.
    LegTimeline       Ordered stops with per-segment relative crowding.
    CrowdingBadge     Level label + 3-bar cue (does not rely on colour).
    EvidenceBadge     "Evidence: high | medium | low | insufficient".
    InsufficientEvidence  The explicit "insufficient evidence" state.
    NoJourney, ErrorState  Empty and error states.
    DataQualityPanel  Lazy summary of GET /api/data-quality.
    Disclaimers       Footer: disclaimers, fallbacks, separate road-traffic note.
  test/fixtures.ts    MOCK data for tests only. Not real, not from the backend.
  styles.css          All styles. Colours are CSS variables (light + dark).
```

## Contract rules for the UI

The API contract is `docs/API.md` and `backend/busplanner/schemas.py`. If either
changes, update `src/api/types.ts` in the same PR.

Rules the UI must keep (tests in `Results.test.tsx` and `App.test.tsx` check them):

* **Never show `relative_rank` as a number or a percentage.** It is a rank among
  segments in the dataset, not occupancy. Show the level label only.
* **Never say** seats, available, occupancy, "% full" or "live". Ticket samples
  are not verified occupancy, and all times are scheduled GTFS times.
* Level wording is fixed: `lower` = "Relatively less crowded", `typical` =
  "About typical", `higher` = "Relatively more crowded",
  `insufficient_evidence` = "Not enough evidence".
* `insufficient_evidence` means "unknown". It gets its own neutral, hatched
  style. It must never look like low crowding and must never be green.
* Crowding must not rely on colour alone: keep the bar-count cue and the text.
* Show the support count ("N tickets over D days") and the pooling basis next
  to every segment estimate.
* Show the "Simulated data" banner whenever `provenance.simulated` is true.
* Road traffic stays in its own boxed note. Never merge it with crowding.
* Times are formatted by slicing the ISO string (`formatClock`), not with
  `Date`, so they do not shift with the viewer's time zone.
