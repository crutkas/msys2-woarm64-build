"""Copy the pipeline-owned, hash-qualified native job/exit driver without mutating its source."""

import argparse
import json
from pathlib import Path
import shutil

from native_job_runner import require_current_observer
from sources import ContractError, digest, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or digest(args.handoff) != args.sha256:
        raise ContractError("A fresh driver copy and exact published handoff hash are required")
    record = json.loads(args.handoff.read_text())
    if record.get("Status") != "native-target-relay-and-job-level-fail-closed-package-controls-passed":
        raise ContractError("Unknown native exit-observer qualification")
    selected = {"native-target-exec.py", "native-target-exec.sh", "native-job.py"}
    sources = {Path(row["Path"]).name: row for row in record["Sources"]
               if Path(row["Path"]).name in selected}
    if sources.keys() != selected:
        raise ContractError("Incomplete native job/relay driver input")
    require_current_observer(sources["native-job.py"]["SHA256"])
    for row in [*sources.values(), *record["Evidence"]]:
        if digest(row["Path"]) != row["SHA256"]:
            raise ContractError("Native exit-observer source or control evidence changed")
    args.output.mkdir(parents=True)
    for name, row in sources.items():
        shutil.copyfile(row["Path"], args.output / name)
        if digest(args.output / name) != row["SHA256"] or digest(row["Path"]) != row["SHA256"]:
            raise ContractError("Native exit-observer changed during copy")
    receipt = {"schema": 1, "status": "byte-identical-native-test-driver",
               "source_handoff_sha256": args.sha256, "files": inventory(args.output),
               "scope": record["JobScope"], "mapping": record["Mapping"]}
    args.output.with_name(args.output.name + ".manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Qualified native target/job observer copied without source changes")


if __name__ == "__main__":
    main()
