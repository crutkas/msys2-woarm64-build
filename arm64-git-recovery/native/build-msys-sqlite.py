"""Run the full seven-split SQLite recipe with bounded observed native jobs."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import sys

from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory
from sqlite_build_inputs import SPLITS, TOOLS, extension_makefile, msys_path, recipe, tcl_config_view


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def process_identity():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *[ctypes.byref(t) for t in times]):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"pid": os.getpid(), "creation_filetime": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
            "command": sys.orig_argv}


def environment(root, output, jobs):
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if k in os.environ}
    env["PATH"] = os.pathsep.join(str(p) for p in (
        root / "compiler/bin", root / "tcl/usr/bin", root / "readline/usr/bin",
        root / "ncurses/usr/bin", root / "zlib/usr/bin", root / "bootstrap/usr/bin",
        Path(os.environ["SystemRoot"]) / "System32"))
    env.update(HOME=str(root / "home"), USERPROFILE=str(root / "home"),
               TMP=str(root / "temp"), TEMP=str(root / "temp"), TMPDIR=str(root / "temp"),
               XDG_CACHE_HOME=str(root / "cache"), CCACHE_DIR=str(root / "cache/ccache"),
               CCACHE_DISABLE="1", MAKEFLAGS=f"-j{jobs}", MFLAGS=f"-j{jobs}", OMP_NUM_THREADS="1",
               CMAKE_BUILD_PARALLEL_LEVEL=str(jobs), WOARM64_NATIVE_ARG_CONVERSION="none",
               WOARM64_NATIVE_PYTHON=sys.executable, WOARM64_NATIVE_PYTHON_SHA256=digest(sys.executable),
               WOARM64_NATIVE_TEST_ROOT=str(root), WOARM64_NATIVE_EXIT_DIR=str(output / "native-exits"),
               WOARM64_NATIVE_DRIVER_ROOT=str(root / "observer"),
               TCL_LIBRARY=msys_path(root / "tcl/usr/lib/tcl8.6"),
               TCLLIBPATH=msys_path(root / "tcl/usr/lib"))
    return env


def prepare_views(root):
    config = root / "tcl-config-windows"
    if config.exists():
        verify_tree(config, root / "tcl-config-windows.inventory.json")
        return
    # This source-only copy backs TCL_SRC_DIR; installed headers and libraries
    # continue to come exclusively from the qualified MSYS Tcl runtime stage.
    manifest = Path(r"C:\ag-e138920f\sqlite-tcl-inputs-01\sources\tcl-msys.inventory.json")
    if digest(manifest) != "663634e00bc1a8472e8bcdfce2adeb671ff3c2bdc4b5c8798f5ebe1856a01742":
        raise ContractError("Pinned MSYS Tcl source receipt differs")
    verify_tree(manifest.with_name("tcl-msys"), manifest)
    if not (root / "tcl-source").exists():
        shutil.copytree(manifest.with_name("tcl-msys"), root / "tcl-source")
    verify_tree(root / "tcl-source", manifest)
    verify_tree(manifest.with_name("tcl-msys"), manifest)
    if not (root / "tcl-source.inventory.json").exists():
        shutil.copyfile(manifest, root / "tcl-source.inventory.json")
    text, replacements = tcl_config_view((root / "tcl/usr/lib/tclConfig.sh").read_text(), root)
    config.mkdir()
    (config / "tclConfig.sh").write_text(text, encoding="utf-8", newline="\n")
    write_json(root / "tcl-config-windows.inventory.json", {
        "schema": 1, "scope": "Path-only private compiler/config view; unchanged version/features/flags",
        "original_sha256": digest(root / "tcl/usr/lib/tclConfig.sh"),
        "replacements": replacements, "files": inventory(config)})
    fstab = root / "tcl/etc/fstab"
    if digest(fstab) != "387ca1e86c1a18a143eb077ca194ad44c0a2faf98795a0d437f2d210d5a6df18":
        raise ContractError("Private drive mount configuration differs")
    if not (root / "compiler/etc").exists():
        (root / "compiler/etc").mkdir()
        shutil.copyfile(fstab, root / "compiler/etc/fstab")
        write_json(root / "compiler-runtime.inventory.json", {
            "schema": 1, "full_cpp_qualified": False,
            "scope": "Byte-identical compiler plus exact approved private etc/fstab only",
            "files": inventory(root / "compiler")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"C:\ag-sqlite-e138-01"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", choices=("configure", "build", "extensions", "install", "quicktest", "tcltest"), required=True)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--jobs", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ContractError("Fresh owned evidence output required")
    adoption = json.loads((root / "adopt-result.json").read_text())
    if adoption["status"] != "private-sqlite-inputs-byte-identical-not-executed":
        raise ContractError("Full byte-identical private adoption required")
    lock = json.loads(Path(__file__).with_name("sqlite-inputs.json").read_text())
    if digest(sys.executable) != lock["python_sha256"]:
        raise ContractError("Exact native Python required")
    prepare_views(root)
    build = (args.build or root / "build-01").resolve()
    if not build.is_relative_to(root):
        raise ContractError("Build must be private")
    if args.phase == "configure":
        build.mkdir(exist_ok=False)
    elif not (build / "Makefile").is_file():
        raise ContractError("An actual configured native build is required")
    output.mkdir()
    (output / "native-exits").mkdir()
    profile = recipe()
    script = Path(__file__).with_suffix(".sh")
    env = environment(root, output, args.jobs)
    env["SQLITE_RECIPE_CPPFLAGS"] = " ".join(profile["cppflags"])
    env["SQLITE_NATIVE_CONFIGURE"] = "\n".join(profile["configure"])
    command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc",
               script.resolve().as_posix(), args.phase, str(root), str(build), str(args.jobs), str(output)]
    report = {"schema": 1, "status": "failed", "phase": args.phase, "version": "3.53.4",
              "jobs": args.jobs, "nested_jobs": 1 if args.phase == "quicktest" else args.jobs,
              "full_cpp_qualified": False, "package_admission": False,
              "launcher": process_identity(), "command": list(map(str, command)),
              "recipe": profile, "splits": SPLITS, "tools": TOOLS, "build": str(build),
              "recipe_driver_sha256": digest(script), "minimum_free_gib": require_memory()}
    write_json(output / "launch.json", report)
    print(json.dumps({"launch": report["launcher"], "command": report["command"],
                      "log": str(output / "build.log")}), flush=True)
    identities = {}
    try:
        for name in lock["inputs"]:
            manifest = root / ("compiler-runtime.inventory.json" if name == "compiler" else f"{name}.inventory.json")
            verify_tree(root / name, manifest)
            identities[name] = digest(manifest)
        verify_driver(root / "observer")
        if args.phase == "extensions":
            extension = build / "ext/misc"
            extension.mkdir(parents=True, exist_ok=False)
            (extension / "Makefile").write_text(extension_makefile(
                (root / "prepared/recipe/Makefile.ext.in").read_text(), root, build), newline="\n")
        report["process"] = run_observed(
            command, cwd=build, env=env, log_path=output / "build.log",
            result_path=output / "native-job.json", relay_records=output / "native-exits",
            timeout=14400 if args.phase in ("quicktest", "tcltest") else 7200,
            driver_prefix=root / "observer")
        report["status"] = "native-sqlite-phase-passed" if report["process"]["passed"] else "native-sqlite-phase-failed"
        if args.phase == "install":
            report["split_files"] = {name: inventory(build / "splits" / name) for name in SPLITS
                                    if (build / "splits" / name).is_dir()}
        if args.phase in ("build", "extensions", "install"):
            report["build_files"] = inventory(build)
    finally:
        failures = []
        for name, sha in identities.items():
            manifest = root / ("compiler-runtime.inventory.json" if name == "compiler" else f"{name}.inventory.json")
            try:
                if digest(manifest) != sha:
                    raise ContractError("Inventory receipt changed")
                verify_tree(root / name, manifest)
            except (OSError, ContractError) as error:
                failures.append(f"{name}: {error}")
        report["input_integrity_errors"] = failures
        if failures:
            report["status"] = "failed"
        write_json(output / "result.json", report)
    if report["status"] != "native-sqlite-phase-passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
