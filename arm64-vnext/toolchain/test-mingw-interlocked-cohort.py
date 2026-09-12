#!/usr/bin/env python3
"""Run frozen ordering controls and native value semantics for a private header cohort."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct

RECIPE = Path(__file__).resolve().parent


def local_path(value):
    if value.startswith("/mnt/") and len(value) > 7 and value[6] == "/":
        return Path(value[5].upper() + ":\\" + value[7:].replace("/", "\\"))
    return Path(value)


def ref(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cohort", "producer", "runner", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    args = parser.parse_args()
    if ref(args.runner)["sha256"] != args.runner_sha256:
        raise ValueError("Bounded runner identity differs")
    producer = json.loads((args.producer / "handoff.json").read_text())
    stage = json.loads((args.cohort / "stage.json").read_text())
    manifest = json.loads((args.cohort / "header-manifest.json").read_text())
    if stage["status"] != "private-mingw-interlocked-header-cohort-staged-not-qualified":
        raise ValueError("Unexpected header staging contract")
    inputs = [ref(args.runner), ref(args.cohort / "stage.json"),
              ref(args.cohort / "header-manifest.json"), ref(args.producer / "handoff.json")]
    for entry in producer["maintained_files"]:
        path = args.producer / entry["path"]
        if ref(path)["sha256"] != entry["sha256"]:
            raise ValueError(f"Frozen producer control changed: {entry['path']}")
        inputs.append(ref(path))
    compiler = Path(producer["codegen"]["compiler"])
    libgcc = Path(producer["codegen"]["libgcc_path"])
    if ref(libgcc)["sha256"] != producer["codegen"]["libgcc_sha256"]:
        raise ValueError("The frozen native compiler's libgcc changed")
    compiler_root = compiler.parent.parent
    tool_inputs = [p for p in (compiler_root / "bin").glob("*.exe")]
    tool_inputs += list((compiler_root / "libexec/gcc/aarch64-w64-mingw32/15.0.1").glob("*.exe"))
    inputs.extend(ref(p) for p in tool_inputs)
    inputs.append(ref(libgcc))
    old = local_path(manifest["baselineIncludeRoot"]).resolve(strict=True)
    new = (args.cohort / "include").resolve(strict=True)

    def verify_headers():
        for directory, files in ((old, manifest["baselineFiles"]), (new, manifest["files"])):
            actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
            if actual != set(files):
                raise ValueError("Header cohort file set changed")
            for relative, entry in files.items():
                if ref(directory / relative)["sha256"] != entry["sha256"]:
                    raise ValueError(f"Header changed: {relative}")

    verify_headers()
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    fixture = out / "interlocked-exchange-native.c"
    shutil.copy2(RECIPE / "probes/interlocked-exchange-native.c", fixture)
    inputs.append(ref(fixture))
    bounded = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    noninteractive = runpy.run_path(str(RECIPE / "run-msys-library-stage.py"))["noninteractive"]
    env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(compiler.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TMP=str(out), TEMP=str(out))
    report = {"schema": 1, "status": "failed", "inputs": inputs, "runs": [],
              "stageReceipt": ref(args.cohort / "stage.json"), "maxCompilerJobs": 1}

    def run(name, command, success=True, inspect=False):
        log = out / (name + ".log")
        machines = []
        with log.open("xb") as stream, noninteractive():
            result = bounded(list(map(str, command)), cwd=out, env=env, log=stream, timeout=90,
                             on_started=(lambda pid: machines.append(native(pid, Path(command[0])))) if inspect else None)
        report["runs"].append({"name": name, "command": list(map(str, command)),
                               "process": result, "native": machines, "log": ref(log)})
        if result["timed_out"] or result["active_at_boundary"] or ((result["exit"] == 0) != success):
            raise ValueError(f"Unexpected bounded result for {name}: {result}")
        return log.read_bytes()

    try:
        if run("compiler-target", [compiler, "-dumpmachine"], inspect=True).strip() != b"aarch64-w64-mingw32":
            raise ValueError("Compiler is not native MinGW target")
        tester = args.producer / ".github/scripts/test-mingw-w64-arm64-interlocked-exchange-ordering.ps1"
        pwsh = shutil.which("pwsh")
        if not pwsh:
            raise ValueError("Existing PowerShell 7 is required for frozen producer controls")
        negative = run("baseline-ordering-control", [pwsh, "-NoProfile", "-File", tester, "-Compiler", compiler,
                      "-IncludeRoot", old, "-OutputDirectory", out / "baseline"], success=False)
        if b"Missing release-capable helper" not in negative:
            raise ValueError("Negative control failed for an unexpected reason")
        run("patched-ordering-control", [pwsh, "-NoProfile", "-File", tester, "-Compiler", compiler,
            "-IncludeRoot", new, "-OutputDirectory", out / "patched"])
        old_asm = (out / "baseline/interlocked-exchange.s").read_text()
        new_asm = (out / "patched/interlocked-exchange.s").read_text()
        for symbol in ("__aarch64_swp4_sync", "__aarch64_swp8_sync"):
            if symbol not in old_asm:
                raise ValueError("Missing acquire-only baseline helper evidence")
        for symbol in ("__aarch64_swp4_acq_rel", "__aarch64_swp8_acq_rel"):
            if symbol not in new_asm:
                raise ValueError("Missing release-capable patched helper")
        if re.search(r"__aarch64_swp[48]_sync", new_asm):
            raise ValueError("Acquire-only exchange remains")
        for mode in ("-moutline-atomics", "-mno-outline-atomics"):
            name = "outlined" if mode == "-moutline-atomics" else "inline"
            exe = out / (name + ".exe")
            run(name + "-build", [compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", mode,
                                 "-I", new, fixture, "-o", exe], inspect=True)
            raw = exe.read_bytes()
            pe = struct.unpack_from("<I", raw, 0x3c)[0]
            if raw[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", raw, pe + 4)[0] != 0xaa64:
                raise ValueError("Probe is not raw ARM64 PE")
            output = run(name + "-native-exchange", [exe], inspect=True).replace(b"\r\n", b"\n")
            if output != b"native-arm64-interlocked-exchange-ok: 32/64/pointer previous and stored values\n":
                raise ValueError("Unexpected native exchange output")
        for entry in inputs:
            if ref(Path(entry["path"])) != entry:
                raise ValueError("Frozen input changed during qualification")
        verify_headers()
        report.update(status="native-mingw-interlocked-header-cohort-qualified",
                      nativeProcess=True, host="windows-arm64", target="aarch64-w64-mingw32",
                      baselineHelpers=["__aarch64_swp4_sync", "__aarch64_swp8_sync"],
                      patchedHelpers=["__aarch64_swp4_acq_rel", "__aarch64_swp8_acq_rel"],
                      nativeBehavior="32-bit, 64-bit and pointer old-value returns and new-value stores; outlined and inline ARM64 atomics",
                      limits="Code-generation/return-value proof, not a statistical memory-ordering proof, compiler rebuild, OpenSSL rebuild, or prior-package admission.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
