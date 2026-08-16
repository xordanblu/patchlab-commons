from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from patchlab_commons.engine import VerificationEngine, VerificationRequest
from patchlab_commons.schema import passport_schema, report_schema
from tests.helpers import commit_all, init_repo

try:
    import jsonschema
except ImportError:  # pragma: no cover - runtime has no dependency on jsonschema
    jsonschema = None


class SchemaContractTests(unittest.TestCase):
    def test_committed_schemas_match_generators(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            json.loads((root / "docs" / "report.schema.json").read_text(encoding="utf-8")),
            report_schema(),
        )
        self.assertEqual(
            json.loads((root / "docs" / "passport.schema.json").read_text(encoding="utf-8")),
            passport_schema(),
        )

    def test_schema_has_strict_public_objects(self) -> None:
        schema = report_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["finding"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["commandResult"]["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1.0")

    def test_passport_schema_has_strict_manifest_objects(self) -> None:
        schema = passport_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["identity"]["additionalProperties"])
        self.assertFalse(schema["properties"]["artifacts"]["additionalProperties"])

    @unittest.skipIf(jsonschema is None, "jsonschema is an optional development dependency")
    def test_real_report_validates_against_public_schema(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "repo"
        init_repo(repo)
        (repo / "patchlab.toml").write_text(
            """[project]\nname = "schema-demo"\n[scope]\nallow = ["**"]\n[policy]\n""",
            encoding="utf-8",
        )
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "file.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")
        result = VerificationEngine().verify(
            VerificationRequest(repo, Path("patchlab.toml"), base, head, Path("out"))
        )
        report = json.loads(Path(result.artifacts["json"]).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(report_schema()).validate(report)


if __name__ == "__main__":
    unittest.main()
