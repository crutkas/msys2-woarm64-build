"""Receipt controls with synthetic files/reports, not native execution evidence."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime_readiness import verify
from sources import ContractError, digest


class RuntimeReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-readiness-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "prefix"
        self.image = r"C:\fixture\hello.exe"
        self.specs_output = b"synthetic default specs\n"
        self.support_tools = {
            name: self.file(f"prefix/support/{name}", f"synthetic {name}".encode())
            for name in ("cc1", "collect2", "as", "ld")
        }
        self.resolved_tools = {name: record["path"] for name, record in self.support_tools.items()}
        self.link_inputs = {
            "crt0.o": {"present": True, **self.file("prefix/lib/crt0.o", b"synthetic startup")},
            "libgcc.a": {"present": True, **self.file("prefix/lib/libgcc.a", b"synthetic compiler runtime")},
            "libgcc_eh.a": {"present": False},
            "libgcc_s.dll.a": {"present": False}
        }
        self.resolved_libraries = {name: record.get("path", name) for name, record in self.link_inputs.items()}

        def compiler_query(argv, **kwargs):
            if argv[1] == "-dumpspecs":
                output = self.specs_output
            elif argv[1].startswith("-print-file-name="):
                name = argv[1].removeprefix("-print-file-name=")
                output = (self.resolved_libraries[name] + "\n").encode()
            else:
                name = argv[1].removeprefix("-print-prog-name=")
                output = (self.resolved_tools[name] + "\n").encode()
            return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=b"")

        self.mock = patch("runtime_readiness.subprocess.run", side_effect=compiler_query)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.receipt = {
            "schema": 1, "target": "aarch64-pc-cygwin",
            "compiler": self.file("prefix/bin/msys2-gcc", b"synthetic wrapper"),
            "base_compiler": self.file("prefix/bin/aarch64-pc-cygwin-gcc", b"synthetic compiler"),
            "specs": self.file("prefix/lib/msys2.specs", b"synthetic overlay"),
            "runtime_dll": self.file("staged/msys-2.0.dll", b"synthetic DLL"),
            "installed_runtime_dll": self.file("prefix/bin/msys-2.0.dll", b"synthetic DLL"),
            "import_library": self.file("prefix/aarch64-pc-cygwin/lib/libmsys-2.0.a", b"synthetic importlib"),
            "source": self.file("hello.c", b"synthetic source"),
            "executable": self.file("hello.exe", b"synthetic executable"),
            "default_specs_sha256": hashlib.sha256(self.specs_output).hexdigest(),
            "support_tools": self.support_tools,
            "runtime_link_inputs": self.link_inputs,
            "link": {"exit_code": 0, "default_runtime_link": True},
            "run": {"exit_code": 0, "windows_image_path": self.image,
                    "windows_runtime_dll_path": r"C:\fixture\msys-2.0.dll",
                    "process_id": 123, "created_utc": "2026-09-05T00:00:00Z"}
        }
        self.receipt["link"]["argv"] = [
            self.receipt["compiler"]["path"], self.receipt["source"]["path"],
            "-o", self.receipt["executable"]["path"]]
        self.process = {
            "Passed": True, "RequestedCount": 1, "MeasuredCount": 1,
            "Processes": [{"ImagePath": self.image, "NativeArm64Process": True,
                           "ProcessId": 123, "CreatedUtc": "2026-09-05T00:00:00Z",
                           "ProcessMachine": "0xAA64", "Wow64ProcessMachine": "0x0000",
                           "NativeMachine": "0xAA64"}]
        }
        self.artifact = {
            "Passed": True, "CandidateCount": 2, "ParsedCount": 2,
            "Files": [
                {"Path": self.image, "SHA256": self.receipt["executable"]["sha256"],
                 "NativeArm64Header": True},
                {"Path": r"C:\fixture\msys-2.0.dll", "SHA256": self.receipt["runtime_dll"]["sha256"],
                 "NativeArm64Header": True}]
        }

    def file(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": str(path.resolve()), "sha256": digest(path)}

    def check(self):
        self.receipt["run"]["native_process_report"] = self.file(
            "process.json", json.dumps(self.process).encode())
        self.receipt["run"]["artifact_report"] = self.file(
            "artifact.json", json.dumps(self.artifact).encode())
        path = self.root / "receipt.json"
        path.write_text(json.dumps(self.receipt))
        return verify(path, self.prefix)

    def test_complete_receipt(self):
        self.assertRegex(self.check(), "^[0-9a-f]{64}$")

    def test_file_presence_without_receipt(self):
        with self.assertRaises(FileNotFoundError):
            verify(self.root / "absent.json", self.prefix)

    def test_raw_cygwin_driver_rejected(self):
        self.receipt["compiler"] = self.receipt["base_compiler"]
        with self.assertRaisesRegex(ContractError, "compiler does not belong"):
            self.check()

    def test_runtime_changed(self):
        Path(self.receipt["runtime_dll"]["path"]).write_bytes(b"rebuilt DLL")
        with self.assertRaisesRegex(ContractError, "missing or changed"):
            self.check()

    def test_specs_file_changed_even_if_dump_unchanged(self):
        Path(self.receipt["specs"]["path"]).write_bytes(b"changed overlay")
        with self.assertRaisesRegex(ContractError, "missing or changed"):
            self.check()

    def test_default_specs_changed(self):
        self.receipt["default_specs_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "default specs changed"):
            self.check()

    def test_manual_runtime_link_rejected(self):
        self.receipt["link"]["argv"].append("-lmsys-2.0")
        with self.assertRaisesRegex(ContractError, "default link interface"):
            self.check()

    def test_manual_specs_override_rejected(self):
        self.receipt["link"]["argv"].insert(1, "-specs=alternate.specs")
        with self.assertRaisesRegex(ContractError, "default link interface"):
            self.check()

    def test_failed_link_rejected(self):
        self.receipt["link"]["exit_code"] = 1
        with self.assertRaisesRegex(ContractError, "successful normal"):
            self.check()

    def test_failed_native_run_rejected(self):
        self.receipt["run"]["exit_code"] = 73
        with self.assertRaisesRegex(ContractError, "Successful native"):
            self.check()

    def test_legacy_tuple_alone_rejected(self):
        del self.process["Processes"][0]["ProcessMachine"]
        with self.assertRaisesRegex(ContractError, "ProcessMachineTypeInfo"):
            self.check()

    def test_wrong_live_image_rejected(self):
        self.process["Processes"][0]["ImagePath"] = r"C:\fixture\different.exe"
        with self.assertRaisesRegex(ContractError, "ProcessMachineTypeInfo"):
            self.check()

    def test_different_run_rejected(self):
        self.receipt["run"]["process_id"] = 456
        with self.assertRaisesRegex(ContractError, "ProcessMachineTypeInfo"):
            self.check()

    def test_live_image_hash_mismatch_rejected(self):
        self.artifact["Files"][0]["SHA256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "hash-bound linked executable"):
            self.check()

    def test_runtime_omitted_from_artifact_proof(self):
        self.artifact["Files"] = self.artifact["Files"][:1]
        self.artifact["CandidateCount"] = self.artifact["ParsedCount"] = 1
        with self.assertRaisesRegex(ContractError, "exact staged runtime"):
            self.check()

    def test_staged_runtime_must_match_installed_bytes(self):
        staged = Path(self.receipt["runtime_dll"]["path"])
        staged.write_bytes(b"different staged DLL")
        self.receipt["runtime_dll"]["sha256"] = digest(staged)
        with self.assertRaisesRegex(ContractError, "differs from the current installed"):
            self.check()

    def test_changed_installed_runtime_rejected(self):
        Path(self.receipt["installed_runtime_dll"]["path"]).write_bytes(b"new installed DLL")
        with self.assertRaisesRegex(ContractError, "missing or changed"):
            self.check()

    def test_wrong_staged_runtime_path_in_artifact_report_rejected(self):
        self.artifact["Files"][1]["Path"] = r"C:\different\msys-2.0.dll"
        with self.assertRaisesRegex(ContractError, "exact staged runtime"):
            self.check()

    def test_missing_support_record_rejected(self):
        del self.receipt["support_tools"]["as"]
        with self.assertRaisesRegex(ContractError, "Complete cc1/collect2/as/ld"):
            self.check()

    def test_replaced_assembler_invalidates_unchanged_driver(self):
        Path(self.support_tools["as"]["path"]).write_bytes(b"corrected assembler")
        with self.assertRaisesRegex(ContractError, "support programs changed: as"):
            self.check()

    def test_changed_linker_invalidates_receipt(self):
        Path(self.support_tools["ld"]["path"]).write_bytes(b"new linker")
        with self.assertRaisesRegex(ContractError, "support programs changed: ld"):
            self.check()

    def test_changed_frontend_invalidates_receipt(self):
        Path(self.support_tools["cc1"]["path"]).write_bytes(b"new frontend")
        with self.assertRaisesRegex(ContractError, "support programs changed: cc1"):
            self.check()

    def test_changed_collect2_invalidates_receipt(self):
        Path(self.support_tools["collect2"]["path"]).write_bytes(b"new collect2")
        with self.assertRaisesRegex(ContractError, "support programs changed: collect2"):
            self.check()

    def test_different_resolved_assembler_rejected_even_with_same_bytes(self):
        original = Path(self.support_tools["as"]["path"]).read_bytes()
        alternate = self.file("prefix/alternate/as", original)
        self.resolved_tools["as"] = alternate["path"]
        with self.assertRaisesRegex(ContractError, "support programs changed: as"):
            self.check()

    def test_foreign_support_program_rejected(self):
        alternate = self.file("foreign/as", b"wrong toolchain assembler")
        self.resolved_tools["as"] = alternate["path"]
        with self.assertRaisesRegex(ContractError, "outside the current prefix"):
            self.check()

    def test_missing_libgcc_identity_rejected(self):
        del self.receipt["runtime_link_inputs"]["libgcc.a"]
        with self.assertRaisesRegex(ContractError, "Complete runtime crt0/libgcc"):
            self.check()

    def test_replaced_libgcc_invalidates_unchanged_driver(self):
        Path(self.link_inputs["libgcc.a"]["path"]).write_bytes(b"new ABI epoch")
        with self.assertRaisesRegex(ContractError, r"Runtime link inputs changed: libgcc\.a"):
            self.check()

    def test_replaced_startup_invalidates_receipt(self):
        Path(self.link_inputs["crt0.o"]["path"]).write_bytes(b"new startup")
        with self.assertRaisesRegex(ContractError, r"Runtime link inputs changed: crt0\.o"):
            self.check()

    def test_new_optional_compiler_library_invalidates_receipt(self):
        library = self.file("prefix/lib/libgcc_s.dll.a", b"new shared runtime importlib")
        self.resolved_libraries["libgcc_s.dll.a"] = library["path"]
        with self.assertRaisesRegex(ContractError, r"Runtime link inputs changed: libgcc_s\.dll\.a"):
            self.check()

    def test_required_libgcc_absence_is_not_optional(self):
        self.resolved_libraries["libgcc.a"] = "libgcc.a"
        with self.assertRaisesRegex(ContractError, "Runtime link input is missing"):
            self.check()


if __name__ == "__main__":
    unittest.main()
