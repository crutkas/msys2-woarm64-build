import importlib.util
from pathlib import Path
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("compiler_copy", Path(__file__).with_name("copy-toolchain-input.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompilerCopyControls(unittest.TestCase):
    def test_cc1_only_delta_rejects_runtime_changes_and_extra_files(self):
        before = {"cc1.exe": "old", "msys-2.0.dll": "runtime"}
        after = {"cc1.exe": "new", "msys-2.0.dll": "runtime"}
        module.verify_cohort_delta(before, after, {"cc1.exe"}, set())
        for invalid in ({**after, "msys-2.0.dll": "changed"}, {**after, "unexpected.dll": "new"},
                        {"cc1.exe": "new"}):
            with self.assertRaises(ContractError):
                module.verify_cohort_delta(before, invalid, {"cc1.exe"}, set())

    def test_guard_inventory_count_and_case_aliases_are_rejected(self):
        handoff = {"schema": 1, "status": "qualified-native-msys-stack-guard-c-compiler-delta",
                   "prefix": str(Path("unexecuted").resolve()),
                   "files": {"bin/compiler.exe": {"sha256": "1" * 64}}, "file_count": 1}
        source, status, expected = module.published_input(handoff)
        self.assertEqual(source, Path(handoff["prefix"]))
        self.assertEqual(status, handoff["status"])
        self.assertEqual(expected, {"bin/compiler.exe": "1" * 64})
        handoff["file_count"] = 2
        with self.assertRaises(ContractError):
            module.published_input(handoff)
        handoff["files"]["BIN/COMPILER.EXE"] = {"sha256": "2" * 64}
        with self.assertRaises(ContractError):
            module.published_input(handoff)

    def test_guard_intake_cannot_infer_its_predecessor(self):
        with self.assertRaises(ContractError):
            module.guard_base({}, Path("unexecuted"), {}, None)


if __name__ == "__main__":
    unittest.main()
