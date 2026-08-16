from __future__ import annotations

import contextlib
import os
from pathlib import Path, PurePosixPath
import signal
import shutil
import subprocess
import tempfile
import threading
import unicodedata
from dataclasses import dataclass, field as dataclass_field
from typing import BinaryIO, Iterator
from urllib.parse import urlsplit, urlunsplit

from .models import ChangedFile

_MAX_GIT_OUTPUT_BYTES = 64 * 1024 * 1024
_MAX_GIT_ERROR_BYTES = 1024 * 1024
_MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
_MAX_SNAPSHOT_MEMBER_BYTES = 128 * 1024 * 1024
_MAX_SNAPSHOT_FILES = 100_000
_GIT_COMMAND_TIMEOUT_SECONDS = 120
_GIT_TERMINATE_GRACE_SECONDS = 1.0


class GitError(RuntimeError):
    """Raised when a required Git operation fails."""


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    mode: str
    object_id: str
    size: int
    path: str

    @property
    def symlink(self) -> bool:
        return self.mode == "120000"

    @property
    def executable(self) -> bool:
        return self.mode == "100755"


class GitRepo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self._run("rev-parse", "--is-inside-work-tree")
        root = self._run("rev-parse", "--show-toplevel").stdout.strip()
        self.path = Path(root).resolve()

    def _run(self, *args: str, check: bool = True) -> GitCommandResult:
        stdout, stderr, returncode = _run_git_bounded(
            self.path,
            args,
            stdout_limit=_MAX_GIT_OUTPUT_BYTES,
            stderr_limit=_MAX_GIT_ERROR_BYTES,
        )
        decoded_stdout = stdout.decode("utf-8", errors="replace")
        decoded_stderr = stderr.decode("utf-8", errors="replace")
        if check and returncode != 0:
            command = "git " + " ".join(args)
            raise GitError(f"{command} failed: {decoded_stderr.strip()}")
        return GitCommandResult(decoded_stdout, decoded_stderr, returncode)

    def _run_bytes(self, *args: str, check: bool = True) -> bytes:
        stdout, stderr, returncode = _run_git_bounded(
            self.path,
            args,
            stdout_limit=_MAX_GIT_OUTPUT_BYTES,
            stderr_limit=_MAX_GIT_ERROR_BYTES,
        )
        if check and returncode != 0:
            command = "git " + " ".join(args)
            error = stderr.decode("utf-8", errors="replace").strip()
            raise GitError(f"{command} failed: {error}")
        return stdout

    def resolve(self, ref: str) -> str:
        return self._run("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").stdout.strip()

    def is_clean(self) -> bool:
        return not self._run("status", "--porcelain=v1").stdout.strip()

    def changed_files(self, base_sha: str, head_sha: str) -> list[ChangedFile]:
        names_raw = self._run_bytes(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-status",
            "-z",
            "--find-renames",
            f"{base_sha}..{head_sha}",
        )
        stats_raw = self._run_bytes(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--text",
            "--numstat",
            "-z",
            "--find-renames",
            f"{base_sha}..{head_sha}",
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
            _validate_snapshot_path(path)
            if old_path is not None:
                _validate_snapshot_path(old_path)
            added, deleted, _ = stats.get(path, (None, None, False))
            binary = self._path_is_binary(base_sha, old_path or path) or self._path_is_binary(
                head_sha, path
            )
            if binary:
                added = None
                deleted = None
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

    def _path_is_binary(self, ref: str, path: str) -> bool:
        object_name = f"{ref}:{path}"
        size_result = self._run("cat-file", "-s", object_name, check=False)
        if size_result.returncode != 0:
            return False
        try:
            size = int(size_result.stdout.strip())
        except ValueError as exc:
            raise GitError(f"git cat-file returned an invalid size for {path}") from exc
        if size < 0:
            raise GitError(f"git cat-file returned a negative size for {path}")
        if size > _MAX_SNAPSHOT_MEMBER_BYTES:
            return True
        raw = _read_git_blob_prefix(self.path, object_name, size, 8192)
        return b"\x00" in raw

    def unified_diff(self, base_sha: str, head_sha: str) -> str:
        return self._run(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--text",
            "--unified=3",
            f"{base_sha}..{head_sha}",
            "--",
        ).stdout

    def file_bytes_at(self, ref: str, path: str) -> bytes | None:
        _validate_snapshot_path(path)
        stdout, _stderr, returncode = _run_git_bounded(
            self.path,
            ("cat-file", "blob", f"{ref}:{path}"),
            stdout_limit=_MAX_GIT_OUTPUT_BYTES,
            stderr_limit=_MAX_GIT_ERROR_BYTES,
        )
        return None if returncode != 0 else stdout

    def file_at(self, ref: str, path: str) -> str | None:
        raw = self.file_bytes_at(ref, path)
        return None if raw is None else raw.decode("utf-8", errors="replace")

    def utf8_file_at(self, ref: str, path: str) -> str | None:
        raw = self.file_bytes_at(ref, path)
        if raw is None:
            return None
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise GitError(f"Git file is not valid UTF-8: {path}") from exc

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
    def snapshot(self, sha: str, label: str) -> Iterator[Path]:
        """Materialize Git objects without hooks, filters, attributes, or .git."""

        parent = Path(tempfile.mkdtemp(prefix=f"patchlab-{label}-"))
        checkout = parent / "repo"
        # The isolated container runs as UID/GID 65532. The snapshot contains
        # only committed Git objects with fixed 0644/0755 modes, so the mount
        # root must be readable and traversable by that unprivileged identity.
        checkout.mkdir(mode=0o755)
        try:
            entries = _parse_tree_entries(
                self._run_bytes(
                    "ls-tree",
                    "-rz",
                    "-l",
                    "--full-tree",
                    sha,
                    "--",
                )
            )
            if len(entries) > _MAX_SNAPSHOT_FILES:
                raise GitError(
                    f"Git tree exceeded the {_MAX_SNAPSHOT_FILES}-file snapshot limit"
                )
            total = sum(item.size for item in entries)
            if total > _MAX_SNAPSHOT_BYTES:
                raise GitError(
                    f"Git tree exceeded the {_MAX_SNAPSHOT_BYTES}-byte snapshot limit"
                )

            ordinary = [item for item in entries if not item.symlink]
            links = [item for item in entries if item.symlink]
            for entry in ordinary:
                raw = self._read_blob(entry.object_id, entry.size)
                _write_snapshot_file(checkout, entry.path, raw, entry.executable)
            for entry in links:
                raw = self._read_blob(entry.object_id, entry.size)
                _write_snapshot_link(checkout, entry.path, raw)
            yield checkout
        finally:
            shutil.rmtree(parent, ignore_errors=True)

    # Backward-compatible internal alias. New code should use snapshot().
    worktree = snapshot

    def _read_blob(self, object_id: str, expected_size: int) -> bytes:
        if expected_size < 0 or expected_size > _MAX_SNAPSHOT_MEMBER_BYTES:
            raise GitError(
                f"Git blob exceeded the {_MAX_SNAPSHOT_MEMBER_BYTES}-byte member limit"
            )
        raw, stderr, returncode = _run_git_bounded(
            self.path,
            ("cat-file", "blob", object_id),
            stdout_limit=expected_size,
            stderr_limit=_MAX_GIT_ERROR_BYTES,
        )
        if returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise GitError(f"git cat-file failed: {detail}")
        if len(raw) != expected_size:
            raise GitError(
                f"Git blob size mismatch for {object_id}: expected {expected_size}, got {len(raw)}"
            )
        return raw

    def repository_display(self) -> str:
        remote = self._run("remote", "get-url", "origin", check=False).stdout.strip()
        return _public_repository_identifier(remote) if remote else self.path.name


def _read_git_blob_prefix(root: Path, object_name: str, size: int, limit: int) -> bytes:
    wanted = min(size, limit)
    stdout, stderr, returncode = _run_git_bounded(
        root,
        ("cat-file", "blob", object_name),
        stdout_limit=wanted,
        stderr_limit=_MAX_GIT_ERROR_BYTES,
        allow_stdout_truncation=size > wanted,
    )
    if len(stdout) != wanted:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git cat-file returned a short blob prefix: {detail}")
    if size <= wanted and returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git cat-file failed: {detail}")
    return stdout


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


def _git_executable(root: Path) -> str:
    path = os.environ.get("PATH", os.defpath)
    executable = shutil.which("git", path=path)
    if not executable:
        raise GitError("git executable was not found on PATH")
    resolved = Path(executable).resolve()
    if not resolved.is_file():
        raise GitError(f"git executable is not a regular file: {resolved}")
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise GitError("git executable resolved inside the untrusted repository")
    return os.fspath(resolved)


def _git_command(root: Path, *args: str) -> list[str]:
    return [
        _git_executable(root),
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "diff.external=",
        "-c",
        "interactive.diffFilter=",
        "-c",
        "protocol.file.allow=never",
        *args,
    ]


def _git_environment(home: Path | None = None) -> dict[str, str]:
    """Build a minimal non-interactive environment for local Git operations."""

    environment: dict[str, str] = {}
    for key in (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "PATHEXT",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "TEMP",
        "TMP",
    ):
        value = os.environ.get(key)
        if value:
            environment[key] = value

    empty_home = home or Path(tempfile.mkdtemp(prefix="patchlab-git-home-"))
    empty_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": os.fspath(empty_home),
            "XDG_CONFIG_HOME": os.fspath(empty_home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PROTOCOL_FROM_USER": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
        }
    )
    return environment


