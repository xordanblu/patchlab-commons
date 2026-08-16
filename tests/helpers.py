from __future__ import annotations

from pathlib import Path
import subprocess


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {process.stderr}")
    return process.stdout.strip()


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "PatchLab Test")
    git(repo, "config", "user.email", "patchlab@example.invalid")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")
