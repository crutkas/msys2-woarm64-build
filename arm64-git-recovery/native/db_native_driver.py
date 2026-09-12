"""Adopt an owner-frozen native shell and qualify a separate DB runtime composition."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

from db_channel_checks import HANDOFF_SHA, own_birth, sealed_json
from db_native_checks import environment, observe, require_exit
from native_job_runner import verify_driver
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json
from ssh_crypt_consumer import arm64_pe, inspect_process, matching_relay, validate_loaded


SHELL_PREPARE_SHA = "8fc7a3ff9d0f869936311218282314989f0740e782b34f91202bf251113dc4d4"
SHELL_RESULT_SHA = "b4a0ee773d0b06c946bce77f68acfb73c5f7157aef6e7f144eabed05be3ea8cd"
D70_SHA = "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d"
FSTAB_SHA = "387ca1e86c1a18a143eb077ca194ad44c0a2faf98795a0d437f2d210d5a6df18"


def validate_shell_record(record):
    files = record.get("runtime", {}).get("files", {})
    required = {"usr/bin/sh.exe": "6d76e238226f02579efad941e4e021ee5aea614b8a54bb6750f572f4acb62512",
                "usr/bin/rm.exe": "ce6b95b18aae78614e7e3c01b8979443a28a7dcd800f28af60971bb3ef5f5915",
                "usr/bin/mkdir.exe": "2768035ab6b0c14454d576c0c734259e755b7128bd9ddfabdfe01e705a14b584",
                "usr/bin/msys-2.0.dll": D70_SHA, "etc/fstab": FSTAB_SHA}
    if (record.get("required_runtime_directories") != ["tmp"] or len(files) != 8868
            or any(files.get(name, {}).get("sha256") != sha for name, sha in required.items())
            or any("sha256" not in row or "symlink" in row for row in files.values())):
        raise ContractError("The owner-approved native shell composition differs")
    return files


def held_cpp(executable, cwd, env, output, observer, expected, report):
    stop = threading.Event()
    watch = {}

    def monitor():
        try:
            deadline = time.monotonic() + 20
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    text = (cwd / "ready").read_text()
                except FileNotFoundError:
                    stop.wait(0.05)
                    continue
                if not text.endswith("\n"):
                    stop.wait(0.05)
                    continue
                if not text.strip().isdecimal():
                    raise ContractError("Invalid held native PID")
                pid = int(text.strip())
                identity = inspect_process(pid, expected)
                validate_loaded(identity, pid, executable, expected)
                watch["identity"] = identity
                write_json(output / "loaded-cpp-process.json", identity)
                (cwd / "continue").write_bytes(b"go\n")
                return
            raise ContractError("Native C++ fixture did not reach its module handshake")
        except (OSError, ValueError) as error:
            watch["error"] = str(error)

    thread = threading.Thread(target=monitor, name="db-composite-cpp-module-proof")
    thread.start()
    try:
        row = observe([sys.executable, "-I", observer / "native-target-exec.py", executable, "hold"],
                      cwd, env, output, "cpp-held", observer, 45)
        report["commands"]["cpp-held"] = row
    finally:
        stop.set()
        thread.join(timeout=5)
    if thread.is_alive() or "identity" not in watch or watch.get("error"):
        raise ContractError("New-cohort held C++ module proof failed: " + str(watch.get("error")))
    require_exit(row, executable)
    if not row["process"]["passed"] or b"DB C++ PASS:" not in (output / "cpp-held.log").read_bytes():
        raise ContractError("New-cohort full C++ API/exception behavior failed")
    report["native_cpp_process"] = watch["identity"]
    report["cpp_relay"] = matching_relay(output / "native-exits", watch["identity"], digest(executable))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("shell-root", "shell-prepare", "shell-result", "db-handoff", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name, path in vars(args).items():
        setattr(args, name, path.resolve())
    output = args.output
    if output.exists() or not output.is_relative_to(Path(r"C:\ag-db-e138-01\resume-20260909")):
        raise ContractError("A fresh DB-owned native composition output is required")
    if any(path.is_symlink() or path.is_junction() for path in output.parents):
        raise ContractError("Native composition output may not traverse links")
    source_record = sealed_json(args.shell_prepare, SHELL_PREPARE_SHA)
    sealed_json(args.shell_result, SHELL_RESULT_SHA)
    files = validate_shell_record(source_record)
    if inventory(args.shell_root) != files:
        raise ContractError("Owner-frozen shell file inventory differs")
    directories = directory_names(args.shell_root)
    base = sealed_json(args.db_handoff, HANDOFF_SHA)
    compiler_receipt = Path(base["compiler_receipt"]["path"])
    producer = sealed_json(compiler_receipt, base["compiler_receipt"]["sha256"])
    prefix = Path(producer["prefix"])
    build_receipt = Path(base["build"]["receipt"]["path"])
    built = sealed_json(build_receipt, base["build"]["receipt"]["sha256"])
    stage = Path(base["stage"])
    observer = Path(r"C:\ag-e138920f\native-test-driver-02")
    if digest(verify_driver(observer)) != built["observer_manifest_sha256"]:
        raise ContractError("The sealed raw-exit observer changed")
    verify_tree(prefix, compiler_receipt)
    verify_tree(stage, build_receipt)
    output.mkdir(parents=True)
    (output / "native-exits").mkdir()
    (output / "temp").mkdir()
    runtime = output / "runtime"
    runtime.mkdir()
    report = {"schema": 1, "status": "failed", "pid": os.getpid(), "creation_filetime": own_birth(),
              "command": [sys.executable, *sys.argv], "commands": {}, "minimum_free_gib": require_memory(),
              "scope": "Explicit new private d70 runtime/old DB payload composition; targeted DB/process qualification only",
              "full_cpp_qualified": False, "provider_admitted": False, "bash_admitted": False,
              "source_shell_assertions_not_whole_observer_admission": True,
              "source_prepare_sha256": SHELL_PREPARE_SHA, "source_consumer_result_sha256": SHELL_RESULT_SHA,
              "base_db_handoff_sha256": HANDOFF_SHA, "runtime_sha256": D70_SHA}
    write_json(output / "launch.json", report)
    print(json.dumps({k: report[k] for k in ("pid", "creation_filetime", "command")}), flush=True)
    identities = {str(path): digest(path) for path in (args.shell_prepare, args.shell_result, args.db_handoff,
                  compiler_receipt, build_receipt, Path(__file__), Path(__file__).with_name("native_job_runner.py"),
                  Path(__file__).with_name("db_native_checks.py"), Path(__file__).with_name("ssh_crypt_consumer.py"))}
    try:
        for name in directories:
            (runtime / name).mkdir(parents=True, exist_ok=True)
        for index, name in enumerate(files):
            source, destination = args.shell_root / name, runtime / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if index % 256 == 0:
                report["minimum_free_gib"] = min(report["minimum_free_gib"], require_memory())
        (runtime / "tmp").mkdir(exist_ok=True)
        copied = inventory(runtime)
        if copied != files or inventory(args.shell_root) != files or directory_names(args.shell_root) != directories:
            raise ContractError("Complete shell before/copy/after inventory equality failed")
        write_json(output / "shell-copy.json", {"files": copied, "directories": directory_names(runtime),
                   "source_unchanged": True, "complete_inventory_equality": True,
                   "source_prepare_sha256": SHELL_PREPARE_SHA})
        additions = {}
        for name in ("msys-db-6.2.dll", "msys-db_cxx-6.2.dll"):
            source, destination = stage / "usr/bin" / name, runtime / "usr/bin" / name
            if destination.exists():
                raise ContractError("Native driver already contains a conflicting DB DLL")
            shutil.copy2(source, destination)
            additions["usr/bin/" + name] = built["files"]["usr/bin/" + name]
            if digest(destination) != additions["usr/bin/" + name]["sha256"]:
                raise ContractError("DB DLL copy differs")
        write_json(output / "composition-before-tests.json", {
            "files": {**files, **additions}, "required_runtime_directories": ["tmp"],
            "prefix": str(runtime), "source_prepare_sha256": SHELL_PREPARE_SHA, "db_handoff_sha256": HANDOFF_SHA})
        compile_env = environment(prefix, output)
        fixture_root = Path(__file__).parent / "fixtures"
        executables = {}
        for name, source, cpp, library in (
            ("c", "native-db-consumer.c", False, "db"),
            ("cpp", "native-db-consumer.cpp", True, "db_cxx"),
            ("compat185", "native-db-185.c", False, "db"),
            ("process", "db-native-driver-process.c", False, None),
        ):
            fixture = fixture_root / source
            identities[str(fixture)] = digest(fixture)
            executable = runtime / "usr/bin" / ("db-proof-" + name + ".exe")
            if executable.exists():
                raise ContractError("Driver fixture name collides with an existing binary")
            command = [prefix / ("bin/g++.exe" if cpp else "bin/gcc.exe"), "-O2", "-g", "-Werror",
                       "-fstack-protector-strong", "-I" + str(stage / "usr/include"), fixture,
                       "-L" + str(stage / "usr/lib"), "-Wl,--no-insert-timestamp", "-o", executable]
            if library:
                command.append("-l" + library)
            row = observe(command, output, compile_env, output, "compile-" + name, observer, 120)
            report["commands"]["compile-" + name] = row
            if not row["process"]["passed"]:
                raise ContractError(f"New runtime fixture compilation failed: {name}")
            executables[name] = executable
            additions[executable.relative_to(runtime).as_posix()] = {
                "sha256": digest(executable), "size": executable.stat().st_size}
        env = environment(prefix, output)
        env["PATH"] = os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
        env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(runtime / "tmp")
        report["runtime_path"] = env["PATH"]
        report["pe"] = [arm64_pe(runtime / name) for name in (
            "usr/bin/sh.exe", "usr/bin/rm.exe", "usr/bin/mkdir.exe", "usr/bin/msys-2.0.dll",
            "usr/bin/msys-db-6.2.dll", "usr/bin/msys-db_cxx-6.2.dll")]
        for name, marker in (("c", b"DB C PASS:"), ("compat185", b"DB 185 PASS:"),
                             ("process", b"DB native driver PASS:")):
            cwd = output / ("work-" + name)
            cwd.mkdir()
            row = observe([sys.executable, "-I", observer / "native-target-exec.py", executables[name]],
                          cwd, env, output, name, observer, 60)
            report["commands"][name] = row
            if name != "process":
                require_exit(row, executables[name])
            native = row["evidence"]["native_target_exits"]
            if (not row["process"]["passed"] or not native or any(event["raw_exit"] != 0 for event in native)
                    or marker not in (output / (name + ".log")).read_bytes()):
                raise ContractError(f"New-cohort {name} behavior failed; raw child evidence retained")
            if name == "process":
                expected_names = {"sh.exe", "rm.exe", "mkdir.exe", executables[name].name}
                if not expected_names <= {Path(event["executable"]).name for event in native}:
                    raise ContractError("Native system preflight lacks the real shell/coreutils execution coverage")
        cpp_work = output / "work-cpp"
        cpp_work.mkdir()
        expected = {name: {"path": str(runtime / "usr/bin" / name), "sha256": digest(runtime / "usr/bin" / name)}
                    for name in ("msys-db_cxx-6.2.dll", "msys-2.0.dll")}
        held_cpp(executables["cpp"], cpp_work, env, output, observer, expected, report)
        final_files = inventory(runtime)
        if final_files != {**files, **additions}:
            raise ContractError("Native composition changed beyond the exact DB DLL/fixture additions")
        write_json(output / "runtime.manifest.json", {"files": final_files, "prefix": str(runtime),
                   "directories": directory_names(runtime), "required_runtime_directories": ["tmp"],
                   "runtime_sha256": D70_SHA, "db_handoff_sha256": HANDOFF_SHA,
                   "scope": "New-cohort native DB/process preflight only; no full Bash/package admission"})
        report["runtime_manifest"] = {"path": str(output / "runtime.manifest.json"),
                                      "sha256": digest(output / "runtime.manifest.json")}
        report["status"] = "private-native-db-d70-shell-process-api-preflight-passed"
    except (OSError, ContractError) as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            if inventory(args.shell_root) != files or directory_names(args.shell_root) != directories:
                raise ContractError("Owner-frozen shell inputs changed")
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("Receipt, helper or source identity changed")
            verify_tree(prefix, compiler_receipt)
            verify_tree(stage, build_receipt)
            verify_driver(observer)
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update(status="failed", inputs_unchanged=False, integrity_error=str(error))
            raise
        finally:
            report["input_identities"] = identities
            write_json(output / "result.json", report)
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
