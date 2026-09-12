"""Run a Windows build fixture inside a kill-on-close job, with a bounded lifetime."""

import ctypes as C
from ctypes import wintypes as W
import os
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
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_int64), ("job_time", C.c_int64),
                ("flags", W.DWORD), ("min_working", C.c_size_t), ("max_working", C.c_size_t),
                ("active_limit", W.DWORD), ("affinity", C.c_size_t),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                ("process_memory", C.c_size_t), ("job_memory", C.c_size_t),
                ("peak_process", C.c_size_t), ("peak_job", C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [(name, C.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        ("page_faults", W.DWORD), ("total", W.DWORD), ("active", W.DWORD), ("terminated", W.DWORD)]


class JobProcessIds(C.Structure):
    _fields_ = [("assigned", W.DWORD), ("count", W.DWORD), ("ids", C.c_size_t * 64)]


def run(command, *, cwd, env, log, timeout, on_started=None, drain_grace=0.5):
    if os.name != "nt" or not 0 < timeout <= 86400 or not 0 <= drain_grace <= 10:
        raise ValueError("Windows and an explicit bounded timeout are required")
    import msvcrt

    api = C.WinDLL("kernel32", use_last_error=True)

    def bind(name, args, result=W.BOOL):
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
        return function

    create_job = bind("CreateJobObjectW", [W.LPVOID, W.LPCWSTR], W.HANDLE)
    close = bind("CloseHandle", [W.HANDLE])
    set_job = bind("SetInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
    query_job = bind("QueryInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID])
    create = bind("CreateProcessW", [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL,
                                    W.DWORD, W.LPVOID, W.LPCWSTR,
                                    C.POINTER(StartupInfo), C.POINTER(ProcessInfo)])
    assign = bind("AssignProcessToJobObject", [W.HANDLE, W.HANDLE])
    resume = bind("ResumeThread", [W.HANDLE], W.DWORD)
    wait = bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    terminate_job = bind("TerminateJobObject", [W.HANDLE, W.UINT])
    terminate_process = bind("TerminateProcess", [W.HANDLE, W.UINT])
    get_exit = bind("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)])
    inherit = bind("SetHandleInformation", [W.HANDLE, W.DWORD, W.DWORD])
    open_process = bind("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
    image_name = bind("QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)])

    def checked(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    job = checked(create_job(None, None))
    info = ProcessInfo()
    assigned = False
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        checked(set_job(job, 9, C.byref(limits), C.sizeof(limits)))
        with open(os.devnull, "rb") as stdin:
            input_handle = msvcrt.get_osfhandle(stdin.fileno())
            output_handle = msvcrt.get_osfhandle(log.fileno())
            checked(inherit(input_handle, 1, 1))
            checked(inherit(output_handle, 1, 1))
            startup = StartupInfo()
            startup.cb, startup.flags = C.sizeof(startup), 0x100
            startup.stdin, startup.stdout, startup.stderr = input_handle, output_handle, output_handle
            environment = C.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda x: x[0].upper())) + "\0")
            try:
                checked(create(None, C.create_unicode_buffer(subprocess.list2cmdline(list(map(str, command)))),
                               None, None, True, 0x404, environment, str(cwd),
                               C.byref(startup), C.byref(info)))
            finally:
                checked(inherit(input_handle, 1, 0))
                checked(inherit(output_handle, 1, 0))
        # Assign while suspended: not even the first child can escape the job.
        checked(assign(job, info.process))
        assigned = True
        if resume(info.thread) != 1:
            raise RuntimeError("Unexpected initial thread suspension count")
        started = time.monotonic()
        if on_started:
            on_started(info.pid)
        remaining = max(0, timeout - (time.monotonic() - started))
        status = wait(info.process, int(remaining * 1000))
        if status not in (0, 258):
            raise C.WinError(C.get_last_error())
        accounting = Accounting()
        checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
        timed_out = status == 258
        active_at_parent_exit = accounting.active
        grace_end = min(time.monotonic() + drain_grace, started + timeout)
        while not timed_out and accounting.active and time.monotonic() < grace_end:
            time.sleep(0.05)
            checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
        remaining_processes = []
        remaining_details = []
        if accounting.active:
            ids = JobProcessIds()
            checked(query_job(job, 3, C.byref(ids), C.sizeof(ids), None))
            remaining_processes = list(ids.ids[:ids.count])
            for pid in remaining_processes:
                handle = open_process(0x1000, False, pid)
                detail = {"pid": pid}
                if handle:
                    try:
                        buffer, size = C.create_unicode_buffer(32768), W.DWORD(32768)
                        if image_name(handle, 0, buffer, C.byref(size)):
                            detail["image"] = buffer.value
                        else:
                            detail["query_error"] = C.get_last_error()
                    finally:
                        checked(close(handle))
                else:
                    detail["query_error"] = C.get_last_error()
                remaining_details.append(detail)
        if timed_out:
            checked(terminate_job(job, 1460))
            if wait(info.process, 10000) != 0:
                raise RuntimeError("Owned job did not terminate")
        code = W.DWORD()
        checked(get_exit(info.process, C.byref(code)))
        return {"pid": info.pid, "exit": code.value, "timed_out": timed_out,
                "active_at_parent_exit": active_at_parent_exit,
                "active_at_boundary": accounting.active,
                "remaining_process_ids": remaining_processes,
                "remaining_process_details": remaining_details,
                "created_processes": accounting.total,
                "drain_grace_seconds": drain_grace,
                "passed": not timed_out and code.value == 0 and accounting.active == 0}
    finally:
        try:
            if info.process and not assigned:
                checked(terminate_process(info.process, 1460))
                if wait(info.process, 10000) != 0:
                    raise RuntimeError("Unassigned owned process did not terminate")
            if assigned:
                cleanup = Accounting()
                checked(query_job(job, 1, C.byref(cleanup), C.sizeof(cleanup), None))
                if cleanup.active:
                    termination_handles = []
                    try:
                        ids = JobProcessIds()
                        checked(query_job(job, 3, C.byref(ids), C.sizeof(ids), None))
                        if ids.count > len(ids.ids) or ids.assigned > len(ids.ids):
                            raise RuntimeError("Owned cleanup process list exceeds its bounded capacity")
                        for pid in ids.ids[:ids.count]:
                            handle = open_process(0x100000, False, pid)
                            if handle:
                                termination_handles.append(handle)
                            elif C.get_last_error() != 87:
                                raise C.WinError(C.get_last_error())
                        checked(terminate_job(job, 1460))
                        deadline = time.monotonic() + 10
                        # Job accounting can drop before process handles signal final I/O teardown.
                        for handle in termination_handles:
                            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                            if wait(handle, remaining_ms) != 0:
                                raise RuntimeError("An owned process did not finish termination")
                        while cleanup.active and time.monotonic() < deadline:
                            time.sleep(0.05)
                            checked(query_job(job, 1, C.byref(cleanup), C.sizeof(cleanup), None))
                        if cleanup.active:
                            raise RuntimeError("Owned job did not drain after termination")
                    finally:
                        for handle in termination_handles:
                            checked(close(handle))
        finally:
            checked(close(job))
            for handle in (info.thread, info.process):
                if handle:
                    checked(close(handle))
