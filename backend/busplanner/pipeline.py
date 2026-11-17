"""Build pipeline: GTFS + tickets -> validated, matched, aggregated dataset.

Output directory (always under the git-ignored ``data/``):

* ``manifest.json``        provenance, source paths, settings, counts
* ``quality_report.json``  machine-readable data-quality report (served by the API)
* ``quality_report.md``    the same report for humans
* ``crowding_model.json``  aggregated segment cells (no individual tickets)
* ``flagged_tickets.csv``  rejected / unmatched / ambiguous ticket rows with the reason
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import LOCAL_UTC_OFFSET, REPO_ROOT, Settings
from .crowding import FALLBACKS, CrowdingModel, build_crowding_model
from .gtfs import load_gtfs
from .matching import MATCHED, Aliases, Matcher
from .network import Network
from .tickets import TicketImport, TicketMapping, load_tickets

IST = timezone(timedelta(hours=5, minutes=30))
SIMULATED_MARKER = "SIMULATED"

BLOCKED_REAL_GTFS = (
    "Real Delhi static GTFS is not imported. The prototype environment has no copy of the feed, the "
    "publisher's open transit data portal was not reachable from it, and no account was registered. "
    "To unblock: place the feed (zip or folder) under data/raw/ and run `busplanner build --gtfs-source real`."
)
BLOCKED_REAL_TICKETS = (
    "Real ticket data is not part of this dataset. The October 2026 hackathon ticket file validates with "
    "config/ticket_mappings/ondc_2026_10.json, but it cannot be matched without the real static GTFS. "
    "To unblock: get the GTFS, then run `busplanner build --tickets-source real` (see docs/HACKATHON.md)."
)
NOT_CONNECTED_TRAFFIC = (
    "Google road traffic is not connected (needs an API key and billing, neither requested). It is kept "
    "separate from passenger crowding by design."
)


@dataclass
class BuildResult:
    ok: bool
    out_dir: Path
    report: dict[str, Any]


def _now() -> str:
    return datetime.now(IST).replace(microsecond=0, tzinfo=None).isoformat() + LOCAL_UTC_OFFSET


def _portable(path: Path) -> str:
    """Store paths relative to the repo when possible so a checkout can move."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def resolve_manifest_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def build_dataset(
    gtfs_path: str | Path,
    out_dir: str | Path,
    gtfs_source: str,
    tickets_path: str | Path | None = None,
    tickets_source: str = "none",
    mapping_path: str | Path | None = None,
    aliases_path: str | Path | None = None,
    label: str | None = None,
    settings: Settings | None = None,
) -> BuildResult:
    settings = settings or Settings()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    feed, gtfs_log = load_gtfs(gtfs_path)
    if any(SIMULATED_MARKER in a.upper() for a in feed.agencies) and gtfs_source != "synthetic":
        notes.append("GTFS agency name is marked SIMULATED: gtfs_source forced to 'synthetic'.")
        gtfs_source = "synthetic"

    tickets: TicketImport | None = None
    if tickets_path is not None:
        mapping = TicketMapping.load(mapping_path) if mapping_path else TicketMapping.identity()
        tickets = load_tickets(tickets_path, mapping)
        if tickets_source == "none":
            raise ValueError("tickets_source must be 'synthetic' or 'real' when a ticket file is given")
        if tickets_source != "synthetic" and any(t.ticket_id.upper().startswith("SIM-") for t in tickets.tickets[:50]):
            notes.append("Ticket ids are marked SIM-: tickets_source forced to 'synthetic'.")
            tickets_source = "synthetic"
    else:
        tickets_source = "none"

    simulated = "synthetic" in (gtfs_source, tickets_source)
    provenance = {
        "gtfs_source": gtfs_source,
        "tickets_source": tickets_source,
        "simulated": simulated,
        "label": label or ("SIMULATED demo fixtures" if simulated else "Imported dataset"),
        "built_at": _now(),
    }

    report: dict[str, Any] = {
        "generated_at": provenance["built_at"],
        "provenance": provenance,
        "provenance_notes": notes,
        "gtfs": {
            "source": _portable(Path(gtfs_path)),
            "usable": not gtfs_log.fatal,
            "file_rows": feed.file_rows,
            "kept": {
                "stops": len(feed.stops),
                "routes": len(feed.routes),
                "trips": len(feed.trips),
                "services": len(feed.services),
                "stop_times": sum(len(t.stop_times) for t in feed.trips.values()),
            },
            "summary": gtfs_log.summary(),
            "issues": gtfs_log.to_list(),
        },
    }
    lo, hi = feed.date_range()
    report["gtfs"]["service_date_range"] = {
        "start": lo.isoformat() if lo else None,
        "end": hi.isoformat() if hi else None,
    }

    model = CrowdingModel.empty(settings.crowding)
    network: Network | None = None
    if not gtfs_log.fatal:
        network = Network(feed, settings.planner)
        report["gtfs"]["kept"]["patterns"] = len(network.patterns)
        report["gtfs"]["kept"]["places"] = len(network.places)

    if tickets is None:
        report["tickets"] = {
            "source": None,
            "summary": {"errors": 0, "warnings": 0, "infos": 0},
            "issues": [],
            "note": "No ticket file was given; every segment reports insufficient evidence.",
        }
        report["matching"] = {"total": 0, "by_status": {}, "match_rate": None, "review": {}}
    else:
        report["tickets"] = {
            **tickets.summary(),
            "source": _portable(Path(tickets.source)),
            "mapping": _portable(Path(mapping_path)) if mapping_path else "(canonical column names)",
            "summary": tickets.log.summary(),
            "issues": tickets.log.to_list(),
        }
        if network is not None and not tickets.log.fatal:
            matcher = Matcher(network, Aliases.load(aliases_path))
            result = matcher.match_all(tickets.tickets)
            report["matching"] = result.report
            model = build_crowding_model(network, result.matches, tickets.service_dates(), settings.crowding)
            _write_flagged(out / "flagged_tickets.csv", tickets, result.matches)
        else:
            report["matching"] = {"total": 0, "by_status": {}, "match_rate": None, "review": {}}
            _write_flagged(out / "flagged_tickets.csv", tickets, [])

    report["crowding"] = {
        **model.stats,
        "usable": model.usable,
        "thresholds": {
            "min_tickets": settings.crowding.min_tickets,
            "min_service_days": settings.crowding.min_service_days,
            "strong_tickets": settings.crowding.strong_tickets,
            "strong_service_days": settings.crowding.strong_service_days,
            "min_reference_cells": settings.crowding.min_reference_cells,
        },
        "fallbacks": list(FALLBACKS),
        "caveat": "Ticket samples are not verified occupancy. Levels are relative ranks within this dataset.",
    }
    blocked = []
    if gtfs_source != "real":
        blocked.append(BLOCKED_REAL_GTFS)
    if tickets_source != "real":
        blocked.append(BLOCKED_REAL_TICKETS)
    blocked.append(NOT_CONNECTED_TRAFFIC)
    report["blocked"] = blocked

    manifest = {
        "provenance": provenance,
        "gtfs_path": _portable(Path(gtfs_path)),
        "tickets_path": _portable(Path(tickets_path)) if tickets_path else None,
        "settings": settings.to_dict(),
        "usable": not gtfs_log.fatal,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "quality_report.md").write_text(render_markdown(report), encoding="utf-8")
    model.save(out / "crowding_model.json")
    return BuildResult(ok=not gtfs_log.fatal, out_dir=out, report=report)


