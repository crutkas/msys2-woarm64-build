#!/usr/bin/env python3
"""Qualify a cc1plus-only guard successor with real C++ and retained MSYS gates."""

import argparse
import ast
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess

RECIPE = Path(__file__).resolve().parent
identity = runpy.run_path(str(RECIPE / "build-msys-windows-imports.py"))["identity"]
contained = runpy.run_path(str(RECIPE / "build-msys-windows-imports.py"))["contained"]
inspect_pe = runpy.run_path(str(RECIPE / "inspect-pe-pseudo-relocs.py"))["inspect"]
native_process = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-receipt", required=True, type=Path)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--cc1plus", required=True, type=Path)
    parser.add_argument("--prerequisite", required=True, type=Path)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--compile-sha256", required=True)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--error-policy", required=True, type=Path)
    parser.add_argument("--error-policy-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows qualification is required")
    for path, sha in ((args.base_receipt, args.base_sha256), (args.runner, args.runner_sha256),
                      (args.error_policy, args.error_policy_sha256),
                      (args.prerequisite / "input.json", args.input_sha256),
                      (args.prerequisite / "compile.json", args.compile_sha256)):
        if identity(path)["sha256"] != sha:
            parser.error(f"Input identity differs: {path}")
    base = json.loads(args.base_receipt.read_text(encoding="utf-8-sig"))
    prerequisite = json.loads((args.prerequisite / "input.json").read_text(encoding="utf-8-sig"))
    original_compile = json.loads((args.prerequisite / "compile.json").read_text(encoding="utf-8-sig"))
    if (base["status"] != "byte-identical-relocated-input-not-new-qualification"
            or base["source_status"] != "qualified-native-msys-stack-guard-c-compiler-delta"
            or base["source_target"]["Profile"] != "MSYS"
            or prerequisite["compiler_receipt_sha256"] != args.base_sha256):
        parser.error("Expected the immediate, qualified C-only predecessor")
    old = Path(base["prefix"]).resolve(strict=True)
    replacement = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1plus.exe"
    retained_c = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe"
    if (original_compile["cc1plus_sha256"] != base["files"][replacement]["sha256"]
            or original_compile["target_executed"] is not False
            or original_compile["process"]["exit"] != 0):
        parser.error("Prerequisite must bind the retained C++ frontend and a successful compile-only failure shape")
    if base["files"][retained_c]["sha256"] != "b8046275497c4e8f4d056530ef2e956d1b7672a0e5eb15ad56fde5bf44e76b0a":
        parser.error("The qualified C frontend is not retained")
    original_probe = args.prerequisite / "probe.c"
    if identity(original_probe)["sha256"] != prerequisite["source_sha256"]:
        parser.error("The exact protected C++ source changed")
    if args.output.resolve().is_relative_to(old) or args.output.resolve().is_relative_to(args.prerequisite.resolve()):
        parser.error("Never stage inside a frozen input")

    def verify_base():
        for relative, expected in base["files"].items():
            path = contained(old, relative)
            if identity(path)["sha256"] != expected["sha256"] or path.stat().st_size != expected["size"]:
                raise ValueError(f"Frozen base changed: {relative}")
        if {p.relative_to(old).as_posix() for p in old.rglob("*") if p.is_file()} != set(base["files"]):
            raise ValueError("Frozen base file set changed")

    verify_base()
    candidate = identity(args.cc1plus)
    if candidate["sha256"] == base["files"][replacement]["sha256"]:
        parser.error("Candidate is identical to the failing C++ frontend")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    tc = out / "tc"
    shutil.copytree(old, tc)
    shutil.copy2(args.cc1plus, tc / replacement)
    probes = out / "probes"
    probes.mkdir()
    temp = out / "tmp"
    temp.mkdir()
    shutil.copy2(args.base_receipt, out / "base-receipt.json")
    shutil.copy2(args.runner, out / "bounded_process.py")
    shutil.copy2(args.error_policy, out / "native_job_runner.py")
    run_bounded = runpy.run_path(str(out / "bounded_process.py"))["run"]
    # Execute only the reviewed context manager, not the helper's observer and
    # source-loader dependencies. Its exact original module is hash-bound above.
    tree = ast.parse(args.error_policy.read_text(encoding="utf-8"))
    policy_nodes = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "noninteractive_error_mode"]
    if len(policy_nodes) != 1:
        raise ValueError("Expected the existing process-local error-mode helper")
    context = {"contextmanager": contextmanager, "ctypes": ctypes, "os": os}
    exec(compile(ast.Module(body=policy_nodes, type_ignores=[]), str(args.error_policy), "exec"), context)
    error_mode = context["noninteractive_error_mode"]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetErrorMode.argtypes = []
    kernel.GetErrorMode.restype = ctypes.c_uint
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(tc / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TEMP=str(temp), TMP=str(temp))
    report = {
        "status": "failed", "base_receipt": identity(args.base_receipt),
        "prefix": str(tc), "candidate_cc1plus": candidate, "target": base["source_target"],
        "changed_files": [replacement], "retained_cc1_sha256": base["files"][retained_c]["sha256"],
        "prerequisite": {"input": identity(args.prerequisite / "input.json"),
                         "compile": identity(args.prerequisite / "compile.json"),
                         "source": identity(original_probe)},
        "error_policy": identity(args.error_policy), "runs": [],
    }

    def run(name, command, *, cwd=probes, expected=0, execute=False, timeout=180):
        log = out / (name + ".log.bin")
        observations = []
        previous_mode = kernel.GetErrorMode()
        with log.open("wb") as stream, error_mode():
            result = run_bounded(
                list(map(str, command)), cwd=cwd, env=env, log=stream, timeout=timeout,
                on_started=(lambda pid: observations.append(native_process(pid, Path(command[0]))))
                if execute else None)
        if kernel.GetErrorMode() != previous_mode:
            raise ValueError("Process-local error mode was not restored")
        report["runs"].append({
            "name": name, "command": list(map(str, command)), "cwd": str(cwd),
            "expected_exit": expected, "nonzero_failure_control": expected is None,
            "process": result, "native_observations": observations, "log": identity(log),
            "error_mode_previous": previous_mode, "error_mode_restored": True,
            "private_path": env["PATH"],
        })
        if result["timed_out"] or result["active_at_boundary"] or result["remaining_process_ids"]:
            raise ValueError(f"Timeout/undrained child: {name}")
        if expected is not None and result["exit"] != expected:
            raise ValueError(f"Unexpected exit from {name}: {result['exit']}")
        return result, log.read_bytes()

    def assert_output(name, command, expected_output, **kwargs):
        _, data = run(name, command, **kwargs)
        if data.replace(b"\r\n", b"\n") != expected_output:
            raise ValueError(f"Unexpected native output: {name}: {data!r}")

    def reject_instruction_relocs(path):
        record = inspect_pe(path)
        if any(entry["bits"] in (12, 21) for entry in record["entries"]):
            raise ValueError(f"Protected C++ still emits instruction pseudo-relocs: {path}")
        return record

    def pwsh():
        path = shutil.which("pwsh")
        if not path:
            raise ValueError("Existing PowerShell 7 is required")
        return path

    try:
        policy_control = (
            "import ctypes,sys; k=ctypes.WinDLL('kernel32'); k.GetErrorMode.restype=ctypes.c_uint; "
            "assert k.GetErrorMode() & 0x8003 == 0x8003; print('owned-error-policy-inherited'); sys.exit(37)")
        assert_output("error-policy-control", [os.sys.executable, "-c", policy_control],
                      b"owned-error-policy-inherited\n", expected=37)
        source = probes / "probe.c"
        shutil.copy2(original_probe, source)
        command = original_compile["command"].copy()
        if Path(command[0]).resolve() != old / "bin" / "g++.exe" or command[-2] != "-o":
            raise ValueError("Unexpected prerequisite compiler command")
        if len(command) != 10 or command[1:7] != [
                "-x", "c++", "-O2", "-g", "-Werror", "-fstack-protector-strong"]:
            raise ValueError("Unexpected prerequisite protection profile")
        original = command.copy()
        original[-3] = str(source)
        original[-1] = str(probes / "old-cpp.exe")
        run("old-cpp-link", original)
        old_relocs = inspect_pe(probes / "old-cpp.exe")
        guard_records = [entry for entry in old_relocs["entries"]
                         if entry["imported"] and entry["imported"]["symbol"] == "__stack_chk_guard"]
        if sorted(entry["bits"] for entry in guard_records) != [12] * 4 + [21] * 4 + [64]:
            raise ValueError("The exact previous C++ 21/12/64 failure shape did not reproduce")
        command[0] = str(tc / "bin" / "g++.exe")
        command[-3] = str(source)
        command[-1] = str(probes / "cpp-guard.exe")
        run("cpp-link", command)
        new_relocs = reject_instruction_relocs(probes / "cpp-guard.exe")
        if not any(entry["bits"] == 64 and entry["imported"]["symbol"] == "__stack_chk_guard"
                   for entry in new_relocs["entries"]):
            raise ValueError("The C++ guard must use a full-width reference cell")
        report["pseudo_relocations"] = {"old": old_relocs, "new": new_relocs}
        assert_output("cpp-native-guard", [probes / "cpp-guard.exe"],
                      b"native-msys-protected-far-guard-ok\n", execute=True, timeout=20)
        result, data = run("cpp-real-canary-failure", [probes / "cpp-guard.exe", "--corrupt"],
                           execute=True, expected=None, timeout=20)
        if (result["exit"] == 0 or b"corrupting-own-process-guard" not in data
                or b"stack smashing" not in data.lower()
                or b"ERROR-guard-corruption-not-detected" in data):
            raise ValueError("Real C++ canary failure was not preserved")
        run("cpp-all-protection-link", [
            tc / "bin" / "g++.exe", "-x", "c++", "-O3", "-g", "-Werror",
            "-fstack-protector-all", "-fdump-rtl-expand", source, "-o", probes / "cpp-all.exe"])
        report["all_protection_relocations"] = reject_instruction_relocs(probes / "cpp-all.exe")
        dumps = list(probes.glob("*.expand"))
        if len(dumps) != 1 or set(re.findall(
                r"\(const_int ([01]) \[[^\]]*\]\)\s*\]\s*UNSPEC_SALT_ADDR",
                dumps[0].read_text())) != {"0", "1"}:
            raise ValueError("The C++ SET/TEST salts were not both retained")
        report["cpp_salted_rtl"] = identity(dumps[0])
        assert_output("cpp-all-native-guard", [probes / "cpp-all.exe"],
                      b"native-msys-protected-far-guard-ok\n", execute=True, timeout=20)
        result, data = run("cpp-all-real-canary-failure", [probes / "cpp-all.exe", "--corrupt"],
                           execute=True, expected=None, timeout=20)
        if (result["exit"] == 0 or b"corrupting-own-process-guard" not in data
                or b"stack smashing" not in data.lower()
                or b"ERROR-guard-corruption-not-detected" in data):
            raise ValueError("All-protected C++ canary failure was not preserved")
        # The longstanding C/C++/DLL/thread/TLS/exception/filesystem matrix runs
        # as a single owned bounded process tree, with inherited modal policy.
        run("retained-msys-matrix", [
            pwsh(), "-NoProfile", "-File", RECIPE / "Test-NativeToolchain.ps1",
            "-Prefix", tc, "-OutputDirectory", out / "native-matrix", "-Profile", "MSYS"],
            timeout=300)
        matrix = json.loads((out / "native-matrix" / "result.json").read_text(encoding="utf-8-sig"))
        if not matrix["Passed"] or matrix["Profile"] != "MSYS" or len(matrix["Runs"]) != 7:
            raise ValueError("Existing native MSYS matrix is incomplete")
        report["retained_native_matrix"] = identity(out / "native-matrix" / "result.json")
        for filename in ("msys-runtime.cc", "msys-module.cc", "msys-native.c", "msys-ctype.cc"):
            shutil.copy2(RECIPE / "probes" / filename, probes)
        cxx = tc / "bin" / "g++.exe"
        cc = tc / "bin" / "gcc.exe"
        protected = ["-O2", "-fstack-protector-all"]
        run("protected-cpp-module", [cxx, *protected, "-shared", probes / "msys-module.cc",
                                    "-o", probes / "module.dll"])
        run("retained-c-loader", [cc, *protected, probes / "msys-native.c", "-o", probes / "loader.exe"])
        assert_output("protected-cpp-dll-execute", [probes / "loader.exe", probes / "module.dll"],
                      b"native-msys-c-ok long=8\n", execute=True, timeout=20)
        run("protected-cpp-thread-build", [cxx, "-std=c++17", *protected, "-pthread",
                                          probes / "msys-runtime.cc", "-o", probes / "threads.exe"])
        assert_output("protected-cpp-thread-execute", [probes / "threads.exe"],
                      b"native-msys-runtime-ok\n", execute=True, timeout=20)
        run("protected-cpp-ctype-build", [cxx, "-std=c++17", *protected, "-Wall", "-Wextra",
                                         probes / "msys-ctype.cc", "-o", probes / "ctype.exe"])
        assert_output("protected-cpp-ctype-execute", [probes / "ctype.exe"],
                      b"native-msys-ctype-ok 73\n", execute=True, timeout=20)
        report["protected_regression_tables"] = [
            reject_instruction_relocs(probes / name)
            for name in ("module.dll", "loader.exe", "threads.exe", "ctype.exe")]
        raw_pe_file = out / "protected-raw-pe.json"
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        images = [tc / replacement, probes / "cpp-guard.exe", probes / "module.dll",
                  probes / "loader.exe", probes / "threads.exe", probes / "ctype.exe"]
        code = ("$ErrorActionPreference='Stop'; . " + quote(RECIPE / "Get-ToolchainPeIdentity.ps1")
                + "; @(" + ",".join(quote(path) for path in images)
                + ") | ForEach-Object { Get-ToolchainPeIdentity -Path $_ } | ConvertTo-Json -Depth 9")
        _, data = run("protected-raw-pe", [pwsh(), "-NoProfile", "-Command", code])
        raw_pe_file.write_bytes(data)
        raw_images = json.loads(data.decode("utf-8-sig"))
        for index, image in enumerate(raw_images):
            dlls = {entry["Dll"].lower() for entry in image["Imports"]}
            if not image["NativeArm64"] or not image["DynamicBase"]:
                raise ValueError("Non-native or non-ASLR C++ output")
            if index == 0:
                if "msys-2.0.dll" in dlls or not any(name.startswith("api-ms-win-crt-") for name in dlls):
                    raise ValueError("Expected a Windows ARM64 UCRT-hosted C++ frontend")
            elif ("msys-2.0.dll" not in dlls or "msvcrt.dll" in dlls
                  or "ucrtbase.dll" in dlls or any(name.startswith("api-ms-win-crt-") for name in dlls)):
                raise ValueError("Expected MSYS-target protected regression images")
        report["raw_pe"] = identity(raw_pe_file)
        # Hold cc1plus on stdin long enough to query its real process machine.
        frontend = tc / replacement
        previous_mode = kernel.GetErrorMode()
        with error_mode():
            child = subprocess.Popen(
                [str(frontend), "-quiet", "-O2", "-o", str(out / "cc1plus-identity.s"), "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        if kernel.GetErrorMode() != previous_mode:
            raise ValueError("Error mode not restored after cc1plus launch")
        try:
            measured = native_process(child.pid, frontend)
            stdout, stderr = child.communicate(b"int native_cpp_identity() { return 73; }\n", timeout=30)
            (out / "cc1plus.stdout.bin").write_bytes(stdout)
            (out / "cc1plus.stderr.bin").write_bytes(stderr)
            if child.returncode or stdout or stderr:
                raise ValueError("Native C++ frontend identity compile failed")
            report["native_cc1plus"] = measured
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        files = {p.relative_to(tc).as_posix(): {"sha256": identity(p)["sha256"], "size": p.stat().st_size}
                 for p in tc.rglob("*") if p.is_file()}
        if set(files) != set(base["files"]):
            raise ValueError("Candidate inventory file set differs")
        changed = [name for name, value in files.items() if value != base["files"][name]]
        if changed != [replacement]:
            raise ValueError(f"Not a cc1plus-only delta: {changed}")
        verify_base()
        report.update(
            status="qualified-native-msys-protected-cpp-frontend-delta",
            files=files, base_unchanged=True, full_cpp_qualified=False,
            scope="cc1plus-only protected guard and scoped native C++ regressions, not whole SDK/library/package admission")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Protected C++ frontend delta qualified: {out / 'result.json'}")


if __name__ == "__main__":
    main()
