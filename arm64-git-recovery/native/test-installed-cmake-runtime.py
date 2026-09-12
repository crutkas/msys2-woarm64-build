"""Exercise installed CMake library APIs with unchanged upstream fixtures and exact loaded DLLs."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from cmake_test_replay import verify_build_files
from native_job_runner import run_observed
from sources import ContractError, digest, inventory, verify_tree

PROFILES = {
    "cmocka": {"tests": 49, "fixture": "example/mock/chef_wrap/waiter_test_wrap.exe",
               "dll": "msys-cmocka-0.dll", "marker": b"[  PASSED  ] 2 test(s)."},
    "libcbor": {"tests": 28, "fixture": "test/array_encoders_test.exe",
                "dll": "msys-cbor-0.14.dll", "marker": b"[  PASSED  ]"},
    "libfido2": {"tests": 8, "fixture": "regress/regress_es256.exe",
                 "dll": "msys-fido2-1.dll", "marker": None},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("tested-result", "compiler-receipt", "native-job-prefix", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists() or digest(args.tested_result) != args.sha256:
        raise ContractError("Installed API control requires a fresh output and the exact complete test/install result")
    tested = json.loads(args.tested_result.read_text())
    package = tested["package"]
    if package not in PROFILES:
        raise ContractError("No reviewed upstream API fixture for this library")
    profile = PROFILES[package]
    tests = tested.get("upstream_tests", [])
    if (tested.get("status") != "native-msys-cmake-built-tested" or tested.get("inputs_unchanged") is not True
            or tested.get("compiler_receipt_sha256") != digest(args.compiler_receipt)
            or len(tests) != profile["tests"] or len(set(tests)) != len(tests)
            or set(tests) != set(tested.get("upstream_test_names", []))):
        raise ContractError("The exact complete observed upstream suite and private installation must pass first")
    original_path = Path(tested["original_build"]["path"])
    if digest(original_path) != tested["original_build"]["sha256"]:
        raise ContractError("Original built fixture receipt changed")
    original = json.loads(original_path.read_text())
    build = original_path.parent / "build"
    verify_build_files(build, original["compiled_files"])
    compiler = json.loads(args.compiler_receipt.read_text())
    verify_tree(compiler["prefix"], args.compiler_receipt)
    stage = args.tested_result.parent / "stage"
    verify_tree(stage, args.tested_result)
    fixture = build / profile["fixture"]
    capture = Path(__file__).with_name("capture-native-exception.py")
    identities = {str(path): digest(path) for path in
                  (args.tested_result, original_path, args.compiler_receipt, fixture, capture,
                   Path(__file__), Path(__file__).with_name("native_job_runner.py"))}
    for item in tested["runtime_inputs"]:
        if digest(item["path"]) != item["sha256"]:
            raise ContractError("Receipt-bound runtime or test-only dependency DLL changed")
        identities[item["path"]] = item["sha256"]
    relocated = args.output / "relocated"
    shutil.copytree(stage, relocated)
    runtime = args.output / "runtime"
    runtime.mkdir()
    (args.output / "tests").mkdir()
    (args.output / "native-exits").mkdir()
    executable = args.output / "tests" / fixture.name
    shutil.copyfile(fixture, executable)
    expected = {executable.name.lower(): (executable, digest(fixture)),
                profile["dll"].lower(): (relocated / "usr/bin" / profile["dll"],
                                         tested["files"]["usr/bin/" + profile["dll"]]["sha256"])}
    for item in tested["runtime_inputs"]:
        path = Path(item["path"])
        if path.name.lower() in expected:
            raise ContractError("Installed library/runtime DLL names collide")
        destination = runtime / path.name
        shutil.copyfile(path, destination)
        expected[path.name.lower()] = (destination, item["sha256"])
    search = [relocated / "usr/bin", runtime, Path(os.environ["SystemRoot"]) / "System32"]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, search)), "HOME": str(args.output),
                "USERPROFILE": str(args.output), "TEMP": str(args.output), "TMP": str(args.output),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output), "WOARM64_NATIVE_ARG_CONVERSION": "none"})
    report = {"schema": 1, "status": "failed", "package": package, "input_identities": identities,
              "tested_result_sha256": args.sha256, "child_path": env["PATH"],
              "scope": "Installed native library API fixture and exact private loaded-DLL closure; test dependencies are not distribution payload or independent package admission"}
    try:
        report["process"] = run_observed(
            [sys.executable, "-B", capture, "--executable", executable, "--path-directory", search[0],
             "--runtime-directory", runtime, "--output", args.output / "capture"],
            cwd=args.output, env=env, log_path=args.output / "observer.log",
            result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
            timeout=30, driver_prefix=args.native_job_prefix)
        evidence = json.loads((args.output / "capture/result.json").read_text())
        native = json.loads((args.output / "native-job.json").read_text())
        exits = [row for row in native["native_target_exits"] if Path(row["executable"]).resolve() == executable]
        if (not report["process"]["passed"] or evidence["exit_code"] != 0 or evidence["timed_out"]
                or evidence["exception_limit_reached"] or len(exits) != 1 or exits[0]["raw_exit"] != 0):
            raise ContractError("Installed API fixture did not produce exactly one successful observed native exit")
        loaded = {}
        for row in evidence["modules"]:
            path = Path(row["path"].removeprefix("\\\\?\\")).resolve()
            loaded[path.name.lower()] = {"path": str(path), "sha256": digest(path)}
        for name, (path, sha) in expected.items():
            row = loaded.get(name)
            if row is None or Path(row["path"]) != path or row["sha256"] != sha:
                raise ContractError(f"Installed API fixture did not load the exact private input: {name}")
        text = (args.output / "capture/stdout.bin").read_bytes() + (args.output / "capture/stderr.bin").read_bytes()
        if profile["marker"] is not None and profile["marker"] not in text:
            raise ContractError("The unchanged upstream API fixture did not report its assertions passed")
        verify_tree(relocated, args.tested_result)
        report.update({"status": "installed-native-cmake-api-and-dll-closure-passed",
                       "loaded_modules": loaded, "native_exit": exits[0], "stage_files": inventory(relocated)})
    finally:
        try:
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("Installed API input or recipe changed during execution")
            verify_tree(stage, args.tested_result)
            verify_build_files(build, original["compiled_files"])
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
