import importlib.util
from pathlib import Path
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("msys_library", Path(__file__).with_name("build-msys-library.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MsysLibraryControls(unittest.TestCase):
    def test_xz_keeps_full_cli_library_and_documentation_payload(self):
        module.validate_source("xz-msys", {
            "source": {"id": "xz", "version": "5.8.3"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "build_policy": {"windows_doxygen_paths": True},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})
        for name in ("bin/msys-lzma-5.dll", "bin/xz.exe", "lib/liblzma.a",
                     "lib/liblzma.dll.a", "share/doc/xz/api/index.html"):
            self.assertIn(name, module.PROFILES["xz-msys"]["required"])

    def test_xz_cannot_use_iconv_without_native_gettext(self):
        files = {name: {} for name in ("usr/include/iconv.h", "usr/lib/libiconv.dll.a",
                                      "usr/bin/msys-iconv-2.dll")}
        with self.assertRaises(ContractError):
            module.validate_dependency("xz-msys", files)
        files.update({name: {} for name in ("usr/include/libintl.h", "usr/lib/libintl.dll.a",
                                           "usr/bin/libintl-8.dll")})
        with self.assertRaises(ContractError):
            module.validate_dependency("xz-msys", files)
        files["usr/bin/msys-intl-8.dll"] = {}
        module.validate_dependency("xz-msys", files)

    def test_unpatched_xz_documentation_source_is_rejected(self):
        for policy in (None, {}, {"windows_doxygen_paths": False}):
            record = {"source": {"id": "xz", "version": "5.8.3"},
                      "libtool_dependency": {"manifest_sha256": "0" * 64},
                      "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes",
                      "build_policy": policy}
            with self.subTest(policy=policy), self.assertRaises(ContractError):
                module.validate_source("xz-msys", record)

    def test_gettext_requires_same_abi_iconv_payload(self):
        with self.assertRaises(ContractError):
            module.validate_dependency("gettext-msys", {})
        files = {name: {} for name in ("usr/include/iconv.h", "usr/lib/libiconv.dll.a",
                                      "usr/bin/libiconv-2.dll")}
        with self.assertRaises(ContractError):
            module.validate_dependency("gettext-msys", files)
        files["usr/bin/msys-iconv-2.dll"] = {}
        module.validate_dependency("gettext-msys", files)

    def test_zlib_uses_its_pinned_nonlibtool_build(self):
        module.validate_source("zlib-msys", {
            "source": {"id": "zlib", "version": "1.3.2"},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})
        self.assertIn("bin/msys-z.dll", module.PROFILES["zlib-msys"]["required"])

    def test_prepared_native_msys_input(self):
        module.validate_source("libxcrypt", {
            "source": {"id": "libxcrypt", "version": "4.5.2"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})

    def test_raw_mingw_source_does_not_substitute(self):
        with self.assertRaises(ContractError):
            module.validate_source("libiconv-bootstrap", {"source": {"id": "libiconv", "version": "1.19"}})

    def test_wrong_package_version_is_rejected(self):
        with self.assertRaises(ContractError):
            module.validate_source("libxcrypt", {
                "source": {"id": "libxcrypt", "version": "4.4.0"},
                "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})

    def test_iconv_bootstrap_omission_is_explicit(self):
        self.assertIn("NLS explicitly disabled", module.PROFILES["libiconv-bootstrap"]["limitations"][0])

    def test_stock_generator_preparation_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "bound MSYS-aware generator"):
            module.validate_source("libxcrypt", {
                "source": {"id": "libxcrypt", "version": "4.5.2"},
                "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})


if __name__ == "__main__":
    unittest.main()
