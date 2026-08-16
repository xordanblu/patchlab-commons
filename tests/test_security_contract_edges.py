from __future__ import annotations

import gzip
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from patchlab_commons import passport as passport_module
from patchlab_commons.config import ConfigError, load_config_text
from patchlab_commons.gitutils import (
    GitError,
    _ensure_parent_directories,
    _parse_tree_entries,
    _validate_link_target,
    _validate_snapshot_path,
    _write_snapshot_link,
)
from patchlab_commons.passport import (
    _BytesReader,
    _MAX_MEMBER_BYTES,
    _read_member,
    _valid_artifact_spec,
    _valid_identity,
    _valid_timestamp,
    create_passport_bundle,
    verify_passport_bundle,
)


class ConfigurationEdgeTests(unittest.TestCase):
    def test_invalid_toml_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "invalid TOML"):
            load_config_text("[project\nname='bad'")

    def test_tables_and_command_array_types_are_strict(self) -> None:
        cases = (
            ("project = []\n", "TOML table"),
            ('commands = {}\n[project]\nname="x"\n', "array of tables"),
            ('commands = ["bad"]\n[project]\nname="x"\n', "must be a table"),
        )
        for text, message in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ConfigError, message):
                    load_config_text(text)

    def test_command_scalar_fields_are_strict(self) -> None:
        base = '[project]\nname="x"\n[[commands]]\nname="c"\ncommand=["python"]\n'
        cases = (
            ("run_on = 1\n", "run_on must be a string"),
            ('run_on = "elsewhere"\n', "run_on must be base, head, or both"),
            ("expected_exit = 1\n", "expected_exit must be a string"),
            ('expected_exit = "sometimes"\n', "expected_exit must be zero"),
            ('command = ["python", "bad\\u0000arg"]\n', "NUL"),
        )
        for setting, message in cases:
            with self.subTest(setting=setting):
                text = base + setting
                if setting.startswith("command"):
                    text = '[project]\nname="x"\n[[commands]]\nname="c"\n' + setting
                with self.assertRaisesRegex(ConfigError, message):
                    load_config_text(text)

    def test_string_array_fields_reject_wrong_types(self) -> None:
        with self.assertRaisesRegex(ConfigError, "array of strings"):
            load_config_text('[project]\nname="x"\n[scope]\nallow="src/**"\n')
        config = load_config_text('[project]\nname="x"\n[scope]\nallow=[]\ndeny=[]\n')
        self.assertEqual(config.scope.allow, ())


