from __future__ import annotations

from datetime import date, datetime

import pytest

from busplanner.schemas import BusLeg, TransferLeg

from .conftest import place

FRIDAY = date(2026, 11, 13)
SATURDAY = date(2026, 11, 14)


def plan(dataset, origin: int, destination: int, day: date = FRIDAY, clock: str = "08:00"):
    net = dataset.network
    h, mnt = (int(x) for x in clock.split(":"))
    t0 = (h * 60 + mnt) * 60
    result = dataset.planner.plan(net.resolve_place(place(origin)), net.resolve_place(place(destination)), day, t0)
    return {o.kind: o for o in result.options}, result


def all_journeys(dataset, origin: int, destination: int, day: date = FRIDAY, clock: str = "08:00"):
    net, planner = dataset.network, dataset.planner
    h, mnt = (int(x) for x in clock.split(":"))
    t0 = (h * 60 + mnt) * 60
    cands = planner.search(
        net.resolve_place(place(origin)).stop_ids, net.resolve_place(place(destination)).stop_ids, day, t0
    )
    return [planner.build_journey(c, day, t0) for c in cands]


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_always_three_options_in_fixed_order(dataset):
    options, result = plan(dataset, 1, 6)
    assert [o.kind for o in result.options] == ["fastest", "balanced", "less_crowded"]
    assert [o.label for o in result.options] == ["Fastest", "Balanced", "Less crowded"]
    assert all(o.reason.summary for o in result.options)
    assert result.candidates_considered > 3


def test_fastest_is_the_earliest_scheduled_arrival(dataset):
    options, _ = plan(dataset, 1, 6)
    journeys = all_journeys(dataset, 1, 6)
    assert options["fastest"].journey.scheduled_arrival == min(j.scheduled_arrival for j in journeys)
    assert "Earliest scheduled arrival" in options["fastest"].reason.summary


def test_demo_query_gives_three_different_journeys(dataset):
    options, _ = plan(dataset, 1, 6)
    routes = {
        k: [leg.route.short_name for leg in o.journey.legs if isinstance(leg, BusLeg)] for k, o in options.items()
    }
    assert routes == {"fastest": ["S4"], "balanced": ["S1"], "less_crowded": ["S2"]}
    # Fastest runs on a route with too few samples: it is still offered, with crowding marked unknown.
    assert options["fastest"].journey.crowding.level == "insufficient_evidence"
    assert options["fastest"].journey.crowding.relative_rank is None
    assert options["less_crowded"].journey.crowding.level == "lower"
    assert options["balanced"].journey.crowding.level == "higher"


def test_journey_structure_ordered_stops_and_segments(dataset):
    for journey in all_journeys(dataset, 10, 6):
        assert ts(journey.scheduled_departure) < ts(journey.scheduled_arrival)
        assert journey.total_min == pytest.approx(journey.initial_wait_min + journey.scheduled_travel_min)
        assert journey.transfers == sum(isinstance(leg, TransferLeg) for leg in journey.legs)
        for leg in journey.legs:
            if not isinstance(leg, BusLeg):
                continue
            assert len(leg.segments) == len(leg.stops) - 1 >= 1
            assert leg.stops[0].stop_id == leg.board_stop.stop_id
            assert leg.stops[-1].stop_id == leg.alight_stop.stop_id
            sequences = [s.sequence for s in leg.stops]
            assert sequences == sorted(sequences)
            times = [ts(s.scheduled_departure) for s in leg.stops]
            assert times == sorted(times)
            for seg, a, b in zip(leg.segments, leg.stops, leg.stops[1:], strict=False):
                assert (seg.from_stop_id, seg.to_stop_id) == (a.stop_id, b.stop_id)
                assert seg.crowding.evidence.min_tickets_required == 10


def test_insufficient_evidence_segments_carry_no_rank_or_level(dataset):
    for origin, destination in ((1, 6), (10, 6), (12, 16)):
        for journey in all_journeys(dataset, origin, destination):
            for leg in journey.legs:
                if isinstance(leg, BusLeg):
                    for seg in leg.segments:
                        c = seg.crowding
                        if c.level == "insufficient_evidence":
                            assert c.relative_rank is None and c.evidence.quality == "insufficient"
                            assert c.evidence.basis == "none"
                        else:
                            assert 0.0 <= c.relative_rank <= 1.0
                            assert c.evidence.ticket_count >= c.evidence.min_tickets_required
                            assert c.evidence.basis != "none"


