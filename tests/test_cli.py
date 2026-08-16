from __future__ import annotations

from pathlib import Path
import io
import tempfile
import unittest
from contextlib import redirect_stdout

from patchlab_commons.cli import main
from patchlab_commons.passport import create_passport_bundle

from tests.helpers import commit_all, init_repo


class CliTests(unittest.TestCase):
    def identity(self) -> dict[str, str]:
        return {
            "project": "cli",
            "repository": "example/cli",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "outcome": "pass",
            "generated_at": "2026-08-16T00:00:00Z",
            "tool_version": "0.1.0",
            "config_source": "base",
            "config_sha256": "c" * 64,
        }

    def test_init_creates_config_and_workflow(self) -> None:
        directory = Path(tempfile.mkdtemp())
        code = main(["init", "--directory", str(directory)])
        self.assertEqual(code, 0)
        self.assertTrue((directory / "patchlab.toml").exists())
        self.assertTrue((directory / ".github" / "workflows" / "patchlab.yml").exists())

    def test_schema_writes_file(self) -> None:
        output = Path(tempfile.mkdtemp()) / "schema.json"
        code = main(["schema", "--output", str(output)])
        self.assertEqual(code, 0)
        self.assertIn('"schema_version"', output.read_text(encoding="utf-8"))

    def test_doctor_json_for_non_repository(self) -> None:
        directory = Path(tempfile.mkdtemp())
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["doctor", "--repo", str(directory), "--json"])
        self.assertEqual(code, 1)
        self.assertIn('"repository"', output.getvalue())

    def test_doctor_plain_text_for_valid_repository(self) -> None:
        directory = Path(tempfile.mkdtemp()) / "repo"
        init_repo(directory)
        (directory / "patchlab.toml").write_text(
            '[project]\nname = "doctor"\n',
            encoding="utf-8",
        )
        commit_all(directory, "base")
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["doctor", "--repo", str(directory), "--config", "patchlab.toml"])
        self.assertEqual(code, 0)
        self.assertIn("[PASS] repository", output.getvalue())

    def test_verify_passport_json(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "report.json").write_text("{}\n", encoding="utf-8")
        (directory / "report.md").write_text("# report\n", encoding="utf-8")
        (directory / "results.sarif").write_text("{}\n", encoding="utf-8")
        bundle = create_passport_bundle(directory, self.identity())["bundle"]
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["verify-passport", bundle, "--json"])
        self.assertEqual(code, 0)
        self.assertIn('"valid": true', output.getvalue())

    def test_invalid_passport_plain_text(self) -> None:
        missing = Path(tempfile.mkdtemp()) / "missing.tar.gz"
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["verify-passport", str(missing)])
        self.assertEqual(code, 1)
        self.assertIn("INVALID", output.getvalue())
        self.assertIn("Error:", output.getvalue())

    def test_verify_command_reports_pass_and_fail(self) -> None:
        directory = Path(tempfile.mkdtemp()) / "repo"
        init_repo(directory)
        (directory / "patchlab.toml").write_text(
            '[project]\nname = "cli-verify"\n[scope]\nallow = ["**"]\n[policy]\n',
            encoding="utf-8",
        )
        (directory / "value.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(directory, "base")
        (directory / "value.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(directory, "head")

        passed_output = io.StringIO()
        with redirect_stdout(passed_output):
            passed = main(
                [
                    "verify",
                    "--repo",
                    str(directory),
                    "--base",
                    base,
                    "--head",
                    head,
                    "--output",
                    "out/pass",
                ]
            )
        self.assertEqual(passed, 0)
        self.assertIn("PatchLab outcome: pass", passed_output.getvalue())

        failed_output = io.StringIO()
        with redirect_stdout(failed_output):
            failed = main(
                [
                    "verify",
                    "--repo",
                    str(directory),
                    "--base",
                    head,
                    "--head",
                    head,
                    "--output",
                    "out/fail",
                ]
            )
        self.assertEqual(failed, 1)
        self.assertIn("PatchLab outcome: fail", failed_output.getvalue())

    def test_schema_prints_to_stdout(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["schema"])
        self.assertEqual(code, 0)
        self.assertIn('PatchLab Patch Passport Report', output.getvalue())

    def test_passport_schema_prints_to_stdout(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["schema", "--kind", "passport"])
        self.assertEqual(code, 0)
        self.assertIn("PatchLab Patch Passport Manifest", output.getvalue())

    def test_init_refuses_overwrite(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.assertEqual(main(["init", "--directory", str(directory), "--no-github"]), 0)
        self.assertEqual(main(["init", "--directory", str(directory), "--no-github"]), 1)

    def test_init_workflow_uses_published_action_without_installing_target(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.assertEqual(main(["init", "--directory", str(directory)]), 0)
        workflow = (directory / ".github" / "workflows" / "patchlab.yml").read_text(encoding="utf-8")
        self.assertIn("uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5", workflow)
        self.assertIn("config-source: base", workflow)
        self.assertNotIn("pip install -e .", workflow)
        self.assertIn("persist-credentials: false", workflow)


if __name__ == "__main__":
    unittest.main()
