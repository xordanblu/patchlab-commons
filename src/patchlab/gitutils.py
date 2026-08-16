from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator
from urllib.parse import urlsplit, urlunsplit

from .models import ChangedFile

_MAX_GIT_OUTPUT_BYTES = 64 * 1024 * 1024
_MAX_GIT_ERROR_BYTES = 1024 * 1024


class GitError(RuntimeError):
    """Raised when a required Git operation fails."""


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    stdout: str
    stderr: str
    returncode: int


class GitRepo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self._run("rev-parse", "--is-inside-work-tree")
        root = self._run("rev-parse", "--show-toplevel").stdout.strip()
        self.path = Path(root).resolve()

    def _run(self, *args: str, check: bool = True) -> GitCommandResult:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.run(
                _git_command(*args),
                cwd=self.path,
                env=_git_environment(),
                stdout=stdout_file,
                stderr=stderr_file,
                check=False,
            )
            stdout = _read_limited(stdout_file, _MAX_GIT_OUTPUT_BYTES, "Git standard output")
            stderr = _read_limited(stderr_file, _MAX_GIT_ERROR_BYTES, "Git standard error")
        decoded_stdout = stdout.decode("utf-8", errors="replace")
        decoded_stderr = stderr.decode("utf-8", errors="replace")
        if check and process.returncode != 0:
            command = "git " + " ".join(args)
            raise GitError(f"{command} failed: {decoded_stderr.strip()}")
        return GitCommandResult(decoded_stdout, decoded_stderr, process.returncode)

    def _run_bytes(self, *args: str, check: bool = True) -> bytes:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.run(
                _git_command(*args),
                cwd=self.path,
                env=_git_environment(),
                stdout=stdout_file,
                stderr=stderr_file,
                check=False,
            )
            stdout = _read_limited(stdout_file, _MAX_GIT_OUTPUT_BYTES, "Git standard output")
            stderr = _read_limited(stderr_file, _MAX_GIT_ERROR_BYTES, "Git standard error")
        if check and process.returncode != 0:
            command = "git " + " ".join(args)
            error = stderr.decode("utf-8", errors="replace").strip()
            raise GitError(f"{command} failed: {error}")
        return stdout

    def resolve(self, ref: str) -> str:
        return self._run("rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()

    def is_clean(self) -> bool:
        return not self._run("status", "--porcelain=v1").stdout.strip()

    def changed_files(self, base_sha: str, head_sha: str) -> list[ChangedFile]:
        names_raw = self._run_bytes(
            "diff", "--name-status", "-z", "--find-renames", f"{base_sha}..{head_sha}"
        )
        stats_raw = self._run_bytes(
            "diff", "--numstat", "-z", "--find-renames", f"{base_sha}..{head_sha}"
        )
        stats = _parse_numstat_z(stats_raw)
        tokens = [token for token in names_raw.split(b"\0") if token]
        result: list[ChangedFile] = []
        index = 0
        while index < len(tokens):
            status = _decode_path(tokens[index])
            index += 1
            old_path: str | None = None
            if status.startswith(("R", "C")):
                if index + 1 >= len(tokens):
                    raise GitError("malformed NUL-delimited rename output from git diff")
                old_path = _decode_path(tokens[index])
                path = _decode_path(tokens[index + 1])
                index += 2
            else:
                if index >= len(tokens):
                    raise GitError("malformed NUL-delimited name output from git diff")
                path = _decode_path(tokens[index])
                index += 1
            added, deleted, binary = stats.get(path, (None, None, False))
            result.append(
                ChangedFile(
                    status=status,
                    path=path,
                    old_path=old_path,
                    added_lines=added,
                    deleted_lines=deleted,
                    binary=binary,
                )
            )
        return result

    def unified_diff(self, base_sha: str, head_sha: str) -> str:
        return self._run(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--unified=3",
            f"{base_sha}..{head_sha}",
            "--",
        ).stdout

    def file_at(self, ref: str, path: str) -> str | None:
        result = self._run("show", f"{ref}:{path}", check=False)
        if result.returncode != 0:
            return None
        return result.stdout

    def commit_metadata(self, sha: str) -> dict[str, str]:
        raw = self._run(
            "show",
            "-s",
            "--format=%H%n%T%n%aI%n%an%n%ae%n%s",
            sha,
        ).stdout.splitlines()
        keys = ["commit", "tree", "authored_at", "author_name", "author_email", "subject"]
        return {key: raw[index] if index < len(raw) else "" for index, key in enumerate(keys)}

    @contextlib.contextmanager
    def worktree(self, sha: str, label: str) -> Iterator[Path]:
        parent = Path(tempfile.mkdtemp(prefix=f"patchlab-{label}-"))
        checkout = parent / "repo"
        try:
            self._run("worktree", "add", "--detach", str(checkout), sha)
            yield checkout
        finally:
            if checkout.exists():
                self._run("worktree", "remove", "--force", str(checkout), check=False)
            with contextlib.suppress(OSError):
                checkout.rmdir()
            with contextlib.suppress(OSError):
                parent.rmdir()

    def repository_display(self) -> str:
        remote = self._run("remote", "get-url", "origin", check=False).stdout.strip()
        return _public_repository_identifier(remote) if remote else self.path.name


def _public_repository_identifier(remote: str) -> str:
    """Remove credentials and local path details from a Git remote."""

    if "://" in remote:
        parsed = urlsplit(remote)
        if parsed.scheme == "file":
            return Path(parsed.path).name or "repository"
        host = parsed.hostname or ""
        try:
            parsed_port = parsed.port
        except ValueError:
            parsed_port = None
        port = f":{parsed_port}" if parsed_port else ""
        return urlunsplit((parsed.scheme, host + port, parsed.path, "", ""))
    if "@" in remote and ":" in remote.rsplit("@", 1)[1]:
        host, path = remote.rsplit("@", 1)[1].split(":", 1)
        return f"{host}/{path}"
    path = Path(remote.rstrip("/"))
    return path.name or "repository"


def _git_command(*args: str) -> list[str]:
    return [
        "git",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *args,
    ]


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
        }
    )
    return environment


def _read_limited(handle: BinaryIO, limit: int, label: str) -> bytes:
    handle.flush()
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    if size > limit:
        raise GitError(f"{label} exceeded the {limit}-byte safety limit")
    handle.seek(0)
    return handle.read()


def _decode_path(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _parse_numstat_z(raw: bytes) -> dict[str, tuple[int | None, int | None, bool]]:
    tokens = raw.split(b"\0")
    stats: dict[str, tuple[int | None, int | None, bool]] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        parts = token.split(b"\t", 2)
        if len(parts) != 3:
            raise GitError("malformed NUL-delimited numstat output from git diff")
        added_raw, deleted_raw, path_raw = parts
        if path_raw:
            path = _decode_path(path_raw)
        else:
            if index + 1 >= len(tokens):
                raise GitError("malformed NUL-delimited rename numstat output from git diff")
            index += 1  # Skip the old path.
            path = _decode_path(tokens[index])
            index += 1
        binary = added_raw == b"-" or deleted_raw == b"-"
        added = None if binary else int(added_raw)
        deleted = None if binary else int(deleted_raw)
        stats[path] = (added, deleted, binary)
    return stats

