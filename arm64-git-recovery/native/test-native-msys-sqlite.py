"""Prove actual staged SQLite tools, C API, Tcl binding and extension DLLs."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

from native_job_runner import run_observed
from pe_exports import export_names
from sources import ContractError, digest, inventory
from sqlite_build_inputs import SPLITS, TOOLS, msys_path, recipe
from sqlite_consumer_inputs import sealed_json, verify_files

spec = importlib.util.spec_from_file_location("sqlite_launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def pe_identity(path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ContractError(f"Not a PE: {path}")
    offset = struct.unpack_from("<I", data, 60)[0]
    if data[offset:offset + 4] != b"PE\0\0":
        raise ContractError(f"Invalid PE header: {path}")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    magic = struct.unpack_from("<H", data, offset + 24)[0]
    if (machine, magic) != (0xAA64, 0x20B):
        raise ContractError(f"Not ordinary ARM64 PE32+: {path}")
    return {"sha256": digest(path), "machine": machine, "optional_magic": magic}


def merge_tree(source, destination):
    for relative, row in inventory(source).items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if "symlink" in row:
            if target.exists() or target.is_symlink():
                if not target.is_symlink() or os.readlink(target) != row["symlink"]:
                    raise ContractError(f"Runtime link collision: {relative}")
            else:
                target.symlink_to(row["symlink"])
        elif target.exists():
            if digest(target) != row["sha256"]:
                raise ContractError(f"Runtime payload collision: {relative}")
        else:
            shutil.copyfile(source / relative, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"C:\ag-sqlite-e138-01"))
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--prepared-sha256")
    args = parser.parse_args()
    root, build, output = args.root.resolve(), args.build.resolve(), args.output.resolve()
    prepared = None
    if (args.prepared is None) != (args.prepared_sha256 is None):
        raise ContractError("Prepared runtime and seal must be supplied together")
    if args.prepared:
        prepared = sealed_json(args.prepared / "prepare.json", args.prepared_sha256)
        if prepared["status"] != "native-sqlite-combined-runtime-private-inputs-prepared":
            raise ContractError("Qualified combined runtime input preparation required")
        project = Path(prepared["project_root"]).resolve()
        if not args.prepared.resolve().is_relative_to(project) or not output.is_relative_to(project):
            raise ContractError("Combined proof must remain in its private project")
        verify_files(prepared["runtime_path"], prepared["runtime_files"])
    if output.exists() or (not prepared and not output.is_relative_to(root)) or not build.is_relative_to(root):
        raise ContractError("Fresh private SQLite proof output required")
    output.mkdir()
    (output / "native-exits").mkdir()
    runtime = Path(prepared["runtime_path"]) if prepared else output / "runtime"
    if not prepared:
        runtime.mkdir()
    report = {"schema": 1, "status": "failed", "scope": "Native SQLite unit only; not full Git/SDK or provider admission",
              "version": "3.53.4", "full_cpp_qualified": False, "launcher": launcher.process_identity(),
              "jobs": 1, "steps": [], "errors": []}
    if prepared:
        report.update(combined_receipt_sha256=prepared["combined_receipt_sha256"],
                      runtime_sha256=prepared["runtime_sha256"], runtime_path=str(runtime),
                      prepared_sha256=args.prepared_sha256, existing_sqlite_rebuilt=False,
                      native_consumer_reuse=[], validation_host="native ARM64; no foreign bootstrap in runtime PATH")
    launcher.write_json(output / "launch.json", report)
    print(json.dumps({"launch": report["launcher"], "log_root": str(output)}), flush=True)
    inputs = {str(root / name): inventory(root / name) for name in ("tcl", "readline", "ncurses", "zlib")}
    inputs.update({str(build / "splits" / name): inventory(build / "splits" / name) for name in SPLITS})
    try:
        if not prepared:
            merge_tree(root / "tcl", runtime)
            for name in ("readline", "ncurses", "zlib"):
                merge_tree(root / name, runtime)
            for name in SPLITS:
                merge_tree(build / "splits" / name, runtime)
        runtime_files = inventory(runtime)
        report["payload_pe"] = {p: pe_identity(runtime / p) for p in runtime_files
                                if Path(p).suffix.lower() in (".exe", ".dll")}
        env = launcher.environment(root, output, 1)
        runtime_dirs = [runtime / "usr/bin"]
        if not prepared:
            runtime_dirs.append(root / "compiler/bin")
        env.update(PATH=os.pathsep.join(map(str, (*runtime_dirs, Path(os.environ["SystemRoot"]) / "System32"))),
                   TCL_LIBRARY=msys_path(runtime / "usr/lib/tcl8.6"),
                   TCLLIBPATH=msys_path(runtime / "usr/lib"))
        if prepared:
            env["WOARM64_NATIVE_TEST_ROOT"] = str(project)
        capture = Path(__file__).with_name("capture-native-exception.py")
        fixture_root = Path(__file__).parent / "fixtures"
        fixture_c = fixture_root / "sqlite-native-api.c"

        def observed(name, command, timeout=120):
            launcher.require_memory()
            log, result = output / f"{name}.log", output / f"{name}.native-job.json"
            step = {"name": name, "command": list(map(str, command))}
            step["process"] = run_observed(command, cwd=output, env=env, log_path=log, result_path=result,
                                           relay_records=output / "native-exits", timeout=timeout,
                                           driver_prefix=root / "observer")
            report["steps"].append(step)
            if not step["process"]["passed"]:
                report["errors"].append(f"{name}: native observer failed")
            return step

        def execute(name, executable, arguments, required_text=None, required_dlls=()):
            capture_dir = output / f"{name}.capture"
            additional_runtime = [] if prepared else ["--runtime-directory", root / "compiler/bin"]
            step = observed(name, [sys.executable, "-B", capture, "--executable", executable,
                                   "--output", capture_dir, "--path-directory", runtime / "usr/bin",
                                   *additional_runtime, "--tcl-environment",
                                   "--", *arguments])
            result = json.loads((capture_dir / "result.json").read_text())
            text = (capture_dir / "stdout.bin").read_text(encoding="utf-8", errors="replace")
            stderr = (capture_dir / "stderr.bin").read_text(encoding="utf-8", errors="replace")
            step.update(capture_sha256=digest(capture_dir / "result.json"), raw_exit=result["exit_code"],
                        stdout=text, stderr=stderr, loaded_modules={})
            if result["exit_code"] != 0 or result["timed_out"] or result["exception_limit_reached"]:
                report["errors"].append(f"{name}: target raw exit/timeout/exception failure")
            if required_text is not None and required_text not in text:
                report["errors"].append(f"{name}: semantic marker missing: {required_text}")
            for module in result["modules"]:
                path = Path(module["path"].removeprefix("\\\\?\\")).resolve()
                identity = {"path": str(path), "sha256": digest(path)}
                step["loaded_modules"][path.name.lower()] = identity
                if path.is_relative_to(runtime):
                    relative = path.relative_to(runtime).as_posix()
                    if identity["sha256"] != runtime_files[relative]["sha256"]:
                        report["errors"].append(f"{name}: loaded private DLL differs: {relative}")
                elif not path.is_relative_to(Path(os.environ["SystemRoot"])) and path != Path(executable).resolve():
                    report["errors"].append(f"{name}: unexpected non-system module: {path}")
            for dll in required_dlls:
                if dll not in step["loaded_modules"]:
                    report["errors"].append(f"{name}: required module not loaded: {dll}")
            if prepared:
                actual_runtime = step["loaded_modules"].get("msys-2.0.dll")
                if (actual_runtime is None or actual_runtime["sha256"] != prepared["runtime_sha256"]
                        or Path(actual_runtime["path"]) != runtime / "usr/bin/msys-2.0.dll"):
                    report["errors"].append(f"{name}: combined runtime was not loaded from the exact private path")
            launcher.write_json(output / f"{name}.result.json", step)
            return text

        include = runtime / "usr/include"
        libraries = runtime / "usr/lib"
        common = ["-O2", "-g", "-fstack-protector-strong", "-D_FORTIFY_SOURCE=2",
                  f"-I{include.as_posix()}", str(fixture_c), f"-L{libraries.as_posix()}",
                  "-Wl,--no-insert-timestamp"]
        def reuse_consumer(exe):
            source = args.prepared / "consumers" / exe.name
            expected = prepared["consumer_files"][exe.name]["sha256"]
            if digest(source) != expected:
                raise ContractError("The previously qualified native consumer changed")
            shutil.copyfile(source, exe)
            if digest(exe) != expected:
                raise ContractError("Native consumer copy differs")
            report["native_consumer_reuse"].append({
                "path": str(exe), "sha256": expected, "source_path": str(source),
                "scope": "Existing native SQLite consumer reused; no compiler or package rebuild"})

        for mode, library in (("shared", "-lsqlite3"), ("static", str(libraries / "libsqlite3.a"))):
            exe = output / f"sqlite-api-{mode}.exe"
            if prepared:
                reuse_consumer(exe)
                ready = True
            else:
                step = observed(f"compile-api-{mode}", [root / "compiler/bin/gcc.exe", *common,
                                                       library, "-lz", "-lm", "-lpthread", "-o", exe])
                ready = step["process"]["passed"]
            if ready:
                report["payload_pe"][exe.name] = pe_identity(exe)
                execute(f"api-{mode}", exe, [msys_path(output / f"api-{mode}.sqlite")],
                        "sqlite-native-api-passed", ("msys-2.0.dll",) +
                        (("msys-sqlite3-0.dll",) if mode == "shared" else ()))
        cli = runtime / "usr/bin/sqlite3.exe"
        db = output / "cli.sqlite"
        text = execute("cli", cli, ["-batch", msys_path(db),
                       "CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT);"
                       "INSERT INTO t VALUES(1,'native'),(2,'sqlite');"
                       "SELECT sqlite_version(),count(*),sqrt(81),json_extract('{\"answer\":42}','$.answer') FROM t;"
                       "PRAGMA integrity_check; PRAGMA compile_options;"],
                       "3.53.4|2|9.0|42", ("msys-2.0.dll", "msys-readline8.dll"))
        report["compile_options"] = text.splitlines()[2:]
        options = set(report["compile_options"])
        for name in ("ENABLE_COLUMN_METADATA", "ENABLE_DBPAGE_VTAB", "ENABLE_DBSTAT_VTAB",
                     "ENABLE_FTS3", "ENABLE_FTS4", "ENABLE_FTS5", "ENABLE_MATH_FUNCTIONS",
                     "ENABLE_PREUPDATE_HOOK", "ENABLE_RTREE", "ENABLE_SESSION", "ENABLE_STAT4",
                     "ENABLE_STMTVTAB", "ENABLE_UNLOCK_NOTIFY", "ENABLE_UPDATE_DELETE_LIMIT",
                     "OMIT_LOOKASIDE", "SECURE_DELETE", "SOUNDEX", "TEMP_STORE=1", "THREADSAFE=1"):
            if name not in options:
                report["errors"].append(f"CLI missing configured compile option: {name}")
        analysis = execute("analyzer", runtime / "usr/bin/sqlite3_analyzer.exe", [msys_path(db)],
                           "Disk-Space Utilization Report", ("libtcl8.6.dll", "msys-2.0.dll"))
        pages = re.search(r"Pages in the whole file \(calculated\)\.+\s+(\d+)", analysis)
        page_size = re.search(r"Page size in bytes\.+\s+(\d+)", analysis)
        if not pages or not page_size or int(pages[1]) * int(page_size[1]) != db.stat().st_size:
            report["errors"].append("Analyzer page accounting does not match the actual database size")
        execute("binding", runtime / "usr/bin/tclsh8.6.exe",
                [msys_path(fixture_root / "sqlite-native-binding.tcl"), msys_path(output),
                 msys_path(runtime / "usr/lib/sqlite3.53.4")],
                "sqlite-native-tcl-binding-passed", ("libtcl8.6.dll", "msys-2.0.dll"))
        copy = output / "cli-copy.sqlite"
        shutil.copyfile(db, copy)
        difference = execute("sqldiff", runtime / "usr/bin/sqldiff.exe", [msys_path(db), msys_path(copy)])
        if difference.strip():
            report["errors"].append("sqldiff: byte-identical databases differ")
        execute("dbhash", runtime / "usr/bin/dbhash.exe", [msys_path(db)])
        rbu = output / "rbu.sqlite"
        execute("rbu-fixture", cli, ["-batch", msys_path(rbu),
                "CREATE TABLE data_t(id,value,rbu_control); INSERT INTO data_t VALUES(3,'rbu',0);"])
        execute("rbu", runtime / "usr/bin/rbu.exe", [msys_path(copy), msys_path(rbu)])
        execute("rbu-result", cli, ["-batch", msys_path(copy), "SELECT id,value FROM t WHERE id=3;"],
                "3|rbu")
        grammar = output / "native-parser.y"
        grammar.write_text("start ::= value.\nvalue ::= TOKEN.\n", newline="\n")
        execute("lemon", runtime / "usr/bin/lemon.exe", ["-s", msys_path(grammar)], "Parser statistics")
        if not grammar.with_suffix(".c").is_file() or not grammar.with_suffix(".h").is_file():
            report["errors"].append("lemon: generated C/header missing")
        extension_dlls = sorted((build / "splits/sqlite-extensions/usr/bin").glob("*.dll"))
        extension_info = {}
        helper_exports = {
            "dbdump": ["sqlite3_db_dump"], "mmapwarm": ["sqlite3_mmap_warm"],
            "normalize": ["sqlite3_normalize"],
            "pcachetrace": ["sqlite3PcacheTraceActivate", "sqlite3PcacheTraceDeactivate"],
            "vfslog": ["sqlite3_register_vfslog"], "sqlite3_stdio": [],
        }
        for path in extension_dlls:
            exports = export_names(path.read_bytes())
            entries = [x for x in exports if re.fullmatch(r"sqlite3_\w+_init", x)]
            stem = path.name.removeprefix("msys-sqlite3").removesuffix("-0.dll")
            canonical = f"sqlite3_{stem}_init"
            entry = canonical if canonical in entries else (entries[0] if len(entries) == 1 else None)
            kind = "loadable"
            if stem in helper_exports:
                kind = "win32-only-source-no-op-on-msys" if stem == "sqlite3_stdio" else "direct-C-helper-API"
                if entries or not set(helper_exports[stem]).issubset(exports):
                    report["errors"].append(f"Unexpected pinned helper exports: {path.name}")
            elif entry is None:
                report["errors"].append(f"No unambiguous canonical init: {path.name}")
            extension_info[path.name] = {
                "sha256": digest(path), "exports": exports, "entries": entries, "canonical_entry": entry,
                "kind": kind, "source_sha256": digest(root / "prepared/source/ext/misc" / f"{stem}.c")}
        report["extensions"] = extension_info
        for name, record in extension_info.items():
            entry = record["canonical_entry"]
            if entry is not None:
                path = msys_path(runtime / "usr/bin" / name)
                # SQL load_extension() runs inside an active VM and cannot
                # replace functions already built into the CLI. .load calls
                # the public loader outside an SQL statement.
                execute(f"load-{name.removesuffix('.dll')}", cli,
                        ["-batch", "-cmd", f".load {path} {entry}", ":memory:",
                         "SELECT 'sqlite-native-extension-load-passed';"],
                        "sqlite-native-extension-load-passed", (name.lower(),))
        helper_exe = output / "sqlite-helper-apis.exe"
        helper_source = fixture_root / "sqlite-native-helper-apis.c"
        if prepared:
            reuse_consumer(helper_exe)
            ready = True
        else:
            step = observed("compile-helper-apis", [root / "compiler/bin/gcc.exe", "-O2", "-g",
                            "-fstack-protector-strong", "-D_FORTIFY_SOURCE=2", f"-I{include.as_posix()}",
                            helper_source, f"-L{libraries.as_posix()}", "-lsqlite3", "-ldl",
                            "-Wl,--no-insert-timestamp", "-o", helper_exe])
            ready = step["process"]["passed"]
        if ready:
            execute("helper-apis", helper_exe, [msys_path(runtime / "usr/bin"),
                    msys_path(output / "helper.sqlite"), msys_path(output / "helper-dump.sql")],
                    "sqlite-native-helper-apis-passed",
                    tuple(f"msys-sqlite3{name}-0.dll" for name in helper_exports))
        compression = runtime / "usr/bin/msys-sqlite3compress-0.dll"
        execute("extension-functions", cli, ["-batch", ":memory:",
                f"SELECT load_extension('{msys_path(compression)}','sqlite3_compress_init');"
                "SELECT CAST(uncompress(compress('native sqlite compression')) AS TEXT);"],
                "native sqlite compression", ("msys-z.dll",))
        if inventory(runtime) != runtime_files:
            report["errors"].append("Private proof runtime changed")
        report["runtime_files"] = runtime_files
        report["status"] = "native-sqlite-unit-proofs-passed" if not report["errors"] else "native-sqlite-unit-proofs-failed"
    finally:
        report["input_integrity_errors"] = [path for path, files in inputs.items() if inventory(path) != files]
        if report["input_integrity_errors"]:
            report["status"] = "failed"
        if prepared:
            verify_files(runtime, prepared["runtime_files"])
            if digest(args.prepared / "prepare.json") != args.prepared_sha256:
                raise ContractError("Prepared combined-runtime receipt changed")
        launcher.write_json(output / "result.json", report)
    if report["status"] != "native-sqlite-unit-proofs-passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
