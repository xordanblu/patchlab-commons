#!/usr/bin/env python3
"""Create a hostile consumer repository for the composite-action E2E test."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(repo: Path, *args: str) -> str:
    discovered = shutil.which("git", path=os.environ.get("PATH", os.defpath))
    if discovered is None:
        raise RuntimeError("Git is not available for the action E2E fixture")
    executable = Path(discovered).resolve(strict=True)
    try:
        executable.relative_to(repo)
    except ValueError:
        pass
    else:
        raise RuntimeError("refusing to use Git from inside the hostile fixture")
    return subprocess.run(
        [
            os.fspath(executable),
            "--no-pager",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "core.fsmonitor=false",
            *args,
        ],
        cwd=repo,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        env={
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": tempfile.gettempdir(),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        },
    ).stdout.strip()


def commit(repo: Path, message: str) -> str:
    run(repo, "add", "-A")
    run(repo, "commit", "-m", message)
    return run(repo, "rev-parse", "HEAD")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args()
    repo = Path(args.repository).resolve()
    repo.mkdir(parents=True, exist_ok=True)
    run(repo, "init", "-b", "main")
    run(repo, "config", "user.name", "PatchLab E2E")
    run(repo, "config", "user.email", "patchlab-e2e@example.invalid")
    (repo / "patchlab.toml").write_text(
        """[project]\nname = \"hostile-consumer\"\n[execution]\nmode = \"static\"\n[scope]\nallow = [\"**\"]\n[policy]\nfail_on_review = false\nrequire_human_review = false\n""",
        encoding="utf-8",
    )
    (repo / "value.txt").write_text("base\n", encoding="utf-8")
    base = commit(repo, "base")
    (repo / "value.txt").write_text("head\n", encoding="utf-8")
    payload = "from pathlib import Path\nPath('BOOTSTRAP-HIJACKED').write_text(__name__)\n"
    for path in (
        "pip/__main__.py",
        "patchlab_commons/__main__.py",
        "sitecustomize.py",
        "usercustomize.py",
        "json.py",
    ):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    head = commit(repo, "hostile candidate")
    output = Path(args.github_output) if args.github_output else None
    if output:
        with output.open("a", encoding="utf-8") as handle:
            handle.write(f"base={base}\nhead={head}\n")
    print(f"base={base}")
    print(f"head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
