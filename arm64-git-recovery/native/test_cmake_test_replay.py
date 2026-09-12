import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from cmake_test_replay import bracket, render, repair_cmocka_path, semantics
from sources import ContractError


class CmakeReplayControls(unittest.TestCase):
    def discovery(self, root):
        return {"kind": "ctestInfo", "version": {"major": 1}, "tests": [
            {"name": "expected failure", "command": ["unexecuted-control.exe", "argument with spaces"],
             "properties": [
                 {"name": "ENVIRONMENT", "value": ["PATH=" + str(root / "src/Release") + r";C:\Windows\System32"]},
                 {"name": "PASS_REGULAR_EXPRESSION", "value": [r"\[  PASSED  \]", "literal;semicolon"]},
                 {"name": "FAIL_REGULAR_EXPRESSION", "value": ["[Ff]ail[.!]"]},
                 {"name": "WILL_FAIL", "value": True},
                 {"name": "WORKING_DIRECTORY", "value": str(root)}]}]}

    def test_repair_changes_only_the_known_path(self):
        root = Path("native-cmocka-build").resolve()
        original = self.discovery(root)
        repaired, count = repair_cmocka_path(original, root)
        self.assertEqual(count, 1)
        self.assertEqual(repaired["tests"][0]["command"], original["tests"][0]["command"])
        self.assertEqual(repaired["tests"][0]["properties"][1:], original["tests"][0]["properties"][1:])
        self.assertIn(str(root / "src/Release"), original["tests"][0]["properties"][0]["value"][0])
        self.assertNotIn(str(root / "src/Release"), repaired["tests"][0]["properties"][0]["value"][0])
        with self.assertRaises(ContractError):
            repair_cmocka_path(repaired, root)

    def test_empty_duplicate_and_unresolved_tests_rejected(self):
        root = Path.cwd()
        for change in ("empty", "duplicate", "command"):
            record = self.discovery(root)
            if change == "empty":
                record["tests"] = []
            elif change == "duplicate":
                record["tests"] *= 2
            else:
                del record["tests"][0]["command"]
            with self.subTest(change=change), self.assertRaises(ContractError):
                render(record)

    def test_brackets_preserve_delimiters_without_expansion(self):
        self.assertTrue(bracket("]]$ENV{PATH}").startswith("[=[\n"))
        self.assertTrue(bracket("suffix]").startswith("[=[\n"))
        self.assertTrue(bracket("]]=]suffix]=").startswith("[==[\n"))
        with self.assertRaises(ContractError):
            bracket("\0")

    @unittest.skipUnless(os.environ.get("NATIVE_TEST_CTEST"), "Existing native CTest is required")
    def test_real_ctest_metadata_roundtrip_does_not_run_the_command(self):
        with tempfile.TemporaryDirectory(prefix="cmake-replay-metadata-") as directory:
            root = Path(directory)
            record = self.discovery(root)
            record["tests"][0]["command"] = [Path(os.environ["NATIVE_TEST_CTEST"]).as_posix(), "--version"]
            (root / "CTestTestfile.cmake").write_text(render(record), encoding="utf-8", newline="\n")
            result = subprocess.run([os.environ["NATIVE_TEST_CTEST"], "--test-dir", str(root),
                                     "--show-only=json-v1"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(semantics(json.loads(result.stdout)), semantics(record))


if __name__ == "__main__":
    unittest.main()
