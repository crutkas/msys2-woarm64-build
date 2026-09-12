#!/usr/bin/env python3
"""Verify the native MinGW C89 header fix without changing language flags."""

import argparse
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--stage-receipt", required=True, type=Path)
    parser.add_argument("--original-consumer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows qualification is required")
    prefix = args.prefix.resolve(strict=True)
    baseline = args.baseline.resolve(strict=True)
    stage = json.loads(args.stage_receipt.read_text(encoding="utf-8-sig"))
    if (Path(stage["Prefix"]).resolve() != prefix or
            Path(stage["BaselinePrefix"]).resolve() != baseline or
            stage["Status"] != "header-delta-candidate-not-qualified"):
        parser.error("Stage receipt does not bind this baseline and candidate")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    report = {
        "passed": False, "prefix": str(prefix), "baseline": str(baseline),
        "stage_receipt": {"path": str(args.stage_receipt), "sha256": digest(args.stage_receipt)},
        "scope": "C89 header compatibility, static fastfail linkage and unchanged C99 code generation; not full compiler or libtool package admission",
        "runs": [],
    }

    def run(name, executable, arguments, expected=0):
        env = dict(os.environ, PATH=str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", ""))
        command = [str(executable), *map(str, arguments)]
        result = subprocess.run(command, cwd=out, env=env, capture_output=True, timeout=60)
        (out / f"{name}.stdout.bin").write_bytes(result.stdout)
        (out / f"{name}.stderr.bin").write_bytes(result.stderr)
        report["runs"].append({"name": name, "command": command, "exit_code": result.returncode})
        if result.returncode != expected:
            raise ValueError(f"Unexpected exit from {name}: {result.returncode}; see retained streams")
        return result

    def verify_inputs():
        for entry in stage["BaselineFiles"]:
            relative = entry["Path"]
            if digest(baseline / relative) != entry["SHA256"]:
                raise ValueError(f"Frozen baseline changed: {relative}")
            expected = stage["HeaderSHA256"] if relative == stage["ChangedHeader"] else entry["SHA256"]
            if digest(prefix / relative) != expected:
                raise ValueError(f"Unexpected candidate input change: {relative}")

    try:
        verify_inputs()
        cc = prefix / "bin" / "gcc.exe"
        old_cc = baseline / "bin" / "gcc.exe"
        cxx = prefix / "bin" / "g++.exe"
        for label, root in (("old", baseline), ("new", prefix)):
            result = run(label + "-target", root / "bin" / "gcc.exe", ["-dumpmachine"])
            if result.stdout.strip() != b"aarch64-w64-mingw32":
                raise ValueError("Wrong toolchain target")
        original = out / "header.c"
        shutil.copy2(args.original_consumer, original)
        report["original_consumer_sha256"] = digest(original)
        negative = run("old-c89", old_cc, ["-std=c89", "-Werror", "-fsyntax-only", original], expected=1)
        if b"__MINGW_FASTFAIL_INLINE" not in negative.stderr or b"expected" not in negative.stderr:
            raise ValueError("The exact original static-inline failure was not reproduced")
        run("old-c99", old_cc, ["-std=c99", "-Werror", "-fsyntax-only", original])
        modes = [("c89", cc, "c"), ("c90", cc, "c"), ("gnu89", cc, "c"),
                 ("c99", cc, "c"), ("c11", cc, "c"), ("c17", cc, "c"), ("c23", cc, "c"),
                 ("c++98", cxx, "c++"), ("c++11", cxx, "c++"), ("c++17", cxx, "c++")]
        for mode, compiler, language in modes:
            run("header-" + mode.replace("+", "p"), compiler,
                [f"-std={mode}", "-Werror", "-fsyntax-only", "-x", language, original])

        # Keep two separate translation units: a header-local definition must
        # neither become a duplicate public symbol nor require an extern stub.
        unit = out / "fastfail-a.c"
        unit.write_text(
            '#include <stdio.h>\n'
            'int answer_a(void) { return 37; }\n'
            'void fastfail_a(unsigned int code) { __fastfail(code); }\n', encoding="ascii")
        second = out / "fastfail-b.c"
        second.write_text(unit.read_text().replace("answer_a", "answer_b").replace(
            "return 37", "return 36").replace("fastfail_a", "fastfail_b"), encoding="ascii")
        main_source = out / "main.c"
        main_source.write_text(
            '#include <windows.h>\n#include <stdio.h>\n'
            'int answer_a(void); int answer_b(void);\n'
            'int main(void) {\n'
            '  struct { WORD machine, reserved; DWORD attributes; } info = {0};\n'
            '  if (!GetProcessInformation(GetCurrentProcess(),(PROCESS_INFORMATION_CLASS)9,'
            '&info,sizeof(info)) || info.machine != 0xaa64) return 10;\n'
            '  if (answer_a()+answer_b()!=73) return 11;\n'
            '  puts("native-c89-header-ok"); return 0;\n}\n', encoding="ascii")
        for optimize in ("-O0", "-O2"):
            tag = optimize[1:]
            old_assembly = out / f"old-{tag}.s"
            new_assembly = out / f"new-{tag}.s"
            flags = ["-std=c99", optimize, "-S", unit]
            run(f"old-code-{tag}", old_cc, flags + ["-o", old_assembly])
            run(f"new-code-{tag}", cc, flags + ["-o", new_assembly])
            # GCC annotates inline assembly with the installed header path.
            # Normalize only that relocation; instructions/directives must match.
            relocated = new_assembly.read_bytes().replace(
                prefix.as_posix().encode(), baseline.as_posix().encode())
            if old_assembly.read_bytes() != relocated:
                raise ValueError("C99 fastfail code generation changed beyond keyword spelling")
            objects = []
            for name, source in (("a", unit), ("b", second)):
                obj = out / f"{name}-{tag}.o"
                run(f"object-{name}-{tag}", cc, ["-std=c89", "-Werror", optimize, "-c", source, "-o", obj])
                symbols = run(f"symbols-{name}-{tag}", prefix / "bin" / "nm.exe", [obj])
                if re.search(rb"\b[TUW]\s+_+fastfail\s*$", symbols.stdout, re.MULTILINE):
                    raise ValueError("Header emitted a public/undefined fastfail symbol")
                disassembly = run(f"code-{name}-{tag}", prefix / "bin" / "objdump.exe", ["-d", obj])
                if b"brk" not in disassembly.stdout or b"0xf003" not in disassembly.stdout:
                    raise ValueError("ARM64 Windows fastfail instruction was lost")
                objects.append(obj)
            exe = out / f"header-{tag}.exe"
            run(f"link-{tag}", cc, ["-std=c89", "-Werror", optimize, main_source, *objects, "-o", exe])
            execution = run(f"execute-{tag}", exe, [])
            if execution.stdout.replace(b"\r\n", b"\n") != b"native-c89-header-ok\n" or execution.stderr:
                raise ValueError("Unexpected native C89 runtime output")
        cpp_exe = out / "header-cpp98.exe"
        run("link-cpp98", cxx, ["-std=c++98", "-Werror", "-O2", main_source, unit, second, "-o", cpp_exe])
        cpp_run = run("execute-cpp98", cpp_exe, [])
        if cpp_run.stdout.replace(b"\r\n", b"\n") != b"native-c89-header-ok\n" or cpp_run.stderr:
            raise ValueError("Unexpected C++98 linkage/runtime output")
        # Query the compiler while it blocks on stdin, not a short-lived PID.
        env = dict(os.environ, PATH=str(prefix / "bin") + os.pathsep + os.environ.get("PATH", ""))
        process = subprocess.Popen([str(cc), "-std=c89", "-x", "c", "-fsyntax-only", "-"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.GetProcessInformation.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
            api.GetProcessInformation.restype = W.BOOL
            info = (ctypes.c_ubyte * 8)()
            if not api.GetProcessInformation(int(process._handle), 9, info, 8):
                raise ctypes.WinError(ctypes.get_last_error())
            if int.from_bytes(bytes(info[:2]), "little") != 0xaa64:
                raise ValueError("Compiler process is not native ARM64")
            report["compiler_process"] = {"pid": process.pid, "machine": "0xAA64", "path": str(cc)}
            stdout, stderr = process.communicate(b"int x;\n", timeout=30)
            if process.returncode != 0 or stderr or stdout:
                raise ValueError("Held native compiler control failed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        verify_inputs()
        report["header"] = {"path": str(prefix / stage["ChangedHeader"]),
                            "sha256": digest(prefix / stage["ChangedHeader"])}
        report["language_modes"] = [mode for mode, _, _ in modes]
        report["c99_assembly_unchanged_except_header_location"] = True
        report["passed"] = True
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Native MinGW C89 header delta passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
