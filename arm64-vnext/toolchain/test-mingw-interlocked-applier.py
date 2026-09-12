#!/usr/bin/env python3
"""Exercise the frozen producer applier on owned source copies, never a prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil


def ref(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("producer", "baseline-header", "bash", "runner", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.producer / "handoff.json").read_text())
    source = manifest["upstream_source"]
    if ref(args.baseline_header)["sha256"] != source["original_sha256"]:
        raise ValueError("Expected exact pinned unpatched header")
    if ref(args.runner)["sha256"] != args.runner_sha256:
        raise ValueError("Bounded runner changed")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    scripts = out / "scripts"
    scripts.mkdir()
    inputs = []
    for entry in manifest["maintained_files"]:
        path = args.producer / entry["path"]
        if ref(path)["sha256"] != entry["sha256"]:
            raise ValueError("Frozen producer input changed")
        inputs.append(ref(path))
    original = args.producer / ".github/scripts/apply-mingw-w64-arm64-interlocked-exchange-ordering.sh"
    script = scripts / original.name
    script.write_bytes(original.read_bytes().replace(b"\r\n", b"\n"))
    shutil.copy2(args.producer / ".github/scripts/mingw-w64-arm64-interlocked-exchange-ordering.patch", scripts)
    tree = out / "source"
    header = tree / source["file"]
    header.parent.mkdir(parents=True)
    shutil.copy2(args.baseline_header, header)
    bounded = runpy.run_path(str(args.runner))["run"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(args.bash.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TMP=str(out), TEMP=str(out), CHERE_INVOKING="1")
    command = [str(args.bash), "--noprofile", "--norc", script.as_posix(), str(tree)]
    record = {"schema": 1, "status": "failed", "runs": [], "inputs": inputs,
              "scriptOriginal": ref(original), "scriptNormalizedLF": ref(script),
              "bootstrapDriver": ref(args.bash),
              "scope": "Unmodified producer applier logic with CRLF-to-LF script normalization; MSYS shell is a bootstrap driver, not a new native tool claim."}
    try:
        for case in ("apply", "idempotent", "unknown-drift"):
            if case == "unknown-drift":
                header.write_bytes(header.read_bytes() + b"\n/* owned rejection control */\n")
            before = ref(header)["sha256"]
            with (out / (case + ".log")).open("xb") as log:
                result = bounded(command, cwd=out, env=env, log=log, timeout=45)
            after = ref(header)["sha256"]
            record["runs"].append({"name": case, "command": command, "result": result,
                                   "before": before, "after": after})
            if result["timed_out"] or result["active_at_boundary"]:
                raise ValueError("Applier did not drain")
            if case == "unknown-drift":
                if result["exit"] != 3 or before != after:
                    raise ValueError("Unknown source was not rejected and preserved")
            elif result["exit"] != 0 or after != source["patched_sha256"]:
                raise ValueError("Exact producer applier failed")
            if case == "idempotent" and before != after:
                raise ValueError("Repeated application changed the header")
        for entry in inputs:
            if ref(Path(entry["path"])) != entry:
                raise ValueError("Frozen producer input changed")
        record["status"] = "frozen-interlocked-applier-controls-qualified"
    finally:
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
