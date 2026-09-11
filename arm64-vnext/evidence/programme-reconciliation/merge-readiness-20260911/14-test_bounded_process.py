import os
from pathlib import Path
import sys
import tempfile
import unittest

from bounded_process import run


@unittest.skipUnless(os.name == "nt", "Windows process-job controls")
class BoundedProcessControls(unittest.TestCase):
    def execute(self, code, timeout=10):
        with tempfile.TemporaryDirectory(prefix="native-job-control-") as root:
            with (Path(root) / "output.log").open("xb") as log:
                return run([sys.executable, "-c", code], cwd=root, env=dict(os.environ),
                           log=log, timeout=timeout)

    def test_success(self):
        self.assertTrue(self.execute("print('native-job-control')")["passed"])

    def test_failure(self):
        result = self.execute("raise SystemExit(7)")
        self.assertFalse(result["passed"])
        self.assertEqual(result["exit"], 7)

    def test_timeout_kills_owned_tree(self):
        result = self.execute(
            "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)",
            timeout=2)
        self.assertTrue(result["timed_out"])
        self.assertGreaterEqual(result["created_processes"], 2)

    def test_orphan_is_not_success(self):
        result = self.execute(
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])")
        self.assertFalse(result["passed"])
        self.assertGreaterEqual(result["active_at_boundary"], 1)

    def test_short_lived_child_can_finish_cleanup(self):
        result = self.execute(
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.1)'])")
        self.assertTrue(result["passed"])
        self.assertEqual(result["active_at_boundary"], 0)

    def test_started_callback_runs_for_owned_process(self):
        seen = []
        with tempfile.TemporaryDirectory(prefix="native-job-callback-") as root:
            with (Path(root) / "output.log").open("xb") as log:
                result = run([sys.executable, "-c", "print('callback fixture')"], cwd=root,
                             env=dict(os.environ), log=log, timeout=10, on_started=seen.append)
        self.assertEqual(seen, [result["pid"]])
        self.assertTrue(result["passed"])

    def test_callback_failure_terminates_owned_process_before_return(self):
        def fail(_):
            raise ValueError("fixture callback failure")

        with tempfile.TemporaryDirectory(prefix="native-job-failed-callback-") as root:
            with (Path(root) / "output.log").open("xb") as log:
                with self.assertRaisesRegex(ValueError, "fixture callback failure"):
                    run([sys.executable, "-c", "import time; time.sleep(30)"], cwd=root,
                        env=dict(os.environ), log=log, timeout=10, on_started=fail)


if __name__ == "__main__":
    unittest.main()
