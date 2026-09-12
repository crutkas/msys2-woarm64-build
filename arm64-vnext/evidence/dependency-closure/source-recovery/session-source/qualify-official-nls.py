import argparse
import ctypes as c
from ctypes import wintypes as w
import gettext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def modules(pid):
    class Module(c.Structure):
        _fields_ = [("size", w.DWORD), ("id", w.DWORD), ("pid", w.DWORD),
                    ("global_count", w.DWORD), ("process_count", w.DWORD),
                    ("base", c.c_void_p), ("base_size", w.DWORD), ("handle", w.HMODULE),
                    ("name", w.WCHAR * 256), ("path", w.WCHAR * 260)]
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Module32FirstW.argtypes = [w.HANDLE, c.POINTER(Module)]
    kernel.Module32NextW.argtypes = [w.HANDLE, c.POINTER(Module)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if handle == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    result = []
    entry = Module()
    entry.size = c.sizeof(entry)
    try:
        found = kernel.Module32FirstW(handle, c.byref(entry))
        if not found and c.get_last_error() != 18:
            raise c.WinError(c.get_last_error())
        while found:
            result.append({"name": entry.name, "path": entry.path, "sha256": digest(entry.path)})
            found = kernel.Module32NextW(handle, c.byref(entry))
        if c.get_last_error() != 18:
            raise c.WinError(c.get_last_error())
    finally:
        kernel.CloseHandle(handle)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    prefix = args.root / "mingwarm64"
    if args.result.exists():
        raise ValueError("Evidence output must be new")
    report = {"status": "incomplete", "root": str(args.root), "scope": "MinGW/UCRT C runtime only, no MSYS load",
              "locale_environment": {name: os.environ.get(name) for name in ("LANGUAGE", "LC_ALL", "LANG")},
              "runs": [], "api": {}}
    env = {
        "SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
        "PATH": str(prefix / "bin") + ";" + os.environ["SystemRoot"] + r"\System32",
        "PATHEXT": ".COM;.EXE;.BAT;.CMD", "HOME": str(args.result.parent / "home"),
        "USERPROFILE": str(args.result.parent / "home"), "TEMP": str(args.result.parent / "tmp"),
        "TMP": str(args.result.parent / "tmp"), "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(args.result.parent / "empty.gitconfig"),
        "GIT_TERMINAL_PROMPT": "0", "GIT_EXEC_PATH": str(prefix / "libexec/git-core"),
        "LANGUAGE": "fr", "LC_ALL": "fr_FR.UTF-8", "LANG": "fr_FR.UTF-8",
    }
    for directory in ("home", "tmp"):
        (args.result.parent / directory).mkdir(exist_ok=True)
    (args.result.parent / "empty.gitconfig").touch(exist_ok=True)
    report["child_environment"] = env

    def run(name, executable, arguments, expected_exit, expected_bytes=None, input_bytes=None):
        command = [str(executable), *arguments]
        result = subprocess.run(command, env=env, cwd=args.root, input=input_bytes,
                                capture_output=True, timeout=30)
        stdout = args.result.with_name(args.result.stem + "-" + name + ".stdout")
        stderr = args.result.with_name(args.result.stem + "-" + name + ".stderr")
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        record = {"name": name, "command": command, "raw_exit": result.returncode,
                  "expected_exit": expected_exit, "stdout": str(stdout), "stderr": str(stderr),
                  "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
                  "exit_matches": result.returncode == expected_exit,
                  "output_matches": None if expected_bytes is None else result.stdout == expected_bytes}
        report["runs"].append(record)
        return result

    try:
        mo = prefix / "share/locale/fr/LC_MESSAGES/gettext-runtime.mo"
        with mo.open("rb") as stream:
            oracle = gettext.GNUTranslations(stream)
        report["catalog"] = {"path": str(mo), "sha256": digest(mo)}
        expected = oracle.gettext("too many arguments")
        default = run("cli-default-french", prefix / "bin/gettext.exe",
                      ["-d", "gettext-runtime", "-s", "too many arguments"], 0,
                      expected.encode() + b"\n")
        lib = c.CDLL(str(prefix / "bin/libintl-8.dll"))
        for name, params in (
            ("libintl_setlocale", [c.c_int, c.c_char_p]),
            ("libintl_bindtextdomain", [c.c_char_p, c.c_char_p]),
            ("libintl_bind_textdomain_codeset", [c.c_char_p, c.c_char_p]),
            ("libintl_dgettext", [c.c_char_p, c.c_char_p]),
        ):
            function = getattr(lib, name)
            function.argtypes = params
            function.restype = c.c_char_p
        locale = lib.libintl_setlocale(0, b"")
        if locale is None:
            raise RuntimeError("Requested locale was rejected")
        api = report["api"]
        api["locale"] = locale.decode()
        api["unbound_gettext_directory"] = lib.libintl_bindtextdomain(b"gettext-runtime", None).decode()
        api["unbound_libidn2_directory"] = lib.libintl_bindtextdomain(b"libidn2", None).decode()
        api["unbound_messages_directory"] = lib.libintl_bindtextdomain(b"messages", None).decode()
        api["unbound_translation"] = lib.libintl_dgettext(b"gettext-runtime", b"too many arguments").decode()
        binding = lib.libintl_bindtextdomain(b"gettext-runtime", str(prefix / "share/locale").encode())
        codec = lib.libintl_bind_textdomain_codeset(b"gettext-runtime", b"UTF-8")
        api["application_binding"] = binding.decode() if binding else None
        api["application_codeset"] = codec.decode() if codec else None
        api["bound_translation"] = lib.libintl_dgettext(b"gettext-runtime", b"too many arguments").decode("utf-8")
        api["expected_translation"] = expected
        api["bound_lookup_passed"] = api["bound_translation"] == expected and expected != "too many arguments"
        api["libidn2_catalog_present"] = (prefix / "share/locale/fr/LC_MESSAGES/libidn2.mo").is_file()

        idn = c.CDLL(str(prefix / "bin/libidn2-0.dll"))
        idn.idn2_lookup_u8.argtypes = [c.c_char_p, c.POINTER(c.c_void_p), c.c_int]
        idn.idn2_lookup_u8.restype = c.c_int
        idn.idn2_free.argtypes = [c.c_void_p]
        idn.idn2_strerror.argtypes = [c.c_int]
        idn.idn2_strerror.restype = c.c_char_p
        output = c.c_void_p()
        rc = idn.idn2_lookup_u8("bücher.example".encode("utf-8"), c.byref(output), 0)
        converted = c.string_at(output).decode("ascii") if output.value else None
        if output.value:
            idn.idn2_free(output)
        api["idn2"] = {"return": rc, "actual": converted, "expected": "xn--bcher-kva.example",
                       "passed": rc == 0 and converted == "xn--bcher-kva.example",
                       "localized_error_minus_200": idn.idn2_strerror(-200).decode("utf-8")}

        self_modules = modules(os.getpid())
        api["live_modules"] = self_modules
        if any(item["name"].lower().startswith("msys-") for item in self_modules):
            raise RuntimeError("Unexpected MSYS runtime in MinGW C API qualification")
        for name in ("libintl-8.dll", "libiconv-2.dll", "libidn2-0.dll"):
            found = [item for item in self_modules if item["name"].lower() == name]
            if len(found) != 1 or Path(found[0]["path"]).resolve() != (prefix / "bin" / name).resolve():
                raise RuntimeError(f"Wrong live DLL origin: {name}")

        run("git-french-diagnostic", prefix / "bin/git.exe",
            ["-C", str(args.root / "intentionally-absent"), "status"], 128)
        run("git-version", prefix / "bin/git.exe", ["--version"], 0)
        report["default_lookup_passed"] = default.stdout == expected.encode() + b"\n"
        report["status"] = "measured-mixed-results-not-admitted"
    finally:
        args.result.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "default_lookup_passed": report.get("default_lookup_passed"),
                      "bound_lookup_passed": report["api"].get("bound_lookup_passed"),
                      "idn2": report["api"].get("idn2"), "runs": report["runs"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
