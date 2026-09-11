"""Attest live, responsive native entrypoints and their actual loaded modules without injecting code."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from artifact import ArtifactError, pe_identity, sha256, write_json


class ModuleEntry(C.Structure):
    _fields_ = [("size", W.DWORD), ("id", W.DWORD), ("pid", W.DWORD),
                ("global_usage", W.DWORD), ("process_usage", W.DWORD),
                ("base", C.POINTER(C.c_byte)), ("length", W.DWORD), ("module", W.HMODULE),
                ("name", W.WCHAR * 256), ("path", W.WCHAR * 260)]


def read_line(stream):
    result = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: result.put(stream.readline()), daemon=True).start()
    try:
        return result.get(timeout=20)
    except queue.Empty as error:
        raise ArtifactError("Native entrypoint did not respond within its protocol deadline") from error


def loaded_modules(pid, root):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(ModuleEntry)]
    kernel.Module32FirstW.restype = W.BOOL
    kernel.Module32NextW.argtypes = [W.HANDLE, C.POINTER(ModuleEntry)]
    kernel.Module32NextW.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if snapshot == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    rows = []
    system = (Path(os.environ["SystemRoot"]) / "System32").resolve()
    try:
        entry = ModuleEntry()
        entry.size = C.sizeof(entry)
        if not kernel.Module32FirstW(snapshot, C.byref(entry)):
            raise C.WinError(C.get_last_error())
        while True:
            path = Path(entry.path).resolve()
            location = "payload" if path.is_relative_to(root) else "Windows system" if path.is_relative_to(system) else "outside-approved-roots"
            pe = pe_identity(path)
            if location == "outside-approved-roots" or (location == "payload" and pe["machine"] != "0xAA64"):
                raise ArtifactError(f"Unexpected loaded module: {path}: {pe['machine']}")
            rows.append({"path": str(path), "payload_path": path.relative_to(root).as_posix() if location == "payload" else None,
                         "size": path.stat().st_size, "sha256": sha256(path), "machine": pe["machine"], "location": location})
            if not kernel.Module32NextW(snapshot, C.byref(entry)):
                error = C.get_last_error()
                if error != 18:
                    raise C.WinError(error)
                break
    finally:
        kernel.CloseHandle(snapshot)
    if not rows:
        raise ArtifactError("No loaded modules observed")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--process-gate", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Fresh process attestation output required")
    output.mkdir(parents=True)
    (output / "home").mkdir()
    empty = output / "home/config"
    empty.write_bytes(b"")
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA") if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (root / "mingwarm64/bin", root / "usr/bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
                "GIT_TERMINAL_PROMPT": "0", "MSYSTEM": "MINGWARM64", "MSYS": "winsymlinks:sys"})
    git = root / "mingwarm64/bin/git.exe"
    init = subprocess.run([git, "init", "--bare", output / "repo.git"], env=env, capture_output=True, timeout=30)
    if init.returncode:
        raise ArtifactError("Attestation fixture repository creation failed")
    cases = [
        ("bash", [root / "usr/bin/bash.exe", "--noprofile", "--norc", "-c", "printf 'ready\\n'; IFS= read -r reply; test \"$reply\" = finish"], b"", b"ready\n", b"finish\n"),
        ("git", [git, "-C", output / "repo.git", "cat-file", "--batch"], b"0000000000000000000000000000000000000000\n",
         b"0000000000000000000000000000000000000000 missing\n", b""),
        ("https-helper", [root / "mingwarm64/libexec/git-core/git-remote-https.exe", "origin", "https://github.com/octocat/Hello-World.git"],
         b"capabilities\n", None, b"\n"),
    ]
    python = root / "mingwarm64/bin/python.exe"
    if python.is_file():
        cases.append(("python", [python, "-I", "-S", "-c",
                      "import ssl,sqlite3,hashlib,ctypes,sys; "
                      "assert sys.maxsize > 2**32; print('python-native-modules-ready',flush=True); "
                      "assert input() == 'finish'"], b"", b"python-native-modules-ready\n", b"finish\n"))
    records = []
    try:
        for name, command, request, expected, finish in cases:
            with subprocess.Popen(list(map(str, command)), cwd=output, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                try:
                    if request:
                        process.stdin.write(request)
                        process.stdin.flush()
                    if expected is None:
                        response = b""
                        while not response.endswith(b"\n\n"):
                            line = read_line(process.stdout)
                            if not line:
                                raise ArtifactError("HTTPS helper closed before capability response")
                            response += line
                        if b"fetch" not in response and b"connect" not in response:
                            raise ArtifactError("HTTPS helper did not expose its real transport capabilities")
                    else:
                        response = read_line(process.stdout)
                        if response.rstrip(b"\r\n") != expected.rstrip(b"\r\n"):
                            raise ArtifactError(f"The held {name} entrypoint returned an unexpected protocol response: {response!r}")
                    gate_path = output / f"{name}.native-process.json"
                    gate = subprocess.run([args.pwsh, "-NoProfile", "-File", args.process_gate,
                                           "-ProcessId", str(process.pid), "-ReportPath", gate_path],
                                          env=env, capture_output=True, timeout=30)
                    native = json.loads(gate_path.read_text())
                    if gate.returncode or not native["Passed"]:
                        raise ArtifactError("Epoch native process attestation failed")
                    modules = loaded_modules(process.pid, root)
                    record = {"name": name, "command": list(map(str, command)), "pid": process.pid,
                              "native_process": native, "modules": modules,
                              "responsive_stdout": response.decode("utf-8"),
                              "process_gate_sha256": sha256(args.process_gate)}
                    records.append(record)
                    process.stdin.write(finish)
                    process.stdin.close()
                    process.stdin = None
                    stdout, stderr = process.communicate(timeout=15)
                    record.update({"raw_exit": process.returncode, "stdout": stdout.decode(errors="replace"),
                                   "stderr": stderr.decode(errors="replace")})
                    if process.returncode:
                        raise ArtifactError("Held native entrypoint failed at normal shutdown")
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
    finally:
        write_json(output / "result.json", {"schema": 1, "passed": len(records) == len(cases) and all(row.get("raw_exit") == 0 for row in records),
                   "scope": "Responsive live Bash/Git/HTTPS entrypoint MachineTypeInfo and complete module snapshots at explicit protocol checkpoints; not all-descendant module completeness",
                   "cases": records})
    print(f"Attested {len(records)} live ARM64 entrypoints and actual loaded modules")


if __name__ == "__main__":
    main()
