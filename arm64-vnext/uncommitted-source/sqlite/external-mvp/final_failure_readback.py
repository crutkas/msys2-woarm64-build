"""Read-only final-input and extracted-file audit after a failed committed verifier."""

import importlib.util
import json
from pathlib import Path
import sys

BASE = Path(r"C:\ag-mvp-independent-sqlite-20260911")
spec = importlib.util.spec_from_file_location("replay", BASE / "final_zip_replay.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
work = BASE / "final-901256b-01"
prepared = json.loads((work / "prepare.json").read_text())
tools, artifact, _ = replay.tools(work)
import verify_handoff

report = {"schema": 1, "passed": False, "scope": "Input immutability and independent extracted-file readback only; committed final verifier remains failed"}
report["inputs"] = {}
for label, row in prepared["files"].items():
    replay.sealed(row["original"], row["sha256"])
    replay.sealed(row["copy"], row["sha256"])
    report["inputs"][label] = {**row, "original_unchanged": True, "copy_unchanged": True}
receipt = json.loads(Path(prepared["files"]["receipt"]["copy"]).read_text())
expected = verify_handoff.read_archive(Path(prepared["files"]["archive"]["copy"]), receipt)
extracted = work / "final ZIP verification/fresh moved Git Bash extraction"
actual = artifact.inventory(extracted)
if actual != expected:
    raise ValueError("Extracted bytes differ after failed verifier")
recreated = work / "final ZIP verification/recreated.zip"
replay.sealed(recreated, receipt["sha256"])
report["extraction_matches_manifest"] = True
report["file_count"] = len(actual)
report["aa64_pe_count"] = sum(row["machine"] == "0xAA64" for row in actual.values())
report["recreated_zip"] = {"path": str(recreated), "size": recreated.stat().st_size, "sha256": replay.sha(recreated)}
report["source_unchanged"] = replay.inventory(work / "source") == prepared["source_files"]
report["fixture_unchanged"] = replay.inventory(work / "ssh-fixture-driver") == prepared["fixture_files"]
report["original_fixture_unchanged"] = replay.inventory(replay.FIXTURE) == prepared["fixture_files"]
report["committed_verifier_result"] = {
    "path": str(work / "final ZIP verification/result.json"),
    "sha256": replay.sha(work / "final ZIP verification/result.json"),
    "passed": False,
}
report["controller_result"] = {
    "path": str(work / "result.json"), "sha256": replay.sha(work / "result.json"), "passed": False}
report["passed"] = report["source_unchanged"] and report["fixture_unchanged"] and report["original_fixture_unchanged"]
report["ephemeral_private_key_absent"] = not (work / "final ZIP verification/ssh/client-key").exists()
destination = work / "failure-input-readback.json"
replay.write(destination, report)
print(json.dumps({"input_readback_passed": report["passed"], "result": str(destination), "sha256": replay.sha(destination),
                  "verifier_result_sha256": report["committed_verifier_result"]["sha256"],
                  "controller_result_sha256": report["controller_result"]["sha256"]}))
