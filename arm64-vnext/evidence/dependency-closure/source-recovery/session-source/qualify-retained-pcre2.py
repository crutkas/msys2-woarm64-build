import argparse
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path


spec = importlib.util.spec_from_file_location("native_nls", Path(__file__).with_name("qualify-official-nls.py"))
nls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    if args.result.exists():
        raise ValueError("Evidence must be new")
    report = {"status": "incomplete", "prefix": str(args.prefix), "runs": [],
              "scope": "Fresh retained63ca DLL API/JIT/Unicode qualification; not a source rebuild or inherited10.48-3 proof"}
    loaded = []
    try:
        for width in (8, 16, 32):
            path = args.prefix / "bin" / f"libpcre2-{width}.dll"
            lib = c.CDLL(str(path))
            loaded.append(lib)

            def bind(name, returns, params):
                function = getattr(lib, name + "_" + str(width))
                function.restype = returns
                function.argtypes = params
                return function

            config = bind("pcre2_config", c.c_int, [c.c_uint32, c.c_void_p])
            compile_pattern = bind("pcre2_compile", c.c_void_p,
                                   [c.c_void_p, c.c_size_t, c.c_uint32, c.POINTER(c.c_int),
                                    c.POINTER(c.c_size_t), c.c_void_p])
            match_data_create = bind("pcre2_match_data_create_from_pattern", c.c_void_p, [c.c_void_p, c.c_void_p])
            match_data_free = bind("pcre2_match_data_free", None, [c.c_void_p])
            code_free = bind("pcre2_code_free", None, [c.c_void_p])
            jit_compile = bind("pcre2_jit_compile", c.c_int, [c.c_void_p, c.c_uint32])
            match_params = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_size_t, c.c_uint32, c.c_void_p, c.c_void_p]
            match = bind("pcre2_match", c.c_int, match_params)
            jit_match = bind("pcre2_jit_match", c.c_int, match_params)
            ovector = bind("pcre2_get_ovector_pointer", c.POINTER(c.c_size_t), [c.c_void_p])
            options = {}
            for name, key in (("jit", 1), ("unicode", 9), ("compiled_widths", 14)):
                value = c.c_uint32()
                rc = config(key, c.byref(value))
                if rc != 0:
                    raise RuntimeError(f"Config {name}/{width} returned {rc}")
                options[name] = value.value
            if options["jit"] != 1 or options["unicode"] != 1:
                raise RuntimeError("Retained PCRE2 lacks required JIT/Unicode")
            codec = {8: "utf-8", 16: "utf-16-le", 32: "utf-32-le"}[width]

            def buffer(text):
                raw = text.encode(codec)
                return c.create_string_buffer(raw), len(raw) // (width // 8)

            for name, pattern, subject, expected_end in (
                ("unicode-properties", r"^\p{L}+$", "caf\u00e9", 5 if width == 8 else 4),
                ("lookahead", "a(?=b)", "ab", 1),
            ):
                pattern_buffer, pattern_length = buffer(pattern)
                subject_buffer, subject_length = buffer(subject)
                error, offset = c.c_int(), c.c_size_t()
                code = compile_pattern(pattern_buffer, pattern_length, 0x00080000 | 0x00020000,
                                       c.byref(error), c.byref(offset), None)
                if not code:
                    raise RuntimeError(f"Compile {width}/{name}: error {error.value} at {offset.value}")
                data = match_data_create(code, None)
                if not data:
                    code_free(code)
                    raise RuntimeError("Match-data allocation failed")
                try:
                    rc = jit_compile(code, 1)
                    if rc != 0:
                        raise RuntimeError(f"JIT compile returned {rc}")
                    for engine, function in (("interpreter", match), ("direct-jit", jit_match)):
                        match_options = 0x00002000 if engine == "interpreter" else 0
                        result = function(code, subject_buffer, subject_length, 0, match_options, data, None)
                        offsets = [ovector(data)[0], ovector(data)[1]] if result >= 0 else None
                        record = {"width": width, "case": name, "engine": engine, "return": result,
                                  "offsets": offsets, "expected": [0, expected_end],
                                  "passed": result == 1 and offsets == [0, expected_end]}
                        report["runs"].append(record)
                        if not record["passed"]:
                            raise RuntimeError(f"Actual PCRE2 match failed: {record}")
                    invalid, invalid_length = buffer("123")
                    result = jit_match(code, invalid, invalid_length, 0, 0, data, None)
                    report["runs"].append({"width": width, "case": name + "-nonmatch", "return": result,
                                           "expected": -1, "passed": result == -1})
                    if result != -1:
                        raise RuntimeError("Expected PCRE2_ERROR_NOMATCH")
                finally:
                    match_data_free(data)
                    code_free(code)
            bad, bad_length = buffer("(")
            error, offset = c.c_int(), c.c_size_t()
            code = compile_pattern(bad, bad_length, 0, c.byref(error), c.byref(offset), None)
            report["runs"].append({"width": width, "case": "invalid-pattern", "null_code": not bool(code),
                                   "error": error.value, "error_offset": offset.value,
                                   "passed": not code and error.value > 0})
            if code:
                code_free(code)
                raise RuntimeError("Invalid pattern compiled unexpectedly")
            report.setdefault("libraries", []).append({"path": str(path), "sha256": nls.digest(path), "features": options})

        class Regex(c.Structure):
            _fields_ = [("code", c.c_void_p), ("match_data", c.c_void_p), ("endp", c.c_char_p),
                        ("nsub", c.c_size_t), ("erroffset", c.c_size_t), ("flags", c.c_int)]
        class Match(c.Structure):
            _fields_ = [("start", c.c_int), ("end", c.c_int)]
        posix = c.CDLL(str(args.prefix / "bin/libpcre2-posix.dll"))
        posix.pcre2_regcomp.argtypes = [c.POINTER(Regex), c.c_char_p, c.c_int]
        posix.pcre2_regexec.argtypes = [c.POINTER(Regex), c.c_char_p, c.c_size_t, c.POINTER(Match), c.c_int]
        posix.pcre2_regfree.argtypes = [c.POINTER(Regex)]
        expression = Regex()
        rc = posix.pcre2_regcomp(c.byref(expression), b"^(native)-([0-9]+)$", 0)
        if rc != 0:
            raise RuntimeError(f"PCRE2 POSIX compilation returned {rc}")
        try:
            matches = (Match * 3)()
            rc = posix.pcre2_regexec(c.byref(expression), b"native-123", 3, matches, 0)
            offsets = [[item.start, item.end] for item in matches]
            no_match = posix.pcre2_regexec(c.byref(expression), b"wrong", 0, None, 0)
            passed = rc == 0 and offsets == [[0, 10], [0, 6], [7, 10]] and no_match == 17
            report["posix"] = {"return": rc, "offsets": offsets, "no_match": no_match, "expected_nonmatch": 17,
                               "structure_size": c.sizeof(Regex), "passed": passed}
            if not passed:
                raise RuntimeError("PCRE2 POSIX match result differs")
        finally:
            posix.pcre2_regfree(c.byref(expression))
        report["modules"] = nls.modules(os.getpid())
        for name in ("libpcre2-8.dll", "libpcre2-16.dll", "libpcre2-32.dll", "libpcre2-posix.dll"):
            found = [item for item in report["modules"] if item["name"].lower() == name]
            if len(found) != 1 or Path(found[0]["path"]).resolve() != (args.prefix / "bin" / name).resolve():
                raise RuntimeError("Wrong live PCRE2 DLL origin")
        if any(item["name"].lower().startswith("msys-") for item in report["modules"]):
            raise RuntimeError("Unexpected MSYS runtime in MinGW PCRE2")
        report["status"] = "fresh-retained-PCRE2-API-JIT-Unicode-POSIX-passed"
    finally:
        args.result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["runs"]),
                      "passed": sum(item["passed"] for item in report["runs"]), "posix": report.get("posix")}))


if __name__ == "__main__":
    main()
