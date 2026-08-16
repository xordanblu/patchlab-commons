from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchlab_commons.gitutils import (
    GitError,
    GitRepo,
    _git_environment,
    _parse_tree_entries,
    _validate_link_target,
    _validate_snapshot_path,
)
from tests.helpers import commit_all, init_repo


class GitSecurityTests(unittest.TestCase):
    def test_hostile_git_environment_is_not_inherited(self) -> None:
        home = Path(tempfile.mkdtemp())
        hostile = {
            "GIT_DIR": "/tmp/attacker",
            "GIT_WORK_TREE": "/tmp/attacker-worktree",
            "GIT_INDEX_FILE": "/tmp/attacker-index",
            "GIT_OBJECT_DIRECTORY": "/tmp/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternate",
            "GIT_EXTERNAL_DIFF": "/tmp/evil-diff",
            "GIT_SSH_COMMAND": "evil-ssh",
            "GIT_ASKPASS": "evil-askpass",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "alias.status",
            "GIT_CONFIG_VALUE_0": "!touch /tmp/ran",
        }
        with patch.dict(os.environ, hostile, clear=False):
            environment = _git_environment(home)
        for key in hostile:
            if key == "GIT_CONFIG_COUNT":
                self.assertEqual(environment[key], "0")
            else:
                self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

    def test_git_operations_ignore_hostile_process_environment(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "file.txt").write_text("safe\n", encoding="utf-8")
        sha = commit_all(repo, "safe")
        hostile = {
            "GIT_DIR": "/definitely/not/the/repository",
            "GIT_WORK_TREE": "/tmp/attacker",
            "GIT_INDEX_FILE": "/tmp/attacker-index",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "alias.rev-parse",
            "GIT_CONFIG_VALUE_0": "!false",
        }
        with patch.dict(os.environ, hostile, clear=False):
            adapter = GitRepo(repo)
            self.assertEqual(adapter.resolve(sha), sha)
            self.assertEqual(adapter.file_at(sha, "file.txt"), "safe\n")

    def test_ref_that_looks_like_an_option_is_not_interpreted_as_one(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "file.txt").write_text("safe\n", encoding="utf-8")
        commit_all(repo, "safe")
        with self.assertRaises(GitError):
            GitRepo(repo).resolve("--help")

    def test_snapshot_ignores_export_ignore_attributes(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / ".gitattributes").write_text("kept.txt export-ignore\n", encoding="utf-8")
        (repo / "kept.txt").write_text("must be verified\n", encoding="utf-8")
        sha = commit_all(repo, "export attribute")
        with GitRepo(repo).snapshot(sha, "attributes") as snapshot:
            self.assertEqual(
                (snapshot / "kept.txt").read_text(encoding="utf-8"),
                "must be verified\n",
            )

    @unittest.skipIf(os.name == "nt", "symbolic-link creation is not reliable on Windows")
    def test_snapshot_rejects_symbolic_link_that_escapes_root(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "escape").symlink_to("../../outside")
        sha = commit_all(repo, "escaping link")
        with self.assertRaisesRegex(GitError, "symbolic link escapes"):
            with GitRepo(repo).snapshot(sha, "escape"):
                pass

    @unittest.skipIf(os.name == "nt", "symbolic-link creation is not reliable on Windows")
    def test_snapshot_allows_internal_symbolic_link_and_contains_no_git_directory(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "target.txt").write_text("safe\n", encoding="utf-8")
        directory = repo / "dir"
        directory.mkdir()
        (directory / "link").symlink_to("../target.txt")
        sha = commit_all(repo, "internal link")
        with GitRepo(repo).snapshot(sha, "safe-link") as snapshot:
            self.assertFalse((snapshot / ".git").exists())
            self.assertTrue((snapshot / "dir" / "link").is_symlink())
            self.assertEqual((snapshot / "dir" / "link").read_text(encoding="utf-8"), "safe\n")

    def test_snapshot_rejects_nonportable_archive_names(self) -> None:
        for name in ("..\\escape", "stream:payload"):
            with self.assertRaisesRegex(GitError, "portable"):
                _validate_snapshot_path(name)

    def test_snapshot_rejects_reserved_git_directory(self) -> None:
        with self.assertRaisesRegex(GitError, "reserved"):
            _validate_snapshot_path("nested/.GIT/config")

    def test_snapshot_rejects_empty_symbolic_link_target(self) -> None:
        with self.assertRaisesRegex(GitError, "invalid target"):
            _validate_link_target(Path("link"), "")

    def test_tree_parser_rejects_gitlinks(self) -> None:
        raw = b"160000 commit " + (b"a" * 40) + b" -\tsubmodule\0"
        with self.assertRaisesRegex(GitError, "unsupported"):
            _parse_tree_entries(raw)

    def test_tree_parser_rejects_invalid_utf8_path(self) -> None:
        raw = b"100644 blob " + (b"a" * 40) + b" 1\tbad-\xff\0"
        with self.assertRaisesRegex(GitError, "valid UTF"):
            _parse_tree_entries(raw)


if __name__ == "__main__":
    unittest.main()
