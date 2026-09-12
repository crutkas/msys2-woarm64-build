#!/usr/bin/env python3
"""Execute real Windows ARM64 FP unwind boundaries for an MSYS assembler."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from coff_unwind import xdata


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixture-object", type=Path,
                        help="Also execute the same native harness against a Linux-assembled object")
    args = parser.parse_args()
    prefix = args.prefix.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    recipe = Path(__file__).resolve().parent
    compiler = prefix / "bin" / "gcc.exe"
    env = dict(os.environ, PATH=str(prefix / "bin") + os.pathsep + os.environ.get("PATH", ""))
    report = {"passed": False, "prefix": str(prefix), "inputs": {}, "runs": []}

    def run(name, command):
        process = subprocess.run([str(arg) for arg in command], cwd=out, env=env,
                                 capture_output=True, timeout=90)
        (out / f"{name}.stdout.bin").write_bytes(process.stdout)
        (out / f"{name}.stderr.bin").write_bytes(process.stderr)
        report["runs"].append({"name": name, "command": [str(arg) for arg in command],
                               "exit": process.returncode})
        process.check_returncode()
        return process

    try:
        if run("target", [compiler, "-dumpmachine"]).stdout.strip() != b"aarch64-pc-cygwin":
            raise ValueError("This harness requires the actual MSYS/Cygwin target")
        selected = run("select-as", [compiler, "-print-prog-name=as"])
        assembler = Path(selected.stdout.decode().strip()).resolve(strict=True)
        if not assembler.is_relative_to(prefix):
            raise ValueError("Compiler selected an assembler outside the new SDK")
        for name, path in (("compiler", compiler), ("assembler", assembler),
                           ("runtime", prefix / "bin" / "msys-2.0.dll")):
            report["inputs"][name] = identity(path)
        for name in ("libgcc.a", "libmsys-2.0.a", "crt0.o", "specs"):
            selected = run(f"select-{name}", [compiler, f"-print-file-name={name}"])
            path = Path(selected.stdout.decode().strip()).resolve(strict=True)
            if not path.is_relative_to(prefix):
                raise ValueError(f"Compiler-selected {name} escaped the SDK")
            report["inputs"][name] = identity(path)
        for name in ("fp-unwind-fixtures.s", "fp-unwind-harness.c"):
            shutil.copy2(recipe / "probes" / name, out / name)
            report["inputs"][name] = identity(out / name)
        shutil.copy2(prefix / "bin" / "msys-2.0.dll", out / "msys-2.0.dll")
        obj = out / "native-fixtures.o"
        run("assemble", [assembler, out / "fp-unwind-fixtures.s", "-o", obj])
        report["native_object"] = identity(obj)
        report["xdata"] = xdata(obj.read_bytes()).hex()
        objects = [("native", obj)]
        if args.fixture_object:
            cross_obj = args.fixture_object.resolve(strict=True)
            if xdata(cross_obj.read_bytes()) != xdata(obj.read_bytes()):
                raise ValueError("Linux/native target assemblers produced different FP unwind data")
            report["cross_object"] = identity(cross_obj)
            objects.append(("cross", cross_obj))
        for label, fixture in objects:
            executable = out / f"{label}-fp-unwind.exe"
            run(f"{label}-build", [compiler, "-O2", "-g", out / "fp-unwind-harness.c",
                                    fixture, "-o", executable])
            data = executable.read_bytes()
            pe = struct.unpack_from("<I", data, 0x3c)[0]
            if data[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", data, pe + 4)[0] != 0xaa64:
                raise ValueError("Unwind harness is not a raw ARM64 PE")
            executed = run(f"{label}-execute", [executable])
            text = executed.stdout.replace(b"\r\n", b"\n")
            if (text.count(b":ok ") != 18 or not text.endswith(b"native-fp-unwind-boundaries-ok\n")
                    or executed.stderr):
                raise ValueError("Native FP boundary matrix did not fully pass")
            report[f"{label}_executable"] = identity(executable)
        for before in report["inputs"].values():
            if identity(before["path"]) != before:
                raise ValueError(f"Input changed during FP proof: {before['path']}")
        report["passed"] = True
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Native MSYS FP unwind boundaries passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
