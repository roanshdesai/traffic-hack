"""Deterministic generator for the SIMULATED camera-count fixtures.

Everything here is invented: five "Sim ..." sites, three weeks of 15-minute
people counts with weekday/weekend rhythms and random noise, a few injected
crowd events (the ground truth used to score the detector), sensor gaps and
deliberately broken rows for the validators. No real place, camera or person
is represented.
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20261116
FIRST_DAY = date(2026, 11, 2)  # Monday
DAYS = 21
BASELINE_DAYS = 14  # 2 Nov - 15 Nov learn usual levels; 16 Nov - 22 Nov are replayed
WINDOW = 15
START, END = 6 * 60, 22 * 60
ONSET_MULTIPLIER = 1.6

# site_id -> (name, kind, lat, lon, base level, am weight, pm weight, weekend factor, threshold, max_plausible)
SITES = {
    "SIM_SITE_01": ("Sim Central Bus Terminal", "terminal", 28.6000, 77.1500, 120, 1.0, 1.0, 0.75, 330, 2000),
    "SIM_SITE_02": ("Sim Metro Interchange Stop", "bus_stop", 28.6100, 77.1700, 80, 1.3, 1.1, 0.55, 230, 1500),
    "SIM_SITE_03": ("Sim Market Stop", "bus_stop", 28.6150, 77.1800, 45, 0.6, 0.9, 1.2, 140, 1000),
    "SIM_SITE_04": ("Sim Stadium Stop", "bus_stop", 28.5980, 77.1920, 35, 0.8, 0.8, 0.8, 120, 1000),
    "SIM_SITE_05": ("Sim College Stop", "bus_stop", 28.6200, 77.1900, 30, 1.4, 0.7, 0.3, 100, 800),
}

# (site, day offset, start "HH:MM", ramp_min, hold_min, fall_min, peak multiplier, kind, description)
EVENTS = [
    ("SIM_SITE_04", 16, "16:15", 150, 75, 30, 3.0, "event_crowd",
     "Simulated: crowd building gradually for two hours before an evening match."),
    ("SIM_SITE_02", 18, "07:30", 30, 60, 30, 2.6, "service_disruption",
     "Simulated: fast surge at the interchange after a rail disruption."),
    ("SIM_SITE_03", 19, "10:30", 120, 90, 45, 2.4, "market_day",
     "Simulated: festival sale building through the morning."),
    ("SIM_SITE_01", 15, "08:00", 0, 45, 15, 2.2, "sudden_spike",
     "Simulated: sudden spike after several buses were cancelled at once (no build-up to forecast)."),
    ("SIM_SITE_03", 5, "12:00", 15, 60, 15, 2.0, "market_day",
     "Simulated: an earlier busy day inside the baseline period."),
]  # fmt: skip


def _shape(minute: int, am: float, pm: float, weekend: bool) -> float:
    """Daily rhythm: a floor plus morning and evening peaks (flatter at weekends)."""

    def bump(centre: float, width: float) -> float:
        return math.exp(-(((minute - centre) / width) ** 2))

    if weekend:
        return 0.35 + 0.55 * bump(13 * 60, 210)
    return 0.3 + am * bump(8 * 60 + 45, 75) + pm * bump(18 * 60 + 15, 90)


def _poisson(rng: random.Random, lam: float) -> int:
    if lam < 30:
        threshold, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= threshold:
                return k
            k += 1
    return max(0, round(rng.gauss(lam, math.sqrt(lam))))


def _event_multiplier(event: tuple, moment: datetime) -> float:
    site, offset, clock, ramp, hold, fall, peak, *_ = event
    h, m = (int(x) for x in clock.split(":"))
    start = datetime.combine(FIRST_DAY + timedelta(days=offset), datetime.min.time()) + timedelta(hours=h, minutes=m)
    minutes = (moment - start).total_seconds() / 60
    if minutes < 0 or minutes >= ramp + hold + fall:
        return 1.0
    if minutes < ramp:
        return 1 + (peak - 1) * (minutes + WINDOW) / (ramp + WINDOW)
    if minutes < ramp + hold:
        return peak
    return 1 + (peak - 1) * (1 - (minutes - ramp - hold + WINDOW) / (fall + WINDOW))


def _windows(day: date):
    for minute in range(START, END, WINDOW):
        yield datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)


def generate() -> tuple[list[list], list[list], list[list]]:
    rng = random.Random(SEED)
    rows: list[list] = []
    for day_offset in range(DAYS):
        day = FIRST_DAY + timedelta(days=day_offset)
        weekend = day.weekday() >= 5
        for moment in _windows(day):
            minute = moment.hour * 60 + moment.minute
            for sid, (_n, _k, _la, _lo, level, am, pm, wk, _t, _mx) in SITES.items():
                lam = level * _shape(minute, am, pm, weekend) * (wk if weekend else 1.0)
                lam *= max((_event_multiplier(e, moment) for e in EVENTS if e[0] == sid), default=1.0)
                # Sensor outage: SIM_SITE_05 has no counts 10:00-13:00 on 19 Nov.
                if sid == "SIM_SITE_05" and day == date(2026, 11, 19) and 10 * 60 <= minute < 13 * 60:
                    continue
                confidence = round(rng.uniform(0.86, 0.99), 2)
                # Poor visibility: low counting confidence on SIM_SITE_03 late evenings on 2 replay days.
                if sid == "SIM_SITE_03" and day in (date(2026, 11, 17), date(2026, 11, 21)) and minute >= 21 * 60:
                    confidence = round(rng.uniform(0.25, 0.45), 2)
                rows.append([sid, moment.strftime("%Y-%m-%d %H:%M"), _poisson(rng, lam), confidence, "SIMULATED"])

    # Deliberately broken rows for the validators.
    rows += [
        ["SIM_SITE_01", "2026-11-03 09:00", 133, 0.95, "SIMULATED"],  # duplicate window
        ["SIM_SITE_02", "2026-11-03 09:07", 70, 0.95, "SIMULATED"],  # misaligned
        ["SIM_SITE_02", "2026-11-04 09:00", -5, 0.95, "SIMULATED"],  # negative (also a duplicate window)
        ["SIM_SITE_03", "2026-11-04 10:00", "many", 0.95, "SIMULATED"],  # not a number
        ["SIM_SITE_04", "2026-11-05 23:30", 12, 0.95, "SIMULATED"],  # outside service hours
        ["SIM_SITE_99", "2026-11-05 09:00", 50, 0.95, "SIMULATED"],  # unknown site
        ["SIM_SITE_05", "05/11/2026 9am", 50, 0.95, "SIMULATED"],  # bad timestamp
    ]
    # A glitch far above anything plausible, replacing a real window (rejected, leaving a gap).
    for row in rows:
        if row[0] == "SIM_SITE_01" and row[1] == "2026-11-06 12:00":
            row[2] = 99999
            break

    sites = [
        [sid, name, kind, f"{lat:.4f}", f"{lon:.4f}", threshold, max_plausible, "SIMULATED"]
        for sid, (name, kind, lat, lon, _l, _a, _p, _w, threshold, max_plausible) in SITES.items()
    ]
    events = []
    for event in EVENTS:
        sid, offset, clock, ramp, hold, fall, _peak, kind, description = event
        day = FIRST_DAY + timedelta(days=offset)
        h, m = (int(x) for x in clock.split(":"))
        start = datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m)
        over = [w for w in _windows(day) if _event_multiplier(event, w) >= ONSET_MULTIPLIER]
        onset, end = over[0], over[-1] + timedelta(minutes=WINDOW)
        events.append([sid, start.strftime("%Y-%m-%d %H:%M"), onset.strftime("%Y-%m-%d %H:%M"),
                       end.strftime("%Y-%m-%d %H:%M"), kind, description, "SIMULATED"])  # fmt: skip
    return rows, sites, events


README = """# SIMULATED early-warning fixtures

