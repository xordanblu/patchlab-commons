from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patchlab_commons.config import DEFAULT_CONFIG, ConfigError, load_config
from patchlab_commons.models import Disposition


class ConfigTests(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "patchlab.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_default_config_is_valid(self) -> None:
        config = load_config(self.write(DEFAULT_CONFIG))
        self.assertEqual(config.project_name, "my-project")
        self.assertEqual(len(config.commands), 2)
        self.assertEqual(config.policy.secret_exposure, Disposition.DENY)

    def test_rejects_missing_project_name(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(self.write("[project]\n"))

    def test_rejects_shell_string_command(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = "pytest | tee output.txt"
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_scope_deny_wins(self) -> None:
        text = """
[project]
name = "scope"
[scope]
allow = ["**"]
deny = ["secrets/**"]
"""
        config = load_config(self.write(text))
        self.assertTrue(config.scope.allowed("src/app.py"))
        self.assertFalse(config.scope.allowed("secrets/key.pem"))

    def test_explicit_empty_allow_list_denies_all_paths(self) -> None:
        text = """
[project]
name = "locked"
[scope]
allow = []
"""
        config = load_config(self.write(text))
        self.assertFalse(config.scope.allowed("src/app.py"))

    def test_rejects_unknown_disposition(self) -> None:
        text = """
[project]
name = "bad"
[policy]
network_additions = "maybe"
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_rejects_string_boolean(self) -> None:
        text = """
[project]
name = "bad"
[policy]
fail_on_review = "false"
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_rejects_string_required_flag(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = ["python", "-V"]
required = "false"
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_rejects_empty_program_name(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = [""]
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_rejects_invalid_environment_name(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = ["python", "-V"]
allow_env = ["GOOD_NAME", "BAD=NAME"]
"""
        with self.assertRaises(ConfigError):
            load_config(self.write(text))

    def test_rejects_unknown_policy_key(self) -> None:
        text = """
[project]
name = "bad"
[policy]
secret_expsoure = "deny"
"""
        with self.assertRaisesRegex(ConfigError, "unknown key"):
            load_config(self.write(text))

    def test_rejects_unknown_command_key(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = ["python", "-V"]
timeout = 10
"""
        with self.assertRaisesRegex(ConfigError, "unknown key"):
            load_config(self.write(text))

    def test_reproduction_expectation_requires_both_revisions(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "regression"
command = ["python", "-V"]
run_on = "head"
expected_exit = "base_nonzero_head_zero"
"""
        with self.assertRaisesRegex(ConfigError, "run_on = 'both'"):
            load_config(self.write(text))

    def test_trimmed_duplicate_command_names_are_rejected(self) -> None:
        text = """
[project]
name = "bad"
[[commands]]
name = "tests"
command = ["python", "-V"]
[[commands]]
name = " tests "
command = ["python", "-V"]
"""
        with self.assertRaisesRegex(ConfigError, "duplicate command"):
            load_config(self.write(text))


if __name__ == "__main__":
    unittest.main()
