"""Early warning: people-count import paths. All data here is SIMULATED."""

from __future__ import annotations

from datetime import date, datetime

from busplanner.earlywarning.config import CAMERA_SOURCE
from busplanner.earlywarning.sources import load_camera_counts, tickets_to_observations
from busplanner.tickets import Ticket, TicketImport

SITES = (
    "site_id,name,kind,lat,lon,alert_threshold,max_plausible\n"
    "S1,Sim A,bus_stop,28.6,77.2,100,500\nS2,Sim B,terminal,,,,\n"
)


def codes(log) -> dict[str, int]:
    return {i["code"]: i["count"] for i in log.to_list()}


def build(tmp_path, counts: str, sites: str = SITES):
    (tmp_path / "sites.csv").write_text(sites)
    (tmp_path / "counts.csv").write_text(counts)
    return load_camera_counts(tmp_path / "counts.csv", tmp_path / "sites.csv")


def test_fixture_counts_reject_exactly_the_planted_rows(camera_obs):
    found = codes(camera_obs.log)
    assert found["duplicate_window"] == 1
    assert found["misaligned_window"] == 1
    assert found["invalid_count"] == 2  # a negative count and a non-number
    assert found["outside_service_hours"] == 1
    assert found["unknown_site"] == 1
    assert found["invalid_timestamp"] == 1
    assert found["implausible_count"] == 1
    assert found["low_confidence"] > 0
    assert camera_obs.rows_total - camera_obs.rows_valid == 8
    # The rejected 99,999 reading leaves a gap: it is not replaced by a guess.
    assert camera_obs.value("SIM_SITE_01", date(2026, 11, 6), (12 * 60 - 6 * 60) // 15) is None


def test_sensor_outage_is_no_data_not_zero(camera_obs):
    slot = (11 * 60 - 6 * 60) // 15
    assert camera_obs.value("SIM_SITE_05", date(2026, 11, 19), slot) is None
    assert camera_obs.value("SIM_SITE_05", date(2026, 11, 18), slot) is not None


def test_low_confidence_windows_are_excluded(camera_obs):
    slot = (21 * 60 + 30 - 6 * 60) // 15
    assert camera_obs.counts["SIM_SITE_03"][(date(2026, 11, 17), slot)] is None


def test_sites_file_parsing(tmp_path):
    obs = build(tmp_path, "site_id,window_start,count\nS1,2026-11-02 08:00,10\n")
    assert obs.sites["S1"].alert_threshold == 100 and obs.sites["S1"].lat == 28.6
    assert obs.sites["S2"].alert_threshold is None and obs.sites["S2"].lat is None
    assert obs.sites["S1"].unit == "people counted" and obs.sites["S1"].coverage == "full_count"


def test_identifying_columns_are_ignored_and_reported(tmp_path):
    obs = build(tmp_path, "site_id,window_start,count,face_crop_path\nS1,2026-11-02 08:00,10,/img/1.jpg\n")
    assert obs.rows_valid == 1
    assert "identifying_columns_ignored" in codes(obs.log)
    assert "/img/1.jpg" not in str(obs.log.to_list())


def test_missing_required_column_is_fatal(tmp_path):
    obs = build(tmp_path, "site_id,window_start\nS1,2026-11-02 08:00\n")
    assert obs.log.fatal and "missing_column" in codes(obs.log)


def test_window_index_and_gap_report(tmp_path):
    obs = build(tmp_path, "site_id,window_start,count\nS1,2026-11-02 08:00,10\nS1,2026-11-02 08:15,12\n")
    assert obs.spec == CAMERA_SOURCE
    assert obs.value("S1", date(2026, 11, 2), 8) == 10  # (08:00 - 06:00) / 15
    assert obs.value("S1", date(2026, 11, 2), 0) is None
    assert codes(obs.log)["missing_windows"] == obs.slots_per_day - 2
    assert codes(obs.log)["site_without_data"] == 1  # S2


def ticket(moment: str, stop: str, pax: int = 1) -> Ticket:
    return Ticket(2, "T", datetime.fromisoformat(moment), "8UP", stop, "Sim Z", pax)


def test_tickets_aggregate_into_hourly_boardings_per_stop():
    imp = TicketImport(source="tickets.csv")
    imp.tickets = [ticket("2026-10-01T08:10", "Sim A"), ticket("2026-10-01T08:50", "sim  a", 2),
                   ticket("2026-10-01T09:05", "Sim A"), ticket("2026-10-01T03:00", "Sim A")]  # fmt: skip
    obs = tickets_to_observations(imp, min_site_records=1)
    assert list(obs.sites) == ["stop:SIM_A"]
    assert obs.sites["stop:SIM_A"].unit == "e-ticket boardings"
    assert obs.sites["stop:SIM_A"].coverage == "sample"
    day = date(2026, 10, 1)
    assert obs.value("stop:SIM_A", day, 3) == 3  # 08:00 window (service starts 05:00), passengers summed
    assert obs.value("stop:SIM_A", day, 4) == 1
    assert obs.value("stop:SIM_A", day, 10) == 0  # a sample with no records means zero, not missing
    assert codes(obs.log)["outside_service_hours"] == 1
    assert codes(obs.log)["stop_name_variants_merged"] == 1


def test_thin_ticket_sites_are_left_out():
    imp = TicketImport(source="tickets.csv")
    imp.tickets = [ticket("2026-10-01T08:10", "Sim A")] * 5 + [ticket("2026-10-01T08:10", "Sim B")]
    obs = tickets_to_observations(imp, min_site_records=3)
    assert list(obs.sites) == ["stop:SIM_A"]
    assert codes(obs.log)["site_below_minimum_records"] == 1
