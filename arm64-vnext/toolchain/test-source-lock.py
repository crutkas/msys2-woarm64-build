#!/usr/bin/env python3
"""Source-lock checks without downloads, compiler builds, or prefix writes."""

import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parent
load_lock = runpy.run_path(str(RECIPE / "source-lock.py"))["load_lock"]


class SourceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="toolchain-source-lock-")
        self.directory = Path(self.temp.name)
        shutil.copy2(RECIPE / "source-lock.json", self.directory)
        for patch in RECIPE.glob("*.patch"):
            shutil.copy2(patch, self.directory)
        self.lock = json.loads((self.directory / "source-lock.json").read_text())

    def tearDown(self):
        self.temp.cleanup()

    def write_lock(self):
        (self.directory / "source-lock.json").write_text(json.dumps(self.lock), encoding="utf-8")

    def test_ordered_series(self):
        lock = load_lock(self.directory)
        self.assertEqual(20, len(lock["sources"]["gcc"]["patches"]))
        self.assertEqual(9, len(lock["sources"]["binutils"]["patches"]))
        self.assertEqual("gcc-arm64-windows-cache.patch", lock["sources"]["gcc"]["patches"][-4]["file"])
        self.assertEqual("gcc-cygming-crt-host-types.patch", lock["sources"]["gcc"]["patches"][-3]["file"])
        self.assertEqual("gcc-arm64-executable-suffix.patch", lock["sources"]["gcc"]["patches"][-2]["file"])
        self.assertEqual("gcc-emutls-returns-twice-safe-insert.patch", lock["sources"]["gcc"]["patches"][-1]["file"])

    def test_patch_drift_is_rejected(self):
        patch = self.directory / "gcc-arm64-windows-cache.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_moving_revision_is_rejected(self):
        self.lock["sources"]["gcc"]["revision"] = "main"
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "40-digit"):
            load_lock(self.directory)

    def test_machine_local_url_is_rejected(self):
        self.lock["sources"]["gcc"]["repository"] = "file:///old-machine/gcc"
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "Nonportable"):
            load_lock(self.directory)

    def test_duplicate_patch_is_rejected(self):
        self.lock["sources"]["gcc"]["patches"].append(self.lock["sources"]["gcc"]["patches"][0])
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "duplicate patch"):
            load_lock(self.directory)

    def test_patch_queries_preserve_order(self):
        result = subprocess.run(
            [sys.executable, str(RECIPE / "source-lock.py"), "--directory", str(self.directory),
             "patches", "binutils"], capture_output=True, text=True, check=True)
        self.assertEqual([str(self.directory / patch["file"])
                          for patch in self.lock["sources"]["binutils"]["patches"]],
                         result.stdout.splitlines())

    def test_gcc_archive_mismatch_is_rejected(self):
        contrib = self.directory / "gcc" / "contrib"
        contrib.mkdir(parents=True)
        (contrib / "prerequisites.sha512").write_text("0" * 128 + " gmp-6.2.1.tar.bz2\n")
        result = subprocess.run(
            [sys.executable, str(RECIPE / "source-lock.py"), "--directory", str(self.directory),
             "verify", "--gcc-source", str(contrib.parent)], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("GCC prerequisite identity differs", result.stderr)


if __name__ == "__main__":
    unittest.main()
