"""Independent final ZIP readback, running only the exact committed verifier."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(r"C:\ag-mvp-independent-sqlite-20260911")
PRODUCER = Path(r"C:\ag-mvp-f6-20260911")
ARCHIVE_NAME = "arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip"
SOURCES = {
    "archive": (PRODUCER / "first-artifact-901256b" / ARCHIVE_NAME,
                "7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854"),
    "receipt": (PRODUCER / "first-artifact-901256b/artifact-receipt.json",
                "dfdce4e6ef60896aca0d810c165d6ed9bfbc5a6e9b9f7adc6a270a66c4bd33b0"),
    "packet": (PRODUCER / "mvp-source-901256b.zip",
               "21ece7da0860cebb067af8b45a01b959ee9cd3dff4be11056bb0cc7834133f83"),
}
FIXTURE = ROOT / "replay-01/ssh-fixture-driver"
FIXTURE_MANIFEST = ROOT / "replay-01/ssh-fixture-driver.files.json"
FIXTURE_SHA = "b0ae85b2d5d0d1720fd1f3da8815962776559ba0a19401f93b85762c0a2fa74c"
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"
COMMIT = "901256ba4e9fe48b6babaa51849733d8189b5e14"
TREE = "1f0bd4fa2fc04e1b484ff5eaa2e22a5829cf321f"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sealed(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Immutable input seal differs: {path}")


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def memory():
    class Status(C.Structure):
        _fields_ = [("length", W.DWORD), ("load", W.DWORD),
                    *[(name, C.c_uint64) for name in ("total", "available", "page", "available_page",
                                                    "virtual", "available_virtual", "extended")]]
    status = Status()
    status.length = C.sizeof(status)
    if not C.windll.kernel32.GlobalMemoryStatusEx(C.byref(status)):
        raise C.WinError(C.get_last_error())
    available = status.available / 1024**3
    if available <= 8:
        raise ValueError(f"Free RAM must exceed 8 GiB, observed {available}")
    return available


def process_identity(pid=None):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid) if pid else kernel.GetCurrentProcess()
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        times = [W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[C.byref(t) for t in times]):
            raise C.WinError(C.get_last_error())
        return {"pid": pid or os.getpid(),
                "creation_filetime": times[0].dwLowDateTime | times[0].dwHighDateTime << 32}
    finally:
        if pid:
            kernel.CloseHandle(handle)


def safe(name):
    if not name or "\\" in name or ":" in name or any(p in ("", ".", "..", ".git") for p in name.split("/")):
        raise ValueError(f"Unsafe or excluded path: {name}")
    return name


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Unexpected source/fixture link: {path}")
        if path.is_file():
            name = safe(path.relative_to(root).as_posix())
            result[name] = {"size": path.stat().st_size, "sha256": sha(path)}
    return result


def tools(work):
    directory = work / "source/arm64-git-recovery/native/mvp"
    sys.path.insert(0, str(directory))
    sys.path.insert(1, str(directory.parent))
    import artifact
    import bounded_process
    return directory, artifact, bounded_process


def prepare(work, pwsh):
    if not work.is_relative_to(ROOT) or work == ROOT or work.exists():
        raise ValueError("Fresh owned final readback directory required")
    sealed(sys.executable, PYTHON_SHA)
    sealed(FIXTURE_MANIFEST, FIXTURE_SHA)
    expected_fixture = json.loads(FIXTURE_MANIFEST.read_text())["files"]
    if inventory(FIXTURE) != expected_fixture:
        raise ValueError("Existing independent SSH fixture changed")
    for path, expected in SOURCES.values():
        sealed(path, expected)
    receipt = json.loads(SOURCES["receipt"][0].read_text())
    if (receipt["sha256"] != SOURCES["archive"][1] or receipt["size"] != 186366963
            or receipt["files"] != 12392 or receipt["directories"] != 568
            or receipt["source"]["commit"] != COMMIT or receipt["source"]["tree"] != TREE):
        raise ValueError("Detached receipt identity/count contract differs")
    work.mkdir()
    report = {"schema": 1, "status": "failed", "launcher": process_identity(),
              "native_cases_launched": 0, "free_ram_gib": memory(), "source_commit": COMMIT,
              "source_tree": TREE, "files": {}, "scope": "Preparation of independent final ZIP readback only"}
    write(work / "prepare-launch.json", report)
    try:
        copied = work / "sealed inputs"
        copied.mkdir()
        for label, (path, expected) in SOURCES.items():
            destination = copied / path.name
            shutil.copyfile(path, destination)
            sealed(destination, expected)
            sealed(path, expected)
            report["files"][label] = {"original": str(path), "copy": str(destination),
                                      "sha256": expected, "size": destination.stat().st_size}
        source = work / "source"
        source.mkdir()
        with zipfile.ZipFile(report["files"]["packet"]["copy"]) as archive:
            seen = set()
            for item in archive.infolist():
                name = item.filename.rstrip("/")
                if not name:
                    continue
                safe(name)
                if name.casefold() in seen:
                    raise ValueError("Duplicate source packet member")
                seen.add(name.casefold())
                if (item.external_attr >> 16) & 0o170000 not in (0, 0o040000, 0o100000):
                    raise ValueError("Unexpected source packet link or object")
                target = source / name
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as incoming, target.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
        directory, artifact, _ = tools(work)
        fixture = work / "ssh-fixture-driver"
        shutil.copytree(FIXTURE, fixture)
        shutil.copyfile(FIXTURE_MANIFEST, work / FIXTURE_MANIFEST.name)
        if inventory(fixture) != expected_fixture or inventory(FIXTURE) != expected_fixture:
            raise ValueError("Private SSH fixture copy/source differs")
        fixture_pe = {name: artifact.pe_identity(fixture / name) for name in expected_fixture
                      if Path(name).suffix.lower() in (".pyd", ".exe", ".dll")}
        if any(p["machine"] != "0xAA64" for p in fixture_pe.values()):
            raise ValueError("SSH fixture contains a foreign-architecture PE")
        if artifact.pe_identity(pwsh)["machine"] != "0xAA64":
            raise ValueError("Native PowerShell required")
        report.update(status="independent-final-zip-inputs-prepared-not-executed",
                      source_files=inventory(source), fixture_files=expected_fixture, fixture_pe=fixture_pe,
                      fixture_manifest_sha256=FIXTURE_SHA,
                      pwsh={"path": str(pwsh), "sha256": sha(pwsh)},
                      native_python={"path": sys.executable, "sha256": PYTHON_SHA},
                      verifier_sha256=sha(directory / "verify_handoff.py"),
                      inputs_before_copy_after_equal=True)
    finally:
        write(work / "prepare.json", report)
    print(json.dumps({"status": report["status"], "prepare_sha256": sha(work / "prepare.json"),
                      "verifier": str(directory / "verify_handoff.py")}), flush=True)


def verify(work, expected):
    if not work.is_relative_to(ROOT) or work == ROOT or (work / "result.json").exists():
        raise ValueError("Unused owned final readback preparation required")
    sealed(work / "prepare.json", expected)
    prepared = json.loads((work / "prepare.json").read_text())
    if prepared["status"] != "independent-final-zip-inputs-prepared-not-executed":
        raise ValueError("Complete sealed preparation required")
    directory, artifact, bounded = tools(work)
    if inventory(work / "source") != prepared["source_files"]:
        raise ValueError("Committed verifier export changed")
    fixture = work / "ssh-fixture-driver"
    if inventory(fixture) != prepared["fixture_files"]:
        raise ValueError("Independent SSH fixture changed")
    for row in prepared["files"].values():
        sealed(row["copy"], row["sha256"])
        sealed(row["original"], row["sha256"])
    sealed(sys.executable, PYTHON_SHA)
    pwsh = Path(prepared["pwsh"]["path"])
    sealed(pwsh, prepared["pwsh"]["sha256"])
    manifest = work / FIXTURE_MANIFEST.name
    sealed(manifest, FIXTURE_SHA)
    verification = work / "final ZIP verification"
    command = [
        sys.executable, "-B", str(directory / "verify_handoff.py"),
        "--archive", prepared["files"]["archive"]["copy"],
        "--receipt", prepared["files"]["receipt"]["copy"],
        "--receipt-sha256", SOURCES["receipt"][1],
        "--output", str(verification), "--pwsh", str(pwsh),
        "--ssh-driver", str(fixture), "--ssh-driver-manifest", str(manifest),
        "--ssh-driver-manifest-sha256", FIXTURE_SHA,
    ]
    report = {
        "schema": 1, "passed": False, "launcher": process_identity(), "command": command,
        "maximum_concurrent_native_cases": 1, "allocation": "One slot borrowed from f6's existing six, not extra global quota",
        "prepare_sha256": expected, "source_commit": COMMIT, "source_tree": TREE,
        "verifier_sha256": sha(directory / "verify_handoff.py"), "controller_sha256": sha(__file__),
        "archive_sha256": SOURCES["archive"][1], "detached_receipt_sha256": SOURCES["receipt"][1],
        "scope": "Independent final limited-engineering ZIP custody/readback/recreation and shipped native execution; not full release, new provider admission, all-short-descendant module completeness, or observer decoder qualification",
        "minimum_free_ram_gib": memory(),
    }
    write(work / "launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "command": command,
                      "log": str(work / "verifier.controller.log")}), flush=True)
    env = {name: os.environ[name] for name in
           ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA", "USERNAME", "USERDOMAIN")
           if name in os.environ}
    env.update(PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
               HOME=str(work / "controller-home"), USERPROFILE=str(work / "controller-home"),
               TMP=str(work / "controller-temp"), TEMP=str(work / "controller-temp"),
               PYTHONDONTWRITEBYTECODE="1", MAKEFLAGS="-j1", OMP_NUM_THREADS="1")
    for name in ("controller-home", "controller-temp"):
        (work / name).mkdir()
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetErrorMode.restype = W.UINT
    kernel.SetErrorMode.argtypes = [W.UINT]
    previous_error_mode = kernel.GetErrorMode()
    kernel.SetErrorMode(previous_error_mode | 0x8003)
    try:
        def started(pid):
            row = {**process_identity(pid), "command": command, "controller_log": str(work / "verifier.controller.log")}
            write(work / "verifier.started.json", row)
            print(json.dumps({"started": row}), flush=True)
        with (work / "verifier.controller.log").open("xb") as log:
            report["process"] = bounded.run(command, cwd=work, env=env, log=log, timeout=2100, on_started=started)
        result_path = verification / "result.json"
        if not result_path.is_file():
            raise ValueError("Committed verifier did not produce its result")
        result = json.loads(result_path.read_text())
        report["verifier_result"] = {"path": str(result_path), "sha256": sha(result_path), "record": result}
        expected_names = ("recreation", "behavior", "launcher", "ssh")
        if tuple(step["name"] for step in result.get("steps", [])) != expected_names:
            raise ValueError("Final verifier did not execute all four expected scopes")
        if not result["passed"] or not report["process"]["passed"]:
            raise ValueError("Committed verifier failed or did not drain; original evidence retained")
        for step in result["steps"]:
            process = step["process"]
            if not process["passed"] or process["exit"] != 0 or process["active_at_boundary"] or process["remaining_process_ids"]:
                raise ValueError(f"Verifier scope did not complete/drain: {step['name']}")
        behavior = json.loads((verification / "behavior/result.json").read_text())
        if len(behavior["cases"]) != 12 or any(case[1] != "PASS" for case in behavior["cases"]):
            raise ValueError("The actual twelve-case moved behavior scope did not pass")
        launcher_result = json.loads((verification / "launcher/result.json").read_text())
        if launcher_result["passed"] is not True:
            raise ValueError("Actual extracted CMD launcher did not pass")
        ssh = json.loads((verification / "ssh/result.json").read_text())
        ssh_cases = {case["name"]: case for case in ssh["cases"]}
        if set(ssh_cases) != {"correct-host-key", "wrong-host-key", "git-encrypted-clone",
                              "git-encrypted-fetch", "git-wrong-host-key"} or not all(c["passed"] for c in ssh_cases.values()):
            raise ValueError("Complete encrypted SSH positive/negative Git fixture did not pass")
        clone = ssh_cases["git-encrypted-clone"]
        if (clone["binary_bytes"] != 131072 or clone["observed_binary_sha256"] != clone["expected_binary_sha256"]
                or clone["expected_head"] != clone["observed_head"]):
            raise ValueError("Independent encrypted Git clone payload differs")
        recreated = verification / "recreated.zip"
        sealed(recreated, SOURCES["archive"][1])
        if recreated.stat().st_size != 186366963:
            raise ValueError("Recreated archive size differs")
        extraction = verification / "fresh moved Git Bash extraction"
        actual = artifact.inventory(extraction)
        with zipfile.ZipFile(prepared["files"]["archive"]["copy"]) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            dirs = [item for item in archive.infolist() if item.is_dir()]
            if len(files) != 12392 or len(dirs) != 568:
                raise ValueError("Final ZIP file/directory counts differ")
            explicit_directories = [safe(item.filename.rstrip("/")) for item in dirs]
        if len(actual) != 12392:
            raise ValueError("Extracted file count differs")
        pes = {name: row for name, row in actual.items() if row["format"] != "non-PE"}
        if len(pes) != 327 or any(row["machine"] != "0xAA64" for row in pes.values()):
            raise ValueError("Actual extracted PE count or machine differs")
        if any(not (extraction / name).is_dir() for name in explicit_directories):
            raise ValueError("An explicit final ZIP directory is absent after extraction")
        report["independent_readback"] = {
            "files": len(actual), "directories": len(explicit_directories), "arm64_pe_count": len(pes),
            "recreated_archive_sha256": sha(recreated), "recreated_archive_size": recreated.stat().st_size,
            "all_explicit_directories_materialized": True,
            "behavior_cases": behavior["cases"], "cmd_launcher": launcher_result,
            "ssh_cases": ssh["cases"], "ssh_server_events_sha256": sha(verification / "ssh/server-events.json"),
        }
        report["input_readbacks"] = {}
        for label, row in prepared["files"].items():
            sealed(row["original"], row["sha256"])
            sealed(row["copy"], row["sha256"])
            report["input_readbacks"][label] = {**row, "original_unchanged": True, "copy_unchanged": True}
        report["source_export_unchanged"] = inventory(work / "source") == prepared["source_files"]
        report["private_ssh_fixture_unchanged"] = inventory(fixture) == prepared["fixture_files"]
        report["original_ssh_fixture_unchanged"] = inventory(FIXTURE) == prepared["fixture_files"]
        sealed(FIXTURE_MANIFEST, FIXTURE_SHA)
        sealed(manifest, FIXTURE_SHA)
        if not all(report[key] for key in ("source_export_unchanged", "private_ssh_fixture_unchanged", "original_ssh_fixture_unchanged")):
            raise ValueError("An independent replay input changed")
        report["owned_jobs_drained"] = (report["process"]["active_at_boundary"] == 0
                                        and not report["process"]["remaining_process_ids"])
        report["passed"] = report["owned_jobs_drained"]
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        kernel.SetErrorMode(previous_error_mode)
        key = verification / "ssh/client-key"
        if key.is_file():
            report["ephemeral_fixture_key"] = {"sha256": sha(key), "removed": True}
            key.unlink()
        write(work / "result.json", report)
    print(json.dumps({"passed": report["passed"], "result": str(work / "result.json"),
                      "sha256": sha(work / "result.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.phase == "prepare":
        if args.pwsh is None:
            parser.error("--pwsh required for preparation")
        prepare(args.work.resolve(), args.pwsh.resolve())
    else:
        if args.sha256 is None:
            parser.error("--sha256 required for execution")
        verify(args.work.resolve(), args.sha256)
