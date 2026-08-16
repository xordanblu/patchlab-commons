from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..models import Disposition, Finding, Severity
from . import CheckContext

_SENSITIVE_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519"}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_SECRET_LOG_RE = re.compile(
    r"\b(?:echo|printf|print|console\.log|logger)\b.*(?:secrets\.|token|password|passwd|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
_TOKEN_ASSIGNMENT_RE = re.compile(
    r"\b(?:token|password|passwd|api[_-]?key|secret|private[_-]?key)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/.+=]{20,}",
    re.IGNORECASE,
)


def check_secret_exposure(context: CheckContext) -> list[Finding]:
    disposition = context.config.policy.secret_exposure
    findings: list[Finding] = []
    for item in context.changed_files:
        name = PurePosixPath(item.path).name
        suffix = PurePosixPath(item.path).suffix.lower()
        if name in _SENSITIVE_NAMES or suffix in _SENSITIVE_SUFFIXES:
            findings.append(
                Finding(
                    rule_id="PL-SECRET-001",
                    title="Sensitive file added or changed",
                    message=f"{item.path} can contain credentials or private key material.",
                    severity=_severity(disposition),
                    disposition=disposition,
                    file=item.path,
                    recommendation="Remove the file from Git history and rotate any exposed credential.",
                    tags=("secrets", "credentials"),
                )
            )

    for file_diff in context.diffs:
        for line in file_diff.additions():
            text = line.text
            if _PRIVATE_KEY_RE.search(text):
                findings.append(
                    Finding(
                        rule_id="PL-SECRET-002",
                        title="Private key material added",
                        message="A private-key header was added to the repository.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=file_diff.path,
                        line=line.new_line,
                        evidence="Private-key header detected; content withheld.",
                        recommendation="Remove it from Git history and rotate the key immediately.",
                        tags=("secrets", "private-key"),
                    )
                )
            if _SECRET_LOG_RE.search(text):
                findings.append(
                    Finding(
                        rule_id="PL-SECRET-003",
                        title="Possible secret logging added",
                        message="A new logging statement may print a credential or secret value.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=file_diff.path,
                        line=line.new_line,
                        evidence=_redact(text),
                        recommendation="Remove the logging statement or log only a non-sensitive identifier.",
                        tags=("secrets", "logging"),
                    )
                )
            if _TOKEN_ASSIGNMENT_RE.search(text) and not _looks_placeholder(text):
                findings.append(
                    Finding(
                        rule_id="PL-SECRET-004",
                        title="Possible hard-coded credential added",
                        message="A long value assigned to a credential-like name was detected.",
                        severity=_severity(disposition),
                        disposition=disposition,
                        file=file_diff.path,
                        line=line.new_line,
                        evidence=_redact(text),
                        recommendation="Use a secret manager or environment variable and rotate the exposed value.",
                        tags=("secrets", "hard-coded"),
                    )
                )
    return findings


def _looks_placeholder(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in ("example", "placeholder", "changeme", "your_", "test-token", "dummy"))


def _redact(text: str) -> str:
    return _TOKEN_ASSIGNMENT_RE.sub("credential=<redacted>", text)[:240]


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
