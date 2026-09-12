import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fido_build_inputs import copy_windows_imports, retained_abi, rewrite_pc, verify_windows_imports
from sources import ContractError, digest, inventory


class FidoMetadataControls(unittest.TestCase):
    text = "prefix=/usr\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\nVersion: 0.14.0\nLibs: -L${libdir} -lcbor\nCflags: -I${includedir}\n"

    def test_only_real_path_variables_and_header_roots_change(self):
        result = rewrite_pc(self.text, {"libdir": "C:/build/src", "includedir": "C:/source/src"}, ["C:/build", "C:/build/src"])
        self.assertIn("Version: 0.14.0\nLibs: -L${libdir} -lcbor", result)
        self.assertIn("Cflags: -I${includedir} -IC:/build -IC:/build/src", result)
        self.assertIn("prefix=/usr", result)

    def test_ambiguous_or_unrepresentable_metadata_rejected(self):
        for text, variables in ((self.text + "libdir=duplicate\n", {"libdir": "C:/build"}),
                                (self.text, {"missing": "C:/build"}),
                                (self.text, {"libdir": "C:/ambiguous path"})):
            with self.assertRaises(ContractError):
                rewrite_pc(text, variables)


class WindowsImportControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / "sealed"
        lib = self.payload / "aarch64-pc-cygwin/lib"
        lib.mkdir(parents=True)
        for name in ("wsock32", "bcrypt", "setupapi", "hid"):
            (lib / f"lib{name}.a").write_bytes(b"unexecuted unit fixture")
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text("{}")
        bound = {"path": str(self.evidence), "sha256": digest(self.evidence)}
        self.record = {
            "status": "qualified-msys-windows-import-overlay-link-only",
            "compiler_base": bound,
            "source_target": {"DataModel": "LP64", "ThreadModel": "posix",
                              "Triple": "aarch64-pc-cygwin", "Profile": "MSYS"},
            "payload_root": str(self.payload),
            "qualification": {"archive_generation": bound, "actual_fido_link": bound},
            "source": {"license": bound},
            "files": [{"Path": name, "SHA256": row["sha256"], "Size": row["size"]}
                      for name, row in inventory(self.payload).items()],
        }
        self.handoff = self.root / "handoff.json"

    def copy(self):
        self.handoff.write_text(json.dumps(self.record))
        return copy_windows_imports(self.handoff, digest(self.handoff), self.evidence, self.root / "copy")

    def test_only_four_byte_identical_archives_copied(self):
        before = inventory(self.payload)
        result = self.copy()
        self.assertEqual(result["files"], before)
        self.assertEqual(inventory(self.payload), before)
        verify_windows_imports(result)
        (Path(result["prefix"]) / "unexpected.a").write_bytes(b"not admitted")
        with self.assertRaises(ContractError):
            verify_windows_imports(result)

    def test_wrong_compiler_and_non_msys_target_rejected(self):
        self.record["compiler_base"] = {"sha256": "0" * 64}
        with self.assertRaises(ContractError):
            self.copy()
        self.record["compiler_base"]["sha256"] = digest(self.evidence)
        self.record["source_target"]["DataModel"] = "LLP64"
        with self.assertRaises(ContractError):
            self.copy()

    def test_extra_duplicate_or_traversing_paths_rejected(self):
        original = list(self.record["files"])
        for name in ("../outside.a", "aarch64-pc-cygwin/lib/libcrt.a", original[0]["Path"]):
            self.record["files"] = original + [{"Path": name, "SHA256": "0" * 64, "Size": 0}]
            with self.assertRaises(ContractError):
                self.copy()

    def test_payload_drift_rejected_before_copy(self):
        (self.payload / self.record["files"][0]["Path"]).write_bytes(b"drift")
        with self.assertRaises(ContractError):
            self.copy()
        self.assertFalse((self.root / "copy").exists())

    def test_successor_requires_retained_abi_without_relabelling_overlay_base(self):
        successor = self.root / "successor.json"
        successor.write_text('{"generation": 2}')
        self.handoff.write_text(json.dumps(self.record))
        handoff_sha = digest(self.handoff)
        retained = {"current_sha256": digest(successor), "predecessor_sha256": digest(self.evidence)}
        with patch("fido_build_inputs.retained_abi", return_value=retained) as verify:
            result = copy_windows_imports(self.handoff, handoff_sha, successor, self.root / "copy",
                                          compiler_ancestors=[self.evidence])
        verify.assert_called_once_with(successor, self.evidence, [])
        self.assertEqual(result["overlay_base_receipt_sha256"], digest(self.evidence))
        self.assertEqual(result["compiler_receipt_sha256"], digest(successor))
        self.assertEqual(result["retained_abi"], retained)
        self.assertEqual(digest(self.handoff), handoff_sha)


class CompilerLineageControls(unittest.TestCase):
    def test_explicit_cc1_only_successor_retains_real_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cc1 = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe"
            base = {"prefix": str(root), "files": {cc1: {"sha256": "old"},
                                                   "bin/msys-2.0.dll": {"sha256": "unchanged"}}}
            prior = root / "prior.json"
            prior.write_text(json.dumps(base))
            middle_record = {**base, "files": {**base["files"], cc1: {"sha256": "middle"}},
                             "source_compiler_delta": {"base_receipt_sha256": digest(prior), "changed_files": [cc1]}}
            middle = root / "middle.json"
            middle.write_text(json.dumps(middle_record))
            current_record = {**base, "files": {**base["files"], cc1: {"sha256": "new"}},
                              "source_compiler_delta": {"base_receipt_sha256": digest(middle), "changed_files": [cc1]}}
            current = root / "current.json"
            current.write_text(json.dumps(current_record))
            with patch("fido_build_inputs.verify_tree"), patch("fido_build_inputs.require_msys_ucontext_receipt"):
                result = retained_abi(current, prior, [middle])
                self.assertEqual(result["receipt_chain_sha256"], [digest(current), digest(middle), digest(prior)])
                with self.assertRaises(ContractError):
                    retained_abi(current, prior)
                current_record["files"]["bin/msys-2.0.dll"]["sha256"] = "runtime-swap"
                current.write_text(json.dumps(current_record))
                with self.assertRaises(ContractError):
                    retained_abi(current, prior, [middle])


if __name__ == "__main__":
    unittest.main()
