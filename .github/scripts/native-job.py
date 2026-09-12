"""Bind a Windows process tree and retain native target exits independently of its shell."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import ntpath
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


def unprotected_native_exits(exits, relayed, expected_contracts=None):
    records = {(record["pid"], record["created"]): record for record in exits}
    protected = {(record["pid"], record["created"])
                 for record in expected_probe_exits(exits, relayed, expected_contracts or {})}
    for identity, record in records.items():
        if record["raw_exit"] <= 255:
            continue
        candidates = relayed.get(identity, [])
        match = next((candidate for candidate in candidates
                      if candidate.get("raw_exit", 0) & 0xFFFFFFFF == record["raw_exit"]
                      and candidate.get("portable_exit") == 255
                      and candidate.get("executable")
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


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def matches_sha256(path, expected):
    if not expected:
        return True
    try:
        return file_sha256(path) == expected
    except OSError:
        return False


def exited_msys_wait_status(raw_exit, portable_exit):
    return (0 <= raw_exit <= 0xffff and raw_exit & 0xff == 0
            and (raw_exit >> 8) & 0xff == portable_exit)


def expected_probe_exits(exits, relayed, contracts):
    records = {(record["pid"], record["created"]): record for record in exits}
    protected = []
    for identity, record in records.items():
        parent = (record.get("parent_pid"), record.get("parent_created"))
        parent_record = records.get(parent)
        if parent_record is None:
            continue
        for candidate in relayed.get(identity, []):
            name = candidate.get("expected_exit_contract")
            contract = contracts.get(name)
            child_name = contract.get("child_image_name", contract.get("image_name", "")) \
                if contract else ""
            parent_name = contract.get("parent_image_name", child_name) if contract else ""
            encoding = contract.get("encoding") if contract else None
            if (contract is not None
                    and candidate.get("probe_source_sha256") == contract.get("probe_source_sha256")
                    and candidate.get("parent_pid") == parent[0]
                    and candidate.get("parent_created") == parent[1]
                    and candidate.get("expected_raw_exit") == contract.get("raw_exit")
                    and candidate.get("portable_exit") == contract.get("portable_exit")
                    and record["raw_exit"] == contract.get("raw_exit")
                    and parent_record["raw_exit"] == contract.get("parent_raw_exit")
                    and ntpath.basename(record["executable"]).casefold()
                    == str(child_name).casefold()
                    and ntpath.basename(parent_record["executable"]).casefold()
                    == str(parent_name).casefold()
                    and matches_sha256(record["executable"], contract.get("image_sha256"))
                    and matches_sha256(parent_record["executable"],
                                       contract.get("parent_image_sha256"))
                    and (encoding != "msys-posix-wait-status-v1"
                         or exited_msys_wait_status(record["raw_exit"],
                                                    contract["portable_exit"]))):
                protected.append({
                    "pid": identity[0], "created": identity[1], "executable": record["executable"],
                    "raw_exit": record["raw_exit"], "portable_exit": contract["portable_exit"],
                    "parent_pid": parent[0], "parent_created": parent[1],
                    "expected_exit_contract": name,
                    "probe_source_sha256": contract["probe_source_sha256"],
                    "encoding": encoding,
                    "classification": ("generation-bound-msys-wait-status"
                                       if encoding == "msys-posix-wait-status-v1"
                                       else "generation-bound-expected-probe-exit"),
                })
                break
    return protected


def normalise_windows_path(path):
    value = ntpath.normpath(str(path))
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return ntpath.normcase(value)


def path_is_within(path, root):
    path = normalise_windows_path(path)
    root = normalise_windows_path(root)
    try:
        return ntpath.commonpath((path, root)) == root
    except ValueError:
        return False


def bind_parent_generation(parent_pid, child_created, identities):
    candidates = [identity for identity in identities
                  if identity[0] == parent_pid and identity[1] < child_created]
    return max(candidates, key=lambda identity: identity[1]) if candidates else None


def query_process_image(image_name, handle):
    errors = []
    for kind, flags in (("win32", 0), ("native", 1)):
        buffer, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        C.set_last_error(0)
        if image_name(handle, flags, buffer, C.byref(size)):
            return {"path": buffer.value, "kind": kind, "errors": errors}
        errors.append({"kind": kind, "error": C.get_last_error()})
    return {"path": None, "kind": None, "errors": errors}


def query_native_root(root, query_dos_device):
    win32_root = normalise_windows_path(root)
    drive, tail = ntpath.splitdrive(win32_root)
    if not drive:
        return None, None
    buffer = C.create_unicode_buffer(32768)
    C.set_last_error(0)
    if not query_dos_device(drive, buffer, len(buffer)):
        return None, C.get_last_error()
    device = buffer[:].split("\0", 1)[0]
    return normalise_windows_path(device + tail), None


def classify_image(image, win32_root, native_root):
    if image["kind"] == "win32":
        return "target" if path_is_within(image["path"], win32_root) else "outside-target"
    if image["kind"] == "native" and native_root:
        return "target" if path_is_within(image["path"], native_root) else "outside-target"
    return None


def load_expected_contracts(path=None):
    contract_path = Path(path) if path else Path(__file__).with_name(
        "expected-exit-contracts.json")
    if not contract_path.is_file():
        if path:
            raise FileNotFoundError(contract_path)
        return {}
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    contracts = document.get("contracts")
    if document.get("schema") not in (1, 2) or not isinstance(contracts, dict):
        raise ValueError(f"Invalid expected-exit contract file {contract_path}")
    return contracts


def run(command, cwd, target_root, relay_records, log_path, timeout,
        expected_exit_contracts=None):
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
    query_dos_device = bind("QueryDosDeviceW", [W.LPCWSTR, W.LPWSTR, W.DWORD], W.DWORD)
    machine_info = bind("GetProcessInformation", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD])
    query_basic = C.WinDLL("ntdll").NtQueryInformationProcess
    query_basic.argtypes = [W.HANDLE, C.c_int, W.LPVOID, W.ULONG, W.LPVOID]
    query_basic.restype = W.LONG
    terminate_job = bind("TerminateJobObject", [W.HANDLE, W.UINT])
    terminate_process = bind("TerminateProcess", [W.HANDLE, W.UINT])
    inherit = bind("SetHandleInformation", [W.HANDLE, W.DWORD, W.DWORD])

    win32_root = normalise_windows_path(Path(target_root).resolve())
    native_root, native_root_error = query_native_root(win32_root, query_dos_device)
    expected_contracts = load_expected_contracts(expected_exit_contracts)
    runtime_exit_dir = Path(log_path).with_name("native-exit-relays")
    if runtime_exit_dir.exists():
        raise FileExistsError(runtime_exit_dir)
    runtime_exit_dir.mkdir()
    job = checked(create_job(None, None))
    port = None
    info = ProcessInfo()
    assigned = False
    handles = {}
    states = {}
    identities = set()
    native = {}
    parents = {}
    exits = []
    missing = []
    unresolved = []
    recorded = set()
    recovered_images = []
    timed_out = False

    def inspect_process(identity):
        state = states[identity]
        if state["classification"] is None:
            image = query_process_image(image_name, state["handle"])
            state["image_query_attempts"] += 1
            for error in image["errors"]:
                if error not in state["image_query_errors"]:
                    state["image_query_errors"].append(error)
            if image["path"]:
                state["image"] = image["path"]
                state["image_kind"] = image["kind"]
                state["classification"] = classify_image(image, win32_root, native_root)
                if image["errors"] and state["classification"] is not None:
                    recovered_images.append({
                        "pid": identity[0], "created": identity[1], "image": image["path"],
                        "image_kind": image["kind"], "prior_errors": image["errors"],
                    })
        if state["classification"] == "target" and state["machine"] is None:
            machine = ProcessMachine()
            C.set_last_error(0)
            if machine_info(state["handle"], 9, C.byref(machine), C.sizeof(machine)):
                state["machine"] = machine.machine
                if machine.machine == 0xAA64:
                    native[identity] = state["image"]
            else:
                error = C.get_last_error()
                if error not in state["machine_query_errors"]:
                    state["machine_query_errors"].append(error)
        if identity in native and not state["parent_bound"]:
            basic = ProcessBasic()
            status = query_basic(state["handle"], 0, C.byref(basic), C.sizeof(basic), None)
            if status >= 0:
                state["parent_bound"] = True
                parent = bind_parent_generation(basic.parent_pid, identity[1], identities)
                if parent:
                    parents[identity] = parent
            else:
                status = status & 0xFFFFFFFF
                if status not in state["parent_query_statuses"]:
                    state["parent_query_statuses"].append(status)

    def register_process(pid, handle):
        created, ended, kernel, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
        C.set_last_error(0)
        if not get_times(handle, C.byref(created), C.byref(ended), C.byref(kernel), C.byref(user)):
            missing.append({"pid": pid, "generation_error": C.get_last_error()})
            checked(close(handle))
            return
        identity = process_identity(pid, created)
        if identity in handles or identity in recorded:
            checked(close(handle))
            return
        handles[identity] = handle
        identities.add(identity)
        states[identity] = {
            "handle": handle, "image": None, "image_kind": None, "classification": None,
            "machine": None, "image_query_attempts": 0, "image_query_errors": [],
            "machine_query_errors": [],
            "parent_query_statuses": [], "parent_bound": False,
        }
        inspect_process(identity)

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
            child_environment = os.environ.copy()
            child_environment["WOARM64_NATIVE_EXIT_DIR"] = str(runtime_exit_dir)
            environment = C.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(
                    child_environment.items(), key=lambda row: row[0].upper())) + "\0")
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
                        missing.append({"pid": pid, "open_error": C.get_last_error()})
                    else:
                        register_process(pid, handle)
                for identity, handle in list(handles.items()):
                    inspect_process(identity)
                    if wait(handle, 0) == 0:
                        inspect_process(identity)
                        code = W.DWORD()
                        checked(get_exit(handle, C.byref(code)))
                        state = states[identity]
                        if (state["classification"] is None
                                or (state["classification"] == "target" and state["machine"] is None)):
                            unresolved.append({
                                "pid": identity[0], "created": identity[1],
                                "image": state["image"], "image_kind": state["image_kind"],
                                "image_query_attempts": state["image_query_attempts"],
                                "image_query_errors": state["image_query_errors"],
                                "machine_query_errors": state["machine_query_errors"],
                            })
                        record = retire_process(native, recorded, identity, code.value, parents)
                        if record is not None:
                            exits.append(record)
                        checked(close(handle))
                        del handles[identity]
                        del states[identity]
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
        runtime_relay_evidence = []
        for path in runtime_exit_dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if "child_pid" not in record or "child_created" not in record:
                raise ValueError(f"Unbound expected-exit relay {path}")
            runtime_relay_evidence.append({
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
            relayed.setdefault((record["child_pid"], record["child_created"]), []).append(record)
        expected_exits = expected_probe_exits(exits, relayed, expected_contracts)
        unprotected = unprotected_native_exits(exits, relayed, expected_contracts)
        return {
            "parent_pid": info.pid, "parent_raw_exit": parent_exit.value, "timed_out": timed_out,
            "created_processes": accounting.total, "observed_processes": len(recorded),
            "observation_count_matches": len(recorded) == accounting.total,
            "unobserved_processes": missing, "unresolved_processes": unresolved,
            "native_target_exits": exits, "unrelayed_high_exits": unprotected,
            "expected_probe_exits": expected_exits,
            "runtime_exit_relays": runtime_relay_evidence,
            "image_query_recoveries": recovered_images,
            "native_target_root": native_root, "native_target_root_error": native_root_error,
            "passed": not timed_out and parent_exit.value == 0 and not missing and not unresolved
                      and not unprotected and len(recorded) == accounting.total,
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
    parser.add_argument("--expected-exit-contracts")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("An explicit child command is required")
    result = run(command, args.cwd, args.target_root, args.relay_records, args.log, args.timeout,
                 args.expected_exit_contracts)
    with open(args.result, "x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    raise SystemExit(0 if result["passed"] else 255)


if __name__ == "__main__":
    main()
