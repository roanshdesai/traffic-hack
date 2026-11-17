"""Static GTFS import and validation.

Loads a GTFS feed from a directory or a ``.zip`` and validates it. Records that
fail validation are dropped and reported; they are never repaired by guessing.
A trip with any invalid stop time is dropped whole, because a trip with a hole
in it would silently produce wrong segments and travel times.

GTFS times are *scheduled* times. Nothing here is live.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from pathlib import Path

from .config import DELHI_BBOX
from .quality import IssueLog
from .textnorm import code_key, name_key

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "stops.txt": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    "routes.txt": ["route_id"],
    "trips.txt": ["route_id", "service_id", "trip_id"],
    "stop_times.txt": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
}
CALENDAR_COLUMNS = [
    "service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "start_date", "end_date",
]  # fmt: skip
CALENDAR_DATES_COLUMNS = ["service_id", "date", "exception_type"]
WEEKDAYS = CALENDAR_COLUMNS[1:8]


@dataclass(slots=True)
class Stop:
    stop_id: str
    name: str
    lat: float
    lon: float
    code: str = ""


@dataclass(slots=True)
class Route:
    route_id: str
    short_name: str
    long_name: str
    agency_id: str = ""

    @property
    def display_name(self) -> str:
        return self.short_name or self.long_name or self.route_id


@dataclass(slots=True)
class StopTime:
    stop_id: str
    arrival: int  # seconds after midnight of the service day; may exceed 86400
    departure: int
    sequence: int


@dataclass(slots=True)
class Trip:
    trip_id: str
    route_id: str
    service_id: str
    headsign: str
    direction_id: str
    stop_times: list[StopTime] = field(default_factory=list)


@dataclass(slots=True)
class Service:
    service_id: str
    days: tuple[bool, ...] = (False,) * 7
    start: date | None = None
    end: date | None = None
    added: set[date] = field(default_factory=set)
    removed: set[date] = field(default_factory=set)

    def runs_on(self, day: date) -> bool:
        if day in self.removed:
            return False
        if day in self.added:
            return True
        if self.start is None or self.end is None:
            return False
        return self.start <= day <= self.end and self.days[day.weekday()]


@dataclass
class Feed:
    source: str
    stops: dict[str, Stop] = field(default_factory=dict)
    routes: dict[str, Route] = field(default_factory=dict)
    trips: dict[str, Trip] = field(default_factory=dict)
    services: dict[str, Service] = field(default_factory=dict)
    agencies: list[str] = field(default_factory=list)
    file_rows: dict[str, int] = field(default_factory=dict)

    def active_services(self, day: date) -> frozenset[str]:
        return frozenset(sid for sid, svc in self.services.items() if svc.runs_on(day))

    def date_range(self) -> tuple[date | None, date | None]:
        starts = [s.start for s in self.services.values() if s.start]
        ends = [s.end for s in self.services.values() if s.end]
        extra = [d for s in self.services.values() for d in s.added]
        lo = min(starts + extra) if starts or extra else None
        hi = max(ends + extra) if ends or extra else None
        return lo, hi


def parse_gtfs_time(value: str) -> int | None:
    """``"25:10:00"`` -> 90600. Returns None when the value is not a valid GTFS time."""
    parts = value.strip().split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    h, m, s = (int(p) for p in parts)
    if m > 59 or s > 59 or h > 47:
        return None
    return h * 3600 + m * 60 + s


def parse_gtfs_date(value: str) -> date | None:
    value = value.strip()
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


class _Source:
    """Uniform access to GTFS tables in a directory or a zip archive."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        self._members: dict[str, str] = {}
        if path.is_dir():
            self._members = {p.name: str(p) for p in path.iterdir() if p.suffix == ".txt"}
        elif path.is_file() and zipfile.is_zipfile(path):
            self._zip = zipfile.ZipFile(path)
            for member in self._zip.namelist():
                base = member.rsplit("/", 1)[-1]
                if base.endswith(".txt"):
                    self._members.setdefault(base, member)
        else:
            raise FileNotFoundError(f"GTFS source is neither a directory nor a zip: {path}")

    def has(self, name: str) -> bool:
        return name in self._members

    def rows(self, name: str) -> tuple[list[str], Iterator[dict[str, str]]]:
        """Return (header, row iterator). Headers and values are whitespace-stripped."""
        if self._zip is not None:
            handle = io.TextIOWrapper(self._zip.open(self._members[name]), encoding="utf-8-sig", newline="")
        else:
            handle = open(self._members[name], encoding="utf-8-sig", newline="")  # noqa: SIM115
        reader = csv.reader(handle)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            handle.close()
            return [], iter(())

        def gen() -> Iterator[dict[str, str]]:
            with handle:
                for raw in reader:
                    if not raw or all(not c.strip() for c in raw):
                        continue
                    yield {h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(header)}

        return header, gen()


