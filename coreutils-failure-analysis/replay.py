"""Fresh same-binary native harness replays; raw observer verdicts remain separate."""

import argparse
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time

from inventory import ROOT, PRODUCER, BUILD, SOURCE, copy, digest, write

MVP = Path(r"C:\ag-exit-e138-01\coreutils-20260910-01")
SEALED = Path(r"C:\ag-exit-e138-01\resume-20260909-01")
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
sys.path.insert(0, str(SEALED / "support"))
from bounded_process import run as bounded_run
from native_job_runner import noninteractive_error_mode


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def memory():
    class Memory(C.Structure):
        _fields_ = [("size", C.c_uint32), ("load", C.c_uint32)] + [(name, C.c_uint64) for name in
                    ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    record = Memory()
    record.size = C.sizeof(record)
    function = C.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
    function.argtypes, function.restype = [C.POINTER(Memory)], C.c_int
    if not function(C.byref(record)):
        raise C.WinError(C.get_last_error())
    if record.available <= 8 * 1024 ** 3:
        raise RuntimeError("Free memory floor <=8GiB")
    return record.available


def msys(path):
    text = str(Path(path).resolve())
    return "/" + text[0].lower() + text[2:].replace("\\", "/")


def prepare():
    destination = ROOT / "source"
    destination.mkdir(exist_ok=False)
    copies = []
    for path in sorted((SOURCE / "tests").rglob("*")):
        if path.is_file():
            copy(path, destination / path.relative_to(SOURCE), copies)
    for name in ("init.cfg", "build-aux/test-driver"):
        copy(SOURCE / name, destination / name, copies)
    copy(BUILD / "lib/config.h", ROOT / "config.h", copies)
    makefile = (BUILD / "Makefile").read_text()
    built = re.search(r"^built_programs = (.+)$", makefile, re.M).group(1)
    utility_manifest = load(r"C:\ag-utils-e138-01\native-utilities-06\native-bash-test-utilities.manifest.json")["files"]
    dependency_manifest = load(MVP / "inputs.json")
    private = MVP / "private/usr/bin"
    for cohort in ("current-noacl", "current-acl", "historical-noacl"):
        prefix = ROOT / cohort
        (prefix / "usr/bin").mkdir(parents=True)
        (prefix / "etc").mkdir()
        (prefix / "tmp").mkdir()
        (prefix / "home").mkdir()
        for path in sorted((BUILD / "src").glob("*.exe")):
            data = path.read_bytes()
            pe = int.from_bytes(data[60:64], "little")
            if data[:2] != b"MZ" or data[pe:pe + 4] != b"PE\0\0" or int.from_bytes(data[pe + 4:pe + 6], "little") != 0xAA64:
                raise RuntimeError(f"Non-native test candidate: {path}")
            copy(path, prefix / "usr/bin" / path.name, copies)
        for name in ("bash.exe", "msys-intl-8.dll", "msys-iconv-2.dll", "msys-gmp-10.dll"):
            expected = next(row["copied"] for row in dependency_manifest["copies"] if row["copy"] == str(private / name))
            copy(private / name, prefix / "usr/bin" / name, copies, expected)
        copy(private / "bash.exe", prefix / "usr/bin/sh.exe", copies,
             "0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c")
        for name in ("gawk.exe", "grep.exe", "diff.exe", "cmp.exe", "sed.exe", "find.exe", "xargs.exe"):
            path = Path(r"C:\ag-utils-e138-01\native-utilities-06\stage\usr\bin") / name
            copy(path, prefix / "usr/bin" / name, copies, utility_manifest[f"usr/bin/{name}"]["sha256"])
        for name in ("msys-mpfr-6.dll", "msys-pcre-1.dll"):
            path = Path(r"C:\ag-utils-e138-01\native-utilities-06\stage\usr\bin") / name
            if path.is_file():
                copy(path, prefix / "usr/bin" / name, copies, utility_manifest[f"usr/bin/{name}"]["sha256"])
        runtime = PRODUCER / "stage/runtime/usr/bin/msys-2.0.dll" if cohort.startswith("historical") else private / "msys-2.0.dll"
        copy(runtime, prefix / "usr/bin/msys-2.0.dll", copies,
             "baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15" if cohort.startswith("historical") else RUNTIME_SHA)
        if cohort.endswith("-noacl"):
            copy(MVP / "private/etc/fstab", prefix / "etc/fstab", copies,
                 "387ca1e86c1a18a143eb077ca194ad44c0a2faf98795a0d437f2d210d5a6df18")
        else:
            with (prefix / "etc/fstab").open("x", encoding="ascii", newline="\n") as stream:
                stream.write("none / cygdrive binary,posix=0,acl,user 0 0\n")
    write(ROOT / "replay-inputs.json", {"schema": 1, "copies": copies, "built_programs": built,
          "source_tests_unchanged": True, "acl_change": "Only fresh owned prefix fstab; no global mounts, policies or privileges",
          "historical_runtime": "Native-parent isolation control, NOT recreation of historical x64-parent launch"})
    print(json.dumps({"copies": len(copies), "root": str(ROOT)}))


def run(cohort, label, test=None, command=None, extras=None, timeout=100):
    inputs = load(ROOT / "replay-inputs.json")
    prefix = ROOT / cohort
    bin_dir = prefix / "usr/bin"
    case = ROOT / "runs" / label
    case.mkdir(parents=True, exist_ok=False)
    (case / "relay").mkdir()
    (case / "work").mkdir()
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    environment.update({
        "PATH": os.pathsep.join([str(bin_dir), str(Path(environment["SystemRoot"]) / "System32")]),
        "HOME": str(prefix / "home"), "USERPROFILE": str(prefix / "home"), "TMP": str(case / "work"),
        "TEMP": str(case / "work"), "TMPDIR": msys(case / "work"), "MSYS": "winsymlinks:sys",
        "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C", "TZ": "UTC",
        "srcdir": msys(ROOT / "source"), "abs_srcdir": msys(ROOT / "source"),
        "abs_top_srcdir": msys(ROOT / "source"), "top_srcdir": msys(ROOT / "source"),
        "abs_top_builddir": msys(case / "work"), "CONFIG_HEADER": msys(ROOT / "config.h"),
        "built_programs": inputs["built_programs"], "fail": "0", "EXEEXT": ".exe",
        "SHELL": "/usr/bin/bash", "BOURNE_SHELL": "/usr/bin/sh", "AWK": "gawk",
        "EGREP": "grep -E", "PACKAGE_VERSION": "8.32", "VERSION": "8.32",
        "host_os": "cygwin", "host_triplet": "aarch64-pc-cygwin", "VERBOSE": "yes",
        "CU_TEST_NAME": label, "PYTHONDONTWRITEBYTECODE": "1", "KEEP": "yes",
    })
    if extras:
        environment.update(extras)
    shell = "exec 9>&2; cd " + msys(case / "work") + " || exit $?; "
    if test is not None:
        harness = ("srcdir", "abs_srcdir", "abs_top_srcdir", "top_srcdir", "abs_top_builddir",
                   "CONFIG_HEADER", "built_programs", "fail", "EXEEXT", "SHELL", "BOURNE_SHELL",
                   "AWK", "EGREP", "PACKAGE_VERSION", "VERSION", "host_os", "host_triplet",
                   "VERBOSE", "CU_TEST_NAME", "KEEP")
        shell += "export " + " ".join(key + "=" + shlex.quote(environment[key]) for key in harness) + "; "
        shell += "ln -s /usr/bin src || exit $?; exec /usr/bin/bash --noprofile --norc " + msys(ROOT / "source" / test)
    else:
        shell += command
    target = [str(bin_dir / "bash.exe"), "--noprofile", "--norc", "-c", shell]
    argv = [sys.executable, "-I", "-B", str(SEALED / "driver/native-job.py"),
            "--cwd", str(case / "work"), "--target-root", str(prefix),
            "--relay-records", str(case / "relay"), "--log", str(case / "target.log"),
            "--result", str(case / "native-job.json"), "--timeout", str(timeout), "--", *target]
    before = memory()
    with noninteractive_error_mode(), (case / "observer.log").open("xb") as log:
        observed = bounded_run(argv, cwd=case, env=environment, log=log, timeout=timeout + 20)
    record = load(case / "native-job.json")
    result = {"schema": 1, "cohort": cohort, "test": test, "shell": shell, "command": argv,
              "environment": environment, "outer": observed, "native_job": record,
              "native_job_sha256": digest(case / "native-job.json"), "log_sha256": digest(case / "target.log"),
              "free_before": before, "free_after": memory(), "same_test_source": test is not None,
              "test_source_sha256": digest(ROOT / "source" / test) if test else None,
              "semantic_test_shell_raw_exit": record["parent_raw_exit"],
              "observer_gate_passed": record["passed"], "not_a_package_admission": True}
    write(case / "result.json", result)
    print(json.dumps({"label": label, "test": test, "shell_raw": record["parent_raw_exit"],
                      "observer_gate": record["passed"], "timed_out": record["timed_out"],
                      "coverage": [record["observed_processes"], record["created_processes"]]}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "shell-batch", "acl-batch"))
    parser.add_argument("--cohort", default="current-noacl",
                        choices=("current-noacl", "current-acl", "historical-noacl", "current-complete"))
    parser.add_argument("--label")
    parser.add_argument("--test")
    parser.add_argument("--command")
    parser.add_argument("--timeout", type=int, default=100)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action in ("shell-batch", "acl-batch"):
        results = []
        acl_tests = {"tests/rm/cycle.sh", "tests/chmod/no-x.sh", "tests/chgrp/basic.sh",
                     "tests/rm/fail-eacces.sh", "tests/rm/inaccessible.sh", "tests/rm/rm1.sh",
                     "tests/rm/rm2.sh", "tests/rm/rm3.sh", "tests/rm/unread2.sh", "tests/rm/unread3.sh",
                     "tests/chgrp/no-x.sh", "tests/chgrp/posix-H.sh", "tests/chgrp/recurse.sh"}
        for test in load(ROOT / "inventory.json")["tests"]:
            if not test["test"].endswith(".sh") or test["test"] == "tests/rm/rm-readdir-fail.sh":
                continue
            if args.action == "acl-batch" and test["test"] not in acl_tests:
                continue
            label = "upstream-" + test["test"].replace("/", "-").removesuffix(".sh") + "-" + args.cohort
            result = run(args.cohort, label, test=test["test"], timeout=180 if "help-version.sh" in test["test"] else 90)
            results.append({"test": test["test"], "original_status": test["status"], "case": str(ROOT / "runs" / label),
                            "test_shell_raw_exit": result["semantic_test_shell_raw_exit"],
                            "observer_gate": result["observer_gate_passed"],
                            "timeout": result["native_job"]["timed_out"]})
        write(ROOT / f"{args.action}-{args.cohort}.json", results)
        print(json.dumps({"batch_complete": len(results), "raw_counts": {
            str(code): sum(row["test_shell_raw_exit"] == code for row in results)
            for code in sorted({row["test_shell_raw_exit"] for row in results})}}))
    else:
        if not args.label or Path(args.label).name != args.label or bool(args.test) == bool(args.command):
            parser.error("Explicit unique case label and one test/command are required")
        run(args.cohort, args.label, args.test, args.command, timeout=args.timeout)
