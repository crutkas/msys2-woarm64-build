#!/usr/bin/env python3
"""Unit controls for the focused Cygwin w32api source lock."""

import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parent


class SourceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cygwin-w32api-source-lock-")
        self.root = Path(self.temp.name)
        for name in (
            "cygwin-w32api-source-lock.json",
            "cygwin-public-interlocked-codegen.c",
            "cygwin-w32api-arm64-abi.patch",
            "cygwin-w32api-arm64-interlocked-exchange-ordering.patch",
            "cygwin-w32api-common.py",
        ):
            shutil.copy2(RECIPE / name, self.root / name)
        self.api = runpy.run_path(str(self.root / "cygwin-w32api-common.py"))

    def tearDown(self):
        self.temp.cleanup()

    def test_lock_and_patch_order(self):
        lock = self.api["load_lock"](self.root)
        self.assertEqual("819a6ec2ea87c19814b287e21d65e0dc7f05abba", lock["revision"])
        self.assertEqual(
            [
                "cygwin-w32api-arm64-abi.patch",
                "cygwin-w32api-arm64-interlocked-exchange-ordering.patch",
            ],
            [patch["file"] for patch in lock["patches"]],
        )
        self.assertEqual(
            "961ca55782fa89516be1dcc71815cc20c9334e537d7a5f306fd752a0d7f40a04",
            self.api["source_identity"](lock)["before_sha256"],
        )
        self.assertEqual(3043, lock["sdk_contract"]["file_count"])
        self.assertEqual(8, len(lock["sdk_contract"]["required_files"]))
        self.assertEqual(
            "a5c27a197a84dbfb2755614131a1c361eec9d70753c13f1e92b58c418e8206cd",
            lock["public_probe"]["sha256"],
        )

    def test_patch_drift_is_rejected(self):
        patch = self.root / "cygwin-w32api-arm64-interlocked-exchange-ordering.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Patch identity differs"):
            self.api["load_lock"](self.root)

    def test_moving_revision_is_rejected(self):
        path = self.root / "cygwin-w32api-source-lock.json"
        lock = json.loads(path.read_text(encoding="utf-8"))
        lock["revision"] = "main"
        path.write_text(json.dumps(lock), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid pinned"):
            self.api["load_lock"](self.root)


if __name__ == "__main__":
    unittest.main()
