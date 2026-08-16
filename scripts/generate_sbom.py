#!/usr/bin/env python3
"""Generate a small deterministic SPDX 2.3 SBOM for PatchLab Commons."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=root,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": __import__("os").defpath, "LC_ALL": "C", "LANG": "C"},
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    commit = _git(root, "rev-parse", "HEAD")
    epoch = int(__import__("os").environ.get("SOURCE_DATE_EPOCH", "0"))
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
