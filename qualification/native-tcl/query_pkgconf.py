"""Query the sealed Tcl providers with the already-qualified native Windows pkgconf."""

import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tarfile

from qualify import ROOT, digest, import_tools, read_json, require, require_memory, verify_inputs, write_json
from finalize import generation_state, reference


SOURCE = Path(r"C:\Users\crutkasLocal\.copilot\session-state\f6ea7713-2cec-41d5-b3f9-b4373e60fa33\files")
DRIVER = SOURCE / "native-pkgconf-02"
DRIVER_SHA = "29cc3d92eb29e354a1db2ca9b88ab731c0eba48c7eaeafdf7cc518bf593a2c09"
ZLIB = SOURCE / "resume-20260907/zlib-msys-01"
ZLIB_RECEIPT = ZLIB.with_name("zlib-msys-01.result.json")
ZLIB_SHA = "e206df14f9a4aa12dca6c88e13427e03ca2d0233100f243426c7cd9b5bfe4960"
OUTPUT = ROOT / "pkgconf-query-01"
PREVIOUS = ROOT / "handoff-02/result.json"
PREVIOUS_SHA = "6f349dbc920a7eb2bbe00ece19f00ec138966009bf5026e112688d91b8ffa398"
PROVIDERS = [ROOT / "provider-01", ROOT / "provider-02"]
QUERIES = {
    "version": ["--modversion", "tcl"],
    "prefix": ["--variable=prefix", "tcl"],
    "includedir": ["--variable=includedir", "tcl"],
    "libdir": ["--variable=libdir", "tcl"],
    "pcfiledir": ["--variable=pcfiledir", "tcl"],
    "path": ["--path", "tcl"],
    "cflags": ["--cflags", "tcl"],
    "libs": ["--libs", "tcl"],
    "static-libs": ["--static", "--libs", "tcl"],
}


def verify_external():
    sources = import_tools()
    require(digest(DRIVER / "result.json") == DRIVER_SHA, "Qualified pkgconf receipt changed")
    require(digest(ZLIB_RECEIPT) == ZLIB_SHA, "Qualified zlib receipt changed")
    require(digest(PREVIOUS) == PREVIOUS_SHA, "Previous Tcl handoff changed")
    driver = read_json(DRIVER / "result.json")
    require(driver["status"] == "native-pkgconf-built-upstream-and-independent-controls-passed" and
            driver["build_host"] == "windows-arm64-native", "The actual qualified native driver is required")
    sources.verify_tree(DRIVER / "stage", DRIVER / "result.json")
    sources.verify_tree(ZLIB / "stage", ZLIB_RECEIPT)
    for provider in PROVIDERS:
        sources.verify_tree(provider / "payload", provider / "result.json")
    verify_inputs()


def prepare():
    sources = import_tools()
    from ssh_crypt_consumer import arm64_pe
    verify_external()
    OUTPUT.mkdir()
    shutil.copytree(DRIVER / "stage", OUTPUT / "driver")
    shutil.copytree(ZLIB / "stage", OUTPUT / "zlib")
    for path in Path(__file__).parent.iterdir():
        if path.suffix in (".py", ".tcl"):
            shutil.copyfile(path, OUTPUT / path.name)
    pc = OUTPUT / "zlib/usr/lib/pkgconfig/zlib.pc"
    before = pc.read_text()
    replacements = {
        "prefix": "${pcfiledir}/../..",
        "exec_prefix": "${prefix}",
        "libdir": "${prefix}/lib",
        "sharedlibdir": "${prefix}/lib",
        "includedir": "${prefix}/include",
    }
    after = before
    for name, value in replacements.items():
        after, count = re.subn(r"^" + name + r"=.*$", lambda _: name + "=" + value, after, flags=re.MULTILINE)
        require(count == 1, "Expected an unambiguous zlib path assignment")
    require(after.split("\nName:", 1)[1] == before.split("\nName:", 1)[1],
            "The zlib version, compiler flags or library metadata changed")
    pc.write_text(after, encoding="utf-8", newline="\n")
    original = read_json(ZLIB_RECEIPT)["files"]
    copied = sources.inventory(OUTPUT / "zlib")
    require(set(copied) == set(original) and
            {name for name in original if copied[name] != original[name]} == {"usr/lib/pkgconfig/zlib.pc"},
            "Only the private dependency metadata path assignments may change")
    write_json(OUTPUT / "inputs.json", {
        "driver_receipt": reference(DRIVER / "result.json"),
        "zlib_receipt": reference(ZLIB_RECEIPT), "previous": reference(PREVIOUS),
        "shared_before": {str(DRIVER / "stage"): sources.inventory(DRIVER / "stage"),
                          str(ZLIB / "stage"): original},
        "private_before": {str(OUTPUT / "driver"): sources.inventory(OUTPUT / "driver"),
                           str(OUTPUT / "zlib"): copied},
        "zlib_metadata_path_only_delta": {"before": before, "after": after},
        "pe": [arm64_pe(OUTPUT / "driver/bin/pkgconf.exe"),
               arm64_pe(OUTPUT / "driver/bin/libpkgconf-8.dll")],
        "scripts": {path.name: digest(path) for path in OUTPUT.iterdir() if path.suffix in (".py", ".tcl")},
    })
    print(json.dumps({"prepared": str(OUTPUT), "native_jobs_started": 0, "driver_files": 27}))