class PassportValidationEdgeTests(unittest.TestCase):
    @staticmethod
    def identity_v2() -> dict[str, object]:
        return {
            "project": "demo",
            "repository": "example/demo",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "outcome": "pass",
            "generated_at": "2026-08-16T00:00:00Z",
            "tool_version": "0.2.0",
            "config_source": "base",
            "config_sha256": "c" * 64,
            "execution_mode": "static",
            "execution_boundary": "static-no-execution",
            "container_runtime": "",
            "container_image": "",
            "network_enabled": False,
            "unsafe_native_accepted": False,
        }

    def test_identity_v2_rejects_each_invalid_security_field(self) -> None:
        cases: tuple[tuple[str, object], ...] = (
            ("project", ""),
            ("generated_at", "not-a-time"),
            ("base_sha", "short"),
            ("head_sha", 12),
            ("outcome", "maybe"),
            ("config_source", "candidate"),
            ("config_sha256", "bad"),
            ("execution_mode", "magic"),
            ("execution_boundary", "none"),
            ("container_runtime", 1),
            ("container_image", 1),
            ("network_enabled", "false"),
            ("unsafe_native_accepted", "false"),
        )
        for key, value in cases:
            with self.subTest(key=key):
                identity = self.identity_v2()
                identity[key] = value
                self.assertFalse(_valid_identity(identity, "1.1.0"))

    def test_identity_v2_requires_consistent_execution_boundary(self) -> None:
        cases: tuple[tuple[str, object], ...] = (
            ("execution_boundary", "isolated-container"),
            ("container_runtime", "docker"),
            ("container_image", "sha256:" + "a" * 64),
            ("network_enabled", True),
            ("unsafe_native_accepted", True),
        )
        for key, value in cases:
            with self.subTest(key=key):
                identity = self.identity_v2()
                identity[key] = value
                self.assertFalse(_valid_identity(identity, "1.1.0"))

        native = self.identity_v2()
        native.update(
            {
                "execution_mode": "native",
                "execution_boundary": "weak-native",
                "network_enabled": True,
                "unsafe_native_accepted": True,
            }
        )
        self.assertTrue(_valid_identity(native, "1.1.0"))

        container = self.identity_v2()
        container.update(
            {
                "execution_mode": "container",
                "execution_boundary": "isolated-container",
                "container_runtime": "docker",
                "container_image": "python@sha256:" + "a" * 64,
            }
        )
        self.assertTrue(_valid_identity(container, "1.1.0"))

    def test_verifier_bounds_decompressed_tar_bytes(self) -> None:
        root = Path(tempfile.mkdtemp())
        bundle = root / "bomb.tar.gz"
        bundle.write_bytes(gzip.compress(b"x" * 2048))
        with patch.object(passport_module, "_MAX_TAR_BYTES", 1024):
            valid, detail = verify_passport_bundle(bundle)
        self.assertFalse(valid)
        self.assertIn("decompressed size limit", detail["error"])

    def test_timestamp_must_include_timezone(self) -> None:
        self.assertFalse(_valid_timestamp("2026-08-16T00:00:00"))
        self.assertTrue(_valid_timestamp("2026-08-16T00:00:00+00:00"))

    def test_artifact_spec_rejects_bool_size_and_extra_keys(self) -> None:
        self.assertFalse(_valid_artifact_spec({"sha256": "a" * 64, "size": True}))
        self.assertFalse(
            _valid_artifact_spec({"sha256": "a" * 64, "size": 1, "extra": "x"})
        )
        self.assertTrue(_valid_artifact_spec({"sha256": "a" * 64, "size": 0}))

    def test_bytes_reader_supports_full_and_bounded_reads(self) -> None:
        reader = _BytesReader(b"abcdef")
        self.assertEqual(reader.read(2), b"ab")
        self.assertEqual(reader.read(), b"cdef")
        self.assertEqual(reader.read(), b"")

    def test_member_reader_rejects_unsafe_unreadable_and_oversized_members(self) -> None:
        class FakeArchive:
            def __init__(self, value: bytes | None) -> None:
                self.value = value

            def extractfile(self, member: tarfile.TarInfo) -> io.BytesIO | None:
                return None if self.value is None else io.BytesIO(self.value)

        unsafe = tarfile.TarInfo("../escape")
        with self.assertRaisesRegex(tarfile.TarError, "unsafe"):
            _read_member(FakeArchive(b"x"), unsafe)  # type: ignore[arg-type]
        missing = tarfile.TarInfo("report.json")
        with self.assertRaisesRegex(tarfile.TarError, "could not read"):
            _read_member(FakeArchive(None), missing)  # type: ignore[arg-type]
        oversized = tarfile.TarInfo("report.json")
        with self.assertRaisesRegex(tarfile.TarError, "size limit"):
            _read_member(FakeArchive(b"x" * (_MAX_MEMBER_BYTES + 1)), oversized)  # type: ignore[arg-type]

    def test_verifier_rejects_non_regular_duplicate_and_unsupported_schema(self) -> None:
        root = Path(tempfile.mkdtemp())

        non_regular = root / "non-regular.tar.gz"
        with tarfile.open(non_regular, "w:gz") as archive:
            info = tarfile.TarInfo("report.json")
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        valid, detail = verify_passport_bundle(non_regular)
        self.assertFalse(valid)
        self.assertIn("regular files", detail["error"])

        duplicate = root / "duplicate.tar.gz"
        with tarfile.open(duplicate, "w:gz") as archive:
            for name in ("report.json", "report.json", "report.md", "results.sarif", "passport.json"):
                raw = b"{}"
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
        valid, detail = verify_passport_bundle(duplicate)
        self.assertFalse(valid)
        self.assertIn("duplicate", detail["error"])

        output = root / "valid"
        output.mkdir()
        (output / "report.json").write_text("{}\n", encoding="utf-8")
        (output / "report.md").write_text("# report\n", encoding="utf-8")
        (output / "results.sarif").write_text("{}\n", encoding="utf-8")
        identity = self.identity_v2()
        result = create_passport_bundle(output, identity)
        extract = root / "extract"
        extract.mkdir()
        with tarfile.open(result["bundle"], "r:gz") as archive:
            archive.extractall(extract, filter="data")
        passport = extract / "passport.json"
        data = json.loads(passport.read_text(encoding="utf-8"))
        data["schema_version"] = "9.9.9"
        passport.write_text(json.dumps(data), encoding="utf-8")
        changed = root / "unsupported.tar.gz"
        with tarfile.open(changed, "w:gz") as archive:
            for path in sorted(extract.iterdir()):
                archive.add(path, arcname=path.name)
        valid, detail = verify_passport_bundle(changed)
        self.assertFalse(valid)
        self.assertIn("unsupported", detail["error"])


class GitSnapshotEdgeTests(unittest.TestCase):
    def test_tree_parser_rejects_malformed_oid_size_and_duplicates(self) -> None:
        cases = (
            (b"malformed\0", "malformed"),
            (b"100644 blob short 1\tfile\0", "object id"),
            (b"100644 blob " + b"a" * 40 + b" nope\tfile\0", "blob size"),
            (
                b"100644 blob " + b"a" * 40 + b" 1\tfile\0"
                b"100644 blob " + b"b" * 40 + b" 1\tfile\0",
                "duplicate",
            ),
        )
        for raw, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(GitError, message):
                    _parse_tree_entries(raw)

    def test_snapshot_path_and_link_portability_are_strict(self) -> None:
        for path in ("", "/absolute", "../escape", "a/../escape"):
            with self.subTest(path=path):
                with self.assertRaises(GitError):
                    _validate_snapshot_path(path)
        for target in ("C:payload", "..\\payload", "/absolute"):
            with self.subTest(target=target):
                with self.assertRaises(GitError):
                    _validate_link_target(PurePosixPath("nested/link"), target)

    def test_invalid_utf8_link_and_parent_collisions_are_rejected(self) -> None:
        root = Path(tempfile.mkdtemp())
        with self.assertRaisesRegex(GitError, "not UTF-8"):
            _write_snapshot_link(root, "link", b"\xff")

        link_parent = root / "link-parent"
        target = root / "target"
        target.mkdir()
        link_parent.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(GitError, "symbolic link"):
            _ensure_parent_directories(root, link_parent / "child")

        file_parent = root / "file-parent"
        file_parent.write_text("not a directory", encoding="utf-8")
        with self.assertRaises((GitError, FileExistsError, NotADirectoryError)):
            _ensure_parent_directories(root, file_parent / "child")


if __name__ == "__main__":
    unittest.main()
