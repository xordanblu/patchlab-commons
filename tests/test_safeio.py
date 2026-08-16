from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from patchlab_commons.safeio import (
    UnsafeOutputPath,
    ensure_output_directory,
    replace_file,
    resolve_output_directory,
    safe_write_text,
)


class SafeIoTests(unittest.TestCase):
    def test_relative_output_stays_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = resolve_output_directory(root, Path(".patchlab/out"))
            self.assertEqual(target, root / ".patchlab" / "out")

    def test_parent_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(UnsafeOutputPath):
                resolve_output_directory(Path(temp), Path("../outside"))

    def test_output_symlink_is_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside"
            outside.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")
            with self.assertRaises(UnsafeOutputPath):
                resolve_output_directory(root, Path("linked/out"))

    def test_safe_write_refuses_file_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            victim = root / "victim.txt"
            victim.write_text("original", encoding="utf-8")
            link = root / "report.json"
            try:
                link.symlink_to(victim)
            except OSError as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")
            with self.assertRaises(UnsafeOutputPath):
                safe_write_text(link, "replacement")
            self.assertEqual(victim.read_text(encoding="utf-8"), "original")

    def test_safe_write_replaces_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report.json"
            target.write_text("old", encoding="utf-8")
            safe_write_text(target, "new")
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse(target.is_symlink())
            if os.name != "nt":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_absolute_output_directory_is_supported(self) -> None:
        root = Path(tempfile.mkdtemp())
        target = Path(tempfile.mkdtemp()) / "out"
        self.assertEqual(resolve_output_directory(root, target), target)

    def test_existing_file_cannot_be_output_directory(self) -> None:
        target = Path(tempfile.mkdtemp()) / "not-a-directory"
        target.write_text("file", encoding="utf-8")
        with self.assertRaises(UnsafeOutputPath):
            ensure_output_directory(target)

    def test_replace_file_rejects_missing_temporary_file(self) -> None:
        directory = Path(tempfile.mkdtemp())
        with self.assertRaises(UnsafeOutputPath):
            replace_file(directory / "missing.tmp", directory / "result.bin")

    def test_replace_file_makes_final_evidence_private(self) -> None:
        directory = Path(tempfile.mkdtemp())
        temporary = directory / "prepared.tmp"
        target = directory / "result.bin"
        temporary.write_bytes(b"evidence")
        replace_file(temporary, target)
        self.assertEqual(target.read_bytes(), b"evidence")
        if os.name != "nt":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
