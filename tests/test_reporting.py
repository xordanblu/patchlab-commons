from __future__ import annotations

import unittest

from patchlab.models import ChangedFile, Outcome, VerificationReport
from patchlab.reporting import render_markdown


class ReportingTests(unittest.TestCase):
    def report(self, path: str) -> VerificationReport:
        return VerificationReport(
            schema_version="1.0.0",
            tool_version="0.1.0",
            project_name="demo",
            generated_at="2026-08-16T00:00:00Z",
            repository="example/demo",
            base_ref="base",
            base_sha="a" * 40,
            head_ref="head",
            head_sha="b" * 40,
            outcome=Outcome.PASS,
            summary={
                "changed_files": 1,
                "commands": 0,
                "commands_passed": 0,
                "findings": 0,
                "blocking_findings": 0,
                "review_findings": 0,
            },
            changed_files=[ChangedFile(status="A", path=path, added_lines=1, deleted_lines=0)],
        )

    def test_malicious_filename_stays_inside_code_span(self) -> None:
        markdown = render_markdown(self.report("` ![track](https://example.invalid/x) | name.py"))
        changed_line = next(line for line in markdown.splitlines() if "track" in line)
        self.assertIn("`` ` ![track](https://example.invalid/x) \\| name.py ``", changed_line)

    def test_multiline_filename_is_flattened(self) -> None:
        markdown = render_markdown(self.report("first\nsecond.py"))
        changed_line = next(line for line in markdown.splitlines() if "first" in line)
        self.assertIn("first second.py", changed_line)
        self.assertEqual(changed_line.count("|"), 5)


if __name__ == "__main__":
    unittest.main()
