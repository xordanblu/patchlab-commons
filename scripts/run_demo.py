#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from patchlab_commons.engine import VerificationEngine, VerificationRequest
from patchlab_commons.passport import verify_passport_bundle

CONFIG = """
[project]
name = "patchlab-demo-calculator"

[execution]
mode = "native"
allow_unsafe_native = true

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

[[commands]]
name = "reproduce-addition-bug"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 30
required = true

[[commands]]
name = "full-test-suite"
command = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 30
required = true
"""


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip())
    return process.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def build_demo_repo() -> tuple[Path, str, str]:
    repo = Path(tempfile.mkdtemp(prefix="patchlab-demo-repo-"))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "PatchLab Demo")
    git(repo, "config", "user.email", "demo@patchlab.invalid")
    git(repo, "remote", "add", "origin", "https://github.com/patchlab/examples.git")
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_regression.py").write_text(
        "import unittest\n"
        "from calculator import add\n\n"
        "class AdditionRegressionTest(unittest.TestCase):\n"
        "    def test_two_plus_three_is_five(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    (repo / "patchlab.toml").write_text(CONFIG, encoding="utf-8")
    base = commit(repo, "add reproducible calculator defect")
    (repo / "calculator.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    head = commit(repo, "correct calculator addition")
    return repo, base, head


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo, base, head = build_demo_repo()
    try:
        internal_output = repo / ".patchlab" / "demo"
        result = VerificationEngine().verify(
            VerificationRequest(
                repository=repo,
                config_path=Path("patchlab.toml"),
                base_ref=base,
                head_ref=head,
                output_dir=internal_output,
            )
        )
        valid, detail = verify_passport_bundle(result.artifacts["bundle"])
        if not valid:
            raise RuntimeError(f"generated passport failed verification: {detail}")

        final_output = (
            args.output.resolve() if args.output else (Path.cwd() / ".patchlab" / "demo").resolve()
        )
        if final_output.exists():
            shutil.rmtree(final_output)
        shutil.copytree(internal_output, final_output)

        print("PatchLab demo completed")
        print(f"Outcome: {result.report.outcome.value}")
        print(f"Base: {base}")
        print(f"Head: {head}")
        print(f"Output: {final_output}")
        print(f"Bundle SHA-256: {result.artifacts['bundle_sha256']}")
        return 0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
