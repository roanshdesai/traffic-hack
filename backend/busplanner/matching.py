"""Match ticket route and stop references to GTFS.

Rule of the module: **flag, never guess**. A ticket is used for crowding only
when its route resolves to exactly one GTFS route and its boarding/alighting
stops resolve to exactly one ordered run of stops on that route. Everything
else gets an explicit status and lands in the review lists of the data-quality
report. Fuzzy matches are offered as *suggestions* for a human to turn into
aliases; they are never applied automatically.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .network import Network
from .quality import IssueLog
from .textnorm import code_key, name_key
from .tickets import Ticket

MATCHED = "matched"
MATCHED_BOARD_ONLY = "matched_board_only"
UNMATCHED_ROUTE = "unmatched_route"
AMBIGUOUS_ROUTE = "ambiguous_route"
UNMATCHED_BOARD_STOP = "unmatched_board_stop"
UNMATCHED_ALIGHT_STOP = "unmatched_alight_stop"
AMBIGUOUS_PATH = "ambiguous_path"
INVALID_STOP_ORDER = "invalid_stop_order"

STATUS_DESCRIPTIONS: dict[str, str] = {
    MATCHED: "Route, boarding stop and alighting stop resolve to one ordered run of stops. Used for crowding.",
    MATCHED_BOARD_ONLY: "Route and boarding stop resolve, but the ticket has no alighting stop. "
    "Not used for segment loads.",
    UNMATCHED_ROUTE: "Route reference matches no GTFS route.",
    AMBIGUOUS_ROUTE: "Route reference matches more than one GTFS route.",
    UNMATCHED_BOARD_STOP: "Boarding stop is not on the matched route.",
    UNMATCHED_ALIGHT_STOP: "Alighting stop is not on the matched route.",
    AMBIGUOUS_PATH: "Stops match more than one distinct run of stops on the route "
    "(route variants or a loop); the segments travelled are unknown.",
    INVALID_STOP_ORDER: "Both stops are on the route but never in boarding-then-alighting order.",
}
REVIEW_LIMIT = 20
SUGGESTION_CUTOFF = 0.8


@dataclass(frozen=True)
class Aliases:
    """Human-reviewed overrides: ticket reference -> GTFS id."""

    routes: dict[str, str] = field(default_factory=dict)  # code_key(ref) -> route_id
    stops: dict[str, str] = field(default_factory=dict)  # name_key(ref) -> stop_id

    @classmethod
    def load(cls, path: str | Path | None) -> Aliases:
        if path is None:
            return cls()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            routes={code_key(k): v for k, v in (raw.get("routes") or {}).items()},
            stops={name_key(k): v for k, v in (raw.get("stops") or {}).items()},
        )


@dataclass(slots=True)
class TicketMatch:
    ticket: Ticket
    status: str
    route_id: str | None = None
    route_method: str | None = None
    #: stop_ids from boarding to alighting, inclusive (only when status == matched)
    path: tuple[str, ...] = ()
    #: scheduled seconds from boarding until the bus departs path[k], k < len(path) - 1
    offsets: tuple[float, ...] = ()
    detail: str = ""


@dataclass
class MatchResult:
    matches: list[TicketMatch]
    report: dict[str, Any]
    log: IssueLog


class Matcher:
    def __init__(self, network: Network, aliases: Aliases | None = None) -> None:
        self.network = network
        self.aliases = aliases or Aliases()
        self.log = IssueLog()
        feed = network.feed
        self._route_keys: dict[str, dict[str, str]] = defaultdict(dict)
        for route in feed.routes.values():
            for value, method in (
                (route.long_name, "route_long_name"),
                (route.route_id, "route_id"),
                (route.short_name, "route_short_name"),
            ):
                if value and code_key(value):
                    self._route_keys[code_key(value)][route.route_id] = method
        self._stop_keys: dict[str, tuple[str, str, str]] = {
            s.stop_id: (code_key(s.stop_id), code_key(s.code), name_key(s.name)) for s in feed.stops.values()
        }
        for ref, route_id in self.aliases.routes.items():
            if route_id not in feed.routes:
                self.log.add("alias_target_unknown", "warning", "aliases",
                             "Route alias points at a route_id that is not in the feed; alias ignored.",
                             sample={"alias": ref, "route_id": route_id})  # fmt: skip
        for ref, stop_id in self.aliases.stops.items():
            if stop_id not in feed.stops:
                self.log.add("alias_target_unknown", "warning", "aliases",
                             "Stop alias points at a stop_id that is not in the feed; alias ignored.",
                             sample={"alias": ref, "stop_id": stop_id})  # fmt: skip
        self._route_cache: dict[str, tuple[str, str | None, str | None, str]] = {}
        self._stop_cache: dict[tuple[str, str, str, str], tuple[str, tuple[str, ...], tuple[float, ...], str]] = {}

    # -- routes -----------------------------------------------------------
    def match_route(self, ref: str) -> tuple[str, str | None, str | None, str]:
        """Return (status, route_id, method, detail). Status is '' when the route resolved."""
        cached = self._route_cache.get(ref)
        if cached is not None:
            return cached
        key = code_key(ref)
        feed = self.network.feed
        alias = self.aliases.routes.get(key)
        if alias and alias in feed.routes:
            result = ("", alias, "alias", "")
        else:
            candidates = self._route_keys.get(key, {})
            if len(candidates) == 1:
                ((route_id, method),) = candidates.items()
                result = ("", route_id, method, "")
            elif len(candidates) > 1:
                result = (AMBIGUOUS_ROUTE, None, None, ", ".join(sorted(candidates)))
            else:
                result = (UNMATCHED_ROUTE, None, None, "")
        self._route_cache[ref] = result
        return result

    # -- stops ------------------------------------------------------------
    def _stop_matches(self, stop_id: str, ref_code: str, ref_name: str, alias_stop: str | None) -> bool:
        if alias_stop is not None:
            return stop_id == alias_stop
        id_key, code, name = self._stop_keys[stop_id]
        return (bool(ref_code) and ref_code in (id_key, code)) or (bool(ref_name) and ref_name == name)

    def match_stops(
        self, route_id: str, board_ref: str, alight_ref: str, direction_ref: str = ""
    ) -> tuple[str, tuple[str, ...], tuple[float, ...], str]:
        cache_key = (route_id, board_ref, alight_ref, direction_ref)
        cached = self._stop_cache.get(cache_key)
        if cached is not None:
            return cached
        feed = self.network.feed
        patterns = self.network.patterns_by_route.get(route_id, [])
        if direction_ref:
            same_direction = [p for p in patterns if p.direction_id == direction_ref]
            patterns = same_direction or patterns

        def keys(ref: str) -> tuple[str, str, str | None]:
            alias = self.aliases.stops.get(name_key(ref))
            return code_key(ref), name_key(ref), alias if alias in feed.stops else None

        b_code, b_name, b_alias = keys(board_ref)
        a_code, a_name, a_alias = keys(alight_ref) if alight_ref else ("", "", None)
        board_found = alight_found = False
        feasible: dict[tuple[str, ...], tuple[float, ...]] = {}
        for pattern in patterns:
            board_idx = [i for i, s in enumerate(pattern.stop_ids) if self._stop_matches(s, b_code, b_name, b_alias)]
            board_found = board_found or bool(board_idx)
            if not alight_ref:
                continue
            alight_idx = [j for j, s in enumerate(pattern.stop_ids) if self._stop_matches(s, a_code, a_name, a_alias)]
            alight_found = alight_found or bool(alight_idx)
            for i in board_idx:
                for j in alight_idx:
                    if i < j:
                        path = pattern.stop_ids[i : j + 1]
                        if path not in feasible:
                            feasible[path] = tuple(pattern.offsets[k] - pattern.offsets[i] for k in range(i, j))

        if not board_found:
            result = (UNMATCHED_BOARD_STOP, (), (), "")
        elif not alight_ref:
            result = (MATCHED_BOARD_ONLY, (), (), "")
        elif not alight_found:
            result = (UNMATCHED_ALIGHT_STOP, (), (), "")
        elif not feasible:
            result = (INVALID_STOP_ORDER, (), (), "")
        elif len(feasible) > 1:
            result = (AMBIGUOUS_PATH, (), (), f"{len(feasible)} distinct stop sequences")
        else:
            ((path, offsets),) = feasible.items()
            result = (MATCHED, path, offsets, "")
        self._stop_cache[cache_key] = result
        return result

    # -- tickets ----------------------------------------------------------
    def match_ticket(self, ticket: Ticket) -> TicketMatch:
        status, route_id, method, detail = self.match_route(ticket.route_ref)
        if status:
            return TicketMatch(ticket, status, detail=detail)
        assert route_id is not None
        status, path, offsets, detail = self.match_stops(
            route_id, ticket.board_ref, ticket.alight_ref, ticket.direction_ref
        )
        return TicketMatch(ticket, status, route_id, method, path, offsets, detail)

    def match_all(self, tickets: list[Ticket]) -> MatchResult:
        matches = [self.match_ticket(t) for t in tickets]
        return MatchResult(matches, self._report(matches), self.log)

    # -- reporting --------------------------------------------------------
    def _suggest(self, key: str, candidates: dict[str, str]) -> list[str]:
        close = difflib.get_close_matches(key, list(candidates), n=3, cutoff=SUGGESTION_CUTOFF)
        return [candidates[c] for c in close]

    def _report(self, matches: list[TicketMatch]) -> dict[str, Any]:
        feed = self.network.feed
        by_status = Counter(m.status for m in matches)
        by_method = Counter(m.route_method for m in matches if m.route_method)
        total = len(matches)

        unmatched_routes: Counter[str] = Counter()
        ambiguous_routes: dict[str, tuple[int, str]] = {}
        stop_problems: dict[tuple[str, str, str, str], int] = Counter()
        path_problems: dict[tuple[str, str, str, str, str], int] = Counter()
        for m in matches:
            t = m.ticket
            if m.status == UNMATCHED_ROUTE:
                unmatched_routes[t.route_ref] += 1
            elif m.status == AMBIGUOUS_ROUTE:
                n, _d = ambiguous_routes.get(t.route_ref, (0, ""))
                ambiguous_routes[t.route_ref] = (n + 1, m.detail)
            elif m.status == UNMATCHED_BOARD_STOP:
                stop_problems[(m.route_id or "", "board", t.board_ref, m.status)] += 1
            elif m.status == UNMATCHED_ALIGHT_STOP:
                stop_problems[(m.route_id or "", "alight", t.alight_ref, m.status)] += 1
            elif m.status in (AMBIGUOUS_PATH, INVALID_STOP_ORDER):
                path_problems[(m.route_id or "", t.board_ref, t.alight_ref, m.status, m.detail)] += 1

        route_names = {code_key(r.display_name): r.display_name for r in feed.routes.values()}
        review_routes = [
            {"route_ref": ref, "tickets": n, "suggestions_not_applied": self._suggest(code_key(ref), route_names)}
            for ref, n in unmatched_routes.most_common(REVIEW_LIMIT)
        ]
        review_ambiguous = [
            {"route_ref": ref, "tickets": n, "candidate_route_ids": detail.split(", ")}
            for ref, (n, detail) in sorted(ambiguous_routes.items(), key=lambda kv: -kv[1][0])[:REVIEW_LIMIT]
        ]
        review_stops = []
        for (route_id, role, ref, _status), n in sorted(stop_problems.items(), key=lambda kv: -kv[1])[:REVIEW_LIMIT]:
            names = {
                name_key(feed.stops[s].name): feed.stops[s].name
                for p in self.network.patterns_by_route.get(route_id, [])
                for s in p.stop_ids
            }
            review_stops.append(
                {
                    "route_id": route_id,
                    "role": role,
                    "stop_ref": ref,
                    "tickets": n,
                    "suggestions_not_applied": self._suggest(name_key(ref), names),
                }
            )
        review_paths = [
            {"route_id": r, "board_ref": b, "alight_ref": a, "status": s, "detail": d, "tickets": n}
            for (r, b, a, s, d), n in sorted(path_problems.items(), key=lambda kv: -kv[1])[:REVIEW_LIMIT]
        ]
        return {
            "total": total,
            "by_status": {s: by_status.get(s, 0) for s in STATUS_DESCRIPTIONS},
            "status_descriptions": STATUS_DESCRIPTIONS,
            "match_rate": round(by_status.get(MATCHED, 0) / total, 4) if total else None,
            "by_route_method": dict(sorted(by_method.items())),
            "aliases": {"routes": len(self.aliases.routes), "stops": len(self.aliases.stops)},
            "review": {
                "unmatched_routes": review_routes,
                "ambiguous_routes": review_ambiguous,
                "unmatched_stops": review_stops,
                "ambiguous_or_invalid_paths": review_paths,
            },
            "issues": self.log.to_list(),
        }
