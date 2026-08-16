from __future__ import annotations

import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from patchlab.gitutils import GitRepo, _public_repository_identifier

from tests.helpers import commit_all, git, init_repo


class GitUtilsTests(unittest.TestCase):
    def test_changed_files_preserves_spaces_in_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            target = repo / "file name.py"
            target.write_text("print('one')\n", encoding="utf-8")
            base = commit_all(repo, "base")

            target.write_text("print('one')\nprint('two')\n", encoding="utf-8")
            head = commit_all(repo, "head")

            changed = GitRepo(repo).changed_files(base, head)

            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0].path, "file name.py")
            self.assertEqual(changed[0].status, "M")
            self.assertEqual(changed[0].added_lines, 1)
            self.assertEqual(changed[0].deleted_lines, 0)
            self.assertFalse(changed[0].binary)

    def test_changed_files_reports_rename_with_old_and_new_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            old_path = repo / "old name.txt"
            old_path.write_text("same content\n", encoding="utf-8")
            base = commit_all(repo, "base")

            git(repo, "mv", "old name.txt", "new name.txt")
            head = commit_all(repo, "rename")

            changed = GitRepo(repo).changed_files(base, head)

            self.assertEqual(len(changed), 1)
            self.assertTrue(changed[0].status.startswith("R"))
            self.assertEqual(changed[0].old_path, "old name.txt")
            self.assertEqual(changed[0].path, "new name.txt")
            self.assertEqual(changed[0].added_lines, 0)
            self.assertEqual(changed[0].deleted_lines, 0)

    def test_changed_files_marks_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            target = repo / "fixture.bin"
            target.write_bytes(b"\x00\x01\x02")
            base = commit_all(repo, "base")

            target.write_bytes(b"\x00\x01\x03\x04")
            head = commit_all(repo, "binary")

            changed = GitRepo(repo).changed_files(base, head)

            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0].path, "fixture.bin")
            self.assertTrue(changed[0].binary)
            self.assertIsNone(changed[0].added_lines)
            self.assertIsNone(changed[0].deleted_lines)

    def test_repository_identifier_removes_https_credentials(self) -> None:
        value = _public_repository_identifier(
            "https://user:very-secret-token@github.com/example/project.git?token=hidden"
        )
        self.assertEqual(value, "https://github.com/example/project.git")
        self.assertNotIn("secret", value)
        self.assertNotIn("hidden", value)

    def test_repository_identifier_normalizes_scp_remote(self) -> None:
        value = _public_repository_identifier("git@github.com:example/project.git")
        self.assertEqual(value, "github.com/example/project.git")

    def test_repository_identifier_hides_local_parent_path(self) -> None:
        value = _public_repository_identifier("/private/home/user/project")
        self.assertEqual(value, "project")

    def test_file_at_distinguishes_empty_file_from_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            (repo / "empty.txt").write_text("", encoding="utf-8")
            sha = commit_all(repo, "empty")
            adapter = GitRepo(repo)
            self.assertEqual(adapter.file_at(sha, "empty.txt"), "")
            self.assertIsNone(adapter.file_at(sha, "missing.txt"))

    def test_repository_identifier_tolerates_invalid_port(self) -> None:
        value = _public_repository_identifier("https://user:secret@example.com:notaport/project.git")
        self.assertEqual(value, "https://example.com/project.git")

    def test_worktree_add_does_not_execute_repository_hooks(self) -> None:
        if os.name == "nt":
            self.skipTest("executable hook test is POSIX-only")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            (repo / "file.txt").write_text("safe\n", encoding="utf-8")
            sha = commit_all(repo, "base")
            marker = Path(temp) / "hook-ran"
            hook = repo / ".git" / "hooks" / "post-checkout"
            hook.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\n", encoding="utf-8")
            hook.chmod(0o755)

            with GitRepo(repo).worktree(sha, "hook-test") as checkout:
                self.assertTrue((checkout / "file.txt").is_file())

            self.assertFalse(marker.exists())

    def test_unified_diff_does_not_execute_textconv_filter(self) -> None:
        if os.name == "nt":
            self.skipTest("executable textconv test is POSIX-only")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            marker = Path(temp) / "textconv-ran"
            converter = Path(temp) / "convert.sh"
            converter.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\ncat \"$1\"\n", encoding="utf-8")
            converter.chmod(0o755)
            git(repo, "config", "diff.patchlab-test.textconv", str(converter))
            (repo / ".gitattributes").write_text("*.demo diff=patchlab-test\n", encoding="utf-8")
            target = repo / "sample.demo"
            target.write_text("base\n", encoding="utf-8")
            base = commit_all(repo, "base")
            target.write_text("head\n", encoding="utf-8")
            head = commit_all(repo, "head")

            diff = GitRepo(repo).unified_diff(base, head)

            self.assertIn("-base", diff)
            self.assertIn("+head", diff)
            self.assertFalse(marker.exists())

    def test_git_output_limit_blocks_oversized_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            target = repo / "large.txt"
            target.write_text("base\n", encoding="utf-8")
            base = commit_all(repo, "base")
            target.write_text("head-" + ("x" * 512) + "\n", encoding="utf-8")
            head = commit_all(repo, "head")
            adapter = GitRepo(repo)

            with patch("patchlab.gitutils._MAX_GIT_OUTPUT_BYTES", 64):
                with self.assertRaisesRegex(RuntimeError, "safety limit"):
                    adapter.unified_diff(base, head)


if __name__ == "__main__":
    unittest.main()
