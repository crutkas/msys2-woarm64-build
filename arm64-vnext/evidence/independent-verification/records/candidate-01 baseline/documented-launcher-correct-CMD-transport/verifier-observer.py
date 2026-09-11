"""Independent ordinary Windows job observation; raw exits and path spellings are never rewritten."""

import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time


COMMON = Path(r"C:\ag-tcl-e138-01\observer\native-job.py")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def machine(path):
    with Path(path).open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError(f"Not a PE image: {path}")
        stream.seek(struct.unpack_from("<I", dos, 60)[0])
        pe = stream.read(6)
    if pe[:4] != b"PE\0\0":
        raise ValueError(f"Invalid PE signature: {path}")
    return f"0x{struct.unpack_from('<H', pe, 4)[0]:04X}"


def run(command, *, cwd, env, output, timeout=120, windows_command_line=None):
    """Use shared structure definitions only; collect every job process, including outside/x64 images."""
    import msvcrt
    spec = importlib.util.spec_from_file_location("windows_job_structures", COMMON)
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    output = Path(output)
    output.mkdir()
    shutil.copyfile(Path(__file__), output / "verifier-observer.py")
    save(output / "request.json", {"argv": list(map(str, command)), "cwd": str(cwd), "environment": env,
                                 "windows_command_line": windows_command_line or subprocess.list2cmdline(list(map(str, command))),
                                 "timeout_seconds": timeout, "structure_source": str(COMMON),
                                 "structure_source_sha256": sha(COMMON),
                                 "verifier_observer_sha256": sha(output / "verifier-observer.py"),
                                 "instrumentation": "Ordinary CreateProcess/job; no debugger, exit decoder, or relay"})
    kernel = C.WinDLL("kernel32", use_last_error=True)

    def bind(name, args, result=W.BOOL):
        method = getattr(kernel, name)
        method.argtypes, method.restype = args, result
        return method

    def checked(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    close = bind("CloseHandle", [W.HANDLE])
    create_job = bind("CreateJobObjectW", [W.LPVOID, W.LPCWSTR], W.HANDLE)
    set_job = bind("SetInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
    query_job = bind("QueryInformationJobObject", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID])
    port_create = bind("CreateIoCompletionPort", [W.HANDLE, W.HANDLE, C.c_size_t, W.DWORD], W.HANDLE)
    event_get = bind("GetQueuedCompletionStatus",
                     [W.HANDLE, C.POINTER(W.DWORD), C.POINTER(C.c_size_t), C.POINTER(W.LPVOID), W.DWORD])
    create = bind("CreateProcessW", [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL, W.DWORD,
                                     W.LPVOID, W.LPCWSTR, C.POINTER(common.StartupInfo),
                                     C.POINTER(common.ProcessInfo)])
    assign = bind("AssignProcessToJobObject", [W.HANDLE, W.HANDLE])
    resume = bind("ResumeThread", [W.HANDLE], W.DWORD)
    wait = bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    exit_code = bind("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)])
    times = bind("GetProcessTimes", [W.HANDLE, *[C.POINTER(W.FILETIME)] * 4])
    open_process = bind("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
    image = bind("QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)])
    enumerate_modules = bind("K32EnumProcessModulesEx",
                             [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD])
    module_name = bind("K32GetModuleFileNameExW", [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD], W.DWORD)
    terminate = bind("TerminateJobObject", [W.HANDLE, W.UINT])
    terminate_one = bind("TerminateProcess", [W.HANDLE, W.UINT])
    inherit = bind("SetHandleInformation", [W.HANDLE, W.DWORD, W.DWORD])
    get_mode = bind("GetErrorMode", [], W.UINT)
    set_mode = bind("SetErrorMode", [W.UINT], W.UINT)
    job = checked(create_job(None, None))
    port = None
    process = common.ProcessInfo()
    assigned = False
    handles, records, missing = {}, {}, []
    module_records, module_errors = {}, set()
    timed_out = False
    old_mode = get_mode()
    report = {"status": "observer-incomplete"}
    try:
        limits = common.ExtendedLimits()
        limits.basic.flags = 0x2000
        checked(set_job(job, 9, C.byref(limits), C.sizeof(limits)))
        port = checked(port_create(W.HANDLE(-1), None, 0, 1))
        link = common.CompletionPort(None, port)
        checked(set_job(job, 7, C.byref(link), C.sizeof(link)))
        set_mode(old_mode | 0x8003)
        with open(os.devnull, "rb") as stdin, (output / "output.log").open("xb") as log:
            ih, oh = msvcrt.get_osfhandle(stdin.fileno()), msvcrt.get_osfhandle(log.fileno())
            checked(inherit(ih, 1, 1))
            checked(inherit(oh, 1, 1))
            startup = common.StartupInfo()
            startup.cb, startup.flags = C.sizeof(startup), 0x100
            startup.stdin, startup.stdout, startup.stderr = ih, oh, oh
            environment = C.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda x: x[0].upper())) + "\0")
            try:
                checked(create(None, C.create_unicode_buffer(windows_command_line or subprocess.list2cmdline(list(map(str, command)))),
                               None, None, True, 0x404, environment, str(cwd),
                               C.byref(startup), C.byref(process)))
            finally:
                checked(inherit(ih, 1, 0))
                checked(inherit(oh, 1, 0))
                set_mode(old_mode)
            checked(assign(job, process.process))
            assigned = True
            created, ended, kt, ut = (W.FILETIME() for _ in range(4))
            checked(times(process.process, C.byref(created), C.byref(ended), C.byref(kt), C.byref(ut)))
            born = created.dwHighDateTime << 32 | created.dwLowDateTime
            save(output / "launch.json", {"pid": process.pid, "creation_filetime": born,
                                         "argv": list(map(str, command)), "log": str(output / "output.log")})
            if resume(process.thread) != 1:
                raise RuntimeError("Unexpected process suspension count")
            deadline = time.monotonic() + timeout
            while True:
                code, key, value = W.DWORD(), C.c_size_t(), W.LPVOID()
                received = event_get(port, C.byref(code), C.byref(key), C.byref(value), 10)
                if not received and C.get_last_error() != 258:
                    raise C.WinError(C.get_last_error())
                if received and code.value == 6:
                    pid = value.value
                    handle = open_process(0x100000 | 0x1000 | 0x0400 | 0x0010, False, pid)
                    if not handle:
                        missing.append({"pid": pid, "error": C.get_last_error()})
                    else:
                        ts = [W.FILETIME() for _ in range(4)]
                        checked(times(handle, *[C.byref(item) for item in ts]))
                        generation = (pid, ts[0].dwHighDateTime << 32 | ts[0].dwLowDateTime)
                        if generation in records:
                            checked(close(handle))
                        else:
                            records[generation] = {"pid": pid, "creation_filetime": generation[1],
                                                   "image": None, "image_query_errors": []}
                            handles[generation] = handle
                for generation, handle in list(handles.items()):
                    if records[generation]["image"] is None:
                        name, size = C.create_unicode_buffer(32768), W.DWORD(32768)
                        if image(handle, 0, name, C.byref(size)):
                            records[generation].update(image=name.value, machine=machine(name.value),
                                                       sha256=sha(name.value))
                        else:
                            records[generation]["image_query_errors"].append(C.get_last_error())
                    modules, needed = (W.HMODULE * 1024)(), W.DWORD()
                    if enumerate_modules(handle, modules, C.sizeof(modules), C.byref(needed), 3):
                        if needed.value > C.sizeof(modules):
                            raise RuntimeError("Module snapshot buffer exhausted")
                        for module in modules[:needed.value // C.sizeof(W.HMODULE)]:
                            name = C.create_unicode_buffer(32768)
                            if module_name(handle, module, name, len(name)):
                                identity = (generation, name.value)
                                if identity not in module_records:
                                    module_records[identity] = {"pid": generation[0], "creation_filetime": generation[1],
                                                                "path": name.value, "machine": machine(name.value),
                                                                "sha256": sha(name.value)}
                            else:
                                module_errors.add((generation[0], generation[1], "module-name", C.get_last_error()))
                    else:
                        module_errors.add((generation[0], generation[1], "enumerate", C.get_last_error()))
                    if wait(handle, 0) == 0:
                        raw = W.DWORD()
                        checked(exit_code(handle, C.byref(raw)))
                        records[generation]["raw_exit"] = raw.value
                        checked(close(handle))
                        del handles[generation]
                accounting = common.Accounting()
                checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
                if accounting.active == 0 and not received:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    checked(terminate(job, 1460))
                    break
            if wait(process.process, 10000) != 0:
                raise RuntimeError("Owned parent did not exit")
            raw = W.DWORD()
            checked(exit_code(process.process, C.byref(raw)))
            report = {"status": "observed", "parent_pid": process.pid, "parent_birth": born,
                      "parent_raw_exit": raw.value, "timed_out": timed_out,
                      "created_processes": accounting.total, "observed_processes": len(records),
                      "missing_process_events": missing, "processes": list(records.values()),
                      "unidentified_processes": [r for r in records.values() if r["image"] is None],
                      "module_snapshots": list(module_records.values()),
                      "module_snapshot_errors": sorted(module_errors),
                      "module_coverage": "Best-effort ordinary-process sampling, NOT complete load-event coverage",
                      "error_dialog_policy": "Per-verifier-process SEM0x8003 inherited and then restored; no global changes"}
    finally:
        set_mode(old_mode)
        if process.process and not assigned:
            checked(terminate_one(process.process, 1460))
        if assigned:
            accounting = common.Accounting()
            checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
            if accounting.active:
                checked(terminate(job, 1460))
                deadline = time.monotonic() + 10
                while accounting.active and time.monotonic() < deadline:
                    time.sleep(0.05)
                    checked(query_job(job, 1, C.byref(accounting), C.sizeof(accounting), None))
            report["active_owned_at_cleanup"] = accounting.active
            if accounting.active:
                raise RuntimeError("Owned job failed to drain")
        for handle in handles.values():
            checked(close(handle))
        for handle in (process.thread, process.process, port, job):
            if handle:
                checked(close(handle))
        save(output / "observation.json", report)
    return report
