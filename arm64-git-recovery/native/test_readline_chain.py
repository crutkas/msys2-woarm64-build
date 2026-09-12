import importlib
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from readline_chain_inputs import ROOT, HERE, fresh, sealed
from sources import ContractError

build = importlib.import_module("build-readline-chain")
export = importlib.import_module("export-readline-chain")


class NativeTerminalChainControls(unittest.TestCase):
    def test_ncurses_requires_full_cxx_static_shared_and_terminfo(self):
        required = build.required_files("ncurses")
        for library in ("ncurses", "ncurses++", "form", "menu", "panel", "tic"):
            self.assertIn(f"usr/lib/lib{library}w.a", required)
            self.assertIn(f"usr/lib/lib{library}w.dll.a", required)
            self.assertIn(f"usr/bin/msys-{library}w6.dll", required)
        self.assertIn("usr/share/terminfo/78/xterm-256color", required)

    def test_readline_requires_both_libraries_and_inputrc(self):
        required = build.required_files("readline")
        for name in ("readline", "history"):
            self.assertIn(f"usr/lib/lib{name}.a", required)
            self.assertIn(f"usr/lib/lib{name}.dll.a", required)
            self.assertIn(f"usr/bin/msys-{name}8.dll", required)
        self.assertIn("etc/inputrc", required)

    def test_libedit_requires_wide_api_header_and_both_linkages(self):
        required = build.required_files("libedit")
        self.assertIn("usr/include/histedit.h", required)
        self.assertIn("usr/include/editline/readline.h", required)
        self.assertIn("usr/lib/libedit.a", required)
        self.assertIn("usr/lib/libedit.dll.a", required)

    def test_private_environment_bounds_threads_and_preserves_pathext(self):
        env = build.environment(ROOT / "test-environment", 2)
        self.assertEqual(env["MAKEFLAGS"], "-j2")
        self.assertEqual(env["OMP_NUM_THREADS"], "1")
        self.assertEqual(env["OPENBLAS_NUM_THREADS"], "1")
        self.assertEqual(env["WOARM64_NATIVE_ARG_CONVERSION"], "none")
        self.assertEqual(env["PATHEXT"], os.environ["PATHEXT"])
        self.assertNotIn("LIBRARY_PATH", env)
        self.assertTrue(Path(env["HOME"]).is_relative_to(ROOT))

    def test_missing_pathext_is_not_silently_replaced(self):
        with patch.dict(os.environ, {"PATHEXT": ""}):
            with self.assertRaisesRegex(ContractError, "PATHEXT"):
                build.environment(ROOT / "test-environment", 1)

    def test_old_roots_cannot_be_outputs(self):
        with self.assertRaises(ContractError):
            fresh(Path(r"C:\ag-e138920f\not-an-owned-output"))

    def test_changed_seal_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "seal differs"):
            sealed(HERE / "readline_chain_inputs.py", "0" * 64)

    def test_multibyte_profile_cannot_be_disabled_or_partially_enabled(self):
        keys = ("HAVE_WCTYPE_H", "HAVE_WCHAR_H", "HAVE_LOCALE_H", "HAVE_ISWCTYPE",
                "HAVE_ISWLOWER", "HAVE_ISWUPPER", "HAVE_MBSRTOWCS", "HAVE_MBRTOWC",
                "HAVE_MBRLEN", "HAVE_WCHAR_T", "HAVE_WCWIDTH")
        config = "\n".join(f"#define {key} 1" for key in keys)
        self.assertTrue(build.readline_multibyte(config)["HANDLE_MULTIBYTE"])
        for invalid in (config + "\n#define NO_MULTIBYTE_SUPPORT 1",
                        config.replace("#define HAVE_WCWIDTH 1", "/* #undef HAVE_WCWIDTH */")):
            with self.assertRaises(ContractError):
                build.readline_multibyte(invalid)

    def test_archive_machine_is_read_from_actual_members(self):
        member = struct.pack("<HHIIIHH", 0xAA64, 1, 0, 0, 0, 0, 0) + bytes(40)
        header = b"member.o/       " + b"0           " + b"0     " + b"0     " + b"0       " + b"60        " + b"`\n"
        archive = b"!<arch>\n" + header + member
        self.assertEqual(export.coff_archive(archive)[0]["machine"], 0xAA64)
        with self.assertRaisesRegex(ContractError, "Non-ARM64"):
            export.coff_archive(archive[:68] + b"\x64\x86" + archive[70:])
        with self.assertRaises(ContractError):
            export.coff_archive(archive[:-1])


if __name__ == "__main__":
    unittest.main()
