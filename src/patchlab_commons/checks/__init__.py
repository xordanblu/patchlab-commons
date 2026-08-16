from __future__ import annotations

from dataclasses import dataclass

from ..config import PatchLabConfig
from ..diffparse import FileDiff
from ..gitutils import GitRepo
from ..models import ChangedFile, Finding


@dataclass(frozen=True, slots=True)
class CheckContext:
    config: PatchLabConfig
    repo: GitRepo
    base_sha: str
    head_sha: str
    changed_files: tuple[ChangedFile, ...]
    diffs: tuple[FileDiff, ...]


def run_checks(context: CheckContext) -> list[Finding]:
    from .dependencies import check_dependencies
    from .network import check_network_additions
    from .scope import check_scope
    from .secrets import check_secret_exposure
    from .tests import check_test_integrity
    from .workflows import check_workflows

    findings: list[Finding] = []
    for check in (
        check_scope,
        check_dependencies,
        check_workflows,
        check_secret_exposure,
        check_network_additions,
        check_test_integrity,
    ):
        findings.extend(check(context))
    return _deduplicate(findings)


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str | None, int | None, str]] = set()
    result: list[Finding] = []
    for finding in findings:
        key = (finding.rule_id, finding.file, finding.line, finding.message)
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result
