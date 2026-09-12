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

    def test_environment_transport_preserves_path_like_arguments(self):
        environment = {
            "WOARM64_NATIVE_ARG_COUNT": "4",
            "WOARM64_NATIVE_ARG_0": "v1:/CN=any",
            "WOARM64_NATIVE_ARG_1": "v1:a/",
            "WOARM64_NATIVE_ARG_2": "v1:",
            "WOARM64_NATIVE_ARG_3": "v1:C:\\already-native",
        }
        self.assertEqual(
            RELAY.relayed_arguments(environment, ["ignored"]),
            ["/CN=any", "a/", "", "C:\\already-native"],
        )
        self.assertFalse(any(name.startswith("WOARM64_NATIVE_ARG") for name in environment))

    def test_positional_arguments_remain_available_for_mingw_conversion(self):
        self.assertEqual(RELAY.relayed_arguments({}, ["/c/input", "plain"]), ["/c/input", "plain"])

    def test_windows_argument_converts_posix_drive_paths(self):
        self.assertEqual(RELAY.windows_argument("/c/native/input.pem"), "C:/native/input.pem")
        self.assertEqual(
            RELAY.windows_argument("file:/c/native/input.pem"),
            "file:C:/native/input.pem",
        )
        self.assertEqual(
            RELAY.windows_argument("file:///c/native/input.pem"),
            "file:///C:/native/input.pem",
        )
        self.assertEqual(
            RELAY.windows_argument("file://localhost/c/native/input.pem"),
            "file://localhost/C:/native/input.pem",
        )
        self.assertEqual(
            RELAY.windows_argument("org.openssl.engine:ossltest:ot:/c/native/input.pem"),
            "org.openssl.engine:ossltest:ot:C:/native/input.pem",
        )

    def test_windows_argument_preserves_non_paths(self):
        self.assertEqual(RELAY.windows_argument("/CN=any"), "/CN=any")
        self.assertEqual(
            RELAY.windows_argument("http://127.0.0.1:8080/ocsp"),
            "http://127.0.0.1:8080/ocsp",
        )
        self.assertEqual(RELAY.windows_argument("/dev/null"), "NUL")

    def test_windows_argument_converts_existing_msys_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "tmp" / "session.pem"
            target.parent.mkdir()
            target.write_text("fixture", encoding="ascii")
            self.assertEqual(
                RELAY.windows_argument("/tmp/session.pem", root),
                target.as_posix(),
            )
            self.assertEqual(RELAY.windows_argument("/CN=any", root), "/CN=any")

    def test_invalid_environment_transport_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "count"):
            RELAY.relayed_arguments({"WOARM64_NATIVE_ARG_COUNT": "-1"}, [])
        with self.assertRaisesRegex(ValueError, "missing"):
            RELAY.relayed_arguments({"WOARM64_NATIVE_ARG_COUNT": "1"}, [])
        with self.assertRaisesRegex(ValueError, "encoding"):
            RELAY.relayed_arguments(
                {"WOARM64_NATIVE_ARG_COUNT": "1", "WOARM64_NATIVE_ARG_0": "/CN=any"},
                [],
            )

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
