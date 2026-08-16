from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchlab_commons.config import ConfigError
from patchlab_commons.engine import VerificationEngine, VerificationRequest
from patchlab_commons.models import Outcome
from patchlab_commons.runner import ExecutionUnavailable, ExecutorSelection
from tests.helpers import commit_all, init_repo


class EngineExecutionTests(unittest.TestCase):
    def _repo(self, config: str) -> tuple[Path, str, str]:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "patchlab.toml").write_text(config, encoding="utf-8")
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "file.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")
        return repo, base, head

    def test_static_mode_reports_commands_as_unexecuted(self) -> None:
        repo, base, head = self._repo(
            """[project]\nname = \"static\"\n[execution]\nmode = \"static\"\n[scope]\nallow = [\"**\"]\n[policy]\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-V\"]\n"""
        )
        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        self.assertEqual(result.report.outcome, Outcome.NEEDS_REVIEW)
        self.assertEqual(result.report.summary["commands"], 0)
        self.assertIn("PL-EXEC-002", {item.rule_id for item in result.report.findings})
        self.assertEqual(result.report.metadata["execution_boundary"], "static-no-execution")

    def test_unavailable_auto_executor_is_blocking_without_native_fallback(self) -> None:
        image = "python@sha256:" + ("a" * 64)
        repo, base, head = self._repo(
            f"""[project]\nname = \"auto\"\n[execution]\nmode = \"auto\"\ncontainer_image = \"{image}\"\n[scope]\nallow = [\"**\"]\n[policy]\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-V\"]\n"""
        )
        with patch("patchlab_commons.runner._find_container_runtime", return_value=("", "")):
            result = VerificationEngine().verify(
                VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
            )
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        self.assertIn("PL-EXEC-001", {item.rule_id for item in result.report.findings})
        self.assertEqual(result.report.summary["commands"], 0)

    def test_container_network_access_requires_review(self) -> None:
        image = "python@sha256:" + ("a" * 64)
        repo, base, head = self._repo(
            f"""[project]\nname = \"network\"\n[execution]\nmode = \"container\"\ncontainer_image = \"{image}\"\nnetwork = true\n[scope]\nallow = [\"**\"]\n[policy]\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-V\"]\n"""
        )
        selected = ExecutorSelection(
            mode="container",
            runtime_name="docker",
            runtime_path="/usr/bin/docker",
            container_image=image,
            network=True,
            memory_mb=128,
            cpus=1.0,
            pids_limit=16,
            tmpfs_mb=8,
        )
        with (
            patch("patchlab_commons.engine.select_executor", return_value=selected),
            patch(
                "patchlab_commons.engine.run_command",
                side_effect=ExecutionUnavailable("runtime rejected secure flags"),
            ),
        ):
            result = VerificationEngine().verify(
                VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
            )
        ids = {item.rule_id for item in result.report.findings}
        self.assertIn("PL-EXEC-003", ids)
        self.assertIn("PL-EXEC-001", ids)
        self.assertEqual(result.report.outcome, Outcome.FAIL)
        self.assertTrue(result.report.metadata["network_enabled"])

    def test_native_metadata_records_unrestricted_network(self) -> None:
        repo, base, head = self._repo(
            """[project]\nname = \"native\"\n[execution]\nmode = \"native\"\nallow_unsafe_native = true\n[scope]\nallow = [\"**\"]\n[policy]\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-c\", \"print('ok')\"]\n"""
        )
        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        self.assertEqual(result.report.outcome, Outcome.PASS)
        self.assertTrue(result.report.metadata["network_enabled"])
        self.assertEqual(result.report.metadata["execution_boundary"], "weak-native")
        self.assertTrue(result.report.command_results[0].network_enabled)

    def test_library_execution_overrides_are_validated(self) -> None:
        repo, base, head = self._repo(
            """[project]\nname = \"override\"\n[scope]\nallow = [\"**\"]\n[policy]\n"""
        )
        cases = (
            {"execution_mode": "magic"},
            {"container_runtime": "nerdctl"},
            {"network": "false"},
            {"allow_unsafe_native": "true"},
            {"container_image": "python:latest"},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                request = VerificationRequest(
                    repo,
                    Path("patchlab.toml"),
                    base,
                    head,
                    Path("out"),
                    **updates,
                )
                with self.assertRaises(ConfigError):
                    VerificationEngine().verify(request)

    def test_working_tree_config_cannot_escape_the_repository(self) -> None:
        repo, base, head = self._repo(
            """[project]\nname = \"inside\"\n[scope]\nallow = [\"**\"]\n[policy]\n"""
        )
        outside = Path(tempfile.mkdtemp()) / "outside.toml"
        outside.write_text(
            """[project]\nname = \"outside\"\n[scope]\nallow = [\"**\"]\n[policy]\n""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigError, "stay inside"):
            VerificationEngine().verify(
                VerificationRequest(
                    repo,
                    outside,
                    base,
                    head,
                    Path("out"),
                    config_source="working-tree",
                )
            )

    @unittest.skipIf(os.name == "nt", "symbolic-link creation is not reliable on Windows")
    def test_working_tree_config_rejects_symbolic_links(self) -> None:
        repo, base, head = self._repo(
            """[project]\nname = \"inside\"\n[scope]\nallow = [\"**\"]\n[policy]\n"""
        )
        target = repo / "trusted.toml"
        target.write_text(
            """[project]\nname = \"linked\"\n[scope]\nallow = [\"**\"]\n[policy]\n""",
            encoding="utf-8",
        )
        link = repo / "linked.toml"
        link.symlink_to(target.name)
        with self.assertRaisesRegex(ConfigError, "symbolic links"):
            VerificationEngine().verify(
                VerificationRequest(
                    repo,
                    Path("linked.toml"),
                    base,
                    head,
                    Path("out"),
                    config_source="working-tree",
                )
            )


if __name__ == "__main__":
    unittest.main()
