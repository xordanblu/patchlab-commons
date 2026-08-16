from __future__ import annotations

import hashlib
import os
import platform
import sys
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ._version import __version__
from .checks import CheckContext, run_checks
from .config import (
    ConfigError,
    ExecutionConfig,
    PatchLabConfig,
    is_pinned_container_image,
    load_config_text,
)
from .diffparse import align_file_diffs, parse_unified_diff
from .gitutils import GitRepo
from .models import Disposition, Finding, Outcome, Severity, VerificationReport
from .passport import create_passport_bundle
from .reporting import write_report_files
from .runner import ExecutionUnavailable, ExecutorSelection, run_command, select_executor
from .safeio import resolve_output_directory


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    repository: Path
    config_path: Path
    base_ref: str
    head_ref: str
    output_dir: Path
    fail_on_review: bool | None = None
    config_source: str = "base"
    execution_mode: str | None = None
    container_runtime: str | None = None
    container_image: str | None = None
    network: bool | None = None
    allow_unsafe_native: bool | None = None
    untrusted_root: Path | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    report: VerificationReport
    artifacts: dict[str, str]


class VerificationEngine:
    def verify(self, request: VerificationRequest) -> VerificationResult:
        repo = GitRepo(
            request.repository,
            untrusted_root=request.untrusted_root or request.repository,
        )
        base_sha = repo.resolve(request.base_ref)
        head_sha = repo.resolve(request.head_ref)
        config, config_text, config_location = _load_config(
            repo,
            request.config_path,
            request.config_source,
            base_sha,
            head_sha,
        )
        config_digest = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
        execution = _effective_execution(config.execution, request)

        findings: list[Finding] = []
        if base_sha == head_sha:
            findings.append(
                Finding(
                    rule_id="PL-GIT-001",
                    title="Base and head are identical",
                    message="The selected refs resolve to the same commit.",
                    severity=Severity.ERROR,
                    disposition=Disposition.DENY,
                    recommendation="Select a base commit before the patch and the candidate head commit.",
                    tags=("git", "configuration"),
                )
            )
        if config.policy.require_clean_worktree and not repo.is_clean():
            findings.append(
                Finding(
                    rule_id="PL-GIT-002",
                    title="Working tree is not clean",
                    message="Uncommitted files are present and are not part of the compared commits.",
                    severity=Severity.ERROR,
                    disposition=Disposition.DENY,
                    recommendation="Commit, stash, or remove unrelated working-tree changes.",
                    tags=("git", "provenance"),
                )
            )

        changed_files = repo.changed_files(base_sha, head_sha)
        diff_text = repo.unified_diff(base_sha, head_sha)
        parsed_diffs = parse_unified_diff(diff_text)
        if len(parsed_diffs) != len(changed_files):
            findings.append(
                Finding(
                    rule_id="PL-GIT-003",
                    title="Diff metadata could not be reconciled",
                    message=(
                        "Git reported a different number of changed files than PatchLab "
                        "could parse from the unified diff."
                    ),
                    severity=Severity.ERROR,
                    disposition=Disposition.DENY,
                    evidence=(
                        f"changed_files={len(changed_files)}, parsed_file_diffs={len(parsed_diffs)}"
                    ),
                    recommendation=(
                        "Re-run with a standard Git diff. Review binary, submodule, rename, "
                        "or unusual path changes before accepting the patch."
                    ),
                    tags=("git", "integrity", "parser"),
                )
            )
        diffs = align_file_diffs(parsed_diffs, changed_files)
        relative_config = _relative_config_path(request.config_path)
        if relative_config is not None:
            before = repo.file_bytes_at(base_sha, relative_config)
            after = repo.file_bytes_at(head_sha, relative_config)
            if before != after:
                findings.append(
                    Finding(
                        rule_id="PL-POLICY-001",
                        title="PatchLab policy changed",
                        message=f"{relative_config} differs between the base and candidate revisions.",
                        severity=Severity.WARNING,
                        disposition=Disposition.REVIEW,
                        file=relative_config,
                        recommendation=(
                            "Review the policy change independently. Keep CI "
                            "configured to load policy from the base revision."
                        ),
                        tags=("policy", "self-modification"),
                    )
                )

        context = CheckContext(
            config=config,
            repo=repo,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_files=tuple(changed_files),
            diffs=tuple(diffs),
        )
        findings.extend(run_checks(context))

        command_results, execution_findings, executor = self._run_commands(
            repo, config, execution, base_sha, head_sha
        )
        findings.extend(execution_findings)
        for result in command_results:
            if result.required and not result.passed:
                detail = result.stderr.strip() or result.stdout.strip() or "No command output."
                findings.append(
                    Finding(
                        rule_id="PL-CMD-001",
                        title="Required verification command failed",
                        message=f"{result.name} did not meet its expected exit policy on {result.phase}.",
                        severity=Severity.ERROR,
                        disposition=Disposition.DENY,
                        evidence=detail[-1000:],
                        recommendation=(
                            "Reproduce the command locally and correct either the "
                            "patch or the explicit expectation."
                        ),
                        tags=("command", "evidence"),
                    )
                )
            elif not result.required and not result.passed:
                findings.append(
                    Finding(
                        rule_id="PL-CMD-002",
                        title="Optional verification command failed",
                        message=(
                            f"Optional command {result.name} did not meet its expected "
                            f"exit policy on {result.phase}."
                        ),
                        severity=Severity.WARNING,
                        disposition=Disposition.REVIEW,
                        evidence=(result.stderr.strip() or result.stdout.strip())[-1000:],
                        recommendation="Review the command output before accepting the patch.",
                        tags=("command", "evidence"),
                    )
                )

        effective_fail_on_review = (
            config.policy.fail_on_review
            if request.fail_on_review is None
            else request.fail_on_review
        )
        outcome = _outcome(findings, effective_fail_on_review)
        summary = {
            "changed_files": len(changed_files),
            "commands": len(command_results),
            "commands_passed": sum(1 for item in command_results if item.passed),
            "findings": len(findings),
            "blocking_findings": sum(1 for item in findings if item.blocking),
            "review_findings": sum(1 for item in findings if item.requires_review),
        }
        generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        report = VerificationReport(
            schema_version="1.1.0",
            tool_version=__version__,
            project_name=config.project_name,
            generated_at=generated_at,
            repository=repo.repository_display(),
            base_ref=request.base_ref,
            base_sha=base_sha,
            head_ref=request.head_ref,
            head_sha=head_sha,
            outcome=outcome,
            summary=summary,
            changed_files=changed_files,
            command_results=command_results,
            findings=findings,
            metadata={
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "base_commit": _public_commit_metadata(repo.commit_metadata(base_sha)),
                "head_commit": _public_commit_metadata(repo.commit_metadata(head_sha)),
                "human_review_required": config.policy.require_human_review,
                "fail_on_review": effective_fail_on_review,
                "environment": "github-actions"
                if os.environ.get("GITHUB_ACTIONS") == "true"
                else "local",
                "config_source": request.config_source,
                "config_location": config_location,
                "config_sha256": config_digest,
                "execution_mode": executor.mode,
                "execution_boundary": (
                    "isolated-container"
                    if executor.mode == "container"
                    else "weak-native"
                    if executor.mode == "native"
                    else "static-no-execution"
                ),
                "container_runtime": executor.runtime_name,
                "container_image": executor.container_image,
                "network_enabled": executor.network,
                "unsafe_native_accepted": (
                    executor.mode == "native" and execution.allow_unsafe_native
                ),
            },
        )

        output_dir = resolve_output_directory(repo.path, request.output_dir)
        report_paths = write_report_files(report, output_dir)
        passport = create_passport_bundle(
            output_dir,
            {
                "project": config.project_name,
                "repository": report.repository,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "outcome": outcome.value,
                "generated_at": generated_at,
                "tool_version": __version__,
                "config_source": request.config_source,
                "config_sha256": config_digest,
                "execution_mode": executor.mode,
                "execution_boundary": (
                    "isolated-container"
                    if executor.mode == "container"
                    else "weak-native"
                    if executor.mode == "native"
                    else "static-no-execution"
                ),
                "container_runtime": executor.runtime_name,
                "container_image": executor.container_image,
                "network_enabled": executor.network,
                "unsafe_native_accepted": (
                    executor.mode == "native" and execution.allow_unsafe_native
                ),
            },
        )
        artifacts = {key: str(path) for key, path in report_paths.items()}
        artifacts.update(passport)
        return VerificationResult(report=report, artifacts=artifacts)

    def _run_commands(
        self,
        repo: GitRepo,
        config: PatchLabConfig,
        execution: ExecutionConfig,
        base_sha: str,
        head_sha: str,
    ) -> tuple[list[Any], list[Finding], ExecutorSelection]:
        if not config.commands:
            return [], [], ExecutorSelection(mode="static")

        findings: list[Finding] = []
        try:
            executor = select_executor(execution, untrusted_root=repo.untrusted_root)
        except ExecutionUnavailable as exc:
            findings.append(
                Finding(
                    rule_id="PL-EXEC-001",
                    title="Safe command executor is unavailable",
                    message=str(exc),
                    severity=Severity.ERROR,
                    disposition=Disposition.DENY,
                    recommendation=(
                        "Use static mode, configure a digest-pinned container image, "
                        "or explicitly acknowledge the weak native boundary for local use."
                    ),
                    tags=("execution", "sandbox", "trust-boundary"),
                )
            )
            return [], findings, ExecutorSelection(mode="static")

        if executor.mode == "static":
            findings.append(
                Finding(
                    rule_id="PL-EXEC-002",
                    title="Verification commands were not executed",
                    message=(
                        "Static mode inspected the patch without running project code. "
                        "Configured reproduction and test commands remain unverified."
                    ),
                    severity=Severity.WARNING,
                    disposition=Disposition.REVIEW,
                    recommendation=(
                        "Run with a digest-pinned container image when dynamic evidence is required."
                    ),
                    tags=("execution", "static-analysis", "evidence"),
                )
            )
            return [], findings, executor

        if executor.mode == "container" and executor.network:
            findings.append(
                Finding(
                    rule_id="PL-EXEC-003",
                    title="Isolated commands have network access",
                    message=(
                        "The trusted policy explicitly enabled network access inside the "
                        "command container. Network responses can affect reproducibility."
                    ),
                    severity=Severity.WARNING,
                    disposition=Disposition.REVIEW,
                    recommendation="Disable execution.network unless the test requires it.",
                    tags=("execution", "network", "reproducibility"),
                )
            )

        need_base = any(item.run_on in {"base", "both"} for item in config.commands)
        need_head = any(item.run_on in {"head", "both"} for item in config.commands)
        results = []
        with ExitStack() as stack:
            base_path = stack.enter_context(repo.snapshot(base_sha, "base")) if need_base else None
            head_path = stack.enter_context(repo.snapshot(head_sha, "head")) if need_head else None
            for command in config.commands:
                phases = ("base", "head") if command.run_on == "both" else (command.run_on,)
                for phase in phases:
                    cwd = base_path if phase == "base" else head_path
                    if cwd is None:
                        raise RuntimeError(f"internal error: no snapshot for {phase}")
                    try:
                        results.append(run_command(command, phase, cwd, executor))
                    except ExecutionUnavailable as exc:
                        findings.append(
                            Finding(
                                rule_id="PL-EXEC-001",
                                title="Safe command executor became unavailable",
                                message=str(exc),
                                severity=Severity.ERROR,
                                disposition=Disposition.DENY,
                                recommendation=(
                                    "Correct the isolated executor configuration and rerun the verification."
                                ),
                                tags=("execution", "sandbox", "trust-boundary"),
                            )
                        )
                        return results, findings, executor
        return results, findings, executor