def verify_private():
    sources = import_tools()
    inputs = read_json(OUTPUT / "inputs.json")
    for path, expected in {**inputs["shared_before"], **inputs["private_before"]}.items():
        require(sources.inventory(path) == expected, f"A pkgconf input tree changed: {path}")
    for name, expected in inputs["scripts"].items():
        require(digest(OUTPUT / name) == expected, "A snapshotted qualification script changed")
    verify_external()


def normalize_flag(flag):
    if flag.startswith(("-I", "-L")):
        value = flag[2:]
        require(re.match(r"^[A-Za-z]:[/\\]", value), f"Non-Windows compiler path emitted: {flag}")
        path = Path(value).resolve()
        require(path.is_dir(), f"Compiler flag directory is absent: {flag}")
        return flag[:2] + str(path).casefold()
    return flag


def validate_answers(answers, payload):
    usr = payload / "usr"
    zusr = OUTPUT / "zlib/usr"
    require(answers["version"] == "8.6.12", "pkgconf selected an unexpected Tcl version")
    for name, expected in (("prefix", usr), ("includedir", usr / "include"), ("libdir", usr / "lib"),
                           ("pcfiledir", usr / "lib/pkgconfig"), ("path", usr / "lib/pkgconfig/tcl.pc")):
        require(re.match(r"^[A-Za-z]:[/\\]", answers[name]) and
                Path(answers[name]).resolve() == expected.resolve(), f"Wrong actual pkgconf {name}")
    flags = {name: [normalize_flag(token) for token in shlex.split(answers[name])]
             for name in ("cflags", "libs", "static-libs")}
    expected_cflags = {"-I" + str((prefix / "include").resolve()).casefold() for prefix in (usr, zusr)}
    expected_libs = {"-L" + str((usr / "lib").resolve()).casefold(), "-ltcl8.6", "-ltclstub8.6"}
    expected_static = expected_libs | {"-L" + str((zusr / "lib").resolve()).casefold(),
                                       "-ldl", "-lz", "-lpthread"}
    require(set(flags["cflags"]) == expected_cflags, "Actual Cflags lost or added a compiler option")
    require(set(flags["libs"]) == expected_libs, "Actual Tcl library flags differ")
    require(set(flags["static-libs"]) == expected_static, "Actual private library flags differ")
    require((usr / "include/tcl.h").is_file() and (usr / "lib/libtcl8.6.dll.a").is_file() and
            (usr / "lib/libtclstub8.6.a").is_file() and (zusr / "lib/libz.dll.a").is_file(),
            "Actual pkgconf outputs do not name installed inputs")
    return flags


