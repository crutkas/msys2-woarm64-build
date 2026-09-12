"""Replay unchanged native OpenSSL binaries, bounding and containing all fixture children."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from bounded_process import run
from compiler_tools import require_msys_ucontext_receipt
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "msys", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    parser.add_argument("--timeout", type=int, required=True)
    parser.add_argument("--compiler-receipt", type=Path)
    parser.add_argument("--runtime-profile", choices=("mingw", "msys"), default="mingw")
    parser.add_argument("--native-job-prefix", type=Path)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    args.build, args.output = args.build.resolve(), args.output.resolve()
    if args.output.exists():
        raise ContractError("A new result directory is required")
    if args.runtime_profile == "msys" and args.compiler_receipt is None:
        raise ContractError("Native MSYS replay requires its exact compiler/runtime receipt")
    if args.runtime_profile == "msys" and args.native_job_prefix is None:
        raise ContractError("Native MSYS upstream replay requires complete native child-exit observation")
    job_manifest = None
    if args.native_job_prefix:
        job_manifest = verify_driver(args.native_job_prefix)
    if args.compiler_receipt:
        verify_tree(args.prefix, args.compiler_receipt)
        compiler = json.loads(args.compiler_receipt.read_text())
        if Path(compiler["prefix"]).resolve() != args.prefix.resolve():
            raise ContractError("The replay compiler receipt identifies a different prefix")
        if args.runtime_profile == "msys":
            require_msys_ucontext_receipt(compiler)
            if compiler.get("source_target", {}).get("Triple") != "aarch64-pc-cygwin":
                raise ContractError("MSYS replay cannot use a MinGW producer")
    scripts = Path(__file__).parent.resolve()
    recipe_files = {str(scripts / name): digest(scripts / name) for name in (
        "replay-openssl-tests.py", "replay-openssl-tests.sh", "openssl-test-transport.sh",
        "openssl-test-uris.sh", "openssl-native-exec.py", "pe-export-names.py", "pe_exports.py",
        "bounded_process.py", "compiler_tools.py", "native_job_runner.py")}
    test_module = args.build / "util/perl/OpenSSL/Test.pm"
    if "$exe_shell //= $ENV{OPENSSL_NATIVE_TEST_TRANSPORT};" not in test_module.read_text():
        raise ContractError("Apply the maintained native transport test-driver patch first")
    recipe_files[str(test_module)] = digest(test_module)
    recipe_files[str(scripts / "patches/openssl-native-test-transport.patch")] = digest(
        scripts / "patches/openssl-native-test-transport.patch")
    if args.runtime_profile == "msys":
        recipe_files[sys.executable] = digest(sys.executable)
    binaries = {name: value for name, value in inventory(args.build).items()
                if name.lower().endswith((".exe", ".dll"))}
    bootstrap_files = inventory(args.msys / "usr")
    command = [args.msys / "usr/bin/bash.exe", "--noprofile", "--norc",
               (scripts / "replay-openssl-tests.sh").as_posix(),
               args.build, args.prefix, args.output, str(args.jobs), *args.tests]
    log_path = args.output.with_suffix(".log")
    report = {"command": list(map(str, command)), "recipes": recipe_files, "binaries": binaries,
              "tests": args.tests, "started": time.time(), "timeout_seconds": args.timeout,
              "runtime_profile": args.runtime_profile,
              "compiler_receipt_sha256": digest(args.compiler_receipt) if args.compiler_receipt else None,
              "driver_scope": "x64 emulated bootstrap Perl/make; target binaries remain native"}
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = str(args.msys / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["HOME"] = env["USERPROFILE"] = str(args.output / "home")
    env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(args.output / "temp")
    env["OPENSSL_NATIVE_TEST_PROFILE"] = args.runtime_profile
    env["OPENSSL_NATIVE_TEST_PYTHON"] = sys.executable
    env["OPENSSL_NATIVE_PE_EXPORT_READER"] = str(scripts / "pe-export-names.py")
    env["OPENSSL_NATIVE_EXIT_LOG"] = str(args.output / "native-exits.jsonl")
    env["OPENSSL_CA_DIR"] = "./demoCA"
    if args.native_job_prefix:
        job_result = args.output.with_name(args.output.name + ".native-job.json")
        env["WOARM64_NATIVE_TEST_ROOT"] = str(args.build)
        report["process"] = run_observed(
            command, cwd=scripts, env=env, log_path=log_path, result_path=job_result,
            relay_records=args.output / "native-exit-records", timeout=args.timeout,
            driver_prefix=args.native_job_prefix)
    else:
        with log_path.open("xb") as log:
            report["process"] = run(command, cwd=scripts, env=env, log=log, timeout=args.timeout)
    report["log_sha256"] = digest(log_path)
    native_exits = args.output / "native-exits.jsonl"
    report["native_exit_log_sha256"] = digest(native_exits) if native_exits.exists() else None
    report["finished"] = time.time()
    text = log_path.read_text(encoding="utf-8", errors="replace")
    report["test_count"] = sum(map(int, re.findall(r"Files=\d+,\s*Tests=(\d+)", text)))
    report["skipped_recipes"] = [line for line in text.splitlines() if "skipped:" in line]
    report["inputs_unchanged"] = (
        all(digest(path) == expected for path, expected in recipe_files.items()) and
        all(digest(args.build / name) == row["sha256"] for name, row in binaries.items()))
    report["bootstrap_unchanged"] = inventory(args.msys / "usr") == bootstrap_files
    if args.compiler_receipt:
        verify_tree(args.prefix, args.compiler_receipt)
    report["passed"] = (report["process"]["passed"] and report["inputs_unchanged"] and report["bootstrap_unchanged"] and
                        report["test_count"] > 0 and "Result: PASS" in text)
    args.output.with_suffix(".result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "process": report["process"]}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
