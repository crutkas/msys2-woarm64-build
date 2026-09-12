#!/usr/bin/env python3
"""Qualify ordinary public Windows Interlocked APIs using a new v12 Cygwin include root."""
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


def ref(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cohort", "public-probe", "runner", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--runner-sha256", required=True)
    args = parser.parse_args()
    stage = json.loads((args.cohort / "stage.json").read_text())
    if stage["status"] != "private-v12-cygwin-interlocked-headers-staged-not-qualified":
        raise ValueError("Wrong header cohort")
    sdk = Path(stage["sdk"]).resolve(strict=True)
    stage_helpers = runpy.run_path(str(RECIPE / "stage-cygwin-interlocked-headers.py"))
    verify_sdk = stage_helpers["verify_sdk_inventory"]
    provenance = stage["sdkProvenance"]
    verify_sdk(sdk, Path(provenance["path"]), provenance["sha256"])
    if ref(args.runner)["sha256"] != args.runner_sha256:
        raise ValueError("Bounded runner changed")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    old = sdk / "aarch64-pc-cygwin/include/w32api"
    new = (args.cohort / "include").resolve(strict=True)
    fixture = out / args.public_probe.name
    shutil.copy2(args.public_probe, fixture)
    behavior = out / "cygwin-public-interlocked-native.c"
    shutil.copy2(RECIPE / "probes/cygwin-public-interlocked-native.c", behavior)
    shutil.copy2(sdk / "bin/msys-2.0.dll", out / "msys-2.0.dll")
    cc = sdk / "bin/gcc.exe"
    selection = {"baseline": ["-I", old], "patched": ["-isysroot", args.cohort.resolve()]}
    runtime = ref(sdk / "bin/msys-2.0.dll")
    if runtime["sha256"] != "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c":
        raise ValueError("Use the explicitly selected unchanged combined runtime")
    bounded = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    quiet = runpy.run_path(str(RECIPE / "run-msys-library-stage.py"))["noninteractive"]
    env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(out) + os.pathsep + str(sdk / "bin") + os.pathsep
               + str(Path(os.environ["SystemRoot"]) / "System32"), TMP=str(out), TEMP=str(out))
    report = {"schema": 1, "status": "failed", "stage": ref(args.cohort / "stage.json"),
              "publicFixture": ref(args.public_probe), "runtime": runtime, "runs": []}

    def run(name, command, expected=0):
        log = out / (name + ".log")
        machines = []
        with log.open("xb") as stream, quiet():
            result = bounded(list(map(str, command)), cwd=out, env=env, log=stream, timeout=90,
                             on_started=lambda pid: machines.append(native(pid, Path(command[0]))))
        report["runs"].append({"name": name, "command": list(map(str, command)),
                               "result": result, "native": machines, "log": ref(log)})
        if result["exit"] != expected or result["timed_out"] or result["active_at_boundary"]:
            raise ValueError(f"Failed or undrained probe: {name}")
        return log.read_bytes()

    def ordering_control(path):
        text = path.read_text()
        for function, helper in (("exchange_public_32", "__aarch64_swp4_acq_rel"),
                                 ("exchange_public_64", "__aarch64_swp8_acq_rel"),
                                 ("exchange_public_pointer", "__aarch64_swp8_acq_rel")):
            start = text.index(function + ":")
            end = text.index(".seh_endproc", start)
            if helper not in text[start:end]:
                raise ValueError(f"Missing release-capable public exchange in {function}")
        if re.search(r"__aarch64_swp[48]_sync", text):
            raise ValueError("Acquire-only public exchange remains")

    try:
        if run("target", [cc, "-dumpmachine"]).strip() != b"aarch64-pc-cygwin":
            raise ValueError("Wrong compiler target")
        for name, include in (("baseline", old), ("patched", new)):
            run(name + "-public-codegen", [cc, "-O2", "-S", *selection[name], fixture, "-o", out / (name + ".s")])
        baseline = (out / "baseline.s").read_text()
        if not all(helper in baseline for helper in ("__aarch64_swp4_sync", "__aarch64_swp8_sync")):
            raise ValueError("Did not reproduce the measured acquire-only baseline")
        try:
            ordering_control(out / "baseline.s")
        except ValueError as error:
            if not str(error).startswith("Missing release-capable"):
                raise
            report["negativeControl"] = {"status": "baseline-rejected", "reason": str(error)}
        else:
            raise ValueError("Ordering control incorrectly accepted the baseline")
        ordering_control(out / "patched.s")
        report["positiveControl"] = "all-three-public-fallbacks-select-acq-rel"
        report["codegen"] = {name: ref(out / (name + ".s")) for name in ("baseline", "patched")}
        report["headerSelection"] = {
            "options": list(map(str, selection["patched"])),
            "reason": "The configured compiler searches its existing Cygwin C headers before -isysroot/include and its built-in -idirafter w32api after that. -I on a copied flat w32api root incorrectly shadows newlib with MinGW CRT headers."
        }
        run("patched-include-order", [cc, *selection["patched"], "-E", "-v", fixture, "-o", out / "include-order.i"])
        # This is an explicit preprocessing-only x64 branch control. It is not
        # execution of an x64 compiler or a claim about an x64 runtime binary.
        x64 = ["-U__aarch64__", "-U_ARM64_", "-D__x86_64__", "-D_AMD64_"]
        for name, include in (("baseline", old), ("patched", new)):
            run(name + "-x64-branch", [cc, "-E", "-P", *x64, *selection[name], fixture, "-o", out / (name + "-x64.i")])
        if re.sub(rb"\s+", b"", (out / "baseline-x64.i").read_bytes()) != re.sub(
                rb"\s+", b"", (out / "patched-x64.i").read_bytes()):
            raise ValueError("x64 selected preprocessor tokens changed")
        report["x64Control"] = "Identical public-probe preprocessing tokens for x64 branch; not x64 codegen/execution."
        for name, flag in (("outlined", "-moutline-atomics"), ("inline", "-mno-outline-atomics")):
            exe = out / (name + ".exe")
            run(name + "-build", [cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", flag,
                                 *selection["patched"], behavior, "-o", exe])
            raw = exe.read_bytes()
            offset = struct.unpack_from("<I", raw, 0x3c)[0]
            if raw[offset:offset + 4] != b"PE\0\0" or struct.unpack_from("<H", raw, offset + 4)[0] != 0xaa64:
                raise ValueError("Public exchange probe is not ARM64 PE")
            output = run(name + "-native", [exe]).replace(b"\r\n", b"\n")
            if output != b"native-msys-public-interlocked-ok: 32/64/pointer previous and stored values\n":
                raise ValueError("Unexpected native behavior output")
        verify_sdk(sdk, Path(provenance["path"]), provenance["sha256"])
        manifest = json.loads((args.cohort / "manifest.json").read_text())
        for name, entry in manifest["files"].items():
            if ref(new / name)["sha256"] != entry["sha256"]:
                raise ValueError("Private headers changed during qualification")
        if ref(args.public_probe) != report["publicFixture"]:
            raise ValueError("Parent's source fixture changed")
        report.update(status="v12-cygwin-public-interlocked-header-successor-qualified",
                      nativeProcess=True, target="aarch64-pc-cygwin", maxCompilerJobs=1,
                      scope="Public Windows API codegen and LP64 runtime return/store behavior only; no forced intrinsic macros in ARM controls, no root06/907/Perl rebuild or prior consumer admission.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