def test_route_without_ticket_evidence_gives_explicit_insufficient_state(dataset):
    options, result = plan(dataset, 12, 16)
    assert options["fastest"].status == "ok" and options["fastest"].journey is not None
    for kind in ("balanced", "less_crowded"):
        option = options[kind]
        assert option.status == "insufficient_evidence"
        assert option.journey is None
        assert option.reason.summary.startswith("Insufficient evidence")
        assert any("does not mean these buses are quiet" in d for d in option.reason.details)
    assert result.candidates_considered >= 1


def test_no_journey_late_at_night(dataset):
    options, result = plan(dataset, 1, 6, clock="23:30")
    assert result.candidates_considered == 0
    assert all(o.status == "no_journey" and o.journey is None for o in options.values())


def test_crowding_rankings_only_use_journeys_with_enough_evidence(dataset):
    cfg = dataset.settings.planner
    for origin, destination, clock in ((1, 6, "08:00"), (1, 12, "17:00"), (10, 6, "08:00"), (3, 5, "12:00")):
        options, _ = plan(dataset, origin, destination, clock=clock)
        journeys = all_journeys(dataset, origin, destination, clock=clock)
        fastest = options["fastest"].journey
        limit = fastest.total_min + max(cfg.slack_min, cfg.slack_ratio * fastest.total_min)
        eligible = [j for j in journeys if j.total_min <= limit and j.crowding.level != "insufficient_evidence"]
        assert eligible, "fixture should provide evidence for these pairs"
        for kind in ("balanced", "less_crowded"):
            picked = options[kind].journey
            assert picked.crowding.coverage >= cfg.min_evidence_coverage
            assert picked.total_min <= limit
        calm = options["less_crowded"].journey
        assert calm.crowding.relative_rank == min(j.crowding.relative_rank for j in eligible)
        cost = dataset.planner.balanced_cost(options["balanced"].journey)["cost"]
        assert cost == min(dataset.planner.balanced_cost(j)["cost"] for j in eligible)


def test_same_journey_as_is_set_when_options_coincide(dataset):
    options, _ = plan(dataset, 1, 6, day=SATURDAY, clock="13:00")
    assert options["balanced"].journey.journey_id == options["fastest"].journey.journey_id
    assert options["balanced"].same_journey_as == "fastest"
    assert options["fastest"].same_journey_as is None


def test_transfers_respect_minimum_connection_time(dataset):
    cfg = dataset.settings.planner
    journeys = [j for j in all_journeys(dataset, 10, 6) if j.transfers == 1]
    assert journeys
    for journey in journeys:
        first, change, second = journey.legs
        assert isinstance(change, TransferLeg)
        gap = (ts(second.scheduled_departure) - ts(first.scheduled_arrival)).total_seconds() / 60
        assert cfg.min_transfer_min <= gap <= cfg.max_transfer_wait_min
        assert change.scheduled_min == pytest.approx(gap)
        assert first.route.route_id != second.route.route_id
        assert change.walk_m <= cfg.place_radius_m


def test_weekend_uses_weekend_services(dataset):
    weekday = all_journeys(dataset, 1, 6, day=FRIDAY)
    weekend = all_journeys(dataset, 1, 6, day=SATURDAY)
    assert all("_WK_" in leg.trip_id for j in weekday for leg in j.legs if isinstance(leg, BusLeg))
    assert all("_WE_" in leg.trip_id for j in weekend for leg in j.legs if isinstance(leg, BusLeg))


def test_search_only_returns_departures_inside_the_window(dataset):
    window = dataset.settings.planner.search_window_min
    for journey in all_journeys(dataset, 1, 6):
        assert 0 <= journey.initial_wait_min <= window


def test_single_stop_reference_restricts_boarding_to_that_stop(dataset):
    net = dataset.network
    origin = net.resolve_place("SIM_S01A")
    assert origin.stop_ids == ["SIM_S01A"]
    assert net.resolve_place("SIM_S99A") is None  # unused stop is not a valid origin
    assert net.resolve_place("nope") is None
