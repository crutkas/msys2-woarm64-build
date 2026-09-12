"""Compare actual shipped converter bytes, aliases, errors and native NLS behavior."""
import argparse
import gettext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity-helper", type=Path, required=True)
    parser.add_argument("--identity-sha", required=True)
    args = parser.parse_args()
    if args.output.exists() or sha(args.identity_helper.read_bytes()) != args.identity_sha:
        raise RuntimeError("Output must be new and the existing identity helper must be pinned")
    root, output = args.root.resolve(), args.output.resolve()
    output.mkdir(parents=True)
    for folder in ("home", "temp"):
        (output / folder).mkdir()
    spec = importlib.util.spec_from_file_location("existing_identity", args.identity_helper)
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    binary = root / "usr/bin"
    environment = {"SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
                   "PATH": str(binary) + ";" + os.environ["SystemRoot"] + r"\System32",
                   "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                   "TMP": str(output / "temp"), "TEMP": str(output / "temp"),
                   "LC_ALL": "C.UTF-8"}
    required = {"msys-2.0.dll": "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c",
                "msys-intl-8.dll": "44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c",
                "msys-iconv-2.dll": "86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215"}
    report = {"schema": 1, "status": "failed", "cases": [], "environment": environment, "runtime_root": str(root),
              "executables": {name: sha((binary / (name + ".exe")).read_bytes())
                              for name in ("dos2unix", "unix2dos", "d2u", "u2d")},
              "test_only_native_exec": sha((binary / "native-utility-exec.exe").read_bytes())}

    def run(name, tool, arguments, *, data=b"", expected_stdout=b"", raw=0, env=None, live=False, contains=None):
        target = binary / (tool + ".exe")
        command = [str(target), *arguments]
        if tool in ("mac2unix", "unix2mac"):
            command.insert(0, str(binary / "native-utility-exec.exe"))
        current = dict(environment)
        current.update(env or {})
        record = {"name": name, "tool": tool, "command": command, "environment": current,
                  "expected_raw_exit": raw, "stdin_sha256": sha(data)}
        report["cases"].append(record)
        process = subprocess.Popen(command, cwd=output, env=current, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        record["pid"] = process.pid
        try:
            if live:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Converter exited before its live stdin control")
                    try:
                        record["live_identity"] = identity.identity(process.pid, root, required)
                        break
                    except RuntimeError as error:
                        if not str(error).startswith("Required live DLL did not match:") or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.02)
                    except OSError as error:
                        if error.winerror not in (18, 24, 299) or time.monotonic() >= deadline:
                            raise
                        record.setdefault("startup_snapshot_errors", []).append(error.winerror)
                        time.sleep(0.02)
            stdout, stderr = process.communicate(data, timeout=15)
            record.update(raw_exit=process.returncode, stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
            (output / (name + ".stdout")).write_bytes(stdout)
            (output / (name + ".stderr")).write_bytes(stderr)
            if process.returncode != raw or (expected_stdout is not None and stdout != expected_stdout):
                raise RuntimeError(f"{name}: raw={process.returncode}, stdout={stdout!r}, stderr={stderr!r}")
            if contains is not None and contains not in stdout:
                raise RuntimeError(f"{name}: required translated output is absent")
            record["passed"] = True
            return record
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def convert(name, tool, content, expected, options=(), raw=0):
        source, target = output / (name + " input.txt"), output / (name + " output.txt")
        source.write_bytes(content)
        record = run(name, tool, [*options, "-n", str(source), str(target)], raw=raw)
        record.update(source_sha256=sha(content), expected_output_sha256=sha(expected) if expected is not None else None)
        if source.read_bytes() != content:
            raise RuntimeError(f"{name}: new-file mode changed its input")
        if expected is None:
            if target.exists():
                raise RuntimeError(f"{name}: skipped/error input created an output")
        elif target.read_bytes() != expected:
            record["actual_output_sha256"] = sha(target.read_bytes())
            record["passed"] = False
            raise RuntimeError(f"{name}: exact output byte comparison failed")
        else:
            record["output_sha256"] = sha(target.read_bytes())

    try:
        lf, crlf, cr = b"alpha\nbeta\n", b"alpha\r\nbeta\r\n", b"alpha\rbeta\r"
        for tool, before, after in (("dos2unix", crlf, lf), ("unix2dos", lf, crlf),
                                    ("mac2unix", cr, lf), ("unix2mac", lf, cr),
                                    ("d2u", crlf, lf), ("u2d", lf, crlf)):
            convert(tool + "-newfile", tool, before, after)
            run(tool + "-stdin", tool, [], data=before, expected_stdout=after,
                live=tool in ("dos2unix", "unix2dos"))
        text = "caf\u00e9 \u03bb \u4e2d \U0001f642"
        utf8 = (text + "\n").encode()
        dos_utf8 = (text + "\r\n").encode()
        convert("utf8-unicode", "dos2unix", dos_utf8, utf8)
        convert("utf8-remove-bom", "dos2unix", b"\xef\xbb\xbf" + dos_utf8, utf8)
        convert("utf8-keep-bom", "dos2unix", b"\xef\xbb\xbf" + dos_utf8, b"\xef\xbb\xbf" + utf8, ["-b"])
        convert("utf8-add-bom", "dos2unix", dos_utf8, b"\xef\xbb\xbf" + utf8, ["-m"])
        convert("unix2dos-default-keep-bom", "unix2dos", b"\xef\xbb\xbf" + utf8, b"\xef\xbb\xbf" + dos_utf8)
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")):
            content = bom + (text + "\r\n").encode(encoding)
            convert(encoding + "-to-utf8", "dos2unix", content, utf8)
            convert(encoding + "-keep-unicode", "dos2unix", content, (text + "\n").encode(encoding), ["-u"])
            convert(encoding + "-keep-unicode-bom", "dos2unix", content, bom + (text + "\n").encode(encoding), ["-u", "-b"])
        binary_data = b"one\r\n\x00two\r\n"
        convert("binary-safe-skip", "dos2unix", binary_data, None)
        convert("binary-explicit-error", "dos2unix", binary_data, None, ["--error-binary"], 1)
        convert("binary-force", "dos2unix", binary_data, b"one\n\x00two\n", ["-f"])
        convert("invalid-surrogate", "dos2unix", b"\xff\xfe\x00\xd8", None, raw=1)
        run("missing-input", "dos2unix", ["-n", str(output / "absent.txt"), str(output / "absent-output.txt")], raw=2)
        if (output / "absent-output.txt").exists():
            raise RuntimeError("Missing input produced an output")
        old = output / "old file keep date.txt"
        old.write_bytes(crlf)
        os.utime(old, (1600000000, 1600000000))
        record = run("oldfile-keepdate", "dos2unix", ["-k", str(old)])
        if old.read_bytes() != lf or old.stat().st_mtime != 1600000000:
            raise RuntimeError("Old-file conversion or keep-date behavior changed")
        record["output_sha256"] = sha(old.read_bytes())
        with (root / "usr/share/locale/fr/LC_MESSAGES/dos2unix.mo").open("rb") as stream:
            catalog = gettext.GNUTranslations(stream)
        original = "Usage: %s [options] [file ...] [-n infile outfile ...]\n"
        translated = catalog.gettext(original)
        if translated == original:
            raise RuntimeError("French catalog lacks the expected real translation")
        run("french-default-locale-path", "dos2unix", ["--help"], expected_stdout=None,
            env={"LANGUAGE": "fr", "LC_ALL": "fr_FR.UTF-8"}, contains=(translated % "dos2unix").encode())
        report["status"] = "native907-shipped-dos2unix-functional-pass"
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"])}))


if __name__ == "__main__":
    main()
