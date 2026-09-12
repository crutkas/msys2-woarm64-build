"""Snapshot the retained failures; never overwrite or rerun the old build tree."""

import hashlib
import json
from pathlib import Path
import re
import shutil
from collections import Counter

ROOT = Path(r"C:\ag-exit-e138-01\coreutils-failures-20260911-01")
PRODUCER = Path(r"C:\ag-coreutils-e138-01\coreutils-native-13")
BUILD = PRODUCER / "build/coreutils"
SOURCE = PRODUCER / "source/coreutils-8.32"
LOCKS = {
    str(PRODUCER / "build.log"): "3c8434c393ee9716816c938a98a127951dee307441f334c38e44e3816d8adc4a",
    str(PRODUCER / "stage-coreutils.sha256"): "ccef88dcf9d454a278c3beb0e1c8844e1cd3ff4f6b81dc54d56338b1f405b4ec",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def copy(source, destination, copies, expected=None):
    before = digest(source)
    if expected is not None and before != expected:
        raise RuntimeError(f"Input changed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    copied, after = digest(destination), digest(source)
    if copied != before or after != before:
        raise RuntimeError(f"Copy changed: {source}")
    copies.append({"source": str(source), "copy": str(destination),
                   "before": before, "copied": copied, "after": after})
    return before


def main():
    for path, sha in LOCKS.items():
        if digest(path) != sha:
            raise RuntimeError(f"Frozen receipt changed: {path}")
    ROOT.mkdir(exist_ok=False)
    copies, tests = [], []
    log = (PRODUCER / "build.log").read_text(errors="replace")
    statuses = re.findall(r"^(PASS|FAIL|SKIP|ERROR): (\S+)$", log, re.M)
    counts = dict(Counter(status for status, _ in statuses))
    if counts != {"PASS": 48, "FAIL": 41, "SKIP": 23, "ERROR": 4}:
        raise RuntimeError(f"Retained status totals differ: {counts}")
    for path, sha in LOCKS.items():
        copy(path, ROOT / "retained" / Path(path).name, copies, sha)
    for path in ("config.log", "config.status", "Makefile", "GNUmakefile", "lib/config.h"):
        source = BUILD / path
        if source.is_file():
            copy(source, ROOT / "retained/build" / path, copies)
    for path in ("tests/init.sh", "tests/Coreutils.pm", "tests/CuTmpdir.pm", "tests/local.mk",
                 "build-aux/test-driver", "tests/test-lib.sh"):
        source = SOURCE / path
        if source.is_file():
            copy(source, ROOT / "retained/source" / path, copies)
    for status, name in statuses:
        if status not in ("FAIL", "ERROR"):
            continue
        relative = Path(name)
        stem = relative.with_suffix("")
        log_path = BUILD / stem.with_suffix(".log")
        trs_path = BUILD / stem.with_suffix(".trs")
        source = SOURCE / relative
        log_sha = copy(log_path, ROOT / "retained/logs" / stem.with_suffix(".log"), copies)
        trs_sha = copy(trs_path, ROOT / "retained/logs" / stem.with_suffix(".trs"), copies)
        source_sha = copy(source, ROOT / "retained/source" / relative, copies)
        lines = log_path.read_text(errors="replace").splitlines()
        source_lines = source.read_text(errors="replace").splitlines()
        tests.append({"status": status, "test": name, "log": str(ROOT / "retained/logs" / stem.with_suffix(".log")),
                      "log_sha256": log_sha, "source": str(ROOT / "retained/source" / relative),
                      "source_sha256": source_sha, "trs_sha256": trs_sha, "log_lines": len(lines),
                      "tail": [{"line": index + 1, "text": line}
                               for index, line in list(enumerate(lines))[-140:]],
                      "source_lines": len(source_lines), "cause": "UNCLASSIFIED"})
    write(ROOT / "inventory.json", {"schema": 1, "counts": counts, "completed_tests": len(statuses),
          "full_suite_completed": False, "tests": tests, "copies": copies, "locks": LOCKS,
          "source_stage_unchanged": True})
    write(ROOT / "log-tails.json", {row["test"]: row["tail"] for row in tests})
    print(json.dumps({"counts": counts, "failures_and_errors": len(tests), "root": str(ROOT)}))


if __name__ == "__main__":
    main()
