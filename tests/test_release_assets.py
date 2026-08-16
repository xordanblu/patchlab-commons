from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_release_assets, generate_sbom
from scripts.verify_release_assets import expected_assets, verify


class ReleaseAssetTests(unittest.TestCase):
    def _source_zip(
        self,
        path: Path,
        version: str,
        members: list[tuple[str, bytes, int]] | None = None,
    ) -> None:
        prefix = f"patchlab-commons-{version}/"
        selected = members or [(f"{prefix}README.md", b"safe\n", stat.S_IFREG | 0o644)]
        with zipfile.ZipFile(
            path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name, data, mode in selected:
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)

    def _sbom(self, version: str, commit: str) -> dict[str, object]:
        package_spdx = "SPDXRef-Package-patchlab-commons"
        return {
            "SPDXID": "SPDXRef-DOCUMENT",
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "name": f"patchlab-commons-{version}",
            "documentNamespace": (
                "https://github.com/xordanblu/patchlab-commons/spdx/" + "a" * 64
            ),
            "documentDescribes": [package_spdx],
            "packages": [
                {
                    "SPDXID": package_spdx,
                    "name": "patchlab-commons",
                    "versionInfo": version,
                    "downloadLocation": "https://github.com/xordanblu/patchlab-commons",
                    "filesAnalyzed": False,
                    "licenseConcluded": "Apache-2.0",
                    "licenseDeclared": "Apache-2.0",
                    "externalRefs": [
                        {
                            "referenceType": "purl",
                            "referenceLocator": f"pkg:pypi/patchlab-commons@{version}",
                        },
                        {
                            "referenceType": "vcs",
                            "referenceLocator": (
                                "git+https://github.com/xordanblu/patchlab-commons@" + commit
                            ),
                        },
                    ],
                }
            ],
            "relationships": [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": package_spdx,
                }
            ],
        }

    def _rewrite_manifest(self, root: Path) -> None:
        records = []
        for path in sorted(root.iterdir()):
            if path.name == "SHA256SUMS.txt":
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(f"{digest}  {path.name}\n")
        (root / "SHA256SUMS.txt").write_text("".join(records), encoding="utf-8")

    def _fixture(self, version: str = "0.2.0", commit: str = "b" * 40) -> Path:
        root = Path(tempfile.mkdtemp())
        for name in expected_assets(version) - {"SHA256SUMS.txt"}:
            path = root / name
            if name.endswith("-source.zip"):
                self._source_zip(path, version)
            elif name == "patchlab-commons.spdx.json":
                path.write_text(
                    json.dumps(self._sbom(version, commit)),
                    encoding="utf-8",
                )
            else:
                path.write_bytes(name.encode("utf-8"))
        self._rewrite_manifest(root)
        return root

    def test_exact_release_fixture_passes(self) -> None:
        commit = "b" * 40
        self.assertEqual(verify(self._fixture(commit=commit), "0.2.0", commit), [])

    def test_missing_unexpected_and_tampered_assets_fail(self) -> None:
        root = self._fixture()
        (root / "patchlab-demo-pass.tar.gz").write_bytes(b"tampered")
        (root / "unexpected.bin").write_bytes(b"bad")
        (root / "patchlab-blocked-passport.tar.gz").unlink()
        errors = verify(root, "0.2.0")
        rendered = "\n".join(errors)
        self.assertIn("missing release assets", rendered)
        self.assertIn("unexpected release assets", rendered)
        self.assertIn("SHA-256 mismatch", rendered)

    def test_checksum_manifest_is_strict(self) -> None:
        root = self._fixture()
        manifest = root / "SHA256SUMS.txt"
        manifest.write_text(manifest.read_text(encoding="utf-8") + "bad line\n", encoding="utf-8")
        self.assertIn("invalid checksum record", "\n".join(verify(root, "0.2.0")))

    def test_sbom_must_match_exact_commit_and_identity(self) -> None:
        root = self._fixture(commit="b" * 40)
        errors = verify(root, "0.2.0", "c" * 40)
        self.assertIn("SBOM VCS reference does not match", "\n".join(errors))
        document = json.loads((root / "patchlab-commons.spdx.json").read_text(encoding="utf-8"))
        document["packages"][0]["name"] = "other"
        (root / "patchlab-commons.spdx.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        self._rewrite_manifest(root)
        self.assertIn("SBOM package field", "\n".join(verify(root, "0.2.0")))

    def test_source_zip_rejects_duplicate_and_nonportable_paths(self) -> None:
        root = self._fixture()
        source = root / "patchlab-commons-v0.2.0-source.zip"
        prefix = "patchlab-commons-0.2.0/"
        self._source_zip(
            source,
            "0.2.0",
            [
                (f"{prefix}README.md", b"one", stat.S_IFREG | 0o644),
                (f"{prefix}readme.md", b"two", stat.S_IFREG | 0o644),
            ],
        )
        self._rewrite_manifest(root)
        rendered = "\n".join(verify(root, "0.2.0"))
        self.assertIn("nonportable-colliding", rendered)

        self._source_zip(
            source,
            "0.2.0",
            [(f"{prefix}CON.txt", b"bad", stat.S_IFREG | 0o644)],
        )
        self._rewrite_manifest(root)
        self.assertIn("nonportable path", "\n".join(verify(root, "0.2.0")))

    def test_source_zip_rejects_escaping_symlink(self) -> None:
        root = self._fixture()
        source = root / "patchlab-commons-v0.2.0-source.zip"
        prefix = "patchlab-commons-0.2.0/"
        self._source_zip(
            source,
            "0.2.0",
            [(f"{prefix}docs/link", b"../../outside", stat.S_IFLNK | 0o777)],
        )
        self._rewrite_manifest(root)
        self.assertIn("symlink escapes", "\n".join(verify(root, "0.2.0")))

    def test_source_zip_rejects_unsupported_metadata(self) -> None:
        root = self._fixture()
        source = root / "patchlab-commons-v0.2.0-source.zip"
        prefix = "patchlab-commons-0.2.0/"
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(f"{prefix}README.md", "unsafe")
        self._rewrite_manifest(root)
        rendered = "\n".join(verify(root, "0.2.0"))
        self.assertIn("deterministic deflate", rendered)
        self.assertIn("unsupported member type", rendered)


class ReleaseBuilderSecurityTests(unittest.TestCase):
    def test_release_outputs_must_stay_inside_repository(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        outside = root.parent / f"{root.name}-outside"
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            build_release_assets._inside_root(root, outside, "release directory")
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            generate_sbom._inside_root(root, outside, "SBOM output")
        with self.assertRaisesRegex(ValueError, "must not be the repository root"):
            build_release_assets._inside_root(root, root, "release directory")

    def test_release_tools_reject_git_from_repository(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        fake = root / "git"
        fake.write_text("fake", encoding="utf-8")
        fake.chmod(0o755)
        for module in (build_release_assets, generate_sbom):
            with self.subTest(module=module.__name__):
                with patch.object(module.shutil, "which", return_value=str(fake)):
                    with self.assertRaisesRegex(RuntimeError, "inside the repository"):
                        module._git_executable(root)

    def test_source_builder_rejects_nonportable_paths(self) -> None:
        for name in (
            "CON.txt",
            "bad:name",
            "trailing.",
            ".git/config",
            "../escape",
            "a//b",
            "a/./b",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "nonportable|unsafe"):
                    build_release_assets._validate_source_path(name)

    def test_source_builder_rejects_escaping_symlinks(self) -> None:
        with self.assertRaisesRegex(ValueError, "escapes"):
            build_release_assets._validate_symlink_target(
                build_release_assets.PurePosixPath("docs/link"), b"../../outside"
            )
        build_release_assets._validate_symlink_target(
            build_release_assets.PurePosixPath("docs/link"), b"../README.md"
        )


if __name__ == "__main__":
    unittest.main()
