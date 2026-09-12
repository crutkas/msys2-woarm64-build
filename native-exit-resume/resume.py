"""Fresh owned replay and forensic runs; sealed prior evidence is read-only."""

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(r"C:\ag-exit-e138-01\resume-20260909-01")
OLD = Path(r"C:\ag-exit-e138-01")
DRIVER = Path(r"C:\ag-native-e138-01\native-test-driver-06")
TC_DIAG = Path(r"C:\Users\crutkasLocal\.copilot\session-state\5b01b4e5-41d0-4535-bc71-1133839af6e1\files\cpp-debug-unwind-static-20260908-02")
D70 = Path(r"C:\Users\crutkasLocal\.copilot\session-state\0af73d1b-9b87-4723-8e25-1e32f44a090c\files\execvp-runtime-01\candidate\usr\bin\msys-2.0.dll")
HASHES = {
    str(OLD / "result.json"): "450554aab8d65bd310a1d60ade4ee7d0dde42852c2767af144b7048bcfed6a88",
    str(OLD / "candidate.manifest.json"): "c1f00cbbfc591d3ed9ef48ed73615836be6f9aeeea8243d02f0e709542168cc6",
    str(DRIVER.with_suffix(".SHA256SUMS")): "b46ccab632b0ef2e29301e9118481188cf705c39d278f3e6d1ec12cf0bb6bd42",
    str(TC_DIAG / "handoff.json"): "590110934257b25fd6e01a1d1a02722ae23c3d0da9d25613e0d0a4f054633341",
    str(TC_DIAG / "result.json"): "78fb4e93fc540f9d3f12103b1f03442662446787bb56842408a4c299456c9eee",
    str(D70): "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d",
    str(OLD / "runtime/usr/bin/exception-fixture.exe"): "0d9189f619a6d5b8b94e6c56769154273e8c274fc9743c0b2df597925ad6ece4",
    str(OLD / "runtime/usr/bin/msys-2.0.dll"): "1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16",
    str(OLD / "runtime/etc/fstab"): "387ca1e86c1a18a143eb077ca194ad44c0a2faf98795a0d437f2d210d5a6df18",
    r"C:\Program Files\Python314-arm64\python.exe": "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29",
    r"C:\Windows\System32\ntdll.dll": "81f9d523d199ba1a8bb5fb6081b39e62cdb3289aa2346880c4db43edc6922f9b",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def copy_locked(source, target, expected):
    before = digest(source)
    if before != expected:
        raise RuntimeError(f"Source identity mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open("rb") as src, target.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    copied, after = digest(target), digest(source)
    if before != copied or before != after:
        raise RuntimeError(f"Copy changed: {source}")
    return {"source": str(source), "copy": str(target), "before": before, "copied": copied, "after": after}


def prepare():
    for path, expected in HASHES.items():
        if digest(path) != expected:
            raise RuntimeError(f"Locked input changed: {path}")
    ROOT.mkdir(exist_ok=False)
    copies = []
    for name in ("handoff.json", "result.json"):
        path = TC_DIAG / name
        copies.append(copy_locked(path, ROOT / "diagnosis" / name, HASHES[str(path)]))
    manifest = DRIVER.with_suffix(".SHA256SUMS")
    copies.append(copy_locked(manifest, ROOT / "driver.SHA256SUMS", HASHES[str(manifest)]))
    for line in manifest.read_text().splitlines():
        sha, name = line.split()
        if Path(name).name != name:
            raise RuntimeError("Driver manifest contains a non-leaf path")
        copies.append(copy_locked(DRIVER / name, ROOT / "driver" / name, sha))
    support_lock = load(OLD / "inputs.json")["copies"]
    for name in ("bounded_process.py", "native_job_runner.py", "sources.py"):
        path = OLD / "support" / name
        row = next(row for row in support_lock if row["copy"] == str(path))
        copies.append(copy_locked(path, ROOT / "support" / name, row["copied"]))
    for name in ("windows-abi.json", "bootstrap-lock.json"):
        copies.append(copy_locked(OLD / name, ROOT / name, digest(OLD / name)))
    for cohort, runtime in (("baseline", OLD / "runtime/usr/bin/msys-2.0.dll"), ("d70", D70)):
        for path, rel in (
            (OLD / "runtime/usr/bin/exception-fixture.exe", Path("usr/bin/exception-fixture.exe")),
            (OLD / "runtime/etc/fstab", Path("etc/fstab")), (runtime, Path("usr/bin/msys-2.0.dll")),
        ):
            copies.append(copy_locked(path, ROOT / cohort / rel, HASHES[str(path)]))
    source = OLD / "cpp/exception-fixture.cpp"
    expected_source = next(row["sha256"] for row in load(TC_DIAG / "result.json")["inputs"]
                           if row["path"] == str(source))
    copies.append(copy_locked(source, ROOT / "fixture.cpp", expected_source))
    write(ROOT / "inputs.json", {"schema": 1, "locks": HASHES, "copies": copies,
          "status": "private-replay-inputs", "original_cohort_unchanged": True,
          "d70_scope": "Runtime substitution of unchanged historical static fixture, not producer requalification",
          "max_aggregate_jobs": 1})
    print(json.dumps({"root": str(ROOT), "copies": len(copies)}))


def verify_inputs():
    record = load(ROOT / "inputs.json")
    expected = dict(record["locks"])
    for row in record["copies"]:
        expected[row["source"]] = row["before"]
        expected[row["copy"]] = row["copied"]
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Experiment identity changed: {path}")
    return expected


def free_memory():
    class Memory(C.Structure):
        _fields_ = [("length", C.c_uint32), ("load", C.c_uint32)] + [
            (name, C.c_uint64) for name in
            ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    memory = Memory()
    memory.length = C.sizeof(memory)
    query = C.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
    query.argtypes, query.restype = [C.POINTER(Memory)], C.c_int
    if not query(C.byref(memory)):
        raise C.WinError(C.get_last_error())
    if memory.available <= 8 * 1024 ** 3:
        raise RuntimeError("Required >8 GiB free memory floor reached")
    return memory.available


def run_case(cohort, mode, label, fixture_name="exception-fixture.exe", arguments=()):
    verify_inputs()
    before_memory = free_memory()
    case = ROOT / "cases" / label
    case.mkdir(parents=True, exist_ok=False)
    (case / "relay").mkdir()
    source_copies = []
    for path in sorted(Path(__file__).parent.glob("*.py")):
        source_copies.append(copy_locked(path, case / "source" / path.name, digest(path)))
    fixture = ROOT / cohort / "usr/bin" / fixture_name
    runtime = fixture.with_name("msys-2.0.dll")
    expected_runtime = HASHES[str(D70 if cohort.endswith("d70") else OLD / "runtime/usr/bin/msys-2.0.dll")]
    if digest(runtime) != expected_runtime:
        raise RuntimeError("Private executable root has an unexpected runtime")
    if cohort not in ("baseline", "d70"):
        built = load(ROOT / ("source-build/result.json" if cohort.startswith("source-") else "scratch-build/result.json"))
        for path, sha in built["outputs"].items():
            if digest(path) != sha:
                raise RuntimeError(f"Private relink output changed: {path}")
        for row in built["copies"]:
            if digest(row["copy"]) != row["copied"]:
                raise RuntimeError(f"Private relink input changed: {row['copy']}")
    if fixture_name == "unwind-matrix.exe":
        matrix = load(ROOT / ("source-build/result.json" if cohort.startswith("source-") else "matrix-build/result.json"))
        if digest(fixture) != matrix["outputs"][str(fixture)]:
            raise RuntimeError("Matrix executable does not match build")
    argv = [str(fixture), *arguments]
    if mode != "ordinary":
        argv = [sys.executable, "-B", str(case / "source/debug_tree.py"), "--output", str(case / "debug"),
                "--abi", str(ROOT / "windows-abi.json"), "--timeout", "20",
                *(["--no-context"] if mode == "no-context" else []),
                *(["--unwind-probes"] if mode == "probe" else []), "--", str(fixture), *arguments]
    command = [sys.executable, "-I", "-B", str(ROOT / "driver/native-job.py"),
               "--cwd", str(case), "--target-root", str(ROOT), "--relay-records", str(case / "relay"),
               "--log", str(case / "fixture.log"), "--result", str(case / "native-job.json"),
               "--timeout", "40", "--", *argv]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join([str(fixture.parent), str(Path(env["SystemRoot"]) / "System32")]),
                "HOME": str(case), "USERPROFILE": str(case), "TMP": str(case), "TEMP": str(case)})
    sys.path.insert(0, str(ROOT / "support"))
    from native_job_runner import noninteractive_error_mode
    from bounded_process import run as bounded_run
    with noninteractive_error_mode(), (case / "observer.log").open("xb") as log:
        launch = bounded_run(command, cwd=case, env=env, log=log, timeout=55)
    observation = load(case / "native-job.json")
    complete = (not launch["timed_out"] and not observation["timed_out"]
                and observation["observation_count_matches"]
                and not observation["unobserved_processes"] and not observation["unresolved_processes"]
                and launch["active_at_boundary"] == 0)
    record = {"schema": 1, "command": command, "mode": mode, "cohort": cohort, "launch": launch,
              "fixture_sha256": digest(fixture), "runtime_sha256": digest(runtime),
              "sources": source_copies, "native_job_sha256": digest(case / "native-job.json"),
              "generation_exits": observation["native_target_exits"],
              "complete_observation": complete, "free_before": before_memory, "free_after": free_memory(),
              "qualified": False, "encoding": "UNKNOWN", "decoded_status": None}
    if mode != "ordinary":
        debug = load(case / "debug/result.json")
        actual = {(row["pid"], row["created"]): row["raw_exit"] for row in observation["native_target_exits"]}
        captured = {(row["pid"], row["created"]): row.get("raw_exit") for row in debug["processes"]}
        exact = (len(actual) == len(observation["native_target_exits"])
                 and len(captured) == len(debug["processes"]) and actual == captured and debug["error"] is None
                 and all(row.get("event_matches_handle_exit") for row in debug["processes"]))
        record["debug_raw_generations_equal_observer"] = exact
        record["complete_observation"] &= exact
        record["debug_sha256"] = digest(case / "debug/result.json")
    record["identities_after"] = verify_inputs()
    write(case / "result.json", record)
    print(json.dumps({"case": str(case), "generation_exits": record["generation_exits"],
                      "complete": record["complete_observation"], "mode": mode}), flush=True)
    if not record["complete_observation"]:
        raise RuntimeError(f"Owned observation is incomplete: {case}")
    return record


def matrix_runs(source_fix=False):
    control = "source-control" if source_fix else "relink"
    fixed = "source-fixed" if source_fix else "scratch"
    controls = []
    for name in ("plain", "cleanup"):
        controls.extend((control, name, False, mode, 0 if mode == "ordinary" else 0xC00000FF)
                        for mode in ("ordinary", "debug"))
    for name in ("plain", "cleanup", "rethrow", "nested", "exception-ptr"):
        controls.extend((fixed, name, False, mode, 0) for mode in ("ordinary", "debug"))
    for name in ("cleanup", "rethrow"):
        controls.extend((fixed, name, True, mode, 0) for mode in ("ordinary", "debug"))
    for name, raw in (("uncaught", 73), ("winapi-256", 256), ("crash", 0xC0000005)):
        controls.extend((fixed, name, False, mode, raw) for mode in ("ordinary", "debug"))
    for name in ("cleanup", "rethrow", "nested"):
        controls.extend((fixed + "-d70", name, False, mode, 0) for mode in ("ordinary", "debug"))
    receipts = []
    traces = {"plain": (1, 0), "cleanup": (321, 0), "rethrow": (21, 0), "nested": (21, 1), "exception-ptr": (21, 0)}
    for cohort, name, fork, mode, raw in controls:
        label = f"matrix-{cohort}-{name}-{'fork-' if fork else ''}{mode}-01"
        record = run_case(cohort, mode, label, "unwind-matrix.exe", [name, *(["fork"] if fork else [])])
        actual = sorted(row["raw_exit"] for row in record["generation_exits"])
        expected = [raw] * (2 if fork else 1)
        if actual != expected:
            raise RuntimeError(f"Matrix raw mismatch {label}: {actual} != {expected}")
        if raw == 0:
            output = ROOT / "cases" / label / ("fixture.log" if mode == "ordinary" else "debug/stdout.bin")
            trace, nested = traces[name]
            if f"case={name} trace={trace} nested={nested} result=0" not in output.read_text():
                raise RuntimeError(f"Matrix cleanup semantics failed: {label}")
        receipts.append({"case": label, "result_sha256": digest(ROOT / "cases" / label / "result.json"),
                         "expected_raw": expected, "actual_raw": actual,
                         "contract": f"Exact owned matrix fixture {name}; not a general native-exit allowance"})
    write(ROOT / ("source-matrix-result.json" if source_fix else "matrix-result.json"),
          {"schema": 1, "status": "private-source-matrix-matched" if source_fix else "private-wrapper-matrix-matched",
          "controls": receipts, "producer_admission": False, "old_results_changed": False})
    print(json.dumps({"matrix_controls": len(receipts), "status": "matched"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "matrix"))
    parser.add_argument("--cohort", choices=("baseline", "d70", "relink", "scratch", "scratch-d70",
                                           "source-control", "source-fixed", "source-fixed-d70"), default="baseline")
    parser.add_argument("--source-fix", action="store_true")
    parser.add_argument("--mode", choices=("ordinary", "debug", "no-context", "probe"), default="ordinary")
    parser.add_argument("--label")
    parser.add_argument("--fixture", choices=("exception-fixture.exe", "unwind-matrix.exe"), default="exception-fixture.exe")
    parser.add_argument("--argument", action="append", default=[])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "matrix":
        matrix_runs(args.source_fix)
    else:
        if not args.label or Path(args.label).name != args.label or args.label in (".", ".."):
            parser.error("A fresh leaf case label is required")
        run_case(args.cohort, args.mode, args.label, args.fixture, args.argument)


if __name__ == "__main__":
    main()
