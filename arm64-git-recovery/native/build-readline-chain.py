"""Build full native ncurses/readline/libedit with exact scoped inputs."""

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys

from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_msys_jmp_headers
from native_job_runner import noninteractive_error_mode, run_observed, verify_driver
from readline_chain_inputs import ROOT, PARENT, HERE, SEALS, fresh, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json

COMPILER = PARENT / "tc-cpp-guard-01"
COMPILER_RECEIPT = PARENT / "tc-cpp-guard-01.copy.json"
BOOTSTRAP = ROOT / "bootstrap/msys64"
BOOTSTRAP_RECEIPT = ROOT / "bootstrap/msys64.copy.json"
OBSERVER = PARENT / "native-test-driver-02"
RUNTIME_SHA = "1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16"
CC1_SHA = "b8046275497c4e8f4d056530ef2e956d1b7672a0e5eb15ad56fde5bf44e76b0a"
CC1PLUS_SHA = "f003aec1b083e8d54ab93b6d1d0d901cd659708f5fc95279dad4f0f24feb3c6c"
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"


def environment(output, jobs):
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    if not env.get("PATHEXT"):
        raise ContractError("A real Windows PATHEXT is required")
    env.update({
        "PATH": os.pathsep.join(map(str, (COMPILER / "bin", BOOTSTRAP / "usr/bin",
                                         Path(os.environ["SystemRoot"]) / "System32"))),
        "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
        "TMP": str(output / "temp"), "TEMP": str(output / "temp"), "TMPDIR": str(output / "temp"),
        "XDG_CACHE_HOME": str(output / "cache"), "CCACHE_DISABLE": "1",
        "MAKEFLAGS": f"-j{jobs}", "MFLAGS": f"-j{jobs}", "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "CMAKE_BUILD_PARALLEL_LEVEL": str(jobs),
        "WOARM64_NATIVE_ARG_CONVERSION": "none", "WOARM64_NATIVE_PYTHON": sys.executable,
        "WOARM64_NATIVE_PYTHON_SHA256": PYTHON_SHA, "WOARM64_NATIVE_TEST_ROOT": str(ROOT),
        "WOARM64_NATIVE_EXIT_DIR": str(output / "native-exits"),
        "WOARM64_NATIVE_DRIVER_ROOT": str(OBSERVER),
    })
    return env


def current_birth():
    from ctypes import wintypes as W
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    values = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *map(ctypes.byref, values)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime


def required_files(package):
    if package == "ncurses":
        return [*[f"usr/lib/lib{name}w{suffix}" for name in ("ncurses", "ncurses++", "panel", "menu", "form", "tic")
                  for suffix in (".a", ".dll.a")],
                *[f"usr/bin/msys-{name}w6.dll" for name in ("ncurses", "ncurses++", "panel", "menu", "form", "tic")],
                "usr/bin/tic.exe", "usr/bin/infocmp.exe", "usr/include/ncursesw/curses.h",
                "usr/share/terminfo/78/xterm-256color"]
    if package == "readline":
        return [*[f"usr/lib/lib{name}{suffix}" for name in ("readline", "history") for suffix in (".a", ".dll.a")],
                "usr/bin/msys-readline8.dll", "usr/bin/msys-history8.dll", "usr/include/readline/readline.h",
                "usr/include/readline/history.h", "etc/inputrc"]
    return ["usr/lib/libedit.a", "usr/lib/libedit.dll.a", "usr/bin/msys-edit-0.dll",
            "usr/include/histedit.h", "usr/include/editline/readline.h", "usr/lib/pkgconfig/libedit.pc"]


def readline_multibyte(config):
    text = re.sub(r"/\*.*?\*/", "", config, flags=re.S)
    defines = dict(re.findall(r"^\s*#define\s+(\w+)\s+([^\n]+)$", text, flags=re.M))
    required = ("HAVE_WCTYPE_H", "HAVE_WCHAR_H", "HAVE_LOCALE_H", "HAVE_ISWCTYPE",
                "HAVE_ISWLOWER", "HAVE_ISWUPPER", "HAVE_MBSRTOWCS", "HAVE_MBRTOWC",
                "HAVE_MBRLEN", "HAVE_WCHAR_T", "HAVE_WCWIDTH")
    if "NO_MULTIBYTE_SUPPORT" in defines or any(defines.get(key, "").strip() != "1" for key in required):
        raise ContractError("Readline's actual HANDLE_MULTIBYTE prerequisites are not enabled")
    return {"HANDLE_MULTIBYTE": True, "required_defines": list(required)}


