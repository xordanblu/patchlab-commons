from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patchlab_commons.doctor import run_doctor
from tests.helpers import commit_all, init_repo


class DoctorTests(unittest.TestCase):
    def test_valid_repository_and_config(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "patchlab.toml").write_text('[project]\nname = "doctor"\n', encoding="utf-8")
        commit_all(repo, "seed")
        checks = {item.name: item for item in run_doctor(repo, Path("patchlab.toml"))}
        self.assertTrue(checks["python"].ok)
        self.assertTrue(checks["git"].ok)
        self.assertTrue(checks["repository"].ok)
        self.assertTrue(checks["working-tree"].ok)
        self.assertTrue(checks["configuration"].ok)

    def test_invalid_repository_and_config(self) -> None:
        directory = Path(tempfile.mkdtemp())
        checks = {item.name: item for item in run_doctor(directory, Path("missing.toml"))}
        self.assertFalse(checks["repository"].ok)
        self.assertFalse(checks["configuration"].ok)


if __name__ == "__main__":
    unittest.main()
