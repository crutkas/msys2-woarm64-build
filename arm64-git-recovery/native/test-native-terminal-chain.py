"""Observed static/shared API, owned-PTY and exact loaded-module proofs."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

from bounded_process import run
from native_job_runner import noninteractive_error_mode, run_observed
from readline_chain_inputs import ROOT, HERE, PARENT, SEALS, fresh, sealed
from sources import ContractError, digest, verify_tree
from ssh_bootstrap import require_memory, write_json

build = importlib.import_module("build-readline-chain")


def process_modules(pid, expected_image, expected_modules):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    kernel.K32GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    kernel.K32GetModuleFileNameExW.restype = W.DWORD

    class Machine(C.Structure):
        _fields_ = [("machine", W.WORD), ("reserved", W.WORD), ("attributes", W.DWORD)]

    kernel.GetProcessInformation.argtypes = [W.HANDLE, C.c_int, W.LPVOID, W.DWORD]
    handle = kernel.OpenProcess(0x1410, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        created, ended, kt, ut = (W.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, *map(C.byref, (created, ended, kt, ut))):
            raise C.WinError(C.get_last_error())
        image, size, machine = C.create_unicode_buffer(32768), W.DWORD(32768), Machine()
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, C.byref(size)):
            raise C.WinError(C.get_last_error())
        if not kernel.GetProcessInformation(handle, 9, C.byref(machine), C.sizeof(machine)):
            raise C.WinError(C.get_last_error())
        if Path(image.value).resolve() != expected_image.resolve() or machine.machine != 0xAA64:
            raise ContractError("Wrong native terminal process image or machine")
        modules, needed = (W.HMODULE * 512)(), W.DWORD()
        if not kernel.K32EnumProcessModulesEx(handle, modules, C.sizeof(modules), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if needed.value > C.sizeof(modules):
            raise ContractError("Module inventory exceeded explicit capacity")
        rows = []
        for module in modules[:needed.value // C.sizeof(W.HMODULE)]:
            path = C.create_unicode_buffer(32768)
            if not kernel.K32GetModuleFileNameExW(handle, module, path, len(path)):
                raise C.WinError(C.get_last_error())
            file = Path(path.value)
            rows.append({"name": file.name, "path": str(file), "sha256": digest(file)})
        indexed = {r["name"].lower(): r for r in rows}
        for name, expected in expected_modules.items():
            actual = indexed.get(name.lower())
            if not actual or Path(actual["path"]).resolve() != Path(expected["path"]).resolve() or actual["sha256"] != expected["sha256"]:
                raise ContractError(f"Wrong loaded terminal-library module: {name}")
        for row in rows:
            if row["name"].lower().startswith("msys-") and Path(row["path"]).parent.resolve() != expected_image.parent.resolve():
                raise ContractError(f"Foreign MSYS runtime module loaded: {row['path']}")
        return {"pid": pid, "creation_filetime": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                "image": image.value, "machine": machine.machine, "attributes": machine.attributes,
                "modules": rows}
    finally:
        kernel.CloseHandle(handle)


def worker(output):
    contract = json.loads((output / "proof-inputs.json").read_text())
    binaries = output / "runtime/usr/bin"
    runner, executable = binaries / "editor-pty.exe", binaries / "probe.exe"
    env = build.environment(output, 1)
    env.update(PATH=str(binaries) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TERM="xterm-256color", LC_ALL="C.UTF-8",
               TERMINFO=str(output / "runtime/usr/share/terminfo"))
    if contract["package"] == "readline":
        env["INPUTRC"] = str(output / "inputrc")
    report = {"passed": False}

    def observe(parent_pid):
        ready = output / "editor-ready.json"
        deadline = time.monotonic() + 25
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not ready.exists():
            raise ContractError("Owned native PTY did not reach its readiness marker")
        child = json.loads(ready.read_text())
        report["runner_identity"] = process_modules(parent_pid, runner, {
            "msys-2.0.dll": contract["required_modules"]["msys-2.0.dll"]})
        report["target_identity"] = process_modules(child["windows_pid"], executable, contract["required_modules"])
        if contract["linkage"] == "static":
            prefixes = ("msys-ncurses", "msys-panel", "msys-form", "msys-menu", "msys-tic",
                        "msys-readline", "msys-history", "msys-edit")
            if any(row["name"].lower().startswith(prefixes) for row in report["target_identity"]["modules"]):
                raise ContractError("Static terminal proof unexpectedly loaded a terminal-library DLL")
        write_json(output / "loaded-modules.json", report)
        (output / "continue").write_bytes(b"go\n")

    try:
        with noninteractive_error_mode(), (output / "runner.log").open("xb") as log:
            report["process"] = run([runner, executable, output / "api-result.json", contract["pty_mode"]],
                                    cwd=output, env=env, log=log, timeout=90, on_started=observe)
        report["api"] = json.loads((output / "api-result.json").read_text())
        report["passed"] = report["process"]["passed"] and report["api"]["passed"] is True
        if contract["package"] == "libedit":
            prompt_bytes = b"\x1b[31m\xe4\xb8\xad\x1b[0m chain-ready> "
            report["colored_cjk_prompt_rendered"] = prompt_bytes in (output / "pty-output.bin").read_bytes()
            report["passed"] = report["passed"] and report["colored_cjk_prompt_rendered"]
        if not report["passed"]:
            raise ContractError("Native terminal API/PTY case failed")
    finally:
        write_json(output / "worker-result.json", report)


def proof(args):
    if args.debug_refresh and (args.package != "libedit-cells" or args.linkage != "static"):
        raise ContractError("DEBUG_REFRESH is only an additional static display-cell regression scope")
    stage = ROOT / args.stage
    stage_manifest = stage.parent / "stage.inventory.json"
    verify_tree(stage, stage_manifest)
    record = json.loads(stage_manifest.read_text())
    if record["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Terminal stage cohort mismatch")
    ncurses = ROOT / args.ncurses
    verify_tree(ncurses, ncurses.parent / "stage.inventory.json")
    if json.loads((ncurses.parent / "stage.inventory.json").read_text())["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Ncurses dependency cohort mismatch")
    output = ROOT / args.output
    fresh(output)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits"):
        (output / name).mkdir()
    require_memory()
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    env = build.environment(output, 1)
    binaries = output / "runtime/usr/bin"
    binaries.mkdir(parents=True)
    modules = {}
    for provider in (build.COMPILER / "bin", ncurses / "usr/bin", stage / "usr/bin"):
        for file in provider.glob("msys-*.dll"):
            destination = binaries / file.name
            if destination.exists() and digest(destination) != digest(file):
                raise ContractError(f"Conflicting private DLL provider: {file.name}")
            shutil.copyfile(file, destination)
            modules[file.name] = {"path": str(destination), "sha256": digest(file)}
    sealed(binaries / "msys-2.0.dll", build.RUNTIME_SHA)
    terminfo = output / "runtime/usr/share/terminfo/78"
    terminfo.mkdir(parents=True)
    shutil.copyfile(ncurses / "usr/share/terminfo/78/xterm-256color", terminfo / "xterm-256color")
    if args.package == "readline":
        shutil.copyfile(stage / "etc/inputrc", output / "inputrc")
    static = args.linkage == "static"
    flags = ["-O2", "-g", "-Werror", "-fstack-protector-strong",
             "-I" + str(ncurses / "usr/include/ncursesw"), "-I" + str(stage / "usr/include"),
             "-L" + str(ncurses / "usr/lib"), "-L" + str(stage / "usr/lib"),
             "-Wl,--no-insert-timestamp"]
    if static:
        flags.append("-DNCURSES_STATIC")
    extension = ".a" if static else ".dll.a"
    compiler = build.COMPILER / "bin/gcc.exe"
    if args.package == "ncurses":
        compiler = build.COMPILER / "bin/g++.exe"
        source = HERE / "fixtures/native-curses-cpp.cc"
        libraries = [ncurses / f"usr/lib/lib{name}w{extension}"
                     for name in ("ncurses++", "form", "menu", "panel", "ncurses")]
        required = ["msys-2.0.dll"] + ([] if static else ["msys-ncurses++w6.dll", "msys-ncursesw6.dll"])
    elif args.package == "libedit-cells":
        if not static:
            raise ContractError("Private display-cell regression requires the real static archive")
        private_root = ROOT / "libedit-01"
        verify_tree(private_root / "source", private_root / "working-source.inventory.json")
        flags += ["-I" + str(private_root / "build"),
                  "-I" + str(private_root / "source/src"), "-I" + str(private_root / "build/src")]
        if args.debug_refresh:
            flags.append("-DDEBUG_REFRESH")
        source = HERE / "fixtures/native-libedit-display-probe.c"
        libraries = [stage / "usr/lib/libedit.a", ncurses / "usr/lib/libncursesw.a"]
        required = ["msys-2.0.dll"]
    elif args.package == "history":
        source = HERE / "fixtures/native-history-api.c"
        libraries = [stage / f"usr/lib/libhistory{extension}"]
        required = ["msys-2.0.dll"] + ([] if static else ["msys-history8.dll"])
    else:
        source = HERE / "fixtures/native-terminal-library.c"
        if args.package == "readline":
            flags.append("-DPROBE_READLINE")
            libraries = [stage / f"usr/lib/libreadline{extension}", stage / f"usr/lib/libhistory{extension}"]
            required = ["msys-2.0.dll"] + ([] if static else ["msys-readline8.dll", "msys-ncursesw6.dll"])
        else:
            libraries = [stage / f"usr/lib/libedit{extension}"]
            required = ["msys-2.0.dll"] + ([] if static else ["msys-edit-0.dll", "msys-ncursesw6.dll"])
        libraries.append(ncurses / f"usr/lib/libncursesw{extension}")
    fixture_inputs = [source, HERE / "fixtures/native-editor-pty.c"]
    if args.package == "libedit-cells":
        fixture_inputs.append(HERE / "patches/libedit-20240808-display-cells-regression.c")
    fixture_sources = {}
    for file in fixture_inputs:
        relative = file.relative_to(HERE)
        destination = output / "recipe-sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        before_sha = digest(file)
        shutil.copyfile(file, destination)
        if digest(destination) != before_sha or digest(file) != before_sha:
            raise ContractError("Native fixture source changed during snapshot")
        fixture_sources[relative.as_posix()] = {"source": str(file), "sha256": before_sha}
    source = output / "recipe-sources" / source.relative_to(HERE)
    commands = [
        [build.COMPILER / "bin/gcc.exe", "-O2", "-g", "-Werror", "-fstack-protector-strong",
         output / "recipe-sources/fixtures/native-editor-pty.c", "-o", binaries / "editor-pty.exe", "-lutil"],
    ]
    extra_objects = []
    if args.debug_refresh:
        extra_objects = [output / "debug-refresh.o"]
        commands.append([compiler, *flags, "-DHAVE_CONFIG_H", "-c",
                         ROOT / "libedit-01/source/src/refresh.c", "-o", extra_objects[0]])
    commands.append([compiler, *flags, source, "-o", binaries / "probe.exe", *extra_objects, *libraries])
    report = {"schema": 1, "package": args.package, "linkage": args.linkage,
              "pid": os.getpid(), "creation_filetime": build.current_birth(),
              "stage_manifest_sha256": digest(stage_manifest),
              "ncurses_manifest_sha256": digest(ncurses.parent / "stage.inventory.json"),
              "compiler_receipt_sha256": SEALS["compiler"], "jobs": 1,
              "pty_mode": {"ncurses": "curses", "history": "history", "libedit": "libedit",
                           "libedit-cells": "curses"}.get(args.package, "library"),
              "debug_refresh": args.debug_refresh,
              "fixture_sources": fixture_sources,
              "required_modules": {name: modules[name] for name in required},
              "compile_commands": [list(map(str, cmd)) for cmd in commands],
              "status": "launched", "scope": "Owned PTY only; no user console/config/account/device interaction"}
    write_json(output / "proof-inputs.json", report)
    print(json.dumps(report), flush=True)
    try:
        for index, command in enumerate(commands):
            result = run_observed(command, cwd=output, env=env, log_path=output / f"compile-{index}.log",
                                  result_path=output / f"compile-{index}.json", relay_records=output / "native-exits",
                                  timeout=120, driver_prefix=build.OBSERVER)
            if not result["passed"]:
                raise ContractError("Protected native PTY/API fixture compilation failed")
        worker_command = [sys.executable, "-B", Path(__file__).resolve(), "--worker", str(output)]
        report["process"] = run_observed(worker_command, cwd=output, env=env,
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=120, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native observed terminal proof failed")
        report["api"] = json.loads((output / "worker-result.json").read_text())
        if report["api"]["passed"] is not True:
            raise ContractError("Native API/PTY result failed")
        report["status"] = "passed-native-static-shared-api-pty-loaded-modules"
        report["loaded_modules_sha256"] = digest(output / "loaded-modules.json")
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            verify_tree(stage, stage_manifest)
            verify_tree(ncurses, ncurses.parent / "stage.inventory.json")
            verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
        except (ContractError, OSError) as error:
            report.update(status="failed", integrity_error=str(error))
            raise
        finally:
            write_json(output / "result.json", report)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--package", required=True, choices=("ncurses", "readline", "history", "libedit", "libedit-cells"))
        parser.add_argument("--stage", required=True)
        parser.add_argument("--ncurses", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--linkage", required=True, choices=("static", "shared"))
        parser.add_argument("--debug-refresh", action="store_true")
        proof(parser.parse_args())
