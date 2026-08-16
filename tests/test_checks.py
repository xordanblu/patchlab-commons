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


class CheckTests(unittest.TestCase):
    def context(
        self,
        diff: str,
        files: list[ChangedFile],
        policy: PolicyConfig | None = None,
    ) -> CheckContext:
        root = Path(tempfile.mkdtemp()) / "repo"
        init_repo(root)
        (root / "seed.txt").write_text("seed\n", encoding="utf-8")
        sha = commit_all(root, "seed")
        return CheckContext(
            config=PatchLabConfig(
                project_name="test",
                scope=ScopeConfig(allow=("**",)),
                policy=policy or PolicyConfig(),
            ),
            repo=GitRepo(root),
            base_sha=sha,
            head_sha=sha,
            changed_files=tuple(files),
            diffs=tuple(parse_unified_diff(diff)),
        )

    def test_detects_write_permission(self) -> None:
        diff = """diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1,3 @@
 name: CI
+permissions:
+  contents: write
"""
        files = [ChangedFile("M", ".github/workflows/ci.yml", added_lines=2, deleted_lines=0)]
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-GHA-002", ids)

    def test_detects_inline_write_permission(self) -> None:
        diff = """diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1,2 @@
 name: CI
+permissions: { contents: write }
"""
        files = [ChangedFile("M", ".github/workflows/ci.yml", added_lines=1, deleted_lines=0)]
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-GHA-002", ids)

    def test_detects_unpinned_action(self) -> None:
        diff = """diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1,2 @@
 steps:
+  - uses: vendor/action@v2
"""
        files = [ChangedFile("M", ".github/workflows/ci.yml", added_lines=1, deleted_lines=0)]
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-GHA-007", ids)

    def test_detects_possible_secret_logging(self) -> None:
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 pass
+print(api_key)
"""
        files = [ChangedFile("M", "app.py", added_lines=1, deleted_lines=0)]
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-SECRET-003", ids)

    def test_detects_network_capability(self) -> None:
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 pass
+requests.post("https://example.invalid")
"""
        files = [ChangedFile("M", "app.py", added_lines=1, deleted_lines=0)]
        ids = {item.rule_id for item in run_checks(self.context(diff, files))}
        self.assertIn("PL-NET-001", ids)

    def test_detects_test_assertion_removal(self) -> None:
        diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1 +1 @@
-assert result == 1
+print(result)
"""
        files = [ChangedFile("M", "tests/test_app.py", added_lines=1, deleted_lines=1)]
        findings = run_checks(self.context(diff, files))
        finding = next(item for item in findings if item.rule_id == "PL-TEST-002")
        self.assertEqual(finding.disposition, Disposition.DENY)

    def test_detects_scope_violation(self) -> None:
        root = Path(tempfile.mkdtemp()) / "repo"
        init_repo(root)
        (root / "seed.txt").write_text("seed", encoding="utf-8")
        sha = commit_all(root, "seed")
        context = CheckContext(
            config=PatchLabConfig(
                project_name="test",
                scope=ScopeConfig(allow=("src/**",), deny=("src/private/**",)),
            ),
            repo=GitRepo(root),
            base_sha=sha,
            head_sha=sha,
            changed_files=(ChangedFile("A", "docs/readme.md", added_lines=2, deleted_lines=0),),
            diffs=(),
        )
        ids = {item.rule_id for item in run_checks(context)}
        self.assertIn("PL-SCOPE-004", ids)


if __name__ == "__main__":
    unittest.main()
