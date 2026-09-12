"""Bounded real PCRE2 interpreter/JIT comparisons; preserve failing raw output."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from sources import ContractError, digest


def test(root, output, pwsh=None, artifact_gate=None, process_gate=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if os.name != "nt" or output.exists():
        raise ContractError("Requires Windows and a new evidence directory")
    output.mkdir(parents=True)
    if any((pwsh, artifact_gate, process_gate)) and not all((pwsh, artifact_gate, process_gate)):
        raise ContractError("Native evidence requires PowerShell and both controlled gate paths")
    if artifact_gate:
        subprocess.run([str(pwsh), "-NoProfile", "-File", str(artifact_gate), "-Root", str(root),
                        "-ReportPath", str(output / "artifacts.json")], check=True)
        artifact = json.loads((output / "artifacts.json").read_text())
        if artifact.get("Passed") is not True or not artifact.get("CandidateCount"):
            raise ContractError("Installed PCRE2 native artifact gate did not pass")
    exe = root / "pcre2test.exe"
    if not exe.is_file():
        raise ContractError("Missing built pcre2test.exe")
    env = dict(os.environ)
    env["PATH"] = str(root) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    payload = b"/the quick brown fox/\n    the quick brown fox\n\n"
    expected = b"/the quick brown fox/\n    the quick brown fox\n 0: the quick brown fox\n\n"
    (output / "input.txt").write_bytes(payload)
    cases = []
    for width in ("8", "16", "32"):
        for jit in (False, True):
            name = f"width-{width}-{'jit' if jit else 'interpreter'}"
            command = [str(exe), "-q", f"-{width}", *(["-jit"] if jit else [])]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd=output, env=env)
            timed_out = False
            try:
                if process_gate:
                    subprocess.run([str(pwsh), "-NoProfile", "-File", str(process_gate),
                                    "-ProcessId", str(process.pid),
                                    "-ReportPath", str(output / f"{name}-process.json")], check=True)
                    native = json.loads((output / f"{name}-process.json").read_text())
                    if (native.get("Passed") is not True or native.get("MeasuredCount") != 1
                            or native["Processes"][0]["ImagePath"].casefold() != str(exe).casefold()):
                        raise ContractError("Native PCRE2 process does not match the installed executable")
                stdout, stderr = process.communicate(payload, timeout=15)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                stdout, stderr = process.communicate()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            (output / f"{name}.stdout.bin").write_bytes(stdout)
            (output / f"{name}.stderr.bin").write_bytes(stderr)
            cases.append({"case": name, "argv": command, "exit_code": process.returncode,
                          "exit_hex": f"0x{process.returncode & 0xffffffff:08X}",
                          "timed_out": timed_out, "matched": b" 0: the quick brown fox" in stdout,
                          "exact_output": stdout == expected and stderr == b"",
                          "stdout_sha256": digest(output / f"{name}.stdout.bin"),
                          "stderr_sha256": digest(output / f"{name}.stderr.bin")})
    result = {"schema": 1, "scope": "Single literal regex through native PCRE2 interpreter and JIT in all widths",
              "passed": all(c["exit_code"] == 0 and c["exact_output"] and not c["timed_out"] for c in cases),
              "inputs": {p.name: digest(p) for p in root.iterdir()
                         if p.is_file() and p.suffix.lower() in (".exe", ".dll")},
              "cases": cases}
    if process_gate:
        result["native_process_gates"] = 6
        result["gate_sha256"] = {"artifact": digest(artifact_gate), "process": digest(process_gate)}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise ContractError("PCRE2 interpreter/JIT behavior failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path)
    parser.add_argument("--artifact-gate", type=Path)
    parser.add_argument("--process-gate", type=Path)
    args = parser.parse_args()
    test(args.root, args.output, args.pwsh, args.artifact_gate, args.process_gate)


if __name__ == "__main__":
    main()
