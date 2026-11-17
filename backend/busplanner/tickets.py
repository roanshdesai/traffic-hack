"""Ticket-sample import and validation.

The real ticket schema is not known yet, so source columns are mapped onto a
small canonical record through a JSON mapping file (see
``fixtures/synthetic/ticket_mapping.json`` and ``docs/DATA.md``).

A ticket is a *sample of ticketed boardings*. It is not an occupancy
measurement: pass holders, unticketed riders and any rows missing from the
extract are invisible here.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .quality import IssueLog

CANONICAL_REQUIRED = ("issued_at", "route", "board_stop")
CANONICAL_OPTIONAL = ("ticket_id", "alight_stop", "passengers", "direction")
DEFAULT_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)
MAX_PASSENGERS_PER_TICKET = 20
#: Tickets issued before this hour belong to the previous service day,
#: mirroring GTFS trips that run past midnight (times >= 24:00:00).
SERVICE_DAY_START_HOUR = 4


@dataclass(frozen=True)
class TicketMapping:
    columns: dict[str, str | None]
    timestamp_formats: tuple[str, ...] = DEFAULT_TIMESTAMP_FORMATS
    delimiter: str = ","
    encoding: str = "utf-8-sig"

    @classmethod
    def load(cls, path: str | Path) -> TicketMapping:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        columns = raw.get("columns")
        if not isinstance(columns, dict):
            raise ValueError(f"{path}: mapping needs a 'columns' object")
        unknown = set(columns) - set(CANONICAL_REQUIRED) - set(CANONICAL_OPTIONAL)
        if unknown:
            raise ValueError(f"{path}: unknown canonical field(s) in mapping: {sorted(unknown)}")
        return cls(
            columns={k: v for k, v in columns.items() if v},
            timestamp_formats=tuple(raw.get("timestamp_formats") or DEFAULT_TIMESTAMP_FORMATS),
            delimiter=raw.get("delimiter", ","),
            encoding=raw.get("encoding", "utf-8-sig"),
        )

    @classmethod
    def identity(cls) -> TicketMapping:
        """Source file already uses the canonical column names."""
        return cls(columns={k: k for k in CANONICAL_REQUIRED + CANONICAL_OPTIONAL})


@dataclass(slots=True)
class Ticket:
    row: int  # 1-based line number in the source file (header is line 1)
    ticket_id: str
    issued_at: datetime  # naive, local (Asia/Kolkata)
    route_ref: str
    board_ref: str
    alight_ref: str  # "" when the ticket has no alighting stop
    passengers: int
    direction_ref: str = ""

    @property
    def service_date(self) -> date:
        return (self.issued_at - timedelta(hours=SERVICE_DAY_START_HOUR)).date()


@dataclass(slots=True)
class RejectedRow:
    row: int
    code: str
    raw: dict[str, str]


@dataclass
class TicketImport:
    source: str
    tickets: list[Ticket] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    log: IssueLog = field(default_factory=IssueLog)
    rows_total: int = 0
    has_alight_column: bool = False
    has_passenger_column: bool = False

    def service_dates(self) -> list[date]:
        return sorted({t.service_date for t in self.tickets})

    def summary(self) -> dict[str, Any]:
        dates = self.service_dates()
        return {
            "source": self.source,
            "rows_total": self.rows_total,
            "rows_valid": len(self.tickets),
            "rows_rejected": len(self.rejected),
            "rows_without_alight_stop": sum(1 for t in self.tickets if not t.alight_ref),
            "service_days": len(dates),
            "first_service_date": dates[0].isoformat() if dates else None,
            "last_service_date": dates[-1].isoformat() if dates else None,
            "has_alight_column": self.has_alight_column,
            "has_passenger_column": self.has_passenger_column,
        }


def _parse_timestamp(value: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=None)
    return None


def load_tickets(path: str | Path, mapping: TicketMapping | None = None) -> TicketImport:
    path = Path(path)
    mapping = mapping or TicketMapping.identity()
    name = path.name
    result = TicketImport(source=str(path))
    log = result.log
    if not path.is_file():
        log.add("source_not_found", "error", name, f"Ticket file not found: {path}", fatal=True)
        return result

    with open(path, encoding=mapping.encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=mapping.delimiter)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            log.add("empty_file", "error", name, "Ticket file is empty.", fatal=True)
            return result

        cols = mapping.columns
        missing = [c for c in CANONICAL_REQUIRED if not cols.get(c) or cols[c] not in header]
        if missing:
            log.add(
                "missing_column", "error", name,
                "A required field is not mapped to a column present in the file. Fix the mapping file.",
                sample={"missing_fields": missing, "file_columns": header}, count=len(missing), fatal=True,
            )  # fmt: skip
            return result
        for optional in CANONICAL_OPTIONAL:
            if cols.get(optional) and cols[optional] not in header:
                log.add("mapped_column_absent", "warning", name,
                        "An optional field is mapped to a column that is not in the file; it is ignored.",
                        sample={"field": optional, "column": cols[optional]})  # fmt: skip
        index = {h: i for i, h in enumerate(header)}

        def col(field_name: str) -> int | None:
            source = cols.get(field_name)
            return index.get(source) if source else None

        c_id, c_ts, c_route = col("ticket_id"), col("issued_at"), col("route")
        c_board, c_alight, c_pax, c_dir = col("board_stop"), col("alight_stop"), col("passengers"), col("direction")
        result.has_alight_column = c_alight is not None
        result.has_passenger_column = c_pax is not None
        if c_alight is None:
            log.add("no_alight_column", "warning", name,
                    "No alighting-stop column: tickets show boardings only, so segment loads "
                    "cannot be estimated and every segment will report insufficient evidence.")  # fmt: skip
        if c_pax is None:
            log.add("no_passenger_column", "info", name,
                    "No passenger-count column: each ticket row is counted as one rider.")  # fmt: skip

        seen_ids: set[str] = set()
        line = 1
        for raw in reader:
            line += 1
            if not raw or all(not c.strip() for c in raw):
                continue
            result.rows_total += 1

            def get(i: int | None, raw: list[str] = raw) -> str:
                return raw[i].strip() if i is not None and i < len(raw) else ""

            def reject(code: str, message: str, raw: list[str] = raw, line: int = line) -> None:
                record = {h: (raw[i].strip() if i < len(raw) else "") for h, i in index.items()}
                log.add(code, "error", name, message, sample={"row": line, **record})
                result.rejected.append(RejectedRow(line, code, record))

            issued = _parse_timestamp(get(c_ts), mapping.timestamp_formats)
            if issued is None:
                reject("invalid_timestamp", "Timestamp is missing or not in a configured format; row rejected.")
                continue
            route_ref, board_ref, alight_ref = get(c_route), get(c_board), get(c_alight)
            if not route_ref:
                reject("missing_route", "Ticket has no route reference; row rejected.")
                continue
            if not board_ref:
                reject("missing_board_stop", "Ticket has no boarding stop; row rejected.")
                continue
            passengers = 1
            if c_pax is not None:
                try:
                    passengers = int(get(c_pax))
                    if passengers < 1:
                        raise ValueError
                except ValueError:
                    reject("invalid_passenger_count", "Passenger count is not a positive integer; row rejected.")
                    continue
                if passengers > MAX_PASSENGERS_PER_TICKET:
                    reject(
                        "implausible_passenger_count",
                        f"Passenger count above {MAX_PASSENGERS_PER_TICKET} on one ticket; row rejected "
                        "pending review rather than capped.",
                    )
                    continue
            ticket_id = get(c_id)
            if ticket_id:
                if ticket_id in seen_ids:
                    reject("duplicate_ticket_id", "Ticket id already seen; later row rejected.")
                    continue
                seen_ids.add(ticket_id)
            if alight_ref and alight_ref == board_ref:
                reject("same_board_alight", "Boarding and alighting stop are identical; row rejected.")
                continue
            if c_alight is not None and not alight_ref:
                log.add("missing_alight_stop", "info", name,
                        "Ticket has no alighting stop. It is kept as a boarding-only record and "
                        "does not contribute to segment loads.", sample={"row": line})  # fmt: skip
            result.tickets.append(
                Ticket(
                    line, ticket_id or f"row-{line}", issued, route_ref, board_ref, alight_ref, passengers, get(c_dir)
                )  # fmt: skip
            )
    if not result.tickets:
        log.add("no_valid_tickets", "error", name, "No ticket row passed validation.")
    return result
