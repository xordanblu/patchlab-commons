from __future__ import annotations

from typing import Any

from .models import Severity, VerificationReport


def build_sarif(report: VerificationReport) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for finding in report.findings:
        rules.setdefault(
            finding.rule_id,
            {
                "id": finding.rule_id,
                "name": _rule_name(finding.rule_id),
                "shortDescription": {"text": finding.title},
                "fullDescription": {"text": finding.message},
                "help": {"text": finding.recommendation or finding.message},
                "properties": {
                    "tags": list(finding.tags),
                    "disposition": finding.disposition.value,
                },
            },
        )
        result: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "level": _level(finding.severity),
            "message": {"text": finding.message},
            "properties": {
                "disposition": finding.disposition.value,
                "evidence": finding.evidence or "",
            },
        }
        if finding.file:
            location: dict[str, Any] = {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file.replace("\\", "/")},
                }
            }
            if finding.line and finding.line > 0:
                location["physicalLocation"]["region"] = {"startLine": finding.line}
            result["locations"] = [location]
        results.append(result)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "PatchLab Commons",
                        "informationUri": "https://github.com/xordanblu/patchlab-commons",
                        "version": report.tool_version,
                        "rules": [rules[key] for key in sorted(rules)],
                    }
                },
                "automationDetails": {
                    "id": f"patchlab/{report.base_sha[:12]}..{report.head_sha[:12]}"
                },
                "results": results,
                "properties": {
                    "outcome": report.outcome.value,
                    "project": report.project_name,
                    "baseSha": report.base_sha,
                    "headSha": report.head_sha,
                },
            }
        ],
    }


def _level(severity: Severity) -> str:
    if severity is Severity.ERROR:
        return "error"
    if severity is Severity.WARNING:
        return "warning"
    return "note"


def _rule_name(rule_id: str) -> str:
    return rule_id.lower().replace("-", "_")
