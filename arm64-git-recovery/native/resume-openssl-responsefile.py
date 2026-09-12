"""Resume an owned failed MSYS OpenSSL link using upstream shared_argfileflag support."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from bounded_process import run
from compiler_tools import verify_support
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "compiler-receipt", "bootstrap", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a fresh recovery receipt directory are required")
    original_receipt = args.build.with_name(args.build.name + ".result.json")
    original = json.loads(original_receipt.read_text())
    if (original["status"] != "failed" or original["target_profile"] != "Cygwin-aarch64"
            or original["upstream_tests"] != "explicitly-deferred"
            or original["compiler_receipt_sha256"] != digest(args.compiler_receipt)):
        raise ContractError("Expected this producer's explicitly unqualified, failed MSYS OpenSSL build")
    verify_tree(args.prefix, args.compiler_receipt)
    compiler_input = json.loads(args.compiler_receipt.read_text())
    if Path(compiler_input["prefix"]).resolve() != args.prefix.resolve():
        raise ContractError("The compiler receipt identifies a different prefix")
    source = args.build / "source"
    config = source / "Configurations/99-msys-arm64.conf"
    profile = Path(__file__).with_name("openssl-msys-arm64.conf")
    line = '        shared_argfileflag => "@",\n'
    updated = profile.read_text()
    current = config.read_text()
    if updated.count(line) != 1 or current not in (updated, updated.replace(line, "")):
        raise ContractError("Only the upstream shared response-file setting may change")
    before = inventory(source)
    bootstrap = inventory(args.bootstrap / "usr")
    args.output.mkdir(parents=True)
    for name in ("temp", "home", "original"):
        (args.output / name).mkdir()
    for name in ("Makefile", "configdata.pm", "Configurations/99-msys-arm64.conf"):
        destination = args.output / "original" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    (args.output / "original-source.json").write_text(json.dumps({"files": before}, indent=2) + "\n")
    reconfigure = current != updated
    if reconfigure:
        config.write_text(updated, newline="\n")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.bootstrap / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    env.update({"HOME": str(args.output / "home"), "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp")})
    script = Path(__file__).with_suffix(".sh")
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.build, args.prefix, args.output, str(args.jobs), "1" if reconfigure else "0"]
    report = {"schema": 1, "status": "failed", "original_receipt_sha256": digest(original_receipt),
              "compiler_receipt_sha256": digest(args.compiler_receipt), "recipe_sha256": digest(script),
              "target_profile_sha256": digest(profile), "command": list(map(str, command)),
              "reconfigured": reconfigure,
              "upstream_tests": "explicitly-deferred", "scope": "Native compiler; x64 bootstrap driver; upstream response files"}
    try:
        with (args.output / "resume.log").open("xb") as log:
            report["process"] = run(command, cwd=args.output, env=env, log=log, timeout=7200)
        if not report["process"]["passed"]:
            raise ContractError("OpenSSL response-file recovery failed; original metadata and new log retained")
        after = inventory(source)
        report["changed_existing_objects"] = [
            name for name in before if name.endswith(".obj") and before[name] != after.get(name)]
        report["original_object_count"] = sum(name.endswith(".obj") for name in before)
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(original["support_tools"], args.prefix / "bin/gcc.exe", args.prefix, env)
        if inventory(args.bootstrap / "usr") != bootstrap:
            raise ContractError("OpenSSL bootstrap changed during recovery")
        stage = args.build / "stage"
        report["files"] = inventory(stage)
        required = ("bin/openssl.exe", "bin/msys-crypto-3.dll", "bin/msys-ssl-3.dll")
        if any(name not in report["files"] for name in required):
            raise ContractError("MSYS OpenSSL installation is incomplete")
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("MSYS OpenSSL native PE gate failed")
        report["stage"] = str(stage)
        report["status"] = "native-msys-openssl-built-tests-deferred"
        report["pending"] = ["Complete OpenSSL upstream suite", "Native crypto/TLS and loaded-library closure",
                             "Final runtime/library FP metadata closure"]
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
