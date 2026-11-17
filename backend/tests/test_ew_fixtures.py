"""The SIMULATED early-warning fixtures stay labelled, small and in sync with their generator."""

from __future__ import annotations

import csv

from busplanner.earlywarning.config import FIXTURE_DIR
from busplanner.earlywarning.synthetic import write_fixtures


def test_fixtures_match_generator(tmp_path):
    write_fixtures(tmp_path)
    for path in tmp_path.iterdir():
        assert path.read_bytes() == (FIXTURE_DIR / path.name).read_bytes(), f"{path.name} drifted: run make fixtures"
    assert {p.name for p in tmp_path.iterdir()} == {p.name for p in FIXTURE_DIR.iterdir()}


def test_every_record_is_labelled_simulated():
    for name in ("simulated_camera_counts.csv", "sites.csv", "simulated_events.csv"):
        with open(FIXTURE_DIR / name, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows and all(r["data_label"] == "SIMULATED" for r in rows), name
        assert all(r["site_id"].startswith("SIM_") for r in rows), name
    with open(FIXTURE_DIR / "sites.csv", encoding="utf-8", newline="") as handle:
        assert all(r["name"].startswith("Sim ") for r in csv.DictReader(handle))
    with open(FIXTURE_DIR / "simulated_events.csv", encoding="utf-8", newline="") as handle:
        assert all(r["description"].startswith("Simulated:") for r in csv.DictReader(handle))


def test_no_identifying_columns_in_camera_fixture():
    header = (FIXTURE_DIR / "simulated_camera_counts.csv").read_text().splitlines()[0]
    assert header == "site_id,window_start,count,confidence,data_label"