def build(args):
    print(json.dumps({"phase": "input-preflight", "pid": os.getpid(),
                      "creation_filetime": current_birth(), "command": [sys.executable, *sys.argv]}), flush=True)
    source = ROOT / "sources" / args.package / "source"
    source_manifest = source.with_name("source.prepare.json")
    output = ROOT / args.output
    fresh(output)
    memory = require_memory()
    sealed(COMPILER_RECEIPT, SEALS["compiler"])
    sealed(source_manifest, SEALS[args.package])
    sealed(sys.executable, PYTHON_SHA)
    verify_tree(source, source_manifest)
    verify_tree(COMPILER, COMPILER_RECEIPT)
    producer = json.loads(COMPILER_RECEIPT.read_text())
    require_msys_ucontext_receipt(producer)
    if (producer["source_handoff_sha256"] != "18d32902652ef1142f4c5ddc0bf09ebea2185e9925be3d4c941efd8e3fe52a53"
            or producer["full_cpp_qualified"] is not False
            or producer["source_cpp_frontend_delta"]["qualification"]["matrix_runs"] != 7):
        raise ContractError("Scoped protected-C++ frontend producer contract differs")
    sealed(COMPILER / "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe", CC1_SHA)
    sealed(COMPILER / "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1plus.exe", CC1PLUS_SHA)
    sealed(COMPILER / "bin/msys-2.0.dll", RUNTIME_SHA)
    bootstrap = json.loads(BOOTSTRAP_RECEIPT.read_text())
    if (bootstrap["source_manifest_sha256"] != SEALS["bootstrap"]
            or bootstrap["complete_inventory_equality"] is not True or len(bootstrap["files"]) != 19265):
        raise ContractError("Private bootstrap not bound to authorized source")
    verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
    if directory_names(BOOTSTRAP) != bootstrap["directories"]:
        raise ContractError("Private bootstrap directory inventory differs")
    observer_manifest = verify_driver(OBSERVER)
    sealed(observer_manifest, SEALS["observer"])
    dependency = ROOT / args.dependency if args.dependency else ROOT / "no-dependency"
    dependency_manifest = dependency.parent / "stage.inventory.json"
    if args.package != "ncurses":
        verify_tree(dependency, dependency_manifest)
        dependency_record = json.loads(dependency_manifest.read_text())
        if dependency_record["compiler_receipt_sha256"] != SEALS["compiler"]:
            raise ContractError("Ncurses stage uses a different consumer cohort")
    script = HERE / "build-readline-chain.sh"
    if b"\r" in script.read_bytes():
        raise ContractError("Shell driver requires LF")
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits"):
        (output / name).mkdir()
    recipes = output / "recipes"
    recipes.mkdir()
    recipe_files = [script, HERE / "build-readline-chain.py"]
    if args.package == "ncurses":
        recipe_files += [HERE / "finish-ncurses-chain.sh", HERE / "ncurses-static-cxx.mk",
                         HERE / "record-ncurses-package-link.py", *sorted((HERE / "patches").glob("ncurses-*.patch"))]
    elif args.package == "readline":
        recipe_files.append(HERE / "patches/readline-8.3-history-example-link.patch")
    else:
        recipe_files += [HERE / "patches/libedit-20240808-read-ioctl.patch",
                         HERE / "patches/libedit-20240808-display-cells.patch",
                         HERE / "patches/libedit-20240808-display-cells.provenance.json",
                         HERE / "libedit-static.mk"]
    for file in recipe_files:
        shutil.copyfile(file, recipes / file.name)
    env = environment(output, args.jobs)
    command = [BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               args.package, source, COMPILER, output, str(args.jobs), dependency]
    report = {
        "schema": 1, "status": "launched", "package": args.package, "jobs": args.jobs,
        "command": list(map(str, command)), "launcher_command": [sys.executable, *sys.argv],
        "launcher_pid": os.getpid(), "launcher_creation_filetime": current_birth(),
        "launched_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest_sha256": SEALS[args.package], "compiler_receipt_sha256": SEALS["compiler"],
        "cpp_scope": producer["source_cpp_frontend_delta"], "full_cpp_qualified": False,
        "runtime_sha256": RUNTIME_SHA, "bootstrap_receipt_sha256": digest(BOOTSTRAP_RECEIPT),
        "observer_manifest_sha256": SEALS["observer"], "driver_sha256": digest(script),
        "minimum_free_gib_before_launch": memory,
        "log": str(output / "observed.log"), "native_job_result": str(output / "native-job.json"),
        "recipe_snapshot": inventory(recipes),
    }
    write_json(output / "launch.json", report)
    print(json.dumps(report), flush=True)
    env["WOARM64_CHAIN_LAUNCH_SHA256"] = digest(output / "launch.json")
    try:
        with noninteractive_error_mode():
            report["support"] = support_identities(COMPILER / "bin/gcc.exe", COMPILER, env)
            report["jump_headers"] = verify_msys_jmp_headers(COMPILER / "bin/gcc.exe", env)
            report["minimum_free_gib_before_launch"] = min(memory, require_memory())
            report["process"] = run_observed(
                command, cwd=ROOT, env=env, log_path=output / "observed.log",
                result_path=output / "native-job.json", relay_records=output / "native-exits",
                timeout=10800, driver_prefix=OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native chain build/check failed; complete evidence retained")
        if args.package == "readline":
            report["multibyte_configuration"] = {
                linkage: readline_multibyte((output / "build" / linkage / "config.h").read_text())
                for linkage in ("static", "shared")
            }
        files = inventory(output / "stage")
        missing = [p for p in required_files(args.package) if p not in files]
        if missing:
            raise ContractError(f"Required full-profile outputs missing: {missing}")
        package_gate = json.loads((output / "package-link-gate.json").read_text()) if args.package == "ncurses" else None
        report["package_link_gate"] = package_gate
        write_json(output / "stage.inventory.json", {
            "schema": 1, "package": args.package, "compiler_receipt_sha256": SEALS["compiler"],
            "runtime_sha256": RUNTIME_SHA, "files": files,
            "status": "native-built-upstream-checks-not-yet-api-pty-admitted",
            "package_link_gate": package_gate,
        })
        report["status"] = "native-built-upstream-checks-not-yet-api-pty-admitted"
        report["stage_manifest_sha256"] = digest(output / "stage.inventory.json")
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            verify_tree(source, source_manifest)
            verify_tree(COMPILER, COMPILER_RECEIPT)
            verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
            verify_driver(OBSERVER)
            report["sealed_inputs_unchanged"] = True
        finally:
            write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "output": str(output)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=("ncurses", "readline", "libedit"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--jobs", required=True, type=int, choices=(1, 2))
    parser.add_argument("--dependency")
    build(parser.parse_args())
