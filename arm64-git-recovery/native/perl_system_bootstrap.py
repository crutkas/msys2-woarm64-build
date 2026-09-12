"""Fail-closed preflight for the explicit supported-system-symlink Perl profile; no nativestrict qualification."""

import argparse
import json
import os
from pathlib import Path
import shutil
import struct

from bounded_process import run
from compiler_tools import support_identities, verify_support, verify_msys_jmp_headers
from perl_profiles import SYSTEM_PROFILE, profile_record, require_system_environment
from perl_system_inputs import bound_json, copy_cohort, require_separate_output, verify_cohort
from sources import ContractError, digest, inventory


def native_machine(path):
    with Path(path).open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ContractError("A native Perl build driver is not a PE image")
        offset = struct.unpack_from("<I", header, 60)[0]
        stream.seek(offset)
        pe = stream.read(26)
    if offset < 64 or len(pe) != 26 or pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0xAA64:
        raise ContractError("Alternative Perl may not silently use an emulated build driver")


def environment(native, compiler, output):
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT")
           if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (native / "usr/bin", compiler / "bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                "TMP": str(output / "temp"), "TEMP": str(output / "temp"),
                "MSYS": "winsymlinks:sys", "MSYSTEM": "CYGWIN", "LC_ALL": "C"})
    require_system_environment(env)
    return env


def compiler_boundary(cohort, output, jobs):
    native, compiler = Path(cohort["native_root"]), Path(cohort["compiler_root"])
    bash, gcc = native / "usr/bin/bash.exe", compiler / "bin/gcc.exe"
    scripts = Path(__file__).parent.resolve()
    for name in (bash, gcc, native / "usr/bin/ln.exe", native / "usr/bin/test.exe"):
        native_machine(name)
    for name in ("home", "temp"):
        (output / name).mkdir()
    env = environment(native, compiler, output)
    support = support_identities(gcc, compiler, env)
    guard = verify_msys_jmp_headers(gcc, env)
    report = {"schema": 1, "status": "failed", **profile_record(SYSTEM_PROFILE),
              "scope": "Current native MSYS POSIX symlinks and UCRT-hosted GCC source/header link compatibility",
              "runtime_sha256": cohort["runtime_sha256"], "jobs": jobs, "support": support,
              "jump_header_guard": guard, "commands": []}

    def execute(name, argv):
        log = output / f"{name}.log"
        with log.open("xb") as stream:
            result = run(argv, cwd=output, env=env, log=stream, timeout=60)
        report["commands"].append({"name": name, "command": list(map(str, argv)), "process": result,
                                   "log": str(log), "log_sha256": digest(log)})
        return result, log

    try:
        process, log = execute("native-architecture", [bash, "--noprofile", "--norc",
                               (scripts / "perl-native-arch-guard.sh").as_posix(), native.as_posix()])
        if not process["passed"] or log.read_text().strip() not in ("aarch64", "arm64"):
            raise ContractError("The existing native Perl architecture guard failed")
        process, log = execute("system-symlinks", [bash, "--noprofile", "--norc",
                               (scripts / "perl-system-symlink-check.sh").as_posix(),
                               (output / "symlinks").as_posix()])
        if not process["passed"] or "PERL_SYSTEM_SYMLINKS=PASS" not in log.read_text():
            raise ContractError("The explicit supported MSYS POSIX symlink prerequisite failed")
        report["native_posix_symlinks"] = "passed"
        compile_root = output / "compiler-links"
        compile_root.mkdir()
        for source, target in (("perl-system-link-control.c", "regular.c"),
                               ("perl-system-link-control.h", "target.h"),
                               ("perl-system-linked-header-control.c", "header-control.c")):
            shutil.copyfile(scripts / "fixtures" / source, compile_root / target)
        process, _ = execute("create-compiler-links", [bash, "--noprofile", "--norc",
                             (scripts / "perl-system-compiler-links.sh").as_posix(), compile_root.as_posix()])
        if not process["passed"]:
            raise ContractError("The exact source/header link controls could not be created")
        results = {}
        for name, source in (("regular", "regular.c"), ("linked-source", "linked-source.c"),
                             ("linked-header", "header-control.c")):
            object_path = compile_root / f"{name}.o"
            result, _ = execute(name, [gcc, "-O2", "-g", "-fwrapv", "-c", compile_root / source,
                                      "-o", object_path])
            results[name] = {"passed": result["passed"], "raw_exit": result["exit"]}
            if result["passed"]:
                if not object_path.is_file() or object_path.read_bytes()[:2] != b"\x64\xaa":
                    raise ContractError("Compiler control did not emit an actual ARM64 COFF object")
                results[name]["object_sha256"] = digest(object_path)
            elif name == "regular":
                raise ContractError("The ordinary current-compiler control failed before testing linked inputs")
        report["compiler_link_results"] = results
        report["system_link_file_bytes"] = {
            name: {"sha256": digest(compile_root / name),
                   "header_hex": (compile_root / name).read_bytes()[:96].hex()}
            for name in ("linked-source.c", "linked-header.h")}
        report["compiler_accepts_system_symlinks"] = all(row["passed"] for row in results.values())
        report["status"] = ("system-symlink-compiler-boundary-passed" if report["compiler_accepts_system_symlinks"]
                            else "blocked-system-symlinks-not-readable-by-native-compiler")
    finally:
        try:
            verify_support(support, gcc, compiler, env)
            if inventory(compiler) != cohort["compiler_files"] or inventory(native) != cohort["native_files"]:
                raise ContractError("Current native Perl cohort changed during the bounded control")
            report["inputs_unchanged"] = True
        except (ContractError, OSError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            with (output / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-spec", type=Path, help="Hash-bound current published inputs; copied to a fresh owned cohort")
    source.add_argument("--cohort", type=Path, help="An existing exact owned current-cohort receipt")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2), required=True)
    parser.epilog = ("This explicit profile currently stops at compiler/source-link compatibility. "
                     "A passing POSIX link probe alone is not Configure, miniperl, XS, or upstream-test qualification.")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if os.name != "nt" or output.exists():
        raise ContractError("The alternative Perl profile requires Windows and a fresh evidence root")
    if args.input_spec:
        spec = json.loads(args.input_spec.read_text(encoding="utf-8"))
        require_separate_output(output, [bound_json(spec["compiler"])["prefix"],
                                        bound_json(spec["utility_admission"])["stage"], spec["source"]["root"],
                                        *[row["root"] for row in spec.get("dependencies", [])]])
        output.mkdir(parents=True)
        cohort = copy_cohort(spec, output / "cohort")
    else:
        cohort = verify_cohort(args.cohort)
        require_separate_output(output, [cohort["native_root"], cohort["compiler_root"], cohort["spec"]["source"]["root"]])
        output.mkdir(parents=True)
    result = compiler_boundary(cohort, output, args.jobs)
    print(result["status"])
    if not result.get("compiler_accepts_system_symlinks"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
