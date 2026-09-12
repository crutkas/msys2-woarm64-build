#!/usr/bin/env python3
"""Bind fresh native MSYS jump-buffer consumers to a sealed runtime cohort."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess


def identify(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--runtime-receipt", required=True, type=Path)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cross-executable", type=Path)
    args = parser.parse_args()
    prefix = args.prefix.resolve(strict=True)
    if identify(args.source)["sha256"] != args.source_sha256:
        parser.error("Runtime-owned regression source hash differs")
    if identify(args.runtime_receipt)["sha256"] != args.receipt_sha256:
        parser.error("Sealed runtime receipt hash differs")
    receipt = json.loads(args.runtime_receipt.read_text(encoding="utf-8-sig"))
    if receipt["status"] not in (
            "coherent-runtime-jump-buffer-abi-and-bounded-upstream-consumer-qualified",
            "coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified"):
        parser.error("Not a qualified jump-ABI runtime cohort")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    env = dict(os.environ, PATH=str(prefix / "bin") + os.pathsep + os.environ.get("PATH", ""))
    compiler = prefix / "bin" / "gcc.exe"
    result = {"passed": False, "prefix": str(prefix), "source": identify(args.source),
              "runtime_receipt": identify(args.runtime_receipt), "inputs": {}, "runs": []}

    def run(name, command, timeout=30):
        completed = subprocess.run([str(arg) for arg in command], cwd=out, env=env,
                                   capture_output=True, timeout=timeout)
        (out / f"{name}.stdout.bin").write_bytes(completed.stdout)
        (out / f"{name}.stderr.bin").write_bytes(completed.stderr)
        result["runs"].append({"name": name, "command": [str(arg) for arg in command],
                               "exit": completed.returncode})
        completed.check_returncode()
        return completed

    try:
        if run("target", [compiler, "-dumpmachine"]).stdout.strip() != b"aarch64-pc-cygwin":
            raise ValueError("Expected a real MSYS/Cygwin-target compiler")
        for name, relative, expected in [
                ("runtime", "bin/msys-2.0.dll", receipt["runtime"]["sha256"]),
                ("jmp-header", "aarch64-pc-cygwin/include/machine/setjmp.h", receipt["header"]["sha256"]),
                ("import-library", "aarch64-pc-cygwin/lib/libmsys-2.0.a", receipt["import_library"]["sha256"]),
                ("crt0", "aarch64-pc-cygwin/lib/crt0.o", receipt["startup"]["sha256"])]:
            actual = identify(prefix / relative)
            if actual["sha256"] != expected:
                raise ValueError(f"SDK input is not from the paired runtime: {name}")
            result["inputs"][name] = actual
        result["inputs"]["compiler"] = identify(compiler)
        for name in ("libgcc.a", "specs"):
            selected = run(f"select-{name}", [compiler, f"-print-file-name={name}"])
            path = Path(selected.stdout.decode().strip()).resolve(strict=True)
            if not path.is_relative_to(prefix):
                raise ValueError(f"Compiler-selected {name} escaped the SDK")
            result["inputs"][name] = identify(path)
        source = out / "sigjmp-mask.c"
        shutil.copy2(args.source, source)
        layout = out / "jump-layout.c"
        layout.write_text(
            "#include <setjmp.h>\n#include <windows.h>\n"
            "_Static_assert(sizeof(jmp_buf)==256,\"jmp_buf\");\n"
            "_Static_assert(sizeof(sigjmp_buf)==272,\"sigjmp_buf\");\n"
            "_Static_assert(_SAVEMASK*sizeof(long)==256,\"flag\");\n"
            "_Static_assert(_SIGMASK*sizeof(long)==264,\"mask\");\n"
            "int main(void){struct{WORD machine,reserved;DWORD attributes;} m={0};"
            "return !GetProcessInformation(GetCurrentProcess(),(PROCESS_INFORMATION_CLASS)9,"
            "&m,sizeof(m))||m.machine!=0xaa64;}\n", encoding="ascii")
        run("layout-build", [compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                             layout, "-o", out / "jump-layout.exe"])
        run("sigjmp-build", [compiler, "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                             source, "-o", out / "sigjmp-mask.exe"])
        shutil.copy2(prefix / "bin" / "msys-2.0.dll", out / "msys-2.0.dll")
        executables = [("layout", out / "jump-layout.exe"), ("sigjmp", out / "sigjmp-mask.exe")]
        if args.cross_executable:
            cross = out / "cross-sigjmp-mask.exe"
            shutil.copy2(args.cross_executable, cross)
            result["cross_input"] = identify(args.cross_executable)
            executables.append(("cross-sigjmp", cross))
        for name, executable in executables:
            data = executable.read_bytes()
            pe = struct.unpack_from("<I", data, 0x3c)[0]
            if data[pe:pe+4] != b"PE\0\0" or struct.unpack_from("<H", data, pe+4)[0] != 0xaa64:
                raise ValueError("Jump consumer is not native ARM64 PE")
            completed = run(f"{name}-execute", [executable], timeout=15)
            if completed.stderr:
                raise ValueError(f"Unexpected stderr from {name}")
            result[name] = identify(executable)
        for before in result["inputs"].values():
            if identify(before["path"]) != before:
                raise ValueError("SDK input changed during qualification")
        result["passed"] = True
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Fresh MSYS jump-buffer consumers passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
