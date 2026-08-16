from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..models import Disposition, Finding, Severity
from . import CheckContext

_SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".sh",
    ".bash",
    ".zsh",
    ".yml",
    ".yaml",
}
_NETWORK_PATTERNS = [
    (re.compile(r"\brequests\.(?:get|post|put|patch|delete|request)\s*\("), "Python requests call"),
    (
        re.compile(r"\bhttpx\.(?:get|post|put|patch|delete|request|Client|AsyncClient)\b"),
        "Python httpx use",
    ),
    (re.compile(r"\burllib\.request\b"), "Python urllib network use"),
    (re.compile(r"\b(?:fetch|axios\.(?:get|post|put|patch|delete))\s*\("), "JavaScript HTTP call"),
    (re.compile(r"\bnet/http\b"), "Go net/http use"),
    (re.compile(r"\breqwest(?:::|\.)"), "Rust reqwest use"),
    (re.compile(r"\b(?:curl|wget)\b"), "command-line network client"),
    (re.compile(r"\bsocket\.(?:socket|create_connection)\b"), "raw socket use"),
    (re.compile(r"https?://[^\s\"']+"), "new URL literal"),
]


def check_network_additions(context: CheckContext) -> list[Finding]:
    disposition = context.config.policy.network_additions
    findings: list[Finding] = []
    for file_diff in context.diffs:
        suffix = PurePosixPath(file_diff.path).suffix.lower()
        if suffix not in _SOURCE_SUFFIXES:
            continue
        for line in file_diff.additions():
            stripped = line.text.strip()
            if stripped.startswith(("#", "//", "*")):
                continue
            for pattern, label in _NETWORK_PATTERNS:
                if pattern.search(line.text):
                    findings.append(
                        Finding(
                            rule_id="PL-NET-001",
                            title="Network capability added",
                            message=f"A {label} was added.",
                            severity=_severity(disposition),
                            disposition=disposition,
                            file=file_diff.path,
                            line=line.new_line,
                            evidence=stripped[:240],
                            recommendation=(
                                "Document the destination, data sent, timeout, retry "
                                "policy, and trust boundary."
                            ),
                            tags=("network", "capability"),
                        )
                    )
                    break
    return findings


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
