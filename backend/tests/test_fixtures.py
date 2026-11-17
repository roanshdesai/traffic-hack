"""The committed fixtures must stay small, clearly SIMULATED and in sync with their generator."""

from __future__ import annotations

import csv
import shutil
import subprocess

import pytest

from busplanner.config import REPO_ROOT
from busplanner.synthetic import write_fixtures

from .conftest import FX


def test_committed_fixtures_match_the_generator(tmp_path):
    write_fixtures(tmp_path)
    generated = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    committed = sorted(p.relative_to(FX) for p in FX.rglob("*") if p.is_file())
    assert generated == committed
    for rel in generated:
        assert (tmp_path / rel).read_bytes() == (FX / rel).read_bytes(), f"{rel} drifted: run `make fixtures`"


def test_every_fixture_record_is_labelled_simulated():
    with open(FX / "tickets.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and all(r["data_label"] == "SIMULATED" and r["ticket_no"].startswith("SIM-") for r in rows)
    with open(FX / "gtfs" / "stops.txt", encoding="utf-8", newline="") as handle:
        assert all(
            r["stop_name"].startswith("Sim ") and r["stop_id"].startswith("SIM_") for r in csv.DictReader(handle)
        )
    assert "SIMULATED" in (FX / "gtfs" / "agency.txt").read_text()
    assert "synthetic" in (FX / "README.md").read_text().lower()


def test_fixtures_stay_small():
    total = sum(p.stat().st_size for p in FX.rglob("*") if p.is_file())
    assert total < 600_000, f"fixtures are {total} bytes"


def test_no_raw_data_or_secrets_are_tracked():
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = [
        f
        for f in tracked
        if f.startswith("data/")
        or f.endswith((".zip", ".sqlite", ".db", ".parquet", ".pem", ".key"))
        or (f.rsplit("/", 1)[-1].startswith(".env") and not f.endswith(".env.example"))
        or (f.endswith((".csv", ".txt")) and not f.startswith("fixtures/synthetic/"))
    ]
    assert offenders == []
