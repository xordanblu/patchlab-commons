from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchlab_commons.engine import VerificationEngine, VerificationRequest
from patchlab_commons.models import Outcome
from patchlab_commons.passport import verify_passport_bundle

from tests.helpers import commit_all, init_repo


SAFE_CONFIG = """
[project]
name = "demo-calculator"

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
name = "regression"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 30
required = true

[[commands]]
name = "all-tests"
command = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 30
required = true
"""


class IntegrationTests(unittest.TestCase):
    def create_safe_patch(self) -> tuple[Path, str, str]:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "tests").mkdir()
        (repo / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (repo / "tests" / "test_regression.py").write_text(
            "import unittest\nfrom calc import add\n\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )
        (repo / "patchlab.toml").write_text(SAFE_CONFIG, encoding="utf-8")
        base = commit_all(repo, "add reproducible bug")
        (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        head = commit_all(repo, "fix addition")
        return repo, base, head

    def test_safe_patch_passes_and_bundle_verifies(self) -> None:
        repo, base, head = self.create_safe_patch()
        result = VerificationEngine().verify(
            VerificationRequest(
                repository=repo,
                config_path=Path("patchlab.toml"),
                base_ref=base,
                head_ref=head,
                output_dir=Path(".patchlab/out"),
            )
        )
        self.assertEqual(result.report.outcome, Outcome.PASS)
        self.assertEqual(result.report.summary["commands_passed"], 3)
        valid, detail = verify_passport_bundle(result.artifacts["bundle"])
        self.assertTrue(valid, detail)

    def test_diff_metadata_mismatch_is_blocking(self) -> None:
        repo, base, head = self.create_safe_patch()
        with patch("patchlab_commons.engine.parse_unified_diff", return_value=[]):
            result = VerificationEngine().verify(
                VerificationRequest(
                    repository=repo,
                    config_path=Path("patchlab.toml"),
                    base_ref=base,
                    head_ref=head,
                    output_dir=Path(".patchlab/out"),
                )
            )
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        finding = next(item for item in result.report.findings if item.rule_id == "PL-GIT-003")
        self.assertEqual(finding.disposition.value, "deny")

    def test_privileged_workflow_fails(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / ".github" / "workflows" / "ci.yml").write_text(
            "name: CI\non: [push]\npermissions:\n  contents: read\n",
            encoding="utf-8",
        )
        (repo / "patchlab.toml").write_text(
            SAFE_CONFIG.split("[[commands]]", 1)[0],
            encoding="utf-8",
        )
        base = commit_all(repo, "safe workflow")
        (repo / ".github" / "workflows" / "ci.yml").write_text(
            "name: CI\non:\n  pull_request_target:\npermissions:\n  contents: write\n",
            encoding="utf-8",
        )
        head = commit_all(repo, "increase workflow permissions")
        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        ids = {item.rule_id for item in result.report.findings}
        self.assertIn("PL-GHA-002", ids)
        self.assertIn("PL-GHA-003", ids)

    def test_new_checkout_must_disable_persisted_credentials(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        workflow = repo / ".github" / "workflows" / "ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: CI\non: [push]\njobs: {}\n", encoding="utf-8")
        (repo / "patchlab.toml").write_text(
            SAFE_CONFIG.split("[[commands]]", 1)[0],
            encoding="utf-8",
        )
        base = commit_all(repo, "base")
        workflow.write_text(
            """name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@1111111111111111111111111111111111111111
      - run: echo ok
""",
            encoding="utf-8",
        )
        head = commit_all(repo, "add checkout")

        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        findings = [item for item in result.report.findings if item.rule_id == "PL-GHA-004"]
        self.assertEqual(len(findings), 1)
        self.assertIn("by default", findings[0].title)
        self.assertEqual(result.report.outcome, Outcome.FAIL)

    def test_candidate_cannot_weaken_base_policy(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / ".github" / "workflows" / "ci.yml").write_text(
            "name: CI\non: [push]\npermissions:\n  contents: read\n",
            encoding="utf-8",
        )
        trusted = SAFE_CONFIG.split("[[commands]]", 1)[0]
        (repo / "patchlab.toml").write_text(trusted, encoding="utf-8")
        base = commit_all(repo, "trusted policy")

        weakened = trusted.replace('dangerous_permissions = "deny"', 'dangerous_permissions = "allow"')
        weakened = weakened.replace('workflow_changes = "review"', 'workflow_changes = "allow"')
        (repo / "patchlab.toml").write_text(weakened, encoding="utf-8")
        (repo / ".github" / "workflows" / "ci.yml").write_text(
            "name: CI\non: [push]\npermissions:\n  contents: write\n",
            encoding="utf-8",
        )
        head = commit_all(repo, "weaken policy and add write access")

        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        self.assertEqual(result.report.metadata["config_source"], "base")
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        ids = {item.rule_id for item in result.report.findings}
        self.assertIn("PL-POLICY-001", ids)
        self.assertIn("PL-GHA-002", ids)

    def test_optional_command_can_require_review_or_fail_strictly(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        config = SAFE_CONFIG.split("[[commands]]", 1)[0] + """
[[commands]]
name = "optional-check"
command = ["python", "-c", "raise SystemExit(7)"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 30
required = false
"""
        (repo / "patchlab.toml").write_text(config, encoding="utf-8")
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "file.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")

        review = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out/review"))
        )
        strict = VerificationEngine().verify(
            VerificationRequest(
                repo,
                Path("patchlab.toml"),
                base,
                head,
                Path("out/strict"),
                fail_on_review=True,
            )
        )
        self.assertEqual(review.report.outcome, Outcome.NEEDS_REVIEW)
        self.assertEqual(strict.report.outcome, Outcome.FAIL)
        self.assertIn("PL-CMD-002", {item.rule_id for item in review.report.findings})

    def test_required_clean_worktree_blocks_uncommitted_files(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        config = SAFE_CONFIG.split("[[commands]]", 1)[0].replace(
            "require_clean_worktree = false",
            "require_clean_worktree = true",
        )
        (repo / "patchlab.toml").write_text(config, encoding="utf-8")
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "file.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")
        (repo / "uncommitted.txt").write_text("not in comparison\n", encoding="utf-8")

        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        self.assertIn("PL-GIT-002", {item.rule_id for item in result.report.findings})

    def test_test_weakening_with_spaced_filename_is_attributed_correctly(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        test_file = repo / "tests" / "test spaced.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "def test_value():\n    assert 1 == 1\n",
            encoding="utf-8",
        )
        (repo / "patchlab.toml").write_text(
            SAFE_CONFIG.split("[[commands]]", 1)[0],
            encoding="utf-8",
        )
        base = commit_all(repo, "add test with spaced name")
        test_file.write_text("def test_value():\n    return None\n", encoding="utf-8")
        head = commit_all(repo, "remove assertion")

        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        finding = next(item for item in result.report.findings if item.rule_id == "PL-TEST-002")
        self.assertEqual(finding.file, "tests/test spaced.py")
        self.assertEqual(result.report.outcome, Outcome.FAIL)

    def test_repository_symlink_cannot_redirect_output(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "patchlab.toml").write_text(
            SAFE_CONFIG.split("[[commands]]", 1)[0],
            encoding="utf-8",
        )
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "file.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")
        outside = Path(tempfile.mkdtemp())
        try:
            (repo / ".patchlab").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symbolic links are unavailable: {exc}")

        with self.assertRaises(OSError):
            VerificationEngine().verify(
                VerificationRequest(
                    repo,
                    Path("patchlab.toml"),
                    base,
                    head,
                    Path(".patchlab/out"),
                )
            )
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
