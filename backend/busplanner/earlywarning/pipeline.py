"""Build an early-warning dataset: observations -> baselines -> replay -> evaluation.

Output directory (keep it under the git-ignored ``data/``):

* ``manifest.json``       provenance, source spec, calendar, settings
* ``sites.json``          site list
* ``baselines.json``      usual levels learned from the baseline period
* ``replay.json``         observations for the replay period only
* ``episodes.json``       merged alert episodes in the replay period
* ``events.json``         simulated ground-truth events (synthetic only)
* ``evaluation.json``     backtest metrics or descriptive statistics
* ``quality_report.json`` / ``quality_report.md``
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..pipeline import IST
from .config import Calendar, WarningConfig
from .evaluate import Event, describe_without_truth, evaluate_against_events, replay
from .model import Baselines, Detector
from .sources import ObservationSet

BLOCKED_CAMERA = (
    "No real camera counts are connected. Camera input is exercised on SIMULATED counts only. A real feed needs "
    "an agreement with the camera owner, aggregated counts only (no images or identities), and the owner's go-ahead."
)
BLOCKED_TRAFFIC = (
    "Google road traffic is not connected (needs an API key, billing and the owner's go-ahead). If added it stays "
    "a separate context signal."
)
CAVEAT_SYNTHETIC = (
    "Measured on SIMULATED data against SIMULATED events. These numbers show the method behaves as designed; "
    "they say nothing about accuracy on real crowds."
)
CAVEAT_REAL = (
    "No ground truth is available for this data, so accuracy is unknown. These are descriptive statistics only."
)


def _now() -> str:
    return datetime.now(IST).replace(microsecond=0, tzinfo=None).isoformat() + "+05:30"


def _looks_simulated(obs: ObservationSet) -> bool:
    ids = list(obs.sites)
    return bool(ids) and all(s.startswith("SIM_") or obs.sites[s].name.startswith("Sim ") for s in ids)


def build_warning_dataset(
    obs: ObservationSet,
    out_dir: str | Path,
    origin: str,
    baseline_end: date,
    label: str | None = None,
    events: list[Event] | None = None,
    calendar: Calendar | None = None,
    cfg: WarningConfig | None = None,
    extra_sources: list[dict[str, Any]] | None = None,
    blocked: list[str] | None = None,
) -> dict[str, Any]:
    cfg = cfg or WarningConfig()
    calendar = calendar or Calendar()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    if origin != "synthetic" and _looks_simulated(obs):
        notes.append("Every site is marked SIM_/Sim: origin forced to 'synthetic'.")
        origin = "synthetic"
    simulated = origin == "synthetic"

    days = sorted(obs.days)
    baseline_days = [d for d in days if d <= baseline_end]
    replay_days = [d for d in days if d > baseline_end]
    if not baseline_days or not replay_days:
        raise ValueError(
            f"baseline_end {baseline_end} must split the data ({days[0] if days else '-'} to "
            f"{days[-1] if days else '-'}) into a baseline period and a replay period"
        )

    baselines = Baselines.build(obs, baseline_days, calendar, cfg)
    detector = Detector(obs, baselines, calendar, cfg)
    site_days, episodes = replay(detector, replay_days)
    if events is not None:
        metrics = evaluate_against_events(site_days, episodes, events, replay_days)
        ground_truth, caveat = "simulated_events", CAVEAT_SYNTHETIC
    else:
        metrics = describe_without_truth(site_days, episodes, detector, baseline_days)
        ground_truth, caveat = "none", CAVEAT_REAL

    provenance = {
        "origin": origin,
        "simulated": simulated,
        "label": label or ("SIMULATED camera counts (test fixtures)" if simulated else "Recorded data"),
        "source_kinds": [obs.spec.kind],
        "built_at": _now(),
        "baseline_period": {"start": baseline_days[0].isoformat(), "end": baseline_days[-1].isoformat()},
        "replay_period": {"start": replay_days[0].isoformat(), "end": replay_days[-1].isoformat()},
    }
    cells = baselines.cells
    with_baseline = {key[1] for key in cells}
    model_section = {
        "baseline_cells": len(cells),
        "sites_with_any_baseline": len(with_baseline),
        "sites_without_baseline": sorted(set(obs.sites) - with_baseline)[:20],
        "baseline_days": len(baseline_days),
        "replay_days": len(replay_days),
        "holidays_treated_as_sunday_or_weekend": sorted(d.isoformat() for d in calendar.holidays),
        "saturday_has_own_baseline": calendar.split_saturday,
    }
    report = {
        "generated_at": provenance["built_at"],
        "provenance": provenance,
        "provenance_notes": notes,
        "sources": [obs.summary(), *(extra_sources or [])],
        "model": model_section,
        "evaluation_summary": {k: v for k, v in metrics.items() if not isinstance(v, (list, dict))},
        "blocked": blocked if blocked is not None else _default_blocked(obs, origin),
    }
    fmt = "%Y-%m-%dT%H:%M"
    replay_obs = {
        sid: [
            [d.isoformat(), slot, obs.counts[sid][(d, slot)]]
            for (d, slot) in sorted(obs.counts.get(sid, {}))
            if d > baseline_end
        ]  # fmt: skip
        for sid in obs.sites
    }
    files: dict[str, Any] = {
        "manifest.json": {
            "provenance": provenance,
            "spec": asdict(obs.spec),
            "holidays": sorted(d.isoformat() for d in calendar.holidays),
            "split_saturday": calendar.split_saturday,
            "settings": cfg.to_dict(),
            "days": [d.isoformat() for d in days],
        },
        "sites.json": [asdict(s) for s in obs.sites.values()],
        "baselines.json": baselines.to_json(),
        "replay.json": replay_obs,
        "episodes.json": [
            {
                "site_id": ep.site_id,
                "site_name": obs.sites[ep.site_id].name,
                "start": ep.start.strftime(fmt),
                "end": ep.end.strftime(fmt),
                "peak_observed": ep.peak_observed,
                "peak_ratio": ep.peak_ratio,
                "triggers": sorted(ep.triggers),
                "first_warning_at": ep.first_warning_at.strftime(fmt) if ep.first_warning_at else None,
                "lead_min": ep.lead_min,
                "matched_event": ep.matched_event,
            }
            for ep in episodes
        ],
        "events.json": [e.to_dict() for e in (events or [])],
        "evaluation.json": {
            "provenance": provenance,
            "ground_truth": ground_truth,
            "caveat": caveat,
            "metrics": metrics,
            "notes": _evaluation_notes(ground_truth, cfg),
        },
        "quality_report.json": report,
    }
    for name, payload in files.items():
        (out / name).write_text(json.dumps(payload, separators=(",", ":") if name == "replay.json" else None,
                                           indent=None if name in ("replay.json", "baselines.json") else 2),
                                encoding="utf-8")  # fmt: skip
    (out / "quality_report.md").write_text(render_markdown(report, files["evaluation.json"]), encoding="utf-8")
    return {"report": report, "evaluation": files["evaluation.json"], "out_dir": out}


def _default_blocked(obs: ObservationSet, origin: str) -> list[str]:
    blocked = []
    if obs.spec.kind != "camera_count" or origin == "synthetic":
        blocked.append(BLOCKED_CAMERA)
    blocked.append(BLOCKED_TRAFFIC)
    return blocked


def _evaluation_notes(ground_truth: str, cfg: WarningConfig) -> list[str]:
    notes = [
        "Usual levels are learned only from the baseline period; the replay period is never used to learn them.",
        "At each replay time only data up to that time is used for the status and the forecast.",
        f"Alert: at least {cfg.alert_ratio}x usual and {cfg.alert_z} usual-variation units above it, or an "
        "operator-set threshold. Thresholds are uncalibrated defaults.",
        "The forecast extends the current departure from usual with a damped trend. It cannot foresee a surge "
        "that has not begun, so sudden spikes are caught only when they happen.",
    ]
    if ground_truth == "simulated_events":
        notes.append(
            "Windows from the start of an event's build-up until 30 min after it ends, but outside the "
            "overcrowded part, count neither for nor against the detector."
        )
    return notes


def render_markdown(report: dict[str, Any], evaluation: dict[str, Any]) -> str:
    prov = report["provenance"]
    lines = ["# Early-warning data-quality report", ""]
    if prov["simulated"]:
        lines += ["> **SIMULATED DATA.** Synthetic test fixtures, not real places or crowds.", ""]
    lines += [
        f"* Generated: {report['generated_at']}",
        f"* Dataset: {prov['label']} (origin `{prov['origin']}`)",
        f"* Baseline period: {prov['baseline_period']['start']} to {prov['baseline_period']['end']}",
        f"* Replay period: {prov['replay_period']['start']} to {prov['replay_period']['end']}",
        "",
    ]
    lines += [f"* Note: {n}" for n in report["provenance_notes"]]
    for source in report["sources"]:
        lines += [f"## Source: {source.get('name')} ({source.get('kind')})", ""]
        for key in ("coverage", "window_minutes", "rows_total", "rows_valid", "sites", "days", "first_day", "last_day"):
            if key in source:
                lines.append(f"* {key}: {source[key]}")
        lines += [f"* {n}" for n in source.get("notes", [])]
        s = source.get("summary", {})
        lines += ["", f"Errors: {s.get('errors', 0)}, warnings: {s.get('warnings', 0)}, info: {s.get('infos', 0)}", ""]
        if source.get("issues"):
            lines += ["| Severity | Code | Count | Message |", "| --- | --- | ---: | --- |"]
            lines += [f"| {i['severity']} | `{i['code']}` | {i['count']} | {i['message']} |" for i in source["issues"]]
            lines.append("")
    lines += ["## Model", ""] + [f"* {k}: {v}" for k, v in report["model"].items()] + [""]
    lines += ["## Evaluation", "", f"_{evaluation['caveat']}_", ""]
    for key, value in evaluation["metrics"].items():
        if isinstance(value, list):
            lines.append(f"* {key}:")
            lines += [f"  * `{json_line(v)}`" for v in value]
        else:
            lines.append(f"* {key}: {json_line(value) if isinstance(value, dict) else value}")
    lines += ["", "Notes:", ""] + [f"* {n}" for n in evaluation["notes"]]
    if report["blocked"]:
        lines += ["", "## Blocked / not connected", ""] + [f"* {b}" for b in report["blocked"]]
    return "\n".join(lines) + "\n"


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def replay_days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]
