"""Drive a real native-GCC OpenSSL build with explicitly labeled bootstrap Perl/make."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from bounded_process import run
from compiler_tools import require_msys_jump_receipt, support_identities, verify_msys_jmp_headers, verify_support
from openssl_contracts import validate_abi
from sources import ContractError, digest, inventory, verify_tree


def build(source, manifest, prefix, msys, output, jobs, target="mingwarm64", compiler_receipt=None, defer_tests=False):
    source, manifest, prefix, msys, output = map(lambda p: Path(p).resolve(),
                                                (source, manifest, prefix, msys, output))
    if os.name != "nt" or not 1 <= jobs <= 8 or output.exists():
        raise ContractError("Requires Windows, fresh output and explicit 1-8 jobs")
    verify_tree(source, manifest)
    source_record = json.loads(manifest.read_text())
    identity = source_record["source"]
    if identity["id"] != "openssl" or identity["version"] != "3.6.4":
        raise ContractError("Expected pinned OpenSSL 3.6.4")
    if target not in ("mingwarm64", "Cygwin-aarch64"):
        raise ContractError("Unknown native OpenSSL ABI profile")
    if target == "Cygwin-aarch64" and source_record.get("target_profile") != target:
        raise ContractError("MSYS OpenSSL requires its separate pinned patch stack and LP64 target")
    if target == "Cygwin-aarch64" and compiler_receipt is None:
        raise ContractError("MSYS OpenSSL requires the explicit producer input receipt")
    if compiler_receipt:
        verify_tree(prefix, compiler_receipt)
        record = json.loads(Path(compiler_receipt).read_text())
        if Path(record["prefix"]).resolve() != prefix:
            raise ContractError("Compiler receipt identifies another prefix")
        if target == "Cygwin-aarch64" and record.get("source_target", {}).get("Triple") != "aarch64-pc-cygwin":
            raise ContractError("The producer receipt does not identify the MSYS target")
        if target == "Cygwin-aarch64":
            require_msys_jump_receipt(record)
    bootstrap_files = inventory(msys / "usr")
    compiler = prefix / "bin/gcc.exe"
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "TMP", "TEMP") if key in os.environ}
    env.update({"MSYSTEM": "MSYS", "MSYS2_PATH_TYPE": "minimal", "CHERE_INVOKING": "1",
                "PATH": str(prefix / "bin") + os.pathsep + str(msys / "usr/bin") +
                        os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")})
    support = support_identities(compiler, prefix, env)
    definitions = subprocess.run([str(compiler), "-dM", "-E", "-x", "c", "-"],
                                 input=b"", env=env, capture_output=True, check=True).stdout.decode()
    macros = {}
    for line in definitions.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "#define":
            macros[parts[1]] = parts[2]
    validate_abi(target, macros)
    jmp_header_guard = verify_msys_jmp_headers(compiler, env) if target == "Cygwin-aarch64" else None
    tools = {str(path): digest(path) for path in
             (compiler, prefix / "bin/ar.exe", prefix / "bin/ranlib.exe", prefix / "bin/windres.exe",
              msys / "usr/bin/bash.exe", msys / "usr/bin/perl.exe", msys / "usr/bin/make.exe")}
    script = Path(__file__).with_suffix(".sh").resolve()
    command = [str(msys / "usr/bin/bash.exe"), "--noprofile", "--norc", script.as_posix(),
               str(source), str(prefix), str(output), str(jobs), target, "deferred" if defer_tests else "all"]
    log_path = output.with_name(output.name + ".launch.log")
    report = {"schema": 1, "status": "failed", "source": identity,
              "source_manifest_sha256": digest(manifest), "tools": tools,
              "compiler_receipt_sha256": digest(compiler_receipt) if compiler_receipt else None,
              "upstream_tests": "explicitly-deferred" if defer_tests else "required",
              "support_tools": support, "recipe_sha256": digest(script), "command": command,
              "build_host": "windows-arm64-native-compiler",
              "configure_driver": "windows-x64-emulated-msys",
              "target_profile": target,
              "jmp_header_guard": jmp_header_guard,
              "measured_abi_macros": {name: value for name, value in macros.items()
                                      if name in ("__aarch64__", "__SIZEOF_POINTER__", "__SIZEOF_LONG__",
                                                  "__MSYS__", "__CYGWIN__", "__MINGW32__")},
              "scope": "OpenSSL intermediate; not native POSIX build-driver or full distribution proof"}
    try:
        with log_path.open("xb") as log:
            report["process"] = run(command, cwd=output.parent, env=env, log=log, timeout=7200)
        report["exit_code"] = report["process"]["exit"]
        if not report["process"]["passed"]:
            raise ContractError(f"OpenSSL failed; see {log_path}")
        verify_support(support, compiler, prefix, env)
        for path, expected in tools.items():
            if digest(path) != expected:
                raise ContractError("Build driver changed during OpenSSL build")
        verify_tree(source, manifest)
        if compiler_receipt:
            verify_tree(prefix, compiler_receipt)
        if inventory(msys / "usr") != bootstrap_files:
            raise ContractError("OpenSSL bootstrap inputs changed")
        report["files"] = inventory(output / "stage")
        report["configdata_sha256"] = digest(output / "configdata.txt")
        report["status"] = ("native-openssl-built-tests-deferred" if defer_tests else
                            "native-openssl-built-tested-bootstrap-driver")
        report["pending"] = ["Native process and exact library behavior", "Full distribution integration"]
        if defer_tests:
            report["pending"].append("Complete OpenSSL upstream suite remains required")
    finally:
        report_path = output.with_name(output.name + ".result.json")
        with report_path.open("x", encoding="utf-8") as dest:
            json.dump(report, dest, indent=2)
            dest.write("\n")
    print(report["status"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "prefix", "msys", "output"):
        p.add_argument(f"--{name}", type=Path, required=True)
    p.add_argument("--jobs", type=int, required=True)
    p.add_argument("--target", choices=("mingwarm64", "Cygwin-aarch64"), default="mingwarm64")
    p.add_argument("--compiler-receipt", type=Path)
    p.add_argument("--defer-tests", action="store_true", help="Build a dependency candidate, explicitly not test-qualified")
    a = p.parse_args()
    build(a.source, a.manifest, a.prefix, a.msys, a.output, a.jobs, a.target, a.compiler_receipt, a.defer_tests)


if __name__ == "__main__":
    main()
