from __future__ import annotations

from datetime import date, datetime

import pytest

from busplanner import matching as m
from busplanner.config import CrowdingConfig
from busplanner.crowding import CrowdingModel, build_crowding_model
from busplanner.tickets import Ticket

SEG = ("R", "A", "B")
CFG = CrowdingConfig(
    min_tickets=10, min_service_days=2, strong_tickets=30, strong_service_days=4, min_reference_cells=3
)


def make_model(l1=None, l2=None, l3=None, cfg=CFG) -> CrowdingModel:
    # Reference distribution: three supported cells with index 0.1, 0.5 and 0.9.
    reference = {
        ("X", "a", "b", "weekday", "midday"): (10, 10, 2, 100),
        ("Y", "a", "b", "weekday", "midday"): (10, 50, 2, 100),
        ("Z", "a", "b", "weekday", "midday"): (10, 90, 2, 100),
    }
    return CrowdingModel(cfg, {**reference, **(l1 or {})}, l2 or {}, l3 or {})


def test_exact_cell_with_strong_support_is_high_quality():
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (40, 95, 5, 100)})
    est = model.lookup(*SEG, "weekday", "am_peak")
    assert (est.level, est.quality, est.basis) == ("higher", "high", "segment_period_daytype")
    assert (est.ticket_count, est.rider_count, est.service_days, est.scheduled_trips) == (40, 95, 5, 100)


def test_exact_cell_with_adequate_support_is_medium_quality():
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (12, 5, 2, 100)})
    est = model.lookup(*SEG, "weekday", "am_peak")
    assert (est.level, est.quality) == ("lower", "medium")


def test_fallback_chain_degrades_basis_and_quality():
    thin = {(*SEG, "weekday", "am_peak"): (4, 4, 2, 100)}
    pooled_period = {(*SEG, "am_peak"): (40, 60, 6, 140)}
    pooled_all = {SEG: (90, 120, 10, 600)}
    est = make_model(l1=thin, l2=pooled_period, l3=pooled_all).lookup(*SEG, "weekday", "am_peak")
    assert (est.basis, est.quality, est.ticket_count) == ("segment_period", "medium", 40)

    est = make_model(l1=thin, l2={(*SEG, "am_peak"): (6, 6, 2, 140)}, l3=pooled_all).lookup(*SEG, "weekday", "am_peak")
    assert (est.basis, est.quality, est.ticket_count) == ("segment_all_day", "low", 90)


def test_too_few_samples_everywhere_is_insufficient_and_keeps_the_support_count():
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (3, 3, 1, 100)}, l3={SEG: (7, 7, 3, 600)})
    est = model.lookup(*SEG, "weekday", "am_peak")
    assert (est.level, est.quality, est.basis) == ("insufficient_evidence", "insufficient", "none")
    assert est.relative_rank is None and est.ticket_count == 7


def test_no_samples_is_insufficient_never_lower():
    est = make_model().lookup("R", "nowhere", "else", "weekday", "am_peak")
    assert est.level == "insufficient_evidence" and est.ticket_count == 0 and est.relative_rank is None


def test_one_busy_day_is_not_enough_service_days():
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (50, 50, 1, 100)})
    assert model.lookup(*SEG, "weekday", "am_peak").level == "insufficient_evidence"


def test_samples_without_scheduled_trips_are_not_usable():
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (50, 50, 5, 0)})
    assert model.lookup(*SEG, "weekday", "am_peak").level == "insufficient_evidence"


def test_small_reference_distribution_disables_all_levels():
    cfg = CrowdingConfig(min_reference_cells=50)
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (40, 95, 5, 100)}, cfg=cfg)
    assert not model.usable
    assert model.lookup(*SEG, "weekday", "am_peak").level == "insufficient_evidence"


def test_rank_is_monotonic_and_bounded():
    model = make_model()
    ranks = [model.rank(x) for x in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 5.0)]
    assert ranks == sorted(ranks)
    assert ranks[0] == 0.0 and ranks[-1] == 1.0
    assert [model.level_for_rank(r) for r in (0.0, 0.5, 1.0)] == ["lower", "typical", "higher"]


