"""Exercise real native conversion/translation APIs with exact private loaded modules."""

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

from bash_chain_inputs import ROOT, HERE, fresh
from bounded_process import run
from native_job_runner import noninteractive_error_mode, run_observed
from readline_chain_inputs import SEALS, sealed
from sources import ContractError, digest, verify_tree
from ssh_bootstrap import require_memory, write_json

nls = importlib.import_module("build-bash-nls")
terminal = importlib.import_module("build-readline-chain")
inspect_process = importlib.import_module("test-native-terminal-chain").process_modules


def worker(output):
    record = json.loads((output / "launch.json").read_text())
    env = nls.environment(output, 1)
    binaries = output / "runtime/usr/bin"
    env["PATH"] = str(binaries) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["LC_ALL"] = "C.UTF-8"
    env["LANGUAGE"] = "fr_FR"
    env["NATIVE_NLS_LOCALE_DIR"] = str(output / "locale")
    program = binaries / "probe.exe"
    report = {"passed": False}

    def observe(pid):
        deadline = time.monotonic() + 20
        while not (output / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not (output / "ready").exists():
            raise ContractError("Native NLS API probe did not reach readiness")
        report["native_process"] = inspect_process(pid, program, record["required_modules"])
        if record["linkage"] == "static" and any(
                row["name"].lower().startswith(("msys-iconv", "msys-charset", "msys-intl", "msys-asprintf"))
                for row in report["native_process"]["modules"]):
            raise ContractError("Static NLS API probe loaded a target NLS DLL")
        write_json(output / "loaded-modules.json", report["native_process"])
        (output / "continue").write_bytes(b"go\n")

    try:
        with noninteractive_error_mode(), (output / "probe.log").open("xb") as log:
            report["process"] = run([program, output / "api.json"], cwd=output, env=env,
                                    log=log, timeout=90, on_started=observe)
        report["api"] = json.loads((output / "api.json").read_text())
        report["passed"] = report["process"]["passed"] and report["api"]["passed"] is True
        if not report["passed"]:
            raise ContractError("Native NLS API assertions failed")
    finally:
        write_json(output / "worker-result.json", report)


def main(args):
    output = ROOT / args.output
    fresh(output)
    stage = ROOT / args.stage
    manifest = stage.parent / "stage.inventory.json"
    verify_tree(stage, manifest)
    if json.loads(manifest.read_text())["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Native NLS stage cohort differs")
    dependencies = [ROOT / value for value in args.dependency]
    for dependency in dependencies:
        verify_tree(dependency, dependency.parent / "stage.inventory.json")
    verify_tree(terminal.COMPILER, terminal.COMPILER_RECEIPT)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "sources"):
        (output / name).mkdir()
    binaries = output / "runtime/usr/bin"
    binaries.mkdir(parents=True)
    modules = {}
    for provider in [terminal.COMPILER / "bin", *[p / "usr/bin" for p in dependencies], stage / "usr/bin"]:
        for file in provider.glob("msys-*.dll"):
            target = binaries / file.name
            if target.exists() and digest(target) != digest(file):
                raise ContractError(f"Conflicting NLS DLL providers: {file.name}")
            shutil.copyfile(file, target)
            modules[file.name] = {"path": str(target), "sha256": digest(file)}
    sealed(binaries / "msys-2.0.dll", terminal.RUNTIME_SHA)
    fixture = HERE / ("fixtures/native-asprintf-api.cc" if args.kind == "asprintf" else "fixtures/native-bash-nls.c")
    copied_fixture = output / "sources" / fixture.name
    shutil.copyfile(fixture, copied_fixture)
    env = nls.environment(output, 1)
    static = args.linkage == "static"
    suffix = ".a" if static else ".dll.a"
    flags = ["-O2", "-g", "-Werror", "-fstack-protector-strong",
             "-I" + str(stage / "usr/include"), "-L" + str(stage / "usr/lib")]
    for dependency in dependencies:
        flags += ["-I" + str(dependency / "usr/include"), "-L" + str(dependency / "usr/lib")]
    required = ["msys-2.0.dll"]
    if args.kind == "iconv":
        flags.append("-DPROBE_ICONV")
        libraries = [stage / ("usr/lib/libcharset" + suffix), stage / ("usr/lib/libiconv" + suffix)]
        if static:
            flags += ["-DLIBICONV_STATIC", "-DLIBCHARSET_STATIC"]
        else:
            required += ["msys-iconv-2.dll", "msys-charset-1.dll"]
    elif args.kind == "asprintf":
        libraries = [stage / ("usr/lib/libasprintf" + suffix)]
        if not static:
            required.append("msys-asprintf-0.dll")
    else:
        if not dependencies:
            raise ContractError("libintl proof requires an explicit coherent iconv dependency")
        libraries = [stage / ("usr/lib/libintl" + suffix),
                     dependencies[0] / ("usr/lib/libiconv" + suffix),
                     dependencies[0] / ("usr/lib/libcharset" + suffix)]
        if static:
            flags += ["-DLIBINTL_STATIC", "-DLIBICONV_STATIC", "-DLIBCHARSET_STATIC"]
        else:
            required += ["msys-intl-8.dll", "msys-iconv-2.dll"]
    compiler = terminal.COMPILER / ("bin/g++.exe" if args.kind == "asprintf" else "bin/gcc.exe")
    command = [compiler, *flags, copied_fixture,
               "-o", binaries / "probe.exe", *libraries]
    report = {"schema": 1, "status": "launched", "kind": args.kind, "linkage": args.linkage,
              "pid": os.getpid(), "creation_filetime": terminal.current_birth(), "jobs": 1,
              "command": list(map(str, command)), "stage_manifest_sha256": digest(manifest),
              "compiler_receipt_sha256": SEALS["compiler"], "fixture_sha256": digest(fixture),
              "required_modules": {name: modules[name] for name in required},
              "minimum_free_gib": require_memory()}
    write_json(output / "launch.json", report)
    print(json.dumps({key: report[key] for key in ("pid", "creation_filetime", "kind", "linkage", "command")}), flush=True)
    try:
        with nls.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            if args.kind == "gettext":
                locale = output / "locale/fr_FR/LC_MESSAGES"
                locale.mkdir(parents=True)
                po = output / "sources/native-nls.po"
                shutil.copyfile(HERE / "fixtures/native-nls.po", po)
                catalog = [nls.BOOTSTRAP / "usr/bin/msgfmt.exe", "--check-format",
                           "-o", locale / "native-nls.mo", po]
                checked = run_observed(catalog, cwd=output, env=env, log_path=output / "catalog.log",
                                       result_path=output / "catalog.native-job.json", relay_records=output / "native-exits",
                                       timeout=60, driver_prefix=terminal.OBSERVER)
                if not checked["passed"]:
                    raise ContractError("Frozen build-driver msgfmt did not create the real catalog")
                report["catalog_sha256"] = digest(locale / "native-nls.mo")
            compiled = run_observed(command, cwd=output, env=env, log_path=output / "compile.log",
                                    result_path=output / "compile.native-job.json", relay_records=output / "native-exits",
                                    timeout=120, driver_prefix=terminal.OBSERVER)
            if not compiled["passed"]:
                raise ContractError("Native NLS public API consumer did not compile")
            report["process"] = run_observed([sys.executable, "-B", Path(__file__).resolve(), "--worker", output],
                                             cwd=output, env=env, log_path=output / "observed.log",
                                             result_path=output / "native-job.json", relay_records=output / "native-exits",
                                             timeout=120, driver_prefix=terminal.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native NLS API/process/module proof failed")
        report["api"] = json.loads((output / "worker-result.json").read_text())
        report["status"] = "native-NLS-API-loaded-modules-passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(stage, manifest)
        verify_tree(terminal.COMPILER, terminal.COMPILER_RECEIPT)
        write_json(output / "result.json", report)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--kind", required=True, choices=("iconv", "gettext", "asprintf"))
        parser.add_argument("--stage", required=True)
        parser.add_argument("--dependency", action="append", default=[])
        parser.add_argument("--linkage", required=True, choices=("static", "shared"))
        parser.add_argument("--output", required=True)
        main(parser.parse_args())
