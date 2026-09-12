#!/usr/bin/env python3
"""Build serial MS ARM64 varargs probes; execution and raw capture use the PS1."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ABI_CASES = [
    "va-list-size", "mixed-scalar-pointer", "named-double", "fixed-double-hfa",
    "fixed-hfa-return", "variadic-double-return", "pair-register-stack-split",
    "large-hfa-indirect", "va-copy-list-tu-boundary", "twelve-stack-slots",
    "eight-named", "nine-named", "named-pair-split", "aligned16-register-gap",
    "aligned16-stack-gap", "int128-register-gap", "int128-stack-gap",
    "aligned16-named-control",
]
STDIO_CASES = [
    "printf", "vfprintf", "vprintf", "fprintf", "wprintf", "vfwprintf", "vwprintf",
    "fwprintf", "ucrt-vfprintf", "ucrt-vfwprintf", "vsnprintf", "vswprintf",
    "ucrt-vsprintf", "ucrt-vswprintf", "fixed-fputs", "fixed-fputws",
]
LABEL_BYTES = b"username=dummy-user\r\npassword=dummy-password\r\n"
MIXED_BYTES = b"17 1234567890123 4.5 safe"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("reference", "acceptance"), required=True)
    parser.add_argument("--suite", choices=("all", "abi", "stdio"), default="all")
    parser.add_argument("--gcc-ready", action="store_true",
                        help="Explicit authorization after the parent confirms GCC/CRT readiness")
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "acceptance" and not args.gcc_ready:
        parser.error("acceptance requires --gcc-ready after compiler AND CRT are ready")
    if args.mode == "reference" and args.gcc_ready:
        parser.error("--gcc-ready is only meaningful for acceptance")
    if args.mode == "reference" and args.suite == "stdio":
        parser.error("stdio is only available in acceptance mode")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_dir = Path(__file__).resolve().parent / "probes"
    sources = output / "sources"
    sources.mkdir()
    for path in sorted(source_dir.glob("ms-varargs*")):
        shutil.copyfile(path, sources / path.name)
    env = dict(os.environ, TMPDIR=str(output), TMP=str(output), TEMP=str(output))
    commands, programs, tools = [], [], {}
    clang = shutil.which(args.clang)
    if not clang:
        parser.error(f"Reference compiler missing: {args.clang}; no installation attempted")
    gcc = args.prefix.resolve() / "bin" / "aarch64-w64-mingw32-gcc"
    gxx = args.prefix.resolve() / "bin" / "aarch64-w64-mingw32-g++"
    linker = args.prefix.resolve() / "bin" / "aarch64-w64-mingw32-ld"
    objdump = args.prefix.resolve() / "bin" / "aarch64-w64-mingw32-objdump"
    libraries = args.prefix.resolve() / "aarch64-w64-mingw32" / "lib"
    tool_paths = [Path(clang), linker, objdump]
    if args.mode == "acceptance":
        tool_paths += [gcc, gxx]
    input_paths = tool_paths + [libraries / "libkernel32.a"]
    if args.mode == "acceptance":
        input_paths += [libraries / name for name in
                        ("crt2.o", "libmingw32.a", "libmingwex.a", "libucrt.a")]
        input_paths += list((args.prefix / "libexec" / "gcc" / "aarch64-w64-mingw32").glob("*/cc1*"))
        input_paths += list((args.prefix / "lib" / "gcc" / "aarch64-w64-mingw32").glob("*/libgcc.a"))
    for path in input_paths:
        tools[str(path)] = sha(path.resolve())

    def run(label, command, work=None):
        log = output / f"{label}.log"
        with log.open("wb") as stream:
            completed = subprocess.run(
                [str(item) for item in command], cwd=work or output, env=env,
                stdout=stream, stderr=subprocess.STDOUT, check=False,
            )
        commands.append({
            "label": label, "command": [str(item) for item in command],
            "returnCode": completed.returncode, "log": log.name,
            "workingDirectory": str(work or output),
        })
        if completed.returncode:
            print(f"FAILED {label}: {log}", file=sys.stderr)
        return completed.returncode == 0

    for index, path in enumerate(tool_paths):
        run(f"tool-{index}-version", [path, "--version"])

    compilers = ({} if args.suite == "stdio" else
                 {"clang-c": (clang, "c"), "clang-cpp": (clang, "c++")})
    if args.mode == "acceptance" and args.suite != "stdio":
        compilers.update({"gcc-c": (gcc, "c"), "gcc-cpp": (gxx, "c++")})
    objects = {}
    for name, (compiler, language) in compilers.items():
        for role in ("producer", "consumer"):
            work = output / "intermediates" / f"{name}-{role}"
            work.mkdir(parents=True)
            obj = work / f"{name}-{role}.o"
            command = [compiler]
            if name.startswith("clang"):
                command += ["--target=aarch64-pc-windows-msvc"]
            command += [
                "-x", language, "-std=c++17" if language == "c++" else "-std=c11",
                "-O2", "-Wall", "-Wextra", "-ffreestanding", "-save-temps=obj",
                "-c", sources / f"ms-varargs-{role}.c", "-o", obj,
            ]
            if run(f"{name}-{role}", command, work):
                objects[name, role] = obj
                run(f"{name}-{role}-disassembly", [objdump, "-dr", obj])
    entry = output / "entry.o"
    entry_ok = args.suite != "stdio" and run("entry", [
        clang, "--target=aarch64-pc-windows-msvc", "-std=c11", "-O2", "-Wall",
        "-Wextra", "-ffreestanding", "-save-temps=obj", "-c",
        sources / "ms-varargs-entry.c", "-o", entry,
    ])
    pairs = ([] if args.suite == "stdio" else
             [(p, c) for p in ("clang-c", "clang-cpp") for c in ("clang-c", "clang-cpp")])
    if args.mode == "acceptance" and args.suite != "stdio":
        pairs += [(p, c) for p in ("gcc-c", "gcc-cpp") for c in ("gcc-c", "gcc-cpp")]
        pairs += [("gcc-c", "clang-c"), ("clang-c", "gcc-c"),
                  ("gcc-cpp", "clang-cpp"), ("clang-cpp", "gcc-cpp")]
    for producer, consumer in pairs:
        name = f"abi-{producer}-to-{consumer}"
        exe = output / f"{name}.exe"
        if not entry_ok or (producer, "producer") not in objects or (consumer, "consumer") not in objects:
            continue
        if not run(f"{name}-link", [
            linker, "--entry=ms_varargs_entry", "--subsystem=console",
            "--dynamicbase", "--nxcompat", "--no-insert-timestamp", "-o", exe,
            entry, objects[producer, "producer"], objects[consumer, "consumer"],
            "-L", libraries, "-lkernel32",
        ]):
            continue
        run(f"{name}-imports", [objdump, "-p", exe])
        programs.append({
            "name": name, "file": exe.name, "sha256": sha(exe), "kind": "abi",
            "producer": producer, "consumer": consumer,
            "group": ("clang-reference" if producer.startswith("clang") and consumer.startswith("clang")
                      else "gcc-self" if producer.startswith("gcc") and consumer.startswith("gcc")
                      else "cross-compiler"),
            "cases": [{"id": i, "name": case,
                       "category": "alignment-reference" if i in (13, 14, 15, 16) else "control"}
                      for i, case in enumerate(ABI_CASES)],
        })
    if args.mode == "acceptance" and args.suite != "abi":
        for name, compiler, language in (("stdio-c", gcc, "c"), ("stdio-cpp", gxx, "c++")):
            exe = output / f"{name}.exe"
            if not run(name, [
                compiler, "-x", language, "-O2", "-Wall", "-Wextra",
                "-save-temps=obj", sources / "ms-varargs-stdio.c",
                "-Wl,--no-insert-timestamp", "-o", exe,
            ]):
                continue
            run(f"{name}-disassembly", [objdump, "-d", exe])
            run(f"{name}-imports", [objdump, "-p", exe])
            programs.append({
                "name": name, "file": exe.name, "sha256": sha(exe), "kind": "stdio",
                "group": "stdio",
                "cases": [{"id": i, "name": case, "category": "stdio",
                           "expectedHex": (MIXED_BYTES if 10 <= i <= 13 else LABEL_BYTES).hex()}
                          for i, case in enumerate(STDIO_CASES)],
            })
    expected_count = (2 if args.suite == "stdio" else 4 if args.mode == "reference"
                      else 12 if args.suite == "abi" else 14)
    changed_inputs = [path for path, digest in tools.items()
                      if not Path(path).exists() or sha(Path(path).resolve()) != digest]
    passed = (not changed_inputs and all(item["returnCode"] == 0 for item in commands)
              and len(programs) == expected_count)
    manifest = {
        "version": 1, "mode": args.mode, "suite": args.suite,
        "gccReadyAcknowledged": args.gcc_ready,
        "buildPassed": passed, "tools": tools, "commands": commands,
        "changedInputsDuringBuild": changed_inputs,
        "sources": {p.name: sha(p) for p in sorted(sources.iterdir())},
        "programs": programs,
        "scope": "Serial compiler invocations. ABI executables use real Kernel32 without CRT; stdio executables use the normal GCC/UCRT path. No patched or substitute printf.",
    }
    (output / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(programs)}/{expected_count} executables built; manifest: {output / 'build.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
