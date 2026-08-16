from __future__ import annotations

import io
import runpy
import sys
import unittest
from unittest.mock import patch

from patchlab.checks import network, scope, secrets, tests, workflows
from patchlab.models import Disposition, Severity


class InternalEdgeTests(unittest.TestCase):
    def test_check_severity_mappings_are_consistent(self) -> None:
        modules = (network, scope, secrets, tests, workflows)
        for module in modules:
            with self.subTest(module=module.__name__):
                self.assertEqual(module._severity(Disposition.DENY), Severity.ERROR)
                self.assertEqual(module._severity(Disposition.REVIEW), Severity.WARNING)
                self.assertEqual(module._severity(Disposition.ALLOW), Severity.INFO)

    def test_checkout_setting_handles_boundaries_and_values(self) -> None:
        workflow = """steps:
  - uses: actions/checkout@0123456789012345678901234567890123456789
    # keep the token out of the worktree
    with:
      persist-credentials: false
  - run: echo done
"""
        self.assertIsNone(workflows._checkout_setting(workflow, None))
        self.assertIsNone(workflows._checkout_setting(workflow, 99))
        self.assertFalse(workflows._checkout_setting(workflow, 2))
        self.assertTrue(
            workflows._checkout_setting(
                workflow.replace("persist-credentials: false", "persist-credentials: TRUE"),
                2,
            )
        )
        self.assertIsNone(
            workflows._checkout_setting(
                workflow.replace("      persist-credentials: false\n", ""),
                2,
            )
        )

    def test_module_entrypoint_calls_cli(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["patchlab", "--version"]), patch(
            "sys.stdout",
            output,
        ), self.assertRaises(SystemExit) as raised:
            runpy.run_module("patchlab", run_name="__main__")
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("PatchLab Commons 0.1.0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
