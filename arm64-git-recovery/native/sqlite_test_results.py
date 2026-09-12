"""Read the upstream runner's actual database without changing its results."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3


def runner_summary(directory):
    database = Path(directory) / "testrunner.db"
    if not database.is_file():
        return {"available": False, "passed": False, "reason": "Upstream runner database was not created"}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        states = dict(db.execute("SELECT state,count(*) FROM jobs GROUP BY state"))
        tests, errors = db.execute(
            "SELECT coalesce(sum(ntest),0),coalesce(sum(nerr),0) FROM jobs").fetchone()
        failed = [{"name": name, "tests": count, "errors": bad, "output": text}
                  for name, count, bad, text in db.execute(
                      "SELECT displayname,ntest,nerr,output FROM jobs WHERE state='failed' ORDER BY displayname")]
    return {"available": True, "states": states, "jobs": sum(states.values()), "tests": tests, "errors": errors,
            "failed_jobs": failed,
            "passed": bool(states) and set(states) == {"done"} and errors == 0}


def shell5_summary(text, verbose, process_passed):
    counts = re.findall(r"(\d+) errors out of (\d+) tests", text)
    if len(counts) != 1:
        return {"passed": False, "reason": "Missing or ambiguous upstream shell5 summary"}
    errors, tests = map(int, counts[0])
    regression_passed = "shell5-1.8... Ok" in verbose
    return {"errors": errors, "tests": tests, "shell5_1_8_passed": regression_passed,
            "passed": process_passed and (errors, tests) == (0, 53) and regression_passed}
