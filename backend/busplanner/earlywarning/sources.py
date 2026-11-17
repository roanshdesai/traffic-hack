"""People-count sources -> validated observations per site and time window.

Two import paths:

* **Camera counts**: a CSV of people counts per site and window, as produced by
  camera counting software, plus a sites file. Only aggregated counts are
  accepted. Columns that could identify people (images, faces, track ids,
  plates) are ignored and reported; they must not be supplied.
* **Ticket samples**: ticket records (reusing ``busplanner.tickets``) are
  aggregated into boardings per boarding stop and window. This is a sample of
  passengers, not a headcount.

Records that fail validation are rejected and reported, never repaired.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..quality import IssueLog
from ..textnorm import name_key
from ..tickets import NULL_TOKENS, TicketImport, _parse_timestamp
from .config import CAMERA_SOURCE, TICKET_SOURCE, SourceSpec

COUNT_REQUIRED = ("site_id", "window_start", "count")
COUNT_OPTIONAL = ("confidence", "camera_id")
SITE_REQUIRED = ("site_id", "name")
TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
#: Column names that suggest personal or identifying data. Never read.
IDENTIFYING_HINTS = ("image", "frame", "photo", "face", "person_id", "track_id", "plate", "embedding", "video")


@dataclass(frozen=True)
class SiteInfo:
    site_id: str
    name: str
    kind: str
    lat: float | None
    lon: float | None
    source: str
    coverage: str
    window_minutes: int
    unit: str
    alert_threshold: int | None = None
    max_plausible: int | None = None


@dataclass
class ObservationSet:
    """Counts keyed by site and (day, slot). ``None`` means excluded (treated as no data)."""

    spec: SourceSpec
    sites: dict[str, SiteInfo] = field(default_factory=dict)
    counts: dict[str, dict[tuple[date, int], int | None]] = field(default_factory=lambda: defaultdict(dict))
    days: set[date] = field(default_factory=set)
    log: IssueLog = field(default_factory=IssueLog)
    source_name: str = ""
    rows_total: int = 0
    rows_valid: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def slots_per_day(self) -> int:
        return (self.spec.service_end_min - self.spec.service_start_min) // self.spec.window_minutes

    def slot_of(self, moment: datetime) -> int | None:
        minute = moment.hour * 60 + moment.minute
        offset = minute - self.spec.service_start_min
        if offset < 0 or minute >= self.spec.service_end_min:
            return None
        return offset // self.spec.window_minutes

    def window_start(self, day: date, slot: int) -> datetime:
        return datetime.combine(day, datetime.min.time()) + timedelta(
            minutes=self.spec.service_start_min + slot * self.spec.window_minutes
        )

    def value(self, site_id: str, day: date, slot: int) -> int | None:
        """Observed count, or None for no usable data."""
        site_counts = self.counts.get(site_id, {})
        key = (day, slot)
        if key in site_counts:
            return site_counts[key]
        if self.spec.missing_means_zero and day in self.days:
            return 0
        return None

    def summary(self) -> dict[str, Any]:
        days = sorted(self.days)
        return {
            "name": self.source_name,
            "kind": self.spec.kind,
            "coverage": self.spec.coverage,
            "window_minutes": self.spec.window_minutes,
            "rows_total": self.rows_total,
            "rows_valid": self.rows_valid,
            "sites": len(self.sites),
            "days": len(days),
            "first_day": days[0].isoformat() if days else None,
            "last_day": days[-1].isoformat() if days else None,
            "notes": self.notes,
            "summary": self.log.summary(),
            "issues": self.log.to_list(),
        }


# ---------------------------------------------------------------------------
# camera counts
# ---------------------------------------------------------------------------
def _read_csv(path: Path, log: IssueLog, file: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    if not path.is_file():
        log.add("source_not_found", "error", file, f"File not found: {path}", fatal=True)
        return [], []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            log.add("empty_file", "error", file, "File is empty.", fatal=True)
            return [], []
        rows = []
        for line, raw in enumerate(reader, start=2):
            if raw and any(c.strip() for c in raw):
                rows.append((line, {h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(header)}))
    return header, rows


def _blank(value: str) -> bool:
    return value in NULL_TOKENS


def load_sites(path: Path, spec: SourceSpec, log: IssueLog) -> dict[str, SiteInfo]:
    file = path.name
    header, rows = _read_csv(path, log, file)
    if log.fatal:
        return {}
    missing = [c for c in SITE_REQUIRED if c not in header]
    if missing:
        log.add("missing_column", "error", file, "Sites file lacks a required column.",
                sample={"missing": missing}, fatal=True)  # fmt: skip
        return {}
    sites: dict[str, SiteInfo] = {}
    for line, row in rows:
        sid = row["site_id"]
        if not sid or sid in sites:
            log.add("duplicate_or_missing_site_id", "error", file, "Site row has no id or repeats one; dropped.",
                    sample={"row": line, "site_id": sid})  # fmt: skip
            continue

        def number(col: str, cast: type, line: int = line, sid: str = sid, row: dict = row) -> Any:
            value = row.get(col, "")
            if _blank(value):
                return None
            try:
                result = cast(value)
            except ValueError:
                log.add(f"invalid_{col}", "error", file, f"{col} is not a valid number; ignored for this site.",
                        sample={"row": line, "site_id": sid, col: value})  # fmt: skip
                return None
            if cast is int and result <= 0:
                log.add(f"invalid_{col}", "error", file, f"{col} must be positive; ignored for this site.",
                        sample={"row": line, "site_id": sid, col: value})  # fmt: skip
                return None
            return result

        lat, lon = number("lat", float), number("lon", float)
        if (lat is None) != (lon is None):
            lat = lon = None
        sites[sid] = SiteInfo(
            site_id=sid,
            name=row["name"] or sid,
            kind=row.get("kind") or "other",
            lat=lat,
            lon=lon,
            source=spec.kind,
            coverage=spec.coverage,
            window_minutes=spec.window_minutes,
            unit="people counted",
            alert_threshold=number("alert_threshold", int),
            max_plausible=number("max_plausible", int),
        )
    return sites


def load_camera_counts(
    counts_path: str | Path,
    sites_path: str | Path,
    mapping_path: str | Path | None = None,
    spec: SourceSpec = CAMERA_SOURCE,
    min_confidence: float = 0.5,
) -> ObservationSet:
    counts_path, sites_path = Path(counts_path), Path(sites_path)
    obs = ObservationSet(spec=spec, source_name=counts_path.name)
    log = obs.log
    obs.sites = load_sites(sites_path, spec, log)
    if log.fatal:
        return obs

    columns = {c: c for c in COUNT_REQUIRED + COUNT_OPTIONAL}
    formats = TIMESTAMP_FORMATS
    if mapping_path:
        raw = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        mapped = {k: v for k, v in (raw.get("columns") or {}).items() if v}
        unknown = set(mapped) - set(columns)
        if unknown:
            raise ValueError(f"{mapping_path}: unknown field(s) in mapping: {sorted(unknown)}")
        columns.update(mapped)
        formats = tuple(raw.get("timestamp_formats") or formats)

    file = counts_path.name
    header, rows = _read_csv(counts_path, log, file)
    if log.fatal:
        return obs
    missing = [c for c in COUNT_REQUIRED if columns[c] not in header]
    if missing:
        log.add("missing_column", "error", file, "A required field is not in the file. Fix the mapping.",
                sample={"missing_fields": missing, "file_columns": header}, fatal=True)  # fmt: skip
        return obs
    identifying = [h for h in header if any(hint in h.lower() for hint in IDENTIFYING_HINTS)]
    if identifying:
        log.add("identifying_columns_ignored", "warning", file,
                "Columns that may identify people were found and ignored. Supply aggregated counts only.",
                sample={"columns": identifying})  # fmt: skip
    c_site, c_ts, c_count = columns["site_id"], columns["window_start"], columns["count"]
    c_conf = columns["confidence"] if columns["confidence"] in header else None

    seen: set[tuple[str, date, int]] = set()
    for line, row in rows:
        obs.rows_total += 1
        record = {k: v for k, v in row.items() if k not in identifying}

        def reject(code: str, message: str, line: int = line, record: dict = record) -> None:
            log.add(code, "error", file, message, sample={"row": line, **record})

        site = obs.sites.get(row[c_site])
        if site is None:
            reject("unknown_site", "Count for a site that is not in the sites file; rejected.")
            continue
        moment = _parse_timestamp(row[c_ts], formats)
        if moment is None:
            reject("invalid_timestamp", "Window start is missing or not in a configured format; rejected.")
            continue
        slot = obs.slot_of(moment)
        if slot is None:
            reject("outside_service_hours", "Window lies outside the configured service hours; rejected.")
            continue
        if moment.minute % spec.window_minutes or moment.second or moment.microsecond:
            reject("misaligned_window", f"Window start is not on a {spec.window_minutes}-minute boundary; "
                   "rejected rather than shifted.")  # fmt: skip
            continue
        try:
            count = int(row[c_count])
            if count < 0:
                raise ValueError
        except ValueError:
            reject("invalid_count", "Count is not a non-negative integer; rejected.")
            continue
        if site.max_plausible is not None and count > site.max_plausible:
            reject("implausible_count", f"Count above this site's plausible maximum ({site.max_plausible}); "
                   "rejected pending review, not capped.")  # fmt: skip
            continue
        key = (site.site_id, moment.date(), slot)
        if key in seen:
            reject("duplicate_window", "A count for this site and window was already read; later row rejected.")
            continue
        seen.add(key)
        confidence = None
        if c_conf and not _blank(row[c_conf]):
            try:
                confidence = float(row[c_conf])
            except ValueError:
                confidence = None
        obs.rows_valid += 1
        obs.days.add(moment.date())
        if confidence is not None and confidence < min_confidence:
            log.add("low_confidence", "warning", file,
                    f"Counting software reported confidence below {min_confidence}; the window is excluded "
                    "and shown as no data.", sample={"row": line, "site_id": site.site_id,
                                                      "window_start": row[c_ts], "confidence": confidence})  # fmt: skip
            obs.counts[site.site_id][(moment.date(), slot)] = None
            continue
        obs.counts[site.site_id][(moment.date(), slot)] = count

    _report_gaps(obs)
    return obs


def _report_gaps(obs: ObservationSet) -> None:
    if obs.spec.missing_means_zero or not obs.days:
        return
    expected = len(obs.days) * obs.slots_per_day
    for sid in sorted(obs.sites):
        have = len(obs.counts.get(sid, {}))
        if have == 0:
            obs.log.add("site_without_data", "warning", obs.source_name, "Site has no valid counts at all.",
                        sample=sid)  # fmt: skip
        elif have < expected:
            obs.log.add("missing_windows", "info", obs.source_name,
                        "Windows with no count inside service hours (sensor gaps). Shown as no data, never as zero.",
                        sample={"site_id": sid, "missing": expected - have}, count=expected - have)  # fmt: skip


# ---------------------------------------------------------------------------
# ticket samples
# ---------------------------------------------------------------------------
def tickets_to_observations(
    tickets: TicketImport,
    spec: SourceSpec = TICKET_SOURCE,
    min_site_records: int = 300,
    baseline_end: date | None = None,
) -> ObservationSet:
    """Aggregate ticket records into sampled boardings per boarding stop and window.

    Sites are keyed by the normalised boarding-stop name, because the ticket
    file has names only. Two physical stops with the same name are merged;
    without static GTFS this cannot be told apart, and the report says so.
    Sites with fewer than ``min_site_records`` records (in the baseline period
    when ``baseline_end`` is set) are left out and counted in the report.
    """
    obs = ObservationSet(spec=spec, source_name=Path(tickets.source).name)
    log = obs.log
    raw_counts: dict[str, Counter] = defaultdict(Counter)
    spellings: dict[str, Counter] = defaultdict(Counter)
    baseline_records: Counter = Counter()
    outside = 0
    for t in tickets.tickets:
        obs.rows_total += 1
        key = name_key(t.board_ref)
        if not key:
            continue
        slot = obs.slot_of(t.issued_at)
        day = t.issued_at.date()
        obs.days.add(day)
        if slot is None:
            outside += 1
            continue
        raw_counts[key][(day, slot)] += t.passengers
        spellings[key][t.board_ref] += 1
        if baseline_end is None or day <= baseline_end:
            baseline_records[key] += 1
        obs.rows_valid += 1
    if outside:
        log.add("outside_service_hours", "info", obs.source_name,
                "Tickets issued outside service hours are not assessed.", count=outside)  # fmt: skip
    kept = [k for k in raw_counts if baseline_records[k] >= min_site_records]
    dropped = len(raw_counts) - len(kept)
    if dropped:
        log.add("site_below_minimum_records", "info", obs.source_name,
                f"Boarding stops with fewer than {min_site_records} ticket records in the baseline period are "
                "not assessed (too little history).", count=dropped)  # fmt: skip
    multi_spelling = 0
    for key in sorted(kept):
        name, _n = spellings[key].most_common(1)[0]
        if len(spellings[key]) > 1:
            multi_spelling += 1
        sid = "stop:" + key.replace(" ", "_")
        obs.sites[sid] = SiteInfo(
            site_id=sid,
            name=name,
            kind="bus_stop",
            lat=None,
            lon=None,
            source=spec.kind,
            coverage=spec.coverage,
            window_minutes=spec.window_minutes,
            unit="e-ticket boardings",
        )
        obs.counts[sid] = dict(raw_counts[key])
    if multi_spelling:
        log.add("stop_name_variants_merged", "info", obs.source_name,
                "Stop names that differ only in case, spacing or punctuation were merged into one site.",
                count=multi_spelling)  # fmt: skip
    obs.notes.append(
        "Sites are boarding-stop names. Different physical stops sharing a name are merged; static GTFS is "
        "needed to separate them."
    )
    obs.notes.append(
        "Counts are ticket records (a sample of passengers), not people present at the stop. A missing hour "
        "means no sampled boardings."
    )
    return obs
