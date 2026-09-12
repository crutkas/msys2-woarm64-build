"""Consume a qualified, immutable pipeline job observer for native target execution."""

from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

from sources import ContractError, digest, verify_tree

REJECTED_OBSERVERS = {
    "21c64abb6c1575d1dcf8626acc0aab054fa4bf2d3bef4cc486ce005cb9a32f1f":
        "PID-reuse classification retains a previous process generation",
}


@contextmanager
def noninteractive_error_mode():
    if os.name != "nt":
        yield
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetErrorMode.argtypes = []
    kernel.GetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    previous = kernel.GetErrorMode()
    # Process-local mode is inherited by children; raw loader/crash exits still fail the observer.
    kernel.SetErrorMode(previous | 0x8003)
    try:
        yield
    finally:
        kernel.SetErrorMode(previous)


def require_current_observer(sha256):
    if sha256 in REJECTED_OBSERVERS:
        raise ContractError(f"Retired native job observer: {REJECTED_OBSERVERS[sha256]}; require a new qualified handoff")


def verify_driver(prefix):
    prefix = Path(prefix)
    manifest = prefix.with_name(prefix.name + ".manifest.json")
    verify_tree(prefix, manifest)
    if json.loads(manifest.read_text()).get("status") != "byte-identical-native-test-driver":
        raise ContractError("Expected the qualified native child-exit observer copy")
    require_current_observer(digest(prefix / "native-job.py"))
    return manifest


def run_observed(command, *, cwd, env, log_path, result_path, relay_records, timeout, driver_prefix):
    driver_prefix = Path(driver_prefix)
    manifest = verify_driver(driver_prefix)
    result_path, log_path = Path(result_path), Path(log_path)
    if result_path.exists() or log_path.exists():
        raise ContractError("Native observation requires new result and log paths")
    argv = [sys.executable, "-I", str(driver_prefix / "native-job.py"),
            "--cwd", str(cwd), "--target-root", env["WOARM64_NATIVE_TEST_ROOT"],
            "--relay-records", str(relay_records), "--log", str(log_path),
            "--result", str(result_path), "--timeout", str(timeout),
            "--", *map(str, command)]
    with noninteractive_error_mode():
        result = subprocess.run(argv, env=env, capture_output=True, timeout=timeout + 60)
    result_path.with_suffix(".stdout").write_bytes(result.stdout)
    result_path.with_suffix(".stderr").write_bytes(result.stderr)
    if not result_path.is_file():
        raise ContractError("Native child-exit observer did not produce its required result")
    observation = json.loads(result_path.read_text())
    verify_tree(driver_prefix, manifest)
    return {
        "passed": observation["passed"] and result.returncode == 0,
        "pid": observation["parent_pid"], "exit": observation["parent_raw_exit"],
        "timed_out": observation["timed_out"],
        "created_processes": observation["created_processes"],
        "observed_processes": observation["observed_processes"],
        "windows_error_dialogs": "suppressed only in this launch and its inheriting children",
        "native_observation": {"path": str(result_path), "sha256": digest(result_path),
                               "driver_manifest_sha256": digest(manifest)},
    }