def _effective_execution(
    configured: ExecutionConfig,
    request: VerificationRequest,
) -> ExecutionConfig:
    updates: dict[str, Any] = {}
    if request.execution_mode is not None and request.execution_mode not in {
        "auto",
        "static",
        "container",
        "native",
    }:
        raise ConfigError("execution mode override is invalid")
    if request.container_runtime is not None and request.container_runtime not in {
        "auto",
        "docker",
        "podman",
    }:
        raise ConfigError("container runtime override is invalid")
    if request.network is not None and not isinstance(request.network, bool):
        raise ConfigError("network override must be a boolean")
    if request.allow_unsafe_native is not None and not isinstance(
        request.allow_unsafe_native, bool
    ):
        raise ConfigError("unsafe native override must be a boolean")
    if request.execution_mode is not None:
        updates["mode"] = request.execution_mode
    if request.container_runtime is not None:
        updates["container_runtime"] = request.container_runtime
    if request.container_image is not None:
        image = request.container_image.strip()
        if image and not is_pinned_container_image(image):
            raise ConfigError(
                "container image overrides must use an immutable @sha256 digest or image ID"
            )
        updates["container_image"] = image
    if request.network is not None:
        updates["network"] = request.network
    if request.allow_unsafe_native is not None:
        updates["allow_unsafe_native"] = request.allow_unsafe_native
    return replace(configured, **updates)


