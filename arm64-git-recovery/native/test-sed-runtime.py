"""Exercise native MSYS text tools and compare Windows behavior to the verified bootstrap."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=("sed", "grep", "gawk"), default="sed")
    for name in ("build", "baseline", "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and fresh evidence output are required")
    manifest = args.build / "build-evidence.json"
    verify_tree(args.build / "stage", manifest)
    args.output.mkdir(parents=True)
    payload = args.output / "payload"
    shutil.copytree(args.build / "stage", payload)
    verify_tree(payload, manifest)
    executable = payload / f"usr/bin/{args.package}.exe"
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    env["PATH"] = str(executable.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["LC_ALL"] = "C"
    subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                    "-Root", str(payload), "-ReportPath", str(args.output / "artifacts.json")], check=True)
    records = []
    cases = (
        ("substitute", ["s/alpha/omega/"], b"alpha\nbeta\n"),
        ("crlf-anchor", ["-n", "/beta$/p"], b"alpha\r\nbeta\r\n"),
        ("binary-crlf", ["-b", "-n", "/beta$/p"], b"alpha\r\nbeta\r\n"),
        ("invalid-script", ["["], b"alpha\n"),
    ) if args.package == "sed" else (
        ("extended", ["-E", "^(alpha|beta)$"], b"alpha\nskip\nbeta\n"),
        ("crlf-anchor", ["-E", "^beta$"], b"alpha\r\nbeta\r\n"),
        ("binary-text", ["-a", "beta"], b"alpha\x00\nbeta\n"),
        ("no-match", ["unfindable"], b"alpha\n"),
        ("invalid-script", ["["], b"alpha\n"),
    ) if args.package == "grep" else (
        ("arithmetic", ["{sum += $1} END {print sum}"], b"1\n2\n3\n"),
        ("crlf-fields", ["{print $1}"], b"alpha one\r\nbeta two\r\n"),
        ("associative", ['{count[$1]++} END {print count["a"], count["b"]}'], b"a\nb\na\n"),
        ("invalid-script", ["BEGIN {"], b""),
    )
    for name, options, data in cases:
        baseline_env = {**env, "PATH": str(args.baseline.parent) + os.pathsep + env["PATH"]}
        baseline = subprocess.run([str(args.baseline), *options], input=data, env=baseline_env,
                                  capture_output=True, timeout=10)
        native = subprocess.run([str(executable), *options], input=data, env=env,
                                capture_output=True, timeout=10)
        for label, result in (("baseline", baseline), ("native", native)):
            (args.output / f"{name}-{label}.stdout").write_bytes(result.stdout)
            (args.output / f"{name}-{label}.stderr").write_bytes(result.stderr)
        passed = native.returncode == baseline.returncode and native.stdout == baseline.stdout
        if name == "invalid-script":
            passed = passed and native.returncode != 0 and bool(native.stderr)
        else:
            passed = passed and native.returncode == (1 if name == "no-match" else 0) and not native.stderr and not baseline.stderr
        if name == "substitute":
            passed = passed and native.stdout == b"omega\nbeta\n"
        if name == "extended":
            passed = passed and native.stdout == b"alpha\nbeta\n"
        if name == "arithmetic":
            passed = passed and native.stdout == b"6\n"
        if name == "associative":
            passed = passed and native.stdout == b"2 1\n"
        records.append({"name": name, "passed": passed, "native_exit": native.returncode,
                        "baseline_exit": baseline.returncode, "native_stdout_hex": native.stdout.hex()})
    if args.package == "grep":
        result = subprocess.run([str(executable), "-P", "beta"], input=b"beta\n", env=env,
                                capture_output=True, timeout=10)
        (args.output / "pcre-unavailable.stderr").write_bytes(result.stderr)
        records.append({"name": "pcre-explicitly-unavailable", "passed": result.returncode != 0 and
                        not result.stdout and b"--disable-perl-regexp" in result.stderr})
    if args.package == "gawk":
        fixture = args.output / "module-input.txt"
        fixture.write_bytes(b"native-gawk-module")
        result = subprocess.run([str(executable), "-l", "readfile", "-v", f"file={fixture.as_posix()}",
                                 'BEGIN {printf "%s", readfile(file)}'], env=env, capture_output=True, timeout=10)
        (args.output / "module.stdout").write_bytes(result.stdout)
        (args.output / "module.stderr").write_bytes(result.stderr)
        records.append({"name": "readfile-loadable", "passed": result.returncode == 0 and
                        result.stdout == b"native-gawk-module" and result.stderr == b""})
    hold_options = (["s/alpha/omega/"] if args.package == "sed" else
                    ["-E", "^alpha$"] if args.package == "grep" else ["{print toupper($0)}"])
    process = subprocess.Popen([str(executable), *hold_options], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                        "-ProcessId", str(process.pid), "-ReportPath", str(args.output / "process.json")], check=True)
        script = (f"(Get-Process -Id {process.pid}).Modules | "
                  "Where-Object {$_.ModuleName -eq 'msys-2.0.dll'} | "
                  "ForEach-Object {[ordered]@{path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                  "ConvertTo-Json -Compress")
        result = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", script],
                                capture_output=True, check=True)
        runtime = json.loads(result.stdout)
        expected_runtime = (executable.parent / "msys-2.0.dll").resolve()
        if Path(runtime["path"]).resolve() != expected_runtime or runtime["sha256"].lower() != digest(expected_runtime):
            raise ContractError("Different native runtime was loaded")
        stdout, stderr = process.communicate(b"alpha\n", timeout=10)
        expected = b"omega\n" if args.package == "sed" else b"alpha\n" if args.package == "grep" else b"ALPHA\n"
        records.append({"name": "observed-native-process", "passed": process.returncode == 0 and
                        stdout == expected and stderr == b""})
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    verify_tree(payload, manifest)
    report = {"passed": all(row["passed"] for row in records), "cases": records,
              "runtime": runtime, "build_manifest_sha256": digest(manifest),
              "baseline_sha256": digest(args.baseline),
              "scope": f"Native {args.package} text/binary/error behavior; x64 baseline is only a behavior control; bootstrap omissions remain explicit"}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native text-tool behavior differs; evidence retained")
    print(f"Native {args.package} passed {len(records)} behavior/native-runtime scenarios")


if __name__ == "__main__":
    main()
