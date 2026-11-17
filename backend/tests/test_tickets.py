from __future__ import annotations

from datetime import date

import pytest

from busplanner.tickets import TicketMapping, load_tickets


def codes(log) -> dict[str, int]:
    return {i["code"]: i["count"] for i in log.to_list()}


def write(tmp_path, text: str):
    path = tmp_path / "tickets.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_simulated_tickets_reject_exactly_the_planted_bad_rows(ticket_import):
    found = codes(ticket_import.log)
    assert found == {
        "duplicate_ticket_id": 3,
        "implausible_passenger_count": 1,
        "invalid_passenger_count": 3,
        "invalid_timestamp": 2,
        "missing_board_stop": 2,
        "missing_route": 2,
        "same_board_alight": 2,
        "missing_alight_stop": 8,
    }
    assert len(ticket_import.rejected) == 15
    assert ticket_import.rows_total == len(ticket_import.tickets) + len(ticket_import.rejected)
    assert len(ticket_import.service_dates()) == 14


def test_canonical_columns_need_no_mapping(tmp_path):
    path = write(tmp_path, "issued_at,route,board_stop,alight_stop\n2026-11-02 08:00:00,S1,Sim A,Sim B\n")
    result = load_tickets(path)
    assert len(result.tickets) == 1
    assert result.tickets[0].passengers == 1  # documented default when no passenger column exists
    assert "no_passenger_column" in codes(result.log)


def test_unmapped_required_column_is_fatal(tmp_path):
    path = write(tmp_path, "when,route_no,from_stop\n2026-11-02 08:00:00,S1,Sim A\n")
    mapping = TicketMapping(columns={"issued_at": "issue_time", "route": "route_no", "board_stop": "from_stop"})
    result = load_tickets(path, mapping)
    assert result.log.fatal and not result.tickets
    assert "missing_column" in codes(result.log)


def test_file_without_alight_column_warns_and_keeps_boardings(tmp_path):
    path = write(tmp_path, "issued_at,route,board_stop\n2026-11-02 08:00:00,S1,Sim A\n")
    result = load_tickets(path)
    assert len(result.tickets) == 1 and result.tickets[0].alight_ref == ""
    assert "no_alight_column" in codes(result.log)


@pytest.mark.parametrize("pax", ["0", "-2", "1.5", "", "many"])
def test_bad_passenger_count_is_rejected_not_defaulted(tmp_path, pax):
    path = write(
        tmp_path, f"issued_at,route,board_stop,alight_stop,passengers\n2026-11-02 08:00:00,S1,Sim A,Sim B,{pax}\n"
    )
    result = load_tickets(path)
    assert not result.tickets
    assert result.rejected[0].code == "invalid_passenger_count"


def test_after_midnight_ticket_belongs_to_previous_service_day(tmp_path):
    path = write(
        tmp_path,
        "issued_at,route,board_stop,alight_stop\n"
        "2026-11-03 00:40:00,S1,Sim A,Sim B\n2026-11-03 04:00:00,S1,Sim A,Sim B\n",
    )
    first, second = load_tickets(path).tickets
    assert first.service_date == date(2026, 11, 2)
    assert second.service_date == date(2026, 11, 3)


def test_mapping_file_rejects_unknown_canonical_fields(tmp_path):
    bad = tmp_path / "mapping.json"
    bad.write_text('{"columns": {"issued_at": "t", "route": "r", "board_stop": "b", "seat_count": "s"}}')
    with pytest.raises(ValueError, match="unknown canonical field"):
        TicketMapping.load(bad)
