# Method: early detection of overcrowding

Technical note for the main product. Code: `backend/busplanner/earlywarning/`.
Thresholds: `earlywarning/config.py` (all uncalibrated prototype defaults).

## 1. What it does

For each **site** (a stop, terminal or station) and each **time window**
(15 min for camera counts, 60 min for ticket samples) it answers three questions:

1. **Is it unusually busy right now?** Compare the count with what this site
   usually has for this day type and time. Status: usual, busier than usual,
   overcrowding alert, not enough history, or no data.
2. **What is likely in the next hour?** A short forecast with a likely range.
3. **Should someone be warned early?** Only when a rise has started, is
   sustained and is still climbing, and the forecast reaches an alert.

Everything runs on **recorded data replayed in time order**. At each replay
time, only data up to that time is used. Nothing is live.

## 2. Inputs ("people data")

| Source | What a count means | Coverage | Status today |
| --- | --- | --- | --- |
| Camera counts | People counted per window by camera counting software. An estimate. | `full_count` | **Simulated only.** Import path built and tested; no real camera feed. |
| Ticket samples | Ticket records whose boarding stop is the site, per hour. | `sample` | **Real:** Oct 2026 Delhi ONDC e-tickets (2.55 M valid rows). |
| Manual counts | Counts entered by staff. | `full_count` | Same CSV format as cameras; not exercised separately. |
| Road traffic (Google) | Vehicle congestion on roads. | n/a | **Not connected.** Separate context only (section 7). |

Camera input is **aggregated counts only**: `site_id, window_start, count`
(+ optional `confidence`). Columns that could identify people (image paths,
faces, track ids, plates) are ignored and reported. No images or identities
are stored or processed anywhere.

Ticket records are a **sample of passengers, not a headcount**. The Problem 3
brief puts e-ticketing at about 3 to 4% of bus tickets. From tickets the system
can show *unusual activity*, never *how full* a place is.

## 3. Validation (flag, never guess)