def test_save_and_load_round_trip(tmp_path):
    model = make_model(l1={(*SEG, "weekday", "am_peak"): (40, 95, 5, 100)}, l3={SEG: (90, 120, 10, 600)})
    model.save(tmp_path / "model.json")
    loaded = CrowdingModel.load(tmp_path / "model.json")
    assert loaded.l1 == model.l1 and loaded.l3 == model.l3 and loaded.reference == model.reference
    assert loaded.lookup(*SEG, "weekday", "am_peak") == model.lookup(*SEG, "weekday", "am_peak")


@pytest.fixture(scope="module")
def built(network, matcher, ticket_import):
    matches = matcher.match_all(ticket_import.tickets).matches
    return build_crowding_model(network, matches, ticket_import.service_dates())


def test_denominator_is_scheduled_trips_over_sampled_days(built):
    # S1 direction 0 leaves Sim Terminal every 12 min from 06:00: 20 departures fall in 07:00-10:59,
    # and the sample covers 10 weekdays -> 200 scheduled trips.
    cell = built.l1[("SIM_R1", "SIM_S01A", "SIM_S02A", "weekday", "am_peak")]
    assert cell[3] == 200
    assert cell[2] == 10  # samples seen on all ten weekdays
    assert cell[1] >= cell[0] >= CFG.min_tickets  # riders >= tickets


def test_built_model_keeps_thin_and_unsampled_routes_insufficient(built):
    assert built.usable
    s4 = built.lookup("SIM_R4", "SIM_S01A", "SIM_S13A", "weekday", "am_peak")
    assert s4.level == "insufficient_evidence" and 0 < s4.ticket_count < 10
    s5 = built.lookup("SIM_R5", "SIM_S12A", "SIM_S15A", "weekday", "am_peak")
    assert s5.level == "insufficient_evidence" and s5.ticket_count == 0


def test_built_model_flags_samples_outside_the_schedule(built):
    assert built.stats["cells_outside_schedule"] == 2
    assert built.stats["ticket_samples_outside_schedule"] == 4
    weekend = built.lookup("SIM_R6A", "SIM_S02A", "SIM_S13A", "weekend", "midday")
    assert weekend.level == "insufficient_evidence"


def test_rider_is_bucketed_when_they_reach_the_segment_not_when_they_board(network):
    # Boarding at 10:55, the rider is on the third S1 segment 10 scheduled minutes later, in "midday".
    path = ("SIM_S01A", "SIM_S02A", "SIM_S03A", "SIM_S04A")
    ticket = Ticket(2, "SIM-T", datetime(2026, 11, 2, 10, 55), "S1", "x", "y", 2)
    match = m.TicketMatch(ticket, m.MATCHED, "SIM_R1", "route_short_name", path, (0.0, 300.0, 600.0))
    model = build_crowding_model(network, [match], [date(2026, 11, 2)])
    assert ("SIM_R1", "SIM_S01A", "SIM_S02A", "weekday", "am_peak") in model.l1
    assert ("SIM_R1", "SIM_S02A", "SIM_S03A", "weekday", "midday") in model.l1
    assert model.l1[("SIM_R1", "SIM_S03A", "SIM_S04A", "weekday", "midday")][:2] == (1, 2)


def test_unmatched_tickets_never_reach_the_model(network):
    ticket = Ticket(2, "SIM-T", datetime(2026, 11, 2, 8, 0), "S9", "x", "y", 1)
    for status in (m.UNMATCHED_ROUTE, m.AMBIGUOUS_ROUTE, m.AMBIGUOUS_PATH, m.MATCHED_BOARD_ONLY):
        model = build_crowding_model(network, [m.TicketMatch(ticket, status)], [date(2026, 11, 2)])
        assert not model.l1 and model.stats["tickets_used"] == 0