def _write_flagged(path: Path, tickets: TicketImport, matches: list) -> None:
    """Rows a human should look at. Lives in data/ and must never be committed."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row", "stage", "reason", "route_ref", "board_ref", "alight_ref", "detail"])
        for rej in tickets.rejected:
            writer.writerow([rej.row, "validation", rej.code, "", "", "", json.dumps(rej.raw, ensure_ascii=False)])
        for m in matches:
            if m.status != MATCHED:
                t = m.ticket
                writer.writerow([t.row, "matching", m.status, t.route_ref, t.board_ref, t.alight_ref, m.detail])


def render_markdown(report: dict[str, Any]) -> str:
    prov = report["provenance"]
    lines = ["# Data-quality report", ""]
    if prov["simulated"]:
        lines += ["> **SIMULATED DATA.** This report describes synthetic fixtures, not real Delhi services.", ""]
    lines += [
        f"* Generated: {report['generated_at']}",
        f"* Dataset: {prov['label']}",
        f"* GTFS source: `{prov['gtfs_source']}`, tickets source: `{prov['tickets_source']}`",
        "",
    ]
    for note in report.get("provenance_notes", []):
        lines.append(f"* Note: {note}")

    def issues_table(section: dict[str, Any]) -> list[str]:
        out = [
            f"Errors: {section['summary']['errors']}, warnings: {section['summary']['warnings']}, "
            f"info: {section['summary']['infos']}",
            "",
        ]
        if section["issues"]:
            out += ["| Severity | File | Code | Count | Message |", "| --- | --- | --- | ---: | --- |"]
            out += [
                f"| {i['severity']} | {i['file']} | `{i['code']}` | {i['count']} | {i['message']} |"
                for i in section["issues"]
            ]
            out.append("")
        return out

    gtfs = report["gtfs"]
    lines += ["## GTFS (scheduled timetable)", "", f"Usable: **{'yes' if gtfs['usable'] else 'NO'}**", ""]
    lines.append("Kept after validation: " + ", ".join(f"{v} {k}" for k, v in gtfs["kept"].items()))
    rng = gtfs["service_date_range"]
    lines += [f"Service dates: {rng['start']} to {rng['end']}", ""]
    lines += issues_table(gtfs)

    tickets = report["tickets"]
    lines += ["## Ticket samples", ""]
    if tickets.get("source") is None:
        lines += [tickets["note"], ""]
    else:
        lines += [
            f"Rows: {tickets['rows_total']} total, {tickets['rows_valid']} valid, "
            f"{tickets['rows_rejected']} rejected, {tickets['rows_without_alight_stop']} without alighting stop",
            f"Service days sampled: {tickets['service_days']} "
            f"({tickets['first_service_date']} to {tickets['last_service_date']})",
            "",
        ]
        lines += issues_table(tickets)

    matching = report["matching"]
    lines += ["## Route and stop matching", ""]
    if matching.get("total"):
        lines += [f"Match rate: **{matching['match_rate']:.1%}** of {matching['total']} valid tickets", ""]
        lines += ["| Status | Tickets | Meaning |", "| --- | ---: | --- |"]
        lines += [f"| `{s}` | {n} | {matching['status_descriptions'][s]} |" for s, n in matching["by_status"].items()]
        lines.append("")
        review = matching["review"]
        for title, key in (
            ("Unmatched route references", "unmatched_routes"),
            ("Ambiguous route references", "ambiguous_routes"),
            ("Unmatched stop references", "unmatched_stops"),
            ("Ambiguous or invalid stop runs", "ambiguous_or_invalid_paths"),
        ):
            if review.get(key):
                lines += [f"### {title} (for human review; nothing here was auto-corrected)", ""]
                lines += [f"* `{json.dumps(item, ensure_ascii=False)}`" for item in review[key]]
                lines.append("")
    else:
        lines += ["No tickets were matched.", ""]

    crowding = report["crowding"]
    lines += ["## Relative crowding model", "", f"Usable: **{'yes' if crowding['usable'] else 'NO'}**", ""]
    lines += [f"* {k}: {v}" for k, v in crowding.items() if k not in ("fallbacks", "thresholds", "caveat", "usable")]
    lines += ["", "Thresholds: " + ", ".join(f"{k}={v}" for k, v in crowding["thresholds"].items()), ""]
    lines += ["Fallback order:", ""]
    lines += [f"{n}. `{f['basis']}` (max grade {f['quality_cap']}): {f['description']}"
              for n, f in enumerate(crowding["fallbacks"], 1)]  # fmt: skip
    lines += ["", f"_{crowding['caveat']}_", "", "## Blocked / not connected", ""]
    lines += [f"* {b}" for b in report["blocked"]]
    return "\n".join(lines) + os.linesep
