from __future__ import annotations

import zipfile
from datetime import date

from busplanner.gtfs import load_gtfs, parse_gtfs_time

from .conftest import FX, MINI_GTFS, write_gtfs


def codes(log) -> dict[str, int]:
    return {i["code"]: i["count"] for i in log.to_list()}


def test_parse_gtfs_time():
    assert parse_gtfs_time("08:05:00") == 8 * 3600 + 300
    assert parse_gtfs_time("8:05:00") == 8 * 3600 + 300
    assert parse_gtfs_time("25:10:00") == 25 * 3600 + 600  # after-midnight service
    for bad in ("", "08:05", "08:61:00", "ab:cd:ef", "99:00:00"):
        assert parse_gtfs_time(bad) is None


def test_simulated_feed_loads_and_reports_its_planted_defects(feed_and_log):
    feed, log = feed_and_log
    assert not log.fatal
    found = codes(log)
    assert found["time_goes_backwards"] == 1
    assert "SIM_BAD_BACKWARDS" not in feed.trips  # dropped, not repaired
    assert found["stop_outside_region"] == 1
    assert found["duplicate_route_short_name"] == 1
    assert found["unused_stop"] == 1
    assert all("SIMULATED" in a for a in feed.agencies)


def test_missing_required_file_is_fatal(tmp_path):
    feed, log = load_gtfs(write_gtfs(tmp_path, {"stop_times.txt": None}))
    assert log.fatal and codes(log)["missing_file"] == 1
    assert not feed.trips


def test_missing_required_column_is_fatal(tmp_path):
    stops = "stop_id,stop_name,stop_lat\nA,Sim A,28.6\n"
    _feed, log = load_gtfs(write_gtfs(tmp_path, {"stops.txt": stops}))
    assert log.fatal and "missing_column" in codes(log)


def test_missing_source_is_fatal(tmp_path):
    _feed, log = load_gtfs(tmp_path / "nope")
    assert log.fatal and "source_not_found" in codes(log)


def test_trip_with_unknown_stop_is_dropped_whole(tmp_path):
    st = MINI_GTFS["stop_times.txt"].replace("T1,08:10:00,08:10:00,B,2", "T1,08:10:00,08:10:00,ZZZ,2")
    feed, log = load_gtfs(write_gtfs(tmp_path, {"stop_times.txt": st}))
    assert not log.fatal
    assert "T1" not in feed.trips and "T2" in feed.trips
    assert codes(log)["unknown_stop"] == 1 and codes(log)["trips_dropped"] == 1


def test_untimed_stop_is_not_interpolated(tmp_path):
    st = MINI_GTFS["stop_times.txt"].replace("T1,08:10:00,08:10:00,B,2", "T1,,,B,2")
    feed, log = load_gtfs(write_gtfs(tmp_path, {"stop_times.txt": st}))
    assert "T1" not in feed.trips
    assert codes(log)["missing_time"] == 1


def test_stop_times_are_ordered_by_sequence_not_file_order(tmp_path):
    lines = MINI_GTFS["stop_times.txt"].strip().split("\n")
    shuffled = "\n".join([lines[0], *reversed(lines[1:])]) + "\n"
    feed, log = load_gtfs(write_gtfs(tmp_path, {"stop_times.txt": shuffled}))
    assert not log.fatal
    assert [st.stop_id for st in feed.trips["T1"].stop_times] == ["A", "B", "C"]


def test_invalid_coordinates_drop_the_stop_and_its_trips(tmp_path):
    stops = MINI_GTFS["stops.txt"].replace("B,Sim B,28.61,77.21", "B,Sim B,,")
    feed, log = load_gtfs(write_gtfs(tmp_path, {"stops.txt": stops}))
    assert "B" not in feed.stops and codes(log)["invalid_coordinates"] == 1
    assert log.fatal and "no_usable_trips" in codes(log)  # every trip used stop B


def test_calendar_dates_exceptions(tmp_path):
    extra = "service_id,date,exception_type\nWK,20260105,2\nWK,20260104,1\n"
    feed, _log = load_gtfs(write_gtfs(tmp_path, {"calendar_dates.txt": extra}))
    assert feed.active_services(date(2026, 1, 6)) == {"WK"}  # ordinary Tuesday
    assert feed.active_services(date(2026, 1, 5)) == set()  # removed Monday
    assert feed.active_services(date(2026, 1, 4)) == {"WK"}  # added Sunday
    assert feed.active_services(date(2026, 1, 3)) == set()  # ordinary Saturday


def test_zip_source_matches_directory(tmp_path, feed_and_log):
    archive = tmp_path / "feed.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in (FX / "gtfs").iterdir():
            zf.write(path, f"nested/{path.name}")
    feed, log = load_gtfs(archive)
    assert not log.fatal
    assert len(feed.trips) == len(feed_and_log[0].trips)
    assert len(feed.stops) == len(feed_and_log[0].stops)