Rejected and reported: unknown site, unparseable timestamp, window not on a
window boundary (not shifted), outside service hours, negative or non-numeric
count, count above a site's plausible maximum (not capped), duplicate window.
Kept but excluded: readings with counting confidence below 0.5 (shown as "no
data"). Gaps in camera data are **no data**, never zero. For ticket samples, an
hour with no records inside service hours is zero sampled boardings.

## 4. Usual level (baseline)

Learned only from the **baseline period** (the first part of the data). The
**replay period** that follows is never used to learn it.

* Cell: site x day type x time slot. Day types: weekday / weekend-or-holiday,
  or, with `split_saturday`, weekday / Saturday / Sunday-or-holiday.
* Value: median of the counts, pooling the neighbouring slots within 15 min.
* Spread: `sigma = max(1.4826 x MAD, sqrt(median), 1)`. The `sqrt(median)`
  floor (count noise) stops very regular sites from alerting on small wobbles.
* Needs at least 3 days of history. Otherwise falls back to the same hour,
  then to the same slot on all days; otherwise "not enough history".
* Evidence grade: high (slot, 8+ days), medium, low (pooled).

## 5. Status rules

`ratio = observed / usual` and `z = (observed - usual) / sigma`.

| Status | Rule |
| --- | --- |
| Overcrowding alert | ratio >= 1.6 **and** z >= 4 **and** observed >= 10 **and** usual >= 5; **or** count >= an operator-set threshold (full-count sources only) |
| Busier than usual | ratio >= 1.3 and z >= 2 and observed >= 5 (also where an alert-sized jump sits on a usual level below 5) |
| Usual for this time | otherwise |
| Not enough history | no baseline (an operator threshold can still raise an alert) |
| No data | no usable reading |

The operator threshold is a **setting**, not a measured capacity, and is labelled
that way everywhere.

## 6. Forecast and early warning

* Forecast: a damped-trend (Holt) model on the ratio to usual over the last 4
  windows (level smoothing 0.6, trend smoothing 0.4, damping 0.8 per step). The
  predicted count is that ratio times the usual level of the target window.
  Horizon: up to 60 min. Range: `sigma x (1 + 0.25 x steps)` plus the trend's
  contribution.
* Early warning fires only if **all** hold: the current window is "busier than
  usual" on a usual level of at least 5; the previous window was also at least
  1.15x usual; the ratio is rising; and a forecast step reaches an alert.

The forecast extends a change that has already started. **It cannot foresee a
surge that has not begun**, so sudden spikes are caught when they happen.

## 7. Road traffic

Google road traffic would describe vehicles on roads, not people at stops. It
lives behind `backend/busplanner/traffic.py`, is returned as its own
`road_traffic` field and never changes a status, threshold or forecast. It is
not connected: it needs an API key, billing and the owner's go-ahead. A later
study could test whether congestion is a *leading indicator* (for example of bus
bunching before platform crowding), but that must be evaluated separately
before it is used.

## 8. Results

### On SIMULATED data (`make data`)

Five invented sites, 15-min camera counts, 2 to 22 Nov 2026. Baseline 2 to 15 Nov,
replay 16 to 22 Nov. Four injected events in the replay period are the ground
truth. **These numbers show the method behaves as designed. They say nothing
about accuracy on real crowds.** The thresholds were also chosen while looking at
this same test data, which flatters them.

| Measure | Value |
| --- | --- |
| Events detected | 4 of 4 |
| False alert episodes | 0 (35 site-days) |
| Window-level precision / recall | 1.00 / 0.70 |
| Detection delay after the surge passes 1.6x | median 15 min (0 to 45) |
| Gradual build-ups warned before the first alert | 2 of 2, 30 min ahead each |
| Fast disruption / sudden spike warned | 0 of 2 (by design: no build-up) |
| Early warnings issued / pointing at a real test event | 6 / 4 |

Recall of 0.70 means the alert switches on later than the true surge on gradual
events; the strict `z >= 4` rule trades that for no false alarms.

### On REAL ticket data (`make data-real-tickets`)

Oct 2026 Delhi ONDC e-tickets, 1,275 boarding stops with at least 300 records in
the baseline period (5,395 thinner stops left out). Baseline 1 to 21 Oct
(2 Oct treated as a holiday, Saturdays separate), replay 22 to 31 Oct, hourly
windows. **There is no ground truth, so accuracy is unknown.**

| Measure | Value |
| --- | --- |
| Windows assessed | 229,500 |
| Share usual / busier / alert | 95.9% / 4.1% / 0.07% |
| Alert episodes | 151 at 114 stops (0.012 per stop-day) |
| Early warnings issued | 52 (1 preceded an alert episode) |
| Weekday profile, week 1 vs week 2 (Pearson r) | median 0.90, 10th percentile 0.71 |

Alerts cluster on Saturday 24 Oct (35) and Saturday 31 Oct (45), mostly at 08:00
to 10:00 and 17:00 to 20:00. Before Saturdays got their own baseline they
dominated even more (162 of 225), so part of the remaining cluster is probably
still a baseline effect: only 3 Saturdays are available. Whether anything
unusual happened on those days is **not verified**. The ticket-based early
warning is weak: hourly sampled counts are too coarse and too noisy to forecast
from.

## 9. Known weaknesses

* No real camera data and no ground truth: nothing here is validated.
* Thresholds are uncalibrated and were tuned on simulated data.
* Ticket samples measure e-ticket use, which varies by stop and time for
  reasons unrelated to crowding (app adoption, conductor practice).
* Ticket sites are stop **names**; same-named stops are merged (no GTFS yet).
* A sustained change (a new route, a closed road) will alert until the
  baseline is rebuilt. Baselines are static per build.
* Holidays must be listed by hand.
* Small sites: floors (5 and 10 people/records) suppress statuses there.
