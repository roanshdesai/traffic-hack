from __future__ import annotations

import csv
import json
from datetime import date

from busplanner.dataset import load_dataset
from busplanner.pipeline import build_dataset

from .conftest import FX, place, write_gtfs


def test_build_writes_all_outputs(dataset_dir):
    names = {p.name for p in dataset_dir.iterdir()}
    assert names == {"manifest.json", "quality_report.json", "quality_report.md", "crowding_model.json",
                     "flagged_tickets.csv"}  # fmt: skip
    markdown = (dataset_dir / "quality_report.md").read_text()
    assert "SIMULATED DATA" in markdown and "Blocked / not connected" in markdown
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    assert manifest["provenance"]["simulated"] is True and manifest["usable"] is True


def test_flagged_tickets_list_every_rejected_and_unmatched_row(dataset_dir):
    with open(dataset_dir / "flagged_tickets.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = json.loads((dataset_dir / "quality_report.json").read_text())
    by = report["matching"]["by_status"]
    assert sum(r["stage"] == "validation" for r in rows) == report["tickets"]["rows_rejected"]
    assert sum(r["stage"] == "matching" for r in rows) == sum(by.values()) - by["matched"]
    assert {r["reason"] for r in rows} >= {"invalid_timestamp", "ambiguous_route", "unmatched_board_stop"}


def test_crowding_model_stores_aggregates_not_tickets(dataset_dir):
    text = (dataset_dir / "crowding_model.json").read_text()
    assert "SIM-0" not in text  # no ticket ids in the served artefact


def test_simulated_inputs_cannot_be_labelled_real(tmp_path):
    result = build_dataset(
        gtfs_path=FX / "gtfs",
        out_dir=tmp_path / "out",
        gtfs_source="real",
        tickets_path=FX / "tickets.csv",
        tickets_source="real",
        mapping_path=FX / "ticket_mapping.json",
    )
    prov = result.report["provenance"]
    assert (prov["gtfs_source"], prov["tickets_source"], prov["simulated"]) == ("synthetic", "synthetic", True)
    assert len(result.report["provenance_notes"]) == 2


def test_gtfs_only_build_plans_journeys_but_reports_insufficient_evidence(tmp_path):
    result = build_dataset(gtfs_path=FX / "gtfs", out_dir=tmp_path / "out", gtfs_source="synthetic")
    assert result.ok and result.report["provenance"]["tickets_source"] == "none"
    assert result.report["crowding"]["usable"] is False
    ds = load_dataset(tmp_path / "out")
    net = ds.network
    options = ds.planner.plan(
        net.resolve_place(place(1)), net.resolve_place(place(6)), date(2026, 11, 13), 8 * 3600
    ).options
    assert [o.status for o in options] == ["ok", "insufficient_evidence", "insufficient_evidence"]


def test_unusable_gtfs_fails_the_build_but_still_writes_a_report(tmp_path):
    gtfs = write_gtfs(tmp_path / "gtfs", {"stop_times.txt": None})
    result = build_dataset(gtfs_path=gtfs, out_dir=tmp_path / "out", gtfs_source="synthetic")
    assert not result.ok and result.report["gtfs"]["usable"] is False
    assert (tmp_path / "out" / "quality_report.md").is_file()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["usable"] is False
