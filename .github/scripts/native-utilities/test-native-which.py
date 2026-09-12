"""Exercise shipped which with only owned PATH entries and exact907 live identity."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def posix(path):
    return "/proc/cygdrive/" + path.drive[0].lower() + path.as_posix()[2:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity-helper", type=Path, required=True)
    parser.add_argument("--identity-sha", required=True)
    args = parser.parse_args()
    if args.output.exists() or sha(args.identity_helper) != args.identity_sha:
        raise RuntimeError("Output must be new and existing identity helper must match")
    args.output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("existing_identity", args.identity_helper)
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    root, output = args.root.resolve(), args.output.resolve()
    exe = root / "usr/bin/which.exe"
    folders = [output / name for name in ("first", "second", "work", "home", "temp")]
    for folder in folders:
        folder.mkdir()
    first, second, work, home, temporary = folders
    for folder in (first, second, work):
        shutil.copyfile(exe, folder / "chosen.exe")
    (first / "directory.exe").mkdir()
    shutil.copyfile(exe, second / "directory.exe")
    environment = {"SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
                   "PATH": posix(first) + ":" + posix(second),
                   "HOME": posix(home), "USERPROFILE": str(home), "TEMP": str(temporary), "TMP": str(temporary),
                   "LC_ALL": "C.UTF-8"}
    report = {"schema": 1, "status": "failed", "package_executable_sha256": sha(exe),
              "environment": environment, "cases": [], "runtime_root": str(root)}

    def run(name, arguments, expected, raw=0, data=b"", path=None, live=False, error_contains=None):
        env = dict(environment)
        if path is not None:
            env["PATH"] = path
        command = [str(exe), *arguments]
        record = {"name": name, "command": command, "cwd": str(work), "environment": env,
                  "expected_raw_exit": raw, "stdin_sha256": hashlib.sha256(data).hexdigest()}
        report["cases"].append(record)
        process = subprocess.Popen(command, cwd=work, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        record["pid"] = process.pid
        try:
            if live:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Which exited before its stdin/live-identity control")
                    try:
                        record["live_identity"] = identity.identity(process.pid, root, {
                            "msys-2.0.dll": "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"})
                        break
                    except RuntimeError as error:
                        if not str(error).startswith("Required live DLL did not match:") or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.02)
                    except OSError as error:
                        if error.winerror != 24 or time.monotonic() >= deadline:
                            raise
                        # Toolhelp documents ERROR_BAD_LENGTH while the loader changes modules.
                        time.sleep(0.02)
            stdout, stderr = process.communicate(data, timeout=15)
            record.update(raw_exit=process.returncode, stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                          stderr_sha256=hashlib.sha256(stderr).hexdigest())
            (output / (name + ".stdout")).write_bytes(stdout)
            (output / (name + ".stderr")).write_bytes(stderr)
            if process.returncode != raw or stdout != expected:
                raise RuntimeError(f"{name}: raw={process.returncode}; stdout={stdout!r}; expected={expected!r}")
            if error_contains is not None and error_contains not in stderr:
                raise RuntimeError(f"{name}: missing expected diagnostic")
            record["passed"] = True
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    p1, p2 = posix(first) + "/chosen.exe\n", posix(second) + "/chosen.exe\n"
    try:
        run("path-first", ["chosen.exe"], p1.encode())
        run("path-reversed", ["chosen.exe"], p2.encode(), path=posix(second) + ":" + posix(first))
        run("all", ["--all", "chosen.exe"], (p1 + p2).encode())
        run("extensionless", ["chosen"], p1.replace(".exe\n", "\n").encode())
        run("missing", ["absent-native-907"], b"", 1, error_contains=b"no absent-native-907 in")
        run("multiple-missing-count", ["missing-one", "missing-two"], b"", 2)
        run("no-host-substitution", ["bash"], b"", 1, error_contains=b"no bash in")
        run("skip-directory", ["directory.exe"], (posix(second) + "/directory.exe\n").encode())
        run("show-dot", ["--show-dot", "chosen.exe"], b"./chosen.exe\n", path=".:" + posix(first))
        run("skip-dot", ["--skip-dot", "chosen.exe"], p1.encode(), path=".:" + posix(first))
        run("mixed-absolute-pinned-patch", [(first / "chosen.exe").as_posix()],
            ((first / "chosen.exe").as_posix() + "\n").encode())
        alias = b"alias nativealias='chosen.exe'\n"
        run("read-alias-live", ["--read-alias", "nativealias"], alias + b"\t" + p1.encode(), data=alias, live=True)
        run("skip-alias", ["--read-alias", "--skip-alias", "nativealias"], b"", 1, data=alias)
        function = b"nativefunc ()\n{\n    chosen.exe\n}\n"
        run("read-functions", ["--read-functions", "nativefunc"], function, data=function)
        run("skip-functions", ["--read-functions", "--skip-functions", "nativefunc"], b"", 1, data=function)
        report["status"] = "native907-shipped-which-functional-pass"
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "exe_sha256": sha(exe)}))


if __name__ == "__main__":
    main()
