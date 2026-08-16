from __future__ import annotations

import unittest

from patchlab_commons.config import (
    ConfigError,
    DEFAULT_CONFIG,
    is_pinned_container_image,
    load_config_text,
)


_DIGEST = "a" * 64


class ExecutionConfigTests(unittest.TestCase):
    def test_default_configuration_never_executes_project_code(self) -> None:
        config = load_config_text(DEFAULT_CONFIG)
        self.assertEqual(config.execution.mode, "static")
        self.assertFalse(config.execution.allow_unsafe_native)
        self.assertFalse(config.execution.network)

    def test_native_mode_requires_explicit_weak_boundary_acknowledgement(self) -> None:
        text = """[project]\nname = \"demo\"\n[execution]\nmode = \"native\"\n"""
        with self.assertRaisesRegex(ConfigError, "allow_unsafe_native"):
            load_config_text(text)

    def test_mutable_container_tag_is_rejected(self) -> None:
        text = """[project]\nname = \"demo\"\n[execution]\nmode = \"container\"\ncontainer_image = \"python:3.14\"\n"""
        with self.assertRaisesRegex(ConfigError, "immutable"):
            load_config_text(text)

    def test_digest_pinned_container_image_is_accepted(self) -> None:
        image = f"python@sha256:{_DIGEST}"
        text = f"""[project]\nname = \"demo\"\n[execution]\nmode = \"container\"\ncontainer_image = \"{image}\"\n"""
        config = load_config_text(text)
        self.assertEqual(config.execution.container_image, image)
        self.assertTrue(is_pinned_container_image(image))
        self.assertTrue(is_pinned_container_image(f"sha256:{_DIGEST}"))
        self.assertFalse(is_pinned_container_image("python:latest"))

    def test_container_mode_requires_image(self) -> None:
        with self.assertRaisesRegex(ConfigError, "required"):
            load_config_text(
                """[project]\nname = \"demo\"\n[execution]\nmode = \"container\"\n"""
            )

    def test_credential_like_allowed_environment_is_rejected(self) -> None:
        text = """[project]\nname = \"demo\"\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-V\"]\nallow_env = [\"SAFE_VALUE\", \"GITHUB_TOKEN\"]\n"""
        with self.assertRaisesRegex(ConfigError, "credential-like"):
            load_config_text(text)

    def test_duplicate_allowed_environment_is_rejected(self) -> None:
        text = """[project]\nname = \"demo\"\n[[commands]]\nname = \"test\"\ncommand = [\"python\", \"-V\"]\nallow_env = [\"SAFE_VALUE\", \"SAFE_VALUE\"]\n"""
        with self.assertRaisesRegex(ConfigError, "duplicate"):
            load_config_text(text)

    def test_invalid_execution_values_are_rejected(self) -> None:
        cases = (
            ("mode = \"magic\"", "execution.mode"),
            ("container_runtime = \"nerdctl\"", "container_runtime"),
            ("network = \"false\"", "execution.network"),
            ("memory_mb = 0", "memory_mb"),
            ("cpus = false", "cpus"),
            ("pids_limit = -1", "pids_limit"),
            ("tmpfs_mb = 0", "tmpfs_mb"),
        )
        for setting, message in cases:
            with self.subTest(setting=setting):
                text = f"[project]\nname = \"demo\"\n[execution]\n{setting}\n"
                with self.assertRaisesRegex(ConfigError, message):
                    load_config_text(text)

    def test_unknown_execution_key_is_rejected(self) -> None:
        text = """[project]\nname = \"demo\"\n[execution]\nnetworking = false\n"""
        with self.assertRaisesRegex(ConfigError, "unknown key"):
            load_config_text(text)


if __name__ == "__main__":
    unittest.main()
