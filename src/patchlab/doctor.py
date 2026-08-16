from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import shutil
import sys
from typing import Any

from .config import ConfigError, load_config
from .gitutils import GitError, GitRepo


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_doctor(repository: Path, config_path: Path) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    checks.append(
        DoctorCheck(
            "python",
            sys.version_info >= (3, 11),
            f"Python {sys.version.split()[0]} (requires 3.11 or newer)",
        )
    )
    git_path = shutil.which("git")
    checks.append(DoctorCheck("git", bool(git_path), git_path or "git was not found on PATH"))
    try:
        repo = GitRepo(repository)
        checks.append(DoctorCheck("repository", True, str(repo.path)))
        clean = repo.is_clean()
        checks.append(
            DoctorCheck(
                "working-tree",
                clean,
                "clean" if clean else "uncommitted changes present",
            )
        )
    except GitError as exc:
        repo = None
        checks.append(DoctorCheck("repository", False, str(exc)))
    actual_config = config_path
    if repo is not None and not actual_config.is_absolute():
        actual_config = repo.path / actual_config
    try:
        config = load_config(actual_config)
        checks.append(
            DoctorCheck(
                "configuration",
                True,
                f"valid configuration for {config.project_name}",
            )
        )
    except ConfigError as exc:
        checks.append(DoctorCheck("configuration", False, str(exc)))
    return checks
