#!/usr/bin/env python3
"""Qualify fresh MSYS ucontext consumers with the runtime owner's exact sources."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def native_process(pid, expected):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL

    class MachineInfo(ctypes.Structure):
        _fields_ = [("machine", wintypes.WORD), ("reserved", wintypes.WORD),
                    ("attributes", wintypes.DWORD)]

    api.GetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.GetProcessInformation.restype = wintypes.BOOL
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = MachineInfo()
        if not api.GetProcessInformation(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        text = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(text))
        if not api.QueryFullProcessImageNameW(handle, 0, text, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.machine != 0xaa64 or Path(text.value).resolve() != expected.resolve():
            raise ValueError("The executed consumer is not the selected native ARM64 image")
        return {"pid": pid, "image": text.value, "machine": "0xAA64", "attributes": info.attributes}
    finally:
        api.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--runtime-receipt", required=True, type=Path)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--invalid-source", required=True, type=Path)
    parser.add_argument("--invalid-source-sha256", required=True)
    parser.add_argument("--process-runner", required=True, type=Path,
                        help="Existing Windows kill-on-close bounded_process.py")
    parser.add_argument("--process-runner-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cross-executable", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows execution is required")
    if identity(args.runtime_receipt)["sha256"] != args.receipt_sha256:
        parser.error("Runtime receipt differs")
    receipt = json.loads(args.runtime_receipt.read_text(encoding="utf-8-sig"))
    if receipt["status"] != "coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified":
        parser.error("This is not a qualified ucontext cohort")
    for path, sha in ((args.source, receipt["native_context_source"]["sha256"]),
                      (args.invalid_source, args.invalid_source_sha256),
                      (args.process_runner, args.process_runner_sha256)):
        if identity(path)["sha256"] != sha:
            parser.error(f"Consumer/runner input differs: {path}")
    prefix = args.prefix.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    shutil.copy2(args.process_runner, out / "bounded_process.py")
    bounded_run = runpy.run_path(str(out / "bounded_process.py"))["run"]
    env = dict(os.environ, PATH=str(prefix / "bin") + os.pathsep + os.environ.get("PATH", ""))
    compiler = prefix / "bin" / "gcc.exe"
    report = {"passed": False, "prefix": str(prefix), "runtime_receipt": identity(args.runtime_receipt),
              "inputs": {}, "runs": []}

    def run(name, command, execute=False, expected_output=b""):
        measurements = []
        with (out / f"{name}.log.bin").open("wb") as log:
            result = bounded_run(
                [str(arg) for arg in command], cwd=out, env=env, log=log,
                timeout=15 if execute else 90,
                on_started=(lambda pid: measurements.append(native_process(pid, Path(command[0]))))
                if execute else None)
        report["runs"].append({"name": name, "command": [str(arg) for arg in command],
                               "process": result, "native_processes": measurements})
        if not result["passed"]:
            raise ValueError(f"Failed consumer or undrained job: {name}: {result}")
        data = (out / f"{name}.log.bin").read_bytes().replace(b"\r\n", b"\n")
        if execute and (data != expected_output or len(measurements) != 1):
            raise ValueError(f"Unexpected native consumer output/identity: {name}: {data!r}")

    try:
        for name, relative, expected in (
                ("runtime", "bin/msys-2.0.dll", receipt["runtime"]["sha256"]),
                ("ucontext-header", "aarch64-pc-cygwin/include/sys/ucontext.h", receipt["ucontext_header"]["sha256"]),
                ("jmp-header", "aarch64-pc-cygwin/include/machine/setjmp.h", receipt["header"]["sha256"]),
                ("import-library", "aarch64-pc-cygwin/lib/libmsys-2.0.a", receipt["import_library"]["sha256"]),
                ("crt0", "aarch64-pc-cygwin/lib/crt0.o", receipt["startup"]["sha256"])):
            actual = identity(prefix / relative)
            if actual["sha256"] != expected:
                raise ValueError(f"SDK does not contain the sealed runtime input: {name}")
            report["inputs"][name] = actual
        report["inputs"]["compiler"] = identity(compiler)
        for name, path in (("source", args.source), ("invalid-source", args.invalid_source),
                           ("process-runner", args.process_runner)):
            report["inputs"][name] = identity(path)
        shutil.copy2(prefix / "bin" / "msys-2.0.dll", out / "msys-2.0.dll")
        for name, source in (("ucontext", args.source), ("invalid", args.invalid_source)):
            copied = out / f"{name}.c"
            shutil.copy2(source, copied)
            exe = out / f"{name}.exe"
            run(f"{name}-build", [compiler, "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                                    copied, "-o", exe])
            data = exe.read_bytes()
            pe = struct.unpack_from("<I", data, 0x3c)[0]
            if data[pe:pe+4] != b"PE\0\0" or struct.unpack_from("<H", data, pe+4)[0] != 0xaa64:
                raise ValueError("Consumer is not raw ARM64 PE")
            report[name] = identity(exe)
        run("layout", [out / "ucontext.exe", "--layout-only"], execute=True)
        run("coroutines", [out / "ucontext.exe"], execute=True)
        run("invalid-context", [out / "invalid.exe"], execute=True,
            expected_output=b"result=-1 errno=22 sigusr1=0\n")
        if args.cross_executable:
            copied = out / "cross-ucontext.exe"
            shutil.copy2(args.cross_executable, copied)
            report["cross_input"] = identity(args.cross_executable)
            run("cross-layout", [copied, "--layout-only"], execute=True)
            run("cross-coroutines", [copied], execute=True)
        for before in report["inputs"].values():
            if identity(before["path"]) != before:
                raise ValueError(f"Input changed during qualification: {before['path']}")
        report["passed"] = True
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Native MSYS ucontext consumers passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
