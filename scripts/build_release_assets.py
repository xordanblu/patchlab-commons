#!/usr/bin/env python3
"""Build deterministic release assets from the selected Git commit."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import tomllib
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, overload

_MAX_MEMBER_BYTES = 32 * 1024 * 1024
_MAX_SOURCE_BYTES = 256 * 1024 * 1024
_GIT_TIMEOUT_SECONDS = 120
_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_WINDOWS_INVALID_CHARS = frozenset('<>:"\\|?*')


@dataclass(frozen=True, slots=True)
class TreeEntry:
    mode: str
    object_id: str
    size: int
    path: str


def _inside_root(root: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the repository") from exc
    if resolved == root:
        raise ValueError(f"{label} must not be the repository root")
    return resolved


def _git_executable(root: Path) -> str:
    discovered = shutil.which("git", path=os.environ.get("PATH", os.defpath))
    if discovered is None:
        raise RuntimeError("Git is not available")
    executable = Path(discovered).resolve(strict=True)
    mode = executable.stat().st_mode
    if not stat.S_ISREG(mode) or not os.access(executable, os.X_OK):
        raise RuntimeError(f"Git executable is not a regular executable file: {executable}")
    try:
        executable.relative_to(root)
    except ValueError:
        return os.fspath(executable)
    raise RuntimeError("refusing to use a Git executable from inside the repository")


def _git_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": tempfile.gettempdir(),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PROTOCOL_FROM_USER": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "LC_ALL": "C",
        "LANG": "C",
    }


@overload
def git(root: Path, *args: str, binary: Literal[False] = False) -> str: ...


@overload
def git(root: Path, *args: str, binary: Literal[True]) -> bytes: ...


def git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    command = [
        _git_executable(root),
        "--no-replace-objects",
        "--no-pager",
        "--literal-pathspecs",
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
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=_git_environment(),
            timeout=_GIT_TIMEOUT_SECONDS,
            start_new_session=os.name != "nt",
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Git command exceeded {_GIT_TIMEOUT_SECONDS} seconds: {args[0] if args else 'git'}"
        ) from exc
    return result.stdout if binary else result.stdout.decode("utf-8", errors="strict").strip()


def _tree_entries(root: Path, commit: str) -> list[TreeEntry]:
    raw = git(root, "ls-tree", "-r", "-z", "--long", commit, binary=True)
    entries: list[TreeEntry] = []
    seen: set[str] = set()
    portable_seen: set[tuple[str, ...]] = set()
    total = 0
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_raw = record.split(b"\t", 1)
            mode_raw, kind_raw, object_raw, size_raw = metadata.split(b" ", 3)
            mode = mode_raw.decode("ascii")
            kind = kind_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
            path = path_raw.decode("utf-8", errors="strict")
            size = int(size_raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("malformed Git tree entry") from exc
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise ValueError(f"unsupported Git tree entry: {mode} {kind} {path}")
        relative = _validate_source_path(path)
        portable_key = tuple(
            unicodedata.normalize("NFC", part).casefold() for part in relative.parts
        )
        if path in seen or portable_key in portable_seen:
            raise ValueError(f"duplicate or nonportable-colliding tracked path: {path}")
        if size < 0 or size > _MAX_MEMBER_BYTES:
            raise ValueError(f"tracked member exceeds size limit: {path}")
        total += size
        if total > _MAX_SOURCE_BYTES:
            raise ValueError("tracked source exceeds total size limit")
        seen.add(path)
        portable_seen.add(portable_key)
        entries.append(TreeEntry(mode, object_id, size, path))
    return entries


def _validate_source_path(path: str) -> PurePosixPath:
    if not path or "\x00" in path or len(path.encode("utf-8")) > 4096:
        raise ValueError(f"unsafe or nonportable tracked path: {path}")
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or relative.as_posix() != path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"unsafe or nonportable tracked path: {path}")
    for part in relative.parts:
        if (
            len(part.encode("utf-8")) > 255
            or any(ord(character) < 32 for character in part)
            or any(character in _WINDOWS_INVALID_CHARS for character in part)
            or part.endswith((" ", "."))
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
            or part.casefold() == ".git"
        ):
            raise ValueError(f"unsafe or nonportable tracked path: {path}")
    return relative


def _validate_symlink_target(path: PurePosixPath, target: bytes) -> None:
    try:
        text = target.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"symbolic link target is not UTF-8: {path}") from exc
    if not text or "\x00" in text or "\\" in text or ":" in text:
        raise ValueError(f"unsafe symbolic link target: {path}")
    link = PurePosixPath(text)
    if link.is_absolute():
        raise ValueError(f"symbolic link escapes the source root: {path}")
    depth = 0
    for part in (*path.parent.parts, *link.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                raise ValueError(f"symbolic link escapes the source root: {path}")
        else:
            depth += 1


def _blob(root: Path, entry: TreeEntry) -> bytes:
    raw = git(root, "cat-file", "blob", entry.object_id, binary=True)
    if len(raw) != entry.size:
        raise ValueError(
            f"Git blob size mismatch for {entry.path}: expected {entry.size}, got {len(raw)}"
        )
    return raw


def source_zip(root: Path, output: Path, prefix: str, epoch: int, commit: str = "HEAD") -> None:
    timestamp = datetime.fromtimestamp(max(epoch, 315532800), UTC)
    # ZIP stores seconds with two-second resolution. Normalize before writing.
    second = timestamp.second - (timestamp.second % 2)
    date_time = (
        timestamp.year,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        second,
    )
    entries = _tree_entries(root, commit)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in entries:
            data = _blob(root, entry)
            if entry.mode == "120000":
                _validate_symlink_target(PurePosixPath(entry.path), data)
                mode = stat.S_IFLNK | 0o777
            else:
                mode = stat.S_IFREG | (0o755 if entry.mode == "100755" else 0o644)
            info = zipfile.ZipInfo(f"{prefix}/{entry.path}", date_time=date_time)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--dist", default="release")
    parser.add_argument("--commit", default="HEAD")
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    if not (root / ".git").exists():
        raise SystemExit(f"repository has no Git metadata: {root}")
    requested_dist = Path(args.dist)
    dist = _inside_root(
        root,
        requested_dist if requested_dist.is_absolute() else root / requested_dist,
        "release directory",
    )
    dist.mkdir(parents=True, exist_ok=True)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    commit = str(git(root, "rev-parse", f"{args.commit}^{{commit}}"))
    epoch_raw = os.environ.get("SOURCE_DATE_EPOCH") or git(
        root, "show", "-s", "--format=%ct", commit
    )
    epoch = int(epoch_raw)
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must not be negative")
    release_tag = f"v{version}"
    if git(root, "rev-parse", f"refs/tags/{release_tag}^{{commit}}") != commit:
        raise ValueError("release tag does not resolve to the selected commit")
    if git(root, "rev-parse", "refs/heads/main^{commit}") != commit:
        raise ValueError("local main does not resolve to the selected commit")
    if (
        git(root, "rev-parse", "refs/tags/v0.1.0^{commit}")
        != "7b61eb318f894dbb5f496a77ed3fea669d6707b8"
    ):
        raise ValueError("historical v0.1.0 tag moved")
    tag_refs = sorted(
        ref
        for ref in git(root, "for-each-ref", "--format=%(refname)", "refs/tags").splitlines()
        if ref
    )
    if f"refs/tags/{release_tag}" not in tag_refs or "refs/tags/v0.1.0" not in tag_refs:
        raise ValueError("required release tags are missing")
    for ref in tag_refs:
        if git(root, "cat-file", "-t", ref) != "tag":
            raise ValueError(f"release bundle refuses a non-annotated tag: {ref}")

    source = dist / f"patchlab-commons-v{version}-source.zip"
    source_zip(root, source, f"patchlab-commons-{version}", epoch, commit)
    bundle = dist / f"patchlab-commons-v{version}.git.bundle"
    git(root, "bundle", "create", os.fspath(bundle), "refs/heads/main", *tag_refs)
    files = sorted(
        path for path in dist.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt"
    )
    checksums = dist / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8"
    )
    for path in (*files, checksums):
        print(f"{sha256(path)}  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
