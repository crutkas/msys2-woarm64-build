"""Real utility controls; raw failure and contract results are separate fields."""

import argparse
import ctypes as C
import json
import os
from pathlib import Path
import re
import sys

from qualify import ROOT, RUNTIME_SHA, CORE_NAMES, EXTRA_NAMES, copy, digest, load, write
from pe_closure import Image
from debug_tree import job

sys.path.insert(0, str(ROOT / "support"))
from bounded_process import run as bounded_run
from native_job_runner import noninteractive_error_mode

FIXTURE = b"pear\napple\napple\nbanana\n"


def memory_available():
    class Memory(C.Structure):
        _fields_ = [("size", C.c_uint32), ("load", C.c_uint32)] + [(name, C.c_uint64) for name in
                    ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    memory = Memory()
    memory.size = C.sizeof(memory)
    query = C.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
    query.argtypes, query.restype = [C.POINTER(Memory)], C.c_int
    if not query(C.byref(memory)):
        raise C.WinError(C.get_last_error())
    if memory.available <= 8 * 1024 ** 3:
        raise RuntimeError("Required >8GiB free memory floor reached")
    return memory.available


def definitions():
    return {
        "cat": ("exec /usr/bin/cat.exe sample.txt", FIXTURE),
        "cp": ("exec /usr/bin/cp.exe sample.txt copied.txt", b""),
        "mkdir": ("exec /usr/bin/mkdir.exe -p created/deep", b""),
        "mv": ("exec /usr/bin/mv.exe sample.txt moved.txt", b""),
        "rm": ("exec /usr/bin/rm.exe sample.txt", b""),
        "rmdir": ("exec /usr/bin/rmdir.exe empty", b""),
        "ln": ("exec /usr/bin/ln.exe -s sample.txt linked", b""),
        "readlink": ("/usr/bin/ln.exe -s sample.txt linked && exec /usr/bin/readlink.exe linked", b"sample.txt\n"),
        "pwd": ("exec /usr/bin/pwd.exe -P", None),
        "env": ("exec /usr/bin/env.exe UTILITY_PROBE=907 /usr/bin/bash.exe --noprofile --norc -c 'printf \"%s\\n\" \"$UTILITY_PROBE\"'", b"907\n"),
        "uname": ("exec /usr/bin/uname.exe -m", b"aarch64\n"),
        "dd": ("exec /usr/bin/dd.exe if=bytes.bin of=bytes-copy.bin bs=3 count=4 status=none", b""),
        "wc": ("exec /usr/bin/wc.exe -l sample.txt", b"4 sample.txt\n"),
        "sort": ("exec /usr/bin/sort.exe sample.txt", b"apple\napple\nbanana\npear\n"),
        "uniq": ("exec /usr/bin/uniq.exe sample.txt", b"pear\napple\nbanana\n"),
        "head": ("exec /usr/bin/head.exe -n 2 sample.txt", b"pear\napple\n"),
        "tail": ("exec /usr/bin/tail.exe -n 2 sample.txt", b"apple\nbanana\n"),
        "cut": ("exec /usr/bin/cut.exe -d : -f 2 fields.txt", b"red\nblue\n"),
        "tr": ("exec /usr/bin/tr.exe a-z A-Z <sample.txt", FIXTURE.upper()),
        "sleep": ("exec /usr/bin/sleep.exe 0.1", b""),
        "true": ("exec /usr/bin/true.exe", b""),
        "false": ("exec /usr/bin/false.exe", b""),
        "test": ("exec /usr/bin/test.exe -s sample.txt", b""),
        "stat": ("exec /usr/bin/stat.exe -c '%s' bytes.bin", b"12\n"),
        "touch": ("exec /usr/bin/touch.exe -t 202001020304.05 touched", b""),
        "chmod": ("/usr/bin/chmod.exe 600 sample.txt && exec /usr/bin/stat.exe -c '%a' sample.txt", b"600\n"),
        "basename": ("exec /usr/bin/basename.exe /a/b/file.txt .txt", b"file\n"),
        "dirname": ("exec /usr/bin/dirname.exe /a/b/file.txt", b"/a/b\n"),
        "tee": ("exec /usr/bin/tee.exe tee-copy.txt <sample.txt", FIXTURE),
        "printf": ("exec /usr/bin/printf.exe 'number=%d text=%s\\n' 42 arm64", b"number=42 text=arm64\n"),
        "expr": ("exec /usr/bin/expr.exe 7 + 5", b"12\n"),
        "install": ("exec /usr/bin/install.exe -m 644 sample.txt installed.txt", b""),
        "ls": ("exec /usr/bin/ls.exe -1 only", b"entry.txt\n"),
        "stty": ("exec /usr/bin/stty.exe -a", None),
        "stty-pty": ("exec /usr/bin/pty-control.exe /usr/bin/stty.exe", b"24 80\n"),
        "chmod-basic": ("/usr/bin/chmod.exe a-w sample.txt && exec /usr/bin/stat.exe -c '%a' sample.txt", b"444\n"),
        "timeout": ("exec /usr/bin/timeout.exe 5 /usr/bin/sleep.exe 0.1", b""),
        "realpath": ("exec /usr/bin/realpath.exe sample.txt", None),
        "od": ("exec /usr/bin/od.exe -An -tu1 bytes.bin", None),
        "find": ("exec /usr/bin/find.exe only -type f -print", b"only/entry.txt\n"),
        "xargs": ("exec /usr/bin/xargs.exe -n 1 /usr/bin/printf.exe '[%s]\\n' <words.txt", b"[one]\n[two]\n"),
        "sed": ("exec /usr/bin/sed.exe 's/apple/fruit/g' sample.txt", b"pear\nfruit\nfruit\nbanana\n"),
        "pipeline": ("/usr/bin/cat.exe sample.txt | /usr/bin/sort.exe | /usr/bin/uniq.exe | /usr/bin/tee.exe pipeline.txt", b"apple\nbanana\npear\n"),
    }


def prepare_case(case):
    case.mkdir(parents=True, exist_ok=False)
    for name, data in (("sample.txt", FIXTURE), ("fields.txt", b"1:red\n2:blue\n"),
                       ("bytes.bin", bytes(range(12))), ("words.txt", b"one two\n")):
        with (case / name).open("xb") as stream:
            stream.write(data)
    (case / "empty").mkdir()
    (case / "only").mkdir()
    with (case / "only/entry.txt").open("xb") as stream:
        stream.write(b"entry\n")
    (case / "relay").mkdir()


def postconditions(name, case, stdout):
    checks = []
    def add(label, passed):
        checks.append({"check": label, "passed": bool(passed)})
    if name == "cp":
        add("copied bytes equal input", (case / "copied.txt").is_file() and (case / "copied.txt").read_bytes() == FIXTURE)
    elif name == "mkdir":
        add("nested directory created", (case / "created/deep").is_dir())
    elif name == "mv":
        add("move preserved bytes and removed source", not (case / "sample.txt").exists()
            and (case / "moved.txt").is_file() and (case / "moved.txt").read_bytes() == FIXTURE)
    elif name == "rm":
        add("requested file removed", not (case / "sample.txt").exists())
    elif name == "rmdir":
        add("requested empty directory removed", not (case / "empty").exists())
    elif name == "ln":
        # winsymlinks:sys is a real MSYS symlink representation, not a copied target.
        add("MSYS system symlink record exists, not a copied data file",
            (case / "linked").is_file() and (case / "linked").read_bytes() != FIXTURE
            and (case / "linked").read_bytes().startswith(b"!<symlink>"))
    elif name == "pwd":
        add("physical path names the exact owned case", stdout.decode(errors="replace").strip().replace("\\", "/").lower().endswith(
            str(case).replace("\\", "/")[2:].lower()))
    elif name == "realpath":
        add("canonical path names the owned input", stdout.decode(errors="replace").strip().replace("\\", "/").lower().endswith(
            (str(case).replace("\\", "/")[2:] + "/sample.txt").lower()))
    elif name == "dd":
        add("all twelve binary bytes copied", (case / "bytes-copy.bin").is_file()
            and (case / "bytes-copy.bin").read_bytes() == bytes(range(12)))
    elif name == "touch":
        add("new empty file and requested timestamp", (case / "touched").is_file()
            and (case / "touched").stat().st_size == 0
            and abs((case / "touched").stat().st_mtime - 1577934245) < 1)
    elif name in ("tee", "install", "pipeline"):
        filename = {"tee": "tee-copy.txt", "install": "installed.txt", "pipeline": "pipeline.txt"}[name]
        expected = b"apple\nbanana\npear\n" if name == "pipeline" else FIXTURE
        add("output file bytes match", (case / filename).is_file() and (case / filename).read_bytes() == expected)
    elif name == "od":
        add("exact binary byte interpretation", stdout.split() == [str(value).encode() for value in range(12)])
    return checks


def run_case(name, root_name="private", suffix="01"):
    private = ROOT / root_name
    bin_dir = private / "usr/bin"
    before_memory = memory_available()
    case = ROOT / "cases" / f"{root_name}-{name}-{suffix}"
    prepare_case(case)
    shell, expected = definitions()[name]
    shell = "cd .. || exit $?; " + shell
    source_records = []
    for source in sorted(Path(__file__).parent.glob("*.py")):
        copy(source, case / "source" / source.name, digest(source), source_records, "qualification-source")
    python = sys.executable
    target = [str(bin_dir / "bash.exe"), "--noprofile", "--norc", "-o", "pipefail", "-c", shell]
    command = [python, "-I", "-B", str(ROOT / "driver/native-job.py"), "--cwd", str(case),
               "--target-root", str(ROOT), "--relay-records", str(case / "relay"),
               "--log", str(case / "target.log"), "--result", str(case / "native-job.json"),
               "--timeout", "40", "--", python, "-B", str(case / "source/debug_tree.py"),
               "--output", str(case / "debug"), "--abi", str(ROOT / "windows-abi.json"),
               "--timeout", "25", "--no-context", "--", *target]
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    environment.update({"PATH": os.pathsep.join([str(bin_dir), str(Path(environment["SystemRoot"]) / "System32")]),
                        "HOME": str(private / "home"), "USERPROFILE": str(private / "home"),
                        "TEMP": str(case), "TMP": str(case), "LC_ALL": "C", "LANG": "C", "TZ": "UTC",
                        "MSYS": "winsymlinks:sys", "PYTHONDONTWRITEBYTECODE": "1"})
    with noninteractive_error_mode(), (case / "observer.log").open("xb") as log:
        launch = bounded_run(command, cwd=case, env=environment, log=log, timeout=55)
    native = load(case / "native-job.json")
    capture = load(case / "debug/result.json")
    stdout = (case / "debug/stdout.bin").read_bytes()
    stderr = (case / "debug/stderr.bin").read_bytes()
    exits = native["native_target_exits"]
    native_map = {(row["pid"], row["created"]): row["raw_exit"] for row in exits}
    debug_map = {(row["pid"], row["created"]): row.get("raw_exit") for row in capture["processes"]}
    complete = (native_map == debug_map and len(native_map) == len(exits)
                and len(debug_map) == len(capture["processes"]) and capture["error"] is None
                and native["observation_count_matches"] and not native["unobserved_processes"]
                and not native["unresolved_processes"] and not native["timed_out"]
                and not launch["timed_out"] and launch["active_at_boundary"] == 0
                and not capture["memory_writes"] and not capture["register_writes"])
    mapped_failures, modules = [], []
    system32 = (Path(environment["SystemRoot"]) / "System32").resolve()
    for process in capture["processes"]:
        if process["machine"] != 0xAA64 or not process.get("event_matches_handle_exit"):
            mapped_failures.append({"process": process["pid"], "reason": "native-generation-or-raw-mismatch"})
        runtimes = []
        for module in [process["image"], *process["modules"]]:
            path = Path(job.normalise_windows_path(module.get("path", ""))).resolve()
            if not path.is_file() or not (path.is_relative_to(bin_dir.resolve()) or path.parent == system32):
                mapped_failures.append({"process": process["pid"], "module": module, "reason": "outside-private-or-System32"})
                continue
            image = Image(path)
            modules.append({"pid": process["pid"], "created": process["created"], **image.summary()})
            if image.machine != 0xAA64 or image.sha256 != module.get("mapped_file_sha256"):
                mapped_failures.append({"process": process["pid"], "module": module, "reason": "wrong-machine-or-mapped-identity"})
            if path.name.lower() == "msys-2.0.dll":
                runtimes.append(image)
        if not runtimes or any(runtime.sha256 != RUNTIME_SHA or runtime.path != (bin_dir / "msys-2.0.dll").resolve()
                               for runtime in runtimes):
            mapped_failures.append({"process": process["pid"], "reason": "not-exact-private-runtime907"})
    checks = postconditions(name, case, stdout)
    if expected is not None:
        checks.append({"check": "exact stdout", "passed": stdout == expected})
    utility_name = {"stty-pty": "stty", "chmod-basic": "chmod"}.get(name, name)
    target_executed = any(Path(row["executable"]).stem.lower() == utility_name for row in exits) if name != "pipeline" else all(
        any(Path(row["executable"]).stem.lower() == utility for row in exits) for utility in ("cat", "sort", "uniq", "tee"))
    positive = bool(exits) and all(row["raw_exit"] == 0 for row in exits)
    result = {"schema": 1, "utility": name, "command": command, "shell": shell, "environment": environment,
              "launch": launch, "raw_generation_exits": exits, "complete_observation": complete,
              "mapped_modules": modules, "mapped_failures": mapped_failures, "target_executed": target_executed,
              "positive_raw_exit": positive, "checks": checks,
              "stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"),
              "status": "positive-control-passed" if complete and not mapped_failures and positive and target_executed and all(
                  check["passed"] for check in checks) else "failed",
              "expected_negative": name == "false", "false_contract_note": "false intentionally returns nonzero; raw remains failure, not normalized" if name == "false" else None,
              "not_admitted": True, "native_job_sha256": digest(case / "native-job.json"),
              "capture_sha256": digest(case / "debug/result.json"), "source_copies": source_records,
              "free_before": before_memory, "free_after": memory_available()}
    write(case / "result.json", result)
    print(json.dumps({"utility": name, "status": result["status"], "raw": [r["raw_exit"] for r in exits],
                      "complete": complete, "mapped_failures": len(mapped_failures),
                      "failed_checks": [r["check"] for r in checks if not r["passed"]],
                      "stderr": result["stderr"][:250]}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--root", default="private", choices=("private", "moved"))
    parser.add_argument("--suffix", default="01")
    args = parser.parse_args()
    for name in args.names or [*CORE_NAMES, *EXTRA_NAMES, "pipeline"]:
        run_case(name, args.root, args.suffix)
