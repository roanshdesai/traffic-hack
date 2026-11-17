"""Derived timetable structures: stop patterns, places and transfer links."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from math import cos, radians

from .config import PlannerConfig
from .gtfs import Feed, Stop, Trip
from .textnorm import haversine_m, name_key


@dataclass
class Pattern:
    """All trips of one route that visit exactly the same ordered list of stops."""

    pattern_id: str
    route_id: str
    direction_id: str
    stop_ids: tuple[str, ...]
    headsign: str
    trips: list[Trip] = field(default_factory=list)
    #: Mean scheduled seconds from departing stop 0 to departing stop i.
    offsets: list[float] = field(default_factory=list)

    def indices_of(self, stop_id: str) -> list[int]:
        return [i for i, s in enumerate(self.stop_ids) if s == stop_id]


@dataclass
class PlaceGroup:
    place_id: str
    name: str
    stop_ids: list[str]
    lat: float
    lon: float
    routes: list[str]


class Network:
    def __init__(self, feed: Feed, config: PlannerConfig | None = None) -> None:
        self.feed = feed
        self.config = config or PlannerConfig()
        self.patterns: dict[str, Pattern] = {}
        self.patterns_by_route: dict[str, list[Pattern]] = defaultdict(list)
        self.stop_patterns: dict[str, list[tuple[Pattern, int]]] = defaultdict(list)
        self.trip_pattern: dict[str, Pattern] = {}
        self.places: dict[str, PlaceGroup] = {}
        self.place_of_stop: dict[str, str] = {}
        self.transfer_links: dict[str, list[tuple[str, float]]] = {}
        self._build_patterns()
        self._build_places()
        self._build_transfer_links()

    # -- patterns ---------------------------------------------------------
    def _build_patterns(self) -> None:
        for trip in self.feed.trips.values():
            stops = tuple(st.stop_id for st in trip.stop_times)
            digest = hashlib.sha1("|".join(stops).encode()).hexdigest()[:8]
            pid = f"{trip.route_id}:{trip.direction_id or '-'}:{digest}"
            pattern = self.patterns.get(pid)
            if pattern is None:
                pattern = self.patterns[pid] = Pattern(pid, trip.route_id, trip.direction_id, stops, trip.headsign)
                self.patterns_by_route[trip.route_id].append(pattern)
                for i, sid in enumerate(stops):
                    self.stop_patterns[sid].append((pattern, i))
            pattern.trips.append(trip)
            self.trip_pattern[trip.trip_id] = pattern
        for pattern in self.patterns.values():
            pattern.trips.sort(key=lambda t: (t.stop_times[0].departure, t.trip_id))
            n = len(pattern.trips)
            sums = [0.0] * len(pattern.stop_ids)
            for trip in pattern.trips:
                base = trip.stop_times[0].departure
                for i, st in enumerate(trip.stop_times):
                    sums[i] += st.departure - base
            pattern.offsets = [s / n for s in sums]
        for patterns in self.patterns_by_route.values():
            patterns.sort(key=lambda p: p.pattern_id)

    # -- places -----------------------------------------------------------
    def _build_places(self) -> None:
        served = set(self.stop_patterns)
        by_name: dict[str, list[Stop]] = defaultdict(list)
        for stop in self.feed.stops.values():
            if stop.stop_id in served:
                by_name[name_key(stop.name) or f"#{stop.stop_id}"].append(stop)
        radius = self.config.place_radius_m
        for stops in by_name.values():
            stops.sort(key=lambda s: s.stop_id)
            clusters: list[list[Stop]] = []
            for stop in stops:
                for cluster in clusters:
                    anchor = cluster[0]
                    if haversine_m(anchor.lat, anchor.lon, stop.lat, stop.lon) <= radius:
                        cluster.append(stop)
                        break
                else:
                    clusters.append([stop])
            for cluster in clusters:
                pid = f"place:{cluster[0].stop_id}"
                routes = sorted(
                    {
                        self.feed.routes[p.route_id].display_name
                        for s in cluster
                        for p, _i in self.stop_patterns[s.stop_id]
                    }
                )
                self.places[pid] = PlaceGroup(
                    pid,
                    cluster[0].name or cluster[0].stop_id,
                    [s.stop_id for s in cluster],
                    sum(s.lat for s in cluster) / len(cluster),
                    sum(s.lon for s in cluster) / len(cluster),
                    routes,
                )
                for s in cluster:
                    self.place_of_stop[s.stop_id] = pid

    def resolve_place(self, ref: str) -> PlaceGroup | None:
        """Accept a ``place_id`` or a single served ``stop_id``."""
        if ref in self.places:
            return self.places[ref]
        if ref in self.stop_patterns:
            stop = self.feed.stops[ref]
            parent = self.places[self.place_of_stop[ref]]
            return PlaceGroup(f"stop:{ref}", stop.name or ref, [ref], stop.lat, stop.lon, parent.routes)
        return None

    def search_places(self, query: str, limit: int) -> list[PlaceGroup]:
        key = name_key(query)
        ranked: list[tuple[int, str, PlaceGroup]] = []
        for place in self.places.values():
            pkey = name_key(place.name)
            if not key:
                rank = 2
            elif pkey.startswith(key):
                rank = 0
            elif any(tok.startswith(key) for tok in pkey.split()):
                rank = 1
            elif key in pkey:
                rank = 2
            else:
                continue
            ranked.append((rank, pkey, place))
        ranked.sort(key=lambda r: (r[0], r[1], r[2].place_id))
        return [p for _r, _k, p in ranked[:limit]]

    # -- transfers --------------------------------------------------------
    def _build_transfer_links(self) -> None:
        """Stops within ``place_radius_m`` of each other (grid-bucketed)."""
        radius = self.config.place_radius_m
        stops = [self.feed.stops[sid] for sid in self.stop_patterns]
        if not stops:
            return
        lat0 = sum(s.lat for s in stops) / len(stops)
        deg_lat = radius / 111_320.0
        deg_lon = radius / (111_320.0 * max(cos(radians(lat0)), 0.1))
        grid: dict[tuple[int, int], list[Stop]] = defaultdict(list)
        for s in stops:
            grid[(int(s.lat / deg_lat), int(s.lon / deg_lon))].append(s)
        for s in stops:
            gx, gy = int(s.lat / deg_lat), int(s.lon / deg_lon)
            links: list[tuple[str, float]] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in grid.get((gx + dx, gy + dy), ()):
                        d = 0.0 if other.stop_id == s.stop_id else haversine_m(s.lat, s.lon, other.lat, other.lon)
                        if d <= radius:
                            links.append((other.stop_id, d))
            links.sort(key=lambda link: (link[1], link[0]))
            self.transfer_links[s.stop_id] = links
