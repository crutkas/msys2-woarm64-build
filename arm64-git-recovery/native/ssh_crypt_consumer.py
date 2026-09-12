"""Observe a fresh installed libxcrypt API client and its exact private DLLs."""

import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import threading
import time

import native_job_runner
from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ssh_library_adapter", HERE / "build-msys-library.py")
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)
ADAPTER_PATH = Path(native_job_runner.__file__).resolve()
ADAPTER_SHA256 = digest(ADAPTER_PATH)
MARKER = b"native-crypt-consumer-passed"


def write_json(path, record):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


def arm64_pe(path):
    with Path(path).open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ContractError("Installed API payload is not a PE image")
        stream.seek(struct.unpack_from("<I", header, 60)[0])
        pe = stream.read(26)
    if (len(pe) != 26 or pe[:4] != b"PE\0\0" or
            struct.unpack_from("<H", pe, 4)[0] != 0xAA64 or struct.unpack_from("<H", pe, 24)[0] != 0x20B):
        raise ContractError("Installed API payload must be ordinary ARM64 PE32+")
    return {"path": str(Path(path).resolve()), "sha256": digest(path), "machine": "0xAA64", "pe32_plus": True}


def validate_loaded(record, pid, binary, expected_dlls):
    if (record.get("pid") != pid or record.get("process_machine") != 0 or
            record.get("native_machine") != 0xAA64 or
            Path(record.get("image", "")).resolve() != Path(binary).resolve() or
            not isinstance(record.get("creation_filetime"), int) or record["creation_filetime"] <= 0):
        raise ContractError("Installed API client is not the exact held native ARM64 process")
    loaded = {row["name"].lower(): row for row in record.get("dlls", [])}
    if len(loaded) != len(record.get("dlls", [])) or set(loaded) != set(expected_dlls):
        raise ContractError("Required native runtime/library modules are missing")
    for name, expected in expected_dlls.items():
        row = loaded[name]
        if Path(row["path"]).resolve() != Path(expected["path"]).resolve() or row["sha256"] != expected["sha256"]:
            raise ContractError("Installed API client loaded a library outside the exact private closure")


def inspect_process(pid, required_dlls):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.IsWow64Process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.USHORT),
                                     ctypes.POINTER(wintypes.USHORT)]
    kernel.IsWow64Process2.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    kernel.K32EnumProcessModulesEx.restype = wintypes.BOOL
    kernel.K32GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.K32GetModuleFileNameExW.restype = wintypes.DWORD
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        image = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(image))
        process_machine, native_machine = wintypes.USHORT(), wintypes.USHORT()
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if (not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)) or
                not kernel.IsWow64Process2(handle, ctypes.byref(process_machine), ctypes.byref(native_machine)) or
                not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                           ctypes.byref(kernel_time), ctypes.byref(user_time))):
            raise ctypes.WinError(ctypes.get_last_error())
        modules = (wintypes.HMODULE * 512)()
        needed = wintypes.DWORD()
        if (not kernel.K32EnumProcessModulesEx(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3)
                or needed.value > ctypes.sizeof(modules)):
            raise ContractError("Cannot enumerate the held native API process module set")
        dlls = []
        for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
            name = ctypes.create_unicode_buffer(32768)
            if not kernel.K32GetModuleFileNameExW(handle, module, name, len(name)):
                raise ctypes.WinError(ctypes.get_last_error())
            path = Path(name.value)
            if path.name.lower() in required_dlls:
                dlls.append({"name": path.name.lower(), "path": str(path.resolve()), "sha256": digest(path)})
        return {"pid": pid, "image": image.value, "process_machine": process_machine.value,
                "native_machine": native_machine.value,
                "creation_filetime": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                "dlls": dlls}
    finally:
        kernel.CloseHandle(handle)