def _load_config(
    repo: GitRepo,
    config_path: Path,
    source: str,
    base_sha: str,
    head_sha: str,
) -> tuple[PatchLabConfig, str, str]:
    if source not in {"base", "head", "working-tree"}:
        raise ConfigError("config source must be base, head, or working-tree")
    if source == "working-tree":
        actual = _trusted_working_tree_config(repo.path, config_path)
        try:
            text = actual.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigError(f"configuration file not found: {actual}") from exc
        except UnicodeDecodeError as exc:
            raise ConfigError(f"configuration file is not valid UTF-8: {actual}") from exc
        return load_config_text(text, source=str(actual)), text, str(actual)

    relative = _relative_config_path(config_path)
    if relative is None:
        raise ConfigError("a base or head configuration path must be relative to the repository")
    ref = base_sha if source == "base" else head_sha
    config_text = repo.utf8_file_at(ref, relative)
    if config_text is None:
        raise ConfigError(f"configuration file not found at {source}:{relative}")
    return (
        load_config_text(config_text, source=f"{source}:{relative}"),
        config_text,
        f"{source}:{relative}",
    )


def _relative_config_path(path: Path) -> str | None:
    if path.is_absolute():
        return None
    normalized = PurePosixPath(path.as_posix())
    if not normalized.parts or ".." in normalized.parts:
        raise ConfigError("configuration path must stay inside the repository")
    return normalized.as_posix()


def _trusted_working_tree_config(root: Path, config_path: Path) -> Path:
    repository = root.resolve()
    candidate = config_path if config_path.is_absolute() else repository / config_path
    lexical = Path(os.path.abspath(candidate))
    try:
        relative = lexical.relative_to(repository)
    except ValueError as exc:
        raise ConfigError("working-tree configuration must stay inside the repository") from exc
    current = repository
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ConfigError("working-tree configuration path must not contain symbolic links")
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError:
        return lexical
    try:
        resolved.relative_to(repository)
    except ValueError as exc:
        raise ConfigError("working-tree configuration must stay inside the repository") from exc
    if not resolved.is_file():
        raise ConfigError(f"configuration path is not a regular file: {resolved}")
    return resolved


def _outcome(findings: list[Finding], fail_on_review: bool) -> Outcome:
    if any(item.blocking for item in findings):
        return Outcome.FAIL
    if any(item.requires_review for item in findings):
        return Outcome.FAIL if fail_on_review else Outcome.NEEDS_REVIEW
    return Outcome.PASS


def _public_commit_metadata(data: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in data.items() if key != "author_email"}
