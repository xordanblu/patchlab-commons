from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchlab.config import CommandConfig
from patchlab.runner import run_command, sanitized_environment


class RunnerTests(unittest.TestCase):
    def test_secret_environment_is_removed(self) -> None:
        with patch.dict(os.environ, {"DEMO_TOKEN": "hidden", "SAFE_VALUE": "visible"}, clear=False):
            env = sanitized_environment()
        self.assertNotIn("DEMO_TOKEN", env)
        self.assertNotIn("SAFE_VALUE", env)

    def test_explicit_environment_can_be_allowed(self) -> None:
        with patch.dict(os.environ, {"DEMO_TOKEN": "allowed"}, clear=False):
            env = sanitized_environment(("DEMO_TOKEN",))
        self.assertEqual(env["DEMO_TOKEN"], "allowed")

    def test_base_nonzero_head_zero_policy(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="result",
            command=("python", "-c", "raise SystemExit(1)"),
            run_on="both",
            expected_exit="base_nonzero_head_zero",
        )
        self.assertTrue(run_command(command, "base", cwd).passed)
        self.assertFalse(run_command(command, "head", cwd).passed)

    def test_timeout_is_reported(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="timeout",
            command=("python", "-c", "import time; time.sleep(2)"),
            timeout_seconds=1,
        )
        result = run_command(command, "head", cwd)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.passed)
        self.assertIn("terminated", result.stderr)

    def test_missing_program_is_reported(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(name="missing", command=("patchlab-program-that-does-not-exist",))
        result = run_command(command, "head", cwd)
        self.assertIsNone(result.exit_code)
        self.assertFalse(result.passed)
        self.assertIn("could not start", result.stderr)

    def test_nonzero_policy_passes(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="expected-failure",
            command=("python", "-c", "raise SystemExit(3)"),
            expected_exit="nonzero",
        )
        self.assertTrue(run_command(command, "head", cwd).passed)

    def test_command_uses_disposable_home(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="home",
            command=("python", "-c", "import os; print(os.environ['HOME'])"),
        )
        result = run_command(command, "head", cwd)
        self.assertTrue(result.passed)
        self.assertIn("patchlab-home-", result.stdout)
        self.assertNotEqual(result.stdout.strip(), os.environ.get("HOME"))

    def test_output_redacts_common_secret_forms(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="redact",
            command=(
                "python",
                "-c",
                "print('Authorization: Bearer abcdefghijklmnop'); print('api_key=supersecretvalue')",
            ),
        )
        result = run_command(command, "head", cwd)
        self.assertTrue(result.passed)
        self.assertNotIn("abcdefghijklmnop", result.stdout)
        self.assertNotIn("supersecretvalue", result.stdout)
        self.assertGreaterEqual(result.stdout.count("[REDACTED]"), 2)

    def test_output_redacts_url_credentials_and_query_tokens(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="url-redact",
            command=(
                "python",
                "-c",
                (
                    "print('https://alice:verysecret@example.com/path?token=hiddenvalue&safe=1'); "
                    "print('https://example.com/path?api_key=anothersecret')"
                ),
            ),
        )
        result = run_command(command, "head", cwd)
        self.assertTrue(result.passed)
        self.assertNotIn("alice", result.stdout)
        self.assertNotIn("verysecret", result.stdout)
        self.assertNotIn("hiddenvalue", result.stdout)
        self.assertNotIn("anothersecret", result.stdout)
        self.assertIn("https://example.com/path?token=[REDACTED]&safe=1", result.stdout)

    def test_large_output_is_bounded_and_keeps_both_ends(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        command = CommandConfig(
            name="large",
            command=("python", "-c", "print('START'); print('x' * 40000); print('END')"),
        )
        result = run_command(command, "head", cwd)
        self.assertTrue(result.passed)
        self.assertIn("START", result.stdout)
        self.assertIn("END", result.stdout)
        self.assertIn("omitted", result.stdout)
        self.assertLess(len(result.stdout), 25_000)


if __name__ == "__main__":
    unittest.main()