def matching_relay(folder, identity, binary_sha256):
    matches = []
    for path in Path(folder).glob("*.json"):
        row = json.loads(path.read_text())
        if row.get("child_pid") == identity["pid"]:
            matches.append((path, row))
    if len(matches) != 1:
        raise ContractError("Expected exactly one current-generation installed API relay")
    path, row = matches[0]
    if (row.get("child_created") != identity["creation_filetime"] or row.get("sha256") != binary_sha256 or
            row.get("raw_exit") != 0 or row.get("portable_exit") != 0):
        raise ContractError("Installed API relay does not match the held process generation and real exit")
    return {"path": str(path.resolve()), "sha256": digest(path), "record": row}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "manifest", "prefix", "compiler-receipt", "native-job-prefix", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--stage-manifest-sha256", required=True)
    parser.add_argument("--compiler-receipt-sha256", required=True)
    parser.add_argument("--jobs", required=True, type=int, choices=(1,))
    args = parser.parse_args()
    library.validate_output(args.output, [args.stage, args.prefix, args.native_job_prefix])
    library.require_seal(args.manifest, args.stage_manifest_sha256, "Installed crypt stage")
    library.require_seal(args.compiler_receipt, args.compiler_receipt_sha256, "Installed crypt compiler")
    library.require_seal(ADAPTER_PATH, ADAPTER_SHA256, "Current parent observer adapter")
    verify_tree(args.stage, args.manifest)
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    stage = json.loads(args.manifest.read_text())
    if (stage.get("status") != "native-msys-library-built-checked-bootstrap-driver" or
            stage.get("package") != "libxcrypt" or stage.get("compiler_receipt_sha256") != args.compiler_receipt_sha256 or
            stage.get("approved_cc1_sha256") != library.APPROVED_CC1_SHA256 or
            Path(producer["prefix"]).resolve() != args.prefix.resolve() or stage.get("input_integrity_errors")):
        raise ContractError("Installed crypt stage and SDK do not identify the admitted new-guard build epoch")
    observer_manifest = native_job_runner.verify_driver(args.native_job_prefix)
    library.require_seal(observer_manifest, library.OBSERVER_MANIFEST_SHA256, "Exact current observer")
    library.validate_observer(json.loads(observer_manifest.read_text()))
    require_memory()
    args.output.mkdir(parents=True)
    for name in ("source", "home", "scratch", "cache", "compile-exits", "native-exits"):
        (args.output / name).mkdir()
    payload = args.output / "relocated"
    shutil.copytree(args.stage, payload)
    bin_dir = payload / "usr/bin"
    runtime = bin_dir / "msys-2.0.dll"
    if runtime.exists():
        raise ContractError("Installed library stage unexpectedly includes a runtime")
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", runtime)
    fixture = HERE / "fixtures/native-crypt-consumer.c"
    source = args.output / "source/native-crypt-consumer.c"
    shutil.copyfile(fixture, source)
    binary = bin_dir / "native-crypt-consumer.exe"
    expected_dlls = {name: {"path": str((bin_dir / name).resolve()), "sha256": digest(bin_dir / name)}
                     for name in ("msys-crypt-2.dll", "msys-2.0.dll")}
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update(PATH=os.pathsep.join((str(args.prefix.resolve() / "bin"), str(bin_dir.resolve()),
                                    str(Path(os.environ["SystemRoot"]) / "System32"))),
               HOME=str((args.output / "home").resolve()), USERPROFILE=str((args.output / "home").resolve()),
               TMP=str((args.output / "scratch").resolve()), TEMP=str((args.output / "scratch").resolve()),
               CCACHE_DISABLE="1", XDG_CACHE_HOME=str((args.output / "cache").resolve()),
               MAKEFLAGS="-j1", OMP_NUM_THREADS="1", WOARM64_NATIVE_ARG_CONVERSION="none",
               WOARM64_NATIVE_PYTHON=sys.executable, WOARM64_NATIVE_PYTHON_SHA256=digest(sys.executable),
               WOARM64_NATIVE_TEST_ROOT=str(args.output.resolve()),
               WOARM64_NATIVE_EXIT_DIR=str((args.output / "native-exits").resolve()))
    report = {"schema": 1, "passed": False, "package": "libxcrypt",
              "scope": "Fresh protected native installed API client; synthetic known answers only, no OS authentication",
              "stage_manifest_sha256": args.stage_manifest_sha256,
              "compiler_receipt_sha256": args.compiler_receipt_sha256,
              "fixture_sha256": digest(fixture), "driver_sha256": digest(Path(__file__)),
              "observer_adapter_sha256": ADAPTER_SHA256,
              "observer_manifest_sha256": library.OBSERVER_MANIFEST_SHA256,
              "jobs": 1, "nested_jobs": 1}
    stop = threading.Event()
    watch = {}
    thread = None

    def monitor():
        try:
            ready = args.output / "ready"
            deadline = time.monotonic() + 20
            pid = None
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    text = ready.read_text()
                    if text.endswith("\n") and text.strip().isdecimal() and int(text.strip()) > 0:
                        pid = int(text.strip())
                        break
                except OSError:
                    pass
                time.sleep(0.05)
            if pid is None:
                raise ContractError("Installed API client did not reach its native-PID handshake")
            identity = inspect_process(pid, expected_dlls)
            validate_loaded(identity, pid, binary, expected_dlls)
            watch["identity"] = identity
            write_json(args.output / "loaded-native-process.json", identity)
            (args.output / "continue").write_bytes(b"go\n")
        except Exception as error:
            watch["error"] = str(error)

    try:
        compiler = args.prefix.resolve() / "bin/gcc.exe"
        with native_job_runner.noninteractive_error_mode():
            support = support_identities(compiler, args.prefix, env)
        library.require_approved_cc1(support)
        report["support"] = support
        compile_command = [compiler, "-O2", "-g", "-fstack-protector-strong", "-Werror",
                           "-I" + str((payload / "usr/include").resolve()), source.resolve(),
                           (payload / "usr/lib/libcrypt.dll.a").resolve(), "-o", binary.resolve()]
        report["compile_command"] = list(map(str, compile_command))
        report["compile"] = native_job_runner.run_observed(
            compile_command, cwd=args.output.resolve(), env=env,
            log_path=(args.output / "compile.log").resolve(),
            result_path=(args.output / "compile.native-job.json").resolve(),
            relay_records=(args.output / "compile-exits").resolve(), timeout=180,
            driver_prefix=args.native_job_prefix)
        if not report["compile"]["passed"]:
            raise ContractError("Fresh installed API client compilation failed")
        report["pe"] = [arm64_pe(path) for path in (binary, runtime, bin_dir / "msys-crypt-2.dll")]
        before = inventory(payload)
        runtime_env = {**env, "PATH": os.pathsep.join((str(bin_dir.resolve()), str(args.prefix.resolve() / "bin"),
                                                      str(Path(os.environ["SystemRoot"]) / "System32")))}
        report["runtime_path"] = runtime_env["PATH"]
        command = [sys.executable, "-I", str((args.native_job_prefix / "native-target-exec.py").resolve()),
                   str(binary.resolve()), str(args.output.resolve())]
        report["run_command"] = command
        library.require_seal(ADAPTER_PATH, ADAPTER_SHA256, "Current parent observer adapter")
        thread = threading.Thread(target=monitor, name="ssh-crypt-module-proof", daemon=True)
        thread.start()
        report["process"] = native_job_runner.run_observed(
            command, cwd=args.output.resolve(), env=runtime_env,
            log_path=(args.output / "run.log").resolve(),
            result_path=(args.output / "run.native-job.json").resolve(),
            relay_records=(args.output / "native-exits").resolve(), timeout=45,
            driver_prefix=args.native_job_prefix)
        stop.set()
        thread.join(timeout=5)
        if thread.is_alive() or watch.get("error") or "identity" not in watch:
            raise ContractError("Installed native process/module proof failed: " + str(watch.get("error")))
        if not report["process"]["passed"] or MARKER not in (args.output / "run.log").read_bytes():
            raise ContractError("Installed native API behavior did not pass")
        report["native_process"] = watch["identity"]
        report["relay"] = matching_relay(args.output / "native-exits", watch["identity"], digest(binary))
        if inventory(payload) != before or digest(source) != digest(fixture):
            raise ContractError("Relocated API payload or fixture changed during execution")
        with native_job_runner.noninteractive_error_mode():
            verify_support(support, compiler, args.prefix, env)
        report.update(passed=True, consumer_sha256=digest(binary), exact_private_dlls=expected_dlls)
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=5)
        errors = []
        for label, root, manifest in (("stage", args.stage, args.manifest),
                                     ("SDK", args.prefix, args.compiler_receipt),
                                     ("observer", args.native_job_prefix, observer_manifest)):
            try:
                verify_tree(root, manifest)
            except Exception as error:
                errors.append(f"{label}: {error}")
        for path, sha in ((args.manifest, args.stage_manifest_sha256),
                          (args.compiler_receipt, args.compiler_receipt_sha256),
                          (observer_manifest, library.OBSERVER_MANIFEST_SHA256)):
            try:
                library.require_seal(path, sha, "Installed API input")
            except Exception as error:
                errors.append(str(error))
        report["input_integrity_errors"] = errors
        report["observer_adapter_sha256_at_exit"] = digest(ADAPTER_PATH)
        if errors:
            report["passed"] = False
        write_json(args.output / "result.json", report)
        if errors:
            raise ContractError("Installed API input integrity changed")
    print("Installed native libxcrypt API and exact private DLL/process-generation proof passed")


if __name__ == "__main__":
    main()
