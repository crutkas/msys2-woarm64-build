import tempfile
from pathlib import Path
import unittest

from package_posix import finish, terminfo_windows_paths
from sources import ContractError


class PosixPackageControls(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="posix-package-control-")
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / "source"
        self.stage = Path(temp.name) / "stage"
        (self.source / "src").mkdir(parents=True)
        (self.stage / "usr/lib/coreutils").mkdir(parents=True)
        (self.source / "COPYING").write_text("synthetic license")
        (self.source / "src/dircolors.hin").write_text("synthetic colors")
        (self.stage / "usr/lib/coreutils/libstdbuf.so.exe").write_bytes(b"synthetic module")

    def test_coreutils_tail_preserves_module_bytes(self):
        finish("coreutils", self.source, self.stage)
        self.assertFalse((self.stage / "usr/lib/coreutils/libstdbuf.so.exe").exists())
        self.assertEqual((self.stage / "usr/lib/coreutils/libstdbuf.dll").read_bytes(), b"synthetic module")
        self.assertEqual((self.stage / "etc/DIR_COLORS").read_text(), "synthetic colors")
        self.assertEqual((self.stage / "usr/share/licenses/coreutils/COPYING").read_text(), "synthetic license")
        finish("coreutils", self.source, self.stage)

    def test_missing_module_rejected(self):
        (self.stage / "usr/lib/coreutils/libstdbuf.so.exe").unlink()
        with self.assertRaisesRegex(ContractError, "Missing coreutils"):
            finish("coreutils", self.source, self.stage)

    def test_conflicting_module_rejected(self):
        (self.stage / "usr/lib/coreutils/libstdbuf.dll").write_bytes(b"different")
        with self.assertRaisesRegex(ContractError, "Conflicting stdbuf"):
            finish("coreutils", self.source, self.stage)

    def test_missing_license_rejected(self):
        (self.source / "COPYING").unlink()
        with self.assertRaisesRegex(ContractError, "Missing package data"):
            finish("make", self.source, self.stage)

    def test_terminfo_preserves_distinct_initial_case(self):
        mapped = terminfo_windows_paths({"e/eterm": "one", "E/Eterm": "two"})
        self.assertEqual(mapped["65/eterm"]["sha256"], "one")
        self.assertEqual(mapped["45/Eterm"]["sha256"], "two")

    def test_terminfo_only_deduplicates_identical_case_aliases(self):
        mapped = terminfo_windows_paths({"h/hp2621A": "same", "h/hp2621a": "same"})
        self.assertEqual(len(mapped), 1)
        self.assertEqual(sum(len(row["aliases"]) for row in mapped.values()), 1)
        with self.assertRaises(ContractError):
            terminfo_windows_paths({"h/hp2621A": "one", "h/hp2621a": "two"})


if __name__ == "__main__":
    unittest.main()
