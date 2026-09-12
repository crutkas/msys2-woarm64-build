"""Rebuild explicit POSIX bootstrap profiles with the coherent native Windows-hosted MSYS compiler."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_msys_jmp_headers, verify_support
from native_job_runner import run_observed, verify_driver
from package_posix import finish
from sources import ContractError, digest, inventory, load_lock, verify_tree

PROFILES = {
    "bash": {"recipe": "msys-recipes", "generator": ["autoconf"],
             "required": ["bash", "sh"], "limitations": ["NLS disabled", "Readline disabled"]},
    "coreutils": {"recipe": "msys-upstream-recipes", "generator": ["autoreconf", "-fi"],
                  "required": ["cat", "cp", "env", "mkdir", "mv", "printf", "rm", "sort", "stat"],
                  "limitations": ["NLS disabled", "GMP disabled"]},
    "make": {"recipe": "msys-upstream-recipes",
             "required": ["make"], "limitations": ["NLS disabled", "Guile disabled"]},
}


def validate_prepared(package, record):
    if (record.get("schema") != 1 or record.get("status") != "source-prepared-not-built" or
            record.get("package") != package or record.get("source_id") != package or
            record.get("recipe_id") != PROFILES[package]["recipe"] or
            any(not isinstance(record.get(field), str) or
                not re.fullmatch(r"[0-9a-f]{64}", record[field])
                for field in ("source_manifest_sha256", "recipe_manifest_sha256"))):
        raise ContractError("Expected the exact prepared POSIX source/recipe boundary")
    generator = PROFILES[package].get("generator")
    if generator and not any(isinstance(row, dict) and row.get("command") == generator
                             for row in record.get("generators", [])):
        raise ContractError("The pinned POSIX source regeneration has not been recorded")


def verify_origins(package, record, source_manifest, recipe_manifest, lock):
    validate_prepared(package, record)
    locked = {row["id"]: row for row in load_lock(lock)["sources"]}
    for label, expected_id, path in (("source", package, source_manifest),
                                     ("recipe", PROFILES[package]["recipe"], recipe_manifest)):
        origin = json.loads(Path(path).read_text(encoding="utf-8"))
        if (digest(path) != record[f"{label}_manifest_sha256"] or
                origin.get("source") != locked[expected_id]):
            raise ContractError(f"Prepared POSIX {label} does not match its locked origin inventory")


def validate_output(output, inputs):
    output = Path(output).resolve()
    for path in inputs:
        path = Path(path).resolve()
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ContractError("POSIX output must be separate from every immutable input")
    for path in (output, *(output.with_name(output.name + suffix) for suffix in
                          (".result.json", ".launch.log", ".native-job.json",
                           ".native-job.stdout", ".native-job.stderr"))):
        if path.exists():
            raise ContractError(f"POSIX build requires fresh output and evidence paths: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PROFILES, required=True)
    for name in ("source", "manifest", "source-origin-manifest", "recipe-origin-manifest",
                 "prefix", "compiler-receipt", "bootstrap", "native-job-prefix", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt":
        raise ContractError("Native Windows is required")
    validate_output(args.output, (args.source, args.prefix, args.bootstrap, args.native_job_prefix))
    if not args.output.parent.is_dir():
        raise ContractError("The build-owned output parent must already exist")
    verify_tree(args.source, args.manifest)
    source_record = json.loads(args.manifest.read_text())
    verify_origins(args.package, source_record, args.source_origin_manifest, args.recipe_origin_manifest, args.lock)
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    if (Path(producer["prefix"]).resolve() != args.prefix.resolve() or
            producer["source_target"] != {"DataModel": "LP64", "Triple": "aarch64-pc-cygwin",
                                          "Profile": "MSYS", "ThreadModel": "posix"}):
        raise ContractError("The POSIX bootstrap requires the current coherent native MSYS compiler")
    driver_manifest = verify_driver(args.native_job_prefix)
    bootstrap = inventory(args.bootstrap / "usr")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "TMP", "TEMP") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.prefix / "bin", args.bootstrap / "usr/bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "WOARM64_NATIVE_PYTHON": sys.executable,
                "WOARM64_NATIVE_PYTHON_SHA256": digest(sys.executable),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output.resolve()),
                "WOARM64_NATIVE_EXIT_DIR": str(args.output.resolve() / "native-exits"),
                "WOARM64_NATIVE_DRIVER_ROOT": str(args.native_job_prefix.resolve())})
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    header_guard = verify_msys_jmp_headers(compiler, env)
    script = Path(__file__).resolve().with_suffix(".sh")
    if b"\r" in script.read_bytes():
        raise ContractError("The native POSIX shell driver must use LF line endings")
    identities = {str(path): digest(path) for path in
                  (args.manifest, args.source_origin_manifest, args.recipe_origin_manifest, args.lock,
                   args.compiler_receipt, driver_manifest, Path(__file__), script)}
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.package, args.source, args.prefix, args.output, str(args.jobs)]
    report = {"schema": 1, "status": "failed", "classification": "bootstrap", "package": args.package,
              "target": "aarch64-pc-cygwin", "build_host": "windows-arm64-native-compiler",
              "orchestration": "explicit-private-x64-bootstrap-drivers",
              "source_manifest_sha256": digest(args.manifest), "prepared_source": source_record,
              "compiler_receipt_sha256": digest(args.compiler_receipt), "support": support,
              "input_identities": identities, "approved_jobs": args.jobs,
              "header_guard": header_guard, "recipe_sha256": digest(script),
              "limitations": PROFILES[args.package]["limitations"],
              "command": list(map(str, command))}
    try:
        report["process"] = run_observed(
            command, cwd=args.output.parent, env=env, timeout=7200,
            log_path=args.output.with_name(args.output.name + ".launch.log"),
            result_path=args.output.with_name(args.output.name + ".native-job.json"),
            relay_records=args.output / "native-exits", driver_prefix=args.native_job_prefix)
        if not report["process"]["passed"]:
            raise ContractError("Native POSIX bootstrap compilation/installation failed")
        source = args.output / "source"
        stage = args.output / "stage"
        build = source if args.package == "bash" else args.output / "build"
        if args.package == "bash":
            shutil.copyfile(stage / "usr/bin/bash.exe", stage / "usr/bin/sh.exe")
        finish(args.package, source, stage, build)
        for name in PROFILES[args.package]["required"]:
            if not (stage / f"usr/bin/{name}.exe").is_file():
                raise ContractError(f"Missing actual rebuilt POSIX executable: {name}")
        shutil.copyfile(args.prefix / "bin/msys-2.0.dll", stage / "usr/bin/msys-2.0.dll")
        for relative in ("tmp", "var/tmp", "etc"):
            (stage / relative).mkdir(parents=True, exist_ok=True)
        report.update({"status": "native-posix-bootstrap-built-not-accepted", "files": inventory(stage),
                       "required_directories": ["tmp", "var/tmp", "etc"],
                       "pending": ["Native PE/loadable inventory", "Native functional and loaded-runtime fixtures",
                                   "Full-feature rebuild and upstream suite", "Package admission"]})
    finally:
        try:
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("A POSIX build manifest or driver changed")
            verify_tree(args.source, args.manifest)
            verify_tree(args.prefix, args.compiler_receipt)
            verify_driver(args.native_job_prefix)
            verify_support(support, compiler, args.prefix, env)
            if inventory(args.bootstrap / "usr") != bootstrap:
                raise ContractError("Private bootstrap inputs changed")
            report["inputs_unchanged"] = True
        except (ContractError, OSError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            with args.output.with_name(args.output.name + ".result.json").open("x", encoding="utf-8", newline="\n") as out:
                json.dump(report, out, indent=2)
                out.write("\n")
    print(report["status"])


if __name__ == "__main__":
    main()
