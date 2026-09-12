"""Synthetic control tests; never launch helpers or touch Windows credentials."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sources import ContractError, digest


HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("helper_builder", "build-winapi-helpers.py")
wincred = load("wincred_fixture", "test-wincred.py")


class HelperControls(unittest.TestCase):
    def test_no_budget_never_starts_build(self):
        with patch.object(builder.sys, "platform", "linux"), \
                patch.object(builder.platform, "machine", return_value="aarch64"), \
                patch.object(builder.subprocess, "run") as command:
            with self.assertRaisesRegex(ContractError, "approved positive"):
                builder.build("unused", "unused", "unused", 0)
            command.assert_not_called()

    def test_duplicate_credential_keys_rejected(self):
        with self.assertRaisesRegex(ContractError, "Malformed/duplicate"):
            wincred.parse_credential("username=one\nusername=two\n")

    def test_invalid_credential_response_rejected(self):
        with self.assertRaisesRegex(ContractError, "Malformed/duplicate"):
            wincred.parse_credential("not a working credential helper\n")

    def exercise(self, mode):
        temporary = tempfile.TemporaryDirectory(prefix="wincred-control-not-native-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        executable = (root / "helper.exe").resolve()
        executable.write_bytes(b"synthetic-not-PE")
        output = root / "evidence"
        vault, operations = {}, []

        class FakeProcess:
            pid = 123

            def __init__(self, argv, **kwargs):
                self.operation = argv[1]
                self.returncode = None

            def communicate(self, request=b"", timeout=None):
                operations.append(self.operation)
                fields = wincred.parse_credential((request or b"").decode("utf-8"))
                self.returncode = 0
                if self.operation == "get":
                    if mode == "existing" and len(operations) == 1:
                        return b"username=existing\npassword=leave-alone\n", b""
                    if vault:
                        if mode == "invalid-utf8":
                            return b"\xf0=corrupted-protocol\n", b""
                        if mode == "extra-newline":
                            return f"username={vault['username']}\npassword={vault['password']}\n\n".encode(), b""
                        if mode == "unexpected-stderr":
                            return f"username={vault['username']}\npassword={vault['password']}\n".encode(), b"unexpected"
                        return f"username={vault['username']}\npassword={vault['password']}\n".encode(), b""
                elif self.operation == "store":
                    vault.update(fields)
                    if mode == "partial-store-failure":
                        self.returncode = 1
                        return b"", b"injected partial-store error"
                elif self.operation == "erase":
                    if mode == "erase-failure":
                        self.returncode = 1
                        return b"", b"injected erase error"
                    vault.clear()
                return b"", b""

            def poll(self):
                return self.returncode

            def kill(self):
                self.returncode = 1

        def fake_gate(pwsh, script, arguments, report):
            if script == "process-gate":
                return {"Passed": True, "MeasuredCount": 1, "Processes": [{
                    "ProcessId": 123, "ImagePath": str(executable),
                    "NativeArm64Process": True, "ProcessMachine": "0xAA64"}]}
            return {"Passed": True, "ParsedCount": 1, "Files": [{
                "SHA256": digest(executable), "NativeArm64Header": True}]}

        original_digest = wincred.digest

        def test_digest(path):
            return "1" * 64 if str(path).endswith("-gate") else original_digest(path)

        with patch.object(wincred.platform, "system", return_value="Windows"), \
                patch.object(wincred.platform, "machine", return_value="ARM64"), \
                patch.dict(wincred.os.environ, {"SystemRoot": str(root / "Windows")}), \
                patch.object(wincred, "gate", side_effect=fake_gate), \
                patch.object(wincred, "digest", side_effect=test_digest), \
                patch.object(wincred, "credential_exists", side_effect=lambda target: bool(vault)), \
                patch.object(wincred, "remove_fixture_credential", side_effect=lambda target: vault.clear()), \
                patch.object(wincred.subprocess, "Popen", FakeProcess), \
                patch("builtins.print"):
            if mode == "success":
                wincred.test(executable, output, "pwsh", "artifact-gate", "process-gate")
            else:
                with self.assertRaises(ContractError):
                    wincred.test(executable, output, "pwsh", "artifact-gate", "process-gate")
        result = json.loads((output / "result.json").read_text())
        if mode == "invalid-utf8":
            self.assertEqual((output / "03-get.stdout.bin").read_bytes(), b"\xf0=corrupted-protocol\n")
            self.assertIn("decode_error", result["commands"][2])
        return vault, operations, result["status"]

    def test_store_get_erase_lifecycle(self):
        vault, operations, status = self.exercise("success")
        self.assertFalse(vault)
        self.assertEqual(operations, ["get", "store", "get", "erase", "get"])
        self.assertEqual(status, "native-wincred-store-get-erase-passed")

    def test_partial_store_failure_still_erases(self):
        vault, operations, status = self.exercise("partial-store-failure")
        self.assertFalse(vault)
        self.assertIn("erase", operations)
        self.assertEqual(status, "failed")

    def test_erase_failure_never_reports_pass(self):
        vault, _, status = self.exercise("erase-failure")
        self.assertFalse(vault)
        self.assertEqual(status, "store-get-passed-cleanup-pending")

    def test_existing_credential_is_never_removed(self):
        _, operations, status = self.exercise("existing")
        self.assertEqual(operations, ["get"])
        self.assertEqual(status, "failed")

    def test_invalid_utf8_is_preserved_and_cleanup_runs(self):
        vault, operations, status = self.exercise("invalid-utf8")
        self.assertFalse(vault)
        self.assertIn("erase", operations)
        self.assertEqual(status, "failed")

    def test_extra_protocol_newline_rejected_and_cleanup_runs(self):
        vault, operations, status = self.exercise("extra-newline")
        self.assertFalse(vault)
        self.assertIn("erase", operations)
        self.assertEqual(status, "failed")

    def test_unexpected_stderr_rejected_and_cleanup_runs(self):
        vault, operations, status = self.exercise("unexpected-stderr")
        self.assertFalse(vault)
        self.assertIn("erase", operations)
        self.assertEqual(status, "failed")


if __name__ == "__main__":
    unittest.main()