def _parse_tree_entries(raw: bytes) -> list[_TreeEntry]:
    entries: list[_TreeEntry] = []
    seen: set[str] = set()
    portable_seen: set[tuple[str, ...]] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_raw = record.split(b"\t", 1)
            mode_raw, kind_raw, object_raw, size_raw = metadata.split(b" ", 3)
        except ValueError as exc:
            raise GitError("malformed NUL-delimited output from git ls-tree") from exc
        try:
            mode = mode_raw.decode("ascii")
            kind = kind_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
            path = path_raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise GitError("snapshot paths and object metadata must be valid UTF-8/ASCII") from exc
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise GitError(f"unsupported Git tree entry: mode={mode}, type={kind}, path={path}")
        if len(object_id) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in object_id):
            raise GitError(f"invalid Git object id for snapshot entry: {path}")
        try:
            size = int(size_raw)
        except ValueError as exc:
            raise GitError(f"invalid Git blob size for snapshot entry: {path}") from exc
        relative = _validate_snapshot_path(path)
        portable_key = _portable_path_key(relative)
        if path in seen or portable_key in portable_seen:
            raise GitError(f"duplicate or nonportable-colliding Git tree path: {path}")
        seen.add(path)
        portable_seen.add(portable_key)
        entries.append(_TreeEntry(mode, object_id, size, path))
    return entries


