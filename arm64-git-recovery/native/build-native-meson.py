"""Build pinned native Meson packages without an emulated build driver."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def validate_tests(package, expected_count, rows, config_text=""):
    if not rows or len(rows) != expected_count:
        raise ContractError("Empty or incomplete Meson package test set")
    skipped = []
    allowed_fuzzers = {"libpsl_idn2_fuzzer", "libpsl_idn2_load_fuzzer", "libpsl_idn2_load_dafsa_fuzzer"}
    no_fmemopen = re.search(r"(?m)^#undef HAVE_FMEMOPEN\s*$", config_text) is not None
    for row in rows:
        if row["result"] == "OK":
            continue
        name = row["name"].split(":", 1)[-1]
        if (package == "libpsl" and name in allowed_fuzzers and row["result"] == "SKIP"
                and row["returncode"] == 77 and no_fmemopen):
            skipped.append({"name": row["name"], "reason": "Upstream fuzz/main.c explicitly exits77 without fmemopen; no fuzz execution claimed"})
        else:
            raise ContractError(f"Failed or unexpected skipped Meson test: {row['name']}")
    if package == "libpsl":
        required = {"test-is-public", "test-is-public-all", "test-is-cookie-domain-acceptable",
                    "test-is-public-builtin", "test-registrable-domain"}
        passed = {row["name"].split(":", 1)[-1] for row in rows if row["result"] == "OK"}
        if not required.issubset(passed):
            raise ContractError("A required PSL functionality test did not pass")
    return skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=("pkgconf", "libpsl"), default="pkgconf")
    parser.add_argument("--variant", choices=("shared", "static"), default="shared")
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--pkg-config", type=Path)
    for name in ("source", "manifest", "meson", "meson-manifest", "prefix", "ninja",
                 "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Native Windows and a new output are required")
    verify_tree(args.source, args.manifest)
    verify_tree(args.meson.parent, args.meson_manifest)
    identity = json.loads(args.manifest.read_text())["source"]
    versions = {"pkgconf": "3.0.5", "libpsl": "0.21.5"}
    if identity["id"] != args.package or identity["version"] != versions[args.package]:
        raise ContractError("Package source differs from the pinned Meson recipe")
    dependency_files = {}
    if args.package == "libpsl":
        if not args.dependencies or not args.pkg_config:
            raise ContractError("libpsl requires the real native IDN/Unicode/text prefix and native pkgconf")
        dependency_files = inventory(args.dependencies)
        for header in ("idn2.h", "unistr.h", "iconv.h", "libintl.h"):
            if f"include/{header}" not in dependency_files:
                raise ContractError(f"Missing libpsl dependency: {header}")
    args.output.mkdir(parents=True)
    build, stage, copied = (args.output / name for name in ("build", "stage", "source"))
    shutil.copytree(args.source, copied)
    (args.output / "temp").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.ninja.parent,
                                           Path(sys.executable).parent, Path(os.environ["SystemRoot"]) / "System32")))
    env["TMP"] = env["TEMP"] = str(args.output / "temp")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if args.dependencies:
        env["PATH"] = str(args.dependencies / "bin") + os.pathsep + env["PATH"]
        env["PKG_CONFIG_LIBDIR"] = str(args.dependencies / "lib/pkgconfig")
        env["PKG_CONFIG_PATH"] = ""
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    tools = {str(path): digest(path) for path in (Path(sys.executable), compiler, args.ninja,
                                                args.prefix / "bin/ar.exe", args.prefix / "bin/windres.exe")}
    native_file = args.output / "native.ini"
    native_file.write_text("[binaries]\n" + "\n".join(
        f"{key} = '{(args.prefix / 'bin' / value).as_posix()}'" for key, value in
        (("c", "gcc.exe"), ("ar", "ar.exe"), ("strip", "strip.exe"), ("windres", "windres.exe"))) + "\n")
    if args.pkg_config:
        tools[str(args.pkg_config)] = digest(args.pkg_config)
        with native_file.open("a") as stream:
            stream.write(f"pkg-config = '{args.pkg_config.as_posix()}'\n")
    if args.dependencies:
        c_args = [f"-I{(args.dependencies / 'include').as_posix()}"]
        if args.variant == "static":
            c_args += ["-DIN_LIBUNISTRING", "-DIDN2_STATIC", "-DPSL_STATIC"]
        with native_file.open("a") as stream:
            stream.write("\n[built-in options]\n")
            stream.write("c_args = " + repr(c_args) + "\n")
            stream.write("c_link_args = " + repr([f"-L{(args.dependencies / 'lib').as_posix()}"]) + "\n")
    meson = [sys.executable, str(args.meson)]
    report = {"status": "failed", "source": identity, "tools": tools, "support": support,
              "package": args.package, "variant": args.variant, "dependencies": dependency_files,
              "meson_manifest_sha256": digest(args.meson_manifest),
              "build_host": "windows-arm64-native", "orchestration": "native-python-meson-ninja",
              "meson_distribution": "official portable source runtime, not the patched MSYS2 package",
              "commands": []}

    def execute(name, command, expected=0, child_env=None):
        result = subprocess.run(list(map(str, command)), cwd=args.output, env=child_env or env,
                                capture_output=True, timeout=1200)
        (args.output / f"{name}.stdout").write_bytes(result.stdout)
        (args.output / f"{name}.stderr").write_bytes(result.stderr)
        report["commands"].append({"name": name, "argv": list(map(str, command)), "exit": result.returncode})
        if result.returncode != expected:
            raise ContractError(f"{args.package} {name} failed; raw output preserved")
        return result.stdout

    try:
        execute("python-native", [args.pwsh, "-NoProfile", "-File", args.process_gate,
                                  "-ProcessId", str(os.getpid()), "-ReportPath", args.output / "python-native.json"])
        for name, path in (("gcc", compiler), ("ninja", args.ninja)):
            execute(f"{name}-native", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                                       "-Path", path, "-ReportPath", args.output / f"{name}-native.json"])
        if args.pkg_config:
            execute("pkgconf-native", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                                       "-Path", args.pkg_config, "-ReportPath", args.output / "pkgconf-native.json"])
        options = ["-Druntime=libidn2", "-Dtests=true", "-Ddocs=false"] if args.package == "libpsl" else []
        execute("setup", [*meson, "setup", build, copied, "--native-file", native_file,
                           "--prefix", stage, "--libdir", "lib", "--buildtype", "release",
                           "--default-library", args.variant, "--wrap-mode", "nodownload", *options])
        execute("build", [*meson, "compile", "-C", build, "-j", str(args.jobs)])
        tests = json.loads(execute("test-inventory", [*meson, "introspect", "--tests", build]))
        if not tests:
            raise ContractError("The Meson package must expose nonempty upstream tests")
        targets = {target["id"]: target for target in json.loads(
            execute("target-inventory", [*meson, "introspect", "--targets", build]))}
        test_outputs = set()
        for test in tests:
            command_path = Path(test["cmd"][0]).resolve()
            if command_path.is_relative_to(build.resolve()):
                test_outputs.add(str(command_path.relative_to(build.resolve())))
            for dependency in test.get("depends", []):
                if dependency not in targets:
                    raise ContractError("Meson test dependency is missing from target introspection")
                for filename in targets[dependency]["filename"]:
                    path = Path(filename).resolve()
                    if not path.is_relative_to(build.resolve()):
                        raise ContractError("Meson build output escaped its build directory")
                    test_outputs.add(str(path.relative_to(build.resolve())))
        if test_outputs:
            execute("build-tests", [args.ninja, "-C", build, "-j", str(args.jobs), *sorted(test_outputs)])
        execute("tests", [*meson, "test", "-C", build, "--no-rebuild",
                           "--num-processes", str(args.jobs), "--print-errorlogs"])
        rows = [json.loads(line) for line in (build / "meson-logs/testlog.json").read_text().splitlines() if line]
        report["unavailable_upstream_tests"] = validate_tests(
            args.package, len(tests), rows, (build / "config.h").read_text() if args.package == "libpsl" else "")
        report["passed_tests"] = [row["name"] for row in rows if row["result"] == "OK"]
        execute("install", [*meson, "install", "-C", build, "--no-rebuild"])
        if args.package == "pkgconf":
            executable = stage / "bin/pkgconf.exe"
            for alias in ("pkg-config.exe", "aarch64-w64-mingw32-pkgconf.exe", "aarch64-w64-mingw32-pkg-config.exe"):
                shutil.copyfile(executable, stage / "bin" / alias)
        license_dir = stage / "share/licenses" / args.package
        license_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(copied / "COPYING", license_dir / "COPYING")
        if args.package == "pkgconf":
            pc_dir = args.output / "pc-fixture"
            pc_dir.mkdir()
            (pc_dir / "base.pc").write_text("Name: base\nDescription: fixture base\nVersion: 1.2\nLibs: -lfixture_base\n")
            (pc_dir / "sample.pc").write_text(
                "prefix=C:/native fixture\nName: sample\nDescription: fixture dependent\nVersion: 2.3\n"
                "Requires: base >= 1.0\nLibs: -lfixture_sample\n")
            child = {**env, "PKG_CONFIG_LIBDIR": str(pc_dir), "PKG_CONFIG_PATH": ""}
            for name, options, expected in (
                ("version", ["--modversion", "sample"], b"2.3"),
                ("transitive", ["--libs", "sample"], b"-lfixture_sample -lfixture_base"),
                ("variable", ["--variable=prefix", "sample"], b"C:/native fixture"),
            ):
                value = execute(name, [executable, *options], child_env=child).strip()
                if value != expected:
                    raise ContractError(f"Wrong pkgconf {name} result: {value!r}")
            execute("missing", [executable, "--exists", "absent-native-fixture"], expected=1, child_env=child)
            execute("unsatisfied-version", [executable, "--exists", "sample >= 3.0"], expected=1, child_env=child)
        execute("stage-native", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                                 "-Root", stage, "-ReportPath", args.output / "stage-native.json"])
        verify_support(support, compiler, args.prefix, env)
        verify_tree(args.source, args.manifest)
        verify_tree(args.meson.parent, args.meson_manifest)
        if args.dependencies and inventory(args.dependencies) != dependency_files:
            raise ContractError("Meson dependency prefix changed")
        if any(digest(path) != value for path, value in tools.items()):
            raise ContractError("Native build driver changed")
        report["files"] = inventory(stage)
        if args.package == "libpsl":
            required = ("bin/libpsl-5.dll", "lib/libpsl.dll.a") if args.variant == "shared" else ("lib/libpsl.a",)
            if any(name not in report["files"] for name in required):
                raise ContractError("Requested PSL library profile was not installed")
        report["status"] = ("native-pkgconf-built-upstream-and-independent-controls-passed" if args.package == "pkgconf"
                            else "native-libpsl-built-upstream-tested-public-api-pending")
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
