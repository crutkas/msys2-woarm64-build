import ctypes as C
from ctypes import wintypes
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
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

    def test_parent_binding_survives_parent_retirement(self):
        identities = {(7, 100), (7, 300), (9, 200)}
        self.assertEqual(JOB.bind_parent_generation(7, 250, identities), (7, 100))
        self.assertEqual(JOB.bind_parent_generation(7, 400, identities), (7, 300))

    def test_win32_image_error_uses_native_path_without_losing_error(self):
        calls = []

        def image_name(_handle, flags, buffer, size):
            calls.append(flags)
            if flags == 0:
                C.set_last_error(31)
                return False
            buffer.value = r"\Device\HarddiskVolume3\target\child.exe"
            size._obj.value = len(buffer.value)
            return True

        result = JOB.query_process_image(image_name, 1)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(result["kind"], "native")
        self.assertEqual(result["errors"], [{"kind": "win32", "error": 31}])

    def test_unresolved_image_retains_both_query_errors(self):
        def image_name(_handle, flags, _buffer, _size):
            C.set_last_error(31 + flags)
            return False

        result = JOB.query_process_image(image_name, 1)
        self.assertIsNone(result["path"])
        self.assertEqual(result["errors"],
                         [{"kind": "win32", "error": 31}, {"kind": "native", "error": 32}])

    def test_native_device_path_is_classified_against_same_volume(self):
        image = {"kind": "native", "path": r"\Device\HarddiskVolume3\target\bin\child.exe"}
        self.assertEqual(
            JOB.classify_image(image, r"C:\target", r"\Device\HarddiskVolume3\target"),
            "target")
        self.assertEqual(
            JOB.classify_image(image, r"C:\other", r"\Device\HarddiskVolume3\other"),
            "outside-target")

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

    def test_exact_expected_probe_relay_is_retained_and_classified(self):
        records = [
            {"pid": 1, "created": 10, "executable": r"C:\owned\probe.exe", "raw_exit": 8,
             "parent_pid": None, "parent_created": None},
            {"pid": 2, "created": 20, "executable": r"C:\owned\probe.exe", "raw_exit": 42 << 8,
             "parent_pid": 1, "parent_created": 10},
        ]
        contracts = {
            "fixture": {
                "probe_source_sha256": "a" * 64, "image_name": "probe.exe",
                "raw_exit": 42 << 8, "portable_exit": 42, "parent_raw_exit": 8,
            }
        }
        relayed = {
            (2, 20): [{
                "expected_exit_contract": "fixture", "probe_source_sha256": "a" * 64,
                "expected_raw_exit": 42 << 8, "portable_exit": 42,
            }]
        }
        protected = JOB.expected_probe_exits(records, relayed, contracts)
        self.assertEqual(protected[0]["raw_exit"], 42 << 8)
        self.assertEqual(protected[0]["portable_exit"], 42)
        self.assertFalse(JOB.unprotected_native_exits(records, relayed, contracts))

    def test_same_image_high_exit_without_expected_probe_relay_is_rejected(self):
        base = {"pid": 1, "created": 10, "executable": r"C:\owned\probe.exe", "raw_exit": 0,
                "parent_pid": None, "parent_created": None}
        children = [
            {"pid": 2, "created": 20, "executable": r"C:\owned\probe.exe", "raw_exit": 42 << 8,
             "parent_pid": 1, "parent_created": 10},
            {"pid": 3, "created": 30, "executable": r"C:\owned\probe.exe", "raw_exit": 256,
             "parent_pid": 1, "parent_created": 10},
        ]
        for child in children:
            with self.subTest(child=child):
                self.assertFalse(JOB.expected_probe_exits([base, child], {}, {}))
                self.assertEqual(JOB.unprotected_native_exits([base, child], {}), [child])

    def test_expected_probe_rejects_wrong_source_parent_image_and_ntstatus(self):
        contract = {
            "fixture": {
                "probe_source_sha256": "a" * 64, "image_name": "probe.exe",
                "raw_exit": 42 << 8, "portable_exit": 42, "parent_raw_exit": 8,
            }
        }
        base = {"pid": 1, "created": 10, "executable": r"C:\owned\probe.exe", "raw_exit": 8,
                "parent_pid": None, "parent_created": None}
        child = {"pid": 2, "created": 20, "executable": r"C:\owned\probe.exe", "raw_exit": 42 << 8,
                 "parent_pid": 1, "parent_created": 10}
        candidates = [
            {"expected_exit_contract": "fixture", "probe_source_sha256": "b" * 64,
             "expected_raw_exit": 42 << 8, "portable_exit": 42},
            {"expected_exit_contract": "fixture", "probe_source_sha256": "a" * 64,
             "expected_raw_exit": 42 << 8, "portable_exit": 42},
        ]
        variants = [
            ([base, child], {(2, 20): [candidates[0]]}),
            ([base, {**child, "executable": r"C:\owned\other.exe"}], {(2, 20): [candidates[1]]}),
            ([base, {**child, "raw_exit": 0xC0000409}], {(2, 20): [candidates[1]]}),
        ]
        for records, relayed in variants:
            with self.subTest(records=records):
                self.assertFalse(JOB.expected_probe_exits(records, relayed, contract))
                self.assertEqual(len(JOB.unprotected_native_exits(records, relayed, contract)), 1)


@unittest.skipUnless(os.name == "nt", "Windows process-job controls")
class ProcessObserverControls(unittest.TestCase):
    def execute(self, code, target_root=None, timeout=30):
        with tempfile.TemporaryDirectory(prefix="native-observer-control-") as root:
            relay = Path(root) / "relay"
            relay.mkdir()
            result = JOB.run(
                [sys.executable, "-c", code],
                root,
                target_root or Path(sys.executable).parent,
                relay,
                Path(root) / "observed.log",
                timeout,
            )
        return result

    def test_success(self):
        result = self.execute("print('observer control')")
        self.assertTrue(result["passed"])
        self.assertTrue(result["observation_count_matches"])

    def test_failure_is_not_inferred_as_success(self):
        result = self.execute("raise SystemExit(7)")
        self.assertFalse(result["passed"])
        self.assertEqual(result["parent_raw_exit"], 7)

    def test_short_lived_process_generations_are_observed_losslessly(self):
        code = (
            "import subprocess,sys; "
            "[subprocess.run([sys.executable,'-c','pass'],check=True) for _ in range(300)]"
        )
        result = self.execute(code, timeout=120)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["created_processes"], 301)
        self.assertEqual(result["observed_processes"], 301)
        self.assertFalse(result["unresolved_processes"])

    def test_same_image_raw_high_exits_are_not_accepted_without_contract(self):
        for code in (256, 10752):
            with self.subTest(code=code):
                result = self.execute(
                    "import os,subprocess,sys; "
                    f"subprocess.run([sys.executable,'-c','import os; os._exit({code})']);"
                )
                self.assertFalse(result["passed"])
                self.assertEqual([row["raw_exit"] for row in result["unrelayed_high_exits"]], [code])


if __name__ == "__main__":
    unittest.main()
