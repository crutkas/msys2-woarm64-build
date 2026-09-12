import re
import unittest
from pathlib import Path

from sources import ContractError
from sqlite_build_inputs import SPLITS, TOOLS, extension_makefile, msys_path, recipe, tcl_config_view


class SqliteInputsTests(unittest.TestCase):
    def test_complete_pinned_recipe(self):
        contract = recipe()
        self.assertEqual(contract["version"], "3.53.4")
        self.assertEqual(len(contract["cppflags"]), 20)
        self.assertIn("-DSQLITE_ENABLE_UPDATE_DELETE_LIMIT=1", contract["cppflags"])
        self.assertIn("--all", contract["configure"])
        self.assertEqual(len(SPLITS), 7)
        self.assertEqual(len(TOOLS), 5)

    def test_explicit_native_drive_path(self):
        self.assertEqual(msys_path(Path(r"C:\ag-sqlite-e138-01\build")), "/c/ag-sqlite-e138-01/build")
        with self.assertRaises(ContractError):
            msys_path(Path(r"C:\ambiguous path"))

    def test_tcl_version_and_feature_fields_are_not_rewritten(self):
        text = "\n".join(f"{key}='{value}'" for key, value in {
            "TCL_VERSION": "8.6", "TCL_PATCH_LEVEL": ".12", "TCL_DEFS": "-DTCL_THREADS=1",
            "TCL_CC": "/old/gcc", "TCL_RANLIB": "/old/ranlib",
            "TCL_PREFIX": "/usr", "TCL_EXEC_PREFIX": "/usr", "TCL_INCLUDE_SPEC": "-I/usr/include",
            "TCL_LIB_SPEC": "-L/usr/lib -ltcl8.6", "TCL_BUILD_LIB_SPEC": "-L/old -ltcl8.6",
            "TCL_STUB_LIB_SPEC": "-L/usr/lib -ltclstub8.6", "TCL_BUILD_STUB_LIB_SPEC": "-L/old -ltclstub8.6",
            "TCL_STUB_LIB_PATH": "/usr/lib/libtclstub8.6.a", "TCL_BUILD_STUB_LIB_PATH": "/old/libtclstub8.6.a",
            "TCL_SRC_DIR": "/old/source", "TCL_PACKAGE_PATH": "{/usr/lib} ",
            "TCL_EXTRA_CFLAGS": "-O2 -fstack-protector-strong -IC:/old/zlib-msys-01/stage/usr/include",
            "TCL_LD_FLAGS": "-LC:/old/zlib-msys-01/stage/usr/lib ",
        }.items())
        updated, fields = tcl_config_view(text, Path(r"C:\ag-sqlite-e138-01"))
        self.assertNotIn("TCL_VERSION", fields)
        self.assertNotIn("TCL_DEFS", fields)
        self.assertIn("TCL_PATCH_LEVEL='.12'", updated)
        self.assertIn("-O2 -fstack-protector-strong -IC:/ag-sqlite-e138-01/zlib/usr/include", updated)
        self.assertEqual(len(re.findall("^TCL_", text, re.M)), len(re.findall("^TCL_", updated, re.M)))

    def test_fail_closed_on_unrecognized_metadata(self):
        with self.assertRaises(ContractError):
            tcl_config_view("TCL_VERSION='8.6'\n", Path(r"C:\ag-sqlite-e138-01"))
        with self.assertRaises(ContractError):
            extension_makefile("CC=@CC@", Path(r"C:\ag-sqlite-e138-01"), Path(r"C:\ag-sqlite-e138-01\build"))

    def test_no_failure_mask_or_unbounded_make(self):
        script = Path(__file__).with_name("build-msys-sqlite.sh").read_text()
        self.assertNotIn("|| true", script)
        self.assertNotRegex(script, r"make\s+-j(?:\s|$)")
        self.assertIn('TSTRNNR_OPTS=--jobs $jobs', script)
        self.assertIn("export MAKEFLAGS=-j1 MFLAGS=-j1", script)


if __name__ == "__main__":
    unittest.main()
