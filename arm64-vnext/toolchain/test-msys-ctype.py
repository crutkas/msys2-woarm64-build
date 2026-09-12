#!/usr/bin/env python3
"""Native MSYS hosted iostream/ctype consumer, with a missing-import control."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess

RECIPE = Path(__file__).resolve().parent
read_exports = runpy.run_path(str(RECIPE / "test-runtime-exports.py"))["exports"]


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-missing-import", action="store_true")
    args = parser.parse_args()
    prefix = args.prefix.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    compiler = prefix / "bin" / "g++.exe"
    env = dict(os.environ, PATH=str(prefix / "bin") + os.pathsep + os.environ.get("PATH", ""))
    result = {"passed": False, "expect_missing_import": args.expect_missing_import,
              "prefix": str(prefix), "inputs": {}, "runs": []}

    def run(name, command):
        completed = subprocess.run([str(item) for item in command], cwd=out, env=env,
                                   capture_output=True, timeout=60)
        (out / f"{name}.stdout.bin").write_bytes(completed.stdout)
        (out / f"{name}.stderr.bin").write_bytes(completed.stderr)
        result["runs"].append({"name": name, "command": [str(item) for item in command],
                               "exit_code": completed.returncode})
        return completed

    def selected(name, option):
        completed = run(f"select-{name}", [compiler, option])
        completed.check_returncode()
        path = Path(completed.stdout.decode("utf-8").strip()).resolve(strict=True)
        if not path.is_relative_to(prefix):
            raise ValueError(f"Compiler input escaped its prefix: {path}")
        result["inputs"][name] = identity(path)
        return path

    try:
        target = run("target", [compiler, "-dumpmachine"])
        target.check_returncode()
        if target.stdout.strip() != b"aarch64-pc-cygwin":
            raise ValueError("Expected a Cygwin/MSYS-target compiler, not MinGW")
        for name in ("libstdc++.a", "libsupc++.a", "libmsys-2.0.a", "crt0.o", "specs"):
            selected(name, f"-print-file-name={name}")
        selected("libgcc.a", "-print-libgcc-file-name")
        selected("cc1plus", "-print-prog-name=cc1plus")
        selected("assembler", "-print-prog-name=as")
        selected("linker", "-print-prog-name=ld")
        version = run("version", [compiler, "-dumpversion"])
        version.check_returncode()
        version = version.stdout.decode("ascii").strip()
        for name, relative in {
            "compiler": "bin/g++.exe", "runtime": "bin/msys-2.0.dll",
            "ctype-header": "aarch64-pc-cygwin/include/ctype.h",
            "iostream-header": f"aarch64-pc-cygwin/include/c++/{version}/iostream",
            "cxx-config": f"aarch64-pc-cygwin/include/c++/{version}/aarch64-pc-cygwin/bits/c++config.h",
        }.items():
            result["inputs"][name] = identity(prefix / relative)
        runtime = prefix / "bin" / "msys-2.0.dll"
        result["ctype_exports"] = sorted(name for name in read_exports(runtime) if "ctype" in name)
        imports = run("import-symbols", [prefix / "bin" / "nm.exe", "-g", "--defined-only",
                                        result["inputs"]["libmsys-2.0.a"]["path"]])
        imports.check_returncode()
        symbols = {line.split()[-1] for line in imports.stdout.decode("utf-8").splitlines()
                   if line.split()}
        result["has_ctype_import"] = "__imp__ctype_" in symbols
        source = out / "msys-ctype.cc"
        shutil.copy2(RECIPE / "probes" / source.name, source)
        result["source"] = identity(source)
        compiled = run("compile", [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                                   "-c", source, "-o", out / "consumer.o"])
        compiled.check_returncode()
        if struct.unpack_from("<H", (out / "consumer.o").read_bytes())[0] != 0xaa64:
            raise ValueError("Consumer object is not raw ARM64 COFF")
        result["object"] = identity(out / "consumer.o")
        linked = run("link", [compiler, out / "consumer.o", "-o", out / "consumer.exe"])
        if args.expect_missing_import:
            if (linked.returncode == 0 or b"__imp__ctype_" not in linked.stderr
                    or result["has_ctype_import"] or "_ctype_" in result["ctype_exports"]):
                raise ValueError("Missing runtime DATA import negative control did not reproduce")
            result["status"] = "missing-runtime-ctype-import-reproduced"
        else:
            linked.check_returncode()
            if not result["has_ctype_import"] or "_ctype_" not in result["ctype_exports"]:
                raise ValueError("Runtime DLL/import library do not expose the required ABI")
            shutil.copy2(runtime, out / runtime.name)
            executed = run("execute", [out / "consumer.exe"])
            executed.check_returncode()
            if (executed.stdout.replace(b"\r\n", b"\n") != b"native-msys-ctype-ok 73\n"
                    or executed.stderr):
                raise ValueError("Native iostream/ctype behavior differs from the contract")
            result["executable"] = identity(out / "consumer.exe")
            result["status"] = "native-hosted-msys-ctype-passed"
        for before in result["inputs"].values():
            if identity(before["path"]) != before:
                raise ValueError(f"Input changed during the consumer proof: {before['path']}")
        result["passed"] = True
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['status']}: {out / 'result.json'}")


if __name__ == "__main__":
    main()
