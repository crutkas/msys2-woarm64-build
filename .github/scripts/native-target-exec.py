"""Preserve raw Windows target exit status across a foreign MSYS test driver."""

import hashlib
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid


def windows_path(value):
    match = re.match(r"^/(?:(?:proc/)?cygdrive/)?([A-Za-z])/(.*)$", value)
    return f"{match[1]}:/{match[2]}" if match else value


def windows_argument(value, msys_root=None):
    if value == "/dev/null":
        return "NUL"

    value = re.sub(
        r"^(?P<prefix>file://(?:localhost)?/)(?P<drive>[A-Za-z])/",
        lambda match: f"{match.group('prefix')}{match.group('drive').upper()}:/",
        value,
    )
    pattern = re.compile(
        r"(?P<prefix>^|[A-Za-z][A-Za-z0-9+.-]*:)"
        r"/(?:(?:proc/)?cygdrive/)?(?P<drive>[A-Za-z])/"
    )
    value = pattern.sub(
        lambda match: f"{match.group('prefix')}{match.group('drive').upper()}:/",
        value,
    )
    if msys_root is not None and value.startswith("/"):
        candidate = Path(msys_root, value.lstrip("/"))
        if candidate.exists():
            return candidate.as_posix()
    return value


def portable_exit(code):
    return code if 0 <= code <= 255 else 255


def relayed_arguments(environment, positional):
    count = environment.pop("WOARM64_NATIVE_ARG_COUNT", None)
    if count is None:
        return positional
    if not count.isdecimal():
        raise ValueError("Native argument count is invalid")
    arguments = []
    for index in range(int(count)):
        name = f"WOARM64_NATIVE_ARG_{index}"
        if name not in environment:
            raise ValueError(f"Native argument is missing: {index}")
        value = environment.pop(name)
        if not value.startswith("v1:"):
            raise ValueError(f"Native argument encoding is invalid: {index}")
        arguments.append(value[3:])
    return arguments


def require_arm64_pe(path):
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("Native execution requires a PE executable")
        offset = struct.unpack_from("<I", header, 60)[0]
        if offset < 64 or offset + 26 > path.stat().st_size:
            raise ValueError("Native PE header is out of bounds")
        stream.seek(offset)
        pe = stream.read(26)
    if (pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0xAA64
            or struct.unpack_from("<H", pe, 24)[0] != 0x20B
            or struct.unpack_from("<H", pe, 22)[0] & 0x2000):
        raise ValueError("Native target execution requires ordinary ARM64 PE32+, not a DLL")


def main():
    if os.name != "nt" or len(sys.argv) < 2:
        raise SystemExit("Native Windows execution and an explicit target command are required")
    interpreter = Path(sys.executable).resolve()
    require_arm64_pe(interpreter)
    expected_python = os.environ["WOARM64_NATIVE_PYTHON_SHA256"]
    with interpreter.open("rb") as stream:
        actual_python = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_python != expected_python:
        raise SystemExit("Native Python interpreter changed")
    root = Path(windows_path(os.environ["WOARM64_NATIVE_TEST_ROOT"])).resolve(strict=True)
    executable = Path(windows_path(sys.argv[1])).resolve(strict=True)
    if not executable.is_relative_to(root) or executable.suffix.lower() != ".exe":
        raise SystemExit("Only an explicit executable inside the owned native test root may run")
    if re.fullmatch(r"(?:.*-)?(?:gcc|g\+\+|cc|c\+\+|cc1|cc1plus|collect2|as|ld|ar|ranlib)(?:\.exe)?", executable.name):
        raise SystemExit("This relay is for target tests, not compiler/tool proxies")
    require_arm64_pe(executable)
    log_root = Path(windows_path(os.environ["WOARM64_NATIVE_EXIT_DIR"])).resolve(strict=True)
    arguments = relayed_arguments(os.environ, sys.argv[2:])
    path_conversion = os.environ.pop("WOARM64_NATIVE_PATH_CONVERSION", "0")
    if path_conversion not in ("0", "1"):
        raise SystemExit("Native path conversion setting is invalid")
    if path_conversion == "1":
        msys_root = os.environ.pop("WOARM64_NATIVE_MSYS_ROOT", None)
        if msys_root is None:
            raise SystemExit("Native MSYS root is required for path conversion")
        arguments = [windows_argument(argument, msys_root) for argument in arguments]
    with executable.open("rb") as stream:
        identity = hashlib.file_digest(stream, "sha256").hexdigest()
    with subprocess.Popen([str(executable), *arguments]) as process:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_times = kernel.GetProcessTimes
        get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        get_times.restype = wintypes.BOOL
        created, ended, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not get_times(int(process._handle), ctypes.byref(created), ctypes.byref(ended),
                         ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise ctypes.WinError(ctypes.get_last_error())
        child_created = (created.dwHighDateTime << 32) | created.dwLowDateTime
        raw_exit = process.wait()
        child_pid = process.pid
    code = portable_exit(raw_exit)
    record = {
        "executable": str(executable), "sha256": identity,
        "raw_exit": raw_exit, "portable_exit": code,
        "relay_pid": os.getpid(), "child_pid": child_pid, "child_created": child_created,
    }
    # A separate file per invocation avoids concurrent append races in parallel suites.
    with (log_root / f"{os.getpid()}-{uuid.uuid4().hex}.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream)
        stream.write("\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
