"""Build pinned native Windows ARM64 curl leaves, retaining fail-closed evidence.

Run with --help for required, explicit paths. Every invocation needs a new
--output directory. Source recovery is shared, read-only after verification;
upstream patches are applied only to the invocation's private source copy.
No package manager, compiler replacement, test dependency download or emulation
is used. A tested library candidate is not full Git or MSYS2-package admission.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

from compiler_tools import support_identities
from sources import ContractError, digest, inventory, load_lock, recover, relative_path, verify_tree


RECIPES = {
    "brotli": {
        "version": "1.2.0", "variants": ["static", "shared"], "cmake": ".",
        "license": "LICENSE", "define": "LEAF_BROTLI",
        "flags": {"BROTLI_BUILD_TOOLS": "ON", "BROTLI_DISABLE_TESTS": "OFF"},
        "libraries": ["brotlienc", "brotlidec", "brotlicommon"],
        "tests": ["compression-roundtrip-bytes", "undersized-destination-rejected",
                  "malformed-stream-rejected"],
        "symbols": ["BrotliEncoderCompress", "BrotliDecoderDecompress"],
        "limits": ["Brotli testdata split package is not installed separately.",
                   "Pinned archive omits tests/testdata; CTest exercises available source-file roundtrips."]
    },
    "c-ares": {
        "version": "1.34.8", "variants": ["combined"], "cmake": ".",
        "license": "LICENSE.md", "define": "LEAF_CARES",
        "flags": {"CARES_STATIC": "ON", "CARES_SHARED": "ON", "CARES_BUILD_TOOLS": "ON",
                  "CARES_BUILD_TESTS": "OFF", "CARES_THREADS": "ON",
                  "CMAKE_DLL_NAME_WITH_SOVERSION": "ON"},
        "libraries": ["cares"],
        "tests": ["ipv4-ipv6-positive-invalid", "dns-query-encode-decode-truncation",
                  "overlong-dns-label-rejected"],
        "symbols": ["ares_create_query", "ares_inet_pton"],
        "limits": ["Native deterministic library API checks only; no live DNS/network qualification.",
                   "Upstream GoogleTest/container suite not built; no test dependencies installed."]
    },
    "zstd": {
        "version": "1.5.7", "variants": ["combined"], "cmake": "build/cmake",
        "license": "LICENSE", "define": "LEAF_ZSTD",
        "flags": {"BUILD_SHARED_LIBS": "ON", "ZSTD_BUILD_STATIC": "ON",
                  "ZSTD_BUILD_SHARED": "ON", "ZSTD_BUILD_PROGRAMS": "ON",
                  "ZSTD_BUILD_CONTRIB": "ON", "ZSTD_PROGRAMS_LINK_SHARED": "ON",
                  "ZSTD_MULTITHREAD_SUPPORT": "ON", "ZSTD_LEGACY_SUPPORT": "ON",
                  "BUILD_TESTING": "OFF", "ZSTD_BUILD_TESTS": "OFF"},
        "libraries": ["zstd"],
        "tests": ["compression-roundtrip-bytes", "undersized-destination-rejected",
                  "malformed-stream-rejected"],
        "symbols": ["ZSTD_compress", "ZSTD_decompress"],
        "limits": ["Native byte-exact API checks; upstream fuzz/CLI shell suite not run.",
                   "Optional third-party CLI compression formats are not added."]
    },
    "nghttp2": {
        "version": "1.70.0", "variants": ["combined"], "cmake": ".",
        "license": "COPYING", "define": "LEAF_NGHTTP2",
        "flags": {"BUILD_SHARED_LIBS": "ON", "BUILD_STATIC_LIBS": "ON",
                  "ENABLE_LIB_ONLY": "ON", "WITH_JEMALLOC": "OFF", "WITH_LIBXML2": "OFF",
                  "ENABLE_DOC": "OFF", "BUILD_TESTING": "ON",
                  "ENABLE_FAILMALLOC": "ON", "CMAKE_DLL_NAME_WITH_SOVERSION": "ON"},
        "libraries": ["nghttp2"],
        "tests": ["hpack-header-roundtrip-bytes", "invalid-hpack-index-rejected",
                  "session-positive-invalid-stream"],
        "symbols": ["nghttp2_hd_deflate_hd", "nghttp2_hd_inflate_hd2"],
        "limits": ["Library-only package configuration; applications/HTTP3/docs are not built.",
                   "Pinned release bundles munit; no CUnit installation is needed."]
    }
}


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def apply_upstream_patch(root, patch):
    """Apply only exact, unique unified-diff contexts, without fuzzy matching."""
    root = Path(root)
    lines = patch.splitlines(keepends=True)
    index, changes = 0, []
    while index < len(lines):
        if not lines[index].startswith("--- "):
            raise ContractError("Expected unified patch file header")
        old_name = lines[index][4:].split()[0]
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ContractError("Missing unified patch destination")
        new_name = lines[index][4:].split()[0]
        for name in (old_name, new_name):
            relative_path(name)
        parts = relative_path(new_name).parts
        if len(parts) < 2:
            raise ContractError("Patch requires a removable top-level component")
        target = root.joinpath(*parts[1:])
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
            raise ContractError("Unsafe patch target")
        before = digest(target)
        text = target.read_text(encoding="utf-8")
        index += 1
        hunks = 0
        while index < len(lines) and lines[index].startswith("@@ "):
            header = re.fullmatch(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@[^\n]*\n?",
                                  lines[index])
            if not header:
                raise ContractError("Malformed unified hunk")
            old_count, new_count = (int(value) if value is not None else 1 for value in header.groups())
            index += 1
            old, new = [], []
            while index < len(lines) and not lines[index].startswith(("@@ ", "--- ")):
                line = lines[index]
                if line[:1] not in (" ", "+", "-"):
                    raise ContractError("Unsupported unified patch line")
                if line[0] in " -":
                    old.append(line[1:])
                if line[0] in " +":
                    new.append(line[1:])
                index += 1
            previous, replacement = "".join(old), "".join(new)
            if len(old) != old_count or len(new) != new_count or not previous:
                raise ContractError("Unified hunk line count mismatch")
            if text.count(previous) != 1:
                raise ContractError("Patch context is absent or ambiguous")
            text = text.replace(previous, replacement, 1)
            hunks += 1
        if not hunks:
            raise ContractError("Patch contains no hunks")
        target.write_text(text, encoding="utf-8", newline="\n")
        changes.append({"path": target.relative_to(root).as_posix(),
                        "before_sha256": before, "after_sha256": digest(target), "hunks": hunks})
    if not changes:
        raise ContractError("Empty patch")
    return changes


def static_archive(path):
    data = Path(path).read_bytes()
    if data[:8] != b"!<arch>\n":
        raise ContractError("Invalid static archive header")
    offset, members = 8, 0
    while offset < len(data):
        if offset + 60 > len(data) or data[offset + 58:offset + 60] != b"`\n":
            raise ContractError("Malformed static archive member")
        name = data[offset:offset + 16].decode("ascii").strip()
        try:
            size = int(data[offset + 48:offset + 58])
        except ValueError as error:
            raise ContractError("Invalid archive member length") from error
        start, end = offset + 60, offset + 60 + size
        if size < 0 or end > len(data):
            raise ContractError("Truncated static archive")
        if name not in ("/", "//", "/SYM64/"):
            member = data[start:end]
            if len(member) < 20 or struct.unpack_from("<H", member)[0] != 0xAA64:
                raise ContractError("Static library contains a non-ARM64 COFF member")
            members += 1
        offset = end + size % 2
    if not members or offset != len(data):
        raise ContractError("Empty or malformed static archive")
    return {"sha256": digest(path), "arm64_coff_members": members}


def ctest_results(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))
    if not cases or any(list(case.iter(tag)) for case in cases for tag in ("failure", "error", "skipped")):
        raise ContractError("Empty, failed or skipped CTest results")
    return [case.attrib["name"] for case in cases]


def validate_api_output(text, recipe, variant, executable, stage):
    cases, bindings = [], {}
    for line in text.splitlines():
        if line.startswith("CASE\t"):
            cases.append(line.split("\t", 1)[1])
        elif line.startswith("BINDING\t"):
            _, symbol, value = line.split("\t")
            if symbol in bindings:
                raise ContractError("Duplicate API binding")
            path = Path(value).resolve()
            if variant == "static":
                valid = path == Path(executable).resolve()
            else:
                valid = path.parent == (Path(stage) / "bin").resolve() and path.suffix.lower() == ".dll"
            if not valid or not path.is_file():
                raise ContractError(f"API bound outside its measured {variant} candidate: {path}")
            bindings[symbol] = {"path": str(path), "sha256": digest(path)}
    if (cases != recipe["tests"] or set(bindings) != set(recipe["symbols"])
            or text.splitlines()[-2:] != ["READY", "PASS"]):
        raise ContractError("Incomplete API exercise/binding evidence")
    return {"cases": cases, "bindings": bindings}


def clean_environment(prefix, cmake, ninja, scratch, jobs):
    if not 1 <= jobs <= 4:
        raise ContractError("An explicit allocation of 1-4 build jobs is required")
    env = dict(os.environ)
    for key in list(env):
        if (key.upper().startswith(("MSYS", "MINGW", "GCC_", "CMAKE", "PKG_CONFIG"))
                or key.upper() in ("CC", "CXX", "AR", "AS", "LD", "RC", "RANLIB", "CFLAGS",
                                   "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "COMPILER_PATH", "LIBRARY_PATH",
                                   "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH",
                                   "OSTYPE", "INCLUDE", "LIB", "LIBPATH")):
            del env[key]
    env["PATH"] = os.pathsep.join(map(str, (prefix / "bin", cmake.parent, ninja.parent,
                                          Path(os.environ["SystemRoot"]) / "System32")))
    env["TMP"] = env["TEMP"] = str(scratch)
    env["LC_ALL"] = "C"
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
    return env


def build(args):
    if os.name != "nt" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise ContractError("Native Windows ARM64 orchestration is mandatory")
    if not 1 <= args.jobs <= 4:
        raise ContractError("An explicit allocation of 1-4 build jobs is required")
    package, output, prefix = args.package, args.output.resolve(), args.prefix.resolve()
    lock = load_lock(args.lock)
    recipe = RECIPES[package]
    item = next(row for row in lock["sources"] if row["id"] == package)
    if item["version"] != recipe["version"]:
        raise ContractError("Lock version differs from maintained recipe")
    if output.exists():
        raise ContractError("Use a new build output; previous failed evidence is immutable")
    output.mkdir(parents=True)
    scratch = output / "scratch"
    scratch.mkdir()
    cmake, ninja = args.cmake.resolve(), args.ninja.resolve()
    ctest = cmake.with_name("ctest.exe")
    env = clean_environment(prefix, cmake, ninja, scratch, args.jobs)
    commands, stages, frozen, invariants = [], [], {}, {}
    report = {"schema": 1, "status": "failed", "package": package,
              "version": recipe["version"], "jobs": args.jobs, "recipe": recipe,
              "build_host": "windows-arm64-native", "target": "aarch64-w64-mingw32",
              "scope": "Native static/shared library candidate, not full Git or package admission",
              "pending": ["full-curl-integration", "full-Git-integration"],
              "limitations": recipe["limits"], "commands": commands, "stages": stages,
              "environment": {key: env[key] for key in ("PATH", "TMP", "TEMP", "LC_ALL",
                                                       "CMAKE_BUILD_PARALLEL_LEVEL")}}

    def freeze(path):
        path = Path(path).resolve()
        frozen[str(path)] = digest(path)
        return frozen[str(path)]

    def run(name, argv, expected=0, input_data=None):
        command = list(map(str, argv))
        stdout_path, stderr_path = output / f"{name}.stdout.bin", output / f"{name}.stderr.bin"
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            row = {"name": name, "argv": command, "cwd": str(output)}
            commands.append(row)
            try:
                result = subprocess.run(command, cwd=output, env=env, input=input_data,
                                        stdout=stdout, stderr=stderr, timeout=1800)
                row["exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                row["timeout_seconds"] = 1800
                raise
        row.update(stdout_sha256=digest(stdout_path), stderr_sha256=digest(stderr_path))
        if result.returncode != expected:
            raise ContractError(f"{name} exited {result.returncode} (0x{result.returncode & 0xffffffff:08X}); "
                                f"logs: {stdout_path}, {stderr_path}")
        return stdout_path.read_bytes()

    def gate(name, script, arguments):
        destination = output / f"{name}.json"
        run(name, [args.pwsh, "-NoProfile", "-File", script, *arguments, "-ReportPath", destination])
        data = json.loads(destination.read_text())
        if data.get("Passed") is not True:
            raise ContractError(f"Native gate did not pass: {name}")
        return data

    def process_gate(name, pid, image):
        data = gate(name, args.process_gate, ["-ProcessId", pid])
        if (data.get("MeasuredCount") != 1 or len(data.get("Processes", [])) != 1
                or Path(data["Processes"][0]["ImagePath"]).resolve() != Path(image).resolve()
                or data["Processes"][0].get("ProcessMachine") != "0xAA64"
                or data["Processes"][0].get("Wow64ProcessMachine") != "0x0000"
                or data["Processes"][0].get("NativeMachine") != "0xAA64"):
            raise ContractError("Live ProcessMachineTypeInfo evidence does not match requested image")
        return digest(output / f"{name}.json")

    try:
        report["lock_sha256"] = freeze(args.lock)
        report["script_sha256"] = freeze(__file__)
        fixture = Path(__file__).with_name("fixtures") / "curl-leaves-api.c"
        report["fixture_sha256"] = freeze(fixture)
        recipe_snapshot = output / "recipe-snapshot"
        recipe_snapshot.mkdir()
        for path in (Path(__file__), args.lock, fixture, Path(__file__).with_name("sources.py"),
                     Path(__file__).with_name("compiler_tools.py")):
            freeze(path)
            shutil.copyfile(path, recipe_snapshot / path.name)
        write_json(output / "recipe-snapshot.inventory.json", {"files": inventory(recipe_snapshot)})
        for path in (args.artifact_gate, args.process_gate, args.pwsh, sys.executable,
                     args.identities, args.proof):
            freeze(path)
        recover(item, args.downloads, args.sources)
        source, manifest = args.sources.resolve() / package, args.sources.resolve() / f"{package}.inventory.json"
        report["source"] = item
        report["source_manifest_sha256"] = freeze(manifest)
        freeze(args.downloads / item["file"])
        verify_tree(source, manifest)
        invariants[str(source)] = inventory(source)
        compiler, cxx = prefix / "bin/gcc.exe", prefix / "bin/g++.exe"
        qualified = json.loads(args.proof.read_text())
        if (qualified.get("Passed") is not True
                or qualified.get("Target") != "aarch64-w64-mingw32"
                or qualified.get("CompilerProcess", {}).get("Machine") != "0xAA64"
                or Path(qualified["CompilerProcess"]["Image"]).resolve() != compiler
                or not qualified.get("Runs") or any(row["ExitCode"] != 0 for row in qualified["Runs"])):
            raise ContractError("Toolchain qualification does not identify this native compiler")
        if run("compiler-target", [compiler, "-dumpmachine"]).strip() != b"aarch64-w64-mingw32":
            raise ContractError("Compiler target changed")
        support = support_identities(compiler, prefix, env)
        cc1plus = Path(run("resolve-cc1plus", [cxx, "-print-prog-name=cc1plus"]).decode().strip()).resolve()
        if not cc1plus.is_file() or not cc1plus.is_relative_to(prefix):
            raise ContractError("C++ front end is outside the admitted prefix")
        support["cc1plus"] = {"path": str(cc1plus), "sha256": digest(cc1plus)}
        report["support_tools"] = support
        admitted = {str(Path(row["Path"]).resolve()).casefold(): row
                    for row in json.loads(args.identities.read_text())}
        tools = [prefix / "bin" / name for name in
                 ("gcc.exe", "g++.exe", "ar.exe", "ranlib.exe", "windres.exe")]
        tools += [Path(row["path"]) for row in support.values()]
        for path in tools:
            row = admitted.get(str(path).casefold())
            if not row or row["Machine"] != "0xAA64" or row["SHA256"].lower() != freeze(path):
                raise ContractError(f"Unadmitted compiler/support component: {path}")
        for path in (cmake, ctest, ninja):
            if freeze(path) != lock["native_driver_sha256"][path.name]:
                raise ContractError(f"Native build driver differs from lock: {path}")
        report["link_inputs"] = {}
        link_names = ("crt2.o", "crt2u.o", "libgcc.a", "libstdc++.a", "libwinpthread.a",
                      "libmingw32.a", "libmingwex.a", "libmsvcrt.a", "libucrt.a", "libkernel32.a",
                      "libadvapi32.a", "libiphlpapi.a", "libws2_32.a", "libuser32.a",
                      "libshell32.a", "libmoldname.a")
        for name in link_names:
            value = run(f"resolve-{name}", [compiler, f"-print-file-name={name}"]).decode().strip()
            path = Path(value).resolve()
            if not Path(value).is_absolute() or not path.is_file() or not path.is_relative_to(prefix):
                raise ContractError(f"Unresolved CRT/link input: {name}")
            sha = freeze(path)
            if name == "libgcc.a" and sha != lock["libgcc_sha256"]:
                raise ContractError("Compiler cache-fixed libgcc hash does not match lock")
            report["link_inputs"][name] = {"path": str(path), "sha256": sha}
        gate("cmake-artifacts", args.artifact_gate, ["-Root", cmake.parent])
        gate("ninja-artifacts", args.artifact_gate, ["-Root", ninja.parent])
        report["python_process"] = process_gate("python-process", os.getpid(), sys.executable)
        held = subprocess.Popen([str(compiler), "-E", "-x", "c", "-"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=output, env=env)
        try:
            report["compiler_process"] = process_gate("compiler-process", held.pid, compiler)
            stdout, stderr = held.communicate(b"\n", timeout=30)
            if held.returncode != 0:
                raise ContractError(f"Observed compiler preprocessing failed: {held.returncode}; {stderr!r}")
        finally:
            if held.poll() is None:
                held.kill()
                held.communicate()
        recipe_dir = args.recipes / f"mingw-w64-{package}"
        pkgbuild = recipe_dir / "PKGBUILD"
        if freeze(pkgbuild) != item["recipe_sha256"]:
            raise ContractError("Pinned MSYS2 package recipe digest mismatch")
        provenance = output / "upstream-recipe"
        provenance.mkdir()
        shutil.copyfile(pkgbuild, provenance / "PKGBUILD")
        report["upstream_recipe"] = {"commit": lock["recipe_commit"], "sha256": item["recipe_sha256"],
                                     "patches": []}
        prepared = output / "source"
        shutil.copytree(source, prepared)
        verify_tree(prepared, manifest)
        for patch_item in item["patches"]:
            path = recipe_dir / patch_item["file"]
            if freeze(path) != patch_item["sha256"]:
                raise ContractError("Pinned upstream patch digest mismatch")
            shutil.copyfile(path, provenance / path.name)
            changes = apply_upstream_patch(prepared, path.read_text(encoding="utf-8"))
            report["upstream_recipe"]["patches"].append({**patch_item, "changes": changes})
        prepared_files = inventory(prepared)
        write_json(output / "prepared-source.inventory.json", {"source": item, "files": prepared_files})
        invariants[str(prepared)] = prepared_files
        for variant in recipe["variants"]:
            directory, stage = output / f"build-{variant}", output / f"stage-{variant}"
            flags = dict(recipe["flags"])
            if package == "brotli":
                flags["BUILD_SHARED_LIBS"] = "ON" if variant == "shared" else "OFF"
            command = [cmake, "-S", prepared.joinpath(*recipe["cmake"].split("/")), "-B", directory,
                       "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                       f"-DCMAKE_INSTALL_PREFIX={stage.as_posix()}",
                       f"-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}",
                       f"-DCMAKE_C_COMPILER={compiler.as_posix()}",
                       f"-DCMAKE_CXX_COMPILER={cxx.as_posix()}",
                       f"-DCMAKE_AR={(prefix / 'bin/ar.exe').as_posix()}",
                       f"-DCMAKE_RANLIB={(prefix / 'bin/ranlib.exe').as_posix()}",
                       f"-DCMAKE_RC_COMPILER={(prefix / 'bin/windres.exe').as_posix()}",
                       "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                       "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
                       *[f"-D{key}={value}" for key, value in flags.items()]]
            run(f"{variant}-configure", command)
            cache = (directory / "CMakeCache.txt").read_text()
            for key, value in flags.items():
                if not any(line.startswith(key + ":") and line.endswith("=" + value) for line in cache.splitlines()):
                    raise ContractError(f"CMake did not retain {key}={value}")
            run(f"{variant}-build", [cmake, "--build", directory, "--parallel", args.jobs])
            run(f"{variant}-install", [cmake, "--install", directory])
            license_dir = stage / "share" / "licenses" / package
            license_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(prepared / recipe["license"], license_dir / recipe["license"])
            pe = gate(f"{variant}-installed-pe", args.artifact_gate, ["-Root", stage])
            if not pe.get("CandidateCount"):
                raise ContractError("Installed PE gate was empty")
            installed = inventory(stage)
            write_json(output / f"{variant}-installed.inventory.json", {"files": installed})
            stage_report = {"variant": variant, "prefix": str(stage), "flags": flags,
                            "upstream_tests": [], "upstream_test_status": "not-applicable",
                            "functional_tests": [],
                            "installed_manifest_sha256": digest(output / f"{variant}-installed.inventory.json"),
                            "archive_members": {}}
            stages.append(stage_report)
            invariants[str(stage)] = installed
            for form in (["static", "shared"] if variant == "combined" else [variant]):
                tests = output / f"tests-{variant}-{form}"
                tests.mkdir()
                executable = tests / f"{package}-{form}.exe"
                libraries = []
                for name in recipe["libraries"]:
                    suffix = "_static" if package == "c-ares" and form == "static" else ""
                    path = stage / "lib" / f"lib{name}{suffix}{'.a' if form == 'static' else '.dll.a'}"
                    if not path.is_file():
                        raise ContractError(f"Missing expected {form} library: {path}")
                    libraries.append(path)
                    if form == "static":
                        stage_report["archive_members"][path.name] = static_archive(path)
                defines = [f"-D{recipe['define']}"]
                if form == "static":
                    defines += {"c-ares": ["-DCARES_STATICLIB"], "nghttp2": ["-DNGHTTP2_STATICLIB"]}.get(package, [])
                else:
                    defines += {"brotli": ["-DBROTLI_SHARED_COMPILATION"],
                                "zstd": ["-DZSTD_DLL_IMPORT=1"]}.get(package, [])
                extra = ["-lws2_32", "-ladvapi32", "-liphlpapi"] if package == "c-ares" else []
                if package == "brotli":
                    extra += ["-lm"]
                run(f"{variant}-{form}-fixture-build", [compiler, "-O2", "-Wall", *defines,
                                                        "-I", stage / "include", fixture,
                                                        *libraries, *extra, "-o", executable])
                gate(f"{variant}-{form}-fixture-pe", args.artifact_gate, ["-Root", tests])
                test_env = dict(env)
                # No PATH broadening: run a test-only copy beside the installed
                # DLLs, checking every exercised API's actual module path.
                test_exe = stage / "bin" / executable.name
                if test_exe.exists():
                    raise ContractError("Test-only executable would overwrite an installed artifact")
                shutil.copyfile(executable, test_exe)
                try:
                    stdout_path = output / f"{variant}-{form}-api.stdout.bin"
                    stderr_path = output / f"{variant}-{form}-api.stderr.bin"
                    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                        held = subprocess.Popen([str(test_exe), "--hold"], cwd=output, env=test_env,
                                                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
                        try:
                            process_hash = process_gate(f"{variant}-{form}-api-process", held.pid, test_exe)
                            held.communicate(b"\n", timeout=120)
                        finally:
                            if held.poll() is None:
                                held.kill()
                                held.communicate()
                    commands.append({"name": f"{variant}-{form}-api", "argv": [str(test_exe), "--hold"],
                                     "exit_code": held.returncode, "stdout_sha256": digest(stdout_path),
                                     "stderr_sha256": digest(stderr_path)})
                    if held.returncode != 0 or stderr_path.read_bytes():
                        raise ContractError(f"Native {form} API test failed ({held.returncode}); logs: {stdout_path}")
                    parsed = validate_api_output(stdout_path.read_text(), recipe, form, test_exe, stage)
                    run(f"{variant}-{form}-negative-control", [test_exe, "--negative-control"], expected=91)
                    stage_report["functional_tests"].append({"form": form, **parsed,
                        "process_report_sha256": process_hash, "fixture_sha256": digest(test_exe),
                        "preserved_executable": str(executable), "executed_copy": str(test_exe),
                        "negative_control_exit_code": 91})
                finally:
                    test_exe.unlink()
            if inventory(stage) != installed:
                raise ContractError("Installed files changed during functional tests")
            if package in ("brotli", "nghttp2"):
                # Keep independent API/install evidence even when the compiler
                # cannot build an upstream runner. A runner failure still fails
                # the entire candidate: this is not a test-skipping fallback.
                stage_report["upstream_test_status"] = "failed"
                if package == "nghttp2":
                    run(f"{variant}-build-tests", [cmake, "--build", directory, "--parallel",
                                                  args.jobs, "--target", "main", "failmalloc"])
                junit = output / f"{variant}-ctest.xml"
                run(f"{variant}-ctest", [ctest, "--test-dir", directory, "--output-on-failure",
                                         "--parallel", args.jobs, "--output-junit", junit])
                stage_report["upstream_tests"] = ctest_results(junit)
                stage_report["upstream_test_status"] = "passed"
        report["status"] = "native-library-candidate-tested"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        failures = []
        for path, sha in frozen.items():
            if not Path(path).is_file() or digest(path) != sha:
                failures.append(f"Frozen input changed: {path}")
        for path, files in invariants.items():
            try:
                if inventory(path) != files:
                    failures.append(f"Tree changed: {path}")
            except Exception as error:
                failures.append(f"Tree verification failed: {path}: {error}")
        report["frozen_inputs"] = frozen
        report["before_after_unchanged"] = not failures
        report["invariant_failures"] = failures
        if failures:
            report["status"] = "failed"
        write_json(output / "result.json", report)
        if failures:
            raise ContractError("; ".join(failures))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=RECIPES)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("curl-leaves.lock.json"))
    for name in ("downloads", "sources", "recipes", "prefix", "identities", "proof",
                 "cmake", "ninja", "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--jobs", type=int, required=True)
    args = parser.parse_args()
    result = build(args)
    print(json.dumps({"package": args.package, "status": result["status"],
                      "prefixes": [row["prefix"] for row in result["stages"]]}))


if __name__ == "__main__":
    main()
