"""Run complete existing CTest suites in a private copy, never in a frozen build tree."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from bounded_process import run
from cmake_test_replay import (cases, render, repair_cmocka_path, repair_cmocka_wrap_environment,
                               semantics, test_results, verify_build_files)
from compiler_tools import require_msys_ucontext_receipt
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree

COUNTS = {"cmocka": 49, "libcbor": 28, "libfido2": 8}
FIDO_TESTS = {f"regress_{name}" for name in ("assert", "cred", "dev", "eddsa", "es256", "es384", "rs256", "compress")}


def relocate(text, original, private):
    for old, new in ((str(original), str(private)), (original.as_posix(), private.as_posix())):
        text = re.sub(re.escape(old) + r'(?=$|[/\\;"\s])', lambda _: new, text, flags=re.IGNORECASE)
    return text


def relocate_metadata(build, original, private):
    records = {}
    for path in build.rglob("*"):
        if not path.is_file() or (path.suffix != ".cmake" and path.name not in
                                  ("CMakeCache.txt", "DartConfiguration.tcl", "InstallScripts.json")):
            continue
        before = path.read_text(encoding="utf-8")
        after = relocate(before, original, private)
        if before != after:
            old_sha = digest(path)
            path.write_text(after, encoding="utf-8", newline="\n")
            records[path.relative_to(build).as_posix()] = {"original_sha256": old_sha, "private_sha256": digest(path)}
    return records


def validate_cases(discovery, package, build):
    tests = cases(discovery)
    if len(tests) != COUNTS[package]:
        raise ContractError("Private replay must preserve the complete pinned upstream test set")
    if package == "libfido2" and {test["name"] for test in tests} != FIDO_TESTS:
        raise ContractError("Only the complete reviewed FIDO synthetic/mock regression suite is authorized")
    for test in tests:
        executable = Path(test["command"][0]).resolve()
        cwd = next(prop["value"] for prop in test["properties"] if prop["name"] == "WORKING_DIRECTORY")
        if (not executable.is_relative_to(build) or not executable.is_file() or executable.suffix != ".exe"
                or not Path(cwd).resolve().is_relative_to(build)):
            raise ContractError("CTest target and working directory must be inside the private build copy")
    return [test["name"] for test in tests]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build-result", "source-manifest", "compiler-receipt", "native-job-prefix",
                 "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--prepare-only", action="store_true", help="Verify private CTest discovery without executing targets or installing")
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt" or args.output.exists() or digest(args.build_result) != args.sha256:
        raise ContractError("Private replay requires Windows, a fresh root and exact build-result identity")
    original = json.loads(args.build_result.read_text())
    package = original["package"]
    if (package not in COUNTS or original.get("status") != "native-msys-cmake-built-not-tested"
            or original.get("inputs_unchanged") is not True
            or original["compiler_receipt_sha256"] != digest(args.compiler_receipt)
            or original["source_manifest_sha256"] != digest(args.source_manifest)):
        raise ContractError("Only exact coherent built-only CMocka/CBOR/FIDO inputs are supported")
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    prefix = Path(producer["prefix"])
    verify_tree(prefix, args.compiler_receipt)
    old_root = args.build_result.parent
    if args.output.is_relative_to(old_root) or old_root.is_relative_to(args.output):
        raise ContractError("Private replay must not overlap its frozen input root")
    verify_tree(old_root / "source", args.source_manifest)
    verify_build_files(old_root / "build", original["compiled_files"])
    old_build = inventory(old_root / "build")
    observer_manifest = verify_driver(args.native_job_prefix)
    cmake = next(Path(path) for path in original["tools"] if Path(path).name == "cmake.exe")
    ctest = cmake.with_name("ctest.exe")
    for tool in (cmake, ctest):
        if digest(tool) != original["tools"][str(tool)]:
            raise ContractError("Original native CMake/CTest identity changed")
    immutable = {str(path): digest(path) for path in
                 (args.build_result, args.source_manifest, args.compiler_receipt, observer_manifest,
                  cmake, ctest, args.artifact_gate, Path(__file__), Path(__file__).with_name("cmake_test_replay.py"),
                  Path(__file__).with_name("native_job_runner.py"))}
    args.output.mkdir(parents=True)
    source, build, replay, runtime, stage = (args.output / name for name in ("source", "build", "replay", "runtime", "stage"))
    report = {"schema": 1, "status": "failed", "package": package,
              "original_build": {"path": str(args.build_result), "sha256": args.sha256},
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "source_manifest_sha256": digest(args.source_manifest),
              "input_identities": immutable, "commands": [],
              "scope": "Complete upstream CTest, private copied binaries and private installation; no original-root writes or compilation",
              "pending": ["Installed native API/loaded-DLL closure", "Package admission"]}
    try:
        shutil.copytree(old_root / "source", source)
        shutil.copytree(old_root / "build", build)
        if inventory(build) != old_build:
            raise ContractError("Frozen build changed while copying")
        for name in ("replay", "runtime", "home", "temp", "native-exits"):
            (args.output / name).mkdir()
        report["metadata_relocations"] = relocate_metadata(build, old_root, args.output)
        # Only receipt-bound DLLs are copied; build/test tools stay read-only inputs.
        dependencies = [{"path": str(prefix / "bin/msys-2.0.dll"),
                         "sha256": producer["files"]["bin/msys-2.0.dll"]["sha256"]}]
        if package == "libcbor":
            dependencies.append(original["uninstalled_build_dependency"]["files"]["runtime_library"])
        if package == "libfido2":
            dependencies.extend(row["dll"] for row in original["fido_build_inputs"]["inputs"]["modules"].values())
            report["fido_scope"] = "All eight pinned synthetic/mock regression fixtures; no real devices, Windows Hello, accounts or authenticators"
        for item in dependencies:
            path = Path(item["path"])
            if digest(path) != item["sha256"] or (runtime / path.name).exists():
                raise ContractError("Runtime input changed or has a duplicate DLL name")
            shutil.copyfile(path, runtime / path.name)
        report["runtime_inputs"] = dependencies
        runtime_files = inventory(runtime)
        runtime_dirs = sorted({path.parent for path in build.rglob("*.dll")})
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
        env.update({"PATH": os.pathsep.join(map(str, (*runtime_dirs, runtime, cmake.parent,
                                                     Path(os.environ["SystemRoot"]) / "System32"))),
                    "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                    "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                    "TMPDIR": str(args.output / "temp"), "WOARM64_NATIVE_TEST_ROOT": str(args.output),
                    "WOARM64_NATIVE_EXIT_DIR": str(args.output / "native-exits"),
                    "WOARM64_NATIVE_ARG_CONVERSION": "none"})

        def discover(root, label):
            command = [str(ctest), "--test-dir", str(root), "--show-only=json-v1"]
            result = subprocess.run(command, cwd=args.output, env=env, capture_output=True, timeout=30)
            (args.output / f"{label}.json").write_bytes(result.stdout)
            (args.output / f"{label}.stderr").write_bytes(result.stderr)
            if result.returncode:
                raise ContractError("Private CTest discovery failed")
            return json.loads(result.stdout)

        discovered = discover(build, "copied-discovery")
        report["repaired_cmocka_paths"] = 0
        if package == "cmocka":
            discovered, report["repaired_cmocka_paths"] = repair_cmocka_path(discovered, build)
            for test in cases(discovered):
                for prop in test["properties"]:
                    if prop["name"] == "ENVIRONMENT":
                        prop["value"] = [setting.replace(str(prefix / "bin"), str(runtime))
                                         if setting.startswith("PATH=") else setting for setting in prop["value"]]
            discovered = repair_cmocka_wrap_environment(discovered)
            report["repaired_cmocka_wrap_environment"] = {
                "test": "waiter_test_wrap", "source": "simple_test",
                "reason": "Upstream DLL_PATH_ENV is function-local; wrapped example inherited an explicit empty PATH"}
        expected = validate_cases(discovered, package, build)
        (replay / "CTestTestfile.cmake").write_text(render(discovered), encoding="utf-8", newline="\n")
        if semantics(discover(replay, "replay-discovery")) != semantics(discovered):
            raise ContractError("Private replay dropped or changed an upstream test property")
        report["upstream_test_names"] = expected
        if args.prepare_only:
            report.update({"status": "private-msys-cmake-replay-prepared-not-executed",
                           "scope": "Private copied source/binaries and complete CTest discovery roundtrip only; no execution/install/admission",
                           "prepared_build_files": inventory(build), "prepared_replay_files": inventory(replay)})
            return
        before_tests = inventory(build)
        junit = args.output / "ctest.xml"
        report["test_process"] = run_observed(
            [ctest, "--test-dir", replay, "--parallel", str(args.jobs), "--timeout", "120",
             "--output-on-failure", "--output-junit", junit],
            cwd=args.output, env=env, log_path=args.output / "ctest.log",
            result_path=args.output / "ctest.native-job.json", relay_records=args.output / "native-exits",
            timeout=600, driver_prefix=args.native_job_prefix)
        if not report["test_process"]["passed"]:
            raise ContractError("Complete upstream suite or native generation/exit observation failed")
        actual = test_results(junit)
        if len(actual) != len(expected) or set(actual) != set(expected):
            raise ContractError("Private CTest did not execute the exact complete upstream suite")
        report["upstream_tests"] = actual
        verify_build_files(build, before_tests)

        def command(name, argv):
            with (args.output / f"{name}.log").open("xb") as log:
                result = run(argv, cwd=args.output, env=env, log=log, timeout=300)
            report["commands"].append({"name": name, "argv": list(map(str, argv)), "process": result})
            if not result["passed"]:
                raise ContractError(f"Private CMake completion failed: {name}")

        command("install", [cmake, "--install", build, "--prefix", (stage / "usr").as_posix()])
        installed = (build / "install_manifest.txt").read_text().splitlines()
        if not installed or any(not Path(path).resolve().is_relative_to(stage) for path in installed):
            raise ContractError("Private CMake install escaped the owned stage")
        license_dir = stage / "usr/share/licenses" / package
        license_dir.mkdir(parents=True)
        shutil.copyfile(source / original["profile"]["license"], license_dir / Path(original["profile"]["license"]).name)
        files = inventory(stage)
        if any(name not in files for name in original["profile"]["headers"] + original["profile"]["imports"]):
            raise ContractError("Installed private development payload is incomplete")
        command("native-pe", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                              "-Root", stage, "-ReportPath", args.output / "native-pe.json"])
        gate = json.loads((args.output / "native-pe.json").read_text())
        if gate.get("Passed") is not True or not gate.get("CandidateCount"):
            raise ContractError("Installed native payload PE gate failed or was empty")
        verify_build_files(build, before_tests, allowed_new=("install_manifest.txt",))
        if inventory(runtime) != runtime_files:
            raise ContractError("Private dependency DLLs changed during tests")
        report.update({"status": "native-msys-cmake-built-tested", "files": files})
    finally:
        try:
            if any(digest(path) != sha for path, sha in immutable.items()):
                raise ContractError("Private replay immutable input changed")
            if inventory(old_root / "build") != old_build:
                raise ContractError("Frozen original build was modified")
            verify_tree(old_root / "source", args.source_manifest)
            verify_tree(prefix, args.compiler_receipt)
            verify_driver(args.native_job_prefix)
            report["inputs_unchanged"] = True
        except (ContractError, OSError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
