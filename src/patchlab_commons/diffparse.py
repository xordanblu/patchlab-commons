from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import ChangedFile

_HUNK_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")


@dataclass(frozen=True, slots=True)
class DiffLine:
    kind: str
    text: str
    old_line: int | None
    new_line: int | None


@dataclass(slots=True)
class FileDiff:
    old_path: str | None
    new_path: str | None
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or "unknown"

    def additions(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "+"]

    def deletions(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "-"]


def align_file_diffs(files: list[FileDiff], changed_files: list[ChangedFile]) -> list[FileDiff]:
    """Apply paths from Git's NUL-delimited metadata to parsed diff hunks.

    Unified diff headers use Git's display quoting. NUL-delimited metadata is
    authoritative for names with spaces, quotes, tabs, or non-ASCII bytes.
    Git emits both views in the same file order.
    """

    if len(files) != len(changed_files):
        return files
    for file_diff, changed in zip(files, changed_files, strict=True):
        if changed.status.startswith("A"):
            file_diff.old_path = None
            file_diff.new_path = changed.path
        elif changed.status.startswith("D"):
            file_diff.old_path = changed.path
            file_diff.new_path = None
        else:
            file_diff.old_path = changed.old_path or changed.path
            file_diff.new_path = changed.path
    return files


def parse_unified_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    old_line: int | None = None
    new_line: int | None = None

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split(" ")
            old_path = _strip_prefix(parts[2]) if len(parts) > 2 else None
            new_path = _strip_prefix(parts[3]) if len(parts) > 3 else None
            current = FileDiff(old_path=old_path, new_path=new_path)
            files.append(current)
            old_line = None
            new_line = None
            continue
        if current is None:
            continue
        if raw.startswith("--- "):
            path = raw[4:].strip()
            current.old_path = None if path == "/dev/null" else _strip_prefix(path)
            continue
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current.new_path = None if path == "/dev/null" else _strip_prefix(path)
            continue
        match = _HUNK_RE.match(raw)
        if match:
            old_line = int(match.group("old"))
            new_line = int(match.group("new"))
            continue
        if old_line is None or new_line is None or not raw:
            continue
        marker = raw[0]
        content = raw[1:]
        if marker == "+":
            current.lines.append(DiffLine("+", content, None, new_line))
            new_line += 1
        elif marker == "-":
            current.lines.append(DiffLine("-", content, old_line, None))
            old_line += 1
        elif marker == " ":
            current.lines.append(DiffLine(" ", content, old_line, new_line))
            old_line += 1
            new_line += 1
        elif marker == "\\":
            continue
    return files


def _strip_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
