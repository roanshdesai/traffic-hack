"""Shared test fixtures. All data used by the tests is SIMULATED (see fixtures/synthetic/README.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from busplanner.api import create_app
from busplanner.config import SYNTHETIC_FIXTURE_DIR
from busplanner.dataset import load_dataset
from busplanner.gtfs import load_gtfs
from busplanner.matching import Aliases, Matcher
from busplanner.network import Network
from busplanner.pipeline import build_dataset
from busplanner.tickets import TicketMapping, load_tickets

FX = SYNTHETIC_FIXTURE_DIR

MINI_GTFS = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,SIMULATED Mini,https://example.invalid,Asia/Kolkata\n",
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Sim A,28.60,77.20\nB,Sim B,28.61,77.21\nC,Sim C,28.62,77.22\n",
    "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR1,1,Sim A - Sim C,3\n",
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WK,1,1,1,1,1,0,0,20260101,20261231\n"
    ),
    "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id\nR1,WK,T1,Sim C,0\nR1,WK,T2,Sim C,0\n",
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,A,1\nT1,08:10:00,08:10:00,B,2\nT1,08:20:00,08:20:00,C,3\n"
        "T2,09:00:00,09:00:00,A,1\nT2,09:10:00,09:10:00,B,2\nT2,09:20:00,09:20:00,C,3\n"
    ),
}


def write_gtfs(directory: Path, overrides: dict[str, str | None] | None = None) -> Path:
    """Write the mini feed, replacing (or with ``None`` removing) individual tables."""
    directory.mkdir(parents=True, exist_ok=True)
    tables = {**MINI_GTFS, **(overrides or {})}
    for name, text in tables.items():
        if text is not None:
            (directory / name).write_text(text, encoding="utf-8")
    return directory


@pytest.fixture(scope="session")
def feed_and_log():
    return load_gtfs(FX / "gtfs")


@pytest.fixture(scope="session")
def network(feed_and_log):
    return Network(feed_and_log[0])


@pytest.fixture(scope="session")
def ticket_import():
    return load_tickets(FX / "tickets.csv", TicketMapping.load(FX / "ticket_mapping.json"))


@pytest.fixture(scope="session")
def matcher(network):
    return Matcher(network, Aliases.load(FX / "aliases.json"))


@pytest.fixture(scope="session")
def dataset_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("dataset")
    result = build_dataset(
        gtfs_path=FX / "gtfs",
        out_dir=out,
        gtfs_source="synthetic",
        tickets_path=FX / "tickets.csv",
        tickets_source="synthetic",
        mapping_path=FX / "ticket_mapping.json",
        aliases_path=FX / "aliases.json",
    )
    assert result.ok
    return out


@pytest.fixture(scope="session")
def dataset(dataset_dir):
    return load_dataset(dataset_dir)


@pytest.fixture(scope="session")
def client(dataset_dir):
    return TestClient(create_app(dataset_dir, serve_frontend=False))


def place(n: int) -> str:
    return f"place:SIM_S{n:02d}A"


# --- early warning ---------------------------------------------------------
from datetime import timedelta  # noqa: E402

from busplanner.earlywarning.config import FIXTURE_DIR as EW_FX  # noqa: E402
from busplanner.earlywarning.dataset import WarningDataset  # noqa: E402
from busplanner.earlywarning.evaluate import load_events  # noqa: E402
from busplanner.earlywarning.pipeline import build_warning_dataset  # noqa: E402
from busplanner.earlywarning.sources import load_camera_counts  # noqa: E402
from busplanner.earlywarning.synthetic import BASELINE_DAYS, FIRST_DAY  # noqa: E402

EW_BASELINE_END = FIRST_DAY + timedelta(days=BASELINE_DAYS - 1)


@pytest.fixture(scope="session")
def camera_obs():
    return load_camera_counts(EW_FX / "simulated_camera_counts.csv", EW_FX / "sites.csv", EW_FX / "mapping.json")


@pytest.fixture(scope="session")
def ew_build(tmp_path_factory, camera_obs):
    out = tmp_path_factory.mktemp("ew")
    result = build_warning_dataset(
        camera_obs, out, origin="synthetic", baseline_end=EW_BASELINE_END,
        events=load_events(EW_FX / "simulated_events.csv"),
    )  # fmt: skip
    return out, result


@pytest.fixture(scope="session")
def ew_dataset(ew_build):
    return WarningDataset(ew_build[0])


@pytest.fixture(scope="session")
def ew_client(ew_build, tmp_path_factory):
    return TestClient(create_app(tmp_path_factory.mktemp("no-planner"), serve_frontend=False,
                                 warning_dataset_dir=ew_build[0]))  # fmt: skip
