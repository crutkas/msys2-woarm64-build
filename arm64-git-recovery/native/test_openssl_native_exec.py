import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("openssl_native_exec", Path(__file__).with_name("openssl-native-exec.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeExitControls(unittest.TestCase):
    def test_nonzero_raw_status_never_becomes_success(self):
        for code in (1, 127, 134, 255, 256, 1536, 0xC0000409, -1):
            self.assertNotEqual(module.portable_exit(code), 0)
        self.assertEqual(module.portable_exit(0), 0)

    def test_ordinary_exit_codes_are_preserved(self):
        for code in range(256):
            self.assertEqual(module.portable_exit(code), code)

    def test_only_drive_paths_are_normalized(self):
        self.assertEqual(module.windows_path("/c/path with spaces"), "c:/path with spaces")
        self.assertEqual(module.windows_path("/cygdrive/D/path"), "D:/path")
        self.assertEqual(module.windows_path("/etc/ssl"), "/etc/ssl")
        self.assertEqual(module.windows_path("file:///c/path"), "file:///c/path")


if __name__ == "__main__":
    unittest.main()
