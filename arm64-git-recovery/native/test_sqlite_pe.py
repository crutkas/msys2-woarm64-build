from pathlib import Path
import struct
import tempfile
import unittest

from sources import ContractError
from sqlite_pe import inspect_pe


class NativePeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "candidate.dll"

    def image(self):
        data = bytearray(1024)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", data, 0x84, 0xAA64, 1)
        struct.pack_into("<HH", data, 0x94, 240, 0x2000)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<I", data, 0x98 + 108, 16)
        struct.pack_into("<IIII", data, 0x188 + 8, 0x200, 0x1000, 0x200, 0x200)
        struct.pack_into("<II", data, 0x98 + 120, 0x1000, 40)
        struct.pack_into("<IIIII", data, 0x200, 0, 0, 0, 0x1060, 0)
        data[0x260:0x26d] = b"msys-2.0.dll\0"
        return data

    def test_reads_real_machine_size_and_import(self):
        self.path.write_bytes(self.image())
        result = inspect_pe(self.path)
        self.assertEqual(result["machine"], "0xAA64")
        self.assertEqual(result["kind"], "dll")
        self.assertEqual(result["size"], 1024)
        self.assertEqual(result["imports"], [{"name": "msys-2.0.dll", "delayed": False}])

    def test_rejects_x64_arm64ec_truncation_and_bad_rva(self):
        for case in ("x64", "arm64ec", "truncated", "rva", "no-null-descriptor"):
            with self.subTest(case=case):
                data = self.image()
                if case in ("x64", "arm64ec"):
                    struct.pack_into("<H", data, 0x84, 0x8664 if case == "x64" else 0xA641)
                elif case == "truncated":
                    data = data[:600]
                elif case == "rva":
                    struct.pack_into("<I", data, 0x20c, 0x9000)
                else:
                    struct.pack_into("<I", data, 0x98 + 124, 20)
                self.path.write_bytes(data)
                with self.assertRaises(ContractError):
                    inspect_pe(self.path)