def _check_columns(name: str, header: list[str], required: list[str], log: IssueLog, fatal: bool) -> bool:
    missing = [c for c in required if c not in header]
    if missing:
        log.add(
            "missing_column", "error", name,
            "Required column is missing; the table cannot be used.",
            sample={"missing": missing}, count=len(missing), fatal=fatal,
        )  # fmt: skip
        return False
    return True


def load_gtfs(path: str | Path) -> tuple[Feed, IssueLog]:
    """Load and validate a feed. Check ``log.fatal`` before using the result."""
    path = Path(path)
    log = IssueLog()
    feed = Feed(source=str(path))
    try:
        src = _Source(path)
    except FileNotFoundError as exc:
        log.add("source_not_found", "error", "(feed)", str(exc), fatal=True)
        return feed, log

    for name in REQUIRED_COLUMNS:
        if not src.has(name):
            log.add("missing_file", "error", name, "Required GTFS file is missing.", fatal=True)
    if not src.has("calendar.txt") and not src.has("calendar_dates.txt"):
        log.add(
            "missing_file", "error", "calendar.txt",
            "Neither calendar.txt nor calendar_dates.txt is present; service days are unknown.",
            fatal=True,
        )  # fmt: skip
    if not src.has("agency.txt"):
        log.add("missing_file", "warning", "agency.txt", "agency.txt is missing (required by the GTFS spec).")
    if log.fatal:
        return feed, log

    _load_agencies(src, feed)
    _load_stops(src, feed, log)
    _load_routes(src, feed, log)
    _load_calendar(src, feed, log)
    _load_trips(src, feed, log)
    _load_stop_times(src, feed, log)
    _post_checks(feed, log)
    if not feed.trips and not log.fatal:
        log.add("no_usable_trips", "error", "(feed)", "No trip survived validation.", fatal=True)
    return feed, log


def _load_agencies(src: _Source, feed: Feed) -> None:
    if not src.has("agency.txt"):
        return
    _header, rows = src.rows("agency.txt")
    n = 0
    for row in rows:
        n += 1
        if row.get("agency_name"):
            feed.agencies.append(row["agency_name"])
    feed.file_rows["agency.txt"] = n


def _load_stops(src: _Source, feed: Feed, log: IssueLog) -> None:
    name = "stops.txt"
    header, rows = src.rows(name)
    if not _check_columns(name, header, REQUIRED_COLUMNS[name], log, fatal=True):
        return
    min_lat, max_lat, min_lon, max_lon = DELHI_BBOX
    n = 0
    for row in rows:
        n += 1
        sid = row["stop_id"]
        if not sid:
            log.add("missing_id", "error", name, "Row has no stop_id; dropped.", sample={"row": n + 1})
            continue
        if sid in feed.stops:
            log.add("duplicate_id", "error", name, "Duplicate stop_id; later rows dropped.", sample=sid)
            continue
        try:
            lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                raise ValueError
        except ValueError:
            log.add(
                "invalid_coordinates", "error", name,
                "Stop has missing or impossible coordinates; stop dropped.",
                sample={"stop_id": sid, "stop_lat": row["stop_lat"], "stop_lon": row["stop_lon"]},
            )  # fmt: skip
            continue
        if not row["stop_name"]:
            log.add("missing_stop_name", "warning", name, "Stop has no name; it cannot be matched by name.",
                    sample=sid)  # fmt: skip
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            log.add(
                "stop_outside_region", "warning", name,
                "Stop lies outside the expected Delhi NCR bounding box; check its coordinates.",
                sample={"stop_id": sid, "lat": lat, "lon": lon},
            )  # fmt: skip
        feed.stops[sid] = Stop(sid, row["stop_name"], lat, lon, row.get("stop_code", ""))
    feed.file_rows[name] = n


