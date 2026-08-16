#!/usr/bin/env python3
"""Generate a small deterministic SPDX 2.3 SBOM for PatchLab Commons."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import tomllib


_GIT_TIMEOUT_SECONDS = 60


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


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [
                _git_executable(root),
                "--no-pager",
                "--literal-pathspecs",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "protocol.file.allow=never",
                *args,
            ],
            cwd=root,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            start_new_session=os.name != "nt",
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "HOME": tempfile.gettempdir(),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_COUNT": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "LC_ALL": "C",
                "LANG": "C",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Git command exceeded {_GIT_TIMEOUT_SECONDS} seconds: {args[0] if args else 'git'}"
        ) from exc
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    requested_output = Path(args.output)
    output = _inside_root(
        root,
        requested_output if requested_output.is_absolute() else root / requested_output,
        "SBOM output",
    )
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    commit = _git(root, "rev-parse", "HEAD^{commit}")
    epoch_raw = os.environ.get("SOURCE_DATE_EPOCH") or _git(
        root, "show", "-s", "--format=%ct", commit
    )
    epoch = int(epoch_raw)
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must not be negative")
    created = datetime.fromtimestamp(epoch, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    namespace_seed = f"{project['name']}:{project['version']}:{commit}".encode()
    namespace = hashlib.sha256(namespace_seed).hexdigest()
    package_spdx = "SPDXRef-Package-patchlab-commons"
    document = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "name": f"{project['name']}-{project['version']}",
        "documentNamespace": f"https://github.com/xordanblu/patchlab-commons/spdx/{namespace}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: patchlab-commons/scripts/generate_sbom.py"],
            "licenseListVersion": "3.26",
        },
        "documentDescribes": [package_spdx],
        "packages": [
            {
                "SPDXID": package_spdx,
                "name": project["name"],
                "versionInfo": project["version"],
                "downloadLocation": "https://github.com/xordanblu/patchlab-commons",
                "filesAnalyzed": False,
                "licenseConcluded": "Apache-2.0",
                "licenseDeclared": "Apache-2.0",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{project['name']}@{project['version']}",
                    },
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "vcs",
                        "referenceLocator": f"git+https://github.com/xordanblu/patchlab-commons@{commit}",
                    },
                ],
            }
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": package_spdx,
            }
        ],
        "annotations": [
            {
                "annotationDate": created,
                "annotationType": "OTHER",
                "annotator": "Tool: patchlab-commons/scripts/generate_sbom.py",
                "comment": "The Python distribution declares zero third-party runtime dependencies.",
            }
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
