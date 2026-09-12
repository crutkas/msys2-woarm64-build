"""Continue sealed DB qualification without rebuilding or mutating its payload."""

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time

from db_build_inputs import require_db_cpp_receipt
from db_native_checks import environment, observe, require_exit
from native_job_runner import verify_driver
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json
from ssh_crypt_consumer import arm64_pe


HANDOFF_SHA = "161ab1ccbc77432e6fe55bfc7741c4200dcac7be04ae4369b54765ab3c5eed97"
CHANNEL_BEFORE = "dc24d504d8c99d6dceac0d98c54fda7c43e2bd680894c1b8cf1ee9c382924962"
CHANNEL_AFTER = "1908ca7ce32e3dd72bb8550a0a2cc03a53d8cd8e792a9472c9c2546e69968127"
CHANNEL_PATCH_SHA = "15e32b210010a8a57cf55ae227b2d0ebae53fde81422187068174edbf6c3ea82"
MUTEX_SOURCE_SHA = "a842940aa812f0eeb873c9b47e7176ff5b3bd8cfb2a9232e613abeace20bf47b"
FLAGS = ["-O2", "-g", "-fstack-protector-strong", "-Wno-incompatible-pointer-types",
         "-D_GNU_SOURCE", "-D_REENTRANT", "-DDLL_EXPORT", "-DPIC"]


def sealed_json(path, expected):
    if digest(path) != expected:
        raise ContractError(f"Sealed receipt differs: {path}")
    return json.loads(path.read_text())


def own_birth():
    from ctypes import wintypes as W
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    times = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *[ctypes.byref(t) for t in times]):
        raise ctypes.WinError(ctypes.get_last_error())
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def expected_mutex_matrix():
    return [(p, t, a, 2000) for p in (1, 2, 4) for t in (1, 2, 4)
            if (p, t) != (1, 1) for a in (32, 64, 128)]


def require_mutex_driver(root, manifest, expected_sha, runtime_sha, qualification=None, qualification_sha=None):
    if root is None or manifest is None or expected_sha is None:
        raise ContractError("The full mutex matrix requires an explicitly sealed native /bin/sh, rm and mkdir driver")
    record = sealed_json(manifest, expected_sha)
    verify_tree(root, manifest)
    if any("sha256" not in row or "symlink" in row for row in record["files"].values()):
        raise ContractError("The private native driver must contain regular files only")
    bindir = "usr/bin" if "usr/bin/sh.exe" in record["files"] else "bin"
    for basename in ("sh.exe", "rm.exe", "mkdir.exe", "msys-2.0.dll"):
        name = f"{bindir}/{basename}"
        if name not in record.get("files", {}):
            raise ContractError(f"The native mutex driver is incomplete: {name}")
        arm64_pe(root / name)
    if record["files"][f"{bindir}/msys-2.0.dll"]["sha256"] != runtime_sha:
        if qualification is None or qualification_sha is None:
            raise ContractError("A newer driver runtime requires a separately qualified coherent DB cohort")
        qualified = sealed_json(qualification, qualification_sha)
        required_commands = ("c", "compat185", "process", "cpp-held")
        if (qualified.get("status") != "private-native-db-d70-shell-process-api-preflight-passed"
                or qualified.get("inputs_unchanged") is not True
                or qualified.get("base_db_handoff_sha256") != HANDOFF_SHA
                or qualified.get("runtime_manifest", {}).get("sha256") != expected_sha
                or qualified.get("runtime_sha256") != record["files"][f"{bindir}/msys-2.0.dll"]["sha256"]
                or any(not qualified.get("commands", {}).get(name, {}).get("process", {}).get("passed")
                       for name in required_commands)):
            raise ContractError("The newer native driver lacks exact DB API/system/fork cohort qualification")
    if bindir == "usr/bin" and (record.get("required_runtime_directories") != ["tmp"] or not (root / "tmp").is_dir()):
        raise ContractError("The qualified native /usr/bin driver requires its real /tmp layout")
    return record


def transition_under_test(text):
    start = text.index("struct master_transition {")
    end = text.index("static int\nawait_condition(", start)
    body = text[start:end]
    if body.count("become_master(") != 1 or body.count("try_master(") != 1:
        raise ContractError("Unexpected exact channel transition helper")
    return body


