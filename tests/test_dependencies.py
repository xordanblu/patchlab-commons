from __future__ import annotations

import unittest

from patchlab_commons.checks.dependencies import _dependency_delta, _parse_dependencies


class DependencyParserTests(unittest.TestCase):
    def test_package_json_delta(self) -> None:
        before = '{"dependencies":{"alpha":"1.0.0","old":"1"}}'
        after = '{"dependencies":{"alpha":"2.0.0","new":"1"}}'
        detail = _dependency_delta("package.json", before, after)
        self.assertIn("Added: new", detail or "")
        self.assertIn("Removed: old", detail or "")
        self.assertIn("Version changed: alpha", detail or "")

    def test_pyproject_dependencies(self) -> None:
        text = """
[project]
dependencies = ["requests>=2", "demo[extra]==1"]
[project.optional-dependencies]
dev = ["coverage~=7"]
"""
        parsed = _parse_dependencies("pyproject.toml", text)
        self.assertEqual(set(parsed or {}), {"requests", "demo", "coverage"})

    def test_requirements_dependencies(self) -> None:
        text = """
# comment
requests==2.0
-r base.txt
httpx[http2]>=0.27 ; python_version >= '3.11'
"""
        parsed = _parse_dependencies("requirements.txt", text)
        self.assertEqual(set(parsed or {}), {"requests", "httpx"})

    def test_cargo_dependencies(self) -> None:
        text = """
[dependencies]
serde = "1"
[dev-dependencies]
tempfile = { version = "3" }
"""
        parsed = _parse_dependencies("Cargo.toml", text)
        self.assertEqual(set(parsed or {}), {"serde", "tempfile"})

    def test_go_mod_dependencies(self) -> None:
        text = """
module example.invalid/demo
require example.invalid/one v1.2.3
require (
  example.invalid/two v2.0.0
)
"""
        parsed = _parse_dependencies("go.mod", text)
        self.assertEqual(
            parsed,
            {
                "example.invalid/one": "v1.2.3",
                "example.invalid/two": "v2.0.0",
            },
        )

    def test_added_and_removed_manifest(self) -> None:
        self.assertEqual(
            _dependency_delta("package.json", None, '{"dependencies":{}}'),
            "The dependency file was added.",
        )
        self.assertEqual(
            _dependency_delta("package.json", '{"dependencies":{}}', None),
            "The dependency file was removed.",
        )

    def test_invalid_or_unsupported_returns_none(self) -> None:
        self.assertIsNone(_dependency_delta("package.json", "{", "{}"))
        self.assertIsNone(_parse_dependencies("yarn.lock", "data"))
        self.assertIsNone(_dependency_delta("yarn.lock", "old", "new"))


if __name__ == "__main__":
    unittest.main()
