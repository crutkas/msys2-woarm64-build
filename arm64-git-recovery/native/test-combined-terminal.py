"""Execute admitted AA64 terminal libraries on the sealed combined native runtime."""

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

from bounded_process import run
from native_job_runner import noninteractive_error_mode, run_observed, verify_driver
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json

inputs = importlib.import_module("prepare-combined-terminal")
ROOT, HERE = inputs.ROOT, inputs.HERE
module_check = importlib.import_module("test-native-terminal-chain").process_modules
birth = importlib.import_module("build-readline-chain").current_birth
cpu_budget = importlib.import_module("build-bash-nls").cpu_budget
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"


def environment(output, native_only=False):
    windows = Path(os.environ["SystemRoot"]) / "System32"
    binaries = output / "runtime/usr/bin" if native_only else ROOT / "compiler/bin"
    if not os.environ.get("PATHEXT"):
        raise ContractError("Real Windows PATHEXT required")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update(PATH=str(binaries) + os.pathsep + str(windows), HOME=str(output / "home"),
               USERPROFILE=str(output / "home"), TMP=str(output / "temp"), TEMP=str(output / "temp"),
               TMPDIR=str(output / "temp"), TERM="xterm-256color", LC_ALL="C.UTF-8",
               TERMINFO=str(output / "runtime/usr/share/terminfo"), INPUTRC=str(output / "runtime/etc/inputrc"),
               MAKEFLAGS="-j1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               WOARM64_NATIVE_ARG_CONVERSION="none", WOARM64_NATIVE_TEST_ROOT=str(ROOT),
               WOARM64_NATIVE_EXIT_DIR=str(output / "native-exits"),
               WOARM64_NATIVE_PYTHON=sys.executable, WOARM64_NATIVE_PYTHON_SHA256=PYTHON_SHA)
    return env


def verify_files(root, expected):
    if inventory(root) != expected:
        raise ContractError(f"Immutable validation input changed: {root}")


def worker(output):
    record = json.loads((output / "launch.json").read_text())
    binaries = output / "runtime/usr/bin"
    env = environment(output, True)
    report = {"passed": False}

    def observe(parent_pid):
        ready = output / "editor-ready.json"
        deadline = time.monotonic() + 25
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready.exists():
            raise ContractError("Owned AA64 terminal did not reach readiness")
        child = json.loads(ready.read_text())["windows_pid"]
        report["controller"] = module_check(parent_pid, Path(record["command"][0]), record["controller_modules"])
        report["editor"] = module_check(child, binaries / "probe.exe", record["required_modules"])
        for process in (report["controller"], report["editor"]):
            for row in process["modules"]:
                path = Path(row["path"])
                if path.is_relative_to(output) and path.suffix.lower() in (".exe", ".dll"):
                    row["pe"] = inputs.pe(path.read_bytes())
                elif not path.is_relative_to(Path(os.environ["SystemRoot"])):
                    raise ContractError(f"Unowned non-Windows loaded module: {path}")
        if record["linkage"] == "static" and any(row["name"].lower().startswith(
                ("msys-readline", "msys-history", "msys-ncurses", "msys-edit", "msys-form", "msys-panel", "msys-menu"))
                for row in report["editor"]["modules"]):
            raise ContractError("Static consumer unexpectedly loaded terminal-library DLL")
        write_json(output / "loaded-modules.json", report)
        (output / "continue").write_bytes(b"go\n")

    try:
        with noninteractive_error_mode(), (output / "controller.log").open("xb") as log:
            report["process"] = run(record["command"], cwd=output, env=env, log=log,
                                    timeout=210, on_started=observe, drain_grace=3)
        if not report["process"]["passed"]:
            raise ContractError("Native terminal/signals controller failed")
        report["api"] = json.loads((output / "api.json").read_text())
        if report["api"]["passed"] is not True:
            raise ContractError("Native terminal API assertions failed")
        if record["kind"] == "readline-signals":
            report["signal_controller"] = json.loads((output / "controller.json").read_text())
            if report["signal_controller"]["passed"] is not True:
                raise ContractError("PTY signal/termios assertions failed")
        if record["kind"] == "libedit" and b"\x1b[31m\xe4\xb8\xad\x1b[0m chain-ready> " not in (output / "pty-output.bin").read_bytes():
            raise ContractError("Colored wide-character libedit prompt was not rendered")
        report["transcript_sha256"] = digest(output / "pty-output.bin")
        report["passed"] = True
    finally:
        write_json(output / "worker-result.json", report)


