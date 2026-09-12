import importlib.util
from pathlib import Path
import unittest

from sources import ContractError


spec = importlib.util.spec_from_file_location(
    "autotools_library", Path(__file__).with_name("build-autotools-library.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AutotoolsInputControls(unittest.TestCase):
    def idn_files(self):
        return dict.fromkeys((*module.REQUIRED_HEADERS["libidn2"], "lib/libiconv.dll.a",
                              "lib/libunistring.a", "lib/libintl.dll.a"))

    def test_exact_pin_and_dependency_headers(self):
        module.validate_inputs("libidn2", {"id": "libidn2", "version": "2.3.8"},
                               self.idn_files())

    def test_missing_gettext_cannot_silently_disable_nls(self):
        files = self.idn_files()
        del files["include/libintl.h"]
        with self.assertRaises(ContractError):
            module.validate_inputs("libidn2", {"id": "libidn2", "version": "2.3.8"}, files)

    def test_header_without_library_is_rejected(self):
        files = self.idn_files()
        del files["lib/libintl.dll.a"]
        with self.assertRaises(ContractError):
            module.validate_inputs("libidn2", {"id": "libidn2", "version": "2.3.8"}, files)

    def test_wrong_version_rejected(self):
        with self.assertRaises(ContractError):
            module.validate_inputs("libiconv", {"id": "libiconv", "version": "1.18"}, {})

    def test_iconv_is_an_independent_leaf(self):
        module.validate_inputs("libiconv", {"id": "libiconv", "version": "1.19"}, {})

    def test_static_intl_cannot_satisfy_shared_profile(self):
        with self.assertRaises(ContractError):
            module.validate_outputs("gettext-runtime", "both", dict.fromkeys((
                "lib/libintl.a", "lib/libasprintf.a", "lib/libasprintf.dll.a", "bin/libasprintf-0.dll")))

    def test_complete_shared_profile(self):
        module.validate_outputs("libidn2", "shared",
                                dict.fromkeys(("bin/libidn2-0.dll", "lib/libidn2.dll.a")))


if __name__ == "__main__":
    unittest.main()
