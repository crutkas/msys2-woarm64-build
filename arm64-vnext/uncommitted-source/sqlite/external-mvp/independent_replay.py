"""Independent, source-read-only replay of the frozen limited MVP candidate."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile

ROOT = Path(r"C:\ag-mvp-independent-sqlite-20260911")
CANDIDATE = Path(r"C:\ag-mvp-f6-20260911\limited-candidate-02")
MANIFEST = CANDIDATE.with_name(CANDIDATE.name + ".manifest.json")
MANIFEST_SHA = "708394d8b303874307db541d278b9891d2b1fde1a9948e5266a3a992555e33f1"
PACKET = Path(r"C:\ag-mvp-f6-20260911\mvp-source-fccdb7b.zip")
PACKET_SHA = "9672c3356df00f01ca0472d2b8e261cb3ce822bec926b2f1d8a7729c3b4ffe83"
FIXTURE = Path(r"C:\ag-mvp-f6-20260911\ssh-fixture-driver")
FIXTURE_MANIFEST = FIXTURE.with_name(FIXTURE.name + ".files.json")
FIXTURE_SHA = "b0ae85b2d5d0d1720fd1f3da8815962776559ba0a19401f93b85762c0a2fa74c"
INSTALL = FIXTURE.with_name(FIXTURE.name + ".install.json")
GATE = Path(r"C:\Users\crutkasLocal\.copilot\session-state\e31c3dfa-2118-401e-a532-d9bb25571f44\files\Test-NativeArm64Process.ps1")
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"
COMMIT = "fccdb7b97945f691c3f6ed231ad907719003f272"
TREE = "61c7aa257b75439d83f128c340018b4c0a80f6e6"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def identity():
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    times = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *[C.byref(t) for t in times]):
        raise C.WinError(C.get_last_error())
    return {"pid": os.getpid(), "creation_filetime": times[0].dwLowDateTime | times[0].dwHighDateTime << 32,
            "argv": sys.orig_argv}


def memory():
    class Status(C.Structure):
        _fields_ = [("length", W.DWORD), ("load", W.DWORD),
                    *[(name, C.c_uint64) for name in ("physical", "available", "page", "available_page",
                                                    "virtual", "available_virtual", "extended")]]
    status = Status()
    status.length = C.sizeof(status)
    if not C.windll.kernel32.GlobalMemoryStatusEx(C.byref(status)):
        raise C.WinError(C.get_last_error())
    gib = status.available / 1024 ** 3
    if gib <= 8:
        raise ValueError(f"Free RAM floor violated: {gib}")
    return gib


def safe(name):
    if not name or "\\" in name or ":" in name or any(p in ("", ".", "..", ".git") for p in name.split("/")):
        raise ValueError(f"Unsafe or excluded input path: {name}")
    if PurePosixPath(name).is_absolute():
        raise ValueError("Absolute input path")
    return name


def plain_inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Unexpected input link: {path}")
        if path.is_file():
            name = safe(path.relative_to(root).as_posix())
            result[name] = {"size": path.stat().st_size, "sha256": sha(path)}
    return result


def require_seal(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Seal differs: {path}")


def load_tools(work):
    directory = work / "source/arm64-git-recovery/native/mvp"
    sys.path.insert(0, str(directory))
    sys.path.insert(1, str(directory.parent))
    import artifact
    import bounded_process
    return directory, artifact, bounded_process


def candidate_inventory(artifact, root, expected):
    actual = artifact.inventory(root)
    projected = {}
    for name, row in expected.items():
        safe(name)
        if row["entry_type"] != "file":
            raise ValueError("Only frozen resolved candidate files are supported")
        projected[name] = {k: row[k] for k in ("size", "sha256", "format", "machine", "managed", "imports", "delay_imports")
                           if k in row}
    if actual != projected:
        changed = sorted(p for p in actual.keys() | projected.keys() if actual.get(p) != projected.get(p))
        raise ValueError(f"Candidate bytes or actual PE metadata differ: {changed[:12]}")
    pe_files = {name: row for name, row in actual.items() if row["format"] != "non-PE"}
    if not pe_files or any(row["machine"] != "0xAA64" for row in pe_files.values()):
        raise ValueError("Non-AA64 candidate PE detected")
    return actual, pe_files


def prepare(work, pwsh):
    if work.exists() or not work.is_relative_to(ROOT):
        raise ValueError("Fresh owned replay root required")
    for path, seal in ((MANIFEST, MANIFEST_SHA), (PACKET, PACKET_SHA), (FIXTURE_MANIFEST, FIXTURE_SHA),
                       (Path(sys.executable), PYTHON_SHA)):
        require_seal(path, seal)
    source_manifest = json.loads(MANIFEST.read_text())
    if source_manifest["top_source"]["commit"] != COMMIT or source_manifest["top_source"]["tree"] != TREE:
        raise ValueError("Frozen assembly source identity differs")
    work.mkdir()
    write(work / "prepare-launch.json", {"launcher": identity(), "free_ram_gib": memory(), "native_cases": 0})
    report = {"schema": 1, "status": "failed", "candidate_source": str(CANDIDATE),
              "manifest_sha256": MANIFEST_SHA, "source_packet_sha256": PACKET_SHA,
              "source_commit": COMMIT, "source_tree": TREE, "native_cases_launched": 0,
              "scope": "One independent spaced-root copy; final limited candidate bytes, not an archive or admission"}
    try:
        source = work / "source"
        source.mkdir()
        with zipfile.ZipFile(PACKET) as archive:
            seen = set()
            for item in archive.infolist():
                name = item.filename.rstrip("/")
                if not name:
                    continue
                safe(name)
                if name.casefold() in seen:
                    raise ValueError("Duplicate source packet member")
                seen.add(name.casefold())
                mode = (item.external_attr >> 16) & 0o170000
                if mode not in (0, 0o040000, 0o100000):
                    raise ValueError("Source packet contains unsupported links")
                target = source / name
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as incoming, target.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
        tools, artifact, _ = load_tools(work)
        report["source_files"] = plain_inventory(source)
        original, pe_files = candidate_inventory(artifact, CANDIDATE, source_manifest["files"])
        target = work / "moved candidate with spaces"
        target.mkdir()
        for index, (name, row) in enumerate(original.items(), 1):
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CANDIDATE / name, destination)
            if destination.stat().st_size != row["size"] or sha(destination) != row["sha256"]:
                raise ValueError(f"Independent copy differs: {name}")
            if index % 2000 == 0:
                print(f"Copied and hashed {index}/{len(original)} candidate files", flush=True)
        for name in ("tmp", "var/tmp", "etc", "home"):
            (target / name).mkdir(parents=True, exist_ok=True)
        copied, copied_pe = candidate_inventory(artifact, target, source_manifest["files"])
        candidate_inventory(artifact, CANDIDATE, source_manifest["files"])
        fixture_manifest = json.loads(FIXTURE_MANIFEST.read_text())
        if plain_inventory(FIXTURE) != fixture_manifest["files"]:
            raise ValueError("SSH fixture inventory differs")
        fixture_copy = work / "ssh-fixture-driver"
        shutil.copytree(FIXTURE, fixture_copy)
        if plain_inventory(fixture_copy) != fixture_manifest["files"] or plain_inventory(FIXTURE) != fixture_manifest["files"]:
            raise ValueError("SSH fixture copy/source changed")
        fixture_pe = {name: artifact.pe_identity(fixture_copy / name) for name in fixture_manifest["files"]
                      if Path(name).suffix.lower() in (".exe", ".dll", ".pyd")}
        if any(row["machine"] != "0xAA64" for row in fixture_pe.values()):
            raise ValueError("Foreign-architecture SSH controller module")
        gate_copy = work / GATE.name
        shutil.copyfile(GATE, gate_copy)
        if sha(gate_copy) != sha(GATE):
            raise ValueError("Native process gate copy changed")
        if artifact.pe_identity(pwsh)["machine"] != "0xAA64":
            raise ValueError("PowerShell controller must be native ARM64")
        for input_path in (MANIFEST, FIXTURE_MANIFEST, INSTALL):
            shutil.copyfile(input_path, work / input_path.name)
        report.update(status="independent-candidate-prepared-not-executed", root=str(target),
                      files=copied, pe_files=copied_pe, file_count=len(copied), pe_count=len(copied_pe),
                      fixture_files=fixture_manifest["files"], fixture_pe=fixture_pe,
                      fixture_install_sha256=sha(INSTALL), process_gate_sha256=sha(gate_copy),
                      pwsh={"path": str(pwsh), "sha256": sha(pwsh)},
                      controller_python={"path": sys.executable, "sha256": PYTHON_SHA},
                      source_before_after_equal=True, candidate_copy_before_after_equal=True,
                      limitations=source_manifest["limitations"], free_ram_gib_after=memory())
    finally:
        write(work / "prepare.json", report)
    print(json.dumps({"status": report["status"], "manifest": str(work / "prepare.json"),
                      "sha256": sha(work / "prepare.json"), "files": report["file_count"], "pes": report["pe_count"]}), flush=True)


def replay(work, expected):
    require_seal(work / "prepare.json", expected)
    prepared = json.loads((work / "prepare.json").read_text())
    if prepared["status"] != "independent-candidate-prepared-not-executed" or (work / "result.json").exists():
        raise ValueError("An unused, verified independent replay root is required")
    tools, artifact, bounded = load_tools(work)
    if plain_inventory(work / "source") != prepared["source_files"]:
        raise ValueError("Committed replay source export changed")
    root = Path(prepared["root"])
    if artifact.inventory(root) != prepared["files"]:
        raise ValueError("Private candidate changed before execution")
    fixture = work / "ssh-fixture-driver"
    if plain_inventory(fixture) != prepared["fixture_files"]:
        raise ValueError("Private SSH fixture changed")
    pwsh = Path(prepared["pwsh"]["path"])
    require_seal(pwsh, prepared["pwsh"]["sha256"])
    require_seal(Path(sys.executable), PYTHON_SHA)
    gate = work / GATE.name
    require_seal(gate, prepared["process_gate_sha256"])
    report = {"schema": 1, "passed": False, "launcher": identity(), "max_concurrent_native_cases": 1,
              "root": str(root), "candidate_manifest_sha256": MANIFEST_SHA, "prepare_sha256": expected,
              "source_commit": COMMIT, "source_tree": TREE, "steps": [],
              "scope": "Independent exact final limited candidate at a new spaced path; no final archive/admission/all-short-child module or negative-observer claim",
              "native_cases_serial": True, "limitations": prepared["limitations"]}
    write(work / "replay-launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "root": str(root), "evidence": str(work)}), flush=True)
    env = {name: os.environ[name] for name in
           ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA", "USERNAME", "USERDOMAIN") if name in os.environ}
    env.update(PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
               HOME=str(work / "controller-home"), USERPROFILE=str(work / "controller-home"),
               TMP=str(work / "controller-temp"), TEMP=str(work / "controller-temp"),
               PYTHONDONTWRITEBYTECODE="1", MAKEFLAGS="-j1", OMP_NUM_THREADS="1")
    for directory in ("controller-home", "controller-temp"):
        (work / directory).mkdir()
    commands = [
        ("behavior", [sys.executable, "-B", tools / "run_behavior.py", "--root", root, "--output", work / "behavior"], 720),
        ("ssh", [sys.executable, "-B", tools / "controlled_ssh.py", "--client", root / "usr/bin/ssh.exe",
                 "--bash", root / "usr/bin/bash.exe", "--test-driver", fixture, "--output", work / "ssh", "--pwsh", pwsh], 180),
        ("attestation", [sys.executable, "-B", tools / "attest_entrypoints.py", "--root", root,
                         "--output", work / "attestation", "--pwsh", pwsh, "--process-gate", gate], 240),
    ]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetErrorMode.restype = W.UINT
    kernel.SetErrorMode.argtypes = [W.UINT]
    previous = kernel.GetErrorMode()
    kernel.SetErrorMode(previous | 0x8003)
    try:
        for name, command, timeout in commands:
            step = {"name": name, "command": list(map(str, command)), "free_ram_gib_before": memory()}
            with (work / f"{name}.controller.log").open("xb") as log:
                def started(pid):
                    write(work / f"{name}.started.json", {"pid": pid, "command": step["command"]})
                    print(json.dumps({"started": name, "pid": pid, "log": str(work / f"{name}.controller.log")}), flush=True)
                step["process"] = bounded.run(command, cwd=work, env=env, log=log, timeout=timeout, on_started=started)
            result_path = work / name / "result.json"
            if not result_path.is_file():
                step["passed"] = False
                step["error"] = "Committed replay did not produce its required result"
            else:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                step["result_sha256"] = sha(result_path)
                step["result"] = result
                step["passed"] = step["process"]["passed"] and result.get("passed") is True
                if name == "behavior":
                    cases = result.get("cases", [])
                    step["passed"] = step["passed"] and len(cases) == 12 and all(row[1] == "PASS" for row in cases)
                elif name == "ssh":
                    cases = result.get("cases", [])
                    step["passed"] = step["passed"] and len(cases) == 2 and all(row["passed"] for row in cases)
                else:
                    cases = result.get("cases", [])
                    step["passed"] = step["passed"] and {row["name"] for row in cases} == {"bash", "git", "https-helper", "python"}
                    for case in cases:
                        if not case["native_process"]["Passed"] or case["raw_exit"] != 0:
                            step["passed"] = False
                        for module in case["modules"]:
                            name_in_payload = module.get("payload_path")
                            if name_in_payload and (module["sha256"] != prepared["files"][name_in_payload]["sha256"]
                                                    or module["machine"] != "0xAA64"):
                                step["passed"] = False
            report["steps"].append(step)
            write(work / f"{name}.independent.json", step)
        report["private_candidate_unchanged"] = artifact.inventory(root) == prepared["files"]
        manifest = json.loads(MANIFEST.read_text())
        candidate_inventory(artifact, CANDIDATE, manifest["files"])
        require_seal(MANIFEST, MANIFEST_SHA)
        require_seal(PACKET, PACKET_SHA)
        report["original_candidate_unchanged"] = True
        report["source_export_unchanged"] = plain_inventory(work / "source") == prepared["source_files"]
        report["fixture_unchanged"] = plain_inventory(fixture) == prepared["fixture_files"]
        report["passed"] = (len(report["steps"]) == 3 and all(s["passed"] for s in report["steps"])
                            and report["private_candidate_unchanged"] and report["source_export_unchanged"]
                            and report["fixture_unchanged"])
        report["owned_jobs_drained"] = all(s["process"]["active_at_boundary"] == 0
                                         and not s["process"]["remaining_process_ids"] for s in report["steps"])
        report["passed"] = report["passed"] and report["owned_jobs_drained"]
    finally:
        kernel.SetErrorMode(previous)
        # These are exclusively generated loopback fixture credentials, never
        # product files or real user credentials. Keep hashes, not private keys.
        key = work / "ssh/client-key"
        if key.is_file():
            report["ephemeral_fixture_private_key"] = {"sha256": sha(key), "removed": True}
            key.unlink()
        write(work / "result.json", report)
    print(json.dumps({"passed": report["passed"], "result": str(work / "result.json"), "sha256": sha(work / "result.json")}), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "replay"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path)
    parser.add_argument("--sha256")
    options = parser.parse_args()
    if options.phase == "prepare":
        if options.pwsh is None:
            parser.error("--pwsh required for preparation")
        prepare(options.work.resolve(), options.pwsh.resolve())
    else:
        if options.sha256 is None:
            parser.error("--sha256 required for replay")
        replay(options.work.resolve(), options.sha256)