def _load_routes(src: _Source, feed: Feed, log: IssueLog) -> None:
    name = "routes.txt"
    header, rows = src.rows(name)
    if not _check_columns(name, header, REQUIRED_COLUMNS[name], log, fatal=True):
        return
    n = 0
    for row in rows:
        n += 1
        rid = row["route_id"]
        if not rid:
            log.add("missing_id", "error", name, "Row has no route_id; dropped.", sample={"row": n + 1})
            continue
        if rid in feed.routes:
            log.add("duplicate_id", "error", name, "Duplicate route_id; later rows dropped.", sample=rid)
            continue
        short, long_ = row.get("route_short_name", ""), row.get("route_long_name", "")
        if not short and not long_:
            log.add("missing_route_name", "warning", name,
                    "Route has neither a short nor a long name; tickets can only match it by route_id.",
                    sample=rid)  # fmt: skip
        feed.routes[rid] = Route(rid, short, long_, row.get("agency_id", ""))
    feed.file_rows[name] = n

    by_key: dict[str, list[str]] = defaultdict(list)
    for route in feed.routes.values():
        if route.short_name:
            by_key[code_key(route.short_name)].append(route.route_id)
    for key, ids in sorted(by_key.items()):
        if len(ids) > 1:
            log.add(
                "duplicate_route_short_name", "warning", name,
                "Several routes share one short name once normalised. Tickets quoting that name "
                "will be flagged as ambiguous instead of matched.",
                sample={"name_key": key, "route_ids": ids},
            )  # fmt: skip


def _load_calendar(src: _Source, feed: Feed, log: IssueLog) -> None:
    if src.has("calendar.txt"):
        name = "calendar.txt"
        header, rows = src.rows(name)
        n = 0
        if _check_columns(name, header, CALENDAR_COLUMNS, log, fatal=False):
            for row in rows:
                n += 1
                sid = row["service_id"]
                start, end = parse_gtfs_date(row["start_date"]), parse_gtfs_date(row["end_date"])
                if not sid or start is None or end is None or start > end:
                    log.add("invalid_service", "error", name,
                            "Service has no id or an invalid date range; dropped.", sample=dict(row))  # fmt: skip
                    continue
                days = tuple(row[d] == "1" for d in WEEKDAYS)
                if not any(days):
                    log.add("service_without_days", "info", name,
                            "Service runs on no weekday (it may rely on calendar_dates.txt).", sample=sid)  # fmt: skip
                feed.services[sid] = Service(sid, days, start, end)
        feed.file_rows[name] = n
    if src.has("calendar_dates.txt"):
        name = "calendar_dates.txt"
        header, rows = src.rows(name)
        n = 0
        if _check_columns(name, header, CALENDAR_DATES_COLUMNS, log, fatal=False):
            for row in rows:
                n += 1
                day = parse_gtfs_date(row["date"])
                if not row["service_id"] or day is None or row["exception_type"] not in ("1", "2"):
                    log.add("invalid_calendar_date", "error", name,
                            "Exception row is invalid; dropped.", sample=dict(row))  # fmt: skip
                    continue
                svc = feed.services.setdefault(row["service_id"], Service(row["service_id"]))
                (svc.added if row["exception_type"] == "1" else svc.removed).add(day)
        feed.file_rows[name] = n
    if not feed.services:
        log.add("no_services", "error", "calendar.txt", "No usable service calendar.", fatal=True)


def _load_trips(src: _Source, feed: Feed, log: IssueLog) -> None:
    name = "trips.txt"
    header, rows = src.rows(name)
    if not _check_columns(name, header, REQUIRED_COLUMNS[name], log, fatal=True):
        return
    n = 0
    for row in rows:
        n += 1
        tid = row["trip_id"]
        if not tid:
            log.add("missing_id", "error", name, "Row has no trip_id; dropped.", sample={"row": n + 1})
            continue
        if tid in feed.trips:
            log.add("duplicate_id", "error", name, "Duplicate trip_id; later rows dropped.", sample=tid)
            continue
        if row["route_id"] not in feed.routes:
            log.add("unknown_route", "error", name, "Trip references a route that is not in routes.txt; dropped.",
                    sample={"trip_id": tid, "route_id": row["route_id"]})  # fmt: skip
            continue
        if row["service_id"] not in feed.services:
            log.add("unknown_service", "error", name,
                    "Trip references a service with no calendar; dropped because it never runs.",
                    sample={"trip_id": tid, "service_id": row["service_id"]})  # fmt: skip
            continue
        feed.trips[tid] = Trip(
            tid, row["route_id"], row["service_id"], row.get("trip_headsign", ""), row.get("direction_id", "")
        )
    feed.file_rows[name] = n


