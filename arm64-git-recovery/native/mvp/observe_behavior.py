"""Run the real MVP cases under the published raw-preserving native process observer."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from artifact import ArtifactError, bound_json, inventory, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observer-source", type=Path, required=True)
    parser.add_argument("--observer-handoff", type=Path, required=True)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--https-repository", default="https://github.com/octocat/Hello-World.git")
    args = parser.parse_args()
    root, output, driver = args.root.resolve(), args.output.resolve(), args.observer_source.resolve()
    if output.exists():
        raise ArtifactError("Fresh observed replay root is required")
    handoff = bound_json({"path": str(args.observer_handoff), "sha256": args.handoff_sha256})
    if handoff.get("status") != "native-exit-observer-contract-qualified-and-published-for-review":
        raise ArtifactError("An explicit qualified observer handoff is required")
    helper_record = handoff["fixtures"]["helper_binary"]
    helper_source = handoff["fixtures"]["helper_source"]
    if sha256(helper_record["path"]) != helper_record["sha256"] or sha256(driver / "msys-exit-contract.c") != helper_source["sha256"]:
        raise ArtifactError("The exact qualified native helper source/binary changed")
    before = inventory(root)
    output.mkdir(parents=True)
    view = output / "extraction"
    shutil.copytree(root, view)
    if inventory(view) != before:
        raise ArtifactError("Independent replay copy differs")
    helper = view / "usr/bin/msys-exit-contract.exe"
    if helper.exists():
        raise ArtifactError("The source payload must not contain the validation-only helper")
    shutil.copyfile(helper_record["path"], helper)
    relays = output / "relays"
    relays.mkdir()
    contracts = output / "expected-exit-contracts.json"
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA") if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (view / "mingwarm64/bin", view / "usr/bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                "TMP": str(output), "TEMP": str(output), "MSYSTEM": "MINGWARM64",
                "WOARM64_NATIVE_EXIT_DIR": str(relays), "WOARM64_EXIT_CONTRACT_SOURCE_SHA256": helper_source["sha256"],
                "MVP_EXPECTED_EXIT_HELPER": "/usr/bin/msys-exit-contract.exe"})
    generation = [sys.executable, "-I", "-B", str(driver / "write-msys-exit-contracts.py"),
                  "--source", str(driver / "msys-exit-contract.c"), "--helper", str(helper),
                  "--bash", str(view / "usr/bin/bash.exe"), "--env", str(view / "usr/bin/env.exe"),
                  "--output", str(contracts)]
    subprocess.run(generation, env=env, check=True, capture_output=True, timeout=30)
    script = Path(__file__).with_name("behavior.sh")
    result_path = output / "native-job.json"
    command = [sys.executable, "-I", "-B", str(driver / "native-job.py"), "--cwd", str(output),
               "--target-root", str(view), "--relay-records", str(relays),
               "--log", str(output / "run.log"), "--result", str(result_path), "--timeout", "600",
               "--expected-exit-contracts", str(contracts), "--", str(view / "usr/bin/bash.exe"),
               "--noprofile", "--norc", script.as_posix(), (output / "work").as_posix(), args.https_repository]
    report = {"schema": 1, "passed": False, "classification": "NON-ADMITTED EXPERIMENTAL DIAGNOSTIC PROJECTION",
              "source_manifest": {name: row["sha256"] for name, row in before.items()},
              "observer_handoff_sha256": args.handoff_sha256,
              "helper_sha256": helper_record["sha256"], "helper_source_sha256": helper_source["sha256"],
              "observer_sha256": sha256(driver / "native-job.py"), "contracts_sha256": sha256(contracts),
              "script_sha256": sha256(script),
              "scope": "Actual complete job-generation accounting and target ProcessMachineTypeInfo plus explicit expected-negative contracts. Raw Windows exits retained; no loaded-module completeness claim."}
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=660)
        (output / "observer.stdout").write_bytes(result.stdout)
        (output / "observer.stderr").write_bytes(result.stderr)
        if not result_path.is_file():
            raise ArtifactError("Native observer produced no durable result")
        observer = json.loads(result_path.read_text())
        report["observer_exit"] = result.returncode
        report["observer_result_sha256"] = sha256(result_path)
        report["observer_passed"] = observer["passed"]
        cases_path = output / "work/cases.tsv"
        report["cases"] = [line.split("\t", 2) for line in cases_path.read_text().splitlines()] if cases_path.is_file() else []
        after = inventory(view)
        del after["usr/bin/msys-exit-contract.exe"]
        report["inputs_unchanged"] = inventory(root) == before and after == before
        report["passed"] = result.returncode == 0 and observer["passed"] and report["inputs_unchanged"] and len(report["cases"]) == 12
        report["raw_expected_exits"] = observer.get("expected_probe_exits", [])
        report["unrelayed_high_exits"] = observer.get("unrelayed_high_exits", [])
        report["created_processes"] = observer["created_processes"]
        report["observed_processes"] = observer["observed_processes"]
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({name: report.get(name) for name in
                      ("passed", "created_processes", "observed_processes", "observer_exit", "inputs_unchanged", "unrelayed_high_exits")}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
