"""Experimental read-only debugger-tree evidence; never infer an exit encoding.

Uses the immutable native-job structures and the established exception-capture
API approach. It must itself run in the outer immutable observer's bounded job.
No attachment, memory writes, register writes, or debug privilege is used.
"""

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(r"C:\ag-exit-e138-01\coreutils-20260910-01")
sys.path.insert(0, str(ROOT / "support"))
from native_job_runner import noninteractive_error_mode
from sources import digest

spec = importlib.util.spec_from_file_location("immutable_job", ROOT / "driver/native-job.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


class ExceptionRecord(C.Structure):
    _fields_ = [("code", W.DWORD), ("flags", W.DWORD), ("record", W.LPVOID),
                ("address", W.LPVOID), ("count", W.DWORD), ("parameters", C.c_size_t * 15)]


class ExceptionInfo(C.Structure):
    _fields_ = [("record", ExceptionRecord), ("first_chance", W.DWORD)]


class CreateProcess(C.Structure):
    _fields_ = [("file", W.HANDLE), ("process", W.HANDLE), ("thread", W.HANDLE),
                ("base", W.LPVOID), ("debug_offset", W.DWORD), ("debug_size", W.DWORD),
                ("tls", W.LPVOID), ("start", W.LPVOID), ("image_name", W.LPVOID), ("unicode", W.WORD)]


class CreateThread(C.Structure):
    _fields_ = [("thread", W.HANDLE), ("tls", W.LPVOID), ("start", W.LPVOID)]


class LoadDll(C.Structure):
    _fields_ = [("file", W.HANDLE), ("base", W.LPVOID), ("debug_offset", W.DWORD),
                ("debug_size", W.DWORD), ("image_name", W.LPVOID), ("unicode", W.WORD)]


class DebugString(C.Structure):
    _fields_ = [("address", W.LPVOID), ("unicode", W.WORD), ("length", W.WORD)]


class Data(C.Union):
    _fields_ = [("exception", ExceptionInfo), ("create", CreateProcess), ("thread", CreateThread),
                ("load", LoadDll), ("string", DebugString), ("exit", W.DWORD), ("unload", W.LPVOID)]


class Event(C.Structure):
    _fields_ = [("code", W.DWORD), ("pid", W.DWORD), ("tid", W.DWORD), ("data", Data)]


class Api:
    def __init__(self):
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.close = self.bind("CloseHandle", [W.HANDLE])
        self.current = self.bind("GetCurrentProcess", [], W.HANDLE)()
        self.duplicate = self.bind("DuplicateHandle",
            [W.HANDLE, W.HANDLE, W.HANDLE, C.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD])
        self.times = self.bind("GetProcessTimes", [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4)
        self.thread_times = self.bind("GetThreadTimes", [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4)
        self.wait_event = self.bind("WaitForDebugEvent", [C.POINTER(Event), W.DWORD])
        self.continue_event = self.bind("ContinueDebugEvent", [W.DWORD, W.DWORD, W.DWORD])
        self.read = self.bind("ReadProcessMemory",
            [W.HANDLE, W.LPVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)])
        self.get_context = self.bind("GetThreadContext", [W.HANDLE, W.LPVOID])
        self.get_exit = self.bind("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)])
        self.wait = self.bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
        self.machine = self.bind("GetProcessInformation", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
        self.path = self.bind("GetFinalPathNameByHandleW", [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD], W.DWORD)
        self.query = C.WinDLL("ntdll").NtQueryInformationProcess
        self.query.argtypes = [W.HANDLE, C.c_int, W.LPVOID, W.ULONG, W.LPVOID]
        self.query.restype = W.LONG

    def bind(self, name, args, result=W.BOOL):
        function = getattr(self.kernel, name)
        function.argtypes, function.restype = args, result
        return function

    @staticmethod
    def check(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    def dup(self, handle):
        duplicate = W.HANDLE()
        self.check(self.duplicate(self.current, handle, self.current, C.byref(duplicate), 0, False, 2))
        return duplicate.value

    def birth(self, handle, thread=False):
        values = [W.FILETIME() for _ in range(4)]
        self.check((self.thread_times if thread else self.times)(handle, *map(C.byref, values)))
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

    def memory(self, handle, address, size):
        buffer, count = C.create_string_buffer(size), C.c_size_t()
        success = self.read(handle, address, buffer, size, C.byref(count))
        return {"success": bool(success), "error": 0 if success else C.get_last_error(),
                "requested": size, "read": count.value, "bytes": buffer.raw[:count.value].hex()}

    def context(self, handle, abi):
        buffer = C.create_string_buffer(abi["context_size"] + 15)
        address = (C.addressof(buffer) + 15) & ~15
        C.c_uint32.from_address(address + abi["context_flags"]).value = 0x00400003
        success = self.get_context(handle, address)
        if not success:
            return {"success": False, "error": C.get_last_error()}
        return {"success": True, "requested_flags": 0x00400003,
                "pc": C.c_uint64.from_address(address + abi["context_pc"]).value,
                "sp": C.c_uint64.from_address(address + abi["context_sp"]).value,
                "registers": {f"x{i}": C.c_uint64.from_address(address + abi["context_x"] + i * 8).value
                              for i in range(31) if i != 18},
                "unrequested_registers": ["x18"]}

    def file(self, handle, base):
        if not handle:
            return {"base": base, "file_handle_missing": True}
        buffer = C.create_unicode_buffer(32768)
        self.check(self.path(handle, buffer, len(buffer), 0))
        path = buffer.value
        # Hash the actual mapped-file handle, not a newly opened path.
        import msvcrt
        fd = msvcrt.open_osfhandle(self.dup(handle), os.O_RDONLY)
        with os.fdopen(fd, "rb") as stream:
            stream.seek(0)
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        self.check(self.close(handle))
        return {"base": base, "path": path, "mapped_file_sha256": sha}


def collect(command, output, abi, timeout, read_context=True, unwind_probes=False):
    api = Api()
    in_job = W.BOOL()
    api.check(api.bind("IsProcessInJob", [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)])(
        api.current, None, C.byref(in_job)))
    if not in_job:
        raise RuntimeError("Run only under the outer immutable bounded observer")
    if C.sizeof(Event) != abi["debug_event_size"] or Event.data.offset != abi["debug_data"]:
        raise RuntimeError("Compiled ARM64 debug-event ABI mismatch")
    ntdll = C.WinDLL("ntdll")
    local_base = ntdll._handle
    breakpoint_rva = C.cast(ntdll.DbgBreakPoint, W.LPVOID).value - local_base
    expected_ntdll = digest(Path(os.environ["SystemRoot"]) / "System32/ntdll.dll")
    bootstrap_lock = ROOT / "bootstrap-lock.json"
    loader_rvas = [breakpoint_rva]
    if bootstrap_lock.exists():
        bootstrap = json.loads(bootstrap_lock.read_text())
        if (bootstrap["ntdll_sha256"] != expected_ntdll
                or digest(bootstrap["control_receipt"]) != bootstrap["control_receipt_sha256"]):
            raise RuntimeError("Native Windows loader breakpoint control changed")
        loader_rvas.append(bootstrap["rva"])
    events, processes, threads = [], {}, {}
    active, all_handles = {}, []
    failure = None
    probes = None
    output.mkdir(exist_ok=False)
    process = None
    pending = None
    try:
        with (output / "stdout.bin").open("xb") as stdout, (output / "stderr.bin").open("xb") as stderr:
            with noninteractive_error_mode():
                process = subprocess.Popen(command, cwd=output, env=os.environ.copy(), stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=stderr, creationflags=1)
            deadline = time.monotonic() + timeout
            while True:
                if time.monotonic() >= deadline or len(events) >= 20000:
                    raise TimeoutError("Owned debug tree exceeded 20,000 events or its deadline")
                event = Event()
                if not api.wait_event(C.byref(event), 100):
                    if C.get_last_error() == 121:
                        continue
                    raise C.WinError(C.get_last_error())
                pending = event
                status = 0x00010002
                row = {"sequence": len(events), "event": event.code, "pid": event.pid, "tid": event.tid}
                if event.code == 3:
                    info = event.data.create
                    handle = api.dup(info.process)
                    all_handles.append(handle)
                    created = api.birth(handle)
                    identity = f"{event.pid}@{created}"
                    if event.pid in active or identity in processes:
                        raise RuntimeError("Duplicate live process or generation")
                    machine, basic = job.ProcessMachine(), job.ProcessBasic()
                    api.check(api.machine(handle, 9, C.byref(machine), C.sizeof(machine)))
                    query_status = api.query(handle, 0, C.byref(basic), C.sizeof(basic), None)
                    if query_status < 0:
                        raise RuntimeError(f"Process identity query NTSTATUS={query_status & 0xffffffff}")
                    parent = active.get(basic.parent_pid)
                    record = {"pid": event.pid, "created": created, "handle": handle,
                              "machine": machine.machine, "os_parent_pid": basic.parent_pid,
                              "held_parent_identity": parent, "parent_binding": "not-creator-callsite-qualified",
                              "image": api.file(info.file, info.base), "modules": [],
                              "encoding": "UNKNOWN", "role": "UNKNOWN", "decoded_status": None,
                              "terminal_evidence": None, "bootstrap_breakpoints": 0}
                    processes[identity] = record
                    active[event.pid] = identity
                    thread = api.dup(info.thread)
                    all_handles.append(thread)
                    threads[(event.pid, event.tid)] = (thread, api.birth(thread, thread=True))
                identity = active.get(event.pid)
                if identity is None:
                    raise RuntimeError("Event without a held creation generation")
                record = processes[identity]
                row["identity"] = identity
                thread_identity = threads.get((event.pid, event.tid))
                if event.code == 2:
                    thread = api.dup(event.data.thread.thread)
                    all_handles.append(thread)
                    threads[(event.pid, event.tid)] = (thread, api.birth(thread, thread=True))
                elif event.code == 4:
                    threads.pop((event.pid, event.tid))
                    row["thread_exit"] = event.data.exit
                elif event.code == 6:
                    module = api.file(event.data.load.file, event.data.load.base)
                    record["modules"].append(module)
                    row["module"] = module
                elif event.code == 7:
                    row["unloaded_base"] = event.data.unload
                elif event.code in (1, 8):
                    if thread_identity is None:
                        raise RuntimeError("Debug event without held thread generation")
                    row["thread_created"] = thread_identity[1]
                    row["context"] = (api.context(thread_identity[0], abi) if read_context else
                                      {"requested": False, "reason": "no-context semantic-isolation control"})
                    if event.code == 8:
                        string = event.data.string
                        length = min(string.length * (2 if string.unicode else 1), 4096)
                        row["debug_string"] = api.memory(record["handle"], string.address, length)
                        row["debug_string"]["unicode"] = bool(string.unicode)
                        row["debug_string"]["trusted_exit_evidence"] = False
                    else:
                        exception = event.data.exception
                        address = exception.record.address or 0
                        row["exception"] = {"code": exception.record.code, "address": address,
                                            "first_chance": bool(exception.first_chance),
                                            "flags": exception.record.flags,
                                            "parameters": list(exception.record.parameters)[:exception.record.count]}
                        if unwind_probes and probes is None and exception.record.code == 0x20474343 and exception.first_chance:
                            from unwind_probes import UnwindProbes
                            probes = UnwindProbes(api, record, event.tid, thread_identity[0], abi)
                            probes.install()
                        own_probe = probes is not None and probes.handle_event(event, row)
                        bootstrap = (exception.record.code == 0x80000003 and exception.first_chance
                                     and record["bootstrap_breakpoints"] == 0
                                     and any(m.get("mapped_file_sha256") == expected_ntdll
                                             and address - m["base"] in loader_rvas
                                             for m in record["modules"]))
                        row["bootstrap_breakpoint"] = bool(bootstrap)
                        naming = (exception.record.code == 0x406D1388 and exception.first_chance
                                  and exception.record.count in (3, 4) and exception.record.parameters[0] == 0x1000)
                        row["thread_name_debugger_notification"] = bool(naming)
                        if bootstrap:
                            record["bootstrap_breakpoints"] += 1
                        elif not naming and not own_probe:
                            status = 0x80010001
                        if probes is not None and exception.record.code == 0xC00000FF:
                            probes.restore_all()
                elif event.code == 5:
                    if probes is not None and event.pid == probes.process["pid"]:
                        probes.restore_all()
                    row["raw_exit"] = event.data.exit
                    record["debug_event_raw_exit"] = event.data.exit
                    record["exit_event_image_read"] = api.memory(record["handle"], record["image"]["base"], 16)
                    del active[event.pid]
                row["continue_status"] = status
                events.append(row)
                api.check(api.continue_event(event.pid, event.tid, status))
                pending = None
                if not active:
                    break
            process.wait(timeout=5)
            for record in processes.values():
                api.check(api.wait(record["handle"], 5000) == 0)
                raw = W.DWORD()
                api.check(api.get_exit(record["handle"], C.byref(raw)))
                record["raw_exit"] = raw.value
                record["event_matches_handle_exit"] = raw.value == record["debug_event_raw_exit"]
    except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if probes is not None:
            probes.restore_all()
        if pending is not None:
            api.check(api.continue_event(pending.pid, pending.tid, 0x80010001 if pending.code == 1 else 0x00010002))
        receipt = {"schema": 1, "status": "experimental-raw-only" if failure is None else "collector-failed",
                   "command": command, "collector_pid": os.getpid(), "debug_root_pid": process.pid if process else None,
                   "debug_mode": "DEBUG_PROCESS", "memory_writes": probes.writes if probes else 0,
                   "register_writes": probes.context_writes if probes else 0,
                   "unwind_probes": probes.result() if probes else None,
                   "context_reads_enabled": read_context,
                   "exception_policy": "exact native-control loader bootstrap and MSVC thread-name protocol handled; faults NOT_HANDLED",
                   "processes": list(processes.values()), "events": events, "error": failure,
                   "qualified": False, "exit_decoding_enabled": False,
                   "debug_event_abi": abi, "loader_breakpoint_rva": breakpoint_rva,
                   "bootstrap_lock_sha256": digest(bootstrap_lock) if bootstrap_lock.exists() else None,
                   "outer_job_owns_cleanup": True}
        with (output / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
        for handle in all_handles:
            api.check(api.close(handle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--abi", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--no-context", action="store_true")
    parser.add_argument("--unwind-probes", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.no_context and args.unwind_probes:
        parser.error("Unwind probes require actual thread context")
    if (not args.output.resolve().is_relative_to(ROOT) or not command
            or not Path(command[0]).resolve().is_relative_to(ROOT) or not 0 < args.timeout <= 60):
        raise RuntimeError("Only new owned fixture trees and bounded timeouts are allowed")
    collect(command, args.output, json.loads(args.abi.read_text()), args.timeout,
            not args.no_context, args.unwind_probes)


if __name__ == "__main__":
    main()
