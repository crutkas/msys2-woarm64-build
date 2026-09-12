"""Run bounded upstream DB checks or independent installed native API fixtures."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time

from db_build_inputs import require_db_cpp_receipt
from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

CXX_RELAY_PATCH_SEAL = "3381a6ee276ad8f48739663111aed1d58824419ee5f292c846235b4f0979ab13"
QUEUE_PATCH_SEAL = "fa91992db2819804a861bc774778b4dc3d778b94417d107d687f228da65670bd"
QUEUE_SOURCE_BEFORE = "db02ace2008b8c1c7b27fbd8afba5e8ff2d253d21985d6e32c5bd0c04f42a9ad"
QUEUE_SOURCE_AFTER = "b8e0adf5a7506cf58c4f1764205ed848b71f99fac29f2d1bc26ccca97b91846f"


def observe(command, cwd, env, output, name, driver, timeout=120):
    require_memory()
    print(json.dumps({"phase": name, "launcher_pid": os.getpid(),
                      "command": list(map(str, command)), "output": str(output)}), flush=True)
    process = run_observed(command, cwd=cwd, env=env, log_path=output / (name + ".log"),
                           result_path=output / (name + ".native-job.json"),
                           relay_records=output / "native-exits", timeout=timeout, driver_prefix=driver)
    evidence = json.loads((output / (name + ".native-job.json")).read_text())
    return {"command": list(map(str, command)), "cwd": str(cwd), "process": process, "evidence": evidence}


def environment(prefix, output, bootstrap=None):
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if k in os.environ}
    paths = [prefix / "bin"]
    if bootstrap:
        paths.append(bootstrap / "usr/bin")
    paths.append(Path(os.environ["SystemRoot"]) / "System32")
    env.update(PATH=os.pathsep.join(map(str, paths)), HOME=str(output), USERPROFILE=str(output),
               TMP=str(output), TEMP=str(output), TMPDIR=str(output), MAKEFLAGS="-j1", MFLAGS="-j1",
               OMP_NUM_THREADS="1", CMAKE_BUILD_PARALLEL_LEVEL="1", CCACHE_DISABLE="1",
               WOARM64_NATIVE_TEST_ROOT=str(output), WOARM64_NATIVE_ARG_CONVERSION="none",
               WOARM64_NATIVE_EXIT_DIR=str(output / "native-exits"), WOARM64_NATIVE_PYTHON=sys.executable,
               WOARM64_NATIVE_PYTHON_SHA256=digest(sys.executable))
    return env


def require_exit(row, executable, code=0):
    matches = [e for e in row["evidence"]["native_target_exits"]
               if Path(e["executable"]).resolve() == executable.resolve()]
    if (len(matches) != 1 or not matches[0].get("created")
            or row["evidence"]["created_processes"] != row["evidence"]["observed_processes"]
            or row["process"]["timed_out"]):
        raise ContractError(f"Missing complete generation-bound raw exit for {executable}")
    if code is not None and matches[0]["raw_exit"] != code:
        raise ContractError(f"Native fixture {executable} exited {matches[0]['raw_exit']:#x}; expected {code:#x}")
    return matches[0]


def installed(args, report):
    output, stage = args.output, args.build / "stage"
    relocated = output / "relocated"
    shutil.copytree(stage, relocated)
    verify_tree(relocated, args.build_result)
    runtime = output / "runtime"
    runtime.mkdir()
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", runtime / "msys-2.0.dll")
    env = environment(args.prefix, output)
    fixture_root = Path(__file__).parent / "fixtures"
    compiled = {}
    for name, source, library in (
        ("c", "native-db-consumer.c", "db"),
        ("cpp", "native-db-consumer.cpp", "db_cxx"),
        ("compat185", "native-db-185.c", "db"),
        ("raw-exit", "native-db-raw-exit.c", None),
    ):
        compiler = args.prefix / ("bin/g++.exe" if name == "cpp" else "bin/gcc.exe")
        exe = output / (name + ".exe")
        command = [compiler, "-O2", "-g", "-Werror", "-fstack-protector-strong",
                   "-I" + str(relocated / "usr/include"), fixture_root / source,
                   "-L" + str(relocated / "usr/lib"), "-Wl,--no-insert-timestamp", "-o", exe]
        if library:
            command.append("-l" + library)
        row = observe(command, output, env, output, "compile-" + name, args.native_job_prefix)
        report["commands"]["compile-" + name] = row
        report["fixture_sources"][source] = digest(fixture_root / source)
        if not row["process"]["passed"]:
            raise ContractError(f"Installed API fixture compilation failed: {name}")
        compiled[name] = exe
    env["PATH"] = os.pathsep.join(map(str, (relocated / "usr/bin", runtime,
                                           Path(os.environ["SystemRoot"]) / "System32")))
    capture = Path(__file__).with_name("capture-native-exception.py")
    errors = []
    for name, executable_name, dll, marker, arguments in (
        ("c", "c", "msys-db-6.2.dll", b"DB C PASS:", []),
        ("cpp-data", "cpp", "msys-db_cxx-6.2.dll", b"DB C++ DATA PASS:", ["data-only"]),
        ("compat185", "compat185", "msys-db-6.2.dll", b"DB 185 PASS:", []),
    ):
        exe = compiled[executable_name]
        row = observe([sys.executable, "-B", capture, "--executable", exe,
                       "--path-directory", relocated / "usr/bin", "--runtime-directory", runtime,
                       "--output", output / ("capture-" + name), *arguments],
                      output, env, output, name, args.native_job_prefix, 60)
        report["commands"][name] = row
        evidence = json.loads((output / ("capture-" + name) / "result.json").read_text())
        loaded = {}
        for module in evidence["modules"]:
            path = Path(module["path"].removeprefix("\\\\?\\")).resolve()
            loaded[path.name.lower()] = {"path": str(path), "sha256": digest(path)}
        case = {"status": "failed", "loaded_modules": loaded, "capture_sha256": digest(
            output / ("capture-" + name) / "result.json")}
        report["api"][name] = case
        try:
            case["native_exit"] = require_exit(row, exe, None)
            for path in (exe, runtime / "msys-2.0.dll", relocated / "usr/bin" / dll):
                expected = {"path": str(path.resolve()), "sha256": digest(path)}
                if loaded.get(path.name.lower()) != expected:
                    raise ContractError(f"Native fixture did not load the exact private module: {path}")
            for module in loaded.values():
                path = Path(module["path"])
                if not path.is_relative_to(output) and not path.is_relative_to(Path(os.environ["SystemRoot"])):
                    raise ContractError(f"Unexpected loaded non-system module: {path}")
            case["exact_modules_verified"] = True
            require_exit(row, exe)
            if (not row["process"]["passed"] or evidence["exit_code"] != 0 or evidence["timed_out"]
                    or evidence["exception_limit_reached"]):
                raise ContractError(f"Installed API fixture failed: {name}")
            if marker not in (output / ("capture-" + name) / "stdout.bin").read_bytes():
                raise ContractError(f"Missing successful API assertion marker: {name}")
            case["status"] = "passed"
        except ContractError as error:
            case["error"] = str(error)
            errors.append(name)
    for name, command, expected in (
        ("negative-direct", [compiled["raw-exit"]], 1536),
        ("negative-relay", [sys.executable, "-I", args.native_job_prefix / "native-target-exec.py",
                            compiled["raw-exit"]], 255),
    ):
        row = observe(command, output, env, output, name, args.native_job_prefix, 30)
        report["commands"][name] = row
        require_exit(row, compiled["raw-exit"], 1536)
        if row["process"]["passed"] or row["process"]["exit"] != expected:
            raise ContractError("High-exit negative was not preserved as a failure")
    report["negative_controls"] = "raw1536 rejected directly and preserved through relay as portable255"
    # Debugger interception changes GCC's exception path; qualify the real path with a held process.
    held_args = argparse.Namespace(**{**vars(args), "installed_input": output})
    cpp_held(held_args, report)
    report["api"]["cpp-exception"] = {"status": "passed", "native_exit": report["native_exit"],
                                     "exact_modules_verified": True, "observer": "ordinary held process, no debugger"}
    report["relocated_files"] = inventory(relocated)
    verify_tree(relocated, args.build_result)
    if errors:
        report["status"] = "installed-native-db-api-partial-failed"
        raise ContractError(f"Installed native API cases failed: {errors}; independent cases and negative controls retained")
    report["status"] = "installed-native-db-c-cpp-185-api-and-exact-modules-passed"


def build_queue_suite(args, env, report):
    build, source, output = args.build / "build", args.build / "source", args.output
    original = source / "test/c/suites/TestQueue.c"
    patch = Path(__file__).parent / "patches/db-6.2.32-queue-test-shared-region.patch"
    if digest(original) != QUEUE_SOURCE_BEFORE or digest(patch) != QUEUE_PATCH_SEAL:
        raise ContractError("Unexpected upstream shared-queue fixture or reviewed adaptation")
    copied = output / "TestQueue.c"
    shutil.copyfile(original, copied)
    command = [args.bootstrap / "usr/bin/patch.exe", "--batch", "--forward", "--fuzz=0",
               "--no-backup-if-mismatch", "-p1", "-d", output, "-i", patch]
    row = observe(command, output, env, output, "queue-source", args.native_job_prefix)
    report["commands"]["queue-source"] = row
    if not row["process"]["passed"] or digest(copied) != QUEUE_SOURCE_AFTER:
        raise ContractError("Test-only queue adaptation did not match the reviewed bytes")
    flags = ["-O2", "-g", "-fstack-protector-strong", "-Wno-incompatible-pointer-types",
             "-D_GNU_SOURCE", "-D_REENTRANT", "-DDLL_EXPORT", "-DPIC"]
    includes = [build, source / "src", source / "test/c/cutest", source / "test/c/suites", source / "test/c/common"]
    command = [args.prefix / "bin/gcc.exe", *flags, *["-I" + str(path) for path in includes],
               "-c", copied, "-o", output / "TestQueue.o"]
    row = observe(command, output, env, output, "queue-compile", args.native_job_prefix)
    report["commands"]["queue-compile"] = row
    if not row["process"]["passed"]:
        raise ContractError("Shared-region queue fixture compilation failed")
    names = (build / "Makefile").read_text().split("CUTEST_OBJS=", 1)[1].split("\n\n", 1)[0].replace("\\\n", " ").split()
    objects = [output / "TestQueue.o" if name == "TestQueue.lo" else build / ".libs" / name.replace(".lo", ".o")
               for name in names]
    if len(objects) != 16 or any(not path.is_file() for path in objects):
        raise ContractError("The exact upstream CuTest object set is incomplete")
    identities = {str(path): digest(path) for path in objects}
    executable = output / "cutest.exe"
    command = [args.prefix / "bin/gcc.exe", "-Wl,--no-insert-timestamp", "-o", executable, *objects,
               args.build / "stage/usr/lib/libdb-6.2.dll.a", "-lm", "-lpthread"]
    row = observe(command, output, env, output, "queue-link", args.native_job_prefix)
    report["commands"]["queue-link"] = row
    if not row["process"]["passed"]:
        raise ContractError("The complete native CuTest fixture failed to link")
    report["queue_adaptation"] = {
        "patch": str(patch), "patch_sha256": QUEUE_PATCH_SEAL, "source_before": QUEUE_SOURCE_BEFORE,
        "source_after": QUEUE_SOURCE_AFTER, "object_identities": identities,
        "scope": "Only test allocation uses one shared region; all 136 queue checks, optimization and protections retained"}
    return executable


def upstream(args, report):
    output, build = args.output, args.build / "build"
    env = environment(args.prefix, output, args.bootstrap)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(args.build.parent)
    env["WOARM64_NATIVE_DRIVER_ROOT"] = str(args.native_job_prefix)
    script = ('set -euo pipefail; export PATH="$(cygpath -u "$1")/bin:/usr/bin"; '
              'cd "$(cygpath -u "$2")/build"; exec make -k -j1 cutest test_mutex test_micro')
    row = observe([args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", "-c", script,
                   "db-upstream-build", args.prefix, args.build],
                  output, env, output, "build-upstream", args.native_job_prefix, 900)
    report["commands"]["build-upstream"] = row
    report["upstream_build_passed"] = row["process"]["passed"]
    suites_source = args.build / "source/test/c/cutest/CuTests.c"
    names = re.findall(r'\{\s*"(Test\w+)",\s*Run\w+Tests\s*\}', suites_source.read_text())
    if len(names) != 13 or len(set(names)) != 13:
        raise ContractError("Unexpected upstream CuTest suite inventory")
    report["upstream_suite_inventory"] = names
    bodies = re.findall(r"int Run\w+Tests\(CuString \*output\)\n\{(.*?)\n\}", suites_source.read_text(), re.S)
    counts = {}
    for body in bodies:
        match = re.search(r'CuSuiteNew\("(Test\w+)"', body)
        if match:
            counts[match[1]] = len(re.findall(r"SUITE_ADD_TEST\(suite,", body))
    if set(counts) != set(names) or any(count == 0 for count in counts.values()):
        raise ContractError("Missing exact upstream CuTest case counts")
    report["upstream_case_counts"] = counts
    report["upstream_annotated_skip_tests"] = re.findall(
        r"extern int (Test\w+)\(CuTest \*ct\); /\* SKIP \*/", suites_source.read_text())
    env["PATH"] = os.pathsep.join(map(str, (build / ".libs", args.prefix / "bin",
                                           args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    executable = build_queue_suite(args, env, report)
    for name in names:
        if name == "TestMutexAlignment":
            report["upstream"][name] = {"status": "resource-gated",
                "reason": "Unmodified suite spawns up to four worker processes plus wakeup; exceeds grant2"}
            continue
        row = observe([sys.executable, "-I", args.native_job_prefix / "native-target-exec.py",
                       executable, "-s", name], build, env, output, name, args.native_job_prefix, 300)
        report["commands"][name] = row
        observation_error = None
        try:
            require_exit(row, executable, None)
        except ContractError as error:
            observation_error = str(error)
        text = (output / (name + ".log")).read_text(errors="replace")
        summary = re.findall(r"OK \((\d+) tests?\)", text)
        passed = row["process"]["passed"] and summary == [str(counts[name])] and observation_error is None
        report["upstream"][name] = {
            "status": "passed" if passed else "failed", "expected_cases": counts[name],
            "reported_pass_counts": list(map(int, summary)), "observation_error": observation_error,
            "log_sha256": digest(output / (name + ".log"))}
    if any(digest(path) != sha for path, sha in report["queue_adaptation"]["object_identities"].items()):
        raise ContractError("Upstream fixture object identities changed during checks")
    report["status"] = ("native-db-upstream-failed-with-explicit-gates"
                        if not report["upstream_build_passed"]
                        or any(row["status"] == "failed" for row in report["upstream"].values())
                        else "native-db-upstream-partial-with-explicit-gates")
    report["remaining"] = [
        "Unmodified CuTest TestMutexAlignment requires additional nested process quota",
        "Test-enabled native MSYS Tcl build and run_std; run_all is the documented extended suite",
        "test_micro is a benchmark target, built but not a substitute for upstream correctness checks",
    ]


def cxx(args, report):
    output = args.output
    source = args.build / "source/test/cxx"
    copied = output / "cxx"
    shutil.copytree(source, copied)
    before = inventory(source)
    if inventory(copied) != before:
        raise ContractError("Upstream C++ source copy differs")
    patch = Path(__file__).parent / "patches/db-6.2.32-cxx-test-relay.patch"
    if digest(patch) != CXX_RELAY_PATCH_SEAL:
        raise ContractError("The reviewed upstream C++ relay adaptation changed")
    env = environment(args.prefix, output, args.bootstrap)
    (output / "temp").mkdir()
    script = (
        'set -euo pipefail; export PATH="$(/usr/bin/cygpath -u "$3")/stage/usr/bin:'
        '$(/usr/bin/cygpath -u "$1")/bin:/usr/bin"; '
        'export CXX="$(/usr/bin/cygpath -u "$1")/bin/g++.exe"; '
        'export CXXFLAGS="-O2 -g -fstack-protector-strong"; '
        'export TMPDIR="$(/usr/bin/cygpath -u "$2")/temp"; '
        'export WOARM64_DB_TEST_RELAY="$(/usr/bin/cygpath -u "$4")/native-target-exec.sh"; '
        'cd "$(/usr/bin/cygpath -u "$2")/cxx"; '
        '/usr/bin/patch --batch --forward --fuzz=0 -p1 -i "$(/usr/bin/cygpath -u "$5")"; '
        'exec /usr/bin/bash ./testall "--prefix=$(/usr/bin/cygpath -m "$3")/stage/usr"')
    row = observe([args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", "-c", script,
                   "db-cxx-upstream", args.prefix, output, args.build, args.native_job_prefix, patch],
                  output, env, output, "cxx-testall", args.native_job_prefix, 900)
    report["commands"]["cxx-testall"] = row
    names = sorted(path.stem for path in source.glob("*.cpp"))
    report["cxx_sources"] = before
    report["cxx_patch"] = {"path": str(patch), "sha256": digest(patch),
                         "testone_before_sha256": before["testone"]["sha256"],
                         "testone_after_sha256": digest(copied / "testone"),
                         "scope": "Keep upstream compiler/golden assertions, route exact exe through sealed relay and fail on raw exit"}
    report["cxx_names"] = names
    if len(names) != 8 or inventory(source) != before:
        raise ContractError("Upstream C++ inventory changed")
    log = (output / "cxx-testall.log").read_text(errors="replace")
    for name in names:
        if f"==== cxx test {name}" not in log:
            raise ContractError(f"Upstream C++ testall did not attempt {name}")
    if any(digest(copied / name) != expected["sha256"]
           for name, expected in before.items() if name != "testone"):
        raise ContractError("Upstream C++ source/golden files changed")
    exits = row["evidence"]["native_target_exits"]
    actual = sorted(Path(event["executable"]).stem for event in exits)
    if row["process"]["passed"] and (actual != names or any(event["raw_exit"] != 0 for event in exits)):
        raise ContractError("Upstream C++ success lacks all eight exact native process exits")
    report["status"] = ("native-db-all-eight-upstream-cxx-tests-passed" if row["process"]["passed"]
                        else "native-db-upstream-cxx-tests-failed")


def queue_diagnostic(args, report):
    env = environment(args.prefix, args.output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(args.build)
    build = args.build / "build"
    command = [sys.executable, "-B", Path(__file__).with_name("capture-native-exception.py"),
               "--executable", build / ".libs/cutest.exe", "--path-directory", build / ".libs",
               "--runtime-directory", args.prefix / "bin", "--output", args.output / "capture",
               "--", "-s", "TestQueue"]
    report["commands"]["queue-diagnostic"] = observe(
        command, args.output, env, args.output, "queue-diagnostic", args.native_job_prefix, 60)
    report["capture_sha256"] = digest(args.output / "capture/result.json")
    report["status"] = "native-db-queue-diagnostic-recorded-not-test-admission"


def cpp_held(args, report):
    from ssh_crypt_consumer import inspect_process, matching_relay, validate_loaded
    if args.installed_input is None:
        raise ContractError("The previously relocated native DB installation is required")
    installed = args.installed_input
    verify_tree(installed / "relocated", args.build_result)
    output = args.output
    env = environment(args.prefix, output)
    fixture = Path(__file__).parent / "fixtures/native-db-consumer.cpp"
    exe = output / "native-db-cpp.exe"
    command = [args.prefix / "bin/g++.exe", "-O2", "-g", "-Werror", "-fstack-protector-strong",
               "-I" + str(installed / "relocated/usr/include"), fixture,
               "-L" + str(installed / "relocated/usr/lib"), "-Wl,--no-insert-timestamp", "-o", exe, "-ldb_cxx"]
    row = observe(command, output, env, output, "compile", args.native_job_prefix)
    report["commands"]["compile"] = row
    report["fixture_sources"][fixture.name] = digest(fixture)
    if not row["process"]["passed"]:
        raise ContractError("Held native C++ fixture compilation failed")
    expected = {path.name.lower(): {"path": str(path), "sha256": digest(path)} for path in
                (installed / "relocated/usr/bin/msys-db_cxx-6.2.dll", installed / "runtime/msys-2.0.dll")}
    env["PATH"] = os.pathsep.join(map(str, (installed / "relocated/usr/bin", installed / "runtime",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    stop = threading.Event()
    watch = {}

    def monitor():
        try:
            deadline = time.monotonic() + 20
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    text = (output / "ready").read_text()
                except FileNotFoundError:
                    time.sleep(0.05)
                    continue
                if not text.endswith("\n"):
                    time.sleep(0.05)
                    continue
                if not text.strip().isdecimal():
                    raise ContractError("Invalid native PID handshake")
                pid = int(text.strip())
                identity = inspect_process(pid, expected)
                validate_loaded(identity, pid, exe, expected)
                watch["identity"] = identity
                write_json(output / "loaded-native-process.json", identity)
                (output / "continue").write_bytes(b"go\n")
                return
            raise ContractError("Native C++ exception fixture did not reach its bounded module handshake")
        except (OSError, ValueError) as error:
            watch["error"] = str(error)

    thread = threading.Thread(target=monitor, name="db-cpp-module-proof")
    thread.start()
    try:
        row = observe([sys.executable, "-I", args.native_job_prefix / "native-target-exec.py", exe, "hold"],
                      output, env, output, "cpp-held", args.native_job_prefix, 45)
        report["commands"]["cpp-held"] = row
    finally:
        stop.set()
        thread.join(timeout=5)
    if thread.is_alive() or watch.get("error") or "identity" not in watch:
        raise ContractError("Held native C++ module proof failed: " + str(watch.get("error")))
    native_exit = require_exit(row, exe)
    if not row["process"]["passed"] or b"DB C++ PASS:" not in (output / "cpp-held.log").read_bytes():
        raise ContractError("The complete held C++ API and exception path failed")
    report["native_process"] = watch["identity"]
    report["native_exit"] = native_exit
    report["relay"] = matching_relay(output / "native-exits", watch["identity"], digest(exe))
    report["exact_private_dlls"] = expected
    verify_tree(installed / "relocated", args.build_result)
    if any(digest(row["path"]) != row["sha256"] for row in expected.values()):
        raise ContractError("Held native C++ input modules changed")
    report["status"] = "installed-native-db-cpp-exception-and-live-module-proof-passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("installed", "upstream", "cxx", "queue-diagnostic", "cpp-held"), required=True)
    for name in ("build", "build-result", "prefix", "compiler-receipt", "bootstrap", "native-job-prefix", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--build-result-sha256", required=True)
    parser.add_argument("--installed-input", type=Path)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists() or digest(args.build_result) != args.build_result_sha256:
        raise ContractError("New check output and the exact native DB build result are required")
    result = json.loads(args.build_result.read_text())
    if (result.get("status") != "native-msys-library-built-upstream-checks-pending"
            or result.get("package") != "db-msys" or result.get("input_integrity_errors")
            or result.get("compiler_receipt_sha256") != digest(args.compiler_receipt)):
        raise ContractError("DB checks require the successful full native package-profile build")
    verify_tree(args.build / "stage", args.build_result)
    verify_tree(args.prefix, args.compiler_receipt)
    require_db_cpp_receipt(json.loads(args.compiler_receipt.read_text()))
    verify_driver(args.native_job_prefix)
    args.output.mkdir(parents=True)
    (args.output / "native-exits").mkdir()
    identities = {str(path): digest(path) for path in
                  (args.build_result, args.compiler_receipt, Path(__file__),
                   Path(__file__).with_name("capture-native-exception.py"),
                   Path(__file__).with_name("native_job_runner.py"))}
    if args.mode in ("cpp-held", "installed"):
        identities[str(Path(__file__).with_name("ssh_crypt_consumer.py"))] = digest(
            Path(__file__).with_name("ssh_crypt_consumer.py"))
    report = {"schema": 1, "status": "failed", "mode": args.mode, "pid": os.getpid(),
              "command": [sys.executable, *sys.argv], "input_identities": identities,
              "commands": {}, "api": {}, "upstream": {}, "fixture_sources": {},
              "full_cpp_qualified": False, "package_admitted": False}
    try:
        {"installed": installed, "upstream": upstream, "cxx": cxx,
         "queue-diagnostic": queue_diagnostic, "cpp-held": cpp_held}[args.mode](args, report)
    except (OSError, ContractError) as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            verify_tree(args.build / "stage", args.build_result)
            verify_tree(args.prefix, args.compiler_receipt)
            verify_driver(args.native_job_prefix)
            if any(digest(path) != seal for path, seal in identities.items()):
                raise ContractError("Check inputs changed during execution")
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update(status="failed", inputs_unchanged=False, integrity_error=str(error))
            raise
        finally:
            write_json(args.output / "result.json", report)
    print(report["status"], flush=True)
    if report["status"] in ("native-db-upstream-failed-with-explicit-gates", "native-db-upstream-cxx-tests-failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
