from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Outcome, VerificationReport
from .safeio import ensure_output_directory, safe_write_text
from .sarif import build_sarif


def pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_report_files(report: VerificationReport, output_dir: Path) -> dict[str, Path]:
    ensure_output_directory(output_dir)
    paths = {
        "json": output_dir / "report.json",
        "markdown": output_dir / "report.md",
        "sarif": output_dir / "results.sarif",
    }
    safe_write_text(paths["json"], pretty_json(report.to_dict()))
    safe_write_text(paths["markdown"], render_markdown(report))
    safe_write_text(paths["sarif"], pretty_json(build_sarif(report)))
    return paths


def render_markdown(report: VerificationReport) -> str:
    icon = {Outcome.PASS: "✅", Outcome.NEEDS_REVIEW: "⚠️", Outcome.FAIL: "❌"}[report.outcome]
    lines = [
        "# Patch Passport",
        "",
        f"{icon} **Outcome: `{report.outcome.value}`**",
        "",
        "## Identity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Project | {_code(report.project_name)} |",
        f"| Repository | {_code(report.repository)} |",
        f"| Base | {_code(report.base_ref)} → {_code(report.base_sha)} |",
        f"| Head | {_code(report.head_ref)} → {_code(report.head_sha)} |",
        f"| Generated | {_code(report.generated_at)} |",
        f"| PatchLab | {_code(report.tool_version)} |",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Changed files | {report.summary.get('changed_files', 0)} |",
        f"| Commands | {report.summary.get('commands', 0)} |",
        f"| Passed commands | {report.summary.get('commands_passed', 0)} |",
        f"| Findings | {report.summary.get('findings', 0)} |",
        f"| Blocking findings | {report.summary.get('blocking_findings', 0)} |",
        f"| Review findings | {report.summary.get('review_findings', 0)} |",
        "",
        "## Command evidence",
        "",
    ]
    if not report.command_results:
        lines.append("No commands were configured.")
    else:
        lines.extend(
            [
                "| Command | Phase | Expected | Exit | Result | Duration |",
                "|---|---|---|---:|---|---:|",
            ]
        )
        for command in report.command_results:
            result = "PASS" if command.passed else "FAIL"
            if command.timed_out:
                exit_value = "timeout"
            elif command.exit_code is None:
                exit_value = "not started"
            else:
                exit_value = str(command.exit_code)
            lines.append(
                "| "
                f"{_code(command.name)} | {_code(command.phase)} | "
                f"{_code(command.expected_exit)} | {_text(exit_value)} | "
                f"**{result}** | {command.duration_seconds:.3f}s |"
            )
    lines.extend(["", "## Policy findings", ""])
    if not report.findings:
        lines.append("No policy findings.")
    else:
        lines.extend(["| Rule | Decision | Location | Finding |", "|---|---|---|---|"])
        for finding in report.findings:
            location = finding.file or "repository"
            if finding.line:
                location += f":{finding.line}"
            lines.append(
                "| "
                f"{_code(finding.rule_id)} | "
                f"**{finding.disposition.value.upper()}** | "
                f"{_code(location)} | {_text(finding.message)} |"
            )
        lines.extend(["", "### Recommendations", ""])
        for finding in report.findings:
            if finding.recommendation:
                lines.append(f"- **{_text(finding.rule_id)}:** {_text(finding.recommendation)}")
    lines.extend(["", "## Changed files", ""])
    if not report.changed_files:
        lines.append("No changed files.")
    else:
        lines.extend(["| Status | File | Added | Deleted |", "|---|---|---:|---:|"])
        for changed in report.changed_files:
            added = (
                "binary"
                if changed.binary
                else str(changed.added_lines if changed.added_lines is not None else "?")
            )
            deleted = (
                "binary"
                if changed.binary
                else str(changed.deleted_lines if changed.deleted_lines is not None else "?")
            )
            lines.append(
                f"| {_code(changed.status)} | {_code(changed.path)} | "
                f"{_text(added)} | {_text(deleted)} |"
            )
    lines.extend(
        [
            "",
            "---",
            "",
            "This passport records reproducible evidence. It does not replace human review.",
            "",
        ]
    )
    return "\n".join(lines)


def _text(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ("|", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped.replace("\r", " ").replace("\n", " ")


def _code(value: str) -> str:
    normalized = value.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    run = 0
    longest = 0
    for character in normalized:
        if character == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    fence = "`" * (longest + 1)
    needs_padding = (
        normalized.startswith("`")
        or normalized.endswith("`")
        or normalized.startswith(" ")
        or normalized.endswith(" ")
    )
    if needs_padding:
        normalized = f" {normalized} "
    return f"{fence}{normalized}{fence}"
