"""Build MSYS LP64 CMake dependencies with native Windows drivers and fail-closed test coverage."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from bounded_process import run
from cmake_build_inputs import cmocka_build_input, require_build_tree_mode
from cmake_test_replay import test_results
from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_msys_jmp_headers, verify_support
from fido_build_inputs import copy_windows_imports, verify_windows_imports, verify_inputs as verify_fido_inputs
from native_job_runner import run_observed, verify_driver
from openssl_contracts import validate_abi
from pe_exports import export_names
from sources import ContractError, digest, inventory, verify_tree

PROFILES = {
    "libfido2": {"version": "1.17.0", "source_subdir": ".", "license": "LICENSE",
                 "flags": {"BUILD_SHARED_LIBS": "ON", "BUILD_STATIC_LIBS": "ON", "BUILD_TESTS": "ON",
                           "BUILD_EXAMPLES": "ON", "BUILD_TOOLS": "ON", "BUILD_MANPAGES": "ON",
                           "USE_WINHELLO": "ON"},
                 "headers": ["usr/include/fido.h"], "imports": ["usr/lib/libfido2.dll.a"]},
    "cmocka": {"version": "1.1.8", "source_subdir": ".", "license": "COPYING",
               "flags": {"BUILD_SHARED_LIBS": "ON", "UNIT_TESTING": "ON", "WITH_CMOCKERY_SUPPORT": "ON",
                         "CMOCKA_SOURCE_COMPILE_DATABASE": "OFF"},
               "headers": ["usr/include/cmocka.h"], "imports": ["usr/lib/libcmocka.dll.a"]},
    "libcbor": {"version": "0.14.0", "source_subdir": ".", "license": "LICENSE.md",
                "flags": {"BUILD_SHARED_LIBS": "ON", "WITH_TESTS": "ON",
                          "WITH_EXAMPLES": "OFF", "CMAKE_POLICY_VERSION_MINIMUM": "3.5"},
                "headers": ["usr/include/cbor.h"], "imports": ["usr/lib/libcbor.dll.a"],
                "required_exports": {"src/msys-cbor-0.14.dll": ["cbor_set_allocs"]}},
    "zstd": {"version": "1.5.7", "source_subdir": "build/cmake", "license": "LICENSE",
             "flags": {"ZSTD_BUILD_SHARED": "ON", "ZSTD_BUILD_STATIC": "ON", "ZSTD_BUILD_TESTS": "ON",
                       "ZSTD_BUILD_PROGRAMS": "ON", "ZSTD_PROGRAMS_LINK_SHARED": "ON",
                       "ZSTD_MULTITHREAD_SUPPORT": "ON"},
             "headers": ["usr/include/zstd.h"], "imports": ["usr/lib/libzstd.dll.a"]},
}


def validate_dependency(package, files):
    if package == "libcbor":
        required = ("usr/include/cmocka.h", "usr/lib/libcmocka.dll.a")
        if any(name not in files for name in required):
            raise ContractError("CBOR upstream tests require the real MSYS CMocka development stage")
        if not any(name.startswith("usr/bin/msys-cmocka") and name.endswith(".dll") for name in files):
            raise ContractError("CMocka dependency must contain its real MSYS shared library")


def verify_bootstrap(package, prefix, manifest):
    if package != "zstd":
        if prefix is not None or manifest is not None:
            raise ContractError("This CMake profile does not require foreign shell drivers")
        return None
    if prefix is None or manifest is None:
        raise ContractError("Zstd requires a receipt-bound private shell bootstrap for its upstream CLI tests")
    prefix, manifest = Path(prefix).resolve(), Path(manifest).resolve()
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if (record.get("status") != "private-emulated-build-input-copy" or
            Path(record.get("prefix", "")).resolve() != prefix or
            not isinstance(record.get("source_handoff_sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", record["source_handoff_sha256"])):
        raise ContractError("Zstd shell drivers must come from the verified private bootstrap copy")
    verify_tree(prefix, manifest)
    for name in ("bash", "sh", "uname"):
        if f"usr/bin/{name}.exe" not in record["files"]:
            raise ContractError(f"Required private Zstd test driver is missing: {name}")
    return {"prefix": str(prefix), "manifest": str(manifest), "sha256": digest(manifest),
            "scope": "Explicit private x64 emulated shell/CLI test drivers; not native build-tool proof"}


def execute_stage(name, argv, *, output, env, native_job_prefix):
    if name == "ctest":
        return run_observed(
            argv, cwd=output, env=env, timeout=3600,
            log_path=output / "ctest.log", result_path=output / "ctest.native-job.json",
            relay_records=output / "native-exits", driver_prefix=native_job_prefix)
    with (output / f"{name}.log").open("xb") as log:
        return run(argv, cwd=output, env=env, log=log, timeout=3600)


def require_test_observer(build_only, prefix):
    if build_only:
        if prefix is not None:
            raise ContractError("Build-only mode does not consume or qualify a test observer")
        return None
    if prefix is None:
        raise ContractError("Full CMake test/install mode requires the qualified native child observer")
    return verify_driver(prefix)


def require_fido_mode(package, build_only, manifest, sha256, stage):
    if package == "libfido2":
        if not build_only or manifest is None or sha256 is None or stage is not None:
            raise ContractError("FIDO2 is currently build-only with exact metadata; device/authentication/tests/install require separate authority")
        return True
    if manifest is not None or sha256 is not None:
        raise ContractError("FIDO dependency metadata is valid only for the FIDO2 profile")
    return False


def verify_fido_features(commands):
    windows = [entry for entry in commands if Path(entry["file"]).name in ("winhello.c", "hid_win.c")]
    if {Path(entry["file"]).name for entry in windows} != {"winhello.c", "hid_win.c"}:
        raise ContractError("FIDO2 Windows Hello/HID sources were not selected")
    for entry in windows:
        command = entry["command"]
        if not re.search(r"(?:^|\s)-DUSE_WINHELLO(?:\s|$)", command):
            raise ContractError("FIDO2 Windows Hello compile definition is missing")
        if re.search(r"(?:^|\s)-D(?:_WIN32|__MINGW32__)(?:=|\s|$)", command):
            raise ContractError("FIDO2 may not substitute a global MinGW/Windows compiler ABI macro")
    return {"windows_sources": sorted({Path(entry["file"]).name for entry in windows}),
            "scope": "Actual generated compile commands, not device execution or authentication support qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PROFILES, required=True)
    for name in ("source", "manifest", "prefix", "compiler-receipt", "cmake", "ninja",
                 "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--dependency-stage", type=Path)
    parser.add_argument("--dependency-manifest", type=Path)
    parser.add_argument("--cmocka-build-result", type=Path)
    parser.add_argument("--cmocka-source-manifest", type=Path)
    parser.add_argument("--cmocka-build-sha256")
    parser.add_argument("--fido-build-inputs", type=Path)
    parser.add_argument("--fido-build-inputs-sha256")
    parser.add_argument("--windows-import-handoff", type=Path)
    parser.add_argument("--windows-import-handoff-sha256")
    parser.add_argument("--bootstrap", type=Path, help="Zstd shell-test drivers only, never an installed/global prefix")
    parser.add_argument("--bootstrap-manifest", type=Path, help="Exact private bootstrap copy receipt")
    parser.add_argument("--native-job-prefix", type=Path)
    parser.add_argument("--build-only", action="store_true",
                        help="Stop after compilation and raw PE inventory; no CTest, installation, or admission")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a fresh CMake dependency root are required")
    if (args.dependency_stage is None) != (args.dependency_manifest is None):
        raise ContractError("Dependency payload and full manifest must be supplied together")
    use_build_tree = require_build_tree_mode(
        args.package, args.build_only, args.dependency_stage, args.cmocka_build_result,
        args.cmocka_source_manifest, args.cmocka_build_sha256)
    use_fido_inputs = require_fido_mode(
        args.package, args.build_only, args.fido_build_inputs, args.fido_build_inputs_sha256, args.dependency_stage)
    if ((args.windows_import_handoff is None) != (args.windows_import_handoff_sha256 is None) or
            (args.windows_import_handoff is not None and not use_fido_inputs)):
        raise ContractError("The sealed Windows import overlay is an explicit paired FIDO-only input")
    job_manifest = require_test_observer(args.build_only, args.native_job_prefix)
    bootstrap = verify_bootstrap(args.package, args.bootstrap, args.bootstrap_manifest)
    verify_tree(args.source, args.manifest)
    record = json.loads(args.manifest.read_text())
    profile = PROFILES[args.package]
    if record["source"]["id"] != args.package or record["source"]["version"] != profile["version"]:
        raise ContractError("CMake dependency differs from the pinned source recipe")
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    if (Path(producer["prefix"]).resolve() != args.prefix.resolve() or
            producer["source_target"]["Triple"] != "aarch64-pc-cygwin"):
        raise ContractError("CMake dependency requires the actual coherent MSYS producer")
    dependencies = {}
    build_dependency = None
    fido_inputs = None
    if use_fido_inputs:
        if digest(args.fido_build_inputs) != args.fido_build_inputs_sha256:
            raise ContractError("FIDO input metadata identity changed")
        fido_inputs = verify_fido_inputs(args.fido_build_inputs, args.compiler_receipt)
    if use_build_tree:
        build_dependency = cmocka_build_input(
            args.cmocka_build_result, args.cmocka_source_manifest, args.compiler_receipt, args.cmocka_build_sha256)
    if args.dependency_stage:
        verify_tree(args.dependency_stage, args.dependency_manifest)
        dependencies = inventory(args.dependency_stage)
    if not use_build_tree and not use_fido_inputs:
        validate_dependency(args.package, dependencies)
    args.output.mkdir(parents=True)
    overlay_ancestors = ([Path(item["path"]) for item in fido_inputs["spec"].get("compiler_ancestors", [])]
                         if fido_inputs else [])
    windows_imports = (copy_windows_imports(args.windows_import_handoff, args.windows_import_handoff_sha256,
                                          args.compiler_receipt, args.output / "windows-import-overlay",
                                          compiler_ancestors=overlay_ancestors)
                       if args.windows_import_handoff else None)
    for name in ("temp", "home", "native-exits"):
        (args.output / name).mkdir()
    source, build, stage = (args.output / name for name in ("source", "build", "stage"))
    shutil.copytree(args.source, source)
    verify_tree(source, args.manifest)
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.prefix / "bin", args.cmake.parent, args.ninja.parent,
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "TMPDIR": str(args.output / "temp"),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output),
                "WOARM64_NATIVE_EXIT_DIR": str(args.output / "native-exits"),
                "CMAKE_BUILD_PARALLEL_LEVEL": str(args.jobs)})
    if bootstrap:
        env["PATH"] += os.pathsep + str(args.bootstrap / "usr/bin")
    if fido_inputs:
        env.update(fido_inputs["environment"])
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    macros_result = subprocess.run([str(compiler), "-dM", "-E", "-x", "c", "-"], input=b"",
                                   env=env, capture_output=True, check=True, timeout=30)
    macros = {parts[1]: parts[2] for line in macros_result.stdout.decode().splitlines()
              if len(parts := line.split(maxsplit=2)) == 3 and parts[0] == "#define"}
    validate_abi("Cygwin-aarch64", macros)
    header_guard = verify_msys_jmp_headers(compiler, env)
    ctest = args.cmake.with_name("ctest.exe")
    tools = {str(path): digest(path) for path in (args.cmake, ctest, args.ninja)}
    recipe_files = {str(path): digest(path) for path in
                    (Path(__file__), Path(__file__).with_name("fido_build_inputs.py"),
                     Path(__file__).with_name("compiler_tools.py"), Path(__file__).with_name("bounded_process.py"),
                     Path(__file__).with_name("cmake_build_inputs.py"), Path(__file__).with_name("sources.py"))}
    report = {"status": "failed", "package": args.package, "profile": profile, "commands": [],
              "source_manifest_sha256": digest(args.manifest),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "native_observer_manifest_sha256": digest(job_manifest) if job_manifest else None,
              "dependency_manifest_sha256": digest(args.dependency_manifest) if args.dependency_manifest else None,
              "uninstalled_build_dependency": build_dependency,
              "fido_build_inputs": {"manifest_sha256": args.fido_build_inputs_sha256,
                                    "inputs": fido_inputs["inputs"]} if fido_inputs else None,
              "windows_import_overlay": windows_imports,
              "recipe_files": recipe_files,
              "tools": tools, "support": support, "header_guard": header_guard,
              "bootstrap_test_drivers": bootstrap,
              "scope": "Native Windows CMake/Ninja/GCC; MSYS LP64 target; not package/provides admission"}

    def command(name, argv, environment=env):
        result = execute_stage(name, argv, output=args.output, env=environment,
                               native_job_prefix=args.native_job_prefix)
        report["commands"].append({"name": name, "argv": list(map(str, argv)), "process": result})
        if not result["passed"]:
            raise ContractError(f"Native MSYS CMake stage failed: {name}")

    def pe_gate(name, root):
        destination = args.output / f"{name}.json"
        command(name, [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                       "-Root", root, "-ReportPath", destination])
        result = json.loads(destination.read_text())
        if result.get("Passed") is not True or not result.get("CandidateCount"):
            raise ContractError("Native driver or output PE gate was empty or failed")

    try:
        pe_gate("cmake-native", args.cmake.parent)
        pe_gate("ninja-native", args.ninja.parent)
        flags = {**profile["flags"], "CMAKE_SYSTEM_NAME": "MSYS", "CMAKE_SYSTEM_PROCESSOR": "aarch64",
                 "CMAKE_BUILD_TYPE": "Release", "CMAKE_INSTALL_PREFIX": "/usr",
                 "CMAKE_STAGING_PREFIX": (stage / "usr").as_posix(),
                 "CMAKE_MAKE_PROGRAM": args.ninja.as_posix(),
                 "CMAKE_C_COMPILER": compiler.as_posix(),
                 "CMAKE_CXX_COMPILER": (args.prefix / "bin/g++.exe").as_posix(),
                 "CMAKE_AR": (args.prefix / "bin/ar.exe").as_posix(),
                 "CMAKE_RANLIB": (args.prefix / "bin/ranlib.exe").as_posix(),
                 "CMAKE_RC_COMPILER": (args.prefix / "bin/windres.exe").as_posix(),
                 "CMAKE_FIND_ROOT_PATH_MODE_PROGRAM": "NEVER",
                 "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY": "ONLY",
                 "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE": "ONLY",
                 "CMAKE_FIND_ROOT_PATH_MODE_PACKAGE": "ONLY"}
        roots = [args.prefix / "aarch64-pc-cygwin"]
        if args.dependency_stage:
            roots.append(args.dependency_stage / "usr")
            flags["CMAKE_PREFIX_PATH"] = (args.dependency_stage / "usr").as_posix()
        if build_dependency:
            flags.update(build_dependency["cmake_flags"])
        if fido_inputs:
            flags.update(fido_inputs["cmake_flags"])
        if windows_imports:
            linker_path = "-L" + Path(windows_imports["library_directory"]).as_posix()
            for kind in ("EXE", "SHARED", "MODULE"):
                flags[f"CMAKE_{kind}_LINKER_FLAGS"] = linker_path
        flags["CMAKE_FIND_ROOT_PATH"] = ";".join(path.as_posix() for path in roots)
        command("configure", [args.cmake, "-S", source / profile["source_subdir"], "-B", build, "-G", "Ninja",
                              *[f"-D{name}={value}" for name, value in flags.items()]])
        if fido_inputs:
            report["fido_feature_selection"] = verify_fido_features(
                json.loads((build / "compile_commands.json").read_text(encoding="utf-8")))
        command("build", [args.cmake, "--build", build, "--parallel", str(args.jobs)])
        pe_gate("build-native", build)
        dlls = sorted(path for path in build.rglob("*.dll") if path.is_file())
        if not dlls:
            raise ContractError("The requested MSYS shared-library build produced no DLL")
        report["required_exports"] = {}
        for name, required in profile.get("required_exports", {}).items():
            path = build / name
            actual = export_names(path.read_bytes())
            if not set(required).issubset(actual):
                raise ContractError(f"Required native library API is missing from {name}: {required}")
            report["required_exports"][name] = {"sha256": digest(path), "present": required}
        if args.build_only:
            report.update({"status": "native-msys-cmake-built-not-tested",
                           "compiled_files": inventory(build),
                           "pending": ["Qualified native child observer", "Complete upstream CTest suite",
                                       "Installation", "Installed native API/loaded-DLL closure", "Package admission"]})
            return report["status"]
        runtime_dirs = sorted({path.parent for path in dlls})
        if args.dependency_stage:
            runtime_dirs.append(args.dependency_stage / "usr/bin")
        runtime_env = {**env, "PATH": os.pathsep.join(map(str, runtime_dirs)) + os.pathsep + env["PATH"]}
        junit = args.output / "ctest.xml"
        command("ctest", [ctest, "--test-dir", build, "--parallel", str(args.jobs),
                           "--output-on-failure", "--output-junit", junit], runtime_env)
        report["upstream_tests"] = test_results(junit)
        command("install", [args.cmake, "--install", build])
        license_dir = stage / "usr/share/licenses" / args.package
        license_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / profile["license"], license_dir / Path(profile["license"]).name)
        files = inventory(stage)
        if any(name not in files for name in profile["headers"] + profile["imports"]):
            raise ContractError("Requested MSYS development payload is incomplete")
        if not any(name.startswith("usr/bin/msys-") and name.endswith(".dll") for name in files):
            raise ContractError("The installed target is not a real MSYS DLL payload")
        pe_gate("stage-native", stage)
        report.update({"status": "native-msys-cmake-built-tested", "files": files,
                       "pending": ["Installed native API/loaded-DLL closure", "Package admission"]})
    finally:
        try:
            for path, field in ((args.manifest, "source_manifest_sha256"),
                                (args.compiler_receipt, "compiler_receipt_sha256"),
                                (args.dependency_manifest, "dependency_manifest_sha256"),
                                (job_manifest, "native_observer_manifest_sha256")):
                if path is not None and digest(path) != report[field]:
                    raise ContractError(f"Native CMake input receipt changed: {field}")
            verify_tree(args.source, args.manifest)
            verify_tree(args.prefix, args.compiler_receipt)
            verify_support(support, compiler, args.prefix, env)
            if args.native_job_prefix is not None:
                verify_driver(args.native_job_prefix)
            if windows_imports:
                verify_windows_imports(windows_imports)
            if verify_bootstrap(args.package, args.bootstrap, args.bootstrap_manifest) != bootstrap:
                raise ContractError("Private CMake shell-test drivers changed")
            if args.dependency_stage:
                verify_tree(args.dependency_stage, args.dependency_manifest)
            if build_dependency and cmocka_build_input(
                    args.cmocka_build_result, args.cmocka_source_manifest, args.compiler_receipt,
                    args.cmocka_build_sha256) != build_dependency:
                raise ContractError("Uninstalled CMocka input changed during compilation")
            if fido_inputs and (digest(args.fido_build_inputs) != args.fido_build_inputs_sha256 or
                                verify_fido_inputs(args.fido_build_inputs, args.compiler_receipt) != fido_inputs):
                raise ContractError("FIDO dependency metadata or actual input bytes changed")
            if any(digest(path) != sha for path, sha in tools.items()):
                raise ContractError("Native CMake/Ninja drivers changed")
            if any(digest(path) != sha for path, sha in recipe_files.items()):
                raise ContractError("Native CMake build recipe changed during execution")
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
    build_status = main()
    if build_status is not None:
        print(build_status)
