"""Deterministic generator for the SIMULATED fixtures in ``fixtures/synthetic/``.

Everything produced here is invented: stop names, coordinates, timetables and
ticket rows. Names carry a ``Sim`` prefix, ids a ``SIM`` prefix, the agency is
named ``SIMULATED ...`` and every ticket row has ``data_label=SIMULATED`` so the
data cannot be mistaken for a real Delhi feed or real ridership.

The ticket file deliberately contains broken, ambiguous and unmatched rows so
that validation and matching have something to flag.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20261102
FIRST_DAY = date(2026, 11, 2)  # a Monday
SAMPLE_DAYS = 14
SERVICE_START_MIN = 6 * 60
SERVICE_END_MIN = 22 * 60

# place number -> (name, lat, lon)
PLACES: dict[int, tuple[str, float, float]] = {
    1: ("Sim Terminal", 28.6000, 77.1500),
    2: ("Sim Rose Garden", 28.6050, 77.1600),
    3: ("Sim Market", 28.6100, 77.1700),
    4: ("Sim Lake View", 28.6150, 77.1800),
    5: ("Sim College", 28.6200, 77.1900),
    6: ("Sim Depot", 28.6250, 77.2000),
    7: ("Sim Old Bridge", 28.5920, 77.1600),
    8: ("Sim Mill Road", 28.5940, 77.1720),
    9: ("Sim Clock Tower", 28.6040, 77.1840),
    10: ("Sim North Gate", 28.6250, 77.1650),
    11: ("Sim Library", 28.6080, 77.1770),
    12: ("Sim Stadium", 28.5980, 77.1920),
    13: ("Sim Canal Road", 28.6120, 77.1580),
    14: ("Sim Riverside", 28.6220, 77.1780),
    15: ("Sim Hill Park", 28.5900, 77.2000),
    16: ("Sim South End", 28.5820, 77.2080),
}

# route_id -> (short_name, places in direction 0, minutes per segment,
#              weekday headway, weekend headway, first-departure offset, both directions)
ROUTES: dict[str, tuple[str, list[int], int, int, int, int, bool]] = {
    "SIM_R1": ("S1", [1, 2, 3, 4, 5, 6], 5, 12, 18, 0, True),
    "SIM_R2": ("S2", [1, 7, 8, 9, 5, 6], 7, 20, 30, 4, True),
    "SIM_R3": ("S3", [10, 3, 11, 9, 12], 6, 15, 20, 2, True),
    "SIM_R4": ("S4", [1, 13, 14, 6], 7, 30, 45, 2, True),
    "SIM_R5": ("S5", [12, 15, 16], 8, 30, 45, 10, True),
    # Two different routes that share a short name once normalised: tickets
    # quoting "S6" must be flagged as ambiguous, not assigned to either.
    "SIM_R6A": ("S6", [2, 13, 14], 6, 60, 0, 20, False),
    "SIM_R6B": ("S 6", [10, 14, 4], 6, 60, 0, 40, False),
}
# A second stop pattern on S3 direction 0 that skips Sim Market (weekdays only).
R3_VARIANT_PLACES = [10, 11, 9, 12]
R3_VARIANT_DEPARTURES = [9 * 60 + 7, 17 * 60 + 7]

# route_id -> (weekday tickets per direction per day, weekend ditto, period weights)
# period weights order: early, am_peak, midday, pm_peak, late
TICKET_RATES: dict[str, tuple[int, int, tuple[float, ...]]] = {
    "SIM_R1": (44, 20, (0.06, 0.34, 0.20, 0.34, 0.06)),
    "SIM_R2": (12, 8, (0.10, 0.25, 0.30, 0.25, 0.10)),
    "SIM_R3": (16, 8, (0.08, 0.30, 0.25, 0.30, 0.07)),
}
PERIOD_WINDOWS = ((360, 420), (420, 660), (660, 960), (960, 1260), (1260, 1350))


def _stop_id(place: int, direction: int) -> str:
    return f"SIM_S{place:02d}{'A' if direction == 0 else 'B'}"


def _hms(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _gtfs_tables() -> dict[str, tuple[list[str], list[list]]]:
    stops: list[list] = []
    for place, (name, lat, lon) in PLACES.items():
        for direction, shift in ((0, 0.0), (1, 0.0003)):
            stops.append([_stop_id(place, direction), f"{place:02d}{'AB'[direction]}", name,
                          f"{lat:.4f}", f"{lon + shift:.4f}"])  # fmt: skip
    # Deliberate issue: an unused stop far outside the Delhi bounding box.
    stops.append(["SIM_S99A", "99A", "Sim Far Depot", "30.5000", "78.0000"])

    routes = [
        [rid, "SIM_AG", short, " - ".join(PLACES[p][0] for p in (places[0], places[-1])), 3]
        for rid, (short, places, *_rest) in ROUTES.items()
    ]
    trips: list[list] = []
    stop_times: list[list] = []

    def add_trip(trip_id: str, route_id: str, service: str, direction: int, places: list[int],
                 start: int, seg_min: int) -> None:  # fmt: skip
        trips.append([route_id, service, trip_id, PLACES[places[-1]][0], direction])
        for seq, place in enumerate(places, start=1):
            t = _hms(start + (seq - 1) * seg_min)
            stop_times.append([trip_id, t, t, _stop_id(place, direction), seq])

    for rid, (_short, places, seg_min, wk_headway, we_headway, offset, both) in ROUTES.items():
        for service, headway in (("SIM_WK", wk_headway), ("SIM_WE", we_headway)):
            if not headway:
                continue
            for direction in (0, 1) if both else (0,):
                ordered = places if direction == 0 else list(reversed(places))
                start = SERVICE_START_MIN + offset + (direction * 3)
                while start <= SERVICE_END_MIN:
                    tid = f"{rid}_{direction}_{service[-2:]}_{start // 60:02d}{start % 60:02d}"
                    add_trip(tid, rid, service, direction, ordered, start, seg_min)
                    start += headway
    for start in R3_VARIANT_DEPARTURES:
        add_trip(f"SIM_R3_0_WK_{start // 60:02d}{start % 60:02d}X", "SIM_R3", "SIM_WK", 0,
                 R3_VARIANT_PLACES, start, 6)  # fmt: skip

    # Deliberate issue: a trip whose scheduled times run backwards (must be dropped).
    trips.append(["SIM_R4", "SIM_WK", "SIM_BAD_BACKWARDS", "Sim Depot", 0])
    for seq, (place, minute) in enumerate(((1, 720), (13, 715), (14, 730)), start=1):
        stop_times.append(["SIM_BAD_BACKWARDS", _hms(minute), _hms(minute), _stop_id(place, 0), seq])

    return {
        "agency.txt": (
            ["agency_id", "agency_name", "agency_url", "agency_timezone"],
            [["SIM_AG", "SIMULATED Transit (not a real agency)", "https://example.invalid", "Asia/Kolkata"]],
        ),
        "stops.txt": (["stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon"], stops),
        "routes.txt": (["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"], routes),
        "calendar.txt": (
            [
                "service_id",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "start_date",
                "end_date",
            ],  # fmt: skip
            [
                ["SIM_WK", 1, 1, 1, 1, 1, 0, 0, "20260101", "20271231"],
                ["SIM_WE", 0, 0, 0, 0, 0, 1, 1, "20260101", "20271231"],
            ],  # fmt: skip
        ),
        "trips.txt": (["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"], trips),
        "stop_times.txt": (["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"], stop_times),
    }


def _ticket_rows() -> list[list]:
    rng = random.Random(SEED)
    rows: list[list] = []

    def stamp(day: date, minute: int) -> str:
        moment = datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute, seconds=rng.randrange(60))
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    def add(day: date, minute: int, route: str, board: str, alight: str, pax: object = 1) -> None:
        rows.append([f"SIM-{len(rows) + 1:06d}", stamp(day, minute), route, board, alight, pax, "SIMULATED"])

    days = [FIRST_DAY + timedelta(days=n) for n in range(SAMPLE_DAYS)]
    for day in days:
        weekend = day.weekday() >= 5
        for rid, (wk_rate, we_rate, weights) in TICKET_RATES.items():
            short, places = ROUTES[rid][0], ROUTES[rid][1]
            for direction in (0, 1):
                ordered = places if direction == 0 else list(reversed(places))
                last = len(ordered) - 1
                # Boardings are weighted towards the start of the route.
                board_weights = [last - i + (2 if i == 0 else 0) for i in range(last)]
                for _ in range(we_rate if weekend else wk_rate):
                    lo, hi = rng.choices(PERIOD_WINDOWS, weights=weights)[0]
                    minute = rng.randrange(lo, hi)
                    b = rng.choices(range(last), weights=board_weights)[0]
                    a = rng.randrange(b + 1, last + 1)
                    use_codes = rng.random() < 0.1
                    board = _stop_id(ordered[b], direction) if use_codes else PLACES[ordered[b]][0]
                    alight = _stop_id(ordered[a], direction) if use_codes else PLACES[ordered[a]][0]
                    # Formatting noise that normalisation is allowed to remove.
                    route = rng.choices([short, short.lower(), f"{short[0]}-{short[1:]}", f"{short[0]} {short[1:]}"],
                                        weights=[85, 5, 5, 5])[0]  # fmt: skip
                    pax = rng.choices([1, 2, 3], weights=[85, 10, 5])[0]
                    add(day, minute, route, board, alight, pax)

    d = days  # shorthand for the hand-written rows below
    # Route S4: far too few samples for any estimate (must stay "insufficient evidence").
    for n, (b, a) in enumerate(((1, 13), (1, 6), (13, 14), (14, 6), (1, 14), (13, 6))):
        add(d[n * 2], 8 * 60 + 10 + n, "S4", PLACES[b][0], PLACES[a][0])
    # Unknown routes (one is close to a real name; it must be suggested, not applied).
    for n in range(6):
        add(d[n], 9 * 60 + n, "S9", "Sim Terminal", "Sim Depot")
    for n in range(3):
        add(d[n], 10 * 60 + n, "S11", "Sim Terminal", "Sim Market")
    # Ambiguous route: two GTFS routes normalise to "S6".
    for n in range(5):
        add(d[n], 11 * 60 + n, "S6", "Sim Canal Road", "Sim Riverside")
    # Reviewed alias (see aliases.json): "Express-1" -> SIM_R1.
    for n in range(4):
        add(d[n], 8 * 60 + 30 + n, "Express-1", "Sim Terminal", "Sim College")
    # Misspelt boarding stop and unknown alighting stop.
    for n in range(4):
        add(d[n], 12 * 60 + n, "S1", "Sim Markt", "Sim Depot")
    for n in range(3):
        add(d[n], 13 * 60 + n, "S1", "Sim Terminal", "Sim Nowhere Chowk")
    # Stop codes in the wrong order for the only direction that has them.
    for n in range(3):
        add(d[n], 14 * 60 + n, "S1", "SIM_S04A", "SIM_S02A")
    # Weekday-only route sampled on a weekend: matched, but outside the schedule.
    add(d[5], 10 * 60, "SIM_R6A", "Sim Rose Garden", "Sim Riverside")
    add(d[6], 10 * 60, "SIM_R6A", "Sim Rose Garden", "Sim Riverside")
    # Boarding-only tickets (no alighting stop).
    for n in range(8):
        add(d[n], 15 * 60 + n, "S2", "Sim Terminal", "")
    # Rows that must fail validation.
    add(d[0], 16 * 60, "S1", "Sim Terminal", "Sim Depot", 0)
    add(d[0], 16 * 60 + 1, "S1", "Sim Terminal", "Sim Depot", -1)
    add(d[0], 16 * 60 + 2, "S1", "Sim Terminal", "Sim Depot", "two")
    add(d[0], 16 * 60 + 3, "S1", "Sim Terminal", "Sim Depot", 45)
    add(d[1], 16 * 60, "", "Sim Terminal", "Sim Depot")
    add(d[1], 16 * 60 + 1, "", "Sim Terminal", "Sim Depot")
    add(d[1], 16 * 60 + 2, "S1", "", "Sim Depot")
    add(d[1], 16 * 60 + 3, "S1", "", "Sim Depot")
    add(d[2], 16 * 60, "S1", "Sim Market", "Sim Market")
    add(d[2], 16 * 60 + 1, "S2", "Sim College", "Sim College")
    rows.append([f"SIM-{len(rows) + 1:06d}", "2026-11-03 25:61:00", "S1", "Sim Terminal", "Sim Depot", 1, "SIMULATED"])
    rows.append([f"SIM-{len(rows) + 1:06d}", "yesterday morning", "S1", "Sim Terminal", "Sim Depot", 1, "SIMULATED"])
    for original in (rows[0], rows[1], rows[2]):  # duplicate ticket ids
        rows.append(list(original))
    return rows


TICKET_HEADER = ["ticket_no", "issue_time", "route_no", "from_stop", "to_stop", "pax", "data_label"]
TICKET_MAPPING = {
    "_comment": "Maps the SIMULATED ticket file onto the canonical ticket fields. Copy and edit for real data.",
    "columns": {
        "ticket_id": "ticket_no",
        "issued_at": "issue_time",
        "route": "route_no",
        "board_stop": "from_stop",
        "alight_stop": "to_stop",
        "passengers": "pax",
        "direction": None,
    },
    "timestamp_formats": ["%Y-%m-%d %H:%M:%S"],
    "delimiter": ",",
    "encoding": "utf-8-sig",
}
ALIASES = {
    "_comment": "Human-reviewed overrides only. Never add an alias just because a suggestion looks close.",
    "routes": {"Express-1": "SIM_R1"},
    "stops": {},
}
FIXTURE_README = """# SIMULATED fixtures