_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_WINDOWS_INVALID_CHARS = frozenset('<>:"\\|?*')


def _validate_snapshot_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name:
        raise GitError("snapshot contains an empty or NUL-containing path")
    if len(name.encode("utf-8")) > 4096:
        raise GitError("snapshot path exceeds the portable length limit")
    relative = PurePosixPath(name)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise GitError(f"snapshot path escapes the snapshot root: {name}")
    for part in relative.parts:
        _validate_portable_component(part, name)
    return relative


def _validate_portable_component(part: str, full_name: str) -> None:
    if len(part.encode("utf-8")) > 255:
        raise GitError(f"snapshot path component exceeds the portable length limit: {full_name}")
    if any(ord(character) < 32 for character in part):
        raise GitError(f"snapshot path contains a control character: {full_name}")
    if any(character in _WINDOWS_INVALID_CHARS for character in part):
        raise GitError(f"snapshot path is not portable across supported hosts: {full_name}")
    if part.endswith((" ", ".")):
        raise GitError(f"snapshot path has a nonportable trailing character: {full_name}")
    stem = part.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        raise GitError(f"snapshot path uses a reserved Windows device name: {full_name}")
    if part.casefold() == ".git":
        raise GitError(f"snapshot path uses the reserved .git name: {full_name}")


def _portable_path_key(path: PurePosixPath) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def _validate_link_target(path: PurePosixPath, target: str) -> None:
    if not target or "\x00" in target:
        raise GitError(f"snapshot symbolic link has an invalid target: {path}")
    if "\\" in target or ":" in target:
        raise GitError(f"snapshot symbolic link is not portable: {path}")
    link = PurePosixPath(target)
    if link.is_absolute() or _lexical_link_escapes(path.parent, link):
        raise GitError(f"snapshot symbolic link escapes the snapshot root: {path}")
    for part in link.parts:
        if part not in {"", ".", ".."}:
            _validate_portable_component(part, f"{path} -> {target}")


