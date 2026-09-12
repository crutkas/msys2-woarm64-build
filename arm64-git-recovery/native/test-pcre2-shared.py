"""Exercise the exact installed PCRE2 DLLs through their public interpreter/JIT APIs."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess

from sources import ContractError, digest


def test(stage, output, pwsh, process_gate):
    stage, output = Path(stage).resolve(), Path(output).resolve()
    if os.name != "nt" or output.exists():
        raise ContractError("Requires Windows and a new evidence directory")
    output.mkdir(parents=True)
    subprocess.run([str(pwsh), "-NoProfile", "-File", str(process_gate),
                    "-ProcessId", str(os.getpid()), "-ReportPath", str(output / "process.json")], check=True)
    identity = json.loads((output / "process.json").read_text())
    if identity.get("Passed") is not True or identity.get("MeasuredCount") != 1:
        raise ContractError("Native test process gate did not pass")
    header = (stage / "include/pcre2.h").read_text()
    flags = {}
    for name in ("PCRE2_UTF", "PCRE2_UCP"):
        value = re.search(rf"(?m)^#define\s+{name}\s+(0x[0-9a-fA-F]+)", header)
        if not value:
            raise ContractError(f"Missing public option constant: {name}")
        flags[name] = int(value.group(1), 16)
    kernel = ctypes.WinDLL(str(Path(os.environ["SystemRoot"]) / "System32/kernel32.dll"), use_last_error=True)
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    records = []
    for width, encoding in ((8, "utf-8"), (16, "utf-16-le"), (32, "utf-32-le")):
        path = stage / f"bin/libpcre2-{width}.dll"
        initial_hash = digest(path)
        lib = ctypes.CDLL(str(path))
        module_name = ctypes.create_unicode_buffer(32768)
        if not kernel.GetModuleFileNameW(lib._handle, module_name, len(module_name)):
            raise ctypes.WinError(ctypes.get_last_error())
        if Path(module_name.value).resolve() != path:
            raise ContractError("A different PCRE2 DLL was loaded")
        compile_re = getattr(lib, f"pcre2_compile_{width}")
        compile_re.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p]
        compile_re.restype = ctypes.c_void_p
        jit_compile = getattr(lib, f"pcre2_jit_compile_{width}")
        jit_compile.argtypes, jit_compile.restype = [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int
        make_data = getattr(lib, f"pcre2_match_data_create_from_pattern_{width}")
        make_data.argtypes, make_data.restype = [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p
        free_data = getattr(lib, f"pcre2_match_data_free_{width}")
        free_data.argtypes, free_data.restype = [ctypes.c_void_p], None
        free_code = getattr(lib, f"pcre2_code_free_{width}")
        free_code.argtypes, free_code.restype = [ctypes.c_void_p], None
        ovector = getattr(lib, f"pcre2_get_ovector_pointer_{width}")
        ovector.argtypes, ovector.restype = [ctypes.c_void_p], ctypes.POINTER(ctypes.c_size_t)
        for jit in (False, True):
            pattern = ctypes.create_string_buffer(rb"\p{L}+".decode().encode(encoding))
            error, offset = ctypes.c_int(), ctypes.c_size_t()
            code = compile_re(pattern, len(pattern.raw[:-1]) // (width // 8),
                              flags["PCRE2_UTF"] | flags["PCRE2_UCP"],
                              ctypes.byref(error), ctypes.byref(offset), None)
            if not code:
                raise ContractError(f"Pattern compilation failed: {error.value} at {offset.value}")
            data = make_data(code, None)
            try:
                if not data:
                    raise ContractError("Match-data allocation failed")
                if jit and jit_compile(code, 1) != 0:
                    raise ContractError("PCRE2_JIT_COMPLETE compilation failed")
                match = getattr(lib, f"pcre2_{'jit_match' if jit else 'match'}_{width}")
                match.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                                  ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
                match.restype = ctypes.c_int
                results = []
                for text, expected, match_text in (
                    ("ARM64", 1, "ARM"), ("1234", -1, None),
                    ("\u03bb\u03b1\u03bc\u03b2\u03b4\u03b1", 1, "\u03bb\u03b1\u03bc\u03b2\u03b4\u03b1")
                ):
                    encoded = text.encode(encoding)
                    subject = ctypes.create_string_buffer(encoded)
                    result = match(code, subject, len(encoded) // (width // 8), 0, 0, data, None)
                    if result != expected:
                        raise ContractError(f"PCRE2-{width} {'JIT' if jit else 'interpreter'} returned {result}, expected {expected}")
                    span = None
                    if match_text is not None:
                        vector = ovector(data)
                        span = [vector[0], vector[1]]
                        if span != [0, len(match_text.encode(encoding)) // (width // 8)]:
                            raise ContractError("PCRE2 returned an incorrect match span")
                    results.append({"subject": text, "result": result, "span": span})
                records.append({"width": width, "jit": jit, "module_path": module_name.value,
                                "dll_sha256": initial_hash, "cases": results})
            finally:
                if data:
                    free_data(data)
                free_code(code)
        if digest(path) != initial_hash:
            raise ContractError("Shared library bytes changed during execution")
    report = {"schema": 1, "passed": True, "scope": "Exact installed DLL paths; public Unicode/UCP APIs, all widths, interpreter and direct JIT including no-match controls",
              "header_sha256": digest(stage / "include/pcre2.h"), "records": records,
              "process_gate_sha256": digest(process_gate)}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Installed shared PCRE2: 18 interpreter/JIT match cases passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "output", "pwsh", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    test(args.stage, args.output, args.pwsh, args.process_gate)


if __name__ == "__main__":
    main()