def main(args):
    output = ROOT / args.output
    if output.exists() or not output.resolve().is_relative_to(ROOT):
        raise ContractError("Fresh owned proof output required")
    record = json.loads((ROOT / "inputs.json").read_text())
    inputs.sealed(inputs.HANDOFF, inputs.HANDOFF_SHA)
    inputs.sealed(sys.executable, PYTHON_SHA)
    verify_files(ROOT / "compiler", record["compiler_files"])
    verify_files(ROOT / "sdk", record["sdk_files"])
    inputs.sealed(verify_driver(ROOT / "observer"), inputs.OBSERVER_SHA)
    output.mkdir()
    for name in ("home", "temp", "native-exits", "sources"):
        (output / name).mkdir()
    shutil.copytree(ROOT / "runtime-payload", output / "runtime")
    binaries = output / "runtime/usr/bin"
    static = args.linkage == "static"
    extension = ".a" if static else ".dll.a"
    sdk = ROOT / "sdk/usr"
    flags = ["-O2", "-g", "-Werror", "-fstack-protector-strong", "-Wl,--no-insert-timestamp", "-Wl,-t",
             "-I" + str(sdk / "include"), "-I" + str(sdk / "include/ncursesw")]
    compiler = ROOT / "compiler/bin/gcc.exe"
    required = ["msys-2.0.dll"]
    commands = []
    if args.kind == "readline-signals":
        fixture = HERE / "fixtures/native-readline-signals.c"
        libraries = [sdk / ("lib/libreadline" + extension), sdk / ("lib/libncursesw" + extension)]
        if not static:
            required += ["msys-readline8.dll", "msys-ncursesw6.dll"]
    elif args.kind == "ncurses":
        compiler = ROOT / "compiler/bin/g++.exe"
        fixture = HERE / "fixtures/native-curses-cpp.cc"
        libraries = [sdk / f"lib/lib{name}w{extension}" for name in ("ncurses++", "form", "menu", "panel", "ncurses")]
        if not static:
            required += ["msys-ncurses++w6.dll", "msys-ncursesw6.dll"]
    elif args.kind == "history":
        fixture = HERE / "fixtures/native-history-api.c"
        libraries = [sdk / ("lib/libhistory" + extension)]
        if not static:
            required += ["msys-history8.dll"]
    else:
        fixture = HERE / "fixtures/native-terminal-library.c"
        libraries = [sdk / ("lib/libedit" + extension), sdk / ("lib/libncursesw" + extension)]
        if not static:
            required += ["msys-edit-0.dll", "msys-ncursesw6.dll"]
    if static:
        flags += ["-DNCURSES_STATIC"]
    snapshots = {}
    for file in (fixture, HERE / "fixtures/native-editor-pty.c"):
        target = output / "sources" / file.name
        shutil.copyfile(file, target)
        snapshots[file.name] = {"source": str(file), "sha256": digest(file)}
        inputs.sealed(target, snapshots[file.name]["sha256"])
    commands.append([compiler, *flags, output / "sources" / fixture.name, "-o", binaries / "probe.exe", *libraries, "-lutil"])
    if args.kind == "readline-signals":
        command = [binaries / "probe.exe", output / "api.json", args.signal_mode]
        controller_modules = required
    else:
        commands.append([ROOT / "compiler/bin/gcc.exe", *flags, output / "sources/native-editor-pty.c",
                         "-o", binaries / "editor-pty.exe", "-lutil"])
        mode = {"ncurses": "curses", "history": "history", "libedit": "libedit"}[args.kind]
        command = [binaries / "editor-pty.exe", binaries / "probe.exe", output / "api.json", mode]
        controller_modules = ["msys-2.0.dll"]
    modules = {name: {"path": str(binaries / name), "sha256": digest(binaries / name)} for name in required}
    report = {"schema": 1, "status": "launched", "kind": args.kind, "linkage": args.linkage,
              "signal_mode": args.signal_mode, "pid": os.getpid(), "creation_filetime": birth(),
              "input_receipt_sha256": digest(ROOT / "inputs.json"), "runtime_sha256": inputs.RUNTIME_SHA,
              "runtime_handoff_sha256": inputs.HANDOFF_SHA, "jobs": 1, "minimum_free_gib": require_memory(),
              "required_modules": modules, "controller_modules": {n: modules[n] for n in controller_modules},
              "fixture_sources": snapshots, "compile_commands": [list(map(str, c)) for c in commands],
              "bounded_helper_sha256": digest(HERE / "bounded_process.py"), "drain_grace_seconds": 3,
              "command": list(map(str, command)), "scope": "Additive combined-runtime compatibility; admitted library bytes unchanged; owned MSYS PTY, no desktop console"}
    write_json(output / "launch.json", report)
    print(json.dumps({"pid": report["pid"], "creation_filetime": report["creation_filetime"],
                      "kind": args.kind, "linkage": args.linkage, "signal_mode": args.signal_mode,
                      "command": report["command"], "log": str(output / "run/observed.log")}), flush=True)
    try:
        with cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            for index, compile_command in enumerate(commands):
                observation = output / f"compile-{index}"
                observation.mkdir()
                process = run_observed(compile_command, cwd=output, env=environment(output),
                                       log_path=observation / "observed.log", result_path=observation / "native-job.json",
                                       relay_records=output / "native-exits", timeout=120, driver_prefix=ROOT / "observer")
                if not process["passed"]:
                    raise ContractError("Combined-runtime fixture compilation failed")
                log = (observation / "observed.log").read_text(errors="replace").replace("\\", "/")
                if "ag-e138920f/tc-cpp-guard-01" in log or "/crt0.o" not in log or "/libmsys-2.0.a" not in log:
                    raise ContractError("Actual fixture link closure not established")
            report["fixture_pe"] = {p.name: {**inputs.pe(p.read_bytes()), "sha256": digest(p)}
                                    for p in binaries.glob("*.exe")}
            (output / "run").mkdir()
            report["process"] = run_observed([sys.executable, "-B", Path(__file__).resolve(), "--worker", output],
                                             cwd=output, env=environment(output, True), log_path=output / "run/observed.log",
                                             result_path=output / "run/native-job.json", relay_records=output / "native-exits",
                                             timeout=240, driver_prefix=ROOT / "observer")
        if not report["process"]["passed"]:
            raise ContractError("Combined-runtime native process/PTY observation failed")
        report["result"] = json.loads((output / "worker-result.json").read_text())
        if not report["result"]["passed"]:
            raise ContractError("Native terminal result failed")
        report["status"] = "passed-real-AA64-packages-on-combined-native-runtime"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            verify_files(ROOT / "sdk", record["sdk_files"])
            verify_files(ROOT / "compiler", record["compiler_files"])
            inputs.sealed(inputs.HANDOFF, inputs.HANDOFF_SHA)
        finally:
            write_json(output / "result.json", report)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--kind", choices=("readline-signals", "ncurses", "libedit", "history"), required=True)
        parser.add_argument("--linkage", choices=("static", "shared"), required=True)
        parser.add_argument("--signal-mode", choices=("tty", "kill"), default="tty")
        parser.add_argument("--output", required=True)
        main(parser.parse_args())
