import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from sources import ContractError, digest, inventory
from tcl_build_inputs import forward_dltest_ldflags

spec = importlib.util.spec_from_file_location("msys_tcl", Path(__file__).with_name("build-msys-tcl.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MsysTclInputControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "private"
        self.prefix.mkdir()
        (self.prefix / "original").write_bytes(b"retained")
        self.base = self.root / "base.json"
        self.base.write_text(json.dumps({"status": "private-ssh-bootstrap-byte-identical-not-executed",
                                        "prefix": str(self.prefix), "files": inventory(self.prefix)}))
        self.archive = self.root / "signed-package"
        self.archive.write_bytes(b"unexecuted unit fixture")
        self.signature = self.root / "signature"
        self.signature.write_bytes(b"unexecuted unit fixture signature")
        self.record = {
            "status": "private-bootstrap-with-signature-verified-host-generators", "prefix": str(self.prefix),
            "base_copy": {"path": str(self.base), "sha256": digest(self.base)},
            "packages": [{"path": str(self.archive), "sha256": digest(self.archive),
                          "signature": {"path": str(self.signature), "sha256": digest(self.signature)}}],
            "evidence": [], "install": {"raw_exit": 0, "signature_policy": "Required"},
            "signature_verification": {"raw_exit": 0, "valid_signatures": 1, "signers": ["unit-fixture"]},
            "files": inventory(self.prefix),
        }
        self.manifest = self.root / "augmented.json"

    def verify(self):
        self.manifest.write_text(json.dumps(self.record))
        return module.verify_bootstrap(self.prefix, self.manifest)

    def test_explicit_augmentation_retains_original_identity(self):
        result = self.verify()
        self.assertEqual(result["base_copy"]["sha256"], digest(self.base))

    def test_unchecked_signature_or_disabled_policy_rejected(self):
        self.record["signature_verification"]["valid_signatures"] = 0
        with self.assertRaises(ContractError):
            self.verify()
        self.record["signature_verification"]["valid_signatures"] = 1
        self.record["install"]["signature_policy"] = "Never"
        with self.assertRaises(ContractError):
            self.verify()

    def test_archive_or_existing_driver_mutation_rejected(self):
        self.archive.write_bytes(b"changed archive")
        with self.assertRaises(ContractError):
            self.verify()
        self.record["packages"][0]["sha256"] = digest(self.archive)
        (self.prefix / "original").write_bytes(b"changed driver")
        self.record["files"] = inventory(self.prefix)
        with self.assertRaises(ContractError):
            self.verify()

    def test_all_existing_dynamic_load_link_flags_forwarded_without_dropping_libraries(self):
        text = "".join(f"\t${{{linker}}} -o pkg{index}.dll pkg{index}.o ${{SHLIB_LD_LIBS}}\n"
                       for linker in ("SHLIB_LD", "DLTEST_LD") for index in range(7))
        corrected = forward_dltest_ldflags(text)
        self.assertEqual(corrected.count("${LDFLAGS} ${SHLIB_LD_LIBS}"), 14)
        self.assertEqual(forward_dltest_ldflags(corrected), corrected)
        with self.assertRaises(ContractError):
            forward_dltest_ldflags(text.split("\n", 1)[1])


if __name__ == "__main__":
    unittest.main()
