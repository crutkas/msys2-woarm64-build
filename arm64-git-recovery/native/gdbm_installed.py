"""Independent native GDBM/NDBM APIs, exact modules, and moved-data replay."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

from db_channel_checks import own_birth
from db_native_checks import environment, require_exit
from db_package import pe_metadata
from gdbm_recovery import RUNTIME_SHA, isolated_observe
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json
from ssh_crypt_consumer import inspect_process, validate_loaded, matching_relay


def closure(executable, dll_sources):
    pending = [executable]
    required = {}
    while pending:
        path = pending.pop()
        for name in pe_metadata(path.read_bytes())["imports"]:
            key = name.lower()
            if key in required:
                continue
            if key in dll_sources:
                source = dll_sources[key]
                pe_metadata(source.read_bytes())
                required[key] = {"path": str(source), "sha256": digest(source)}
                pending.append(source)
            elif not (Path(os.environ["SystemRoot"]) / "System32" / name).is_file() and not key.startswith(("api-ms-win-", "ext-ms-win-")):
                raise ContractError(f"Unresolved native API import: {name}")
    return required


def run_held(root, output, runtime, executable, existing=False):
    output.mkdir()
    (output / "native-exits").mkdir()
    dlls = {path.name.lower(): path for path in (runtime / "usr/bin").glob("*.dll")}
    required = closure(executable, dlls)
    env = environment(root / "compiler", output)
    env["PATH"] = os.pathsep.join((str(runtime / "usr/bin"), str(Path(os.environ["SystemRoot"]) / "System32")))
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    ready, release = output / "ready", output / "release"
    stop = threading.Event()
    observed = {}

    def monitor():
        try:
            deadline = time.monotonic() + 30
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    text = ready.read_text()
                except FileNotFoundError:
                    time.sleep(0.05)
                    continue
                if not text.endswith("\n"):
                    time.sleep(0.05)
                    continue
                fields = text.split()
                if len(fields) != 2 or any(not field.isdecimal() for field in fields):
                    raise ContractError("Malformed native PID/FILETIME handshake")
                pid, birth = map(int, fields)
                identity = inspect_process(pid, required)
                validate_loaded(identity, pid, executable, required)
                if identity["creation_filetime"] != birth:
                    raise ContractError("Module observation mismatches the native process generation")
                observed["identity"] = identity
                write_json(output / "loaded-modules.json", identity)
                release.write_bytes(b"go\n")
                return
            raise ContractError("Native GDBM API did not reach its bounded module handshake")
        except (OSError, ContractError, ValueError) as error:
            observed["error"] = str(error)

    command = [sys.executable, "-I", root / "observer/native-target-exec.py", executable, ready, release]
    if existing:
        command.append("--existing")
    watcher = threading.Thread(target=monitor, name="gdbm-native-module-proof", daemon=True)
    watcher.start()
    try:
        row = isolated_observe(root, output, "api", command, runtime / "work", env, 150)
    finally:
        stop.set()
        watcher.join(timeout=5)
    report = {"process": row, "module_observation": observed, "required_dlls": required}
    if watcher.is_alive() or "error" in observed or "identity" not in observed:
        write_json(output / "result.json", report)
        raise ContractError("Independent native GDBM module proof failed")
    raw = require_exit(row, executable)
    if raw["pid"] != observed["identity"]["pid"] or raw["created"] != observed["identity"]["creation_filetime"]:
        raise ContractError("Native exit and loaded modules identify different generations")
    relays = row["evidence"]["runtime_exit_relays"]
    if len(relays) != 1 or digest(relays[0]["path"]) != relays[0]["sha256"]:
        raise ContractError("The generation observer did not bind exactly one intact API relay")
    report["matching_relay"] = matching_relay(Path(relays[0]["path"]).parent,
                                              observed["identity"], digest(executable))
    report["raw_exit"] = raw
    write_json(output / "result.json", report)
    if not row["process"]["passed"]:
        raise ContractError("Native GDBM API observer failed")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--static", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01") or Path(args.run_name).name != args.run_name or args.run_name in (".", ".."):
        raise ContractError("Explicit owned GDBM API output required")
    output = root / args.run_name
    output.mkdir()
    stage = (args.stage or root / "stage").resolve()
    if not stage.is_relative_to(root):
        raise ContractError("Installed API stage must be an owned GDBM output")
    before = inventory(stage)
    if not all((stage / path).is_file() for path in (
        "usr/include/gdbm.h", "usr/include/gdbm/ndbm.h",
        "usr/lib/libgdbm.dll.a", "usr/lib/libgdbm_compat.dll.a",
        "usr/lib/libgdbm.a", "usr/lib/libgdbm_compat.a",
    )):
        raise ContractError("Real installed GDBM and NDBM development payload required")
    fixture = Path(__file__).parent / "fixtures/native-gdbm-consumer.c"
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    executable = output / "gdbm-api.exe"
    libraries = ([stage / "usr/lib/libgdbm_compat.a", stage / "usr/lib/libgdbm.a",
                  "-L" + str(root / "dependencies/usr/lib"), "-lintl"] if args.static else
                 ["-L" + str(stage / "usr/lib"), "-lgdbm_compat", "-lgdbm"])
    command = [root / "compiler/bin/gcc.exe", "-O2", "-g", "-Werror", "-fstack-protector-strong",
               "-I" + str(stage / "usr/include"), fixture, *libraries,
               "-Wl,--no-insert-timestamp", "-o", executable]
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "jobs": 1, "free_gib": require_memory(), "stage_files": before,
        "compiler_sha256": digest(root / "compiler/bin/gcc.exe"),
        "source_sha256": digest(fixture), "command": list(map(str, command)),
        "linkage": "static-gdbm" if args.static else "shared-gdbm", "stage": str(stage)})
    compiled = isolated_observe(root, output, "compile", command, output, env, 120)
    if not compiled["process"]["passed"]:
        raise ContractError("Installed-header GDBM API consumer did not compile")
    sources = {path.name.lower(): path for path in (root / "build-runtime/usr/bin").glob("*.dll")}
    sources.update({path.name.lower(): path for path in (stage / "usr/bin").glob("*.dll")})
    needed = closure(executable, sources)
    if needed.get("msys-2.0.dll", {}).get("sha256") != RUNTIME_SHA:
        raise ContractError("Installed API is not bound to the requested native907 runtime")
    runtime = output / "installed-runtime"
    (runtime / "usr/bin").mkdir(parents=True)
    (runtime / "work").mkdir()
    (runtime / "tmp").mkdir()
    (runtime / "etc").mkdir()
    shutil.copy2(root / "build-runtime/etc/fstab", runtime / "etc/fstab")
    for name, row in needed.items():
        destination = runtime / "usr/bin" / name
        shutil.copy2(row["path"], destination)
        if digest(destination) != row["sha256"] or digest(row["path"]) != row["sha256"]:
            raise ContractError("Native API DLL copy differs")
    first = run_held(root, output / "installed", runtime, executable)
    runtime_files = inventory(runtime)
    moved = output / "moved-runtime"
    runtime.rename(moved)
    if runtime.exists() or inventory(moved) != runtime_files:
        raise ContractError("The actual runtime/database move was not exact")
    second = run_held(root, output / "moved", moved, executable, existing=True)
    if inventory(stage) != before:
        raise ContractError("Installed GDBM stage changed during independent APIs")
    write_json(output / "result.json", {"schema": 1, "passed": True, "compile": compiled,
        "linkage": "static-gdbm" if args.static else "shared-gdbm", "stage": str(stage),
        "installed": first, "moved": second, "source_sha256": digest(fixture),
        "client": {"path": str(executable), "sha256": digest(executable), **pe_metadata(executable.read_bytes())},
        "stage_files": before, "original_runtime_path_absent": not runtime.exists(),
        "scope": "Native GDBM and NDBM CRUD, binary data, iteration, persistent reopen, exact907 modules, real moved-data replay; no provider admission"})
    print("Native installed and moved-root GDBM/NDBM APIs and exact modules passed", flush=True)


if __name__ == "__main__":
    main()
