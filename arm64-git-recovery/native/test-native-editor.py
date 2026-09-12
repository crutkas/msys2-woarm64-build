"""Edit and save an owned file with native nano inside a private Windows pseudoconsole."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from bounded_process import ProcessInfo, StartupInfo
from sources import ContractError, digest


class Coord(C.Structure):
    _fields_ = [("x", C.c_short), ("y", C.c_short)]


class StartupInfoEx(C.Structure):
    _fields_ = [("startup", StartupInfo), ("attributes", C.c_void_p)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "output", "pwsh", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--console-probe", type=Path, help="Run only a native Win32 console API discriminator")
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a new editor fixture are required")
    args.output.mkdir(parents=True)
    (args.output / "home").mkdir()
    fixture = args.output / "editor-fixture.txt"
    fixture.write_bytes(b"before\n")
    executable = args.console_probe or args.root / "usr/bin/nano.exe"
    api = C.WinDLL("kernel32", use_last_error=True)

    def bind(name, arguments, result=W.BOOL):
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
        return function

    create_pipe = bind("CreatePipe", [C.POINTER(W.HANDLE), C.POINTER(W.HANDLE), W.LPVOID, W.DWORD])
    create_console = bind("CreatePseudoConsole", [Coord, W.HANDLE, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], C.c_long)
    close_console = bind("ClosePseudoConsole", [W.HANDLE], None)
    init_attributes = bind("InitializeProcThreadAttributeList", [W.LPVOID, W.DWORD, W.DWORD, C.POINTER(C.c_size_t)])
    update_attributes = bind("UpdateProcThreadAttribute", [W.LPVOID, W.DWORD, C.c_size_t, W.LPVOID,
                                                          C.c_size_t, W.LPVOID, W.LPVOID])
    delete_attributes = bind("DeleteProcThreadAttributeList", [W.LPVOID], None)
    create_process = bind("CreateProcessW", [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL, W.DWORD,
                                            W.LPVOID, W.LPCWSTR, C.POINTER(StartupInfoEx), C.POINTER(ProcessInfo)])
    read = bind("ReadFile", [W.HANDLE, W.LPVOID, W.DWORD, C.POINTER(W.DWORD), W.LPVOID])
    write = bind("WriteFile", [W.HANDLE, W.LPVOID, W.DWORD, C.POINTER(W.DWORD), W.LPVOID])
    wait = bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    exit_code = bind("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)])
    terminate = bind("TerminateProcess", [W.HANDLE, W.UINT])
    close = bind("CloseHandle", [W.HANDLE])

    def checked(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    input_read, input_write, output_read, output_write, console = (W.HANDLE() for _ in range(5))
    process = ProcessInfo()
    attributes = None
    output = bytearray()
    lock, changed = threading.Lock(), threading.Event()
    reader_errors = []
    thread = None
    report = {"passed": False, "scope": "Private ConPTY editing only; no user desktop, config, credentials or services",
              "executable": str(executable), "executable_sha256": digest(executable)}
    try:
        checked(create_pipe(C.byref(input_read), C.byref(input_write), None, 0))
        checked(create_pipe(C.byref(output_read), C.byref(output_write), None, 0))
        status = create_console(Coord(100, 30), input_read, output_write, 0, C.byref(console))
        if status != 0:
            raise ContractError(f"CreatePseudoConsole failed: 0x{status & 0xffffffff:08x}")
        size = C.c_size_t()
        init_attributes(None, 1, 0, C.byref(size))
        if not size.value:
            raise ContractError("No process attribute-list size returned")
        attributes = C.create_string_buffer(size.value)
        checked(init_attributes(attributes, 1, 0, C.byref(size)))
        checked(update_attributes(attributes, 0, 0x00020016, console, C.sizeof(W.HANDLE), None, None))
        startup = StartupInfoEx()
        startup.startup.cb = C.sizeof(startup)
        startup.attributes = C.cast(attributes, C.c_void_p)
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        env.update({"PATH": str(args.root / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                    "HOME": str(args.output / "home"), "TERM": "xterm-256color",
                    "TERMINFO": str(args.root / "usr/share/terminfo"), "LC_ALL": "C.UTF-8",
                    "TMP": str(args.output), "TEMP": str(args.output)})
        environment = C.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(env.items())) + "\0")
        command = [str(executable), "--ignorercfiles", "--nonewlines", str(fixture)]
        if args.console_probe:
            command = [str(executable), str(args.output / "win32-console.json")]
        checked(create_process(None, C.create_unicode_buffer(subprocess.list2cmdline(command)), None, None,
                               False, 0x80400, environment, str(args.output), C.byref(startup), C.byref(process)))
        checked(close(input_read)); input_read.value = None
        checked(close(output_write)); output_write.value = None
        report["pid"] = process.pid

        def drain():
            while True:
                data, count = C.create_string_buffer(8192), W.DWORD()
                if not read(output_read, data, len(data), C.byref(count), None):
                    error = C.get_last_error()
                    if error not in (109, 232):
                        reader_errors.append(error)
                    changed.set()
                    return
                with lock:
                    output.extend(data.raw[:count.value])
                changed.set()

        thread = threading.Thread(target=drain)
        thread.start()

        def await_text(text, start=0):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                with lock:
                    if text in output[start:]:
                        return
                if wait(process.process, 0) == 0:
                    raise ContractError("Native editor exited before the requested terminal state")
                changed.wait(0.2)
                changed.clear()
            raise ContractError(f"Native editor did not display expected state: {text!r}")

        def send(data):
            count = W.DWORD()
            checked(write(input_write, data, len(data), C.byref(count), None))
            if count.value != len(data):
                raise ContractError("Incomplete pseudoconsole input")

        if not args.console_probe:
            await_text(b"before")
            subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                            "-ProcessId", str(process.pid), "-ReportPath", str(args.output / "process.json")], check=True)
            send(b"\x05" + " after \u03bb".encode("utf-8") + b"\x0f")
            await_text(b"Write to File:")
            send(b"\r")
            await_text(b"Wrote")
            send(b"\x18")
        if wait(process.process, 15000) != 0:
            raise ContractError("Native editor did not exit after save")
        code = W.DWORD()
        checked(exit_code(process.process, C.byref(code)))
        report["exit"] = code.value
        if args.console_probe:
            report["console_api"] = json.loads((args.output / "win32-console.json").read_text())
            report["scope"] = "Native Win32 console API discriminator only; not editor behavior"
            report["passed"] = code.value == 0
        else:
            expected = "before after \u03bb\n".encode("utf-8")
            report["actual_hex"], report["expected_hex"] = fixture.read_bytes().hex(), expected.hex()
            report["passed"] = code.value == 0 and fixture.read_bytes() == expected
    finally:
        if process.process:
            if wait(process.process, 0) != 0:
                checked(terminate(process.process, 1460))
                wait(process.process, 10000)
            checked(close(process.process))
            checked(close(process.thread))
        if console:
            close_console(console)
        if thread:
            thread.join(10)
        for handle in (input_read, input_write, output_read, output_write):
            if handle:
                close(handle)
        if attributes:
            delete_attributes(attributes)
        with lock:
            (args.output / "terminal-output.bin").write_bytes(output)
        report["reader_errors"] = reader_errors
        report["passed"] = report["passed"] and not reader_errors
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native editor save/readback failed")
    print("Native console API discriminator completed" if args.console_probe else
          "Native nano edited and saved the exact Unicode fixture through a private terminal")


if __name__ == "__main__":
    main()
