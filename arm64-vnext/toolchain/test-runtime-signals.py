#!/usr/bin/env python3
"""Build and exercise native signal register/fault probes with an explicit DLL trio."""
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
import time

RECIPE = Path(__file__).resolve().parent


def identity(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk", "runtime", "import-library", "crt0", "runner", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("runtime", "import-library", "crt0", "runner"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--extra-probes", type=Path, nargs="*", default=[],
                        help="Existing native regression executables to copy unchanged and require raw exit zero")
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    selected = ((args.runtime, args.runtime_sha256), (args.import_library, args.import_library_sha256),
                (args.crt0, args.crt0_sha256), (args.runner, args.runner_sha256))
    for path, digest in selected:
        if identity(path)["sha256"] != digest:
            raise ValueError(f"Selected source-cohort input differs: {path}")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    link = out / "link-inputs"
    link.mkdir()
    shutil.copy2(args.crt0, link / "crt0.o")
    shutil.copy2(args.import_library, link / "libmsys-2.0.a")
    shutil.copy2(args.runtime, out / "msys-2.0.dll")
    shutil.copy2(sdk / "bin/msys-gcc_s-seh-1.dll", out / "msys-gcc_s-seh-1.dll")
    sources = ("signal-registers-arm64.c", "signal-registers-arm64.S", "signal-myfault-arm64.c")
    for name in sources:
        shutil.copy2(RECIPE / "probes" / name, out / name)
    extras = out / "regressions"
    extras.mkdir()
    for path in args.extra_probes:
        if (extras / path.name).exists():
            raise ValueError("Duplicate regression executable")
        shutil.copy2(path, extras / path.name)
    shutil.copy2(args.runtime, extras / "msys-2.0.dll")
    bounded = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    modules = runpy.run_path(str(RECIPE / "native-loaded-modules.py"))["modules"]
    noninteractive = runpy.run_path(str(RECIPE / "run-msys-library-stage.py"))["noninteractive"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(out) + os.pathsep + str(sdk / "bin") + os.pathsep
               + str(Path(os.environ["SystemRoot"]) / "System32"),
               HOME=str(out), TMP=str(out), TEMP=str(out))
    inputs = [identity(path) for path, _ in selected]
    inputs += [identity(sdk / "bin/gcc.exe")] + [identity(out / name) for name in sources]
    inputs += [identity(path) for path in args.extra_probes]
    report = {"schema": 1, "status": "failed", "inputs": inputs, "runs": [], "loaded_modules": {},
              "recipe": identity(Path(__file__)), "raw_pe": {}}
    cc = sdk / "bin/gcc.exe"
    prefix = "-B" + str(link) + os.sep

    def run(name, argv, marker=None):
        log = out / (name + ".log")
        machines = []

        def started(pid):
            machines.append(native(pid, Path(argv[0])))
            if marker:
                api = ctypes.WinDLL("kernel32", use_last_error=True)
                api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                api.OpenProcess.restype = wintypes.HANDLE
                api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                api.WaitForSingleObject.restype = wintypes.DWORD
                api.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = api.OpenProcess(0x100000, False, pid)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                deadline = time.monotonic() + 10
                try:
                    while marker not in log.read_bytes():
                        state = api.WaitForSingleObject(handle, 0)
                        if state == 0 or time.monotonic() > deadline:
                            # Return to the bounded runner to retain the raw
                            # failing exit/timeout before rejecting the marker.
                            return
                        if state != 0x102:
                            raise ctypes.WinError(ctypes.get_last_error())
                        time.sleep(0.01)
                    report["loaded_modules"][name] = modules(pid)
                finally:
                    api.CloseHandle(handle)

        with log.open("xb") as stream, noninteractive():
            result = bounded(list(map(str, argv)), cwd=out, env=env, log=stream,
                             timeout=20 if marker else 120, on_started=started)
        report["runs"].append({"name": name, "argv": list(map(str, argv)), "process": result,
                               "native": machines, "log": identity(log)})
        if not result["passed"]:
            raise ValueError(f"Native probe failed or did not drain: {name}: {result}")
        if marker and log.read_bytes().replace(b"\r\n", b"\n") != marker + b"\n":
            raise ValueError(f"Unexpected native probe output: {name}")
        return log.read_bytes()

    try:
        for name in ("crt0.o", "libmsys-2.0.a"):
            found = Path(run("select-" + name, [cc, prefix, "-print-file-name=" + name]).decode().strip())
            if identity(found) != identity(link / name):
                raise ValueError("GCC did not select the explicit new runtime link input")
        common = [cc, prefix, "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-pthread",
                  "-fstack-protector-strong"]
        run("register-build", common + [out / sources[0], out / sources[1], "-o", out / "registers.exe"])
        run("myfault-build", common + [out / sources[2], "-o", out / "myfault.exe"])
        for path in [out / "msys-2.0.dll", out / "registers.exe", out / "myfault.exe"] + [
                extras / path.name for path in args.extra_probes]:
            raw = path.read_bytes()
            pe = struct.unpack_from("<I", raw, 0x3c)[0]
            if (raw[:2] != b"MZ" or raw[pe:pe + 4] != b"PE\0\0" or
                    struct.unpack_from("<H", raw, pe + 4)[0] != 0xaa64 or
                    struct.unpack_from("<H", raw, pe + 24)[0] != 0x20b):
                raise ValueError(f"Not raw ARM64 PE32+: {path}")
            report["raw_pe"][path.name] = identity(path)
        for name, marker in (
                ("registers", b"arm64-signal-registers-ok: 16 deliveries, integer/vector/control state"),
                ("myfault", b"arm64-myfault-efault-ok: 8 protected-page faults")):
            run(name, [out / (name + ".exe"), "--hold"], marker)
            actual = {Path(row["path"]).name.lower(): row for row in report["loaded_modules"][name]}
            if actual["msys-2.0.dll"]["sha256"] != args.runtime_sha256:
                raise ValueError("Wrong actual mapped MSYS runtime")
            if Path(actual["msys-2.0.dll"]["path"]).resolve() != out / "msys-2.0.dll":
                raise ValueError("MSYS runtime escaped owned loader-adjacent directory")
        for path in args.extra_probes:
            if identity(extras / path.name)["sha256"] != identity(path)["sha256"]:
                raise ValueError("Existing regression executable changed during copy")
            run("regression-" + path.stem, [extras / path.name])
        for item in inputs:
            if identity(Path(item["path"])) != item:
                raise ValueError("Input changed during qualification")
        report.update(status="native-arm64-signal-register-and-myfault-qualified",
                      existing_regressions=[path.name for path in args.extra_probes],
                      limits="Ordinary asynchronous signal register/FP restoration and repeated myfault EFAULT. Debugger and wider signal-mask/fork scopes are separate.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
