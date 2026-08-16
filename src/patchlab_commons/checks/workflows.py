from __future__ import annotations

import re

from ..models import Disposition, Finding, Severity
from . import CheckContext

_WORKFLOW_RE = re.compile(r"^\.github/workflows/.*\.ya?ml$")
_WRITE_PERMISSION_NAMES = (
    "actions|checks|contents|deployments|discussions|id-token|issues|packages|"
    "pages|pull-requests|repository-projects|security-events|statuses"
)
_WRITE_PERMISSION_RE = re.compile(
    rf"^\s*({_WRITE_PERMISSION_NAMES}):\s*write\s*(?:#.*)?$",
    re.IGNORECASE,
)
_INLINE_WRITE_PERMISSION_RE = re.compile(
    rf"^\s*permissions\s*:\s*\{{[^}}]*\b(?:{_WRITE_PERMISSION_NAMES})"
    rf"\s*:\s*write\b",
    re.IGNORECASE,
)
_USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
_SHA_RE = re.compile(r"^[^@]+@[0-9a-fA-F]{40}$")


def check_workflows(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    workflow_paths = {item.path for item in context.changed_files if _WORKFLOW_RE.match(item.path)}
    for path in sorted(workflow_paths):
        disposition = context.config.policy.workflow_changes
        findings.append(
            Finding(
                rule_id="PL-GHA-001",
                title="GitHub Actions workflow changed",
                message=f"{path} changes repository automation and its effective permissions.",
                severity=_severity(disposition),
                disposition=disposition,
                file=path,
                recommendation="Review the event trigger, permissions, secrets, external actions, and shell steps.",
                tags=("github-actions", "permissions"),
            )
        )

    for file_diff in context.diffs:
        path = file_diff.path
        if path not in workflow_paths:
            continue
        for line in file_diff.additions():
            text = line.text.strip()
            lower = text.lower()
            if (
                lower.startswith("permissions: write-all")
                or _WRITE_PERMISSION_RE.match(line.text)
                or _INLINE_WRITE_PERMISSION_RE.match(line.text)
            ):
                disposition = context.config.policy.dangerous_permissions
                findings.append(
                    Finding(
                        rule_id="PL-GHA-002",
                        title="Write permission added",
                        message=f"A GitHub Actions write permission was added: {text}",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=path,
                        line=line.new_line,
                        evidence=text,
                        recommendation=(
                            "Use read-only permissions by default and grant one "
                            "narrow write permission only where required."
                        ),
                        tags=("github-actions", "least-privilege"),
                    )
                )
            if re.match(r"^pull_request_target\s*:", text):
                disposition = context.config.policy.dangerous_permissions
                findings.append(
                    Finding(
                        rule_id="PL-GHA-003",
                        title="pull_request_target trigger added",
                        message="pull_request_target can expose privileged context to untrusted pull-request data.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=path,
                        line=line.new_line,
                        evidence=text,
                        recommendation=(
                            "Use pull_request with read-only permissions, or isolate "
                            "all untrusted checkout and input handling."
                        ),
                        tags=("github-actions", "untrusted-input"),
                    )
                )
            if "persist-credentials: true" in lower:
                disposition = context.config.policy.dangerous_permissions
                findings.append(
                    Finding(
                        rule_id="PL-GHA-004",
                        title="Git credentials persisted",
                        message="actions/checkout credentials are explicitly persisted in the working copy.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=path,
                        line=line.new_line,
                        evidence=text,
                        recommendation="Set persist-credentials to false unless a reviewed write step requires it.",
                        tags=("github-actions", "credentials"),
                    )
                )
            if "continue-on-error: true" in lower:
                findings.append(
                    Finding(
                        rule_id="PL-GHA-005",
                        title="Workflow failure suppression added",
                        message="A workflow step can now fail without failing the job.",
                        severity=Severity.WARNING,
                        disposition=Disposition.REVIEW,
                        file=path,
                        line=line.new_line,
                        evidence=text,
                        recommendation="Explain why failure is safe, or remove continue-on-error.",
                        tags=("github-actions", "test-integrity"),
                    )
                )
            if re.search(r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", line.text):
                disposition = context.config.policy.dangerous_permissions
                findings.append(
                    Finding(
                        rule_id="PL-GHA-006",
                        title="Remote script execution added",
                        message="The workflow downloads content and executes it directly in a shell.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=path,
                        line=line.new_line,
                        evidence=text,
                        recommendation="Download a pinned artifact, verify its digest, and execute only after review.",
                        tags=("github-actions", "supply-chain"),
                    )
                )
            uses = _USES_RE.match(line.text)
            if uses:
                target = uses.group(1)
                if target.lower().startswith("actions/checkout@"):
                    head_workflow = context.repo.file_at(context.head_sha, path)
                    if (
                        head_workflow is not None
                        and _checkout_setting(
                            head_workflow,
                            line.new_line,
                        )
                        is None
                    ):
                        disposition = context.config.policy.dangerous_permissions
                        findings.append(
                            Finding(
                                rule_id="PL-GHA-004",
                                title="Git credentials persisted by default",
                                message=(
                                    "A newly added actions/checkout step does not set "
                                    "persist-credentials to false."
                                ),
                                severity=_severity(disposition),
                                disposition=disposition,
                                file=path,
                                line=line.new_line,
                                evidence=target,
                                recommendation=(
                                    "Set persist-credentials: false unless a reviewed "
                                    "write step requires the checkout token."
                                ),
                                tags=("github-actions", "credentials"),
                            )
                        )
                if not target.startswith(("./", "docker://")) and not _SHA_RE.match(target):
                    findings.append(
                        Finding(
                            rule_id="PL-GHA-007",
                            title="External action is not pinned by commit SHA",
                            message=f"{target} uses a mutable tag or branch.",
                            severity=Severity.WARNING,
                            disposition=Disposition.REVIEW,
                            file=path,
                            line=line.new_line,
                            evidence=target,
                            recommendation="Pin third-party actions to a reviewed 40-character commit SHA.",
                            tags=("github-actions", "supply-chain"),
                        )
                    )
    return findings


def _checkout_setting(workflow: str, line_number: int | None) -> bool | None:
    """Return an explicit persist-credentials value for one checkout step.

    ``None`` means that the step relies on the action default.
    """

    if line_number is None:
        return None
    lines = workflow.splitlines()
    index = line_number - 1
    if index < 0 or index >= len(lines):
        return None
    uses_line = lines[index]
    step_indent = len(uses_line) - len(uses_line.lstrip())
    for raw in lines[index + 1 :]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent <= step_indent and stripped.startswith("-"):
            break
        match = re.match(r"^persist-credentials\s*:\s*(true|false)\s*(?:#.*)?$", stripped, re.I)
        if match:
            return match.group(1).lower() == "true"
    return None


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
