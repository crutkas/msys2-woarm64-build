import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from native_job_runner import REJECTED_OBSERVERS, run_observed
from sources import ContractError, inventory


class NativeJobRunnerControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-observer-wrapper-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.driver = self.root / "driver"
        self.driver.mkdir()
        (self.driver / "native-job.py").write_bytes(b"unit fixture only")
        self.manifest = self.root / "driver.manifest.json"
        self.manifest.write_text(json.dumps({"status": "byte-identical-native-test-driver",
                                             "files": inventory(self.driver)}))

    def invoke(self, passed, outer_exit=0):
        def observer(command, **kwargs):
            result = Path(command[command.index("--result") + 1])
            result.write_text(json.dumps({"passed": passed, "parent_pid": 123,
                                          "parent_raw_exit": 0, "timed_out": False,
                                          "created_processes": 2, "observed_processes": 2}))
            return SimpleNamespace(returncode=outer_exit, stdout=b"", stderr=b"")
        with patch("native_job_runner.subprocess.run", side_effect=observer):
            return run_observed(["fixture-command"], cwd=self.root,
                                env={"WOARM64_NATIVE_TEST_ROOT": str(self.root)},
                                log_path=self.root / "output.log", result_path=self.root / "result.json",
                                relay_records=self.root / "exits", timeout=5, driver_prefix=self.driver)

    def test_parent_zero_does_not_override_observation_failure(self):
        self.assertFalse(self.invoke(False)["passed"])

    def test_observer_process_failure_cannot_claim_success(self):
        self.assertFalse(self.invoke(True, 255)["passed"])

    def test_complete_observation_passes(self):
        self.assertTrue(self.invoke(True)["passed"])

    def test_changed_driver_is_rejected_before_execution(self):
        (self.driver / "native-job.py").write_bytes(b"changed")
        with self.assertRaises(ContractError):
            self.invoke(True)

    def test_retired_pid_reuse_observer_cannot_be_reused(self):
        with patch("native_job_runner.digest", return_value=next(iter(REJECTED_OBSERVERS))):
            with self.assertRaisesRegex(ContractError, "Retired native job observer"):
                self.invoke(True)


if __name__ == "__main__":
    unittest.main()
