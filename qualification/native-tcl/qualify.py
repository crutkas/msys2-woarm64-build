"""Qualify the already-built native MSYS Tcl without rebuilding or changing its tests."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(r"C:\ag-tcl-e138-01")
INPUT = Path(r"C:\ag-e138920f")
PYTHON = Path(r"C:\Program Files\Python314-arm64\python.exe")
SEALS = {
    INPUT / "consumer-tools-03.json": "c237262f0e4bda779d25c8831a307b52dd5f02d14f57edaab6abdd184954032d",
    INPUT / "tcl-msys-api-03/result.json": "aefc02298614559c73aab69bfe790a31cf4b5cec11158b70b402e38d519ebacc",
    INPUT / "tcl-msys-finish-03/result.json": "ccaff96d6d54bcd77bc5e9e53de062738211a29190a12b9f0a23a883ac633a32",
    INPUT / "native-test-driver-02.manifest.json": "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa",
    PYTHON: "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29",
}
PROFILE = ["basic", "expr", "dict", "list", "regexp", "encoding", "zlib", "load"]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def msys(path):
    path = Path(path).resolve()
    require(path.drive == "C:", "Only the approved private C-drive mount is qualified")
    return "/c/" + path.as_posix()[3:]


def require_memory():
    class Memory(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total", "available", "page_total", "page_available",
                       "virtual_total", "virtual_available", "extended")]]
    value = Memory()
    value.length = ctypes.sizeof(value)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
    api.GlobalMemoryStatusEx.restype = wintypes.BOOL
    if not api.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    require(value.available > 8 * 1024**3, "The Tcl grant requires more than 8 GiB free RAM")
    return value.available


def import_tools():
    sys.path.insert(0, str(ROOT / "tools"))
    import sources
    return sources


def prepare():
    require(not ROOT.exists() or {p.name for p in ROOT.iterdir()} == {"tools"},
            "Preparation requires a fresh root or the exact tools-only failed preparation")
    for path, sha in SEALS.items():
        require(digest(path) == sha, f"Input receipt changed: {path}")
    require(Path(sys.executable).resolve() == PYTHON, "Use the sealed native Python")
    tools = read_json(INPUT / "consumer-tools-03.json")
    for row in tools["files"]:
        require(digest(INPUT / "consumer-tools-03" / row["path"]) == row["sha256"],
                f"Tool snapshot changed: {row['path']}")
    ROOT.mkdir(exist_ok=True)
    if not (ROOT / "tools").exists():
        shutil.copytree(INPUT / "consumer-tools-03", ROOT / "tools")
    sources = import_tools()
    require(sources.inventory(ROOT / "tools") == sources.inventory(INPUT / "consumer-tools-03"),
            "The private imported tools changed")
    runtime = INPUT / "tcl-msys-api-03/relocated"
    runtime_files = sources.inventory(runtime)
    require(runtime_files == read_json(INPUT / "tcl-msys-api-03/result.json")["stage_files"],
            "The complete private runtime differs from its API receipt")
    source = INPUT / "tcl-msys-02/source"
    build = INPUT / "tcl-msys-02/build"
    source_files = sources.inventory(source)
    build_files = sources.inventory(build)
    raw = INPUT / "sqlite-tcl-inputs-01/sources/tcl-msys"
    sources.verify_tree(raw, raw.with_name("tcl-msys.inventory.json"))
    upstream_tests, patched_tests = {}, {}
    for path in (source / "tests").rglob("*"):
        if path.is_file():
            relative = path.relative_to(source)
            if digest(path) == digest(raw / relative):
                upstream_tests[relative.as_posix()] = digest(path)
            else:
                patched_tests[relative.as_posix()] = {
                    "raw_sha256": digest(raw / relative), "patched_sha256": digest(path)}
    require(all("tests/" + name + ".test" in upstream_tests for name in PROFILE),
            "The selected profile must use unchanged upstream tests")
    shutil.copytree(runtime, ROOT / "runtime")
    shutil.copytree(source, ROOT / "source")
    test_bin = ROOT / "test-bin"
    test_bin.mkdir()
    shutil.copyfile(build / "tcltest.exe", test_bin / "tcltest.exe")
    shutil.copytree(build / "dltest", test_bin / "dltest")
    driver = INPUT / "native-test-driver-02"
    sources.verify_tree(driver, driver.with_name(driver.name + ".manifest.json"))
    shutil.copytree(driver, ROOT / "observer")
    shutil.copyfile(driver.with_name(driver.name + ".manifest.json"),
                    ROOT / "observer.manifest.json")
    scripts = ROOT / "scripts"
    scripts.mkdir()
    for name in ("qualify.py", "entry.tcl"):
        shutil.copyfile(Path(__file__).with_name(name), scripts / name)
    from ssh_crypt_consumer import arm64_pe
    pe = [arm64_pe(path) for parent in (ROOT / "runtime", test_bin)
          for path in parent.rglob("*") if path.suffix.lower() in (".exe", ".dll")]
    write_json(ROOT / "inputs.json", {
        "schema": 1, "root": str(ROOT), "receipt_seals": {str(k): v for k, v in SEALS.items()},
        "shared": {str(runtime): runtime_files, str(source): source_files, str(build): build_files},
        "private": {str(path): sources.inventory(path) for path in
                    (ROOT / "runtime", ROOT / "source", test_bin, ROOT / "tools", ROOT / "observer", scripts)},
        "unchanged_upstream_test_files": upstream_tests,
        "preexisting_patched_test_files_not_in_profile": patched_tests, "pe": pe,
        "preserved_preparation_failure": {
            "phase": "before execution or runtime copy",
            "error": "Raw upstream equality rejected preexisting MSYS patch to chanio.test",
            "resolution": "Record all existing patch differences; require unchanged bytes for selected tests",
        },
        "dltest_dll_count": len(list((test_bin / "dltest").glob("*.dll"))),
        "scope": "Exact runtime plus existing tcltest/dltest; no compilation or installation",
    })
    print(json.dumps({"prepared": str(ROOT), "runtime_files": len(runtime_files),
                      "upstream_test_files": len(upstream_tests), "pe_count": len(pe)}))


def verify_inputs():
    sources = import_tools()
    record = read_json(ROOT / "inputs.json")
    for path, sha in record["receipt_seals"].items():
        require(digest(path) == sha, f"Read-only receipt changed: {path}")
    for path, files in {**record["shared"], **record["private"]}.items():
        require(sources.inventory(path) == files, f"Input inventory changed: {path}")
    return True


def environment(output, runtime):
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update({
        "PATH": os.pathsep.join((str(runtime / "usr/bin"),
                                str(Path(env["SystemRoot"]) / "System32"))),
        "TCL_LIBRARY": msys(runtime / "usr/lib/tcl8.6"),
        "TCLLIBPATH": msys(runtime / "usr/lib"),
        "HOME": msys(output), "USERPROFILE": str(output),
        "TEMP": msys(output), "TMP": msys(output), "TMPDIR": msys(output),
        "ERROR_ON_FAILURES": "1", "MAKEFLAGS": "-j1", "OMP_NUM_THREADS": "1",
        "WOARM64_NATIVE_TEST_ROOT": str(ROOT), "WOARM64_NATIVE_ARG_CONVERSION": "none",
        "TCL_QUALIFICATION_WORK": msys(output),
    })
    return env


def creation_filetime(child):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
    api.GetProcessTimes.restype = wintypes.BOOL
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(int(child._handle), *[ctypes.byref(t) for t in times]):
        raise ctypes.WinError(ctypes.get_last_error())
    return times[0].dwHighDateTime << 32 | times[0].dwLowDateTime


def host_launch(request_path):
    import_tools()
    from native_job_runner import noninteractive_error_mode
    require(request_path.resolve().is_relative_to(ROOT), "Host launch request must be private")
    request = read_json(request_path)
    output = Path(request["record"])
    require(output.resolve().is_relative_to(ROOT), "Host process evidence must be private")
    with noninteractive_error_mode(), subprocess.Popen(request["command"], stdin=subprocess.DEVNULL) as child:
        born = creation_filetime(child)
        record = {"pid": child.pid, "creation_filetime": born, "argv": request["command"],
                  "driver": "x64/emulated metadata evaluation only", "log": request["log"]}
        write_json(output, record)
        raw = child.wait()
        write_json(output.with_suffix(".exit.json"), {**record, "raw_exit": raw})
    raise SystemExit(raw if 0 <= raw <= 255 else 255)


def launch(request_path):
    """Ordinary child launch; the unchanged outer observer owns the entire process tree."""
    import_tools()
    from native_job_runner import noninteractive_error_mode
    from ssh_crypt_consumer import inspect_process, validate_loaded
    request = read_json(request_path)
    output = Path(request["output"])
    command = request["command"]
    expected = request["expected_dlls"]
    with noninteractive_error_mode(), subprocess.Popen(command, stdin=subprocess.DEVNULL) as child:
        born = creation_filetime(child)
        write_json(output / "launch.json", {"pid": child.pid, "creation_filetime": born,
                                          "argv": command, "log": str(output / "run.log")})
        deadline = time.monotonic() + 25
        while not (output / "ready").exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.025)
        if (output / "ready").exists():
            identity = inspect_process(child.pid, expected)
            write_json(output / "modules.json", identity)
            normalized = {**identity, "image": identity["image"].removeprefix("\\\\?\\"),
                          "dlls": [{**row, "path": row["path"].removeprefix("\\\\?\\")}
                                   for row in identity["dlls"]]}
            validate_loaded(normalized, child.pid, command[0], expected)
            write_json(output / "validated-modules.json", normalized)
            require(identity["creation_filetime"] == born, "Held child generation changed")
            (output / "continue").write_bytes(b"go\n")
        else:
            raise ValueError("The ordinary native child did not reach its module handshake")
        raw = child.wait()
        write_json(output / "exit.json", {"pid": child.pid, "creation_filetime": born, "raw_exit": raw})
    raise SystemExit(raw if 0 <= raw <= 255 else 255)


def run(name, mode, files=None, match=None, runtime=None, jobs=2, interpreter_name="tclsh8.6.exe"):
    require(jobs in (1, 2), "An explicit one/two-job qualification allocation is required")
    require(interpreter_name in ("tclsh8.6.exe", "tclsh.exe"), "Only the known native Tcl interpreter aliases are allowed")
    sources = import_tools()
    from native_job_runner import run_observed
    import re
    verify_inputs()
    output = ROOT / name
    output.mkdir()
    (output / "native-exits").mkdir()
    shutil.copyfile(Path(__file__), output / "driver.py")
    free_memory = require_memory()
    runtime = Path(runtime) if runtime else ROOT / "runtime"
    require(runtime.resolve().is_relative_to(ROOT), "Runtime must be inside the owned root")
    runtime_files = sources.inventory(runtime)
    if mode == "api":
        executable = runtime / "usr/bin" / interpreter_name
        script = ROOT / "tools/fixtures/native-msys-tcl-core.tcl"
        arguments = [msys(output / "work")]
        dlls = {"libtcl8.6.dll": runtime / "usr/bin/libtcl8.6.dll",
                "msys-2.0.dll": runtime / "usr/bin/msys-2.0.dll",
                "msys-z.dll": runtime / "usr/bin/msys-z.dll",
                "libitcl4.2.2.dll": runtime / "usr/lib/itcl4.2.2/libitcl4.2.2.dll",
                "libtdbc1.1.3.dll": runtime / "usr/lib/tdbc1.1.3/libtdbc1.1.3.dll",
                "libthread2.8.7.dll": runtime / "usr/lib/thread2.8.7/libthread2.8.7.dll"}
    else:
        unchanged = read_json(ROOT / "inputs.json")["unchanged_upstream_test_files"]
        require(all("tests/" + name + ".test" in unchanged for name in files or PROFILE),
                "Selected tests differ from raw upstream; review their original oracles first")
        executable = ROOT / "test-bin/tcltest.exe"
        script = ROOT / "source/tests/all.tcl"
        arguments = ["-singleproc", "1", "-file", " ".join(n + ".test" for n in files or PROFILE),
                     "-tmpdir", msys(output), "-verbose", "beps"]
        if match:
            arguments += ["-match", match]
        dlls = {name: runtime / "usr/bin" / name for name in
                ("libtcl8.6.dll", "msys-2.0.dll", "msys-z.dll")}
    command = [str(executable), msys(ROOT / "scripts/entry.tcl"), mode, msys(script), *arguments]
    request = {"output": str(output), "command": command,
               "expected_dlls": {name: {"path": str(path), "sha256": digest(path)}
                                 for name, path in dlls.items()}}
    write_json(output / "request.json", request)
    report = {"schema": 1, "status": "failed", "scope": mode, "command": command,
              "driver": {"path": str(output / "driver.py"), "sha256": digest(output / "driver.py")},
              "free_memory_before": free_memory, "aggregate_test_job_limit": jobs,
              "full_upstream_suite": False, "test_case_skip_flags": [],
              "files": files or PROFILE if mode != "api" else []}
    try:
        report["process"] = run_observed(
            [sys.executable, "-B", output / "driver.py", "launch", output / "request.json"],
            cwd=output, env=environment(output, runtime), log_path=output / "run.log",
            result_path=output / "native-job.json", relay_records=output / "native-exits",
            timeout=600, driver_prefix=ROOT / "observer")
        text = (output / "run.log").read_text(errors="replace")
        summaries = re.findall(r"(\S+):\s+Total\s+(\d+)\s+Passed\s+(\d+)\s+Skipped\s+(\d+)\s+Failed\s+(\d+)", text)
        report["summaries"] = [dict(zip(("name", "total", "passed", "skipped", "failed"),
                                      (s[0], *map(int, s[1:])))) for s in summaries]
        report["failed_tests"] = sorted(set(re.findall(r"^==== (\S+).* FAILED$", text, re.MULTILINE)))
        report["skipped_tests"] = re.findall(r"^\+\+\+\+ (\S+) SKIPPED: (.+)$", text, re.MULTILINE)
        report["file_errors"] = re.findall(r"^Test file error: (.+)$", text, re.MULTILINE)
        api_passed = "native-msys-tcl-core-api-passed" in text
        suite_passed = bool(summaries) and all(int(s[4]) == 0 for s in summaries) and not report["file_errors"]
        semantic = api_passed if mode == "api" else suite_passed
        report["semantic_passed"] = semantic
        report["status"] = "passed" if report["process"]["passed"] and semantic else "failed"
        for name in ("launch", "modules", "validated-modules", "exit", "native-job"):
            path = output / (name + ".json")
            if path.exists():
                report[name] = {"path": str(path), "sha256": digest(path)}
    finally:
        require(sources.inventory(runtime) == runtime_files, "Executed provider runtime changed")
        report["runtime"] = {"path": str(runtime), "files": len(runtime_files), "unchanged": True}
        report["inputs_unchanged"] = verify_inputs()
        report["free_memory_after"] = require_memory()
        write_json(output / "result.json", report)
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare")
    sub.add_parser("verify")
    child = sub.add_parser("launch")
    child.add_argument("request", type=Path)
    host = sub.add_parser("host-launch")
    host.add_argument("request", type=Path)
    execute = sub.add_parser("run")
    execute.add_argument("name")
    execute.add_argument("--mode", choices=("suite", "api"), required=True)
    execute.add_argument("--files", nargs="+")
    execute.add_argument("--match")
    execute.add_argument("--runtime", type=Path)
    execute.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    batch = sub.add_parser("profile")
    batch.add_argument("name")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "verify":
        print(verify_inputs())
    elif args.action == "launch":
        launch(args.request)
    elif args.action == "host-launch":
        host_launch(args.request)
    elif args.action == "profile":
        results = [run(args.name + "-" + name, "suite", [name]) for name in PROFILE]
        if any(result["status"] != "passed" for result in results):
            raise SystemExit(1)
    else:
        result = run(args.name, args.mode, args.files, args.match, args.runtime, args.jobs)
        if result["status"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
