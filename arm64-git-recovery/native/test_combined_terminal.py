import importlib
import struct
import unittest

from sources import ContractError

prepare = importlib.import_module("prepare-combined-terminal")
seal = importlib.import_module("seal-combined-terminal")


class CombinedTerminalContracts(unittest.TestCase):
    @staticmethod
    def image(machine=0xAA64, magic=0x20B, dll=True):
        image = bytearray(128)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 60, 64)
        image[64:68] = b"PE\0\0"
        struct.pack_into("<H", image, 68, machine)
        struct.pack_into("<H", image, 86, 0x2000 if dll else 0)
        struct.pack_into("<H", image, 88, magic)
        return bytes(image)

    def test_machine_is_read_from_actual_pe(self):
        self.assertEqual(prepare.pe(self.image())["machine"], "0xAA64")
        self.assertTrue(prepare.pe(self.image())["dll"])
        self.assertFalse(prepare.pe(self.image(dll=False))["dll"])
        for machine in (0x8664, 0x14C, 0xA641):
            with self.subTest(machine=machine), self.assertRaises(ContractError):
                prepare.pe(self.image(machine))

    def test_malformed_or_non_pe32plus_inputs_fail_closed(self):
        for data in (b"plain text", self.image()[:70], self.image(magic=0x10B)):
            with self.subTest(data=data[:8]), self.assertRaises(ContractError):
                prepare.pe(data)

    def test_all_signal_delivery_and_linkage_scopes_are_required(self):
        scopes = {value for value in seal.REQUIRED.values() if value[0] == "readline-signals"}
        self.assertEqual(scopes, {("readline-signals", linkage, delivery)
                                  for linkage in ("static", "shared") for delivery in ("tty", "kill")})

    def test_chain_requires_static_and_shared_actual_libraries(self):
        for package in ("ncurses", "libedit", "history"):
            self.assertIn((package, "static", None), seal.REQUIRED.values())
            self.assertIn((package, "shared", None), seal.REQUIRED.values())


if __name__ == "__main__":
    unittest.main()
