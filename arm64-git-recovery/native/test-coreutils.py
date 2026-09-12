"""Exercise installed native coreutils using only a fresh isolated fixture."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from sources import ContractError, digest


def test(root, output, pwsh, artifact_gate, process_gate):
    if os.name != "nt":
        raise ContractError("Coreutils target execution requires Windows")
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ContractError("Use a new fixture directory")
    output.mkdir(parents=True)
    subprocess.run([str(pwsh), "-NoProfile", "-File", str(artifact_gate), "-Root", str(root),
                    "-ReportPath", str(output / "artifacts.json")], check=True)
    artifacts = json.loads((output / "artifacts.json").read_text())
    if artifacts.get("Passed") is not True or not artifacts.get("CandidateCount"):
        raise ContractError("Native artifact gate did not pass")
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("MSYS", "MINGW", "GIT_", "BASH")) or name in ("SHELL", "ENV"):
            del env[name]
    env["PATH"] = str(root / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["HOME"] = str(output)
    env["LC_ALL"] = "C"
    data = b"b\na\nb\n"
    (output / "source file.txt").write_bytes(data)
    cases = [
        ("printf", [r"coreutils:%s:%d\n", "native", "37"], b"", b"coreutils:native:37\n"),
        ("cat", ["source file.txt"], b"", data),
        ("sort", [], data, b"a\nb\nb\n"),
        ("uniq", [], b"a\nb\nb\n", b"a\nb\n"),
        ("cp", ["source file.txt", "copied file.txt"], b"", b""),
        ("mkdir", ["created directory"], b"", b""),
        ("stat", ["--format=%s", "source file.txt"], b"", b"6\n"),
        ("sha256sum", ["--binary", "source file.txt"], b"", hashlib.sha256(data).hexdigest().encode() + b" *source file.txt\n"),
        ("rm", ["-f", "copied file.txt"], b"", b"")
    ]
    results = []
    for name, args, stdin, expected in cases:
        executable = root / "usr/bin" / f"{name}.exe"
        result = subprocess.run([str(executable), *args], input=stdin, capture_output=True,
                                cwd=output, env=env, timeout=30)
        (output / f"{name}.stdout.bin").write_bytes(result.stdout)
        (output / f"{name}.stderr.bin").write_bytes(result.stderr)
        passed = result.returncode == 0 and result.stdout == expected and result.stderr == b""
        if name == "cp":
            copied = output / "copied file.txt"
            passed = passed and copied.is_file() and copied.read_bytes() == data
        elif name == "mkdir":
            passed = passed and (output / "created directory").is_dir()
        elif name == "rm":
            passed = passed and not (output / "copied file.txt").exists()
        results.append({
            "name": name, "executable_sha256": digest(executable), "args": args,
            "exit_code": result.returncode, "exit_hex": f"0x{result.returncode & 0xffffffff:08X}",
            "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
            "stderr": result.stderr.decode("utf-8", errors="backslashreplace"), "passed": passed
        })
    cat = root / "usr/bin/cat.exe"
    process = subprocess.Popen([str(cat)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=output, env=env)
    native = False
    try:
        gate = subprocess.run([str(pwsh), "-NoProfile", "-File", str(process_gate),
                               "-ProcessId", str(process.pid), "-ReportPath", str(output / "cat-process.json")],
                              capture_output=True)
        (output / "cat-process-gate.stdout.bin").write_bytes(gate.stdout)
        (output / "cat-process-gate.stderr.bin").write_bytes(gate.stderr)
        if gate.returncode == 0:
            report = json.loads((output / "cat-process.json").read_text())
            native = (report.get("Passed") is True and report.get("MeasuredCount") == 1
                      and report["Processes"][0]["ImagePath"].casefold() == str(cat).casefold()
                      and report["Processes"][0].get("ProcessMachine") == "0xAA64")
        stdout, stderr = process.communicate(b"held-cat\n", timeout=10)
        native = native and process.returncode == 0 and stdout == b"held-cat\n" and stderr == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    summary = {
        "passed": native and all(case["passed"] for case in results),
        "scope": "Nine coreutils functional scenarios and held cat native identity; bootstrap NLS/GMP disabled",
        "native_cat": native, "cases": results,
        "artifact_gate_sha256": digest(artifact_gate), "process_gate_sha256": digest(process_gate)
    }
    (output / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        raise ContractError("Native coreutils behavior failed; full results preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    test(args.root, args.output, args.pwsh, args.artifact_gate, args.process_gate)


if __name__ == "__main__":
    main()
