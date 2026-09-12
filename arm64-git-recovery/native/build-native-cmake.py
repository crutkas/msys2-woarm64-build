"""Build and test pinned native Git library candidates using ARM64 CMake/Ninja."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


RECIPES = {
    "zlib": {
        "version": "1.3.2", "variants": ["combined"], "license": "LICENSE",
        "flags": {"ZLIB_BUILD_TESTING": "ON", "ZLIB_BUILD_STATIC": "ON",
                  "ZLIB_BUILD_SHARED": "ON", "ZLIB_INSTALL": "ON"},
        "scope": "Native upstream static/shared zlib libraries and tests; excludes separately packaged minizip"
    },
    "expat": {
        "version": "2.8.4", "variants": ["static", "shared"], "license": "COPYING",
        "flags": {"EXPAT_BUILD_TESTS": "ON", "EXPAT_BUILD_EXAMPLES": "ON",
                  "EXPAT_BUILD_TOOLS": "ON", "EXPAT_BUILD_DOCS": "OFF"},
        "scope": "Native static/shared Expat libraries, examples, xmlwf and upstream tests; man-page generation excluded"
    },
    "pcre2": {
        "version": "10.48", "variants": ["combined"], "license": "LICENCE.md",
        "flags": {"BUILD_SHARED_LIBS": "ON", "BUILD_STATIC_LIBS": "ON",
                  "PCRE2_BUILD_PCRE2_8": "ON", "PCRE2_BUILD_PCRE2_16": "ON",
                  "PCRE2_BUILD_PCRE2_32": "ON", "PCRE2_SUPPORT_JIT": "ON",
                  "PCRE2_SUPPORT_UNICODE": "ON", "PCRE2_BUILD_TESTS": "ON",
                  "PCRE2_BUILD_PCRE2GREP": "ON", "PCRE2_SUPPORT_LIBZ": "OFF",
                  "PCRE2_SUPPORT_LIBBZ2": "OFF", "PCRE2_SUPPORT_LIBREADLINE": "OFF",
                  "PCRE2_SUPPORT_LIBEDIT": "OFF"},
        "scope": "Native static/shared Unicode 8/16/32-bit PCRE2 with JIT and tests; CLI gzip/bzip2/editline integrations excluded, not a complete MSYS2 package"
    }
}


def ctest_results(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ContractError("CTest did not produce a test suite")
    cases = list(root.iter("testcase"))
    if not cases or any(list(case.iter("failure")) or list(case.iter("error")) or list(case.iter("skipped"))
                        for case in cases):
        raise ContractError("Empty, failed or skipped CTest cases cannot qualify the library")
    return [case.attrib["name"] for case in cases]


def expat_test_results(text):
    summaries = re.findall(r"([0-9]+)%: Checks: ([0-9]+), Failed: ([0-9]+)", text)
    if not summaries or any(percent != "100" or int(count) == 0 or failures != "0"
                            for percent, count, failures in summaries):
        raise ContractError("Expat did not report completed nonempty passing native tests")
    return {"runner": "upstream-runtests-native", "checks": [int(row[1]) for row in summaries]}


def build(package, source, manifest, prefix, identities, proof, cmake, ninja,
          output, jobs, pwsh, artifact_gate):
    if os.name != "nt" or platform.machine().lower() not in ("aarch64", "arm64"):
        raise ContractError("Native Windows ARM64 is required")
    if not 1 <= jobs <= 4:
        raise ContractError("Explicit allocation of 1-4 jobs is required")
    recipe = RECIPES[package]
    source, manifest, prefix, cmake, ninja, output = [
        Path(path).resolve() for path in (source, manifest, prefix, cmake, ninja, output)]
    verify_tree(source, manifest)
    source_identity = json.loads(manifest.read_text())["source"]
    if source_identity["id"] != package or source_identity["version"] != recipe["version"]:
        raise ContractError("Source identity differs from the maintained library recipe")
    if output.exists():
        raise ContractError("Build output must be a new directory")
    compiler, cxx = prefix / "bin/gcc.exe", prefix / "bin/g++.exe"
    qualified = json.loads(Path(proof).read_text())
    if (qualified.get("Passed") is not True
            or Path(qualified["CompilerProcess"]["Image"]).resolve() != compiler
            or qualified.get("Target") != "aarch64-w64-mingw32"
            or not qualified.get("Runs")
            or any(row["ExitCode"] != 0 for row in qualified["Runs"])):
        raise ContractError("Toolchain qualification does not match the requested native compiler")
    env = dict(os.environ)
    for key in list(env):
        if (key.startswith(("MSYS", "MINGW", "CMAKE", "GCC_", "PKG_CONFIG")) or key in
                ("CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "COMPILER_PATH",
                 "LIBRARY_PATH", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OSTYPE")):
            del env[key]
    env["PATH"] = os.pathsep.join(map(str, (prefix / "bin", cmake.parent, ninja.parent,
                                          Path(os.environ["SystemRoot"]) / "System32")))
    env["LC_ALL"] = "C"
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
    output.mkdir(parents=True)
    (output / "temp").mkdir()
    env["TMP"] = env["TEMP"] = str(output / "temp")
    support = support_identities(compiler, prefix, env)
    ctest = cmake.with_name("ctest.exe")
    tool_files = [compiler, cxx, cmake, ctest, ninja, prefix / "bin/ar.exe",
                  prefix / "bin/ranlib.exe", prefix / "bin/windres.exe"]
    tools = {str(path): digest(path) for path in tool_files}
    compiler_snapshot = {str(Path(row["Path"]).resolve()).casefold(): row
                         for row in json.loads(Path(identities).read_text())}
    for path in (compiler, cxx, prefix / "bin/ar.exe", prefix / "bin/ranlib.exe",
                 prefix / "bin/windres.exe", *(Path(row["path"]) for row in support.values())):
        row = compiler_snapshot.get(str(path).casefold())
        if not row or row["Machine"] != "0xAA64" or row["SHA256"].lower() != digest(path):
            raise ContractError(f"Native compiler component identity mismatch: {path}")
    commands, variants = [], []
    report = {"schema": 1, "package": package, "version": recipe["version"], "status": "failed",
              "build_host": "windows-arm64-native", "target": "aarch64-w64-mingw32",
              "scope": recipe["scope"], "jobs": jobs, "source": source_identity,
              "source_manifest_sha256": digest(manifest), "recipe": recipe,
              "recipe_script_sha256": digest(__file__),
              "artifact_gate_sha256": digest(artifact_gate),
              "toolchain_proof_sha256": digest(proof), "tools": tools,
              "support_tools": support, "tool_identity_snapshot_sha256": digest(identities)}

    def run(name, argv):
        command = list(map(str, argv))
        with (output / f"{name}.log").open("xb") as log:
            completed = subprocess.run(command, cwd=output, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=1800)
        commands.append({"name": name, "argv": command, "exit_code": completed.returncode,
                         "log_sha256": digest(output / f"{name}.log")})
        if completed.returncode != 0:
            raise ContractError(f"{name} failed ({completed.returncode}); see {output / (name + '.log')}")

    def pe_gate(name, root):
        destination = output / f"{name}.json"
        run(name, [pwsh, "-NoProfile", "-File", artifact_gate, "-Root", root,
                   "-ReportPath", destination])
        data = json.loads(destination.read_text())
        if data.get("Passed") is not True or not data.get("CandidateCount"):
            raise ContractError("Empty or failing native PE inventory")
        return digest(destination)

    try:
        pe_gate("cmake-native", cmake.parent)
        pe_gate("ninja-native", ninja.parent)
        link_inputs = {}
        for name in ("crt2.o", "libgcc.a", "libmingw32.a", "libmingwex.a", "libucrt.a",
                     "libstdc++.a", "libwinpthread.a"):
            driver = cxx if name == "libstdc++.a" else compiler
            run(f"resolve-{name}", [driver, f"-print-file-name={name}"])
            value = (output / f"resolve-{name}.log").read_text().strip()
            path = Path(value).resolve()
            if not Path(value).is_absolute() or not path.is_file() or not path.is_relative_to(prefix):
                raise ContractError(f"Missing native link input: {name}")
            link_inputs[name] = {"path": str(path), "sha256": digest(path)}
        report["link_inputs"] = link_inputs
        copied = output / "source"
        shutil.copytree(source, copied)
        verify_tree(copied, manifest)
        for variant in recipe["variants"]:
            directory, stage = output / f"build-{variant}", output / f"stage-{variant}"
            flags = dict(recipe["flags"])
            if package == "expat":
                flags["EXPAT_SHARED_LIBS"] = "ON" if variant == "shared" else "OFF"
                flags["BUILD_SHARED_LIBS"] = flags["EXPAT_SHARED_LIBS"]
                flags["CMAKE_DLL_NAME_WITH_SOVERSION"] = "ON"
            configure = [cmake, "-S", copied, "-B", directory, "-G", "Ninja",
                         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={stage.as_posix()}",
                         f"-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}",
                         f"-DCMAKE_C_COMPILER={compiler.as_posix()}",
                         f"-DCMAKE_CXX_COMPILER={cxx.as_posix()}",
                         f"-DCMAKE_AR={(prefix / 'bin/ar.exe').as_posix()}",
                         f"-DCMAKE_RANLIB={(prefix / 'bin/ranlib.exe').as_posix()}",
                         f"-DCMAKE_RC_COMPILER={(prefix / 'bin/windres.exe').as_posix()}",
                         *[f"-D{key}={value}" for key, value in flags.items()]]
            run(f"{variant}-configure", configure)
            cache = (directory / "CMakeCache.txt").read_text()
            for key, value in flags.items():
                if not any(line.startswith(key + ":") and line.endswith("=" + value) for line in cache.splitlines()):
                    raise ContractError(f"CMake did not record requested flag {key}={value}")
            run(f"{variant}-build", [cmake, "--build", directory, "--parallel", jobs])
            pe_hash = pe_gate(f"{variant}-build-pe", directory)
            if package == "pcre2":
                run(f"{variant}-literal-jit", [sys.executable, "-B",
                    Path(__file__).with_name("test-pcre2-runtime.py"),
                    "--root", directory, "--output", output / f"{variant}-literal-jit"])
                literal = json.loads((output / f"{variant}-literal-jit/results.json").read_text())
                if literal.get("passed") is not True or len(literal.get("cases", [])) != 6:
                    raise ContractError("Complete PCRE2 interpreter/JIT prerequisite did not pass")
            if package == "expat":
                # Upstream run.sh only selects direct execution or Wine. Native
                # Windows needs neither its Bash dispatcher nor Wine.
                run(f"{variant}-native-runtests", [directory / "tests/runtests.exe"])
                log = output / f"{variant}-native-runtests.log"
                tests = expat_test_results(log.read_text())
                test_hash = digest(log)
            else:
                if package == "zlib":
                    # The pinned upstream fixture mistakenly depends on as_config
                    # rather than asx_config. Prepare the missing dependency first;
                    # the complete test suite still runs and must pass afterward.
                    run(f"{variant}-fixture-order", [ctest, "--test-dir", directory,
                        "--output-on-failure", "--no-tests=error",
                        "-R", "^zlib_add_subdirectory_exclude_configure$"])
                run(f"{variant}-ctest", [ctest, "--test-dir", directory, "--output-on-failure",
                                         "--no-tests=error", "--parallel", 1,
                                         "--output-junit", directory / "ctest-results.xml"])
                tests = ctest_results(directory / "ctest-results.xml")
                test_hash = digest(directory / "ctest-results.xml")
            run(f"{variant}-install", [cmake, "--install", directory])
            license_dir = stage / "share/licenses" / package
            license_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(copied / recipe["license"], license_dir / recipe["license"])
            files = inventory(stage)
            if not any(name.endswith(".a") for name in files):
                raise ContractError("Installed library/import archive is absent")
            variants.append({"variant": variant, "stage": str(stage), "files": files,
                             "upstream_tests": tests, "build_pe_report_sha256": pe_hash,
                             "cmake_cache_sha256": digest(directory / "CMakeCache.txt"),
                             "test_results_sha256": test_hash})
        verify_tree(source, manifest)
        verify_support(support, compiler, prefix, env)
        for path, expected in tools.items():
            if digest(path) != expected:
                raise ContractError(f"Native tool changed during build: {path}")
        for record in link_inputs.values():
            if digest(record["path"]) != record["sha256"]:
                raise ContractError("Native CRT/library changed during build")
        report["status"] = "native-library-candidate-tested"
    finally:
        report["commands"], report["variants"] = commands, variants
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{package}: {report['status']}; variants={len(variants)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=RECIPES)
    for key in ("source", "manifest", "prefix", "identities", "proof", "cmake", "ninja",
                "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{key}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, required=True)
    a = parser.parse_args()
    build(a.package, a.source, a.manifest, a.prefix, a.identities, a.proof,
          a.cmake, a.ninja, a.output, a.jobs, a.pwsh, a.artifact_gate)


if __name__ == "__main__":
    main()
