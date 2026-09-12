"""Bound a Windows test tree and retain native target exits independently of its shell."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import time


class StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR),
                ("title", W.LPWSTR), ("x", W.DWORD), ("y", W.DWORD),
                ("width", W.DWORD), ("height", W.DWORD), ("xchars", W.DWORD),
                ("ychars", W.DWORD), ("fill", W.DWORD), ("flags", W.DWORD),
                ("show", W.WORD), ("reserved_size", W.WORD), ("reserved_data", W.LPBYTE),
                ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_int64), ("job_time", C.c_int64),
                ("flags", W.DWORD), ("min_working", C.c_size_t), ("max_working", C.c_size_t),
                ("active_limit", W.DWORD), ("affinity", C.c_size_t),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters), ("process_memory", C.c_size_t),
                ("job_memory", C.c_size_t), ("peak_process", C.c_size_t), ("peak_job", C.c_size_t)]


class CompletionPort(C.Structure):
    _fields_ = [("key", W.LPVOID), ("port", W.HANDLE)]


class Accounting(C.Structure):
    _fields_ = [(name, C.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        ("page_faults", W.DWORD), ("total", W.DWORD), ("active", W.DWORD), ("terminated", W.DWORD)]


class ProcessMachine(C.Structure):
    _fields_ = [("machine", W.WORD), ("reserved", W.WORD), ("attributes", W.DWORD)]


class ProcessBasic(C.Structure):
    _fields_ = [("exit_status", W.LONG), ("peb", W.LPVOID), ("affinity", C.c_size_t),
                ("priority", W.LONG), ("pid", C.c_size_t), ("parent_pid", C.c_size_t)]


def process_identity(pid, created):
    return pid, (created.dwHighDateTime << 32) | created.dwLowDateTime


def retire_process(native, recorded, identity, code, parents=None):
    executable = native.pop(identity, None)
    recorded.add(identity)
    parent = parents.pop(identity, None) if parents is not None else None
    if executable is None:
        return None
    return {"pid": identity[0], "created": identity[1], "executable": executable, "raw_exit": code,
            "parent_pid": parent[0] if parent else None, "parent_created": parent[1] if parent else None}


def unprotected_native_exits(exits, relayed):
    records = {(record["pid"], record["created"]): record for record in exits}
    protected = set()
    for identity, record in records.items():
        if record["raw_exit"] <= 255:
            continue
        candidates = relayed.get(identity, [])
        match = next((candidate for candidate in candidates
                      if candidate["raw_exit"] & 0xFFFFFFFF == record["raw_exit"]
                      and candidate["portable_exit"] == 255
                      and Path(candidate["executable"]).resolve() == Path(record["executable"]).resolve()), None)
        if match is not None:
            candidates.remove(match)
            protected.add(identity)
    changed = True
    while changed:
        changed = False
        for identity, record in records.items():
            parent = (record.get("parent_pid"), record.get("parent_created"))
            if (identity not in protected and parent in protected
                    and record["raw_exit"] > 255 and record["raw_exit"] == records[parent]["raw_exit"]):
                protected.add(identity)
                changed = True
    return [record for identity, record in records.items()
            if record["raw_exit"] > 255 and identity not in protected]


def run(command, cwd, target_root, relay_records, log_path, timeout):
    if os.name != "nt" or not 0 < timeout <= 86400:
        raise ValueError("Windows and an explicit bounded timeout are required")
    import msvcrt

    api = C.WinDLL("kernel32", use_last_error=True)

    def bind(name, args, result=W.BOOL):
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
        return function

    def checked(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    close = bind("CloseHandle", [W.HANDLE])
    create_job = bind("CreateJobObjectW", [W.LPVOID, W.LPCWSTR], W.HANDLE)
    set_job = bind("SetInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
    query_job = bind("QueryInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID])
    create_port = bind("CreateIoCompletionPort", [W.HANDLE, W.HANDLE, C.c_size_t, W.DWORD], W.HANDLE)
    get_event = bind("GetQueuedCompletionStatus", [W.HANDLE, C.POINTER(W.DWORD),
                     C.POINTER(C.c_size_t), C.POINTER(W.LPVOID), W.DWORD])
    create = bind("CreateProcessW", [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL,
                  W.DWORD, W.LPVOID, W.LPCWSTR, C.POINTER(StartupInfo), C.POINTER(ProcessInfo)])
    assign = bind("AssignProcessToJobObject", [W.HANDLE, W.HANDLE])
    resume = bind("ResumeThread", [W.HANDLE], W.DWORD)
    wait = bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    get_exit = bind("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)])
    get_times = bind("GetProcessTimes", [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME),
                                       C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)])
    open_process = bind("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
    image_name = bind("QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)])
    machine_info = bind("GetProcessInformation", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
    query_basic = C.WinDLL("ntdll").NtQueryInformationProcess
    query_basic.argtypes = [W.HANDLE, C.c_int, W.LPVOID, W.ULONG, W.LPVOID]
    query_basic.restype = W.LONG
    terminate_job = bind("TerminateJobObject", [W.HANDLE, W.UINT])
    terminate_process = bind("TerminateProcess", [W.HANDLE, W.UINT])
    inherit = bind("SetHandleInformation", [W.HANDLE, W.DWORD, W.DWORD])

    root = Path(target_root).resolve()
    job = checked(create_job(None, None))
    port = None
    info = ProcessInfo()
    assigned = False
    handles = {}
    native = {}
    parents = {}
    exits = []
    missing = set()
    recorded = set()
    timed_out = False
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000
        checked(set_job(job, 9, C.byref(limits), C.sizeof(limits)))
        port = checked(create_port(W.HANDLE(-1), None, 0, 1))
        completion = CompletionPort(None, port)
        checked(set_job(job, 7, C.byref(completion), C.sizeof(completion)))
        with open(os.devnull, "rb") as stdin, open(log_path, "xb") as log:
            input_handle = msvcrt.get_osfhandle(stdin.fileno())
            output_handle = msvcrt.get_osfhandle(log.fileno())
            checked(inherit(input_handle, 1, 1))
            checked(inherit(output_handle, 1, 1))
            startup = StartupInfo()
            startup.cb, startup.flags = C.sizeof(startup), 0x100
            startup.stdin, startup.stdout, startup.stderr = input_handle, output_handle, output_handle
            environment = C.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(os.environ.items(), key=lambda row: row[0].upper())) + "\0")
            try:
                checked(create(None, C.create_unicode_buffer(subprocess.list2cmdline(command)), None, None, True,
                               0x404, environment, str(cwd), C.byref(startup), C.byref(info)))
            finally:
                checked(inherit(input_handle, 1, 0))
                checked(inherit(output_handle, 1, 0))
            checked(assign(job, info.process))
            assigned = True
            if resume(info.thread) != 1:
                raise RuntimeError("Unexpected initial suspension count")
            deadline = time.monotonic() + timeout
            while True:
                message, key, value = W.DWORD(), C.c_size_t(), W.LPVOID()
                received = get_event(port, C.byref(message), C.byref(key), C.byref(value), 50)
                if not received and C.get_last_error() != 258:
                    raise C.WinError(C.get_last_error())
                if received and message.value == 6:  # JOB_OBJECT_MSG_NEW_PROCESS
                    pid = value.value
                    handle = open_process(0x101000, False, pid)
                    if not handle:
                        missing.add(pid)
                    else:
                        created, ended, kernel, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
                        checked(get_times(handle, C.byref(created), C.byref(ended), C.byref(kernel), C.byref(user)))
                        identity = process_identity(pid, created)
                        if identity in handles or identity in recorded:
                            checked(close(handle))
                            continue
                        handles[identity] = handle
                        buffer, size = C.create_unicode_buffer(32768), W.DWORD(32768)
                        checked(image_name(handle, 0, buffer, C.byref(size)))
                        path = Path(buffer.value).resolve()
                        if path.is_relative_to(root):
                            machine = ProcessMachine()
                            checked(machine_info(handle, 9, C.byref(machine), C.sizeof(machine)))
                            if machine.machine == 0xAA64:
                                native[identity] = str(path)
                                basic = ProcessBasic()
                                status = query_basic(handle, 0, C.byref(basic), C.sizeof(basic), None)
                                if status < 0:
                                    raise RuntimeError(f"Cannot bind native parent generation: NTSTATUS {status & 0xffffffff:#x}")
                                ancestors = [key for key in handles
                                             if key[0] == basic.parent_pid and key[1] < identity[1]]
                                if ancestors:
                                    parents[identity] = max(ancestors, key=lambda key: key[1])
                for identity, handle in list(handles.items()):
                    if wait(handle, 0) == 0:
                        code = W.DWORD()
                        checked(get_exit(handle, C.byref(code)))
                        record = retire_process(native, recorded, identity, code.value, parents)
                        if record is not None:
                            exits.append(record)
                        checked(close(handle))
                        del handles[identity]
                accounting = Accounting()
                checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
                if accounting.active == 0 and not received:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    checked(terminate_job(job, 1460))
                    if wait(info.process, 10000) != 0:
                        raise RuntimeError("Owned job parent did not terminate")
                    break
            parent_exit = W.DWORD()
            checked(get_exit(info.process, C.byref(parent_exit)))
        relayed = {}
        for path in Path(relay_records).glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if "child_pid" in record and "child_created" in record:
                relayed.setdefault((record["child_pid"], record["child_created"]), []).append(record)
        unprotected = unprotected_native_exits(exits, relayed)
        return {
            "parent_pid": info.pid, "parent_raw_exit": parent_exit.value, "timed_out": timed_out,
            "created_processes": accounting.total, "observed_processes": len(recorded),
            "observation_count_matches": len(recorded) == accounting.total,
            "unobserved_process_ids": sorted(missing), "native_target_exits": exits,
            "unrelayed_high_exits": unprotected,
            "passed": not timed_out and parent_exit.value == 0 and not missing and not unprotected
                      and len(recorded) == accounting.total,
        }
    finally:
        try:
            if info.process and not assigned:
                checked(terminate_process(info.process, 1460))
            if assigned:
                accounting = Accounting()
                checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
                if accounting.active:
                    checked(terminate_job(job, 1460))
                    deadline = time.monotonic() + 10
                    while accounting.active and time.monotonic() < deadline:
                        time.sleep(0.05)
                        checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
                    if accounting.active:
                        raise RuntimeError("Owned job did not drain")
        finally:
            for handle in handles.values():
                checked(close(handle))
            for handle in (info.thread, info.process, port, job):
                if handle:
                    checked(close(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--relay-records", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("An explicit child command is required")
    result = run(command, args.cwd, args.target_root, args.relay_records, args.log, args.timeout)
    with open(args.result, "x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    raise SystemExit(0 if result["passed"] else 255)


if __name__ == "__main__":
    main()
