"""Build the exact missing native Bash NLS closure with explicit temporary scopes."""

import argparse
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from bash_chain_inputs import ROOT, PREPARED, fresh
from compiler_tools import support_identities, verify_msys_jmp_headers
from native_job_runner import noninteractive_error_mode, run_observed, verify_driver
from readline_chain_inputs import HERE, SEALS, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json

terminal = importlib.import_module("build-readline-chain")
BOOTSTRAP = ROOT / "host-bootstrap-02/msys64"
BOOTSTRAP_RECEIPT = ROOT / "host-bootstrap-02/host-generators-02.json"
BOOTSTRAP_RECEIPT_SHA = "618ed8549fed89da4d44d902c79f156c1091097860c90eb8e62806e32250e0c4"


def validate_generated_configure(text, label):
    unresolved = re.search(r"(?m)^[ \t]*gl_RELOCATABLE(?:[ \t]*\([^\n]*\))?[ \t]*$", text)
    if unresolved:
        line = text.count("\n", 0, unresolved.start()) + 1
        raise ContractError(f"Unexpanded gl_RELOCATABLE in {label}:{line}; require corrected source generation")


def environment(output, jobs):
    env = terminal.environment(output, jobs)
    env["PATH"] = os.pathsep.join(map(str, (terminal.COMPILER / "bin", BOOTSTRAP / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    env["WOARM64_NATIVE_TEST_ROOT"] = str(ROOT)
    return env


@contextmanager
def cpu_budget(count):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.GetProcessAffinityMask.argtypes = [W.HANDLE, C.POINTER(C.c_size_t), C.POINTER(C.c_size_t)]
    kernel.SetProcessAffinityMask.argtypes = [W.HANDLE, C.c_size_t]
    process = kernel.GetCurrentProcess()
    allowed, system = C.c_size_t(), C.c_size_t()
    if not kernel.GetProcessAffinityMask(process, C.byref(allowed), C.byref(system)):
        raise C.WinError(C.get_last_error())
    chosen = 0
    for bit in range(C.sizeof(C.c_size_t) * 8):
        if allowed.value & (1 << bit):
            chosen |= 1 << bit
            if chosen.bit_count() == count:
                break
    if not chosen or not kernel.SetProcessAffinityMask(process, chosen):
        raise C.WinError(C.get_last_error())
    record = {"original_mask": allowed.value, "inherited_mask": chosen,
              "maximum_cpus": chosen.bit_count(), "test_cases_or_required_threads_removed": False}
    try:
        yield record
    finally:
        if not kernel.SetProcessAffinityMask(process, allowed.value):
            raise C.WinError(C.get_last_error())
        record["original_affinity_restored"] = True


def required(profile):
    if profile.startswith("iconv"):
        return ["usr/bin/msys-iconv-2.dll", "usr/bin/msys-charset-1.dll", "usr/bin/iconv.exe",
                "usr/include/iconv.h", "usr/lib/libiconv.a", "usr/lib/libiconv.dll.a",
                "usr/lib/libcharset.a", "usr/lib/libcharset.dll.a"]
    return ["usr/bin/msys-intl-8.dll", "usr/bin/msys-asprintf-0.dll",
            "usr/bin/gettext.exe", "usr/bin/ngettext.exe", "usr/bin/envsubst.exe",
            "usr/include/libintl.h", "usr/lib/libintl.a", "usr/lib/libintl.dll.a",
            "usr/lib/libasprintf.a", "usr/lib/libasprintf.dll.a"]


def main(args):
    print(json.dumps({"pid": os.getpid(), "creation_filetime": terminal.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    package = "gettext-msys" if args.profile == "gettext-runtime" else "libiconv"
    source = ROOT / "sources" / package / "source"
    manifest = source.with_name("source.prepare.json")
    if (args.source_preparation is None) != (args.source_preparation_sha256 is None):
        raise ContractError("Explicit source preparation and its SHA must be supplied together")
    if args.source_preparation:
        manifest = args.source_preparation.resolve()
        source = manifest.parent / "source"
        if not source.is_relative_to(ROOT):
            raise ContractError("Regenerated source must remain under the owned Bash root")
        sealed(manifest, args.source_preparation_sha256)
        delta = json.loads(manifest.read_text()).get("source_generation_delta", {})
        if (package != "libiconv" or delta.get("base_manifest_sha256") != PREPARED[package][1]
                or delta.get("host_manifest_sha256") != BOOTSTRAP_RECEIPT_SHA
                or delta.get("libtool_manifest_sha256") != "f9880d4da0e9fd8b8fe7e041cf4950224ce38358342d7b2bee26823259f8f3d7"
                or delta.get("process", {}).get("passed") is not True
                or delta.get("unexpanded_relocatable_macro") is not False):
            raise ContractError("Source regeneration is not bound to this approved macro/tool closure")
    else:
        sealed(manifest, PREPARED[package][1])
    output = ROOT / args.output
    fresh(output)
    verify_tree(source, manifest)
    for script in ((source / "configure", source / "libcharset/configure") if package == "libiconv"
                   else (source / "gettext-runtime/configure", source / "gettext-runtime/intl/configure",
                         source / "gettext-runtime/libasprintf/configure")):
        validate_generated_configure(script.read_text(), str(script))
    sealed(terminal.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(terminal.COMPILER, terminal.COMPILER_RECEIPT)
    sealed(BOOTSTRAP_RECEIPT, BOOTSTRAP_RECEIPT_SHA)
    verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
    bootstrap = json.loads(BOOTSTRAP_RECEIPT.read_text())
    if (bootstrap["status"] != "owned-host-augmented-with-genuine-verified-automake"
            or bootstrap["signature_policy"] != "Required" or not bootstrap["verify"]["passed"]
            or not bootstrap["install"]["passed"] or len(bootstrap["files"]) != 19682
            or directory_names(BOOTSTRAP) != bootstrap["directories"]):
        raise ContractError("Bash bootstrap copy does not match its approved lineage")
    sealed(verify_driver(terminal.OBSERVER), SEALS["observer"])
    sealed(sys.executable, terminal.PYTHON_SHA)
    dependency = ROOT / args.dependency if args.dependency else ROOT / "no-dependency"
    if args.profile != "iconv-bridge":
        dependency_manifest = dependency.parent / "stage.inventory.json"
        verify_tree(dependency, dependency_manifest)
        if json.loads(dependency_manifest.read_text())["compiler_receipt_sha256"] != SEALS["compiler"]:
            raise ContractError("NLS dependency cohort differs")
    script = HERE / "build-bash-nls.sh"
    if b"\r" in script.read_bytes():
        raise ContractError("Bash NLS shell driver must use LF")
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    for path in (script, HERE / "build-bash-nls.py", HERE / "native-msys-test-dispatch.sh"):
        shutil.copyfile(path, output / "recipes" / path.name)
    command = [BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               args.profile, source, terminal.COMPILER, output, str(args.jobs), dependency]
    report = {"schema": 1, "status": "launched", "profile": args.profile, "jobs": args.jobs,
              "pid": os.getpid(), "creation_filetime": terminal.current_birth(),
              "command": list(map(str, command)), "source_manifest_sha256": digest(manifest),
              "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": terminal.RUNTIME_SHA,
              "bootstrap_receipt_sha256": digest(BOOTSTRAP_RECEIPT), "observer_manifest_sha256": SEALS["observer"],
              "minimum_free_gib": require_memory(), "full_cpp_qualified": False,
              "classification": "temporary-NLS-off-iconv-CLI-bridge-not-final" if args.profile == "iconv-bridge" else "full-selected-native-NLS-component",
              "scope": "MSYS LP64 native target; private x64 build/test drivers only; no full gettext-tools/distribution admission"}
    write_json(output / "launch.json", report)
    env = environment(output, args.jobs)
    env["WOARM64_BASH_NLS_LAUNCH_SHA256"] = digest(output / "launch.json")
    try:
        with cpu_budget(args.jobs) as budget, noninteractive_error_mode():
            report["cpu_budget"] = budget
            report["support"] = support_identities(terminal.COMPILER / "bin/gcc.exe", terminal.COMPILER, env)
            report["jump_headers"] = verify_msys_jmp_headers(terminal.COMPILER / "bin/gcc.exe", env)
            report["process"] = run_observed(command, cwd=ROOT, env=env, log_path=output / "observed.log",
                                             result_path=output / "native-job.json", relay_records=output / "native-exits",
                                             timeout=14400, driver_prefix=terminal.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native Bash NLS component build/check failed")
        files = inventory(output / "stage")
        missing = [name for name in required(args.profile) if name not in files]
        if missing:
            raise ContractError(f"Required NLS component payload missing: {missing}")
        nls = "#define ENABLE_NLS 1" in (output / "build/config.h").read_text()
        if nls != (args.profile != "iconv-bridge"):
            raise ContractError("Actual NLS configuration disagrees with the explicit profile")
        report.update(status="native-NLS-component-built-upstream-checked-consumer-proof-pending", nls_enabled=nls)
        write_json(output / "stage.inventory.json", {"schema": 1, "profile": args.profile,
                   "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": terminal.RUNTIME_SHA,
                   "nls_enabled": nls, "classification": report["classification"], "files": files})
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            verify_tree(source, manifest)
            verify_tree(terminal.COMPILER, terminal.COMPILER_RECEIPT)
            verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
        finally:
            write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "profile": args.profile,
                      "stage_manifest_sha256": digest(output / "stage.inventory.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("iconv-bridge", "gettext-runtime", "iconv-full"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--dependency")
    parser.add_argument("--jobs", type=int, required=True, choices=(1, 2))
    parser.add_argument("--source-preparation", type=Path)
    parser.add_argument("--source-preparation-sha256")
    main(parser.parse_args())
