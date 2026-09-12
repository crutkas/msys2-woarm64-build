from pathlib import Path
import tempfile
import unittest

from package_tcl import finalize_tk, relocate_tcl_metadata, relocate_tk_metadata
from sources import ContractError


class TclMetadataControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-tcl-metadata-")
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        (self.stage / "lib/pkgconfig").mkdir(parents=True)
        self.config = self.stage / "lib/tclConfig.sh"
        names = ("TCL_PREFIX", "TCL_EXEC_PREFIX", "TCL_PACKAGE_PATH", "TCL_BUILD_LIB_SPEC",
                 "TCL_LIB_SPEC", "TCL_SRC_DIR", "TCL_INCLUDE_SPEC", "TCL_BUILD_STUB_LIB_SPEC",
                 "TCL_STUB_LIB_SPEC", "TCL_STUB_LIB_PATH", "TCL_BUILD_STUB_LIB_PATH")
        self.config.write_text("".join(f"{name}='/old/build'\n" for name in names))
        self.pc = self.stage / "lib/pkgconfig/tcl.pc"
        self.pc.write_text("prefix=/old/build\nexec_prefix=/old/build\nlibdir=/old/build/lib\n")

    def test_all_development_paths_are_retargeted(self):
        relocate_tcl_metadata(self.stage)
        self.assertNotIn("/old/build", self.config.read_text())
        self.assertIn(f"TCL_PREFIX='{self.stage.as_posix()}'", self.config.read_text())
        self.assertIn("/include/tcl8.6/tcl-private", self.config.read_text())

    def test_pkgconfig_is_relative(self):
        relocate_tcl_metadata(self.stage)
        self.assertEqual(self.pc.read_text(),
                         "prefix=${pcfiledir}/../..\nexec_prefix=${prefix}\nlibdir=${exec_prefix}/lib\n")

    def test_shell_metadata_is_lf_only(self):
        relocate_tcl_metadata(self.stage)
        self.assertNotIn(b"\r", self.config.read_bytes())
        self.assertNotIn(b"\r", self.pc.read_bytes())

    def test_missing_config_field_fails_closed(self):
        self.config.write_text("TCL_PREFIX='/old/build'\n")
        with self.assertRaises(ContractError):
            relocate_tcl_metadata(self.stage)

    def test_duplicate_config_field_fails_closed(self):
        with self.config.open("a") as stream:
            stream.write("TCL_PREFIX='/duplicate'\n")
        with self.assertRaises(ContractError):
            relocate_tcl_metadata(self.stage)

    def prepare_tk(self):
        config = self.stage / "lib/tkConfig.sh"
        names = ("TK_PREFIX", "TK_EXEC_PREFIX", "TK_BUILD_LIB_SPEC", "TK_LIB_SPEC", "TK_SRC_DIR",
                 "TK_BUILD_STUB_LIB_SPEC", "TK_STUB_LIB_SPEC", "TK_BUILD_STUB_LIB_PATH", "TK_STUB_LIB_PATH")
        config.write_text("".join(f"{name}='/old/build'\n" for name in names))
        pc = self.stage / "lib/pkgconfig/tk.pc"
        pc.write_text("prefix=/old/build\nexec_prefix=/old/build\nlibdir=/old/build/lib\n")
        return config, pc

    def test_tk_metadata_is_relocated_and_lf(self):
        config, pc = self.prepare_tk()
        relocate_tk_metadata(self.stage)
        self.assertNotIn("/old/build", config.read_text())
        self.assertIn("/include/tk8.6/tk-private", config.read_text())
        self.assertIn("prefix=${pcfiledir}/../..", pc.read_text())
        self.assertNotIn(b"\r", config.read_bytes())
        self.assertNotIn(b"\r", pc.read_bytes())

    def test_tk_missing_field_and_private_headers_are_rejected(self):
        config, _ = self.prepare_tk()
        config.write_text("TK_PREFIX='/old'\n")
        with self.assertRaises(ContractError):
            relocate_tk_metadata(self.stage)
        with self.assertRaises(ContractError):
            finalize_tk(self.stage / "missing-source", self.stage)


if __name__ == "__main__":
    unittest.main()