def sample_native_workers(root):
    from ctypes import wintypes as W

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
                    ("heap", ctypes.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                    ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD),
                    ("name", W.WCHAR * 260)]

    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", W.WORD), ("maximum_length", W.WORD), ("buffer", ctypes.c_void_p)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtQueryInformationProcess.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                               W.ULONG, ctypes.POINTER(W.ULONG)]
    ntdll.NtQueryInformationProcess.restype = W.LONG
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [W.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.name.lower() in ("cutest.exe", "test_mutex.exe"):
                handle = kernel.OpenProcess(0x1000, False, entry.pid)
                if handle:
                    try:
                        image = ctypes.create_unicode_buffer(32768)
                        length = W.DWORD(len(image))
                        times = [W.FILETIME() for _ in range(4)]
                        if (kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))
                                and Path(image.value).is_relative_to(root)
                                and kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times])):
                            command_buffer = ctypes.create_string_buffer(32768)
                            returned = W.ULONG()
                            status = ntdll.NtQueryInformationProcess(
                                handle, 60, command_buffer, len(command_buffer), ctypes.byref(returned))
                            command = None
                            if status == 0:
                                value = ctypes.cast(command_buffer, ctypes.POINTER(UnicodeString)).contents
                                command = ctypes.wstring_at(value.buffer, value.length // 2)
                            result.append({"pid": entry.pid, "parent_pid": entry.parent,
                                           "created": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                                           "image": image.value, "actual_os_threads": entry.threads,
                                           "kernel_time_100ns": (times[2].dwHighDateTime << 32) | times[2].dwLowDateTime,
                                           "user_time_100ns": (times[3].dwHighDateTime << 32) | times[3].dwLowDateTime,
                                           "command": command, "command_query_status": status})
                    finally:
                        kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(snapshot)
    return result


def observe_mutex(command, cwd, env, output, label, driver, report, timeout=900):
    stop = threading.Event()
    samples, errors = [], []

    def monitor():
        try:
            with (output / "mutex-progress.jsonl").open("x", encoding="utf-8") as stream:
                while not stop.is_set():
                    sample = {"monotonic": time.monotonic(), "utc": datetime.now(timezone.utc).isoformat(),
                              "free_gib": require_memory(), "workers": sample_native_workers(output)}
                    samples.append(sample)
                    stream.write(json.dumps(sample) + "\n")
                    stream.flush()
                    stop.wait(0.5)
        except (OSError, ContractError) as error:
            errors.append(str(error))

    thread = threading.Thread(target=monitor, name="db-mutex-resource-observer")
    thread.start()
    try:
        row = observe(command, cwd, env, output, label, driver, timeout)
    finally:
        stop.set()
        thread.join(timeout=5)
        write_json(output / "mutex-resource-samples.json", {"samples": samples, "errors": errors,
                    "scope": "Actual OS thread counts include MSYS infrastructure, not just requested locker threads"})
        report["mutex_resource_samples"] = {"path": str(output / "mutex-resource-samples.json"),
                                            "sha256": digest(output / "mutex-resource-samples.json")}
    if thread.is_alive() or errors:
        raise ContractError(f"Mutex resource observation failed: {errors}")
    report["minimum_free_gib"] = min(report["minimum_free_gib"], min(s["free_gib"] for s in samples))
    report["maximum_sampled_native_processes"] = max(len(s["workers"]) for s in samples)
    report["maximum_sampled_native_os_threads"] = max(
        sum(worker["actual_os_threads"] for worker in s["workers"]) for s in samples)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("channel-baseline", "channel", "mutex", "suite"), required=True)
    parser.add_argument("--runs", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--approved-mutex-matrix", action="store_true")
    parser.add_argument("--matrix-timeout", type=int, choices=(900, 7200), default=900,
                        help="900 seconds by default; 7200 only for an explicitly authorized full-load timing investigation")
    parser.add_argument("--native-driver", type=Path)
    parser.add_argument("--native-driver-manifest", type=Path)
    parser.add_argument("--native-driver-sha256")
    parser.add_argument("--native-driver-qualification", type=Path)
    parser.add_argument("--native-driver-qualification-sha256")
    args = parser.parse_args()
    output = args.output.resolve()
    handoff = sealed_json(args.handoff, HANDOFF_SHA)
    old_root = Path(handoff["owned_root"])
    if (output.exists() or not output.is_relative_to(old_root / "resume-20260909")
            or any(path.is_symlink() or path.is_junction() for path in output.parents)):
        raise ContractError("A fresh, disjoint owned continuation output is required")
    if args.mode in ("mutex", "suite") and (not args.approved_mutex_matrix or args.runs != 1):
        raise ContractError("The unchanged mutex matrix needs an explicit new grant and a single full run")
    if args.mode not in ("mutex", "suite") and args.matrix_timeout != 900:
        raise ContractError("The extended timeout applies only to the unchanged mutex matrix")
    compiler_receipt = Path(handoff["compiler_receipt"]["path"])
    producer = sealed_json(compiler_receipt, handoff["compiler_receipt"]["sha256"])
    prefix = Path(producer["prefix"])
    require_db_cpp_receipt(producer)
    driver_record = None
    if args.mode in ("mutex", "suite"):
        driver_record = require_mutex_driver(args.native_driver, args.native_driver_manifest,
                                              args.native_driver_sha256,
                                              producer["files"]["bin/msys-2.0.dll"]["sha256"],
                                              args.native_driver_qualification,
                                              args.native_driver_qualification_sha256)
    elif any(value is not None for value in (args.native_driver, args.native_driver_manifest, args.native_driver_sha256,
                                            args.native_driver_qualification, args.native_driver_qualification_sha256)):
        raise ContractError("A native system-shell driver is only used by mutex/full-suite execution")
    build_result = Path(handoff["build"]["receipt"]["path"])
    built = sealed_json(build_result, handoff["build"]["receipt"]["sha256"])
    build_root = Path(handoff["stage"]).parent
    stage = build_root / "stage"
    prior_receipt = Path(handoff["qualification"]["upstream_C"]["receipt"]["path"])
    prior = sealed_json(prior_receipt, handoff["qualification"]["upstream_C"]["receipt"]["sha256"])
    prepared = Path(handoff["prepared_source"]["path"])
    source_record = sealed_json(prepared, handoff["prepared_source"]["sha256"])
    bootstrap_receipt = Path(handoff["private_bootstrap"]["path"])
    bootstrap_record = sealed_json(bootstrap_receipt, handoff["private_bootstrap"]["sha256"])
    bootstrap = Path(bootstrap_record["prefix"])
    observer_manifest = Path(old_root.parent / "ag-e138920f/native-test-driver-02.manifest.json")
    driver = observer_manifest.with_name("native-test-driver-02")
    if digest(verify_driver(driver)) != built["observer_manifest_sha256"]:
        raise ContractError("Historical observer no longer matches the sealed DB cohort")
    verify_tree(stage, build_result)
    verify_tree(prefix, compiler_receipt)
    verify_tree(bootstrap, bootstrap_receipt)
    originals = prior["queue_adaptation"]["object_identities"]
    if len(originals) != 16 or any(digest(path) != sha for path, sha in originals.items()):
        raise ContractError("The complete prior CuTest object set changed")
    original_channel = build_root / "source/test/c/suites/TestChannel.c"
    original_mutex = build_root / "source/test/c/suites/TestMutexAlignment.c"
    if digest(original_channel) != CHANNEL_BEFORE or digest(original_mutex) != MUTEX_SOURCE_SHA:
        raise ContractError("Sealed upstream channel or mutex test source changed")
    output.mkdir(parents=True)
    (output / "native-exits").mkdir()
    native_bindir = output / ("usr/bin" if driver_record and "usr/bin/sh.exe" in driver_record["files"] else "bin")
    native_bindir.mkdir(parents=True)
    report = {"schema": 1, "status": "failed", "mode": args.mode, "pid": os.getpid(),
              "creation_filetime": own_birth(), "recorded_utc": datetime.now(timezone.utc).isoformat(),
              "command": [sys.executable, *sys.argv], "base_handoff_sha256": HANDOFF_SHA,
              "scope": "Historical sealed native DB cohort continuation; no current provider or blanket SDK admission",
              "full_cpp_qualified": False, "package_admitted": False, "commands": {}, "tests": [],
              "minimum_free_gib": require_memory(), "parallel_test_runs": 1,
              "matrix_timeout_seconds": args.matrix_timeout,
              "mutex_grant": {"lockers": 4, "wakeup": 1, "threads_per_locker": 4}
              if args.approved_mutex_matrix else None}
    if driver_record is not None:
        report["scope"] = "Sealed historical DB payload with a separately qualified native-driver runtime composition"
        relative_bin = native_bindir.relative_to(output).as_posix()
        report["runtime_sha256"] = driver_record["files"][relative_bin + "/msys-2.0.dll"]["sha256"]
        report["native_driver_qualification_sha256"] = args.native_driver_qualification_sha256
    write_json(output / "launch.json", report)
    print(json.dumps({k: report[k] for k in ("pid", "creation_filetime", "command")}), flush=True)
    identities = {str(path): digest(path) for path in
                  (args.handoff, build_result, compiler_receipt, prepared, bootstrap_receipt,
                   prior_receipt, original_channel, original_mutex, Path(__file__),
                   Path(__file__).with_name("db_native_checks.py"),
                   Path(__file__).with_name("native_job_runner.py"))}
    if driver_record is not None:
        for directory in driver_record.get("directories", []):
            (output / directory).mkdir(parents=True, exist_ok=True)
        for directory in driver_record.get("required_runtime_directories", []):
            (output / directory).mkdir(parents=True, exist_ok=True)
        for name in driver_record["files"]:
            destination = output / name
            if destination.exists():
                raise ContractError("Native driver file collides with continuation evidence")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.native_driver / name, destination)
            if digest(destination) != driver_record["files"][name]["sha256"]:
                raise ContractError("Native driver copy differs")
        verify_tree(args.native_driver, args.native_driver_manifest)
        identities[str(args.native_driver_manifest)] = args.native_driver_sha256
        if args.native_driver_qualification is not None:
            identities[str(args.native_driver_qualification)] = args.native_driver_qualification_sha256
        report["native_driver_input"] = {"root": str(args.native_driver),
                                         "manifest_sha256": args.native_driver_sha256}
    runtime_sources = [stage / "usr/bin/msys-db-6.2.dll"]
    if driver_record is None:
        runtime_sources.append(prefix / "bin/msys-2.0.dll")
    for source in runtime_sources:
        identities[str(source)] = digest(source)
        target = native_bindir / source.name
        if not target.exists():
            shutil.copy2(source, target)
        if digest(target) != identities[str(source)]:
            raise ContractError("Private runtime/DLL copy differs")
        report.setdefault("runtime_inputs", []).append(arm64_pe(target))
    env = environment(prefix, output, bootstrap)
    env["PATH"] = str(native_bindir) + os.pathsep + env["PATH"]
    includes = [build_root / "build", build_root / "source/src",
                build_root / "source/test/c/cutest", build_root / "source/test/c/suites",
                build_root / "source/test/c/common"]

    def checked(name, command, cwd=output, timeout=120):
        row = observe(command, cwd, env, output, name, driver, timeout)
        report["commands"][name] = row
        report["minimum_free_gib"] = min(report["minimum_free_gib"], require_memory())
        if not row["process"]["passed"]:
            raise ContractError(f"Native continuation phase failed: {name}")
        return row

    def compile_source(name, source):
        checked(name, [prefix / "bin/gcc.exe", *FLAGS, *["-I" + str(p) for p in includes],
                       "-c", source, "-o", output / (name + ".o")])
        return output / (name + ".o")

    try:
        objects = [Path(path) for path in originals]
        if args.mode in ("channel", "suite"):
            copied = output / "TestChannel.c"
            shutil.copyfile(original_channel, copied)
            patch = Path(__file__).parent / "patches/db-6.2.32-channel-master-transition.patch"
            if digest(patch) != CHANNEL_PATCH_SHA:
                raise ContractError("Reviewed master-transition patch changed")
            identities[str(patch)] = CHANNEL_PATCH_SHA
            checked("channel-patch", [bootstrap / "usr/bin/patch.exe", "--batch", "--forward", "--fuzz=0",
                                      "--no-backup-if-mismatch", "-p1", "-d", output, "-i", patch])
            if digest(copied) != CHANNEL_AFTER:
                raise ContractError("Patched channel source is not the reviewed version")
            report["channel_patch"] = {"sha256": CHANNEL_PATCH_SHA, "before": CHANNEL_BEFORE, "after": CHANNEL_AFTER}
            candidate = compile_source("channel", copied)
            objects = [candidate if path.name == "TestChannel.o" else path for path in objects]
            helper = output / "db-channel-transition-under-test.h"
            helper.write_text(transition_under_test(copied.read_text()), newline="\n")
            control = Path(__file__).parent / "fixtures/db-master-transition-control.c"
            identities[str(control)] = digest(control)
            binary = output / "transition-control.exe"
            checked("control-compile", [prefix / "bin/gcc.exe", "-O2", "-g", "-Werror", "-fstack-protector-strong",
                                       "-I" + str(stage / "usr/include"), "-I" + str(output), control, "-o", binary])
            row = checked("control", [sys.executable, "-I", driver / "native-target-exec.py", binary])
            require_exit(row, binary)
            if b"DB master transition controls PASS:" not in (output / "control.log").read_bytes():
                raise ContractError("The deterministic transition controls did not execute")
            report["transition_control"] = {"fixture_sha256": digest(control), "extracted_helper_sha256": digest(helper),
                                          "cases": ["success", "delayed", "timeout", "wrong-master", "start-error", "stat-error"]}
        executable = native_bindir / "cutest.exe"
        checked("link", [prefix / "bin/gcc.exe", "-Wl,--no-insert-timestamp", "-o", executable, *objects,
                         stage / "usr/lib/libdb-6.2.dll.a", "-lm", "-lpthread"])
        report["executable"] = arm64_pe(executable)
        if args.mode in ("mutex", "suite"):
            mutex_source = build_root / "source/src/mutex/test_mutex.c"
            if digest(mutex_source) != source_record["files"]["src/mutex/test_mutex.c"]["sha256"]:
                raise ContractError("Original mutex worker source changed")
            worker = native_bindir / "test_mutex.exe"
            obj = compile_source("mutex", mutex_source)
            checked("mutex-link", [prefix / "bin/gcc.exe", "-Wl,--no-insert-timestamp", "-o", worker, obj,
                                   stage / "usr/lib/libdb-6.2.dll.a", "-lm", "-lpthread"])
            report["mutex_worker"] = arm64_pe(worker)
        names = prior["upstream_suite_inventory"] if args.mode == "suite" else [
            "TestMutexAlignment" if args.mode == "mutex" else "TestChannel"]
        failures = []
        for attempt in range(1, args.runs + 1):
            for name in names:
                cwd = output / f"run-{attempt:02d}-{name}"
                cwd.mkdir()
                if name == "TestMutexAlignment":
                    shutil.copy2(native_bindir / "test_mutex.exe", cwd / "test_mutex.exe")
                if name == "TestDbTuner":
                    shutil.copy2(stage / "usr/bin/db_tuner.exe", cwd / "db_tuner.exe")
                label = f"{attempt:02d}-{name}"
                command = [sys.executable, "-I", driver / "native-target-exec.py", executable, "-s", name]
                run_env = dict(env)
                if driver_record is not None:
                    run_env["PATH"] = os.pathsep.join(map(str, (
                        native_bindir, Path(os.environ["SystemRoot"]) / "System32")))
                if name == "TestMutexAlignment":
                    row = observe_mutex(command, cwd, run_env, output, label, driver, report, args.matrix_timeout)
                else:
                    row = observe(command, cwd, run_env, output, label, driver, 300)
                report["commands"][label] = row
                text = (output / (label + ".log")).read_text(errors="replace")
                count = prior["upstream_case_counts"][name]
                passed = row["process"]["passed"] and re.findall(r"OK \((\d+) tests?\)", text) == [str(count)]
                raw = require_exit(row, executable, None)
                passed = passed and raw["raw_exit"] == 0
                if name == "TestMutexAlignment":
                    matrix = [tuple(map(int, values)) for values in re.findall(
                        r"\./test_mutex -p (\d+) -t (\d+) -a (\d+) -n (\d+)", text)]
                    passed = passed and matrix == expected_mutex_matrix()
                    report["mutex_actual_matrix"] = matrix
                    report["mutex_native_exits"] = row["evidence"]["native_target_exits"]
                report["tests"].append({"name": name, "attempt": attempt, "passed": passed,
                                        "native_exit": raw, "expected_cases": count})
                report["minimum_free_gib"] = min(report["minimum_free_gib"], require_memory())
                if not passed:
                    failures.append(label)
        report["status"] = "passed" if not failures else "failed"
        report["failures"] = failures
    except (OSError, ContractError) as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            if any(digest(path) != sha for path, sha in {**originals, **identities}.items()):
                raise ContractError("Sealed input or maintained driver changed during continuation")
            verify_tree(stage, build_result)
            verify_tree(prefix, compiler_receipt)
            verify_tree(bootstrap, bootstrap_receipt)
            if driver_record is not None:
                verify_tree(args.native_driver, args.native_driver_manifest)
                if any(digest(output / name) != row["sha256"] for name, row in driver_record["files"].items()):
                    raise ContractError("Native driver input changed during mutex checks")
            verify_driver(driver)
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update(status="failed", inputs_unchanged=False, integrity_error=str(error))
            raise
        finally:
            report["input_identities"] = identities
            write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "tests": report["tests"]}), flush=True)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
