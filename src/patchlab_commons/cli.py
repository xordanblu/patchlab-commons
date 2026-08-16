from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ._version import __version__
from .config import ConfigError, DEFAULT_CONFIG
from .doctor import run_doctor
from .engine import VerificationEngine, VerificationRequest
from .gitutils import GitError
from .models import Outcome
from .passport import verify_passport_bundle
from .reporting import pretty_json
from .schema import passport_schema, report_schema

_WORKFLOW = """name: PatchLab Passport

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
      # Add the target project's dependency setup here when its tests need it.
      - name: Create Patch Passport
        id: patchlab
        uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          config: patchlab.toml
          config-source: base
          output: .patchlab/out
          fail-on-review: "true"
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always()
        with:
          name: patchlab-passport
          path: .patchlab/out/
          if-no-files-found: error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchlab",
        description="Create evidence-first Patch Passports for software changes.",
    )
    parser.add_argument("--version", action="version", version=f"PatchLab Commons {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create patchlab.toml and an optional GitHub workflow")
    init.add_argument("--directory", type=Path, default=Path.cwd())
    init.add_argument("--github", action=argparse.BooleanOptionalAction, default=True)
    init.add_argument("--force", action="store_true")

    verify = subparsers.add_parser("verify", help="compare two Git refs and create a Patch Passport")
    verify.add_argument("--repo", type=Path, default=Path.cwd())
    verify.add_argument("--config", type=Path, default=Path("patchlab.toml"))
    verify.add_argument(
        "--config-source",
        choices=("base", "head", "working-tree"),
        default="base",
        help="trusted revision that supplies patchlab.toml (default: base)",
    )
    verify.add_argument("--base", required=True)
    verify.add_argument("--head", required=True)
    verify.add_argument("--output", type=Path, default=Path(".patchlab/out"))
    verify.add_argument(
        "--execution-mode",
        choices=("auto", "static", "container", "native"),
        help="override the trusted execution mode",
    )
    verify.add_argument(
        "--container-runtime",
        choices=("auto", "docker", "podman"),
        help="override the container runtime",
    )
    verify.add_argument(
        "--container-image",
        help="digest-pinned image, for example name@sha256:<64 hex characters>",
    )
    verify.add_argument(
        "--network",
        dest="network",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="allow or deny network access inside the command container",
    )
    verify.add_argument(
        "--allow-unsafe-native",
        dest="allow_unsafe_native",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="explicitly accept the weak native command boundary",
    )
    review = verify.add_mutually_exclusive_group()
    review.add_argument("--fail-on-review", dest="fail_on_review", action="store_true")
    review.add_argument("--allow-review", dest="fail_on_review", action="store_false")
    verify.set_defaults(fail_on_review=None)

    doctor = subparsers.add_parser("doctor", help="check the local PatchLab environment")
    doctor.add_argument("--repo", type=Path, default=Path.cwd())
    doctor.add_argument("--config", type=Path, default=Path("patchlab.toml"))
    doctor.add_argument("--json", action="store_true")

    passport = subparsers.add_parser("verify-passport", help="verify a Patch Passport bundle")
    passport.add_argument("bundle", type=Path)
    passport.add_argument("--json", action="store_true")

    schema = subparsers.add_parser("schema", help="print the Patch Passport JSON schema")
    schema.add_argument(
        "--kind",
        choices=("report", "passport"),
        default="report",
        help="schema to print (default: report)",
    )
    schema.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "verify":
            return _verify(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "verify-passport":
            return _verify_passport(args)
        if args.command == "schema":
            return _schema(args)
    except (ConfigError, GitError, OSError, RuntimeError, ValueError) as exc:
        print(f"patchlab: {exc}", file=sys.stderr)
        return 1
    return 64


def _init(args: argparse.Namespace) -> int:
    directory: Path = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "patchlab.toml"
    _write_new(config_path, DEFAULT_CONFIG, args.force)
    created = [config_path]
    if args.github:
        workflow = directory / ".github" / "workflows" / "patchlab.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        _write_new(workflow, _WORKFLOW, args.force)
        created.append(workflow)
    for path in created:
        print(f"created {path}")
    return 0


def _write_new(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; use --force to replace it")
    path.write_text(content, encoding="utf-8")


def _verify(args: argparse.Namespace) -> int:
    result = VerificationEngine().verify(
        VerificationRequest(
            repository=args.repo,
            config_path=args.config,
            base_ref=args.base,
            head_ref=args.head,
            output_dir=args.output,
            fail_on_review=args.fail_on_review,
            config_source=args.config_source,
            execution_mode=args.execution_mode,
            container_runtime=args.container_runtime,
            container_image=args.container_image,
            network=args.network,
            allow_unsafe_native=args.allow_unsafe_native,
        )
    )
    report = result.report
    if report.metadata.get("execution_boundary") == "weak-native":
        print(
            "WARNING: project code ran with the weak native boundary; it was not OS-isolated.",
            file=sys.stderr,
        )
    print(f"PatchLab outcome: {report.outcome.value}")
    print(f"Changed files: {report.summary['changed_files']}")
    print(f"Commands: {report.summary['commands_passed']}/{report.summary['commands']} passed")
    print(f"Findings: {report.summary['findings']} ({report.summary['blocking_findings']} blocking)")
    print(f"Passport: {result.artifacts['bundle']}")
    print(f"SHA-256: {result.artifacts['bundle_sha256']}")
    if report.outcome is Outcome.FAIL:
        return 1
    return 0


def _doctor(args: argparse.Namespace) -> int:
    checks = run_doctor(args.repo, args.config)
    if args.json:
        print(pretty_json([item.to_dict() for item in checks]), end="")
    else:
        for item in checks:
            marker = "PASS" if item.ok else "FAIL"
            print(f"[{marker}] {item.name}: {item.detail}")
    return 0 if all(item.ok for item in checks if item.name != "working-tree") else 1


def _verify_passport(args: argparse.Namespace) -> int:
    valid, detail = verify_passport_bundle(args.bundle)
    if args.json:
        print(pretty_json(detail), end="")
    else:
        print("VALID" if valid else "INVALID")
        print(f"Bundle: {args.bundle}")
        if detail.get("bundle_sha256"):
            print(f"SHA-256: {detail['bundle_sha256']}")
        if detail.get("error"):
            print(f"Error: {detail['error']}")
    return 0 if valid else 1


def _schema(args: argparse.Namespace) -> int:
    selected = report_schema() if args.kind == "report" else passport_schema()
    rendered = pretty_json(selected)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"created {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
