#!/usr/bin/env python3
"""Source-contract and raw COFF controls for the Windows import-only overlay."""

import argparse
import json
from pathlib import Path
import runpy
import struct
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(RECIPE / "build-msys-windows-imports.py"))
archive_identity = helpers["archive_identity"]
OVERLAY = None


class ImportTests(unittest.TestCase):
    def test_source_contract(self):
        lock = runpy.run_path(str(RECIPE / "source-lock.py"))["load_lock"](RECIPE)
        contract = json.loads((RECIPE / "windows-system-imports.json").read_text())
        self.assertEqual(lock["sources"]["mingw-w64"]["revision"], contract["revision"])
        self.assertEqual({"wsock32", "bcrypt", "setupapi", "hid"}, set(contract["definitions"]))
        bootstrap = (RECIPE / "bootstrap-cygwin.sh").read_text()
        libraries = bootstrap.split("for library in ", 1)[1].split("; do", 1)[0].split()
        for name in contract["definitions"]:
            self.assertEqual(1, libraries.count(name))

    def test_raw_archive_contract(self):
        contract = json.loads((RECIPE / "windows-system-imports.json").read_text())
        with tempfile.TemporaryDirectory(prefix="windows-import-controls-") as temp:
            sample = Path(temp) / "sample.a"
            for name, spec in contract["definitions"].items():
                with self.subTest(library=name):
                    source = OVERLAY / "payload" / "aarch64-pc-cygwin" / "lib" / f"lib{name}.a"
                    good = archive_identity(source, spec["dll"])
                    self.assertGreater(len(good["members"]), 1)
                    with self.assertRaisesRegex(ValueError, "Wrong import DLL descriptor"):
                        archive_identity(source, "not-the-system-library.dll")
                    original = source.read_bytes()
                    offset = 8
                    while original[offset:offset + 16].decode("ascii").strip() in ("/", "//"):
                        size = int(original[offset + 48:offset + 58])
                        offset += 60 + size + (size & 1)
                    changed = bytearray(original)
                    struct.pack_into("<H", changed, offset + 60, 0x8664)
                    sample.write_bytes(changed)
                    with self.assertRaisesRegex(ValueError, "Not an ordinary ARM64"):
                        archive_identity(sample, spec["dll"])
                    changed = bytearray(original)
                    changed[offset + 80:offset + 88] = b".evil\0\0\0"
                    sample.write_bytes(changed)
                    with self.assertRaisesRegex(ValueError, "Unexpected import section"):
                        archive_identity(sample, spec["dll"])
                    sample.write_bytes(original[:-1])
                    with self.assertRaises(ValueError):
                        archive_identity(sample, spec["dll"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=Path, required=True)
    args = parser.parse_args()
    OVERLAY = args.overlay.resolve(strict=True)
    unittest.main(argv=["test-windows-imports.py"])
