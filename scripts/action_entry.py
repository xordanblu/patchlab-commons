#!/usr/bin/env python3
"""Trusted entry point for the PatchLab composite GitHub Action.

The script must run with ``python -I`` from the action directory. It imports
PatchLab only from this action's own ``src`` directory and never installs or
imports code from the caller workspace during bootstrap.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid

_ACTION_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = (_ACTION_ROOT / "src").resolve()


def _bootstrap() -> None:
    if not sys.flags.isolated or not sys.flags.safe_path or not sys.flags.no_site:
        raise RuntimeError("the GitHub Action entry point requires Python isolated no-site mode (-I -S)")
    if not (_SOURCE_ROOT / "patchlab_commons" / "__init__.py").is_file():
        raise RuntimeError("trusted PatchLab source tree is incomplete")
    sys.path.insert(0, os.fspath(_SOURCE_ROOT))
    for name in tuple(sys.modules):
        if name == "patchlab_commons" or name.startswith("patchlab_commons."):
            del sys.modules[name]


_bootstrap()

from patchlab_commons.engine import VerificationEngine, VerificationRequest  # noqa: E402
from patchlab_commons.models import Outcome  # noqa: E402
from patchlab_commons.passport import sha256_file, verify_passport_bundle  # noqa: E402
import patchlab_commons as _trusted_package  # noqa: E402

if not Path(_trusted_package.__file__).resolve().is_relative_to(_SOURCE_ROOT):
    raise RuntimeError("PatchLab was not imported from the trusted action source tree")


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"required action environment variable is missing: {name}")
    return value


def _choice(name: str, choices: set[str], default: str) -> str:
    value = os.environ.get(name, default)
    if value not in choices:
        rendered = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {rendered}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"{name} must be true or false")


def _inside(root: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside GITHUB_WORKSPACE") from exc
    return resolved


def _emit(path: Path, name: str, value: str) -> None:
    delimiter = f"patchlab_{uuid.uuid4().hex}"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def _write_summary(result: object, digest: str) -> None:
    summary_raw = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_raw:
        return
    report = result.report  # type: ignore[attr-defined]
    summary_path = Path(summary_raw)
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("## PatchLab Passport\n\n")
        handle.write(f"- Outcome: `{report.outcome.value}`\n")
        handle.write(f"- Changed files: `{report.summary['changed_files']}`\n")
        handle.write(
            f"- Commands: `{report.summary['commands_passed']}/{report.summary['commands']}` passed\n"
        )
        handle.write(f"- Findings: `{report.summary['findings']}`\n")
        handle.write(f"- Blocking findings: `{report.summary['blocking_findings']}`\n")
        handle.write(f"- Bundle SHA-256: `{digest}`\n")
        handle.write(
            f"- Execution boundary: `{report.metadata['execution_boundary']}`\n"
        )


def main() -> int:
    workspace = Path(_required("GITHUB_WORKSPACE")).resolve()
    repository_input = Path(os.environ.get("PATCHLAB_REPOSITORY", "."))
    repository = _inside(
        workspace,
        repository_input if repository_input.is_absolute() else workspace / repository_input,
        "repository",
    )

    # A local action inside the candidate repository is mutable by that
    # repository. Published actions live outside GITHUB_WORKSPACE. Refuse the
    # unsafe layout rather than claiming a trusted bootstrap.
    try:
        _ACTION_ROOT.relative_to(repository)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "the PatchLab Action must be loaded from a separately checked-out or published action; "
            "uses: ./ is not safe for untrusted pull requests"
        )

    config_source = _choice(
        "PATCHLAB_CONFIG_SOURCE", {"base", "head", "working-tree"}, "base"
    )
    config_input = Path(os.environ.get("PATCHLAB_CONFIG", "patchlab.toml"))
    if config_source == "working-tree":
        config_path = _inside(
            repository,
            config_input if config_input.is_absolute() else repository / config_input,
            "working-tree configuration",
        )
    else:
        if config_input.is_absolute():
            raise ValueError("base or head configuration must be relative to the repository")
        config_path = config_input
    output_input = Path(os.environ.get("PATCHLAB_OUTPUT", ".patchlab/out"))
    output_dir = _inside(
        repository,
        output_input if output_input.is_absolute() else repository / output_input,
        "output directory",
    )
    execution_mode = _choice(
        "PATCHLAB_EXECUTION_MODE", {"auto", "static", "container"}, "static"
    )
    container_runtime = _choice(
        "PATCHLAB_CONTAINER_RUNTIME", {"auto", "docker", "podman"}, "auto"
    )
    if execution_mode == "container" and os.name == "nt":
        raise RuntimeError("container execution is supported only on Linux hosts")

    result = VerificationEngine().verify(
        VerificationRequest(
            repository=repository,
            config_path=config_path,
            base_ref=_required("PATCHLAB_BASE"),
            head_ref=_required("PATCHLAB_HEAD"),
            output_dir=output_dir,
            fail_on_review=_boolean("PATCHLAB_FAIL_ON_REVIEW", True),
            config_source=config_source,
            execution_mode=execution_mode,
            container_runtime=container_runtime,
            container_image=os.environ.get("PATCHLAB_CONTAINER_IMAGE", ""),
            network=_boolean("PATCHLAB_NETWORK", False),
            allow_unsafe_native=False,
        )
    )

    bundle = Path(result.artifacts["bundle"])
    valid, detail = verify_passport_bundle(bundle)
    if not valid:
        raise RuntimeError(f"generated Patch Passport failed verification: {detail}")
    identity = detail.get("identity")
    if not isinstance(identity, dict) or identity.get("outcome") != result.report.outcome.value:
        raise RuntimeError("verified Patch Passport identity does not match the in-memory result")
    digest = sha256_file(bundle)
    if digest != result.artifacts["bundle_sha256"]:
        raise RuntimeError("generated Patch Passport digest changed before action output")

    output_path = Path(_required("GITHUB_OUTPUT"))
    outputs = {
        "outcome": result.report.outcome.value,
        "report": result.artifacts["json"],
        "markdown": result.artifacts["markdown"],
        "sarif": result.artifacts["sarif"],
        "passport": result.artifacts["passport"],
        "bundle": result.artifacts["bundle"],
        "bundle_sha256": digest,
        "sidecar": result.artifacts["sidecar"],
        "exit_code": "1" if result.report.outcome is Outcome.FAIL else "0",
    }
    for name, value in outputs.items():
        _emit(output_path, name, value)
    _write_summary(result, digest)
    print(f"PatchLab outcome: {result.report.outcome.value}")
    print(f"Patch Passport SHA-256: {digest}")
    return 1 if result.report.outcome is Outcome.FAIL else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"patchlab-action: {exc}", file=sys.stderr)
        raise SystemExit(1)