def _write_snapshot_file(root: Path, name: str, raw: bytes, executable: bool) -> None:
    relative = _validate_snapshot_path(name)
    target = root.joinpath(*relative.parts)
    _ensure_parent_directories(root, target.parent)
    if target.exists() or target.is_symlink():
        raise GitError(f"snapshot path collides with an existing entry: {name}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags, 0o755 if executable else 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(raw)
            destination.flush()
    finally:
        os.close(descriptor)


def _write_snapshot_link(root: Path, name: str, raw: bytes) -> None:
    relative = _validate_snapshot_path(name)
    try:
        link_target = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GitError(f"snapshot symbolic link target is not UTF-8: {name}") from exc
    _validate_link_target(relative, link_target)
    target = root.joinpath(*relative.parts)
    _ensure_parent_directories(root, target.parent)
    if target.exists() or target.is_symlink():
        raise GitError(f"snapshot path collides with an existing entry: {name}")
    try:
        target.symlink_to(link_target)
    except OSError as exc:
        raise GitError(f"could not materialize symbolic link {name}: {exc}") from exc


def _lexical_link_escapes(parent: PurePosixPath, link: PurePosixPath) -> bool:
    depth = 0
    for part in (*parent.parts, *link.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        else:
            depth += 1
    return False


def _ensure_parent_directories(root: Path, parent: Path) -> None:
    relative = parent.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise GitError(f"archive parent path is a symbolic link: {relative}")
        current.mkdir(mode=0o755, exist_ok=True)
        if not current.is_dir():
            raise GitError(f"archive parent path is not a directory: {relative}")


@dataclass(slots=True)
class _LimitedBuffer:
    limit: int
    label: str
    data: bytearray = dataclass_field(default_factory=bytearray)
    exceeded: bool = False
    lock: threading.Lock = dataclass_field(default_factory=threading.Lock)

    def feed(self, chunk: bytes, process: subprocess.Popen[bytes]) -> None:
        with self.lock:
            remaining = self.limit - len(self.data)
            if len(chunk) <= remaining:
                self.data.extend(chunk)
                return
            if remaining > 0:
                self.data.extend(chunk[:remaining])
            self.exceeded = True
        try:
            process.kill()
        except OSError:
            pass


def _run_git_bounded(
    root: Path,
    args: tuple[str, ...],
    *,
    stdout_limit: int,
    stderr_limit: int,
    allow_stdout_truncation: bool = False,
) -> tuple[bytes, bytes, int]:
    if stdout_limit < 0 or stderr_limit < 0:
        raise ValueError("Git output limits must be non-negative")
    with tempfile.TemporaryDirectory(prefix="patchlab-git-home-") as home_raw:
        popen_options: dict[str, object] = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        process = subprocess.Popen(
            _git_command(root, *args),
            cwd=root,
            env=_git_environment(Path(home_raw)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_options,
        )
        if process.stdout is None or process.stderr is None:
            process.kill()
            raise GitError("Git pipes were not created")
        stdout = _LimitedBuffer(stdout_limit, "Git standard output")
        stderr = _LimitedBuffer(stderr_limit, "Git standard error")
        threads = (
            threading.Thread(
                target=_drain_git_stream, args=(process.stdout, stdout, process), daemon=True
            ),
            threading.Thread(
                target=_drain_git_stream, args=(process.stderr, stderr, process), daemon=True
            ),
        )
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            returncode = process.wait(timeout=_GIT_COMMAND_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_git_process(process)
            returncode = process.returncode if process.returncode is not None else -1
        for thread in threads:
            thread.join(timeout=5)
        for stream in (process.stdout, process.stderr):
            stream.close()
        for thread in threads:
            thread.join(timeout=1)
    if timed_out:
        raise GitError(
            f"Git command exceeded the {_GIT_COMMAND_TIMEOUT_SECONDS}-second safety limit"
        )
    for buffer in (stdout, stderr):
        if buffer.exceeded:
            if buffer is stdout and allow_stdout_truncation:
                continue
            raise GitError(f"{buffer.label} exceeded the {buffer.limit}-byte safety limit")
    return bytes(stdout.data), bytes(stderr.data), returncode


def _terminate_git_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=_GIT_TERMINATE_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def _drain_git_stream(
    stream: BinaryIO, buffer: _LimitedBuffer, process: subprocess.Popen[bytes]
) -> None:
    try:
        while chunk := stream.read(64 * 1024):
            buffer.feed(chunk, process)
            if buffer.exceeded:
                return
    except (OSError, ValueError):
        return


def _decode_path(raw: bytes) -> str:
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GitError("Git paths must be valid UTF-8") from exc


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
        try:
            added = None if binary else int(added_raw)
            deleted = None if binary else int(deleted_raw)
        except ValueError as exc:
            raise GitError("malformed numeric fields in git diff numstat output") from exc
        stats[path] = (added, deleted, binary)
    return stats
