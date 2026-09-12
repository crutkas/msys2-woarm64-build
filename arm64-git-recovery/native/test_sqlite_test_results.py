from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sqlite_test_results import runner_summary, shell5_summary


class RunnerSummaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def database(self, rows):
        with closing(sqlite3.connect(self.root / "testrunner.db")) as db:
            db.execute("CREATE TABLE jobs(state,ntest,nerr,displayname,output)")
            db.executemany("INSERT INTO jobs VALUES(?,?,?,?,?)", rows)
            db.commit()

    def test_missing_database_is_a_gate(self):
        result = runner_summary(self.root)
        self.assertFalse(result["available"])
        self.assertFalse(result["passed"])

    def test_all_completed_successes(self):
        self.database([("done", 7, 0, "first", ""), ("done", 3, 0, "second", "")])
        result = runner_summary(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(result["tests"], 10)
        self.assertEqual(result["jobs"], 2)

    def test_pending_halted_or_omitted_jobs_do_not_pass(self):
        for state in ("ready", "running", "halt", "omit", ""):
            with self.subTest(state=state):
                (self.root / "testrunner.db").unlink(missing_ok=True)
                self.database([("done", 7, 0, "completed", ""), (state, None, None, "unfinished", None)])
                result = runner_summary(self.root)
                self.assertFalse(result["passed"])
                self.assertEqual(result["tests"], 7)

    def test_crash_without_counted_assertion_still_fails(self):
        self.database([("failed", 0, 0, "crashed", "actual raw failure")])
        result = runner_summary(self.root)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failed_jobs"][0]["output"], "actual raw failure")

    def test_error_count_cannot_be_overridden_by_done_state(self):
        self.database([("done", 10, 1, "inconsistent", "one error")])
        self.assertFalse(runner_summary(self.root)["passed"])

    def test_full_shell5_requires_summary_regression_and_observer(self):
        summary = "0 errors out of 53 tests on MSYS"
        verbose = "shell5-1.8... Ok\n"
        self.assertTrue(shell5_summary(summary, verbose, True)["passed"])
        self.assertFalse(shell5_summary(summary, verbose, False)["passed"])
        self.assertFalse(shell5_summary(summary, "", True)["passed"])

    def test_shell5_does_not_accept_partial_ambiguous_or_failed_results(self):
        for text in ("", "0 errors out of 52 tests", "1 errors out of 53 tests",
                     "0 errors out of 53 tests\n0 errors out of 53 tests"):
            with self.subTest(text=text):
                self.assertFalse(shell5_summary(text, "shell5-1.8... Ok\n", True)["passed"])
