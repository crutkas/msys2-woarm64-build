"""Capture a failing native compile from a build log without modifying its source or toolchain."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import shlex
import subprocess

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory


def windows_arguments(command):
    count = ctypes.c_int()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(argv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build-log", "cwd", "prefix", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--expected-error", required=True)
    parser.add_argument("--compile-commands", type=Path)
    parser.add_argument("--output-fragment")
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a fresh repro directory required")
    database_hash = None
    if args.compile_commands:
        database_hash = digest(args.compile_commands)
        entries = [entry for entry in json.loads(args.compile_commands.read_text())
                   if Path(entry["file"]).name == args.source_name
                   and (not args.output_fragment or args.output_fragment in entry.get("output", "").replace("\\", "/"))]
        if len(entries) != 1 or Path(entries[0]["directory"]).resolve() != args.cwd.resolve():
            raise ContractError("Expected one exact compiler database entry in the supplied build directory")
        original = entries[0].get("arguments") or windows_arguments(entries[0]["command"])
    else:
        lines = [line for line in args.build_log.read_text().splitlines()
                 if line.startswith("gcc -c ") and args.source_name in line]
        if len(lines) != 1:
            raise ContractError("Expected exactly one explicit failing C compiler command")
        original = shlex.split(lines[0])
    compiler = args.prefix / "bin/gcc.exe"
    if args.compile_commands and Path(original[0]).resolve() != compiler.resolve():
        raise ContractError("Compiler database entry belongs to a different producer")
    original[0] = str(compiler)
    source_indexes = [index for index, word in enumerate(original) if Path(word).name == args.source_name]
    if len(source_indexes) != 1 or original.count("-o") != 1 or original.count("-c") != 1:
        raise ContractError("Unexpected native compiler command shape")
    source_index, output_index = source_indexes[0], original.index("-o") + 1
    source = Path(original[source_index])
    if not source.is_absolute():
        source = args.cwd / source
        original[source_index] = str(source)
    source_hash, log_hash = digest(source), digest(args.build_log)
    compiler_files = inventory(args.prefix)
    args.output.mkdir(parents=True)
    (args.output / "temp").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env["PATH"] = str(args.prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["TMP"] = env["TEMP"] = str(args.output / "temp")
    support = support_identities(compiler, args.prefix, env)
    preprocessed = args.output / (Path(args.source_name).stem + ".i")
    preprocess = list(original)
    preprocess[preprocess.index("-c")] = "-E"
    preprocess[output_index] = str(preprocessed)
    standalone = list(original)
    standalone[source_index] = str(preprocessed)
    standalone[output_index] = str(args.output / "repro.o")
    standalone[1:1] = ["-x", "cpp-output"]
    report = {"schema": 1, "status": "failed", "original_command": original,
              "original_log_sha256": log_hash, "source": str(source), "source_sha256": source_hash,
              "compile_database_sha256": database_hash,
              "compiler_sha256": digest(compiler), "support": support, "commands": [],
              "optimization_or_feature_workaround": False}
    try:
        for name, command in (("preprocess", preprocess), ("standalone", standalone)):
            result = subprocess.run(command, cwd=args.cwd, env=env, capture_output=True, timeout=120)
            (args.output / f"{name}.stdout").write_bytes(result.stdout)
            (args.output / f"{name}.stderr").write_bytes(result.stderr)
            report["commands"].append({"name": name, "argv": command, "exit": result.returncode})
            if name == "preprocess" and result.returncode:
                raise ContractError("Preprocessing failed instead of creating a standalone repro")
            if name == "standalone" and (not result.returncode or args.expected_error.encode() not in result.stderr):
                raise ContractError("Standalone input did not reproduce the original compiler failure")
        report["preprocessed_sha256"] = digest(preprocessed)
        verify_support(support, compiler, args.prefix, env)
        if (inventory(args.prefix) != compiler_files or digest(source) != source_hash
                or digest(args.build_log) != log_hash or
                (args.compile_commands and digest(args.compile_commands) != database_hash)):
            raise ContractError("Original source, build log or toolchain changed")
        report["status"] = "standalone-native-compiler-failure-reproduced"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
