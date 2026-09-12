#!/usr/bin/env python3
"""Relink frozen FIDO2 objects with the Windows import overlay, without execution."""

import argparse
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import runpy
import shutil

RECIPE = Path(__file__).resolve().parent
identity = runpy.run_path(str(RECIPE / "build-msys-windows-imports.py"))["identity"]


def split_command(text):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [W.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(W.LPWSTR)
    kernel.LocalFree.argtypes = [W.HLOCAL]
    kernel.LocalFree.restype = W.HLOCAL
    count = ctypes.c_int()
    argv = shell.CommandLineToArgvW(text, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(argv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure-log", required=True, type=Path)
    parser.add_argument("--failure-log-sha256", required=True)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--overlay-receipt-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows link replay is required")
    if identity(args.failure_log)["sha256"] != args.failure_log_sha256:
        parser.error("Frozen link command differs")
    overlay = args.overlay.resolve(strict=True)
    receipt = overlay / "result.json"
    if identity(receipt)["sha256"] != args.overlay_receipt_sha256:
        parser.error("Overlay receipt differs")
    manifest = json.loads(receipt.read_text(encoding="utf-8"))
    if manifest["status"] != "qualified-msys-windows-import-overlay-link-only":
        parser.error("Overlay link qualification is incomplete")
    prefix = Path(manifest["base_prefix"]).resolve(strict=True)
    build = args.build_root.resolve(strict=True)
    out = args.output.resolve()
    if any(out.is_relative_to(root) for root in (prefix, overlay, build.parent)):
        parser.error("Use a new output outside all frozen producer and consumer roots")
    lines = args.failure_log.read_text(encoding="utf-8").splitlines()
    commands = [line for line in lines if ' /C "cd . && ' in line and " -shared " in line]
    if len(commands) != 1:
        parser.error("Expected one frozen DLL link command")
    command = commands[0].split(' /C "cd . && ', 1)[1]
    if not command.endswith(' && cd ."'):
        parser.error("Unexpected shell command tail")
    original = split_command(command[:-len(' && cd ."')])
    if Path(original[0]).resolve() != prefix / "bin" / "gcc.exe":
        parser.error("Link command selects a different compiler")
    for name in ("wsock32", "bcrypt", "setupapi", "hid"):
        if original.count("-l" + name) != 1:
            parser.error("Frozen missing-library set differs")
    if original.count("-o") != 1 or len([s for s in original if s.startswith("-Wl,--out-implib,")]) != 1:
        parser.error("Expected exactly one DLL and import-library output")
    if any(s.startswith("@") for s in original):
        parser.error("Unbound response files are not allowed")

    def inventory(root):
        return {p.relative_to(root).as_posix(): identity(p)["sha256"]
                for p in root.rglob("*") if p.is_file()}

    baseline = inventory(build.parent)
    compiler = json.loads((overlay / "sources" / "baseline-copy-receipt.json").read_text(encoding="utf-8-sig"))
    dependencies = {}
    for index, value in enumerate(original):
        if index == 0 or value.endswith((".o", ".obj")):
            path = Path(value)
        elif value.startswith("-Wl,--version-script="):
            path = Path(value.split("=", 1)[1])
        else:
            continue
        path = path if path.is_absolute() else build / path
        dependencies[str(path.resolve(strict=True))] = identity(path)["sha256"]
    for value in original:
        if value.startswith("-L"):
            directory = Path(value[2:]).resolve(strict=True)
            for path in directory.glob("*.a"):
                dependencies[str(path)] = identity(path)["sha256"]
    for relative, expected in compiler["files"].items():
        path = prefix.joinpath(*relative.split("/"))
        if identity(path)["sha256"] != expected["sha256"]:
            raise ValueError(f"Compiler input drift: {relative}")
        dependencies[str(path)] = expected["sha256"]
    for relative, expected in manifest["payload"].items():
        path = overlay / "payload" / Path(relative)
        if identity(path)["sha256"] != expected["sha256"]:
            raise ValueError(f"Overlay drift: {relative}")
        dependencies[str(path)] = expected["sha256"]
    out.mkdir(parents=True, exist_ok=False)
    run = runpy.run_path(str(overlay / "sources" / "bounded_process.py"))["run"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    temp = out / "tmp"
    temp.mkdir()
    env.update(PATH=str(prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TMP=str(temp), TEMP=str(temp))
    command = original.copy()
    command[command.index("-o") + 1] = str(out / "msys-fido2-1.dll")
    for index, value in enumerate(command):
        if value.startswith("-Wl,--out-implib,"):
            command[index] = "-Wl,--out-implib," + str(out / "libfido2.dll.a")
    command.append("-L" + str(overlay / "payload" / "aarch64-pc-cygwin" / "lib"))
    report = {"status": "failed", "failure_log": identity(args.failure_log),
              "overlay_receipt": identity(receipt), "compiler_receipt": manifest["compiler_receipt"],
              "original_command": original, "command": command, "cwd": str(build),
              "frozen_inputs": dependencies, "runs": []}
    try:
        with (out / "link.log.bin").open("wb") as log:
            result = run(command, cwd=build, env=env, log=log, timeout=120)
        report["runs"].append(result)
        if not result["passed"]:
            raise ValueError(f"Actual FIDO DLL link or drain failed: {result}")
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        shell = shutil.which("pwsh")
        if not shell:
            raise ValueError("Existing PowerShell 7 is required for raw PE inspection")
        code = ("$ErrorActionPreference='Stop'; . " + quote(RECIPE / "Get-ToolchainPeIdentity.ps1")
                + "; Get-ToolchainPeIdentity -Path " + quote(out / "msys-fido2-1.dll")
                + " | ConvertTo-Json -Depth 8")
        with (out / "pe.json").open("wb") as log:
            result = run([shell, "-NoProfile", "-Command", code], cwd=out, env=env, log=log, timeout=30)
        report["runs"].append(result)
        if not result["passed"]:
            raise ValueError("Raw FIDO PE parser failed")
        pe = json.loads((out / "pe.json").read_text(encoding="utf-8-sig"))
        imports = {s["Dll"].lower(): s["Symbols"] for s in pe["Imports"]}
        if not pe["NativeArm64"] or not pe["DynamicBase"] or "msys-2.0.dll" not in imports:
            raise ValueError("FIDO DLL lost native MSYS identity")
        # MSYS random.c selects arc4random_buf, not its _WIN32 BCrypt branch.
        # The common link list still names bcrypt/wsock32 even without uses.
        for name in ("setupapi", "hid"):
            if not imports.get(name + ".dll"):
                raise ValueError(f"FIDO DLL lost its {name} dependency")
        if "arc4random_buf" not in imports["msys-2.0.dll"]:
            raise ValueError("The unchanged MSYS randomness backend was lost")
        if inventory(build.parent) != baseline:
            raise ValueError("Frozen FIDO cohort changed during link replay")
        if any(identity(path)["sha256"] != sha for path, sha in dependencies.items()):
            raise ValueError("Compiler, object or dependency bytes changed")
        report.update(status="actual-fido-dll-link-passed-not-executed",
                      dll=identity(out / "msys-fido2-1.dll"),
                      import_library=identity(out / "libfido2.dll.a"),
                      pe=pe, frozen_cohort_unchanged=True,
                      optional_unreferenced_link_libraries=[
                          name for name in ("bcrypt", "wsock32") if name + ".dll" not in imports],
                      scope="Only -L and own DLL/import-output paths changed; no source recompile, "
                            "FIDO execution, device/auth action, install or package admission")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen FIDO DLL link passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
