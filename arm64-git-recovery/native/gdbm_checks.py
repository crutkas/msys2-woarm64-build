"""Run original GDBM checks through a coherent, explicitly native shell."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil

from db_channel_checks import own_birth
from db_native_checks import environment
from gdbm_recovery import isolated_observe
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json


def autotest(args):
    root = args.root
    output = root / args.run_name
    output.mkdir()
    (output / "native-exits").mkdir()
    tests = root / "build/tests"
    for name in ("testsuite.log", "testsuite.dir"):
        source = tests / name
        if source.is_dir():
            shutil.copytree(source, output / ("previous-" + name))
        elif source.is_file():
            shutil.copy2(source, output / ("previous-" + name))
    posix = "/c/" + root.relative_to(root.anchor).as_posix()
    bash = root / "build-runtime/usr/bin/bash.exe"
    shell = f"{posix}/build-runtime/usr/bin/bash.exe"
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (bash.parent, root / "compiler/bin",
                    root / "bootstrap/usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    body = (f'export PATH="{posix}/build-runtime/usr/bin:{posix}/compiler/bin:{posix}/bootstrap/usr/bin"; '
            f'export CONFIG_SHELL="{shell}" SHELL="{shell}"; '
            f'cd "{posix}/build/tests"; exec "{shell}" "{posix}/source/tests/testsuite"')
    if args.group:
        body += f" {args.group}"
    command = [bash, "--noprofile", "--norc", "-c", body]
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "command": list(map(str, command)), "jobs": 1, "free_gib": require_memory(),
        "group": args.group or "all38", "testsuite_sha256": digest(root / "source/tests/testsuite"),
        "atconfig_sha256": digest(tests / "atconfig"), "atlocal_sha256": digest(tests / "atlocal"),
        "atlocal_in_sha256": digest(root / "source/tests/atlocal.in"),
        "native_images": {str(path.relative_to(root)): digest(path)
                          for path in (root / "build").rglob("*")
                          if path.is_file() and path.suffix in (".exe", ".dll")}})
    row = isolated_observe(root, output, "original-autotest", command, tests, env, 1200)
    for name in ("testsuite.log", "testsuite.dir"):
        source = tests / name
        if source.is_dir():
            shutil.copytree(source, output / name)
        elif source.is_file():
            shutil.copy2(source, output / name)
    write_json(output / "result.json", {"process": row, "group": args.group or "all38",
                                       "upstream_log_sha256": digest(output / "testsuite.log")})
    print(json.dumps(row["process"]), flush=True)
    if not row["process"]["passed"]:
        raise ContractError("Original GDBM test command failed; raw evidence retained")


def dejagnu(args):
    root = args.root
    output = root / args.run_name
    output.mkdir()
    (output / "native-exits").mkdir()
    posix = "/c/" + root.relative_to(root.anchor).as_posix()
    cwd = root / "build/tests/dejagnu"
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    host = root / "bootstrap/usr/bin/bash.exe"
    host_command = (f'export PATH="{posix}/bootstrap/usr/bin"; '
                    f'cd "{posix}/build/tests/dejagnu"; '
                    f'exec "{posix}/bootstrap/usr/bin/make.exe" -j1 '
                    f'MAKE="{posix}/bootstrap/usr/bin/make.exe" SHELL="{posix}/bootstrap/usr/bin/bash.exe" site.exp')
    generated = isolated_observe(root, output, "original-site-exp", [host, "--noprofile", "--norc", "-c", host_command], cwd, env, 120)
    if not generated["process"]["passed"]:
        raise ContractError("Original GDBM DejaGNU site.exp generation failed")
    env["PATH"] = os.pathsep.join((str(root / "check-runtime/usr/bin"),
                                  str(Path(os.environ["SystemRoot"]) / "System32")))
    env["TCL_LIBRARY"] = posix + "/check-runtime/usr/lib/tcl8.6"
    env["TCLLIBPATH"] = posix + "/check-runtime/usr/lib"
    env["EXPECT"] = posix + "/check-runtime/usr/bin/expect.exe"
    env["DEJAGNU"] = "/dev/null"
    env["LC_ALL"] = "C"
    command = [root / "check-runtime/usr/bin/bash.exe", "--noprofile", "--norc",
               posix + "/check-runtime/usr/bin/runtest", "--tool", "gdbmtool",
               "--srcdir", posix + "/source/tests/dejagnu"]
    images = {str(path.relative_to(root)): digest(path)
              for directory in ("src", "compat", "tools")
              for path in (root / "build" / directory).rglob("*")
              if path.is_file() and path.suffix in (".exe", ".dll")}
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(), "jobs": 1,
        "command": list(map(str, command)), "native_images": images,
        "site_exp_sha256": digest(cwd / "site.exp"),
        "original_test_sha256": digest(root / "source/tests/dejagnu/testsuite/gdbmtool/base.exp"),
        "native_check_runtime_sha256": digest(root / "check-runtime.json")})
    row = isolated_observe(root, output, "original-dejagnu", command, cwd, env, 600)
    for name in ("site.exp", "gdbmtool.sum", "gdbmtool.log"):
        if (cwd / name).is_file():
            shutil.copy2(cwd / name, output / name)
    summary = (output / "gdbmtool.sum").read_text() if (output / "gdbmtool.sum").exists() else ""
    counts = {label: int(value) for label, value in re.findall(r"^# of (.+?)\s+(\d+)\s*$", summary, re.M)}
    unchanged = all(digest(root / name) == sha for name, sha in images.items())
    passed = (counts.get("expected passes") == 2
              and not re.search(r"^(FAIL|UNRESOLVED|ERROR):", summary, re.M)
              and row["process"]["exit"] == 0 and not row["process"]["timed_out"] and unchanged)
    write_json(output / "result.json", {"schema": 1, "site_generation": generated,
        "process": row, "upstream_counts": counts, "upstream_semantics_passed": passed,
        "native_images_unchanged": unchanged})
    print(json.dumps({"upstream_counts": counts, "upstream_semantics_passed": passed,
                      "observer_passed": row["process"]["passed"]}), flush=True)
    if not passed or not row["process"]["passed"]:
        raise ContractError("Original native GDBM DejaGNU qualification did not fully pass")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--group", type=int, choices=range(1, 39))
    parser.add_argument("--dejagnu", action="store_true")
    args = parser.parse_args()
    args.root = args.root.resolve()
    if args.root != Path(r"C:\ag-gdbm-20260911-01") or Path(args.run_name).name != args.run_name:
        raise ContractError("Explicit owned GDBM check root and run directory required")
    (dejagnu if args.dejagnu else autotest)(args)


if __name__ == "__main__":
    main()
