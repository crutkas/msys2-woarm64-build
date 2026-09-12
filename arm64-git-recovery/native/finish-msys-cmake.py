"""Run the complete observed CMocka replay and install existing binaries without rebuilding."""

import argparse
import json
import os
from pathlib import Path
import shutil

from bounded_process import run
from cmake_test_replay import cases, test_results, verify_build_files
from compiler_tools import require_msys_ucontext_receipt
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree


def validate_test_set(expected, actual):
    if len(actual) != len(set(actual)) or set(actual) != set(expected) or len(actual) != len(expected):
        raise ContractError("CTest did not execute exactly the complete original upstream test set")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("replay", "manifest", "prefix", "compiler-receipt", "source-manifest",
                 "native-job-prefix", "cmake", "pwsh", "artifact-gate", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Exact prepared replay manifest identity")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt" or args.output.exists() or digest(args.manifest) != args.sha256:
        raise ContractError("Windows, a fresh output and the exact prepared test replay are required")
    driver_manifest = verify_driver(args.native_job_prefix)
    verify_tree(args.replay, args.manifest)
    replay = json.loads(args.manifest.read_text(encoding="utf-8"))
    if replay.get("status") != "cmocka-test-replay-prepared-not-executed":
        raise ContractError("Expected a prepared, unexecuted CMocka test replay")
    original_path = Path(replay["build_result"]["path"])
    if digest(original_path) != replay["build_result"]["sha256"]:
        raise ContractError("Original build-only result changed")
    original = json.loads(original_path.read_text(encoding="utf-8"))
    if (original.get("status") != "native-msys-cmake-built-not-tested" or
            original.get("package") != "cmocka" or
            original["compiler_receipt_sha256"] != digest(args.compiler_receipt) or
            original["source_manifest_sha256"] != digest(args.source_manifest) or
            original["tools"].get(str(args.cmake)) != digest(args.cmake)):
        raise ContractError("CMocka completion requires the exact original compiler, source and native CMake")
    compiler = json.loads(args.compiler_receipt.read_text(encoding="utf-8"))
    require_msys_ucontext_receipt(compiler)
    if Path(compiler["prefix"]).resolve() != args.prefix:
        raise ContractError("The compiler receipt identifies a different runtime prefix")
    verify_tree(args.prefix, args.compiler_receipt)
    build, source = original_path.parent / "build", original_path.parent / "source"
    verify_tree(source, args.source_manifest)
    verify_build_files(build, original["compiled_files"])
    ctest = Path(replay["ctest"]["path"])
    if digest(ctest) != replay["ctest"]["sha256"]:
        raise ContractError("Native CTest changed")
    expected = [test["name"] for test in cases(json.loads((args.replay / "original-discovery.json").read_text()))]
    immutable = {str(path): digest(path) for path in
                 (args.manifest, original_path, args.compiler_receipt, args.source_manifest,
                  driver_manifest, args.cmake, ctest, args.artifact_gate, Path(__file__),
                  Path(__file__).with_name("cmake_test_replay.py"), Path(__file__).with_name("native_job_runner.py"),
                  args.replay / "CTestTestfile.cmake", args.replay / "original-discovery.json",
                  args.replay / "replay-discovery.json")}
    args.output.mkdir(parents=True)
    for name in ("home", "temp", "native-exits"):
        (args.output / name).mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (build / "src", args.prefix / "bin", args.cmake.parent,
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "TMPDIR": str(args.output / "temp"), "WOARM64_NATIVE_TEST_ROOT": str(build)})
    stage = args.output / "stage"
    report = {"schema": 1, "status": "failed", "package": "cmocka",
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "source_manifest_sha256": digest(args.source_manifest), "input_identities": immutable,
              "scope": "Complete observed upstream CMocka test replay and private installation; no compilation",
              "commands": []}

    def command(name, argv):
        with (args.output / f"{name}.log").open("xb") as log:
            process = run(argv, cwd=args.output, env=env, log=log, timeout=300)
        report["commands"].append({"name": name, "command": list(map(str, argv)), "process": process})
        if not process["passed"]:
            raise ContractError(f"CMocka completion failed: {name}")

    try:
        junit = args.output / "ctest.xml"
        report["test_process"] = run_observed(
            [ctest, "--test-dir", args.replay, "--parallel", str(args.jobs), "--output-on-failure",
             "--output-junit", junit], cwd=args.output, env=env,
            log_path=args.output / "ctest.log", result_path=args.output / "ctest.native-job.json",
            relay_records=args.output / "native-exits", timeout=600, driver_prefix=args.native_job_prefix)
        if not report["test_process"]["passed"]:
            raise ContractError("CMocka native child observation or upstream test execution failed")
        report["upstream_tests"] = test_results(junit)
        validate_test_set(expected, report["upstream_tests"])
        command("install", [args.cmake, "--install", build, "--prefix", (stage / "usr").as_posix()])
        installed = (build / "install_manifest.txt").read_text().splitlines()
        if not installed or any(not Path(path).resolve().is_relative_to(stage) for path in installed):
            raise ContractError("CMocka install manifest contains a path outside the new private stage")
        license_dir = stage / "usr/share/licenses/cmocka"
        license_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "COPYING", license_dir / "COPYING")
        files = inventory(stage)
        if any(name not in files for name in ("usr/bin/msys-cmocka-0.dll", "usr/include/cmocka.h",
                                              "usr/lib/libcmocka.dll.a")):
            raise ContractError("CMocka native shared-library/development payload is incomplete")
        pe_report = args.output / "native-pe.json"
        command("native-pe", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                              "-Root", stage, "-ReportPath", pe_report])
        gate = json.loads(pe_report.read_text())
        if gate.get("Passed") is not True or not gate.get("CandidateCount"):
            raise ContractError("CMocka installed native PE gate failed or was empty")
        report.update({"status": "native-msys-cmake-built-tested", "files": files,
                       "pending": ["Installed native API/loaded-DLL closure", "Package admission"]})
    finally:
        try:
            if any(digest(path) != sha for path, sha in immutable.items()):
                raise ContractError("CMocka completion input or recipe changed")
            verify_tree(source, args.source_manifest)
            verify_tree(args.prefix, args.compiler_receipt)
            verify_driver(args.native_job_prefix)
            verify_build_files(build, original["compiled_files"], allowed_new=("install_manifest.txt",))
            report["inputs_unchanged"] = True
        except (ContractError, OSError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            with (args.output / "result.json").open("x", encoding="utf-8", newline="\n") as out:
                json.dump(report, out, indent=2)
                out.write("\n")
    print(report["status"])


if __name__ == "__main__":
    main()
