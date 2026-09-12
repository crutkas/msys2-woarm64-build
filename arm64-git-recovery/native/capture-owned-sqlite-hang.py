"""Capture a normal minidump of one exact, already-owned hung test generation."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import msvcrt
from pathlib import Path

from sources import ContractError, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--pid", type=int, required=True)
parser.add_argument("--created", type=int, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(r"C:\ag-sqlite-e138-01")
output = args.output.resolve()
if not output.is_relative_to(root) or output.exists():
    raise ContractError("Fresh private diagnostic output required")
kernel = C.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
process = kernel.OpenProcess(0x0400 | 0x0010, False, args.pid)
if not process:
    raise C.WinError(C.get_last_error())
try:
    times = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(process, *[C.byref(t) for t in times]):
        raise C.WinError(C.get_last_error())
    created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    name, count = C.create_unicode_buffer(32768), W.DWORD(32768)
    if not kernel.QueryFullProcessImageNameW(process, 0, name, C.byref(count)):
        raise C.WinError(C.get_last_error())
    exe = Path(name.value).resolve()
    if created != args.created or not exe.is_relative_to(root) or exe.name != "testfixture.exe":
        raise ContractError("The exact owned test process generation does not match")
    output.mkdir()
    dbghelp = C.WinDLL("dbghelp", use_last_error=True)
    dbghelp.MiniDumpWriteDump.argtypes = [W.HANDLE, W.DWORD, W.HANDLE, W.DWORD, W.LPVOID, W.LPVOID, W.LPVOID]
    dbghelp.MiniDumpWriteDump.restype = W.BOOL
    dump = output / "testfixture.dmp"
    with dump.open("xb") as stream:
        if not dbghelp.MiniDumpWriteDump(process, args.pid, msvcrt.get_osfhandle(stream.fileno()),
                                        0x1000, None, None, None):
            raise C.WinError(C.get_last_error())
    report = {"scope": "Read-only normal/thread-info minidump of the exact owned test; not full process memory or a passing test",
              "pid": args.pid, "creation_filetime": created, "executable": str(exe),
              "executable_sha256": digest(exe), "dump_sha256": digest(dump)}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
finally:
    kernel.CloseHandle(process)
