from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_release import MINIMUM_PUBLISHABLE_VERSION, VERSION_RE


class ReleaseMetadataTests(unittest.TestCase):
    def test_minimum_publishable_version_excludes_historical_release(self) -> None:
        self.assertLess((0, 1, 0), MINIMUM_PUBLISHABLE_VERSION)
        self.assertEqual(MINIMUM_PUBLISHABLE_VERSION, (0, 2, 0))

    def test_release_version_pattern_is_strict(self) -> None:
        self.assertIsNotNone(VERSION_RE.fullmatch("0.2.0"))
        self.assertIsNone(VERSION_RE.fullmatch("v0.2.0"))
        self.assertIsNone(VERSION_RE.fullmatch("0.2.0-alpha"))


class HostedWorkflowContractTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def _read(cls, relative: str) -> str:
        return (cls.ROOT / relative).read_text(encoding="utf-8")

    def test_ci_and_codeql_allow_exact_manual_reruns(self) -> None:
        for relative in (
            ".github/workflows/ci.yml",
            ".github/workflows/codeql.yml",
        ):
            with self.subTest(workflow=relative):
                text = self._read(relative)
                self.assertIn("workflow_dispatch:", text)

    def test_release_verification_has_required_tag_input(self) -> None:
        text = self._read(".github/workflows/release-verification.yml")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("tag:", text)
        self.assertIn("required: true", text)
        self.assertIn("gh release download", text)
        self.assertIn("gh attestation verify", text)

    def test_release_explicitly_dispatches_remote_verification(self) -> None:
        text = self._read(".github/workflows/release.yml")
        self.assertIn("actions: write", text)
        self.assertIn("release-verification.yml/dispatches", text)
        self.assertIn('-f "inputs[tag]=$GITHUB_REF_NAME"', text)
        self.assertLess(
            text.index('gh release create "$GITHUB_REF_NAME"'),
            text.index("release-verification.yml/dispatches"),
        )

    def test_historical_tag_cannot_pass_release_floor(self) -> None:
        text = self._read(".github/workflows/release.yml")
        self.assertIn('python -I scripts/check_release.py --tag "$GITHUB_REF_NAME"', text)
        self.assertIn(
            "test \"$(git rev-parse 'v0.1.0^{commit}')\" = \"7b61eb318f894dbb5f496a77ed3fea669d6707b8\"",
            text,
        )


if __name__ == "__main__":
    unittest.main()
