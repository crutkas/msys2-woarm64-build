import importlib.util
from pathlib import Path
import unittest

from sources import ContractError
from openssl_contracts import require_msys_build


spec = importlib.util.spec_from_file_location("openssl_native_builder", Path(__file__).with_name("build-openssl.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tls_spec = importlib.util.spec_from_file_location("openssl_tls", Path(__file__).with_name("test-openssl-tls.py"))
tls = importlib.util.module_from_spec(tls_spec)
tls_spec.loader.exec_module(tls)


class OpenSslAbiControls(unittest.TestCase):
    def test_msys_is_lp64(self):
        module.validate_abi("Cygwin-aarch64", {
            "__aarch64__": "1", "__SIZEOF_POINTER__": "8", "__SIZEOF_LONG__": "8", "__MSYS__": "1"})

    def test_mingw_is_llp64(self):
        module.validate_abi("mingwarm64", {
            "__aarch64__": "1", "__SIZEOF_POINTER__": "8", "__SIZEOF_LONG__": "4", "__MINGW32__": "1"})

    def test_mingw_cannot_supply_msys_crypto(self):
        with self.assertRaises(ContractError):
            module.validate_abi("Cygwin-aarch64", {
                "__aarch64__": "1", "__SIZEOF_POINTER__": "8", "__SIZEOF_LONG__": "4", "__MINGW32__": "1"})

    def test_raw_cygwin_does_not_fake_msys(self):
        with self.assertRaises(ContractError):
            module.validate_abi("Cygwin-aarch64", {
                "__aarch64__": "1", "__SIZEOF_POINTER__": "8", "__SIZEOF_LONG__": "8", "__CYGWIN__": "1"})

    def test_runtime_module_profiles_do_not_alias(self):
        self.assertEqual(tls.module_names("msys"), ("msys-crypto-3.dll", "msys-ssl-3.dll", "msys-2.0.dll"))
        self.assertEqual(tls.module_names("mingw"), ("libcrypto-3.dll", "libssl-3.dll"))
        with self.assertRaises(ContractError):
            tls.module_names("unknown")

    def test_deferred_mingw_build_cannot_be_restaged_as_msys(self):
        record = {"status": "native-openssl-built-tests-deferred", "target_profile": "mingwarm64"}
        with self.assertRaises(ContractError):
            require_msys_build(record)
        record["target_profile"] = "Cygwin-aarch64"
        with self.assertRaises(ContractError):
            require_msys_build(record)
        record["measured_abi_macros"] = {"__aarch64__": "1", "__SIZEOF_POINTER__": "8",
                                       "__SIZEOF_LONG__": "8", "__MSYS__": "1"}
        require_msys_build(record)


if __name__ == "__main__":
    unittest.main()
