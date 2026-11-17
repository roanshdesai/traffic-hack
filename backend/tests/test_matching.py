from __future__ import annotations

from datetime import datetime

import pytest

from busplanner import matching as m
from busplanner.tickets import Ticket


def ticket(route: str, board: str, alight: str = "", pax: int = 1) -> Ticket:
    return Ticket(2, "SIM-T", datetime(2026, 11, 2, 8, 0), route, board, alight, pax)


@pytest.mark.parametrize("ref", ["S1", "s1", "S-1", " S 1 ", "SIM_R1"])
def test_route_formatting_noise_is_normalised(matcher, ref):
    status, route_id, _method, _detail = matcher.match_route(ref)
    assert (status, route_id) == ("", "SIM_R1")


def test_unknown_route_is_unmatched_and_close_names_are_only_suggested(matcher):
    result = matcher.match_all([ticket("S11", "Sim Terminal", "Sim Market")])
    assert result.matches[0].status == m.UNMATCHED_ROUTE
    assert result.matches[0].route_id is None
    review = result.report["review"]["unmatched_routes"][0]
    assert review["route_ref"] == "S11" and review["suggestions_not_applied"] == ["S1"]


def test_route_name_shared_by_two_routes_is_ambiguous_not_picked(matcher):
    match = matcher.match_ticket(ticket("S6", "Sim Canal Road", "Sim Riverside"))
    assert match.status == m.AMBIGUOUS_ROUTE
    assert match.route_id is None and match.path == ()
    assert set(match.detail.split(", ")) == {"SIM_R6A", "SIM_R6B"}


def test_reviewed_alias_is_applied_and_labelled(matcher):
    match = matcher.match_ticket(ticket("Express-1", "Sim Terminal", "Sim College"))
    assert (match.status, match.route_id, match.route_method) == (m.MATCHED, "SIM_R1", "alias")


def test_shared_stop_names_resolve_to_the_direction_that_fits(matcher):
    out = matcher.match_ticket(ticket("S1", "Sim Terminal", "Sim Market"))
    back = matcher.match_ticket(ticket("S1", "Sim Market", "Sim Terminal"))
    assert out.path == ("SIM_S01A", "SIM_S02A", "SIM_S03A")
    assert back.path == ("SIM_S03B", "SIM_S02B", "SIM_S01B")
    assert out.offsets == (0.0, 300.0)  # scheduled seconds from boarding to each segment start


def test_stop_codes_and_ids_match_exactly(matcher):
    match = matcher.match_ticket(ticket("S1", "SIM_S02A", "sim_s04a"))
    assert match.status == m.MATCHED and match.path == ("SIM_S02A", "SIM_S03A", "SIM_S04A")


def test_misspelt_stop_is_flagged_with_a_suggestion_not_corrected(matcher):
    result = matcher.match_all([ticket("S1", "Sim Markt", "Sim Depot")])
    assert result.matches[0].status == m.UNMATCHED_BOARD_STOP
    review = result.report["review"]["unmatched_stops"][0]
    assert review["suggestions_not_applied"] == ["Sim Market"]


def test_unknown_alighting_stop(matcher):
    assert matcher.match_ticket(ticket("S1", "Sim Terminal", "Sim Nowhere Chowk")).status == m.UNMATCHED_ALIGHT_STOP


def test_stop_on_another_route_does_not_match(matcher):
    # Sim Old Bridge exists, but only on route S2.
    assert matcher.match_ticket(ticket("S1", "Sim Old Bridge", "Sim Depot")).status == m.UNMATCHED_BOARD_STOP


def test_wrong_order_is_invalid(matcher):
    assert matcher.match_ticket(ticket("S1", "SIM_S04A", "SIM_S02A")).status == m.INVALID_STOP_ORDER


def test_route_variants_with_different_stop_runs_are_ambiguous(matcher):
    # S3 has a variant that skips Sim Market, so North Gate -> Library has two possible runs.
    assert matcher.match_ticket(ticket("S3", "Sim North Gate", "Sim Library")).status == m.AMBIGUOUS_PATH
    # Both variants share the same run from Library onwards, so this one is unambiguous.
    match = matcher.match_ticket(ticket("S3", "Sim Library", "Sim Stadium"))
    assert match.status == m.MATCHED and match.path == ("SIM_S11A", "SIM_S09A", "SIM_S12A")
    # Boarding or alighting at the skipped stop pins the variant.
    assert matcher.match_ticket(ticket("S3", "Sim North Gate", "Sim Market")).status == m.MATCHED


def test_ticket_without_alighting_stop_is_board_only(matcher):
    match = matcher.match_ticket(ticket("S2", "Sim Terminal"))
    assert match.status == m.MATCHED_BOARD_ONLY and match.path == ()


def test_fixture_match_report_counts(matcher, ticket_import):
    report = matcher.match_all(ticket_import.tickets).report
    by = report["by_status"]
    assert sum(by.values()) == report["total"] == len(ticket_import.tickets)
    assert by[m.UNMATCHED_ROUTE] == 9 and by[m.AMBIGUOUS_ROUTE] == 5
    assert by[m.UNMATCHED_BOARD_STOP] == 4 and by[m.UNMATCHED_ALIGHT_STOP] == 3
    assert by[m.INVALID_STOP_ORDER] == 3 and by[m.MATCHED_BOARD_ONLY] == 8
    assert by[m.AMBIGUOUS_PATH] > 0
    assert report["by_route_method"]["alias"] == 4
    assert 0.9 < report["match_rate"] < 1.0
