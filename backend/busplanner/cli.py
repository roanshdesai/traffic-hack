"""Command line entry point: ``busplanner <command>`` or ``python -m busplanner.cli``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import DEFAULT_DATASET_DIR, SYNTHETIC_FIXTURE_DIR


def _cmd_build(args: argparse.Namespace) -> int:
    from .pipeline import build_dataset

    if args.tickets and not args.tickets_source:
        print("error: --tickets-source is required when --tickets is given", file=sys.stderr)
        return 2
    result = build_dataset(
        gtfs_path=args.gtfs,
        out_dir=args.out,
        gtfs_source=args.gtfs_source,
        tickets_path=args.tickets,
        tickets_source=args.tickets_source if args.tickets else "none",
        mapping_path=args.mapping,
        aliases_path=args.aliases,
        label=args.label,
    )
    _print_summary(result.report, result.out_dir)
    return 0 if result.ok else 2


def _cmd_build_synthetic(args: argparse.Namespace) -> int:
    from .pipeline import build_dataset

    fx = Path(args.fixtures)
    result = build_dataset(
        gtfs_path=fx / "gtfs",
        out_dir=args.out,
        gtfs_source="synthetic",
        tickets_path=fx / "tickets.csv",
        tickets_source="synthetic",
        mapping_path=fx / "ticket_mapping.json",
        aliases_path=fx / "aliases.json",
        label="SIMULATED demo fixtures",
    )
    _print_summary(result.report, result.out_dir)
    return 0 if result.ok else 2


def _cmd_validate_gtfs(args: argparse.Namespace) -> int:
    from .gtfs import load_gtfs

    feed, log = load_gtfs(args.gtfs)
    print(json.dumps({"usable": not log.fatal, "summary": log.summary(), "issues": log.to_list()}, indent=2))
    print(f"kept: {len(feed.stops)} stops, {len(feed.routes)} routes, {len(feed.trips)} trips", file=sys.stderr)
    return 0 if not log.fatal else 2


def _cmd_validate_tickets(args: argparse.Namespace) -> int:
    from .tickets import TicketMapping, load_tickets

    mapping = TicketMapping.load(args.mapping) if args.mapping else TicketMapping.identity()
    result = load_tickets(args.tickets, mapping)
    print(json.dumps({**result.summary(), "summary": result.log.summary(), "issues": result.log.to_list()}, indent=2))
    return 0 if not result.log.fatal else 2


def _cmd_generate_fixtures(args: argparse.Namespace) -> int:
    from .synthetic import write_fixtures

    counts = write_fixtures(Path(args.out))
    print(f"Wrote SIMULATED fixtures to {args.out}: {counts}")
    return 0


def _warning_summary(result: dict) -> None:
    report, evaluation = result["report"], result["evaluation"]
    prov = report["provenance"]
    print(f"Early-warning dataset: {prov['label']}  (origin={prov['origin']})")
    if prov["simulated"]:
        print("  ** SIMULATED DATA: not real places or crowds **")
    print(f"  baseline {prov['baseline_period']['start']}..{prov['baseline_period']['end']}, "
          f"replay {prov['replay_period']['start']}..{prov['replay_period']['end']}")  # fmt: skip
    for source in report["sources"]:
        s = source["summary"]
        counts = f"errors={s['errors']} warnings={s['warnings']} info={s['infos']}"
        print(f"  {source['name']}: rows {source.get('rows_valid')}/{source.get('rows_total')} valid, "
              f"sites {source.get('sites')}, {counts}")  # fmt: skip
    print(f"  evaluation ({evaluation['ground_truth']}):")
    for key, value in report["evaluation_summary"].items():
        print(f"    {key}: {value}")
    print(f"Report: {result['out_dir'] / 'quality_report.md'}")


def _parse_day(value: str):
    from datetime import date

    return date.fromisoformat(value)


def _cmd_warn_build_synthetic(args: argparse.Namespace) -> int:
    from datetime import timedelta

    from .earlywarning.evaluate import load_events
    from .earlywarning.pipeline import build_warning_dataset
    from .earlywarning.sources import load_camera_counts
    from .earlywarning.synthetic import BASELINE_DAYS, FIRST_DAY

    fx = Path(args.fixtures)
    obs = load_camera_counts(fx / "simulated_camera_counts.csv", fx / "sites.csv", fx / "mapping.json")
    result = build_warning_dataset(
        obs, args.out, origin="synthetic", baseline_end=FIRST_DAY + timedelta(days=BASELINE_DAYS - 1),
        events=load_events(fx / "simulated_events.csv"),
        blocked=[_BLOCKED_CAMERA, _BLOCKED_TRAFFIC],
    )  # fmt: skip
    _warning_summary(result)
    return 0


def _cmd_warn_build_camera(args: argparse.Namespace) -> int:
    from .earlywarning.config import Calendar
    from .earlywarning.evaluate import load_events
    from .earlywarning.pipeline import build_warning_dataset
    from .earlywarning.sources import load_camera_counts

    obs = load_camera_counts(args.counts, args.sites, args.mapping)
    if obs.log.fatal:
        print(json.dumps(obs.summary(), indent=2))
        return 2
    result = build_warning_dataset(
        obs, args.out, origin=args.origin, baseline_end=_parse_day(args.baseline_end), label=args.label,
        events=load_events(args.events) if args.events else None,
        calendar=Calendar(frozenset(_parse_day(h) for h in args.holiday), split_saturday=args.split_saturday),
        blocked=[_BLOCKED_TRAFFIC],
    )  # fmt: skip
    _warning_summary(result)
    return 0


def _cmd_warn_build_tickets(args: argparse.Namespace) -> int:
    from .earlywarning.config import Calendar
    from .earlywarning.pipeline import build_warning_dataset
    from .earlywarning.sources import tickets_to_observations
    from .tickets import TicketMapping, load_tickets

    mapping = TicketMapping.load(args.mapping) if args.mapping else TicketMapping.identity()
    tickets = load_tickets(args.tickets, mapping)
    if tickets.log.fatal:
        print(json.dumps(tickets.summary(), indent=2))
        return 2
    baseline_end = _parse_day(args.baseline_end)
    origin = args.origin
    if any(t.ticket_id.upper().startswith("SIM-") for t in tickets.tickets[:50]):
        origin = "synthetic"
    obs = tickets_to_observations(tickets, min_site_records=args.min_site_records, baseline_end=baseline_end)
    ticket_source = {
        **tickets.summary(),
        "name": Path(args.tickets).name + " (ticket validation)",
        "kind": "ticket_records",
        "summary": tickets.log.summary(),
        "issues": tickets.log.to_list(),
    }
    result = build_warning_dataset(
        obs, args.out, origin=origin, baseline_end=baseline_end, label=args.label,
        calendar=Calendar(frozenset(_parse_day(h) for h in args.holiday), split_saturday=not args.no_split_saturday),
        extra_sources=[ticket_source], blocked=[_BLOCKED_CAMERA, _BLOCKED_TRAFFIC],
    )  # fmt: skip
    _warning_summary(result)
    return 0


def _cmd_warn_generate_fixtures(args: argparse.Namespace) -> int:
    from .earlywarning.synthetic import write_fixtures

    print(f"Wrote SIMULATED early-warning fixtures to {args.out}: {write_fixtures(Path(args.out))}")
    return 0


from .earlywarning.pipeline import BLOCKED_CAMERA as _BLOCKED_CAMERA  # noqa: E402
from .earlywarning.pipeline import BLOCKED_TRAFFIC as _BLOCKED_TRAFFIC  # noqa: E402


def _cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    if args.dataset:
        os.environ["BUSPLANNER_DATASET_DIR"] = str(args.dataset)
    if args.warning_dataset:
        os.environ["EARLYWARNING_DATASET_DIR"] = str(args.warning_dataset)
    uvicorn.run("busplanner.api:app_factory", factory=True, host=args.host, port=args.port, reload=args.reload)
    return 0


def _print_summary(report: dict, out_dir: Path) -> None:
    prov = report["provenance"]
    print(f"Dataset: {prov['label']}  (gtfs={prov['gtfs_source']}, tickets={prov['tickets_source']})")
    if prov["simulated"]:
        print("  ** SIMULATED DATA: not real Delhi services or crowding **")
    for section in ("gtfs", "tickets"):
        s = report[section]["summary"]
        print(f"  {section:8s} errors={s['errors']} warnings={s['warnings']} info={s['infos']}")
    m = report["matching"]
    if m.get("total"):
        print(f"  matching match_rate={m['match_rate']:.1%} of {m['total']} valid tickets")
        flagged = {k: v for k, v in m["by_status"].items() if v and k != "matched"}
        print(f"           flagged={flagged}")
    c = report["crowding"]
    print(f"  crowding usable={c['usable']} supported_cells={c.get('cells_supported', 0)}")
    print(f"Report: {out_dir / 'quality_report.md'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="busplanner", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="Validate, match and aggregate GTFS + tickets into a dataset.")
    p.add_argument("--gtfs", required=True, help="GTFS directory or .zip")
    p.add_argument("--gtfs-source", required=True, choices=["synthetic", "real"],
                   help="Say what the feed is. Required so nothing is labelled real by accident.")  # fmt: skip
    p.add_argument("--tickets", help="Ticket CSV (optional)")
    p.add_argument("--tickets-source", choices=["synthetic", "real"],
                   help="Required with --tickets, for the same reason as --gtfs-source.")  # fmt: skip
    p.add_argument("--mapping", help="Ticket column mapping JSON (default: canonical column names)")
    p.add_argument("--aliases", help="Reviewed route/stop alias JSON (optional)")
    p.add_argument("--label", help="Dataset label shown in the UI")
    p.add_argument("--out", required=True, help="Output directory (keep it under data/)")
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("build-synthetic", help="Build the dataset from the committed SIMULATED fixtures.")
    p.add_argument("--fixtures", default=str(SYNTHETIC_FIXTURE_DIR))
    p.add_argument("--out", default=str(DEFAULT_DATASET_DIR))
    p.set_defaults(func=_cmd_build_synthetic)

    p = sub.add_parser("validate-gtfs", help="Validate a GTFS feed and print the issues as JSON.")
    p.add_argument("--gtfs", required=True)
    p.set_defaults(func=_cmd_validate_gtfs)

    p = sub.add_parser("validate-tickets", help="Validate a ticket file and print the issues as JSON.")
    p.add_argument("--tickets", required=True)
    p.add_argument("--mapping")
    p.set_defaults(func=_cmd_validate_tickets)

    p = sub.add_parser("generate-fixtures", help="Regenerate the SIMULATED fixtures (deterministic).")
    p.add_argument("--out", default=str(SYNTHETIC_FIXTURE_DIR))
    p.set_defaults(func=_cmd_generate_fixtures)

    from .earlywarning.config import DEFAULT_DATASET_DIR as WARN_DIR
    from .earlywarning.config import FIXTURE_DIR as WARN_FX

    p = sub.add_parser("warn-build-synthetic", help="Early warning: build from the SIMULATED camera fixtures.")
    p.add_argument("--fixtures", default=str(WARN_FX))
    p.add_argument("--out", default=str(WARN_DIR))
    p.set_defaults(func=_cmd_warn_build_synthetic)

    p = sub.add_parser("warn-build-camera", help="Early warning: build from a camera-count export.")
    p.add_argument("--counts", required=True)
    p.add_argument("--sites", required=True)
    p.add_argument("--mapping")
    p.add_argument("--origin", required=True, choices=["synthetic", "real"])
    p.add_argument("--baseline-end", required=True, help="Last day (YYYY-MM-DD) used to learn usual levels")
    p.add_argument("--events", help="Ground-truth events CSV (test data only)")
    p.add_argument("--split-saturday", action="store_true", help="Give Saturday its own usual levels")
    p.add_argument("--holiday", action="append", default=[], help="YYYY-MM-DD treated like a weekend; repeatable")
    p.add_argument("--label")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_warn_build_camera)

    p = sub.add_parser("warn-build-tickets", help="Early warning: build from ticket records (a passenger sample).")
    p.add_argument("--tickets", required=True)
    p.add_argument("--mapping")
    p.add_argument("--origin", required=True, choices=["synthetic", "real"])
    p.add_argument("--baseline-end", required=True)
    p.add_argument("--holiday", action="append", default=[])
    p.add_argument("--min-site-records", type=int, default=300)
    p.add_argument("--no-split-saturday", action="store_true", help="Pool Saturday with Sunday (default: separate)")
    p.add_argument("--label")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_warn_build_tickets)

    p = sub.add_parser("warn-generate-fixtures", help="Early warning: regenerate the SIMULATED camera fixtures.")
    p.add_argument("--out", default=str(WARN_FX))
    p.set_defaults(func=_cmd_warn_generate_fixtures)

    p = sub.add_parser("serve", help="Run the API (and the built UI, if frontend/dist exists).")
    p.add_argument("--dataset", help="Planner dataset directory (secondary; default: data/processed/synthetic)")
    p.add_argument(
        "--warning-dataset",
        help="Early-warning dataset directory (main; default: data/processed/earlywarning-synthetic)",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
