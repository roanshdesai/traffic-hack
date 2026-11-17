"""Load a dataset produced by ``busplanner build`` for serving."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CrowdingConfig, PlannerConfig, Settings
from .crowding import CrowdingModel
from .gtfs import load_gtfs
from .network import Network
from .planner import Planner
from .schemas import Provenance


class DatasetError(RuntimeError):
    pass


@dataclass
class LoadedDataset:
    directory: Path
    provenance: Provenance
    settings: Settings
    network: Network
    model: CrowdingModel
    planner: Planner
    quality_report: dict[str, Any]


def load_dataset(directory: str | Path) -> LoadedDataset:
    from .pipeline import resolve_manifest_path

    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise DatasetError(f"No dataset at {directory}. Run `make data` (or `busplanner build ...`) first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("usable"):
        raise DatasetError(f"Dataset at {directory} failed GTFS validation; see quality_report.md there.")
    settings = Settings(
        crowding=CrowdingConfig(**manifest["settings"]["crowding"]),
        planner=PlannerConfig(**manifest["settings"]["planner"]),
    )
    feed, log = load_gtfs(resolve_manifest_path(manifest["gtfs_path"]))
    if log.fatal:
        raise DatasetError(f"GTFS at {manifest['gtfs_path']} can no longer be loaded; rebuild the dataset.")
    network = Network(feed, settings.planner)
    model = CrowdingModel.load(directory / "crowding_model.json")
    report = json.loads((directory / "quality_report.json").read_text(encoding="utf-8"))
    return LoadedDataset(
        directory=directory,
        provenance=Provenance(**manifest["provenance"]),
        settings=settings,
        network=network,
        model=model,
        planner=Planner(network, model, settings),
        quality_report=report,
    )
