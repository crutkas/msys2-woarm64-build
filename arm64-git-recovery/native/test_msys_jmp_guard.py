from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from compiler_tools import require_msys_jump_receipt, verify_msys_jmp_headers
from sources import ContractError


class MsysJumpHeaderControls(unittest.TestCase):
    def test_header_overlay_alone_is_not_coherent_sdk_proof(self):
        with self.assertRaises(ContractError):
            require_msys_jump_receipt({})
        record = {"source_jump_buffer_qualification": {
            "JmpBufBytes": 256, "SigjmpBufBytes": 272, "SaveMaskOffset": 256, "SignalMaskOffset": 264}}
        with self.assertRaises(ContractError):
            require_msys_jump_receipt(record)
        proof = {"Path": "unit-fixture", "SHA256": "0" * 64}
        record["source_jump_buffer_qualification"].update({
            "ExistingConsumersRecompiled": False, "Header": proof, "Consumer": proof, "RuntimeReceipt": proof})
        record["source_runtime_pairing"] = {"SysrootManifest": proof, "DllManifest": proof}
        require_msys_jump_receipt(record)

    def test_old_header_diagnostic_fails_closed(self):
        with patch("compiler_tools.subprocess.run", return_value=SimpleNamespace(
                returncode=1, stderr=b"static assertion failed: 256-byte runtime ABI")):
            with self.assertRaisesRegex(ContractError, "coherent corrected SDK"):
                verify_msys_jmp_headers("fixture-gcc")

    def test_guard_never_links_or_executes_target(self):
        with tempfile.TemporaryDirectory(prefix="msys-jmp-guard-") as directory:
            compiler = Path(directory) / "fixture-gcc"
            compiler.write_bytes(b"unit control")
            with patch("compiler_tools.subprocess.run", return_value=SimpleNamespace(
                    returncode=0, stderr=b"")) as run:
                result = verify_msys_jmp_headers(compiler, {"PATH": "controlled"})
            self.assertIn("-fsyntax-only", run.call_args.args[0])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs["env"], {"PATH": "controlled"})
            self.assertIn("no target execution", result["scope"])


if __name__ == "__main__":
    unittest.main()
