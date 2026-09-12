"""Launch-only child-aware diagnostics for the retained GDBM wrapper failure."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

from db_native_checks import environment
from native_job_runner import noninteractive_error_mode
from sources import ContractError, digest
from ssh_bootstrap import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--case", choices=("original", "coherent"), required=True)
    parser.add_argument("--run-name")
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Only the owned GDBM reproducer may be launched")
    source = Path(__file__).with_name("capture-native-exception.py")
    spec = importlib.util.spec_from_file_location("native_exception_types", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kernel = C.WinDLL("kernel32", use_last_error=True)
    for name, arguments, result in (
        ("WaitForDebugEvent", [C.POINTER(module.DebugEvent), W.DWORD], W.BOOL),
        ("ContinueDebugEvent", [W.DWORD, W.DWORD, W.DWORD], W.BOOL),
        ("GetFinalPathNameByHandleW", [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD], W.DWORD),
        ("GetProcessTimes", [W.HANDLE, *([C.POINTER(W.FILETIME)] * 4)], W.BOOL),
        ("ReadProcessMemory", [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
        ("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
        ("OpenThread", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
        ("GetThreadContext", [W.HANDLE, C.c_void_p], W.BOOL),
        ("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
        ("TerminateProcess", [W.HANDLE, W.UINT], W.BOOL),
        ("CloseHandle", [W.HANDLE], W.BOOL),
    ):
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    name = args.run_name or ("wrapper-debug-" + args.case)
    if Path(name).name != name or name in (".", ".."):
        raise ContractError("An owned diagnostic directory name is required")
    output = root / name
    output.mkdir()
    tests = root / "reproduce02/tests"
    executable = tests / ("gtver.exe" if args.case == "original" else "gtver-coherent.exe")
    env = environment(root / "compiler", output)
    env["PATH"] = os.pathsep.join(map(str, (root / "reproduce02/original-layout/usr/bin",
                                          tests / ".libs", Path(os.environ["SystemRoot"]) / "System32")))
    command = [str(executable), "--lt-debug", "-lib", "-full", "-header", "-full"]
    processes, handles, exceptions = {}, {}, []
    report = {"schema": 1, "scope": "Launch-only debugger diagnostic, not ordinary-run admission",
              "command": command, "environment": env, "types_source_sha256": digest(source),
              "processes": processes, "exceptions": exceptions}
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        with noninteractive_error_mode():
            child = subprocess.Popen(command, cwd=tests, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=1)
        deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                event = module.DebugEvent()
                if not kernel.WaitForDebugEvent(C.byref(event), 100):
                    if C.get_last_error() == 121:
                        continue
                    raise C.WinError(C.get_last_error())
                status = 0x00010002
                raw = bytes(event.data.raw)
                if event.code == 3:
                    handle = kernel.OpenProcess(0x00101411, False, event.pid)
                    if not handle:
                        raise C.WinError(C.get_last_error())
                    handles[event.pid] = handle
                    timestamps = [W.FILETIME() for _ in range(4)]
                    if not kernel.GetProcessTimes(handle, *map(C.byref, timestamps)):
                        raise C.WinError(C.get_last_error())
                    birth = timestamps[0].dwLowDateTime | (timestamps[0].dwHighDateTime << 32)
                    processes[event.pid] = {"pid": event.pid, "created": birth, "modules": []}
                    if len(processes) > 8:
                        raise ContractError("Wrapper diagnostic exceeded its eight-process bound")
                if event.code in (3, 6):
                    file_handle = int.from_bytes(raw[:8], "little")
                    base_offset = 24 if event.code == 3 else 8
                    base = int.from_bytes(raw[base_offset:base_offset + 8], "little")
                    if file_handle:
                        path_buffer = C.create_unicode_buffer(32768)
                        length = kernel.GetFinalPathNameByHandleW(file_handle, path_buffer, len(path_buffer), 0)
                        kernel.CloseHandle(file_handle)
                        if not length or length >= len(path_buffer):
                            raise C.WinError(C.get_last_error())
                        path = Path(path_buffer.value.removeprefix("\\\\?\\"))
                        data = path.read_bytes()
                        pe = int.from_bytes(data[60:64], "little")
                        size = int.from_bytes(data[pe + 24 + 56:pe + 24 + 60], "little")
                        processes[event.pid]["modules"].append({
                            "path": str(path), "sha256": digest(path), "base": base,
                            "image_size": size, "machine": hex(int.from_bytes(data[pe + 4:pe + 6], "little"))})
                elif event.code == 1:
                    record = event.data.exception.record
                    if record.code not in (0x80000003, 0x406D1388):
                        address = record.address or 0
                        loaded = next((entry for entry in processes[event.pid]["modules"]
                                       if entry["base"] <= address < entry["base"] + entry["image_size"]), None)
                        details = {"pid": event.pid, "tid": event.tid, "code": hex(record.code),
                                   "first_chance": bool(event.data.exception.first_chance),
                                   "address": hex(address), "parameters": list(record.parameters)[:record.count],
                                   "module": loaded, "offset": hex(address - loaded["base"]) if loaded else None}
                        exceptions.append(details)
                        thread = kernel.OpenThread(0x0008, False, event.tid)
                        if not thread:
                            raise C.WinError(C.get_last_error())
                        context = C.create_string_buffer(928)
                        aligned = (C.addressof(context) + 15) & ~15
                        C.c_uint32.from_address(aligned).value = 0x00400003
                        if not kernel.GetThreadContext(thread, aligned):
                            raise C.WinError(C.get_last_error())
                        kernel.CloseHandle(thread)
                        details["registers"] = {f"x{i}": hex(C.c_uint64.from_address(aligned + 8 + i * 8).value)
                                                for i in range(31) if i != 18}
                        details["sp"] = hex(C.c_uint64.from_address(aligned + 256).value)
                        details["pc"] = hex(C.c_uint64.from_address(aligned + 264).value)
                        status = 0x80010001
                elif event.code == 5:
                    processes[event.pid]["raw_exit"] = int.from_bytes(raw[:4], "little")
                if not kernel.ContinueDebugEvent(event.pid, event.tid, status):
                    raise C.WinError(C.get_last_error())
                if processes and all("raw_exit" in row for row in processes.values()):
                    break
        finally:
            report["diagnostic_error"] = str(sys.exc_info()[1]) if sys.exc_info()[1] else None
            remaining = [pid for pid, handle in handles.items() if kernel.WaitForSingleObject(handle, 1000) != 0]
            report["timed_out_or_incomplete"] = any("raw_exit" not in row for row in processes.values())
            report["cleanup_errors"] = []
            for pid in remaining:
                if not kernel.TerminateProcess(handles[pid], 1460):
                    error = C.get_last_error()
                    if kernel.WaitForSingleObject(handles[pid], 1000) != 0:
                        report["cleanup_errors"].append({"pid": pid, "winerror": error})
            cleanup_deadline = time.monotonic() + 5
            while remaining and time.monotonic() < cleanup_deadline:
                event = module.DebugEvent()
                if kernel.WaitForDebugEvent(C.byref(event), 100):
                    kernel.ContinueDebugEvent(event.pid, event.tid, 0x00010002)
                remaining = [pid for pid in remaining if kernel.WaitForSingleObject(handles[pid], 0) != 0]
            report["remaining_process_ids"] = remaining
            for handle in handles.values():
                kernel.CloseHandle(handle)
            write_json(output / "result.json", report)
            if remaining or report["cleanup_errors"]:
                raise ContractError("Owned debugger generations did not drain")
            child.wait(timeout=5)


if __name__ == "__main__":
    main()
