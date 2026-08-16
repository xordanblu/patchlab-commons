from __future__ import annotations

import os
import tempfile
from pathlib import Path


class UnsafeOutputPath(OSError):
    """Raised when an output path could redirect writes unexpectedly."""


def resolve_output_directory(repository: Path, requested: Path) -> Path:
    """Resolve a report directory without following repository symlinks.

    Relative output paths must stay below the repository root. Existing path
    components below that root must not be symbolic links.
    """

    root = repository.resolve()
    if requested.is_absolute():
        target = requested
        _reject_directory_link(target)
        return target

    if not requested.parts or requested == Path(".") or ".." in requested.parts:
        raise UnsafeOutputPath("relative output directory must stay below the repository root")

    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeOutputPath(f"output path contains a symbolic link: {current}")

    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafeOutputPath("output directory escapes the repository root") from exc
    return current


def ensure_output_directory(path: Path) -> None:
    _reject_directory_link(path)
    if path.exists() and not path.is_dir():
        raise UnsafeOutputPath(f"output path is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    _reject_directory_link(path)
    if not path.is_dir():
        raise UnsafeOutputPath(f"output path is not a directory: {path}")


def safe_write_text(path: Path, content: str) -> None:
    safe_write_bytes(path, content.encode("utf-8"))


def safe_write_bytes(path: Path, content: bytes) -> None:
    ensure_output_directory(path.parent)
    _reject_destination(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        _reject_destination(path)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def replace_file(temporary: Path, target: Path) -> None:
    """Atomically install a prepared regular file at a safe destination."""

    ensure_output_directory(target.parent)
    _reject_destination(target)
    if temporary.is_symlink() or not temporary.is_file():
        raise UnsafeOutputPath(f"temporary output is not a regular file: {temporary}")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def _reject_directory_link(path: Path) -> None:
    if path.is_symlink():
        raise UnsafeOutputPath(f"output directory is a symbolic link: {path}")


def _reject_destination(path: Path) -> None:
    if path.is_symlink():
        raise UnsafeOutputPath(f"refusing to overwrite symbolic link: {path}")
    if path.exists() and not path.is_file():
        raise UnsafeOutputPath(f"refusing to overwrite non-file output: {path}")
