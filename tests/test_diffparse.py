from __future__ import annotations

import unittest

from patchlab_commons.diffparse import FileDiff, align_file_diffs, parse_unified_diff
from patchlab_commons.models import ChangedFile

DIFF = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
-old = True
+old = False
+new = 1
 keep = 2
"""


class DiffParseTests(unittest.TestCase):
    def test_parses_additions_and_deletions(self) -> None:
        files = parse_unified_diff(DIFF)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "app.py")
        self.assertEqual([line.new_line for line in files[0].additions()], [1, 2])
        self.assertEqual(files[0].deletions()[0].old_line, 1)

    def test_handles_added_file(self) -> None:
        diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+print("hi")
"""
        file = parse_unified_diff(diff)[0]
        self.assertIsNone(file.old_path)
        self.assertEqual(file.new_path, "new.py")
        self.assertEqual(file.additions()[0].new_line, 1)

    def test_nul_metadata_replaces_display_quoted_path(self) -> None:
        parsed = [FileDiff(old_path='"a/file', new_path='name.py"')]
        changed = [ChangedFile(status="M", path="file name.py")]
        aligned = align_file_diffs(parsed, changed)
        self.assertEqual(aligned[0].old_path, "file name.py")
        self.assertEqual(aligned[0].new_path, "file name.py")

    def test_alignment_preserves_rename_identity(self) -> None:
        parsed = [FileDiff(old_path="wrong-old", new_path="wrong-new")]
        changed = [ChangedFile(status="R100", old_path="old name.py", path="new name.py")]
        aligned = align_file_diffs(parsed, changed)
        self.assertEqual(aligned[0].old_path, "old name.py")
        self.assertEqual(aligned[0].new_path, "new name.py")


if __name__ == "__main__":
    unittest.main()