def _load_stop_times(src: _Source, feed: Feed, log: IssueLog) -> None:
    name = "stop_times.txt"
    header, rows = src.rows(name)
    if not _check_columns(name, header, REQUIRED_COLUMNS[name], log, fatal=True):
        return
    bad_trips: dict[str, str] = {}
    n = 0
    for row in rows:
        n += 1
        tid = row["trip_id"]
        trip = feed.trips.get(tid)
        if trip is None:
            log.add("unknown_trip", "error", name,
                    "Stop time references a trip that is missing or was dropped; ignored.", sample=tid)  # fmt: skip
            continue
        if tid in bad_trips:
            continue
        if row["stop_id"] not in feed.stops:
            bad_trips[tid] = "unknown_stop"
            log.add("unknown_stop", "error", name,
                    "Stop time references a stop that is missing or was dropped.",
                    sample={"trip_id": tid, "stop_id": row["stop_id"]})  # fmt: skip
            continue
        arr, dep = parse_gtfs_time(row["arrival_time"]), parse_gtfs_time(row["departure_time"])
        if arr is None and dep is None:
            code = "missing_time" if not row["arrival_time"] and not row["departure_time"] else "invalid_time"
            bad_trips[tid] = code
            log.add(code, "error", name,
                    "Stop time has no usable arrival/departure time. Untimed stops are not interpolated.",
                    sample={"trip_id": tid, "stop_sequence": row["stop_sequence"],
                            "arrival_time": row["arrival_time"], "departure_time": row["departure_time"]})  # fmt: skip
            continue
        arr = dep if arr is None else arr
        dep = arr if dep is None else dep
        try:
            seq = int(row["stop_sequence"])
        except ValueError:
            bad_trips[tid] = "invalid_stop_sequence"
            log.add("invalid_stop_sequence", "error", name, "stop_sequence is not an integer.",
                    sample={"trip_id": tid, "stop_sequence": row["stop_sequence"]})  # fmt: skip
            continue
        trip.stop_times.append(StopTime(row["stop_id"], arr, dep, seq))
    feed.file_rows[name] = n

    zero_duration = 0
    for tid, trip in feed.trips.items():
        if tid in bad_trips:
            continue
        sts = trip.stop_times
        if len(sts) < 2:
            bad_trips[tid] = "trip_too_short"
            log.add("trip_too_short", "warning", name,
                    "Trip has fewer than two stop times; dropped.", sample=tid)  # fmt: skip
            continue
        sts.sort(key=lambda st: st.sequence)
        problem = None
        for prev, cur in pairwise(sts):
            if cur.sequence == prev.sequence:
                problem = ("duplicate_stop_sequence", "Trip repeats a stop_sequence value.")
            elif cur.arrival < prev.departure or cur.departure < cur.arrival:
                problem = ("time_goes_backwards", "Scheduled times decrease along the trip.")
            elif cur.stop_id == prev.stop_id:
                problem = ("consecutive_duplicate_stop", "Trip lists the same stop twice in a row.")
            if problem:
                break
            if cur.arrival == prev.departure:
                zero_duration += 1
        if problem is None and sts[0].departure < sts[0].arrival:
            problem = ("time_goes_backwards", "Scheduled times decrease along the trip.")
        if problem:
            bad_trips[tid] = problem[0]
            log.add(problem[0], "error", name, problem[1] + " Trip dropped.", sample=tid)
    if zero_duration:
        log.add("zero_duration_segment", "info", name,
                "Consecutive stops share the same scheduled time (often minute rounding).",
                count=zero_duration)  # fmt: skip
    if bad_trips:
        reasons = Counter(bad_trips.values())
        log.add("trips_dropped", "warning", "trips.txt",
                "Trips removed because their stop times failed validation.",
                sample=dict(sorted(reasons.items())), count=len(bad_trips))  # fmt: skip
        for tid in bad_trips:
            del feed.trips[tid]


def _post_checks(feed: Feed, log: IssueLog) -> None:
    used_stops = {st.stop_id for trip in feed.trips.values() for st in trip.stop_times}
    unused = sorted(set(feed.stops) - used_stops)
    if unused:
        log.add("unused_stop", "info", "stops.txt", "Stop is not served by any usable trip.",
                sample=unused[:5], count=len(unused))  # fmt: skip
    used_routes = {trip.route_id for trip in feed.trips.values()}
    idle = sorted(set(feed.routes) - used_routes)
    if idle:
        log.add("route_without_trips", "info", "routes.txt", "Route has no usable trips.",
                sample=idle[:5], count=len(idle))  # fmt: skip
    names = Counter(name_key(s.name) for s in feed.stops.values() if s.name)
    shared = sum(1 for c in names.values() if c > 1)
    if shared:
        log.add("shared_stop_name", "info", "stops.txt",
                "Stop names used by more than one stop_id (normal for the two sides of a road). "
                "Name-based ticket matching is resolved per route and direction.",
                count=shared)  # fmt: skip
