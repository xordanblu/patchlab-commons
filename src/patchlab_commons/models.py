from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Disposition(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


class Outcome(StrEnum):
    PASS = "pass"
    NEEDS_REVIEW = "needs_review"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    title: str
    message: str
    severity: Severity
    disposition: Disposition
    file: str | None = None
    line: int | None = None
    evidence: str | None = None
    recommendation: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.disposition is Disposition.DENY

    @property
    def requires_review(self) -> bool:
        return self.disposition is Disposition.REVIEW

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["disposition"] = self.disposition.value
        data["tags"] = list(self.tags)
        return data


@dataclass(frozen=True, slots=True)
class CommandResult:
    name: str
    phase: str
    command: tuple[str, ...]
    required: bool
    expected_exit: str
    exit_code: int | None
    passed: bool
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = list(self.command)
        return data


@dataclass(frozen=True, slots=True)
class ChangedFile:
    status: str
    path: str
    old_path: str | None = None
    added_lines: int | None = None
    deleted_lines: int | None = None
    binary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationReport:
    schema_version: str
    tool_version: str
    project_name: str
    generated_at: str
    repository: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    outcome: Outcome
    summary: dict[str, int]
    changed_files: list[ChangedFile] = field(default_factory=list)
    command_results: list[CommandResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "project_name": self.project_name,
            "generated_at": self.generated_at,
            "repository": self.repository,
            "base_ref": self.base_ref,
            "base_sha": self.base_sha,
            "head_ref": self.head_ref,
            "head_sha": self.head_sha,
            "outcome": self.outcome.value,
            "summary": dict(self.summary),
            "changed_files": [item.to_dict() for item in self.changed_files],
            "command_results": [item.to_dict() for item in self.command_results],
            "findings": [item.to_dict() for item in self.findings],
            "metadata": self.metadata,
        }
