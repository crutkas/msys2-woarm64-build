"""Build explicit MSYS LP64 dependency profiles with native GCC and a private bootstrap driver."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_msys_jmp_headers, verify_support
from documentation_tools import verify_documentation_driver
from openssl_contracts import validate_abi
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree

PROFILES = {
    "xz-msys": {"id": "xz", "version": "5.8.3",
                "required": ["bin/msys-lzma-5.dll", "bin/xz.exe", "bin/xzdec.exe",
                             "bin/lzmadec.exe", "bin/lzmainfo.exe", "include/lzma.h",
                             "lib/liblzma.a", "lib/liblzma.dll.a", "lib/pkgconfig/liblzma.pc",
                             "share/doc/xz/api/index.html"],
                "limitations": []},
    "gettext-msys": {"id": "gettext-msys", "version": "0.22.5",
                     "required": ["bin/msys-intl-8.dll", "bin/msys-gettextpo-0.dll", "bin/msys-asprintf-0.dll",
                                  "bin/gettext.exe", "bin/msgfmt.exe", "bin/msgmerge.exe", "bin/xgettext.exe",
                                  "include/libintl.h", "include/gettext-po.h",
                                  *[f"lib/lib{name}{suffix}" for name in ("intl", "gettextpo", "asprintf")
                                    for suffix in (".a", ".dll.a")]],
                     "limitations": ["Pinned package disables styled gettext-tools, Java, C#, Emacs and OpenMP integrations"]},
    "zlib-msys": {"id": "zlib", "version": "1.3.2", "libtool": False,
                  "required": ["bin/msys-z.dll", "include/zlib.h", "lib/libz.a", "lib/libz.dll.a"],
                  "limitations": []},
    "libxcrypt": {"id": "libxcrypt", "version": "4.5.2",
                  "required": ["bin/msys-crypt-2.dll", "include/crypt.h", "lib/libcrypt.a", "lib/libcrypt.dll.a"],
                  "limitations": []},
    "libiconv-bootstrap": {"id": "libiconv", "version": "1.19",
                          "required": ["bin/msys-iconv-2.dll", "bin/msys-charset-1.dll",
                                       "include/iconv.h", "lib/libiconv.a", "lib/libiconv.dll.a"],
                          "limitations": ["Encoder CLI NLS explicitly disabled until native MSYS libintl exists"]},
}


def validate_source(profile, record):
    expected = PROFILES[profile]
    generator = record.get("libtool_dependency")
    if (record["source"]["id"] != expected["id"] or record["source"]["version"] != expected["version"]
            or record.get("dependency_abi") != "MSYS runtime; MinGW/UCRT libraries are not substitutes"):
        raise ContractError("The prepared MSYS source does not match this library profile")
    if expected.get("libtool", True) and (not isinstance(generator, dict) or
            not re.fullmatch(r"[0-9a-f]{64}", generator.get("manifest_sha256", ""))):
        raise ContractError("MSYS library preparation requires the bound MSYS-aware generator")
    policy = record.get("build_policy")
    if profile == "xz-msys" and (not isinstance(policy, dict) or policy.get("windows_doxygen_paths") is not True):
        raise ContractError("Native XZ documentation requires the explicit Windows-path source preparation")


def validate_dependency(profile, files):
    if profile == "gettext-msys":
        required = ("usr/include/iconv.h", "usr/lib/libiconv.dll.a", "usr/bin/msys-iconv-2.dll")
        if any(name not in files for name in required):
            raise ContractError("MSYS gettext requires a complete native MSYS iconv development stage")
    if profile == "xz-msys":
        required = ("usr/include/iconv.h", "usr/lib/libiconv.dll.a", "usr/bin/msys-iconv-2.dll",
                    "usr/include/libintl.h", "usr/lib/libintl.dll.a", "usr/bin/msys-intl-8.dll")
        if any(name not in files for name in required):
            raise ContractError("Full MSYS XZ requires native iconv and gettext development inputs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PROFILES, required=True)
    for name in ("source", "manifest", "prefix", "compiler-receipt", "bootstrap", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    parser.add_argument("--native-job-prefix", type=Path, required=True)
    parser.add_argument("--dependency-stage", type=Path)
    parser.add_argument("--dependency-manifest", type=Path)
    parser.add_argument("--documentation-driver", type=Path)
    parser.add_argument("--documentation-manifest", type=Path)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a new dependency build root are required")
    verify_tree(args.source, args.manifest)
    validate_source(args.package, json.loads(args.manifest.read_text()))
    documentation = None
    if args.package == "xz-msys":
        if args.documentation_driver is None or args.documentation_manifest is None:
            raise ContractError("Full MSYS XZ requires its explicit qualified documentation driver")
        documentation = verify_documentation_driver(args.documentation_driver, args.documentation_manifest)
    elif args.documentation_driver is not None or args.documentation_manifest is not None:
        raise ContractError("This library profile does not use the standalone documentation driver")
    if (args.dependency_stage is None) != (args.dependency_manifest is None):
        raise ContractError("Dependency payload and manifest must be provided together")
    dependency = {}
    if args.dependency_stage:
        verify_tree(args.dependency_stage, args.dependency_manifest)
        dependency_record = json.loads(args.dependency_manifest.read_text())
        if dependency_record.get("compiler_receipt_sha256") != digest(args.compiler_receipt):
            raise ContractError("Dependency was not built with this coherent compiler/runtime input")
        dependency = inventory(args.dependency_stage)
    validate_dependency(args.package, dependency)
    verify_driver(args.native_job_prefix)
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    if (Path(producer["prefix"]).resolve() != args.prefix.resolve() or
            producer["source_target"] != {"DataModel": "LP64", "Triple": "aarch64-pc-cygwin",
                                          "Profile": "MSYS", "ThreadModel": "posix"}):
        raise ContractError("Expected an explicit native MSYS LP64/POSIX producer")
    bootstrap = inventory(args.bootstrap / "usr")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "TMP", "TEMP") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.bootstrap / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    env["HOME"] = env["USERPROFILE"] = str(args.output / "home")
    env.update({"WOARM64_NATIVE_PYTHON": sys.executable,
                "WOARM64_NATIVE_PYTHON_SHA256": digest(sys.executable),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output.resolve()),
                "WOARM64_NATIVE_EXIT_DIR": str(args.output.resolve() / "native-exits"),
                "WOARM64_NATIVE_DRIVER_ROOT": str(args.native_job_prefix.resolve())})
    if documentation:
        env["WOARM64_DOCUMENTATION_DRIVER"] = str(args.documentation_driver.resolve())
        env["WOARM64_DOCUMENTATION_MANIFEST"] = str(args.documentation_manifest.resolve())
        env["WOARM64_DOCUMENTATION_EXIT_DIR"] = str(args.output.resolve() / "documentation-exits")
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    definitions = subprocess.run([str(compiler), "-dM", "-E", "-x", "c", "-"], input=b"",
                                 env=env, capture_output=True, check=True).stdout.decode()
    macros = {parts[1]: parts[2] for line in definitions.splitlines()
              if len(parts := line.split(maxsplit=2)) == 3 and parts[0] == "#define"}
    validate_abi("Cygwin-aarch64", macros)
    jmp_header_guard = verify_msys_jmp_headers(compiler, env)
    script = Path(__file__).with_suffix(".sh")
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.package, args.source, args.prefix, args.output, str(args.jobs)]
    if args.dependency_stage:
        command.append(args.dependency_stage)
    report = {"schema": 1, "status": "failed", "package": args.package,
              "source_manifest_sha256": digest(args.manifest),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "driver_sha256": digest(script), "support": support,
              "jmp_header_guard": jmp_header_guard,
              "dependency_manifest_sha256": digest(args.dependency_manifest) if args.dependency_manifest else None,
              "documentation_driver": documentation,
              "command": list(map(str, command)),
              "build_host": "windows-arm64-native-compiler",
              "orchestration": "private-x64-emulated-bootstrap",
              "limitations": PROFILES[args.package]["limitations"]}
    try:
        report["process"] = run_observed(
            command, cwd=args.output.parent, env=env,
            log_path=args.output.with_name(args.output.name + ".launch.log"),
            result_path=args.output.with_name(args.output.name + ".native-job.json"),
            relay_records=args.output / "native-exits", timeout=3600,
            driver_prefix=args.native_job_prefix)
        if not report["process"]["passed"]:
            raise ContractError("Native MSYS library build/check failed; private evidence retained")
        files = inventory(args.output / "stage")
        if any(f"usr/{name}" not in files for name in PROFILES[args.package]["required"]):
            raise ContractError("MSYS library profile did not produce its required payload")
        verify_tree(args.source, args.manifest)
        if args.dependency_stage:
            verify_tree(args.dependency_stage, args.dependency_manifest)
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(support, compiler, args.prefix, env)
        if inventory(args.bootstrap / "usr") != bootstrap:
            raise ContractError("Private bootstrap changed during dependency build")
        if documentation and verify_documentation_driver(args.documentation_driver, args.documentation_manifest) != documentation:
            raise ContractError("Standalone documentation inputs changed")
        report.update({"status": "native-msys-library-built-checked-bootstrap-driver", "files": files,
                       "pending": ["Native process/loaded-library consumer", "Package admission",
                                   "Coherent runtime/library FP metadata closure"]})
    finally:
        args.output.with_name(args.output.name + ".result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
