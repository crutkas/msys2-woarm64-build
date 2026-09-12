"""Confirm one unchanged CMocka wrapped example with exact private DLLs and loader events."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from cmake_test_replay import verify_build_files
from native_job_runner import run_observed
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build-result", "compiler-receipt", "native-job-prefix", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists() or digest(args.build_result) != args.sha256:
        raise ContractError("One-helper control requires a fresh output and the exact CMocka build")
    build_record = json.loads(args.build_result.read_text())
    compiler = json.loads(args.compiler_receipt.read_text())
    if (build_record.get("package") != "cmocka" or
            build_record.get("status") != "native-msys-cmake-built-not-tested" or
            build_record["compiler_receipt_sha256"] != digest(args.compiler_receipt) or
            compiler.get("source_status") != "qualified-native-msys-stack-guard-c-compiler-delta"):
        raise ContractError("The wrapped-example control requires the freshly rebuilt protected CMocka cohort")
    build = args.build_result.parent / "build"
    verify_build_files(build, build_record["compiled_files"])
    verify_tree(compiler["prefix"], args.compiler_receipt)
    inputs = [build / "example/mock/chef_wrap/waiter_test_wrap.exe",
              build / "src/msys-cmocka-0.dll", Path(compiler["prefix"]) / "bin/msys-2.0.dll"]
    identities = {str(path): digest(path) for path in inputs}
    capture = Path(__file__).with_name("capture-native-exception.py")
    recipe = {str(path): digest(path) for path in
              (Path(__file__), capture, Path(__file__).with_name("native_job_runner.py"),
               args.build_result, args.compiler_receipt)}
    destinations = {inputs[0]: args.output / "build/example/mock/chef_wrap" / inputs[0].name,
                    inputs[1]: args.output / "build/src" / inputs[1].name,
                    inputs[2]: args.output / "runtime" / inputs[2].name}
    for path, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    (args.output / "native-exits").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    search_path = os.pathsep.join(map(str, (destinations[inputs[1]].parent, destinations[inputs[2]].parent,
                                          Path(os.environ["SystemRoot"]) / "System32")))
    env.update({"PATH": search_path,
                "HOME": str(args.output), "USERPROFILE": str(args.output), "TEMP": str(args.output),
                "TMP": str(args.output), "WOARM64_NATIVE_TEST_ROOT": str(args.output)})
    report = {"status": "failed", "inputs": identities, "recipe": recipe, "child_path": search_path,
              "scope": "One byte-identical wrapped example, private compatible DLLs, actual load events and native raw exit; no source/link/flag changes"}
    try:
        report["process"] = run_observed(
            [sys.executable, "-B", capture, "--executable", destinations[inputs[0]],
             "--path-directory", destinations[inputs[1]].parent,
             "--runtime-directory", destinations[inputs[2]].parent, "--output", args.output / "capture"],
            cwd=args.output, env=env, log_path=args.output / "observer.log",
            result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
            timeout=30, driver_prefix=args.native_job_prefix)
        evidence = json.loads((args.output / "capture/result.json").read_text())
        if (not report["process"]["passed"] or evidence["exit_code"] != 0 or evidence["timed_out"]
                or evidence["exception_limit_reached"]):
            raise ContractError("The single wrapped-example native control did not exit successfully")
        loaded = {}
        for row in evidence["modules"]:
            path = Path(row["path"].removeprefix("\\\\?\\")).resolve()
            loaded[path.name.lower()] = {"path": str(path), "sha256": digest(path)}
        for path in inputs:
            expected = destinations[path]
            row = loaded.get(path.name.lower())
            if row is None or Path(row["path"]) != expected or row["sha256"] != identities[str(path)]:
                raise ContractError("Wrapped example loaded an unexpected executable or MSYS/CMocka DLL")
        text = (args.output / "capture/stdout.bin").read_bytes() + (args.output / "capture/stderr.bin").read_bytes()
        if b"[  PASSED  ] 2 test(s)." not in text:
            raise ContractError("Both unchanged upstream wrapped-example assertions must pass")
        report.update({"status": "native-cmocka-wrapped-example-and-exact-dll-closure-passed",
                       "loaded_modules": loaded,
                       "files": {destination.relative_to(args.output).as_posix():
                                 {"sha256": digest(destination), "size": destination.stat().st_size}
                                 for destination in destinations.values()}})
    finally:
        if any(digest(path) != sha for path, sha in {**identities, **recipe}.items()):
            report["status"] = "failed"
            report["input_error"] = "Control input or recipe changed"
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] == "failed":
        raise ContractError("Wrapped-example input integrity failed")
    print(report["status"])


if __name__ == "__main__":
    main()
