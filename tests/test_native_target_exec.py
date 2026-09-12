import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "native-target-exec.py"
SPEC = importlib.util.spec_from_file_location("native_target_exec", SCRIPT)
RELAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELAY)


class NativeTargetExitTests(unittest.TestCase):
    def test_portable_exit_is_lossless_for_byte_statuses(self):
        for value in range(256):
            self.assertEqual(RELAY.portable_exit(value), value)

    def test_high_native_failure_never_becomes_success(self):
        for value in (256, 512, 1536, -1, -1073741819, 0xC0000005, 0xFFFFFFFF):
            self.assertEqual(RELAY.portable_exit(value), 255)

    def test_all_supported_msys_drive_spellings(self):
        for value in ("/c/a b/file.exe", "/cygdrive/c/a b/file.exe", "/proc/cygdrive/c/a b/file.exe"):
            self.assertEqual(RELAY.windows_path(value), "c:/a b/file.exe")
        self.assertEqual(RELAY.windows_path("C:\\private\\file.exe"), "C:\\private\\file.exe")

    def test_only_ordinary_arm64_pe32plus_programs_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nonexecuted-header-fixture.exe"
            for machine, optional, characteristics, accepted in (
                (0xAA64, 0x20B, 0, True),
                (0x8664, 0x20B, 0, False),
                (0xA641, 0x20B, 0, False),
                (0xAA64, 0x10B, 0, False),
                (0xAA64, 0x20B, 0x2000, False),
            ):
                data = bytearray(90)
                data[:2] = b"MZ"
                struct.pack_into("<I", data, 60, 64)
                data[64:68] = b"PE\0\0"
                struct.pack_into("<H", data, 68, machine)
                struct.pack_into("<H", data, 86, characteristics)
                struct.pack_into("<H", data, 88, optional)
                path.write_bytes(data)
                if accepted:
                    RELAY.require_arm64_pe(path)
                else:
                    with self.assertRaises(ValueError):
                        RELAY.require_arm64_pe(path)
            path.write_bytes(b"not a PE executable")
            with self.assertRaises(ValueError):
                RELAY.require_arm64_pe(path)


if __name__ == "__main__":
    unittest.main()