def execute(grant):
    import_tools()
    from native_job_runner import run_observed
    verify_private()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update({
        "PATH": os.pathsep.join((str(OUTPUT / "driver/bin"), str(Path(env["SystemRoot"]) / "System32"))),
        "HOME": str(OUTPUT), "USERPROFILE": str(OUTPUT), "TMP": str(OUTPUT), "TEMP": str(OUTPUT),
        "PKG_CONFIG_PATH": "", "PKG_CONFIG_SYSROOT_DIR": "",
        "PKG_CONFIG_SYSTEM_INCLUDE_PATH": "", "PKG_CONFIG_SYSTEM_LIBRARY_PATH": "",
        "PKG_CONFIG_ALLOW_SYSTEM_CFLAGS": "1", "PKG_CONFIG_ALLOW_SYSTEM_LIBS": "1",
        "WOARM64_NATIVE_TEST_ROOT": str(ROOT), "WOARM64_NATIVE_ARG_CONVERSION": "none",
        "WOARM64_NATIVE_PYTHON_SHA256": digest(sys.executable),
    })
    results, observations, states = [], [], []
    report = {"status": "failed", "scope": "Actual native pkgconf queries, no builds or Tcl re-execution",
              "aggregate_jobs": 1, "parent_grant": grant, "inputs": reference(OUTPUT / "inputs.json")}
    try:
        for provider in PROVIDERS:
            payload = provider / "payload"
            env["PKG_CONFIG_LIBDIR"] = os.pathsep.join(
                str(path) for path in (payload / "usr/lib/pkgconfig", OUTPUT / "zlib/usr/lib/pkgconfig"))
            answers, commands = {}, {}
            for name, options in QUERIES.items():
                query = OUTPUT / (provider.name + "-" + name)
                query.mkdir()
                exits = query / "native-exits"
                exits.mkdir()
                env["WOARM64_NATIVE_EXIT_DIR"] = str(exits)
                executable = OUTPUT / "driver/bin/pkgconf.exe"
                command = [str(executable), *options]
                write_json(query / "request.json", {"argv": command, "environment": env})
                memory = require_memory()
                process = run_observed(
                    [sys.executable, "-I", ROOT / "observer/native-target-exec.py", *command],
                    cwd=query, env=env, log_path=query / "query.log", result_path=query / "native-job.json",
                    relay_records=exits, timeout=30, driver_prefix=ROOT / "observer")
                observed = read_json(query / "native-job.json")
                observations.append({"observation": reference(query / "native-job.json"), **process})
                require(process["passed"], f"Native pkgconf query failed: {provider.name}/{name}")
                records = list(exits.glob("*.json"))
                require(len(records) == 1 and len(observed["native_target_exits"]) == 1,
                        "Expected exactly one generation-bound native pkgconf execution")
                relay = read_json(records[0])
                native = observed["native_target_exits"][0]
                require(relay["child_pid"] == native["pid"] and relay["child_created"] == native["created"] and
                        relay["raw_exit"] == native["raw_exit"] == 0 and
                        relay["sha256"] == digest(executable), "Native query relay and collector disagree")
                state = generation_state(native["pid"], native["created"])
                states.append(state)
                answers[name] = (query / "query.log").read_text(encoding="utf-8").strip()
                commands[name] = {"argv": command, "pid": native["pid"], "creation_filetime": native["created"],
                                  "free_memory_before": memory, "log": reference(query / "query.log"),
                                  "relay": reference(records[0]), "observer": reference(query / "native-job.json"),
                                  "raw_exit": native["raw_exit"]}
            normalized = validate_answers(answers, payload)
            result = {"prefix": str(payload), "answers": answers, "normalized_for_assertion_only": normalized,
                      "commands": commands, "pkg_config_libdir": env["PKG_CONFIG_LIBDIR"],
                      "pkg_config_path": env["PKG_CONFIG_PATH"]}
            results.append(result)
            write_json(OUTPUT / (provider.name + "-queries.json"), result)
        report.update(status="native-pkgconf-actual-two-prefix-queries-passed", results=results)
    finally:
        verify_private()
        report["inputs_unchanged"] = True
        report["observations"] = observations
        report["observed_drained_generations"] = states
        report["free_memory_after"] = require_memory()
        write_json(OUTPUT / "result.json", report)
    publish(report)


def publish(report):
    require(report["status"] == "native-pkgconf-actual-two-prefix-queries-passed", "Cannot promote a failed query")
    output = ROOT / "handoff-03"
    output.mkdir()
    previous = read_json(PREVIOUS)
    previous["supersedes"] = reference(PREVIOUS)
    previous["revision_reason"] = "Closed actual native pkgconf query gate in both unchanged physical provider prefixes"
    previous["pkgconf_queries"] = reference(OUTPUT / "result.json")
    previous["provider"]["pkg_config_execution"] = (
        "Qualified native Windows ARM64 pkgconf executed version/prefix/include/lib/pcfile provenance, "
        "Cflags, dynamic Libs and static Libs in both physical prefixes. Exact private dependency metadata "
        "and actual Windows compiler-path semantics verified; no structural-only promotion.")
    previous["remaining_gates"].remove("pkg-config process validation in an approved provider")
    previous["jobs_returnable"] = 1
    counts = Counter()
    for row in report["observations"]:
        counts.update(created=row["created_processes"], observed=row["observed_processes"])
    write_json(output / "drain.json", {
        "previous": previous["drain"], "aggregate_regrant": 1, "jobs": len(report["observations"]),
        "process_counts": dict(counts), "native_generations": report["observed_drained_generations"],
        "active_owned_generations": 0, "returnable_jobs": 1})
    previous["drain"] = reference(output / "drain.json")
    archive = output / "maintained-native-tcl-qualification.tar.gz"
    maintained = {}
    with archive.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for path in sorted(OUTPUT.iterdir()):
                if path.suffix not in (".py", ".tcl"):
                    continue
                maintained[path.name] = reference(path)
                info = tarfile.TarInfo(path.name)
                info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
                with path.open("rb") as source:
                    tar.addfile(info, source)
    previous["maintained_export"]["archive"] = reference(archive)
    previous["maintained_export"]["sources"] = maintained
    write_json(output / "result.json", previous)
    print(json.dumps({"result": reference(output / "result.json"), "query_receipt": reference(OUTPUT / "result.json"),
                      "queries": len(report["observations"]), "drained": len(report["observed_drained_generations"]),
                      "returnable_jobs": 1}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare")
    execute_parser = sub.add_parser("execute")
    execute_parser.add_argument("--grant", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        execute(args.grant)
