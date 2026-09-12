"""Build pinned internationalization libraries with native GCC and labeled bootstrap drivers."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


VERSIONS = {"libiconv": "1.19", "libunistring": "1.4.2", "libidn2": "2.3.8",
            "libpsl": "0.21.5", "gettext-runtime": "1.0"}
REQUIRED_HEADERS = {
    "libiconv": (),
    "libunistring": ("include/iconv.h",),
    "gettext-runtime": ("include/iconv.h",),
    "libidn2": ("include/iconv.h", "include/unistr.h", "include/uninorm.h", "include/libintl.h"),
    "libpsl": ("include/iconv.h", "include/unistr.h", "include/idn2.h"),
}
REQUIRED_LIBRARIES = {
    "libiconv": (),
    "libunistring": ("iconv",),
    "gettext-runtime": ("iconv",),
    "libidn2": ("iconv", "unistring", "intl"),
    "libpsl": ("iconv", "unistring", "idn2"),
}
OUTPUT_LIBRARIES = {
    "libiconv": {"iconv": "libiconv-2.dll", "charset": "libcharset-1.dll"},
    "libunistring": {"unistring": "libunistring-5.dll"},
    "gettext-runtime": {"intl": "libintl-8.dll", "asprintf": "libasprintf-0.dll"},
    "libidn2": {"idn2": "libidn2-0.dll"},
    "libpsl": {"psl": "libpsl-5.dll"},
}


def validate_outputs(package, profile, files):
    required = []
    for library, dll in OUTPUT_LIBRARIES[package].items():
        if profile in ("both", "shared"):
            required.extend((f"bin/{dll}", f"lib/lib{library}.dll.a"))
        if profile in ("both", "static-bootstrap"):
            required.append(f"lib/lib{library}.a")
    missing = [path for path in required if path not in files]
    if missing:
        raise ContractError(f"Requested library profile was not produced: {missing}")


def validate_inputs(package, identity, dependency_files):
    if (identity["id"] != ("gettext" if package == "gettext-runtime" else package)
            or identity["version"] != VERSIONS[package]):
        raise ContractError("Package/source version differs from the maintained recipe")
    missing = [path for path in REQUIRED_HEADERS[package] if path not in dependency_files]
    missing.extend(f"lib/lib{name}.a or lib/lib{name}.dll.a" for name in REQUIRED_LIBRARIES[package]
                   if not any(f"lib/lib{name}{suffix}" in dependency_files for suffix in (".a", ".dll.a")))
    if missing:
        raise ContractError(f"Required dependencies missing; refusing implicit feature loss: {missing}")


def build(package, source, manifest, prefix, msys, output, dependencies, jobs, profile="both"):
    if package not in ("libiconv", "libunistring", "libidn2", "libpsl", "gettext-runtime") or not 1 <= jobs <= 8:
        raise ContractError("Supported package and explicit 1-8 job allocation required")
    if profile not in ("both", "shared", "static-bootstrap"):
        raise ContractError("Unknown library profile")
    if package == "libidn2" and profile == "both":
        raise ContractError("libidn2 requires separate shared/static configurations and static-specific defines")
    source, manifest, prefix, msys, output, dependencies = map(lambda p: Path(p).resolve(),
        (source, manifest, prefix, msys, output, dependencies))
    if os.name != "nt" or output.exists():
        raise ContractError("Requires Windows and a new output")
    verify_tree(source, manifest)
    source_record = json.loads(manifest.read_text())
    identity = source_record["source"]
    dep_files = inventory(dependencies) if any(dependencies.iterdir()) else {}
    validate_inputs(package, identity, dep_files)
    env = {name: os.environ[name] for name in (
        "SystemRoot", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "PATHEXT", "TEMP", "TMP") if name in os.environ}
    env["HOME"] = env["USERPROFILE"] = str(output / "home")
    env.update({"MSYSTEM": "MSYS", "MSYS2_PATH_TYPE": "minimal", "CHERE_INVOKING": "1",
                "PATH": str(prefix / "bin") + os.pathsep + str(msys / "usr/bin") +
                        os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")})
    compiler = prefix / "bin/gcc.exe"
    support = support_identities(compiler, prefix, env)
    libraries = {}
    for name in ("crt2.o", "libgcc.a", "libmingw32.a", "libmingwex.a", "libucrt.a", "libadvapi32.a"):
        resolved = subprocess.run([str(compiler), f"-print-file-name={name}"], env=env,
                                  capture_output=True, check=True).stdout.decode().strip()
        path = Path(resolved).resolve()
        if not Path(resolved).is_absolute() or not path.is_file() or not path.is_relative_to(prefix):
            raise ContractError(f"Missing native link input: {name}")
        libraries[name] = {"path": str(path), "sha256": digest(path)}
    scripts = Path(__file__).with_suffix(".sh")
    tools = {str(p): digest(p) for p in (compiler, prefix / "bin/ar.exe", prefix / "bin/ranlib.exe",
                                       msys / "usr/bin/bash.exe", msys / "usr/bin/make.exe")}
    command = [str(msys / "usr/bin/bash.exe"), "--noprofile", "--norc", scripts.as_posix(),
               package, str(source), str(prefix), str(output), str(jobs), str(dependencies), profile]
    report = {"schema": 1, "package": package, "source": identity, "status": "failed",
              "build_host": "windows-arm64-native-compiler", "orchestration": "windows-x64-emulated-msys",
              "environment_policy": "minimal Windows/bootstrap variables; private HOME; no inherited credentials",
              "profile": profile, "pending_shared_package": profile == "static-bootstrap",
              "pending_static_package": profile == "shared",
              "source_manifest_sha256": digest(manifest), "support_tools": support,
              "source_preparation": ("recorded-package-regeneration" if "generation_commands" in source_record
                                     else "official-release-build-system"),
              "tools": tools, "dependencies": dep_files, "script_sha256": digest(scripts),
              "link_inputs": libraries,
              "command": command}
    try:
        if package in ("gettext-runtime", "libidn2"):
            archive = libraries["libadvapi32.a"]["path"]
            dump = subprocess.run([str(prefix / "bin/objdump.exe"), "-f", archive], env=env,
                                  capture_output=True, check=True)
            output.with_name(output.name + ".advapi32-archive.txt").write_bytes(dump.stdout)
            text = dump.stdout.decode()
            architectures = re.findall(r"^architecture: ([^,]+),", text, re.MULTILINE)
            formats = re.findall(r"file format (\S+)", text)
            if (dump.stderr or not architectures or len(architectures) != len(formats) or
                    any(value != "aarch64" for value in architectures) or
                    any(value != "pe-aarch64-little" for value in formats)):
                raise ContractError("The real advapi32 import archive did not validate as ARM64 COFF")
            report["advapi32_archive_members"] = len(architectures)
            report["deplibs_check_policy"] = "Windows import compatibility policy used by pinned gettext recipe; actual advapi32 import archive independently checked"
        with output.with_name(output.name + ".launch.log").open("xb") as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        report["exit_code"] = result.returncode
        if result.returncode:
            raise ContractError(f"{package} failed; see {output}/build.log")
        verify_support(support, compiler, prefix, env)
        verify_tree(source, manifest)
        current = inventory(dependencies) if any(dependencies.iterdir()) else {}
        if current != dep_files or any(digest(p) != value for p, value in tools.items()):
            raise ContractError("Dependency or tool changed during build")
        if any(digest(row["path"]) != row["sha256"] for row in libraries.values()):
            raise ContractError("Native CRT or compiler library changed during build")
        report["files"] = inventory(output / "stage")
        validate_outputs(package, profile, report["files"])
        report["status"] = "native-library-built-tested-bootstrap-driver"
    finally:
        with output.with_name(output.name + ".result.json").open("x", encoding="utf-8") as dest:
            json.dump(report, dest, indent=2)
            dest.write("\n")
    print(report["status"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", required=True)
    for name in ("source", "manifest", "prefix", "msys", "output", "dependencies"):
        p.add_argument(f"--{name}", required=True, type=Path)
    p.add_argument("--jobs", type=int, required=True)
    p.add_argument("--profile", choices=("both", "shared", "static-bootstrap"), default="both")
    a = p.parse_args()
    build(a.package, a.source, a.manifest, a.prefix, a.msys, a.output, a.dependencies, a.jobs, a.profile)


if __name__ == "__main__":
    main()
