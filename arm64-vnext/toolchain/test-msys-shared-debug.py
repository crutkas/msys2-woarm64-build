#!/usr/bin/env python3
"""Join actual shared-C++ ordinary/debug exits without changing debugger policy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"
MARKER = b"native-msys-shared-gcc-cpp-ok\n"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shared-proof", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    inputs = load(root / "inputs.json")
    for relative, entry in inputs["files"].items():
        if sha(root / relative) != entry["sha256"]:
            raise ValueError(f"Capture input changed: {relative}")
    if sha(Path(sys.executable)) != PYTHON_SHA:
        raise ValueError("Use the source-bound native ARM64 Python")
    proof_path = args.shared_proof.resolve(strict=True)
    proof = load(proof_path)
    if proof["status"] != "native-msys-shared-gcc-runtimes-qualified":
        raise ValueError("Ordinary shared-runtime qualification is required first")
    fixture = root / "fixture"
    fixture.mkdir(exist_ok=False)
    names = ("consumer.exe", "provider.dll", "msys-2.0.dll", "msys-gcc_s-seh-1.dll", "msys-stdc++-6.dll")
    original = proof_path.parent
    files = {}
    for name in names:
        source = original / name
        shutil.copy2(source, fixture / name)
        files[name] = sha(source)
    # The ordinary receipt's mapped modules bind the same provider DLL bytes.
    loaded = {Path(row["path"]).name.lower(): row for row in proof["loaded_modules"]["cpp-shared-runtime"]}
    for name in names:
        if name not in loaded or loaded[name]["sha256"] != files[name]:
            raise ValueError(f"Ordinary proof did not bind {name}")
    sys.path.insert(0, str(root / "support"))
    try:
        bounded = runpy.run_path(str(root / "support" / "bounded_process.py"))["run"]
        noninteractive = runpy.run_path(str(root / "support" / "native_job_runner.py"))["noninteractive_error_mode"]
    finally:
        sys.path.pop(0)
    report = {"schema": 1, "status": "failed", "files": files, "cases": [],
              "ordinary_proof": {"path": str(proof_path), "sha256": sha(proof_path)},
              "capture_inputs_sha256": sha(root / "inputs.json")}
    try:
        for mode in ("ordinary", "debug", "no-context"):
            case = root / "cases" / mode
            case.mkdir(parents=True, exist_ok=False)
            command = [str(fixture / "consumer.exe"), "--hold"]
            if mode != "ordinary":
                command = [sys.executable, "-B", str(root / "debug_tree.py"), "--output", str(case / "debug"),
                           "--abi", str(root / "windows-abi.json"), "--timeout", "20",
                           *(["--no-context"] if mode == "no-context" else []), "--", *command]
            argv = [sys.executable, "-I", "-B", str(root / "driver" / "native-job.py"),
                    "--cwd", str(case), "--target-root", str(root), "--relay-records", str(case / "relay"),
                    "--log", str(case / "fixture.log"), "--result", str(case / "native-job.json"),
                    "--timeout", "40", "--", *command]
            env = {key: value for key, value in os.environ.items()
                   if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
            env.update(PATH=str(fixture) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                       HOME=str(case), USERPROFILE=str(case), TEMP=str(case), TMP=str(case))
            with noninteractive(), (case / "observer.log").open("xb") as stream:
                result = bounded(argv, cwd=case, env=env, log=stream, timeout=55)
            observer = load(case / "native-job.json")
            record = {"mode": mode, "command": argv, "outer": result, "observer": observer,
                      "observer_sha256": sha(case / "native-job.json"), "passed": False}
            report["cases"].append(record)
            if (not result["passed"] or not observer["passed"] or observer["timed_out"]
                    or not observer["observation_count_matches"] or observer["unobserved_processes"]
                    or observer["unresolved_processes"] or result["active_at_boundary"]):
                raise ValueError(f"Incomplete native process coverage: {mode}")
            exits = observer["native_target_exits"]
            if len(exits) != 1 or exits[0]["raw_exit"] != 0:
                raise ValueError(f"Unexpected actual native target exits: {mode}: {exits}")
            output = case / ("fixture.log" if mode == "ordinary" else "debug/stdout.bin")
            if output.read_bytes().replace(b"\r\n", b"\n") != MARKER:
                raise ValueError(f"Missing actual C++ semantic success: {mode}")
            if mode != "ordinary":
                debug = load(case / "debug" / "result.json")
                observed = {(row["pid"], row["created"]): row["raw_exit"] for row in exits}
                captured = {(row["pid"], row["created"]): row["raw_exit"] for row in debug["processes"]}
                if (debug["error"] is not None or len(debug["processes"]) != 1 or captured != observed
                        or not all(row["event_matches_handle_exit"] and row["machine"] == 0xaa64
                                   and row["image"]["mapped_file_sha256"] == files["consumer.exe"]
                                   for row in debug["processes"])
                        or debug["memory_writes"] or debug["register_writes"] or debug["unwind_probes"] is not None
                        or debug["context_reads_enabled"] != (mode != "no-context")):
                    raise ValueError("Debugger/held-handle/native-job generation evidence differs")
                events = debug["events"]
                gcc_events = [row for row in events if row.get("exception", {}).get("code")
                              in (0x20474343, 0x21474343, 0x22474343)]
                if not gcc_events or any(row["continue_status"] != 0x80010001 for row in gcc_events):
                    raise ValueError("GNU exception forwarding differs")
                mapped = {Path(row["module"]["path"].removeprefix("\\\\?\\")).name.lower(): row["module"]
                          for row in events if "module" in row and "path" in row["module"]}
                for name in names[1:]:
                    entry = mapped[name]
                    path = Path(entry["path"].removeprefix("\\\\?\\")).resolve()
                    if path != (fixture / name).resolve() or entry["mapped_file_sha256"] != files[name]:
                        raise ValueError(f"Wrong actually mapped shared DLL: {name}")
                record["debug_sha256"] = sha(case / "debug" / "result.json")
                record["gnu_exceptions_forwarded"] = len(gcc_events)
            record["passed"] = True
        for name, digest in files.items():
            if sha(original / name) != digest or sha(fixture / name) != digest:
                raise ValueError("Shared-runtime fixture bytes changed")
        for relative, entry in inputs["files"].items():
            if sha(root / relative) != entry["sha256"]:
                raise ValueError(f"Capture input changed during qualification: {relative}")
        report.update(status="native-shared-cpp-ordinary-debug-parity-qualified",
                      scope="Actual shared-provider fixture with bidirectional exceptions, cleanup/rethrow/exception_ptr and TLS. No general exit-domain collector qualification.")
    finally:
        (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(root / "result.json")


if __name__ == "__main__":
    main()
