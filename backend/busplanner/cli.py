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


def _cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    if args.dataset:
        os.environ["BUSPLANNER_DATASET_DIR"] = str(args.dataset)
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

    p = sub.add_parser("serve", help="Run the API (and the built UI, if frontend/dist exists).")
    p.add_argument("--dataset", help="Dataset directory (default: data/processed/synthetic)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
