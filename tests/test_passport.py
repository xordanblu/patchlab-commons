from __future__ import annotations

from pathlib import Path
import tarfile
import tempfile
import unittest

from patchlab.passport import create_passport_bundle, verify_passport_bundle


class PassportTests(unittest.TestCase):
    def identity(self) -> dict[str, str]:
        return {
            "project": "demo",
            "repository": "example/demo",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "outcome": "pass",
            "generated_at": "2026-08-16T00:00:00Z",
            "tool_version": "0.1.0",
            "config_source": "base",
            "config_sha256": "c" * 64,
        }

    def make_output(self) -> Path:
        output = Path(tempfile.mkdtemp())
        (output / "report.json").write_text('{"ok":true}\n', encoding="utf-8")
        (output / "report.md").write_text("# Report\n", encoding="utf-8")
        (output / "results.sarif").write_text('{"version":"2.1.0"}\n', encoding="utf-8")
        return output

    def test_bundle_verifies(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        valid, detail = verify_passport_bundle(result["bundle"])
        self.assertTrue(valid, detail)
        self.assertEqual(detail["identity"]["project"], "demo")

    def test_creation_rejects_invalid_identity(self) -> None:
        output = self.make_output()
        with self.assertRaisesRegex(ValueError, "identity"):
            create_passport_bundle(output, {"project": "demo"})

    def test_creation_rejects_invalid_identity_timestamp(self) -> None:
        output = self.make_output()
        identity = self.identity()
        identity["generated_at"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, "identity"):
            create_passport_bundle(output, identity)

    def test_creation_requires_all_report_files(self) -> None:
        output = self.make_output()
        (output / "report.md").unlink()
        with self.assertRaisesRegex(OSError, "regular file"):
            create_passport_bundle(output, self.identity())

    def test_tampered_bundle_fails(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        bundle = Path(result["bundle"])
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(bundle, "r:gz") as archive:
            archive.extractall(extract, filter="data")
        (extract / "report.md").write_text("tampered\n", encoding="utf-8")
        tampered = output / "tampered.tar.gz"
        with tarfile.open(tampered, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, _ = verify_passport_bundle(tampered)
        self.assertFalse(valid)

    def test_bundle_is_deterministic_for_same_files(self) -> None:
        output = self.make_output()
        first = create_passport_bundle(output, self.identity())
        first_bytes = Path(first["bundle"]).read_bytes()
        second = create_passport_bundle(output, self.identity())
        self.assertEqual(first_bytes, Path(second["bundle"]).read_bytes())

    def test_unexpected_member_is_rejected(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        (extract / "unexpected.txt").write_text("extra", encoding="utf-8")
        changed = output / "unexpected.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertIn("member set", detail["error"])

    def test_invalid_digest_record_is_rejected(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        passport = extract / "passport.json"
        import json
        data = json.loads(passport.read_text(encoding="utf-8"))
        data["artifacts"]["report.json"]["sha256"] = "not-a-digest"
        passport.write_text(json.dumps(data), encoding="utf-8")
        changed = output / "invalid-digest.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertEqual(detail["checks"]["report.json"]["error"], "invalid digest record")

    def test_non_object_identity_is_rejected(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        passport = extract / "passport.json"
        import json
        data = json.loads(passport.read_text(encoding="utf-8"))
        data["identity"] = "untrusted"
        passport.write_text(json.dumps(data), encoding="utf-8")
        changed = output / "invalid-identity.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertIn("identity", detail["error"])

    def test_incomplete_identity_is_rejected(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        passport = extract / "passport.json"
        import json
        data = json.loads(passport.read_text(encoding="utf-8"))
        del data["identity"]["head_sha"]
        passport.write_text(json.dumps(data), encoding="utf-8")
        changed = output / "incomplete-identity.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertIn("identity", detail["error"])

    def test_modified_verification_metadata_is_rejected(self) -> None:
        output = self.make_output()
        result = create_passport_bundle(output, self.identity())
        extract = Path(tempfile.mkdtemp())
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        passport = extract / "passport.json"
        import json
        data = json.loads(passport.read_text(encoding="utf-8"))
        data["verification"]["artifact_input"] = "normalized text"
        passport.write_text(json.dumps(data), encoding="utf-8")
        changed = output / "invalid-verification.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in extract.iterdir():
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertIn("verification", detail["error"])


if __name__ == "__main__":
    unittest.main()
