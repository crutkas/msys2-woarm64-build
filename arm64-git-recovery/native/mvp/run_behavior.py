"""Exercise the native extraction through a minimal Windows parent; preserve raw status and evidence."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bounded_process import run
from artifact import ArtifactError, inventory, pe_identity, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--https-repository", default="https://github.com/octocat/Hello-World.git")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Fresh behavior evidence path required")
    before = inventory(root)
    for name in ("usr/bin/bash.exe", "usr/bin/msys-2.0.dll", "mingwarm64/bin/git.exe"):
        if before.get(name, {}).get("machine") != "0xAA64":
            raise ArtifactError(f"Required native entrypoint absent: {name}")
    output.mkdir(parents=True)
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA") if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (root / "mingwarm64/bin", root / "usr/bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                "TMP": str(output), "TEMP": str(output), "MSYSTEM": "MINGWARM64", "MSYS": "winsymlinks:sys"})
    script = Path(__file__).with_name("behavior.sh")
    command = [root / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               (output / "work").as_posix(), args.https_repository]
    report = {"schema": 1, "passed": False, "root": str(root), "command": list(map(str, command)),
              "runtime_sha256": before["usr/bin/msys-2.0.dll"]["sha256"],
              "script_sha256": sha256(script),
              "scope": "Real local/network functional cases; parent raw status and bounded cleanup; all-child architecture/exit attestation is a separate required gate"}
    try:
        with (output / "run.log").open("xb") as log:
            report["process"] = run(command, cwd=output, env=env, log=log, timeout=600)
        cases = output / "work/cases.tsv"
        report["cases"] = [line.split("\t", 2) for line in cases.read_text().splitlines()] if cases.is_file() else []
        report["inputs_unchanged"] = inventory(root) == before
        report["passed"] = (report["process"]["passed"] and report["inputs_unchanged"]
                            and len(report["cases"]) == 12
                            and all(len(row) >= 2 and row[1] == "PASS" for row in report["cases"]))
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"passed": report["passed"], "case_count": len(report.get("cases", [])),
                      "raw_exit": report.get("process", {}).get("exit")}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
