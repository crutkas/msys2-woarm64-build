import json
from collections import Counter
from pathlib import Path
import unittest

from inventory import ROOT, digest


def read(path):
    return json.loads(Path(path).read_text())


class FailureAnalysisTests(unittest.TestCase):
    def test_original_counts_and_hashes_are_unchanged(self):
        inventory = read(ROOT / "inventory.json")
        self.assertEqual(inventory["counts"], {"PASS": 48, "FAIL": 41, "SKIP": 23, "ERROR": 4})
        for path, sha in inventory["locks"].items():
            self.assertEqual(digest(path), sha)
        for row in inventory["copies"]:
            self.assertEqual(digest(row["source"]), row["before"])
            self.assertEqual(digest(row["copy"]), row["copied"])

    def test_every_failure_has_exactly_one_primary_bucket(self):
        causes = read(ROOT / "causes.json")
        tests = [row["test"] for row in causes["tests"]]
        self.assertEqual(len(tests), 45)
        self.assertEqual(len(set(tests)), 45)
        self.assertEqual(Counter(row["original_status"] for row in causes["tests"]), {"FAIL": 41, "ERROR": 4})
        self.assertEqual(sum(row["counts"].get("FAIL", 0) for row in causes["groups"]), 41)
        self.assertEqual(sum(row["counts"].get("ERROR", 0) for row in causes["groups"]), 4)
        self.assertEqual(len(causes["unconfirmed_secondary_causes"]), 2)

    def test_exact_upstream_scripts_are_not_edited(self):
        for path in (ROOT / "runs").glob("*/result.json"):
            result = read(path)
            if result["test"]:
                self.assertTrue(result["same_test_source"])
                self.assertEqual(digest(ROOT / "source" / result["test"]), result["test_source_sha256"])
                original = Path(r"C:\ag-coreutils-e138-01\coreutils-native-13\source\coreutils-8.32") / result["test"]
                self.assertEqual(digest(original), result["test_source_sha256"])

    def test_runtime_version_is_not_confounded_with_parent_coherence(self):
        for name in ("dir-nonrecur", "wc-proc", "pwd-option"):
            result = read(ROOT / "runs" / f"historical-native-{name}-01/result.json")
            self.assertEqual(result["semantic_test_shell_raw_exit"], 0)
            self.assertFalse(result["native_job"]["timed_out"])
            self.assertFalse(result["observer_gate_passed"])

    def test_acl_differential_does_not_hide_residual_failures(self):
        rows = read(ROOT / "acl-batch-current-acl.json")
        self.assertEqual(Counter(row["test_shell_raw_exit"] for row in rows), {0: 6, 1: 7})
        text = (ROOT / "runs/api-boundary-current-acl/target.log").read_text()
        self.assertIn("parent-mode=500", text)
        self.assertIn("access-parent-W_OK result=-1 errno=13", text)
        self.assertIn("unlinkat-child result=0 errno=0", text)
        self.assertIn("chdir-unsearchable-parent result=-1 errno=13", text)
        self.assertIn("open-through-unsearchable-parent result=3 errno=0", text)

    def test_byte_replays_preserve_genuine_exit_failures(self):
        for cohort in ("current-noacl", "historical-noacl"):
            text = (ROOT / "runs" / f"exact-byte-subcases-{cohort}/target.log").read_text()
            self.assertIn("date: invalid date '\\260'", text)
            self.assertIn("date: invalid date '\\357\\202\\260'", text)
            self.assertIn("join_exit=0", text)
            self.assertIn("join_exit=1", text)
            self.assertIn("seq_exit=1", text)

    def test_setup_error_has_real_absent_target_api(self):
        text = (ROOT / "runs/api-boundary-current-acl/target.log").read_text()
        self.assertIn("RTLD_NEXT=absent", text)
        original = (ROOT / "retained/logs/tests/rm/rm-readdir-fail.log").read_text()
        self.assertIn("'RTLD_NEXT' undeclared", original)
        self.assertIn("exit status: 99", original)

    def test_timeouts_remain_failed_and_observation_gaps_visible(self):
        for label in ("upstream-tests-misc-help-version-current-noacl",
                      "complete-help-version-02"):
            result = read(ROOT / "runs" / label / "result.json")
            self.assertTrue(result["native_job"]["timed_out"])
            self.assertEqual(result["semantic_test_shell_raw_exit"], 1460)
            self.assertFalse(result["observer_gate_passed"])
            self.assertLess(result["native_job"]["observed_processes"], result["native_job"]["created_processes"])
        for path in (ROOT / "runs").glob("*/result.json"):
            result = read(path)
            if result["native_job"]["timed_out"]:
                continue
            self.assertFalse(result["outer"]["timed_out"])
            self.assertEqual(result["outer"]["active_at_boundary"], 0)

    def test_real_support_file_repair_does_not_claim_full_help_pass(self):
        bad = (ROOT / "runs/focused-stdbuf-layout-current-noacl/target.log").read_text()
        good = (ROOT / "runs/focused-stdbuf-canonical-layout-01/target.log").read_text()
        self.assertIn("stdbuf_exit=125", bad)
        self.assertIn("stdbuf_exit=0", good)
        full = read(ROOT / "runs/complete-help-version-02/result.json")
        self.assertTrue(full["native_job"]["timed_out"])


if __name__ == "__main__":
    unittest.main()
