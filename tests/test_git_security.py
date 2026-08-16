from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from patchlab_commons.gitutils import (
    GitError,
    GitRepo,
    _decode_path,
    _git_environment,
    _git_executable,
    _parse_tree_entries,
    _run_git_bounded,
    _validate_link_target,
    _validate_snapshot_path,
)
from tests.helpers import commit_all, init_repo
from tests.helpers import git as run_git


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
        (repo / "file.txt").write_bytes(b"safe\n")
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

    def test_git_replace_refs_cannot_substitute_selected_commit_objects(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "file.txt").write_bytes(b"safe\n")
        safe_sha = commit_all(repo, "safe")
        (repo / "file.txt").write_bytes(b"replacement\n")
        replacement_sha = commit_all(repo, "replacement")
        run_git(repo, "replace", safe_sha, replacement_sha)

        adapter = GitRepo(repo)
        self.assertEqual(adapter.resolve(safe_sha), safe_sha)
        self.assertEqual(adapter.file_at(safe_sha, "file.txt"), "safe\n")
        with adapter.snapshot(safe_sha, "no-replace") as snapshot:
            self.assertEqual((snapshot / "file.txt").read_text(encoding="utf-8"), "safe\n")

    def test_alternate_object_database_outside_boundary_is_rejected(self) -> None:
        root = Path(tempfile.mkdtemp())
        external = root / "external"
        victim = root / "victim"
        init_repo(external)
        (external / "external.txt").write_text("outside\n", encoding="utf-8")
        external_sha = commit_all(external, "external")
        init_repo(victim)
        alternates = victim / ".git" / "objects" / "info" / "alternates"
        alternates.write_bytes((external / ".git" / "objects").as_posix().encode() + b"\n")
        run_git(victim, "update-ref", "refs/heads/main", external_sha)

        with self.assertRaisesRegex(GitError, "alternate object databases"):
            GitRepo(victim)

    @unittest.skipIf(os.name == "nt", "symbolic-link creation requires POSIX semantics")
    def test_symlinked_loose_object_outside_boundary_is_rejected(self) -> None:
        root = Path(tempfile.mkdtemp())
        repo = root / "repo"
        init_repo(repo)
        (repo / "file.txt").write_text("safe\n", encoding="utf-8")
        commit_all(repo, "safe")
        object_id = run_git(repo, "rev-parse", "HEAD:file.txt")
        loose_object = repo / ".git" / "objects" / object_id[:2] / object_id[2:]
        outside = root / "outside-object"
        outside.write_bytes(loose_object.read_bytes())
        loose_object.unlink()
        loose_object.symlink_to(outside)

        with self.assertRaisesRegex(GitError, "contains a symbolic link"):
            GitRepo(repo)

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

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are required")
    def test_snapshot_root_is_readable_by_the_unprivileged_container_user(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "file.txt").write_text("safe\n", encoding="utf-8")
        sha = commit_all(repo, "safe")
        with GitRepo(repo).snapshot(sha, "permissions") as snapshot:
            mode = snapshot.stat().st_mode
            self.assertTrue(mode & stat.S_IROTH)
            self.assertTrue(mode & stat.S_IXOTH)

    @unittest.skipIf(os.name == "nt", "POSIX executable fixtures are required")
    def test_git_executable_cannot_be_loaded_from_the_candidate_repository(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        repo.mkdir()
        fake = repo / "git"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(repo)}, clear=False):
            with self.assertRaisesRegex(GitError, "inside the declared untrusted root"):
                _git_executable(repo)

    @unittest.skipIf(os.name == "nt", "POSIX executable fixtures are required")
    def test_git_executable_is_rejected_from_a_sibling_in_the_untrusted_root(self) -> None:
        workspace = Path(tempfile.mkdtemp())
        repo = workspace / "repo"
        repo.mkdir()
        tools = workspace / "tools"
        tools.mkdir()
        fake = tools / "git"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(tools)}, clear=False):
            with self.assertRaisesRegex(GitError, "declared untrusted root"):
                _git_executable(workspace)

    @unittest.skipIf(os.name == "nt", "POSIX fake Git executable is required")
    def test_git_commands_have_a_hard_timeout(self) -> None:
        root = Path(tempfile.mkdtemp())
        tools = Path(tempfile.mkdtemp())
        fake = tools / "git"
        fake.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
        fake.chmod(0o755)
        with (
            patch.dict(os.environ, {"PATH": f"{tools}{os.pathsep}{os.defpath}"}, clear=False),
            patch("patchlab_commons.gitutils._GIT_COMMAND_TIMEOUT_SECONDS", 0.1),
        ):
            with self.assertRaisesRegex(GitError, "safety limit"):
                _run_git_bounded(root, ("status",), stdout_limit=1024, stderr_limit=1024)

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
        for name in ("..\\escape", "stream:payload", "a//b", "a/./b"):
            with self.assertRaisesRegex(GitError, "portable|escapes"):
                _validate_snapshot_path(name)

    def test_snapshot_rejects_windows_device_names_and_trailing_characters(self) -> None:
        for name in ("NUL", "con.txt", "nested/COM1.log", "bad. ", "bad."):
            with self.subTest(name=name):
                with self.assertRaises(GitError):
                    _validate_snapshot_path(name)

    def test_tree_parser_rejects_casefold_and_unicode_collisions(self) -> None:
        object_id = b"a" * 40
        raw = (
            b"100644 blob " + object_id + b" 1\tFile.txt\0"
            b"100644 blob " + object_id + b" 1\tfile.txt\0"
        )
        with self.assertRaisesRegex(GitError, "colliding"):
            _parse_tree_entries(raw)

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

    def test_diff_path_decoder_rejects_invalid_utf8(self) -> None:
        with self.assertRaisesRegex(GitError, "valid UTF-8"):
            _decode_path(b"bad-\xff")


if __name__ == "__main__":
    unittest.main()
