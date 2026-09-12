"""Exercise native wincred with a unique temporary credential, then erase it."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import platform
import subprocess
import uuid

from sources import ContractError, digest


def gate(pwsh, script, arguments, report):
    subprocess.run([str(pwsh), "-NoProfile", "-File", str(script),
                    *arguments, "-ReportPath", str(report)], check=True)
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("Passed") is not True:
        raise ContractError(f"Native gate did not pass: {report}")
    return data


def parse_credential(text):
    result = {}
    for line in text.splitlines():
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator or key in result:
            raise ContractError("Malformed/duplicate credential response")
        result[key] = value
    return result


def credential_exists(target):
    api = ctypes.WinDLL(str(Path(os.environ["SystemRoot"]) / "System32/Advapi32.dll"),
                        use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.POINTER(ctypes.c_void_p)]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    pointer = ctypes.c_void_p()
    if api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        api.CredFree(pointer)
        return True
    error = ctypes.get_last_error()
    if error != 1168:  # ERROR_NOT_FOUND is the only evidence of absence.
        raise ctypes.WinError(error)
    return False


def remove_fixture_credential(target):
    api = ctypes.WinDLL(str(Path(os.environ["SystemRoot"]) / "System32/Advapi32.dll"),
                        use_last_error=True)
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    if not api.CredDeleteW(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise ctypes.WinError(error)


def test(executable, output, pwsh, artifact_gate, process_gate):
    if platform.system() != "Windows" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise ContractError("Native wincred execution requires Windows ARM64")
    executable, output = Path(executable).resolve(), Path(output).resolve()
    if output.exists():
        raise ContractError("Use a new evidence directory")
    output.mkdir(parents=True)
    before = gate(pwsh, artifact_gate, ["-Path", str(executable)], output / "artifact-before.json")
    expected_hash = digest(executable)
    if (before.get("ParsedCount") != 1 or before["Files"][0]["SHA256"].lower() != expected_hash
            or before["Files"][0].get("NativeArm64Header") is not True):
        raise ContractError("Artifact gate did not identify the expected helper")
    token = uuid.uuid4().hex
    host = f"arm64-wincred-fixture-{token}.invalid"
    username, password = f"fixture-{token}", f"fixture-only-not-a-secret-{token}"
    target = f"git:https://{username}@{host}"
    query = f"protocol=https\nhost={host}\nusername={username}\n\n"
    store = f"protocol=https\nhost={host}\nusername={username}\npassword={password}\n\n"
    environment = dict(os.environ)
    environment["PATH"] = str(executable.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    commands = []

    def invoke(operation, request, observe=False):
        process = subprocess.Popen([str(executable), operation], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment, cwd=output)
        try:
            if observe:
                live = gate(pwsh, process_gate, ["-ProcessId", str(process.pid)], output / "native-process.json")
                if (live.get("MeasuredCount") != 1 or live["Processes"][0]["ProcessId"] != process.pid
                        or live["Processes"][0]["ImagePath"].casefold() != str(executable).casefold()
                        or live["Processes"][0].get("NativeArm64Process") is not True
                        or live["Processes"][0].get("ProcessMachine") != "0xAA64"):
                    raise ContractError("Live native helper identity mismatch")
            raw_stdout, raw_stderr = process.communicate(request.encode("utf-8"), timeout=30)
            name = f"{len(commands) + 1:02d}-{operation}"
            stdout_path, stderr_path = output / f"{name}.stdout.bin", output / f"{name}.stderr.bin"
            stdout_path.write_bytes(raw_stdout)
            stderr_path.write_bytes(raw_stderr)
            record = {"operation": operation, "process_id": process.pid, "exit_code": process.returncode,
                      "stdout_path": stdout_path.name, "stdout_sha256": digest(stdout_path),
                      "stderr_path": stderr_path.name, "stderr_sha256": digest(stderr_path)}
            commands.append(record)
            if process.returncode:
                raise ContractError(f"wincred {operation} failed: {process.returncode}; see {stderr_path}")
            try:
                stdout, stderr = raw_stdout.decode("utf-8"), raw_stderr.decode("utf-8")
            except UnicodeDecodeError as error:
                record["decode_error"] = str(error)
                raise ContractError(f"wincred {operation} emitted invalid UTF-8; raw bytes retained in {output}") from error
            record.update({"stdout": stdout, "stderr": stderr})
            if stderr or (operation in ("store", "erase") and stdout):
                raise ContractError(f"wincred {operation} emitted unexpected output; raw bytes retained")
            return parse_credential(stdout)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    attempted_store = False
    cleanup = {"verified_absent": False, "api_fallback_required": False}
    status = "failed"
    try:
        if credential_exists(target) or invoke("get", query, observe=True):
            raise ContractError("Unique fixture credential unexpectedly exists; refusing to alter it")
        attempted_store = True
        invoke("store", store)
        found = invoke("get", query)
        expected_output = f"username={username}\npassword={password}\n"
        if (found != {"username": username, "password": password}
                or commands[-1]["stdout"] != expected_output):
            raise ContractError("Windows credential store/get did not round-trip the fixture values")
        status = "store-get-passed-cleanup-pending"
    finally:
        try:
            if attempted_store:
                erase_error = None
                try:
                    invoke("erase", query)
                except (ContractError, subprocess.TimeoutExpired, OSError) as error:
                    erase_error = error
                if credential_exists(target):
                    cleanup["api_fallback_required"] = True
                    remove_fixture_credential(target)
                if credential_exists(target):
                    raise ContractError("Fixture credential remains in Windows Credential Manager")
                cleanup["verified_absent"] = True
                if erase_error or cleanup["api_fallback_required"]:
                    raise ContractError("Helper erase failed; direct API cleanup was required") from erase_error
                if invoke("get", query):
                    raise ContractError("Fixture credential remains after erase")
            if status == "store-get-passed-cleanup-pending":
                after = gate(pwsh, artifact_gate, ["-Path", str(executable)], output / "artifact-after.json")
                if after["Files"][0]["SHA256"].lower() != expected_hash or digest(executable) != expected_hash:
                    raise ContractError("Helper changed during credential round trip")
                status = "native-wincred-store-get-erase-passed"
        finally:
            (output / "result.json").write_text(json.dumps({
                "status": status, "scope": "Real wincred helper and temporary Windows credential only; not GCM or full Git",
                "fixture_host": host, "helper_sha256": expected_hash,
                "cleanup": cleanup,
                "artifact_gate_sha256": digest(artifact_gate), "process_gate_sha256": digest(process_gate),
                "commands": commands
            }, indent=2) + "\n", encoding="utf-8")
    print(status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--artifact-gate", type=Path, required=True)
    parser.add_argument("--process-gate", type=Path, required=True)
    args = parser.parse_args()
    test(args.executable, args.output, args.pwsh, args.artifact_gate, args.process_gate)


if __name__ == "__main__":
    main()