**Everything in this folder is synthetic.** The stops, coordinates, routes,
timetables and ticket rows were invented by `backend/busplanner/synthetic.py`.
They do not describe real Delhi bus services, real ridership or real crowding,
and must not be presented as such.

* `gtfs/` is a tiny static GTFS feed (agency `SIMULATED Transit`).
* `tickets.csv` holds simulated ticket samples. Every row has `data_label=SIMULATED`
  and a `SIM-` ticket number.
* `ticket_mapping.json` maps the ticket columns onto the canonical ticket fields.
* `aliases.json` is the reviewed route/stop alias table.

The files contain deliberate defects (a backwards trip, an out-of-region stop,
duplicate route names, unknown and misspelt references, invalid rows) so the
validators and the matcher have something to flag.

Do not edit these files by hand. Regenerate them with:

```
make fixtures        # or: busplanner generate-fixtures
```

`backend/tests/test_fixtures.py` fails if the committed files drift from the generator.
"""


def write_fixtures(out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    (out_dir / "gtfs").mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, (header, rows) in _gtfs_tables().items():
        _write_csv(out_dir / "gtfs" / name, header, rows)
        counts[name] = len(rows)
    tickets = _ticket_rows()
    _write_csv(out_dir / "tickets.csv", TICKET_HEADER, tickets)
    counts["tickets.csv"] = len(tickets)
    (out_dir / "ticket_mapping.json").write_text(json.dumps(TICKET_MAPPING, indent=2) + "\n", encoding="utf-8")
    (out_dir / "aliases.json").write_text(json.dumps(ALIASES, indent=2) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(FIXTURE_README, encoding="utf-8")
    return counts
