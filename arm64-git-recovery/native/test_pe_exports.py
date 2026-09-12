import importlib.util
from pathlib import Path
import struct
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("pe_exports", Path(__file__).with_name("pe-export-names.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PeExportControls(unittest.TestCase):
    def image(self):
        data = bytearray(1024)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", data, 0x84, 0xAA64, 1)
        struct.pack_into("<H", data, 0x94, 240)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<I", data, 0x98 + 108, 1)
        struct.pack_into("<II", data, 0x98 + 112, 0x1000, 0x100)
        struct.pack_into("<IIII", data, 0x188 + 8, 0x200, 0x1000, 0x200, 0x200)
        struct.pack_into("<IIIII", data, 0x200 + 20, 1, 1, 0x1040, 0x1044, 0x1048)
        struct.pack_into("<IIH", data, 0x240, 0x1100, 0x1050, 0)
        data[0x250:0x256] = b"Alpha\0"
        return data

    def test_reads_only_actual_export_name(self):
        self.assertEqual(module.export_names(self.image()), ["Alpha"])

    def test_wrong_machine_bad_rva_ordinal_and_truncation_rejected(self):
        for kind in ("machine", "rva", "ordinal", "truncated"):
            with self.subTest(kind=kind):
                data = self.image()
                if kind == "machine":
                    struct.pack_into("<H", data, 0x84, 0xA641)
                elif kind == "rva":
                    struct.pack_into("<I", data, 0x244, 0x200000)
                elif kind == "ordinal":
                    struct.pack_into("<H", data, 0x248, 2)
                else:
                    data = data[:600]
                with self.assertRaises(ContractError):
                    module.export_names(data)


if __name__ == "__main__":
    unittest.main()
