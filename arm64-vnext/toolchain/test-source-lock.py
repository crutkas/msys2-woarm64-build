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
        self.assertEqual(22, len(lock["sources"]["gcc"]["patches"]))
        self.assertEqual(9, len(lock["sources"]["binutils"]["patches"]))
        self.assertEqual(
            ["mingw-woarm64-crt-cexp-no-builtin-sincos.patch",
             "mingw-woarm64-fastfail-c89-inline.patch",
             "mingw-woarm64-interlocked-exchange-ordering.patch"],
            [patch["file"] for patch in lock["sources"]["mingw-woarm64"]["patches"]])
        self.assertEqual(
            ["binutils-arm64-add-fp.patch", "binutils-arm64-fp-unwind-enum-order.patch",
             "binutils-arm64-unwind-storage.patch"],
            [patch["file"] for patch in lock["sources"]["binutils"]["patches"][1:4]])
        self.assertEqual(
            ["gcc-arm64-seh-frames.patch", "gcc-arm64-seh-stackalloc-reg.patch",
             "gcc-arm64-seh-prepost-index-save.patch", "gcc-arm64-seh-sp-direct-save-portable.patch",
             "gcc-arm64-seh-order-offsets.patch"],
            [patch["file"] for patch in lock["sources"]["gcc"]["patches"][7:12]])
        self.assertEqual(
            ["gcc-arm64-windows-cache.patch", "gcc-cygming-crt-host-types.patch",
             "gcc-arm64-executable-suffix.patch", "gcc-emutls-returns-twice-safe-insert.patch",
             "gcc-arm64-pe-salted-guard.patch", "libgcc-arm64-unwind-context.patch"],
            [patch["file"] for patch in lock["sources"]["gcc"]["patches"][-6:]])
        self.assertEqual(
            "cfccc4de9849a50b5687b0a50a945abcd34dbf96dfe82d3f8ea4918761f2772c",
            lock["sources"]["gcc"]["patches"][10]["sha256"])

    def test_portable_sp_patch_drift_is_rejected(self):
        patch = self.directory / "gcc-arm64-seh-sp-direct-save-portable.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_emutls_patch_drift_is_rejected(self):
        patch = self.directory / "gcc-emutls-returns-twice-safe-insert.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_salted_guard_patch_drift_is_rejected(self):
        patch = self.directory / "gcc-arm64-pe-salted-guard.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_unwind_context_patch_drift_is_rejected(self):
        patch = self.directory / "libgcc-arm64-unwind-context.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_interlocked_patch_drift_is_rejected(self):
        patch = self.directory / "mingw-woarm64-interlocked-exchange-ordering.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_interlocked_transport_drift_is_rejected(self):
        patch = self.directory / "mingw-woarm64-interlocked-exchange-ordering-original.patch"
        patch.write_bytes(patch.read_bytes().replace(b"\r\n", b"\n"))
        with self.assertRaisesRegex(ValueError, "Transported patch identity differs"):
            load_lock(self.directory)

    def test_interlocked_normalization_is_exact(self):
        patch = self.lock["sources"]["mingw-woarm64"]["patches"][-1]
        self.assertEqual((self.directory / patch["file"]).read_bytes(),
                         (self.directory / patch["transport"]["file"]).read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual("mingw-w64-headers/include/psdk_inc/intrin-impl.h", patch["source_identity"]["file"])
        self.assertEqual([], self.lock["sources"]["mingw-w64"]["patches"])

    def test_w32api_ordering_is_a_separate_overlay(self):
        source = self.lock["sources"]["mingw-w64"]
        self.assertEqual("819a6ec2ea87c19814b287e21d65e0dc7f05abba", source["revision"])
        self.assertEqual(["w32api-arm64-cygwin.patch", "w32api-arm64-interlocked-exchange-ordering.patch"],
                         [patch["file"] for patch in source["overlay_patches"]])
        self.assertEqual("961ca55782fa89516be1dcc71815cc20c9334e537d7a5f306fd752a0d7f40a04",
                         source["overlay_patches"][-1]["source_identity"]["before_sha256"])

    def test_w32api_ordering_patch_drift_is_rejected(self):
        patch = self.directory / "w32api-arm64-interlocked-exchange-ordering.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

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
        for name in ("gcc", "binutils"):
            with self.subTest(source=name):
                result = subprocess.run(
                    [sys.executable, str(RECIPE / "source-lock.py"), "--directory", str(self.directory),
                     "patches", name], capture_output=True, text=True, check=True)
                self.assertEqual([str(self.directory / patch["file"])
                                  for patch in self.lock["sources"][name]["patches"]],
                                 result.stdout.splitlines())

    def test_crt_patch_query(self):
        result = subprocess.run(
            [sys.executable, str(RECIPE / "source-lock.py"), "--directory", str(self.directory),
             "patches", "mingw-woarm64"], capture_output=True, text=True, check=True)
        self.assertEqual(
            [str(self.directory / "mingw-woarm64-crt-cexp-no-builtin-sincos.patch"),
             str(self.directory / "mingw-woarm64-fastfail-c89-inline.patch"),
             str(self.directory / "mingw-woarm64-interlocked-exchange-ordering.patch")],
            result.stdout.splitlines())

    def test_fastfail_header_patch_drift_is_rejected(self):
        patch = self.directory / "mingw-woarm64-fastfail-c89-inline.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

    def test_crt_patch_drift_is_rejected(self):
        patch = self.directory / "mingw-woarm64-crt-cexp-no-builtin-sincos.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            load_lock(self.directory)

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
