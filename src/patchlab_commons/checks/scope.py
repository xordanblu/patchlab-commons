from __future__ import annotations

from pathlib import PurePosixPath

from ..models import Disposition, Finding, Severity
from . import CheckContext

_GENERATED_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".map",
    ".lockb",
    ".pb.go",
    ".generated.py",
    ".g.cs",
}
_GENERATED_PATH_PARTS = {"dist", "build", "coverage", "vendor", "node_modules"}


def check_scope(context: CheckContext) -> list[Finding]:
    config = context.config
    findings: list[Finding] = []
    files = context.changed_files
    if len(files) > config.scope.max_files:
        findings.append(
            Finding(
                rule_id="PL-SCOPE-001",
                title="Too many changed files",
                message=f"The patch changes {len(files)} files; the policy limit is {config.scope.max_files}.",
                severity=Severity.ERROR,
                disposition=Disposition.DENY,
                recommendation="Split the patch into smaller, reviewable changes or raise the limit deliberately.",
                tags=("scope", "reviewability"),
            )
        )

    added = sum(item.added_lines or 0 for item in files)
    deleted = sum(item.deleted_lines or 0 for item in files)
    if added > config.scope.max_added_lines:
        findings.append(
            Finding(
                rule_id="PL-SCOPE-002",
                title="Added-line limit exceeded",
                message=f"The patch adds {added} lines; the policy limit is {config.scope.max_added_lines}.",
                severity=Severity.ERROR,
                disposition=Disposition.DENY,
                recommendation="Reduce the patch or document and approve a larger review scope.",
                tags=("scope", "reviewability"),
            )
        )
    if deleted > config.scope.max_deleted_lines:
        findings.append(
            Finding(
                rule_id="PL-SCOPE-003",
                title="Deleted-line limit exceeded",
                message=f"The patch deletes {deleted} lines; the policy limit is {config.scope.max_deleted_lines}.",
                severity=Severity.ERROR,
                disposition=Disposition.DENY,
                recommendation="Reduce the patch or document and approve a larger review scope.",
                tags=("scope", "reviewability"),
            )
        )

    for item in files:
        if not config.scope.allowed(item.path):
            findings.append(
                Finding(
                    rule_id="PL-SCOPE-004",
                    title="File outside approved scope",
                    message=f"{item.path} is not allowed by the configured scope.",
                    severity=Severity.ERROR,
                    disposition=Disposition.DENY,
                    file=item.path,
                    recommendation="Remove the file from this patch or update patchlab.toml after human review.",
                    tags=("scope",),
                )
            )
        if item.binary:
            findings.append(
                Finding(
                    rule_id="PL-SCOPE-005",
                    title="Binary file changed",
                    message=f"{item.path} is binary and cannot be reviewed as a text diff.",
                    severity=_severity(config.policy.binary_files),
                    disposition=config.policy.binary_files,
                    file=item.path,
                    recommendation="Provide provenance and a reproducible build, or remove the binary from the patch.",
                    tags=("binary", "provenance"),
                )
            )
        if _looks_generated(item.path):
            findings.append(
                Finding(
                    rule_id="PL-SCOPE-006",
                    title="Generated output changed",
                    message=f"{item.path} looks generated or vendored.",
                    severity=_severity(config.policy.generated_files),
                    disposition=config.policy.generated_files,
                    file=item.path,
                    recommendation="Document the generator and include a reproducible generation command.",
                    tags=("generated", "provenance"),
                )
            )
    return findings


def _looks_generated(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized.endswith(suffix) for suffix in _GENERATED_SUFFIXES):
        return True
    return any(part in _GENERATED_PATH_PARTS for part in PurePosixPath(normalized).parts)


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
