#!/usr/bin/env python3
"""Check release metadata consistency before a tag is published."""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MINIMUM_PUBLISHABLE_VERSION = (0, 2, 0)


def _module_version(path: Path) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, str):
                        return value
    raise ValueError(f"no string __version__ found in {path}")


def _cff_value(path: Path, key: str) -> str:
    prefix = f"{key}:"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().strip('"')
    raise ValueError(f"{key} is missing from {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    versions = {
        "pyproject.toml": project["version"],
        "_version.py": _module_version(root / "src" / "patchlab_commons" / "_version.py"),
        "CITATION.cff": _cff_value(root / "CITATION.cff", "version"),
    }
    unique = set(versions.values())
    errors: list[str] = []
    if len(unique) != 1:
        errors.append(
            "version mismatch: " + ", ".join(f"{key}={value}" for key, value in versions.items())
        )
    version = next(iter(unique)) if len(unique) == 1 else ""
    if version and not VERSION_RE.fullmatch(version):
        errors.append(f"version is not stable SemVer: {version}")
    if version and VERSION_RE.fullmatch(version):
        parsed = tuple(int(part) for part in version.split("."))
        if parsed < MINIMUM_PUBLISHABLE_VERSION:
            minimum = ".".join(str(part) for part in MINIMUM_PUBLISHABLE_VERSION)
            errors.append(
                f"version {version} is historical and must not be published; minimum is {minimum}"
            )
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if version and f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md has no [{version}] release section")
    release_notes = (root / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    if version and version not in release_notes:
        errors.append(f"RELEASE-NOTES.md does not identify version {version}")
    expected_tag = f"v{version}" if version else ""
    tag = args.tag.removeprefix("refs/tags/")
    if tag and tag != expected_tag:
        errors.append(f"tag {tag!r} does not match version {expected_tag!r}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"release metadata is consistent for {expected_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
