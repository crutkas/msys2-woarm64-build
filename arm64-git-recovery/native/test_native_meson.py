import importlib.util
from pathlib import Path
import unittest

from sources import ContractError


spec = importlib.util.spec_from_file_location("native_meson", Path(__file__).with_name("build-native-meson.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeMesonControls(unittest.TestCase):
    def rows(self):
        rows = [{"name": "libpsl:" + name, "result": "OK", "returncode": 0} for name in (
            "test-is-public", "test-is-public-all", "test-is-cookie-domain-acceptable",
            "test-is-public-builtin", "test-registrable-domain")]
        rows += [{"name": "libpsl:" + name, "result": "SKIP", "returncode": 77} for name in (
            "libpsl_idn2_fuzzer", "libpsl_idn2_load_fuzzer", "libpsl_idn2_load_dafsa_fuzzer")]
        return rows

    def test_only_documented_platform_fuzz_exclusions(self):
        self.assertEqual(len(module.validate_tests("libpsl", 8, self.rows(), "#undef HAVE_FMEMOPEN\n")), 3)

    def test_available_fmemopen_cannot_skip(self):
        with self.assertRaises(ContractError):
            module.validate_tests("libpsl", 8, self.rows(), "#define HAVE_FMEMOPEN 1\n")

    def test_functional_failure_is_not_waived(self):
        rows = self.rows()
        rows[0]["result"] = "FAIL"
        with self.assertRaises(ContractError):
            module.validate_tests("libpsl", 8, rows, "#undef HAVE_FMEMOPEN\n")

    def test_unexpected_skip_rejected(self):
        rows = self.rows()
        rows[-1]["name"] = "libpsl:unexpected"
        with self.assertRaises(ContractError):
            module.validate_tests("libpsl", 8, rows, "#undef HAVE_FMEMOPEN\n")

    def test_pkgconf_still_rejects_all_skips(self):
        with self.assertRaises(ContractError):
            module.validate_tests("pkgconf", 8, self.rows(), "#undef HAVE_FMEMOPEN\n")

    def test_incomplete_test_set_rejected(self):
        with self.assertRaises(ContractError):
            module.validate_tests("libpsl", 9, self.rows(), "#undef HAVE_FMEMOPEN\n")


if __name__ == "__main__":
    unittest.main()