**Everything in this folder is synthetic.** It was produced by
`backend/busplanner/earlywarning/synthetic.py`. The sites, people counts and
crowd events are invented. They do not describe real places, cameras, people
or crowds.

* `sites.csv`: five "Sim ..." sites. `alert_threshold` is a made-up operator
  setting, not a capacity.
* `simulated_camera_counts.csv`: three weeks (2 to 22 Nov 2026) of 15-minute
  people counts, as camera counting software might report them, with a
  detector `confidence`. Counts only: no images, no identities.
* `simulated_events.csv`: the crowd events injected into the counts. They are
  the ground truth used to score detection and early warning on test data.
  `onset` is when the injected surge first reaches 1.6x the normal level.
* `mapping.json`: column mapping for the counts file.

Planted defects: a duplicate window, a misaligned timestamp, a negative count,
a non-numeric count, a window outside service hours, an unknown site, an
unparseable timestamp, an implausible 99,999 reading, a 3-hour sensor outage
and low-confidence evening readings.

Do not edit by hand. Regenerate with `make fixtures`.
"""


def write_fixtures(out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, sites, events = generate()

    def write(name: str, header: list[str], data: list[list]) -> None:
        with open(out_dir / name, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(data)

    write("simulated_camera_counts.csv", ["site_id", "window_start", "count", "confidence", "data_label"], rows)
    write("sites.csv", ["site_id", "name", "kind", "lat", "lon", "alert_threshold", "max_plausible", "data_label"],
          sites)  # fmt: skip
    write("simulated_events.csv", ["site_id", "start", "onset", "end", "kind", "description", "data_label"], events)
    mapping = {
        "_comment": "Column mapping for SIMULATED camera counts. Copy and edit for a real counter export.",
        "columns": {
            "site_id": "site_id",
            "window_start": "window_start",
            "count": "count",
            "confidence": "confidence",
        },  # fmt: skip
        "timestamp_formats": ["%Y-%m-%d %H:%M"],
    }
    (out_dir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(README, encoding="utf-8")
    return {"simulated_camera_counts.csv": len(rows), "sites.csv": len(sites), "simulated_events.csv": len(events)}
