"""Build explicit MSYS LP64 dependency profiles with native GCC and a private bootstrap driver."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import native_job_runner
from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_msys_jmp_headers, verify_support
from documentation_tools import verify_documentation_driver
from db_build_inputs import mutex_customization, require_db_cpp_receipt, validate_db_preparation, verify_db_working_source
from openssl_contracts import validate_abi
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, load_lock, verify_tree
from ssh_bootstrap import directory_names, require_memory
from ssh_build_inputs import validate_preparation

BOOTSTRAP_RECEIPT_SHA256 = "347a9b744efc7918d1ec69855d62c597d5e7d89e9787302ecd04625b84a6372e"
OBSERVER_MANIFEST_SHA256 = "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa"
OBSERVER_HANDOFF_SHA256 = "096ec4b08cb96559d5571d693017d081e2f0b234fa4dea94369fe40cd964acbf"
LIBXCRYPT_PREPARATION_SHA256 = "52c89e7429bbaf2425ae9d58ce95b3a67be6ec7b36cd54dcb45d26db9b68d51d"
APPROVED_CC1_SHA256 = "b8046275497c4e8f4d056530ef2e956d1b7672a0e5eb15ad56fde5bf44e76b0a"
GUARD_PRODUCER_HANDOFF_SHA256 = "a10d72ca0959a24a41eca68f6833ce669b8ab1e5e462920f1d16c2a5ef58e474"
LIBXCRYPT_GUARD_TEST_PATCH_SHA256 = "c676f08ff02447cf98eaf478e1a80620556d9932782acecea63c87d39b0e3253"
LIBXCRYPT_SYMBOL_TEST = "test/symbols-static.pl"
LIBXCRYPT_SYMBOL_TEST_BEFORE = {"sha256": "d1125224216094e9f74c13705877c9d01348b23753215a72caddc4e0f4e63f44", "size": 2633}
LIBXCRYPT_SYMBOL_TEST_AFTER = {"sha256": "42ab33d5587d70e7d46e19c535d423dcf33fa04bac9d0ddfbe327a6004fd0541", "size": 2733}
OBSERVER_ADAPTER_PATH = Path(native_job_runner.__file__).resolve()
LOADED_OBSERVER_ADAPTER_SHA256 = digest(OBSERVER_ADAPTER_PATH)
RETIRED_COMPILER_RECEIPTS = {
    "bd5cbf12484d98243098def7e037c20a41710e88a0eff9d81a0b64501f7d939a",
    "f54f7039d16e546ebc8de7721a85013724f798db9a1679816106171ff7b1b854",
    "150f0d53a5dbf5e2fdac855314f8ab5a674041865c5a359142a58b162f0e946e",
}

PROFILES = {
    "db-msys": {"id": "db", "version": "6.2.32",
                "required": ["bin/msys-db-6.2.dll", "bin/msys-db_cxx-6.2.dll",
                             "bin/db_dump.exe", "bin/db_load.exe", "bin/db_verify.exe",
                             "include/db.h", "include/db_185.h", "include/db_cxx.h",
                             *[f"lib/lib{name}{suffix}" for name in ("db", "db-6.2", "db_cxx", "db_cxx-6.2")
                               for suffix in (".a", ".dll.a")],
                             "share/doc/db/html/index.html", "share/licenses/db/LICENSE"],
                "limitations": ["Pinned recipe disables Java, Tcl and test instrumentation; "
                                "separate upstream and installed API evidence is required"]},
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


def require_seal(path, expected, label):
    if not re.fullmatch("[0-9a-f]{64}", expected or "") or digest(path) != expected:
        raise ContractError(f"{label} seal differs")
    return expected


def validate_bootstrap(record, prefix):
    if (record.get("status") != "private-ssh-bootstrap-byte-identical-not-executed" or
            Path(record.get("prefix", "")).resolve() != Path(prefix).resolve() or
            record.get("source_unchanged") is not True or
            record.get("complete_inventory_equality") is not True or
            record.get("target_or_bootstrap_processes_launched") != 0):
        raise ContractError("Expected the explicitly approved private SSH bootstrap snapshot")


def validate_observer(record):
    if (record.get("status") != "byte-identical-native-test-driver" or
            record.get("source_handoff_sha256") != OBSERVER_HANDOFF_SHA256 or
            set(record.get("files", {})) != {"native-job.py", "native-target-exec.py", "native-target-exec.sh"}):
        raise ContractError("Expected the exact current three-script native observer handoff")


def require_approved_cc1(support):
    cc1 = support.get("cc1")
    if not isinstance(cc1, dict) or cc1.get("sha256") != APPROVED_CC1_SHA256:
        raise ContractError("The compiler does not contain the approved protected stack-guard cc1 fix")


def libxcrypt_test_customization(source_record):
    if source_record.get("files", {}).get(LIBXCRYPT_SYMBOL_TEST) != LIBXCRYPT_SYMBOL_TEST_BEFORE:
        raise ContractError("Unexpected pinned libxcrypt static-symbol test input")
    patch = Path(__file__).parent / "patches/libxcrypt-coff-stack-guard-refptr-test.patch"
    require_seal(patch, LIBXCRYPT_GUARD_TEST_PATCH_SHA256, "Narrow COFF stack-guard reference test patch")
    return {"patch": str(patch.resolve()), "patch_sha256": LIBXCRYPT_GUARD_TEST_PATCH_SHA256,
            "file": LIBXCRYPT_SYMBOL_TEST, "before": LIBXCRYPT_SYMBOL_TEST_BEFORE,
            "after": LIBXCRYPT_SYMBOL_TEST_AFTER,
            "scope": "Only the exact compiler-private .refptr.__stack_chk_guard is excluded from public API enumeration; no C source, protection, test or public-symbol checks removed"}


def verify_libxcrypt_working_source(source, source_record):
    expected = dict(source_record["files"])
    expected[LIBXCRYPT_SYMBOL_TEST] = LIBXCRYPT_SYMBOL_TEST_AFTER
    if inventory(source) != expected:
        raise ContractError("Libxcrypt working source changed beyond the exact static-symbol test patch")


def validate_output(output, inputs):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ContractError("A fresh owned native library output is required")
    if any(parent.is_symlink() or parent.is_junction() for parent in output.parents):
        raise ContractError("Native library output may not traverse a link or junction")
    resolved = output.resolve()
    for root in inputs:
        root = Path(root).resolve()
        if resolved.is_relative_to(root) or root.is_relative_to(resolved):
            raise ContractError("Native library output must be disjoint from every sealed input")
    for suffix in (".launch.log", ".result.json", ".native-job.json", ".native-job.stdout", ".native-job.stderr"):
        if output.with_name(output.name + suffix).exists():
            raise ContractError("A native library evidence sidecar already exists")


def launch_environment(args):
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix.resolve() / "bin", args.bootstrap.resolve() / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    root = args.output.resolve()
    env.update({
        "HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
        "TMP": str(root / "temp"), "TEMP": str(root / "temp"), "TMPDIR": str(root / "temp"),
        "XDG_CACHE_HOME": str(root / "cache"), "CCACHE_DIR": str(root / "cache/ccache"),
        "CCACHE_DISABLE": "1", "MAKEFLAGS": "-j1", "MFLAGS": "-j1",
        "OMP_NUM_THREADS": "1", "CMAKE_BUILD_PARALLEL_LEVEL": "1",
        "WOARM64_NATIVE_ARG_CONVERSION": "none",
        "WOARM64_NATIVE_PYTHON": sys.executable,
        "WOARM64_NATIVE_PYTHON_SHA256": digest(sys.executable),
        "WOARM64_NATIVE_TEST_ROOT": str(root),
        "WOARM64_NATIVE_EXIT_DIR": str(root / "native-exits"),
        "WOARM64_NATIVE_DRIVER_ROOT": str(args.native_job_prefix.resolve()),
    })
    return env


def libxcrypt_summary(path):
    text = Path(path).read_text(encoding="utf-8")
    counts = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        values = re.findall(rf"^# {name}:\s+(\d+)\s*$", text, flags=re.M)
        if len(values) != 1:
            raise ContractError(f"Missing or ambiguous upstream libxcrypt {name} result")
        counts[name] = int(values[0])
    if (counts["TOTAL"] != 54 or counts["TOTAL"] != sum(value for name, value in counts.items() if name != "TOTAL")
            or counts["PASS"] < 53 or counts["SKIP"] > 1
            or any(counts[name] for name in ("XFAIL", "FAIL", "XPASS", "ERROR"))):
        raise ContractError("The complete pinned libxcrypt upstream suite did not pass")
    return {"counts": counts, "sha256": digest(path), "scope": "All 54 upstream tests; upstream skips remain explicit"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PROFILES, required=True)
    for name in ("source", "manifest", "prefix", "compiler-receipt", "bootstrap", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--compiler-receipt-sha256", required=True,
                        help="Explicit newly approved compiler seal; never infer an old compiler from a path")
    parser.add_argument("--bootstrap-receipt", type=Path, required=True)
    parser.add_argument("--bootstrap-receipt-sha256", default=BOOTSTRAP_RECEIPT_SHA256)
    parser.add_argument("--jobs", type=int, choices=(1,), required=True)
    parser.add_argument("--native-job-prefix", type=Path, required=True)
    parser.add_argument("--dependency-stage", type=Path)
    parser.add_argument("--dependency-manifest", type=Path)
    parser.add_argument("--documentation-driver", type=Path)
    parser.add_argument("--documentation-manifest", type=Path)
    return parser.parse_args(argv)


def build(args):
    if os.name != "nt" or args.jobs != 1:
        raise ContractError("Windows and the single approved library job are required")
    memory = require_memory()
    require_seal(OBSERVER_ADAPTER_PATH, LOADED_OBSERVER_ADAPTER_SHA256, "Loaded parent observer adapter")
    validate_output(args.output, [args.source, args.prefix, args.bootstrap, args.native_job_prefix,
                                 *([args.dependency_stage] if args.dependency_stage else []),
                                 *([args.documentation_driver] if args.documentation_driver else [])])
    require_seal(args.compiler_receipt, args.compiler_receipt_sha256, "Explicit new compiler receipt")
    if args.compiler_receipt_sha256 in RETIRED_COMPILER_RECEIPTS:
        raise ContractError("Historical compiler receipts are blocked; require the new protected stack-guard fix")
    bootstrap_seal = getattr(args, "bootstrap_receipt_sha256", BOOTSTRAP_RECEIPT_SHA256)
    require_seal(args.bootstrap_receipt, bootstrap_seal, "Approved private SSH bootstrap")
    bootstrap = json.loads(args.bootstrap_receipt.read_text())
    if (bootstrap_seal != BOOTSTRAP_RECEIPT_SHA256
            and bootstrap.get("source_receipt_sha256") != BOOTSTRAP_RECEIPT_SHA256):
        raise ContractError("Private bootstrap copy must retain the approved parent receipt")
    validate_bootstrap(bootstrap, args.bootstrap)
    verify_tree(args.bootstrap, args.bootstrap_receipt)
    if directory_names(args.bootstrap) != bootstrap["directories"]:
        raise ContractError("Private bootstrap directory inventory differs")
    observer_manifest = verify_driver(args.native_job_prefix)
    require_seal(observer_manifest, OBSERVER_MANIFEST_SHA256, "Current native observer")
    validate_observer(json.loads(observer_manifest.read_text()))
    verify_tree(args.source, args.manifest)
    source_record = json.loads(args.manifest.read_text())
    validate_source(args.package, source_record)
    if args.package == "db-msys":
        validate_db_preparation(source_record)
    test_customization = None
    db_customization = mutex_customization(args.source, source_record) if args.package == "db-msys" else None
    if args.package == "libxcrypt":
        require_seal(args.manifest, LIBXCRYPT_PREPARATION_SHA256, "Pinned full-profile libxcrypt source")
        validate_preparation("libxcrypt", source_record, load_lock(Path(__file__).with_name("sources.lock.json")))
        test_customization = libxcrypt_test_customization(source_record)
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
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    if args.package == "db-msys":
        require_db_cpp_receipt(producer)
    if (Path(producer["prefix"]).resolve() != args.prefix.resolve() or
            producer["source_target"] != {"DataModel": "LP64", "Triple": "aarch64-pc-cygwin",
                                          "Profile": "MSYS", "ThreadModel": "posix"}):
        raise ContractError("Expected an explicit native MSYS LP64/POSIX producer")
    memory = min(memory, require_memory())
    env = launch_environment(args)
    if db_customization:
        env["WOARM64_DB_SOURCE_PATCH"] = db_customization["patch"]
        env["WOARM64_DB_SOURCE_PATCH_SHA256"] = db_customization["patch_sha256"]
        env["WOARM64_DB_LIBTOOL_PATCH"] = db_customization["libtool_path_patch"]
        env["WOARM64_DB_LIBTOOL_PATCH_SHA256"] = db_customization["libtool_path_patch_sha256"]
        db_customization["link_probe_sha256"] = digest(Path(__file__).parent / "fixtures/native-db-link-probe.c")
    if test_customization:
        env.update(WOARM64_LIBXCRYPT_TEST_PATCH=test_customization["patch"],
                   WOARM64_LIBXCRYPT_TEST_PATCH_SHA256=test_customization["patch_sha256"],
                   WOARM64_LIBXCRYPT_TEST_AFTER_SHA256=LIBXCRYPT_SYMBOL_TEST_AFTER["sha256"])
    if documentation:
        env["WOARM64_DOCUMENTATION_DRIVER"] = str(args.documentation_driver.resolve())
        env["WOARM64_DOCUMENTATION_MANIFEST"] = str(args.documentation_manifest.resolve())
        env["WOARM64_DOCUMENTATION_EXIT_DIR"] = str(args.output.resolve() / "documentation-exits")
    args.output.mkdir(parents=True)
    for name in ("home", "temp", "cache", "native-exits", "documentation-exits"):
        (args.output / name).mkdir()
    script = Path(__file__).with_suffix(".sh")
    command = [args.bootstrap.resolve() / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.package, args.source.resolve(), args.prefix.resolve(), args.output.resolve(), str(args.jobs)]
    if args.dependency_stage:
        command.append(args.dependency_stage.resolve())
    report = {"schema": 1, "status": "failed", "package": args.package,
              "source_manifest_sha256": digest(args.manifest),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "bootstrap_receipt_sha256": bootstrap_seal,
              "observer_manifest_sha256": OBSERVER_MANIFEST_SHA256,
              "observer_adapter": {"path": str(OBSERVER_ADAPTER_PATH),
                                   "source_sha256_at_import": LOADED_OBSERVER_ADAPTER_SHA256},
              "guard_producer_handoff_sha256": GUARD_PRODUCER_HANDOFF_SHA256,
              "approved_cc1_sha256": APPROVED_CC1_SHA256,
              "working_source_test_customization": test_customization,
              "working_source_db_customization": db_customization,
              "dispatcher_sha256": digest(Path(__file__).with_name("native-msys-test-dispatch.sh")),
              "driver_sha256": digest(script),
              "minimum_free_gib_before_launch": memory,
              "jobs": 1, "nested_jobs": 1, "native_argument_conversion": "none",
              "libxcrypt_test_runtime_directories": (
                  [str(args.output.resolve() / "build/.libs"), str(args.prefix.resolve() / "bin"),
                   str(args.bootstrap.resolve() / "usr/bin")] if args.package == "libxcrypt" else None),
              "dependency_manifest_sha256": digest(args.dependency_manifest) if args.dependency_manifest else None,
              "documentation_driver": documentation,
              "command": list(map(str, command)),
              "build_host": "windows-arm64-native-compiler",
              "orchestration": "private-x64-emulated-bootstrap",
              "limitations": PROFILES[args.package]["limitations"]}
    if args.package == "db-msys":
        report["source_cpp_frontend_delta"] = producer["source_cpp_frontend_delta"]
        report["full_cpp_qualified"] = False
    marker = args.output / "launch-inputs.json"
    with marker.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    env["WOARM64_LIBRARY_LAUNCH_SEAL"] = digest(marker)
    compiler = args.prefix.resolve() / "bin/gcc.exe"
    try:
        support = support_identities(compiler, args.prefix, env)
        report["support"] = support
        require_approved_cc1(support)
        definitions = subprocess.run([str(compiler), "-dM", "-E", "-x", "c", "-"], input=b"",
                                     env=env, capture_output=True, check=True, timeout=30).stdout.decode()
        macros = {parts[1]: parts[2] for line in definitions.splitlines()
                  if len(parts := line.split(maxsplit=2)) == 3 and parts[0] == "#define"}
        validate_abi("Cygwin-aarch64", macros)
        report["jmp_header_guard"] = verify_msys_jmp_headers(compiler, env)
        report["minimum_free_gib_before_launch"] = min(memory, require_memory())
        require_seal(OBSERVER_ADAPTER_PATH, LOADED_OBSERVER_ADAPTER_SHA256, "Loaded parent observer adapter")
        report["process"] = run_observed(
            command, cwd=args.output.resolve().parent, env=env,
            log_path=args.output.resolve().with_name(args.output.name + ".launch.log"),
            result_path=args.output.resolve().with_name(args.output.name + ".native-job.json"),
            relay_records=args.output.resolve() / "native-exits", timeout=3600,
            driver_prefix=args.native_job_prefix)
        if not report["process"]["passed"]:
            raise ContractError("Native MSYS library build/check failed; private evidence retained")
        if args.package == "libxcrypt":
            report["upstream_tests"] = libxcrypt_summary(args.output / "build/test-suite.log")
            verify_libxcrypt_working_source(args.output / "source", source_record)
        if args.package == "db-msys":
            verify_db_working_source(args.output / "source", source_record, db_customization)
        files = inventory(args.output / "stage")
        if any(f"usr/{name}" not in files for name in PROFILES[args.package]["required"]):
            raise ContractError("MSYS library profile did not produce its required payload")
        verify_support(support, compiler, args.prefix, env)
        if documentation and verify_documentation_driver(args.documentation_driver, args.documentation_manifest) != documentation:
            raise ContractError("Standalone documentation inputs changed")
        report.update({"status": "native-msys-library-built-checked-bootstrap-driver", "files": files,
                       "pending": ["Native process/loaded-library consumer", "Package admission",
                                   "Coherent runtime/library FP metadata closure"]})
        if args.package == "db-msys":
            report["status"] = "native-msys-library-built-upstream-checks-pending"
            report["pending"].insert(0, "Separate upstream DB checks including native Tcl test-enabled build")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        integrity_errors = []
        for label, root, manifest in (
            ("source", args.source, args.manifest), ("compiler", args.prefix, args.compiler_receipt),
            ("bootstrap", args.bootstrap, args.bootstrap_receipt),
            ("observer", args.native_job_prefix, observer_manifest),
            *([("dependency", args.dependency_stage, args.dependency_manifest)] if args.dependency_stage else []),
        ):
            try:
                verify_tree(root, manifest)
            except Exception as error:
                integrity_errors.append(f"{label}: {error}")
        for label, path, seal in (
            ("compiler", args.compiler_receipt, args.compiler_receipt_sha256),
            ("bootstrap", args.bootstrap_receipt, bootstrap_seal),
            ("observer", observer_manifest, OBSERVER_MANIFEST_SHA256),
            ("source", args.manifest, report["source_manifest_sha256"]),
        ):
            try:
                require_seal(path, seal, label)
            except Exception as error:
                integrity_errors.append(str(error))
        try:
            if directory_names(args.bootstrap) != bootstrap["directories"]:
                integrity_errors.append("bootstrap directories changed")
        except Exception as error:
            integrity_errors.append(f"bootstrap directories: {error}")
        report["input_integrity_errors"] = integrity_errors
        try:
            current_adapter_sha = digest(OBSERVER_ADAPTER_PATH)
            report["observer_adapter"]["source_sha256_at_exit"] = current_adapter_sha
            report["observer_adapter"]["file_changed_after_import"] = current_adapter_sha != LOADED_OBSERVER_ADAPTER_SHA256
        except OSError as error:
            report["observer_adapter"]["source_read_error_at_exit"] = str(error)
        if integrity_errors:
            report["status"] = "failed"
        args.output.with_name(args.output.name + ".result.json").write_text(json.dumps(report, indent=2) + "\n")
        if integrity_errors:
            raise ContractError("Native library input integrity changed; failure evidence retained")
    print(report["status"])
    return report


def main():
    build(parse_args())


if __name__ == "__main__":
    main()
