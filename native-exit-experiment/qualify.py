"""Serial qualification gates using the sealed bounded-process/job helpers."""

import argparse
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import sys

from prepare import ROOT, TC, WIN_TC, digest, write_json

sys.path.insert(0, str(ROOT / "support"))
from bounded_process import run as bounded_run
from native_job_runner import noninteractive_error_mode, run_observed


class Memory(C.Structure):
    _fields_ = [("length", C.c_uint32), ("load", C.c_uint32)] + [
        (name, C.c_uint64) for name in
        ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]


def free_memory():
    memory = Memory()
    memory.length = C.sizeof(memory)
    query = C.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
    query.argtypes, query.restype = [C.POINTER(Memory)], C.c_int
    if not query(C.byref(memory)):
        raise C.WinError(C.get_last_error())
    if memory.available <= 8 * 1024 ** 3:
        raise RuntimeError("Required >8 GiB free memory floor reached")
    return memory.available


def environment(work, toolchain=None):
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    directories = [ROOT / "runtime/usr/bin", Path(env["SystemRoot"]) / "System32"]
    if toolchain:
        directories.insert(0, toolchain / "bin")
    env.update({"PATH": os.pathsep.join(map(str, directories)), "HOME": str(work),
                "USERPROFILE": str(work), "TEMP": str(work), "TMP": str(work),
                "WOARM64_NATIVE_TEST_ROOT": str(ROOT), "WOARM64_NATIVE_ARG_CONVERSION": "none",
                "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def build():
    output = ROOT / "build"
    output.mkdir(exist_ok=False)
    source = Path(__file__).with_name("fixture.c")
    copied = output / source.name
    before = digest(source)
    shutil.copyfile(source, copied)
    if digest(copied) != before or digest(source) != before:
        raise RuntimeError("Fixture source changed while copied")
    commands = [
        ("msys", TC, [str(TC / "bin/gcc.exe"), "-O0", "-g", str(copied),
                      "-o", str(ROOT / "runtime/usr/bin/exit-fixture.exe")]),
        ("windows", WIN_TC, [str(WIN_TC / "bin/gcc.exe"), "-DWINDOWS_CONTROL", "-O0", "-g", str(copied),
                             "-o", str(ROOT / "windows-fixture.exe")]),
    ]
    receipts = []
    for name, toolchain, argv in commands:
        before_memory = free_memory()
        with noninteractive_error_mode(), (output / f"{name}.log").open("xb") as log:
            record = bounded_run(argv, cwd=output, env=environment(output, toolchain), log=log, timeout=120)
        receipts.append({"name": name, "command": argv, "result": record,
                         "free_before": before_memory, "free_after": free_memory()})
        write_json(output / f"{name}.json", receipts[-1])
        if not record["passed"]:
            raise RuntimeError(f"Fixture build failed; inspect {name}.log")
    abi_dir = ROOT / "abi"
    abi_dir.mkdir()
    with noninteractive_error_mode(), (abi_dir / "abi.log").open("xb") as log:
        abi_result = bounded_run([str(ROOT / "windows-fixture.exe"), "abi"], cwd=abi_dir,
                                 env=environment(abi_dir), log=log, timeout=10)
    write_json(abi_dir / "run.json", abi_result)
    if not abi_result["passed"]:
        raise RuntimeError("Native Windows ABI probe failed")
    abi = json.loads((abi_dir / "abi.log").read_text())
    write_json(ROOT / "windows-abi.json", abi)
    write_json(output / "result.json", {"schema": 1, "builds": receipts,
               "fixture_source": {"source": str(source), "copy": str(copied),
                                  "before": before, "copied": digest(copied), "after": digest(source)},
               "outputs": {str(path): digest(path) for path in
                           (ROOT / "runtime/usr/bin/exit-fixture.exe", ROOT / "windows-fixture.exe")}})
    print(json.dumps({"status": "fixtures-built", "abi": abi, "build_pids": [r["result"]["pid"] for r in receipts]}))


def observe(name, command, debug, no_context=False):
    output = ROOT / "cases" / (name + ("-debug" if debug else "-ordinary"))
    output.mkdir(parents=True, exist_ok=False)
    (output / "relay").mkdir()
    snapshots = []
    for path in sorted(Path(__file__).parent.iterdir()):
        if path.suffix not in (".py", ".c", ".cpp"):
            continue
        before = digest(path)
        target = output / "source" / path.name
        target.parent.mkdir(exist_ok=True)
        with path.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        copied, after = digest(target), digest(path)
        if before != copied or before != after:
            raise RuntimeError("Experimental source changed while snapshotted")
        snapshots.append({"source": str(path), "copy": str(target), "before": before, "copied": copied, "after": after})
    env = environment(output)
    argv = command
    if debug:
        argv = [sys.executable, "-B", str(Path(__file__).with_name("debug_tree.py")),
                "--abi", str(ROOT / "windows-abi.json"), "--output", str(output / "debug"),
                "--timeout", "20", *(["--no-context"] if no_context else []), "--", *command]
    before = free_memory()
    image_before = digest(command[0])
    result = run_observed(argv, cwd=output, env=env, log_path=output / "observer.log",
                          result_path=output / "native-job.json", relay_records=output / "relay",
                          timeout=40, driver_prefix=ROOT / "driver")
    raw = json.loads((output / "native-job.json").read_text())
    image_after = digest(command[0])
    if image_before != image_after:
        raise RuntimeError("Owned fixture changed during observation")
    receipt = {"schema": 1, "command": argv, "fixture_command": command, "debug": debug,
               "source_snapshots": snapshots,
               "fixture_identity": {"path": command[0], "before": image_before, "after": image_after},
               "wrapper_result": result, "free_before": before, "free_after": free_memory(),
               "collector_source_sha256": digest(Path(__file__).with_name("debug_tree.py")),
               "native_job_sha256": digest(output / "native-job.json"),
               "raw_exits": sorted(row["raw_exit"] for row in raw["native_target_exits"]),
               "identities": [{"pid": row["pid"], "created": row["created"], "raw_exit": row["raw_exit"]}
                              for row in raw["native_target_exits"]],
               "full_observation": (raw["observation_count_matches"] and not raw["timed_out"]
                                    and not raw["unobserved_process_ids"])}
    if debug and (output / "debug/result.json").exists():
        captured = json.loads((output / "debug/result.json").read_text())
        receipt["debug_result_sha256"] = digest(output / "debug/result.json")
        receipt["debug_status"] = captured["status"]
        receipt["debug_raw_exits"] = sorted(row["raw_exit"] for row in captured["processes"] if "raw_exit" in row)
        receipt["debug_error"] = captured["error"]
        receipt["debug_vs_job_exits_match"] = receipt["debug_raw_exits"] == receipt["raw_exits"]
        receipt["full_observation"] &= (captured["error"] is None
                                        and len(captured["processes"]) == len(raw["native_target_exits"])
                                        and receipt["debug_vs_job_exits_match"]
                                        and all(row.get("event_matches_handle_exit") for row in captured["processes"]))
    elif debug:
        receipt["full_observation"] = False
    write_json(output / "result.json", receipt)
    print(json.dumps({"case": name, "debug": debug, "raw_exits": receipt["raw_exits"],
                      "full_observation": receipt["full_observation"], "identities": receipt["identities"]}), flush=True)
    return receipt


def cases():
    msys = str(ROOT / "runtime/usr/bin/exit-fixture.exe")
    windows = str(ROOT / "windows-fixture.exe")
    result = {
        "windows-zero": [windows, "direct", "winapi", "0"],
        "msys-direct-one": [msys, "direct", "native", "1"],
        "msys-fork-one": [msys, "fork", "native", "1"],
        "msys-fork-six": [msys, "fork", "native", "6"],
        "winapi-fork-256": [msys, "fork", "winapi", "256"],
        "winapi-fork-1536": [msys, "fork", "winapi", "1536"],
        "msys-exec-one": [msys, "fork", "exec", "1", msys],
        "forged-fork-256": [msys, "fork", "forged", "256"],
        "msys-signal": [msys, "fork", "signal", "0"],
        "msys-crash": [msys, "fork", "crash", "0"],
        "msys-forced": [msys, "fork", "forced", "1536"],
        "forkfailure-marker": [msys, "fork", "winapi", "0x00800000"],
        "cpp-exception": [str(ROOT / "runtime/usr/bin/exception-fixture.exe")],
        "cpp-fork-exception": [str(ROOT / "runtime/usr/bin/exception-fixture.exe"), "fork"],
    }
    for code in (0, 1, 6, 255, 256, 1536):
        result[f"overlay-{code}"] = [msys, "fork", "overlay", str(code), windows]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("build", "cpp", "inspect", "bootstrap", "legacy", "cases"))
    parser.add_argument("--suffix", default="")
    parser.add_argument("--no-context", action="store_true")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    if args.phase == "legacy":
        output = ROOT / "legacy-debug-only"
        output.mkdir(exist_ok=False)
        (output / "relay").mkdir()
        command = [sys.executable, "-B", str(ROOT / "support/capture-native-exception.py"),
                   "--executable", str(ROOT / "runtime/usr/bin/exception-fixture.exe"),
                   "--output", str(output / "capture"), "--path-directory", str(ROOT / "runtime/usr/bin")]
        record = run_observed(command, cwd=output, env=environment(output),
                              log_path=output / "observer.log", result_path=output / "native-job.json",
                              relay_records=output / "relay", timeout=40, driver_prefix=ROOT / "driver")
        write_json(output / "result.json", {"command": command, "wrapper_result": record,
                   "helper_sha256": digest(ROOT / "support/capture-native-exception.py"),
                   "capture_sha256": digest(output / "capture/result.json"),
                   "free_after": free_memory()})
        print(json.dumps(record))
        return
    if args.phase == "build":
        build()
        return
    if args.phase in ("cpp", "inspect"):
        output = ROOT / args.phase
        output.mkdir(exist_ok=False)
        if args.phase == "cpp":
            source = Path(__file__).with_name("exception-fixture.cpp")
            copied = output / source.name
            before = digest(source)
            shutil.copyfile(source, copied)
            if before != digest(copied) or before != digest(source):
                raise RuntimeError("C++ source changed while copying")
            command = [str(TC / "bin/g++.exe"), "-O0", "-g", "-static-libgcc", "-static-libstdc++",
                       str(copied), "-o", str(ROOT / "runtime/usr/bin/exception-fixture.exe")]
        else:
            command = [str(TC / "bin/objdump.exe"), "-t", str(ROOT / "runtime/usr/bin/msys-2.0.dll")]
        before_memory = free_memory()
        with noninteractive_error_mode(), (output / "output.log").open("xb") as log:
            record = bounded_run(command, cwd=output, env=environment(output, TC), log=log, timeout=120)
        write_json(output / "result.json", {"command": command, "result": record,
                   "free_before": before_memory, "free_after": free_memory()})
        if not record["passed"]:
            raise RuntimeError(f"{args.phase} failed; inspect private output.log")
        print(json.dumps(record))
        return
    if args.phase == "bootstrap":
        path = ROOT / "cases/windows-zero-debug/debug/result.json"
        control = json.loads(path.read_text())
        exceptions = [row for row in control["events"] if row["event"] == 1]
        if (control["error"] is not None or len(exceptions) != 1
                or exceptions[0]["exception"]["code"] != 0x80000003
                or control["processes"][0]["raw_exit"] != 0):
            raise RuntimeError("Expected the single native Windows initial loader breakpoint")
        ntdll = next(m for m in control["processes"][0]["modules"]
                     if Path(m.get("path", "")).name.lower() == "ntdll.dll")
        write_json(ROOT / "bootstrap-lock.json",
                   {"schema": 1, "control_receipt": str(path), "control_receipt_sha256": digest(path),
                    "ntdll_sha256": ntdll["mapped_file_sha256"],
                    "rva": exceptions[0]["exception"]["address"] - ntdll["base"],
                    "scope": "Initial loader debug protocol only, never exit-domain evidence"})
        return
    matrix = cases()
    for name in args.names:
        command = matrix[name]
        label = name + args.suffix
        ordinary = observe(label, command, False)
        debug = observe(label, command, True, args.no_context)
        parity = ordinary["full_observation"] and debug["full_observation"] and ordinary["raw_exits"] == debug["raw_exits"]
        write_json(ROOT / "cases" / f"{label}-parity.json",
                   {"schema": 1, "name": name, "behavioral_exit_parity": parity,
                    "ordinary": ordinary, "debug": debug, "qualified": False})
        if not parity:
            raise SystemExit(f"PARITY GATE FAILED: {name}; no promotion or decoding permitted")


if __name__ == "__main__":
    main()
