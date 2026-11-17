# Transport Stack Hackathon 2026: Problem 2 fit

Sources, read 17 Nov 2026:
[hackathon page](https://delhi.transportstack.in/hackathon/),
[Problem 2 brief](https://docs.google.com/document/d/1ocS9rG4_E_Fb9DJcqTG8SClrLJJ_UJqGGAhgPbV8tr4/preview),
[registration and rules](https://whereuelevate.com/drills/transport-stack-hackathon-2026),
[data README](https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/README.md).
Re-check them before relying on any date below.

## Dates (IST)

| What | When |
| --- | --- |
| Team registration closes (Where U Elevate) | 20 Nov 2026, 23:59 |
| Phase 1 submission closes (Problem 1 or 2) | 24 Nov 2026, 18:29 |
| Phase 2 build sprint (about 10 to 12 shortlisted teams) | 24 Nov to 9 Dec 2026 |
| Finale at IIIT Delhi | 10 or 11 Dec 2026 (the two pages disagree) |

## Rules that affect us

* Teams of 2 or 3. One member registers the team and adds the others.
* Phase 1 needs: a proposal, a working prototype, a code repo URL, a README, a
  short technical note and a short demo video. Mock-only or slide-only
  submissions do not qualify. **The repo must be readable by the judges.**
* Original work. Open-source libraries and AI tools are allowed if credited.
* Judging (indicative): problem relevance; technical depth and correct use of
  the data; feasibility; innovation; usability and impact. Problem 2 is judged
  on how well the crowding estimate is grounded in the data and how clearly it
  is shown to commuters. "A simple planner with a sound crowding model is
  better than a polished planner with a weak one."
* Data access: the guidelines say to sign up on the Delhi Transport Stack
  platform and request datasets. The Phase 1 ticket file is also a public
  direct download linked from the hackathon page.

Nothing has been registered or submitted.

## Data received

`October-Delhi.csv.zip` downloaded to `data/raw/2026-10/` (git-ignored), SHA-256
verified against the published `SHA256SUMS`. Profile of the unpacked CSV:

| Item | Value |
| --- | --- |
| Rows | 2,559,899 tickets, 1 to 31 Oct 2026, all timestamps `+05:30` with microseconds |
| Source | ONDC e-ticketing only (data README). No ETM (conductor machine) records, despite the brief mentioning them. |
| `route` | 2,259 values; direction is a suffix: 1,104 end `UP`, 1,094 end `DOWN`, 61 neither. 354 have 10 or fewer tickets. |
| Stops | 7,148 distinct boarding names, 6,941 alighting names. Names only, no stop ids or codes. |
| `end_stop_name` | Present on every row (planned alighting stop). |
| `vehicle_number` | Present on 51% of rows (blank or `NULL` otherwise); 6,809 vehicles, almost all seen on more than one route. |
| `passenger_count` | 1 (93%), 2, 3; a single row has 6. |
| `ticket_type_id` | Always 1. |
| `is_ac` | True on 80% of rows. |
| Time of day | Peaks 08:00 to 10:00 and 17:00 to 20:00. |
| Low days | 2 Oct (Gandhi Jayanti), 20 Oct (a Tuesday at about half normal volume; check whether it was a holiday), and Sundays. Useful spot checks. |

Our importer reads it with `config/ticket_mappings/ondc_2026_10.json`:

```
.venv/bin/busplanner validate-tickets --tickets data/raw/2026-10/October-Delhi.csv \
  --mapping config/ticket_mappings/ondc_2026_10.json
```

Result: 2,559,796 rows valid, 103 rejected (boarding stop equals alighting
stop), about 40 s. Tickets issued before 04:00 on 1 Oct belong to the
30 Sep service day.

## Still blocked

| Item | Why | To unblock |
| --- | --- | --- |
| Static GTFS | Only available through a Transport Stack platform account and dataset request. Without it, tickets cannot be matched to stop sequences, so no segment estimates can be made from the real data. | A team member signs up at delhi.transportstack.in and requests the static bus GTFS, then puts it in `data/raw/`. |
| Team registration | Has to be done by a team member on Where U Elevate before 20 Nov 23:59 IST. | Roansh or Aashu registers. |

## Gaps between the prototype and the brief

| The brief asks for | Prototype today | Gap |
| --- | --- | --- |
| On-board load by route, direction, stretch and time of day, from a running count per bus trip | Relative index per segment from all tickets, no per-trip running count | Build a per-vehicle running count using `vehicle_number` (51% of rows); compare with the pooled estimate. |
| A level the commuter understands, e.g. "seats available, standing room, crowded" | Relative levels only: lower / typical / higher / insufficient evidence | **Open decision, see below.** |
| Outputs operators can read (overloaded routes and hours) | Commuter view only | Add a route-by-hour view and an export. |
| Queryable or map display by route, stretch and time | API by journey only; no map | Add a segment query endpoint and a map (frontend). |
| Checks against peaks, busy corridors, weekday vs weekend, week-to-week stability | None on real data | Add a validation report once GTFS is in. |
| Pass holders, planned vs actual alighting, bus size | Documented as limits | Keep documenting; use `is_ac` only if the organisers confirm it says something about vehicle size. |
| Technical note | `docs/DATA.md` covers most of it | Write a short submission note. |
| Demo video, proposal | None | To do before 24 Nov. |

## Open decision: absolute crowding labels

The brief suggests labels such as "seats available" and "standing room". The
project rules (`AGENTS.md`) forbid claiming seats or percentage full, because
ticket samples are not verified occupancy.

This data makes that rule matter more, not less: it is ONDC e-ticketing only.
The Problem 3 brief says e-ticketing captures about 3 to 4% of bus tickets. A
running count from it is a count of e-ticket holders on board, not of
passengers. Turning it into seats or standing room needs a scale factor per
route and hour (which the data does not provide) and the bus capacity (which it
does not give either).

Options:

1. **Keep relative levels for commuters** (current), and add the per-trip
   e-ticket running count as an operator-facing, clearly labelled sample measure.
2. **Add indicative comfort bands** ("likely seats / likely standing / likely
   crowded") derived from a stated scale factor and capacity assumption, shown
   with the assumption and the evidence grade every time.
3. **Ask the organisers** whether ETM data or a published e-ticket share per
   route will be provided, and decide after.

Recommendation: 1 now, and 3 in parallel. Move to 2 only if the organisers
provide a defensible scale factor.
