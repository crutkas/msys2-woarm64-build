"""Capture first/second-chance faults from one explicitly launched native fixture."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import time

from sources import ContractError, digest


class ExceptionRecord(C.Structure):
    _fields_ = [("code", W.DWORD), ("flags", W.DWORD), ("record", C.c_void_p),
                ("address", C.c_void_p), ("count", W.DWORD), ("parameters", C.c_size_t * 15)]


class ExceptionInfo(C.Structure):
    _fields_ = [("record", ExceptionRecord), ("first_chance", W.DWORD)]


class EventData(C.Union):
    _fields_ = [("exception", ExceptionInfo), ("raw", C.c_ubyte * 160)]


class DebugEvent(C.Structure):
    _fields_ = [("code", W.DWORD), ("pid", W.DWORD), ("tid", W.DWORD), ("data", EventData)]


def capture(executable, arguments, output, path_directory=None, max_exceptions=32):
    if os.name != "nt":
        raise ContractError("Windows debugging API required")
    if not 1 <= max_exceptions <= 128:
        raise ContractError("An explicit 1-128 exception capture bound is required")
    executable, output = Path(executable).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForDebugEvent.argtypes = [C.POINTER(DebugEvent), W.DWORD]
    kernel.WaitForDebugEvent.restype = W.BOOL
    kernel.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
    kernel.ContinueDebugEvent.restype = W.BOOL
    kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype = W.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = W.DWORD
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenThread.restype = W.HANDLE
    kernel.GetThreadContext.argtypes = [W.HANDLE, C.c_void_p]
    kernel.GetThreadContext.restype = W.BOOL
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env["PATH"] = str(path_directory or executable.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env.update({"HOME": str(output), "USERPROFILE": str(output), "TMP": str(output), "TEMP": str(output)})
    modules, exceptions = [], []
    with (output / "stdout.bin").open("wb") as stdout, (output / "stderr.bin").open("wb") as stderr:
        process = subprocess.Popen([str(executable), *arguments], cwd=output, env=env,
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=2)
        deadline = time.monotonic() + 15
        timed_out = True
        exception_limit_reached = False
        try:
            while time.monotonic() < deadline:
                event = DebugEvent()
                if not kernel.WaitForDebugEvent(C.byref(event), 100):
                    error = C.get_last_error()
                    if error == 121:
                        continue
                    raise C.WinError(error)
                status = 0x00010002
                if event.code in (3, 6):
                    raw = bytes(event.data.raw)
                    handle = int.from_bytes(raw[:8], "little")
                    base_offset = 24 if event.code == 3 else 8
                    base = int.from_bytes(raw[base_offset:base_offset + 8], "little")
                    if handle:
                        path = C.create_unicode_buffer(32768)
                        length = kernel.GetFinalPathNameByHandleW(handle, path, len(path), 0)
                        if length:
                            modules.append({"base": base, "path": path.value})
                        kernel.CloseHandle(handle)
                elif event.code == 1:
                    record = event.data.exception.record
                    # MSVC's thread-name notification is a debugger protocol,
                    # not an application fault requiring SEH unwinding.
                    if record.code not in (0x80000003, 0x406d1388):
                        address = record.address or 0
                        data, count = C.create_string_buffer(32), C.c_size_t()
                        readable = kernel.ReadProcessMemory(int(process._handle), address, data, 32, C.byref(count))
                        module = next((m for m in reversed(sorted(modules, key=lambda m: m["base"]))
                                       if m["base"] <= address), None)
                        details = {
                            "code": f"0x{record.code:08X}", "address": f"0x{address:X}",
                            "first_chance": bool(event.data.exception.first_chance),
                            "parameters": list(record.parameters)[:record.count],
                            "instruction_bytes": data.raw[:count.value].hex() if readable else None,
                            "nearest_module": module,
                            "offset": f"0x{address - module['base']:X}" if module else None
                        }
                        thread = kernel.OpenThread(0x0008, False, event.tid)
                        if thread:
                            context = C.create_string_buffer(928)
                            aligned = (C.addressof(context) + 15) & ~15
                            C.c_uint32.from_address(aligned).value = 0x00400003
                            if kernel.GetThreadContext(thread, aligned):
                                details["registers"] = {
                                    f"x{i}": hex(C.c_uint64.from_address(aligned + 8 + i * 8).value)
                                    for i in range(31) if i != 18
                                }
                                details["context_flags"] = "0x00400003"
                                details["unrequested_registers"] = ["x18"]
                                details["sp"] = hex(C.c_uint64.from_address(aligned + 256).value)
                                details["pc"] = hex(C.c_uint64.from_address(aligned + 264).value)
                                frames, frame = [], C.c_uint64.from_address(aligned + 240).value
                                seen = set()
                                for _ in range(8):
                                    if not frame or frame in seen or frame % 16:
                                        break
                                    seen.add(frame)
                                    saved, read = C.create_string_buffer(16), C.c_size_t()
                                    if not kernel.ReadProcessMemory(int(process._handle), frame, saved, 16, C.byref(read)) or read.value != 16:
                                        break
                                    parent = int.from_bytes(saved.raw[:8], "little")
                                    caller = int.from_bytes(saved.raw[8:16], "little")
                                    frames.append({"fp": hex(frame), "caller": hex(caller)})
                                    frame = parent
                                details["frame_pointer_chain"] = frames
                            kernel.CloseHandle(thread)
                        exceptions.append(details)
                        (output / "exceptions-so-far.json").write_text(json.dumps(exceptions, indent=2))
                        status = 0x80010001
                elif event.code == 5:
                    timed_out = False
                    kernel.ContinueDebugEvent(event.pid, event.tid, status)
                    break
                if not kernel.ContinueDebugEvent(event.pid, event.tid, status):
                    raise C.WinError(C.get_last_error())
                if len(exceptions) >= max_exceptions:
                    exception_limit_reached = True
                    timed_out = False
                    break
        finally:
            if process.poll() is None:
                process.kill()
                for _ in range(50):
                    event = DebugEvent()
                    if kernel.WaitForDebugEvent(C.byref(event), 100):
                        kernel.ContinueDebugEvent(event.pid, event.tid, 0x00010002)
                    if process.poll() is not None:
                        break
            process.wait(timeout=5)
    record = {"schema": 1, "executable": str(executable), "sha256": digest(executable),
              "arguments": arguments, "exit_code": process.returncode,
              "timed_out": timed_out, "exceptions": exceptions, "modules": modules,
              "exception_limit": max_exceptions, "exception_limit_reached": exception_limit_reached,
              "scope": "One newly launched fixture only; no attachment to existing user processes"}
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"exit_code": process.returncode, "timed_out": timed_out,
                      "exception_count": len(exceptions), "exception_limit_reached": exception_limit_reached,
                      "result": str(output / "result.json")}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--path-directory", type=Path)
    p.add_argument("--max-exceptions", type=int, default=32)
    p.add_argument("arguments", nargs=argparse.REMAINDER)
    a = p.parse_args()
    capture(a.executable, a.arguments, a.output, a.path_directory, a.max_exceptions)


if __name__ == "__main__":
    main()
