from ctypes import wintypes
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "native-job.py"
SPEC = importlib.util.spec_from_file_location("native_job", SCRIPT)
JOB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JOB)


class ProcessIdentityTests(unittest.TestCase):
    def test_same_pid_with_different_creation_time_is_distinct(self):
        first = wintypes.FILETIME(10, 20)
        second = wintypes.FILETIME(11, 20)
        self.assertNotEqual(JOB.process_identity(42, first), JOB.process_identity(42, second))

    def test_native_classification_does_not_leak_to_reused_host_pid(self):
        first, second = (42, 100), (42, 200)
        native = {first: r"C:\owned\target.exe"}
        recorded = set()
        record = JOB.retire_process(native, recorded, first, 0)
        self.assertEqual(record["executable"], r"C:\owned\target.exe")
        self.assertNotIn(first, native)
        self.assertIsNone(JOB.retire_process(native, recorded, second, 256))
        self.assertEqual(len(recorded), 2)

    def test_reused_native_pid_retains_its_own_path_and_raw_exit(self):
        first, second = (42, 100), (42, 200)
        native = {first: r"C:\owned\first.exe", second: r"C:\owned\second.exe"}
        recorded = set()
        self.assertEqual(JOB.retire_process(native, recorded, first, 1536)["raw_exit"], 1536)
        record = JOB.retire_process(native, recorded, second, 256)
        self.assertEqual(record["created"], 200)
        self.assertEqual(record["executable"], r"C:\owned\second.exe")
        self.assertEqual(record["raw_exit"], 256)
        self.assertEqual(len(recorded), 2)
        self.assertFalse(native)

    def test_exact_wrapper_propagation_is_covered_by_real_relay(self):
        records = [
            {"pid": 1, "created": 10, "executable": "wrapper.exe", "raw_exit": 1536},
            {"pid": 2, "created": 20, "executable": "target.exe", "raw_exit": 1536,
             "parent_pid": 1, "parent_created": 10},
        ]
        relay = {(1, 10): [{"executable": "wrapper.exe", "raw_exit": 1536, "portable_exit": 255}]}
        self.assertFalse(JOB.unprotected_native_exits(records, relay))

    def test_a_different_child_failure_or_parent_generation_is_not_waived(self):
        for parent_time, code in ((9, 1536), (10, 256)):
            records = [
                {"pid": 1, "created": 10, "executable": "wrapper.exe", "raw_exit": 1536},
                {"pid": 2, "created": 20, "executable": "target.exe", "raw_exit": code,
                 "parent_pid": 1, "parent_created": parent_time},
            ]
            relay = {(1, 10): [{"executable": "wrapper.exe", "raw_exit": 1536, "portable_exit": 255}]}
            self.assertEqual(len(JOB.unprotected_native_exits(records, relay)), 1)

    def test_successful_parent_cannot_hide_a_high_child_exit(self):
        records = [
            {"pid": 1, "created": 10, "executable": "wrapper.exe", "raw_exit": 0},
            {"pid": 2, "created": 20, "executable": "target.exe", "raw_exit": 1536,
             "parent_pid": 1, "parent_created": 10},
        ]
        self.assertEqual(len(JOB.unprotected_native_exits(records, {})), 1)


if __name__ == "__main__":
    unittest.main()
