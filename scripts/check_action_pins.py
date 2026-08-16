#!/usr/bin/env python3
"""Reject mutable external GitHub Action references."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def iter_workflows(root: Path) -> list[Path]:
    paths = list((root / ".github" / "workflows").glob("*.yml"))
    paths.extend((root / ".github" / "workflows").glob("*.yaml"))
    paths.extend((root / "examples").glob("*.yml"))
    paths.extend((root / "examples").glob("*.yaml"))
    return sorted(set(paths))


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in USES_RE.finditer(text):
        reference = match.group(1)
        if reference.startswith("./"):
            continue
        if "@" not in reference:
            errors.append(f"{path}: action reference has no immutable ref: {reference}")
            continue
        _, ref = reference.rsplit("@", 1)
        if not SHA_RE.fullmatch(ref):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path}:{line}: action is not pinned to a 40-character SHA: {reference}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = [error for path in iter_workflows(root) for error in check_file(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"checked {len(iter_workflows(root))} workflow example(s); all external actions use full SHAs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
