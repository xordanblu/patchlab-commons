from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..models import Disposition, Finding, Severity
from . import CheckContext

_ASSERT_RE = re.compile(r"\b(assert|expect\s*\(|pytest\.raises|assertRaises|should\b|require\.)")
_SKIP_RE = re.compile(
    r"(@(?:unittest\.)?skip|pytest\.mark\.(?:skip|xfail)|"
    r"\b(?:describe|it|test)\.skip\b|\bxit\s*\(|\bxdescribe\s*\()"
)
_SUPPRESS_RE = re.compile(r"(?:\|\|\s*true|continue-on-error:\s*true|set\s*\+e|--passWithNoTests)", re.IGNORECASE)


def check_test_integrity(context: CheckContext) -> list[Finding]:
    disposition = context.config.policy.test_weakening
    findings: list[Finding] = []
    for item in context.changed_files:
        if item.status.startswith("D") and _is_test_path(item.path):
            findings.append(
                Finding(
                    rule_id="PL-TEST-001",
                    title="Test file deleted",
                    message=f"The patch deletes test file {item.path}.",
                    severity=_severity(disposition),
                    disposition=disposition,
                    file=item.path,
                    recommendation="Explain why coverage remains equivalent or restore the test.",
                    tags=("tests", "integrity"),
                )
            )

    for file_diff in context.diffs:
        is_test = _is_test_path(file_diff.path)
        if is_test:
            for line in file_diff.deletions():
                if _ASSERT_RE.search(line.text):
                    findings.append(
                        Finding(
                            rule_id="PL-TEST-002",
                            title="Test assertion removed",
                            message="An assertion or expected-failure check was removed from a test.",
                            severity=_severity(disposition),
                            disposition=disposition,
                            file=file_diff.path,
                            line=line.old_line,
                            evidence=line.text.strip()[:240],
                            recommendation="Show equivalent coverage or restore the assertion.",
                            tags=("tests", "integrity"),
                        )
                    )
            for line in file_diff.additions():
                if _SKIP_RE.search(line.text):
                    findings.append(
                        Finding(
                            rule_id="PL-TEST-003",
                            title="Test skip added",
                            message="A test skip or expected-failure marker was added.",
                            severity=_severity(disposition),
                            disposition=disposition,
                            file=file_diff.path,
                            line=line.new_line,
                            evidence=line.text.strip()[:240],
                            recommendation="Remove the skip or document a narrow, time-bounded exception.",
                            tags=("tests", "integrity"),
                        )
                    )
        for line in file_diff.additions():
            if _SUPPRESS_RE.search(line.text):
                findings.append(
                    Finding(
                        rule_id="PL-TEST-004",
                        title="Failure suppression added",
                        message="The patch adds syntax that can hide a failed command or empty test run.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=file_diff.path,
                        line=line.new_line,
                        evidence=line.text.strip()[:240],
                        recommendation=(
                            "Let failures propagate, or add a reviewed check for the "
                            "specific acceptable failure."
                        ),
                        tags=("tests", "integrity"),
                    )
                )
    return findings


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = PurePosixPath(normalized).name
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or "/test/" in normalized
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts", "test.go"))
    )


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
