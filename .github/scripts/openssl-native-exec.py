"""Run one native MSYS OpenSSL test while preserving its exact Windows exit."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import uuid


def windows_path(value):
    match = re.match(r"^/(?:cygdrive/)?([A-Za-z])/(.*)$", value)
    return f"{match[1]}:/{match[2]}" if match else value


def portable_exit(code):
    return code if 0 <= code <= 255 else 255


def process_created(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_times = kernel.GetProcessTimes
    get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    get_times.restype = wintypes.BOOL
    created, ended, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
    if not get_times(
        handle,
        ctypes.byref(created),
        ctypes.byref(ended),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def main():
    if os.name != "nt" or len(sys.argv) < 2:
        raise SystemExit("Native Windows execution and an explicit command are required")
    root = Path(windows_path(os.environ["OPENSSL_NATIVE_TEST_ROOT"])).resolve()
    executable = Path(windows_path(sys.argv[1])).resolve()
    if not executable.is_relative_to(root) or executable.suffix.lower() != ".exe":
        raise SystemExit("Only an executable from the explicit native OpenSSL build may run")
    with executable.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise SystemExit("The native test command is not a PE executable")
        offset = struct.unpack_from("<I", header, 60)[0]
        if offset < 64 or offset + 26 > executable.stat().st_size:
            raise SystemExit("Native test PE header is out of bounds")
        stream.seek(offset)
        pe = stream.read(26)
    if (
        pe[:4] != b"PE\0\0"
        or struct.unpack_from("<H", pe, 4)[0] != 0xAA64
        or struct.unpack_from("<H", pe, 24)[0] != 0x20B
    ):
        raise SystemExit("Native test execution requires ordinary ARM64 PE32+")

    env = dict(os.environ)
    env["OPENSSL_RUNNING_UNIT_TESTS"] = "yes"
    defaults = {
        "OPENSSL_ENGINES": root / "engines",
        "OPENSSL_MODULES": root / "providers",
        "OPENSSL_CONF": root / "apps/openssl.cnf",
    }
    for key, value in defaults.items():
        if not env.get(key) and value.exists():
            env[key] = str(value)
    for key in ("OPENSSL_ENGINES", "OPENSSL_MODULES", "OPENSSL_CONF", "OPENSSL_CONF_INCLUDE"):
        if env.get(key):
            env[key] = windows_path(env[key])
    env["PATH"] = str(root) + os.pathsep + env.get("PATH", "")

    log_path = Path(windows_path(env["OPENSSL_NATIVE_EXIT_LOG"])).resolve()
    control = env.get("OPENSSL_NATIVE_SERVER_CONTROL")
    if control:
        control = Path(windows_path(control)).resolve(strict=True)
        if not control.is_relative_to(log_path.parent) or (control / "done.json").exists():
            raise SystemExit("Native server control must be a fresh directory inside the owned result root")

    stopped, timed_out = False, False
    with subprocess.Popen([str(executable), *sys.argv[2:]], env=env) as process:
        child_pid = process.pid
        child_created = process_created(int(process._handle))
        if control:
            (control / "started.json").write_text(
                json.dumps(
                    {
                        "relay_pid": os.getpid(),
                        "child_pid": child_pid,
                        "child_created": child_created,
                    }
                )
                + "\n"
            )
            deadline = time.monotonic() + 900
            while process.poll() is None:
                if (control / "stop").exists():
                    stopped = True
                    process.terminate()
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    process.terminate()
                    break
                time.sleep(0.02)
        raw_exit = process.wait()

    record = {
        "executable": str(executable),
        "raw_exit": raw_exit,
        "portable_exit": portable_exit(raw_exit),
        "relay_pid": os.getpid(),
        "child_pid": child_pid,
        "child_created": child_created,
        "stop_requested": stopped,
        "timed_out": timed_out,
    }
    encoded = json.dumps(record) + "\n"
    with log_path.open("ab") as log:
        log.write(encoded.encode())
    records = log_path.parent / "native-exit-records"
    records.mkdir(exist_ok=True)
    with (records / f"{os.getpid()}-{uuid.uuid4().hex}.json").open("x") as output:
        output.write(encoded)
    if control:
        (control / "done.json").write_text(encoded)
    raise SystemExit(record["portable_exit"])


if __name__ == "__main__":
    main()
