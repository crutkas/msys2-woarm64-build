#!/usr/bin/env python3
"""Qualify public ARM64 Cygwin InterlockedExchange codegen and runtime behavior."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct

RECIPE = Path(__file__).resolve().parent
COMMON = runpy.run_path(str(RECIPE / "cygwin-w32api-common.py"))


def require_disjoint(path, protected):
    path = Path(path).resolve()
    for item in protected:
        item = Path(item).resolve(strict=True)
        if path == item or path.is_relative_to(item) or item.is_relative_to(path):
            raise ValueError(f"Output path overlaps protected input: {item}")


@contextmanager
def environment(values):
    previous = dict(os.environ)
    allowed = {
        name: value
        for name, value in previous.items()
        if name.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE")
    }
    os.environ.clear()
    os.environ.update(allowed)
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cohort", "observer", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--observer-sha256", required=True)
    args = parser.parse_args()
    stage_path = args.cohort / "stage.json"
    stage = json.loads(stage_path.read_text(encoding="utf-8-sig"))
    if stage["status"] != "private-v12-cygwin-interlocked-headers-staged-not-qualified":
        raise ValueError("Wrong header cohort")
    if COMMON["sha"](args.observer) != args.observer_sha256:
        raise ValueError("Generation-bound native observer changed")
    observer = runpy.run_path(str(args.observer))["run"]
    lock = COMMON["load_lock"]()
    public_probe = RECIPE / lock["public_probe"]["file"]
    sdk = Path(stage["sdk"]).resolve(strict=True)
    COMMON["verify_sdk_inventory"](lock, sdk, Path(stage["sdkProvenance"]["path"]))
    new = args.cohort.resolve(strict=True)
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Use a fresh qualification path")
    require_disjoint(out, (sdk, new, args.observer, RECIPE))
    out.mkdir(parents=True)
    fixture = out / public_probe.name
    behavior = out / "cygwin-public-interlocked-native.c"
    shutil.copy2(public_probe, fixture)
    shutil.copy2(RECIPE / "cygwin-public-interlocked-native.c", behavior)
    runtime_copy = out / "msys-2.0.dll"
    shutil.copy2(sdk / "bin/msys-2.0.dll", runtime_copy)
    old = sdk / "aarch64-pc-cygwin/include/w32api"
    cc = sdk / "bin/gcc.exe"
    selection = {"baseline": ["-I", old], "patched": ["-isysroot", new]}
    report = {
        "schema": 1,
        "status": "failed",
        "output": str(out),
        "cohortRoot": str(args.cohort.resolve(strict=True)),
        "stage": COMMON["ref"](stage_path),
        "publicFixture": COMMON["ref"](fixture),
        "publicFixtureSource": COMMON["ref"](public_probe),
        "observer": COMMON["ref"](args.observer),
        "runtimeSource": COMMON["ref"](sdk / "bin/msys-2.0.dll"),
        "runtimeExecuted": COMMON["ref"](runtime_copy),
        "recipeInputs": {
            "test": COMMON["ref"](__file__),
            "common": COMMON["ref"](RECIPE / "cygwin-w32api-common.py"),
            "nativeFixture": COMMON["ref"](RECIPE / "cygwin-public-interlocked-native.c"),
            "publicFixture": COMMON["ref"](public_probe),
            "sourceLock": COMMON["ref"](RECIPE / "cygwin-w32api-source-lock.json"),
        },
        "runs": [],
        "childEnvironment": [
            "COMSPEC",
            "LANG",
            "LC_ALL",
            "PATH",
            "PATHEXT",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "WINDIR",
        ],
    }
    if (
        report["runtimeSource"]["sha256"] != lock["sdk_contract"]["runtime_sha256"]
        or report["runtimeExecuted"]["sha256"] != lock["sdk_contract"]["runtime_sha256"]
    ):
        raise ValueError("Use the selected unchanged runtime907")
    env = {
        "PATH": str(out) + os.pathsep + str(sdk / "bin") + os.pathsep
        + str(Path(os.environ["SystemRoot"]) / "System32"),
        "TMP": str(out),
        "TEMP": str(out),
        "LC_ALL": "C",
        "LANG": "C",
    }

    def run(name, command, target_root, timeout=90):
        run_root = out / "runs" / name
        relay = run_root / "relay-inputs"
        relay.mkdir(parents=True)
        log = run_root / "process.log"
        with environment(env):
            result = observer(
                list(map(str, command)),
                out,
                Path(target_root),
                relay,
                log,
                timeout,
            )
        report["runs"].append(
            {
                "name": name,
                "command": list(map(str, command)),
                "result": result,
                "log": COMMON["ref"](log),
            }
        )
        if not result["passed"]:
            raise ValueError(f"Failed or incompletely observed probe: {name}")
        if (
            result["created_processes"] != result["observed_processes"]
            or len(result["native_target_exits"]) != result["created_processes"]
        ):
            raise ValueError(f"Probe escaped its pinned native target root: {name}")
        return log.read_bytes()

    def require_header_trace(data, expected):
        trace = data.decode("utf-8", errors="replace").replace("/", "\\").casefold()
        for path in expected:
            if str(Path(path).resolve()).casefold() not in trace:
                raise ValueError(f"Header trace did not select {path}")

    def ordering_control(path):
        text = path.read_text(encoding="utf-8", errors="replace")
        for function, helper in (
            ("exchange_public_32", "__aarch64_swp4_acq_rel"),
            ("exchange_public_64", "__aarch64_swp8_acq_rel"),
            ("exchange_public_pointer", "__aarch64_swp8_acq_rel"),
        ):
            start = text.index(function + ":")
            end = text.index(".seh_endproc", start)
            if helper not in text[start:end]:
                raise ValueError(f"Missing release-capable public exchange in {function}")
        if re.search(r"__aarch64_swp[48]_sync", text):
            raise ValueError("Acquire-only public exchange remains")

    def baseline_control(path):
        text = path.read_text(encoding="utf-8", errors="replace")
        for function, helper in (
            ("exchange_public_32", "__aarch64_swp4_sync"),
            ("exchange_public_64", "__aarch64_swp8_sync"),
            ("exchange_public_pointer", "__aarch64_swp8_sync"),
        ):
            start = text.index(function + ":")
            end = text.index(".seh_endproc", start)
            body = text[start:end]
            if helper not in body or "_acq_rel" in body:
                raise ValueError(f"Baseline ordering differs in {function}")

    def inline_ordering_control(path):
        text = path.read_text(encoding="utf-8", errors="replace")
        for function in (
            "exchange_public_32",
            "exchange_public_64",
            "exchange_public_pointer",
        ):
            start = text.index(function + ":")
            end = text.index(".seh_endproc", start)
            body = text[start:end]
            if "ldaxr" not in body or "stlxr" not in body:
                raise ValueError(f"Missing inline acquire-release exchange in {function}")
            if re.search(r"\b(?:ldxr|stxr)\b", body):
                raise ValueError(f"Relaxed inline exchange remains in {function}")

    try:
        if run("target", [cc, "-dumpmachine"], sdk).strip() != b"aarch64-pc-cygwin":
            raise ValueError("Wrong compiler target")
        for name in ("baseline", "patched"):
            run(
                name + "-public-codegen",
                [cc, "-O2", "-S", *selection[name], fixture, "-o", out / (name + ".s")],
                sdk,
            )
        baseline_control(out / "baseline.s")
        try:
            ordering_control(out / "baseline.s")
        except ValueError as error:
            if not str(error).startswith("Missing release-capable"):
                raise
            report["negativeControl"] = {
                "status": "baseline-rejected",
                "reason": str(error),
            }
        else:
            raise ValueError("Ordering control incorrectly accepted the baseline")
        ordering_control(out / "patched.s")
        report["positiveControl"] = "all-three-public-fallbacks-select-acq-rel"
        report["codegen"] = {
            name: COMMON["ref"](out / (name + ".s"))
            for name in ("baseline", "patched")
        }
        mode_codegen = {}
        for name, flag in (
            ("outlined", "-moutline-atomics"),
            ("inline", "-mno-outline-atomics"),
        ):
            assembly = out / ("patched-" + name + ".s")
            run(
                "patched-" + name + "-ordering",
                [cc, "-O2", "-S", flag, *selection["patched"], fixture, "-o", assembly],
                sdk,
            )
            if name == "outlined":
                ordering_control(assembly)
            else:
                inline_ordering_control(assembly)
            mode_codegen[name] = COMMON["ref"](assembly)
        report["codegen"]["patchedModes"] = mode_codegen
        for name, root in (("baseline", old), ("patched", new / "include")):
            trace = run(
                name + "-header-trace",
                [cc, "-H", "-E", *selection[name], fixture, "-o", out / (name + "-trace.i")],
                sdk,
            )
            require_header_trace(
                trace,
                (root / "windows.h", root / "psdk_inc/intrin-impl.h"),
            )
        x64 = ["-U__aarch64__", "-U_ARM64_", "-D__x86_64__", "-D_AMD64_"]
        for name in ("baseline", "patched"):
            run(
                name + "-x64-branch",
                [cc, "-E", "-P", *x64, *selection[name], fixture, "-o", out / (name + "-x64.i")],
                sdk,
            )
        baseline_x64 = re.sub(rb"\s+", b"", (out / "baseline-x64.i").read_bytes())
        patched_x64 = re.sub(rb"\s+", b"", (out / "patched-x64.i").read_bytes())
        if baseline_x64 != patched_x64:
            raise ValueError("x64 selected preprocessor tokens changed")
        report["x64Control"] = (
            "Identical public-probe preprocessing tokens for the x64 branch; "
            "not an x64 execution claim."
        )
        pe = {}
        for name, flag in (("outlined", "-moutline-atomics"), ("inline", "-mno-outline-atomics")):
            exe = out / (name + ".exe")
            run(
                name + "-build",
                [
                    cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", flag,
                    *selection["patched"], behavior, "-o", exe,
                ],
                sdk,
            )
            raw = exe.read_bytes()
            offset = struct.unpack_from("<I", raw, 0x3C)[0]
            machine = struct.unpack_from("<H", raw, offset + 4)[0]
            if raw[offset:offset + 4] != b"PE\0\0" or machine != 0xAA64:
                raise ValueError("Public exchange probe is not ARM64 PE")
            output = run(name + "-native", [exe], out, timeout=30).replace(b"\r\n", b"\n")
            expected = b"native-msys-public-interlocked-ok: 32/64/pointer previous and stored values\n"
            if output != expected:
                raise ValueError(f"Unexpected native behavior output: {name}")
            native_records = report["runs"][-1]["result"]["native_target_exits"]
            matching = [
                record for record in native_records
                if Path(record["executable"]).resolve() == exe.resolve()
            ]
            if len(matching) != 1 or matching[0]["raw_exit"] != 0:
                raise ValueError(f"Native executable identity/exit not observed: {name}")
            pe[name] = {"image": COMMON["ref"](exe), "machine": "0xAA64"}
            if COMMON["ref"](runtime_copy) != report["runtimeExecuted"]:
                raise ValueError("Executed runtime changed")
        (out / "pe-identities.json").write_text(
            json.dumps(pe, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        COMMON["verify_sdk_inventory"](lock, sdk, Path(stage["sdkProvenance"]["path"]))
        manifest = json.loads((args.cohort / "manifest.json").read_text(encoding="utf-8-sig"))
        if COMMON["inventory"](args.cohort / "include") != manifest["files"]:
            raise ValueError("Private header cohort changed during qualification")
        if COMMON["ref"](public_probe) != report["publicFixtureSource"]:
            raise ValueError("Public source fixture changed")
        if COMMON["sha"](fixture) != lock["public_probe"]["sha256"]:
            raise ValueError("Copied public source fixture changed")
        if COMMON["ref"](runtime_copy) != report["runtimeExecuted"]:
            raise ValueError("Executed runtime changed after qualification")
        report.update(
            status="v12-cygwin-public-interlocked-header-successor-qualified",
            target="aarch64-pc-cygwin",
            maxCompilerJobs=1,
            headerSelection={
                "options": list(map(str, selection["patched"])),
                "reason": (
                    "The configured compiler searches its existing Cygwin C headers before "
                    "-isysroot/include and its built-in w32api after it."
                ),
            },
            peIdentities=COMMON["ref"](out / "pe-identities.json"),
            scope=(
                "Ordinary public Windows API codegen and LP64 32/64/pointer return/store "
                "behavior; no forced ARM intrinsic macros and no runtime/compiler rebuild."
            ),
        )
    finally:
        (out / "result.json").write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(out / "result.json")


if __name__ == "__main__":
    main()
