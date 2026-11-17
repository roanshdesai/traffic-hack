"""Issue collection shared by the GTFS and ticket importers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]
MAX_SAMPLES = 5


@dataclass
class Issue:
    code: str
    severity: Severity
    file: str
    message: str
    count: int = 0
    samples: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file,
            "count": self.count,
            "message": self.message,
            "samples": self.samples,
        }


class IssueLog:
    """Aggregates repeated problems into one issue per (code, file) with a few samples."""

    def __init__(self) -> None:
        self._issues: dict[tuple[str, str], Issue] = {}
        self.fatal = False

    def add(
        self,
        code: str,
        severity: Severity,
        file: str,
        message: str,
        sample: Any = None,
        count: int = 1,
        fatal: bool = False,
    ) -> None:
        issue = self._issues.get((code, file))
        if issue is None:
            issue = self._issues[(code, file)] = Issue(code, severity, file, message)
        issue.count += count
        if sample is not None and len(issue.samples) < MAX_SAMPLES:
            issue.samples.append(sample)
        if fatal:
            self.fatal = True

    def count(self, code: str) -> int:
        return sum(i.count for (c, _f), i in self._issues.items() if c == code)

    def summary(self) -> dict[str, int]:
        out = {"errors": 0, "warnings": 0, "infos": 0}
        for issue in self._issues.values():
            out[issue.severity + "s"] += issue.count
        return out

    def to_list(self) -> list[dict[str, Any]]:
        order = {"error": 0, "warning": 1, "info": 2}
        issues = sorted(self._issues.values(), key=lambda i: (order[i.severity], i.file, i.code))
        return [i.to_dict() for i in issues]
