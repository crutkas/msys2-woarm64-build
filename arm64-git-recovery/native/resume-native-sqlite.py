"""Run fresh targeted MSYS SQLite consumer proofs without changing sealed inputs."""

import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory, verify_tree
from sqlite_build_inputs import msys_path
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("sqlite_proofs", Path(__file__).with_name("test-native-msys-sqlite.py"))
proofs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proofs)

HANDOFF = Path(r"C:\ag-sqlite-e138-01\handoff-01\result.json")
HANDOFF_SHA = "9bfa0f82b6456b546e654e53da68661555fee0d8a9656b592258a052c2edf718"
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"
BOOTSTRAP_SHA = "e087cd54f265eb5fbc2442878d0bf7063e1b770cdcd6c9c4a4db9868bdd551b1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(r"C:\ag-sqlite-resume-01")
    output = args.output.resolve()
    if (not output.is_relative_to(root) or output == root or output.exists() or
            any(p.is_symlink() or p.is_junction() for p in output.parents)):
        raise ContractError("Fresh, disjoint owned continuation output required")
    if digest(HANDOFF) != HANDOFF_SHA or digest(sys.executable) != PYTHON_SHA:
        raise ContractError("Exact original MSYS SQLite handoff/native Python required")
    handoff = json.loads(HANDOFF.read_text())
    old = HANDOFF.parent.parent
    output.mkdir(parents=True)
    for name in ("native-exits", "temp", "home", "runtime", "inputs", "work"):
        (output / name).mkdir()
    runtime = output / "runtime"
    original = {}
    report = {"schema": 1, "status": "failed", "source_handoff_sha256": HANDOFF_SHA,
              "scope": "Targeted MSYS LP64 shell-pipe and TDBC SQLite consumers; not MinGW provider intake",
              "jobs": 1, "full_git_complete": False, "provider_admission": False,
              "launcher": proofs.launcher.process_identity(), "free_ram_gib": require_memory(), "steps": []}
    proofs.launcher.write_json(output / "launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "logs": str(output)}), flush=True)
    try:
        for name in ("tcl", "readline", "ncurses", "zlib"):
            manifest = old / f"{name}.inventory.json"
            verify_tree(old / name, manifest)
            original[name] = digest(manifest)
            proofs.merge_tree(old / name, runtime)
        for name in ("sqlite", "libsqlite", "tcl-sqlite"):
            row = handoff["payloads"][name]
            if inventory(row["stage"]) != row["files"]:
                raise ContractError(f"Sealed SQLite split changed: {name}")
            proofs.merge_tree(Path(row["stage"]), runtime)
        bootstrap_manifest = old / "bootstrap.upstream.json"
        if digest(bootstrap_manifest) != BOOTSTRAP_SHA:
            raise ContractError("Sealed read-only foreign host driver identity changed")
        verify_tree(old / "bootstrap", bootstrap_manifest)
        verify_tree(old / "compiler", old / "compiler-runtime.inventory.json")
        observer_manifest = verify_driver(old / "observer")
        if digest(observer_manifest) != "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa":
            raise ContractError("Unexpected original fail-closed observer")
        runtime_before = inventory(runtime)
        for name in ("sqlite-shell-pipe.c", "sqlite-tdbc-consumer.tcl"):
            shutil.copyfile(Path(__file__).parent / "fixtures" / name, output / "inputs" / name)
        env = proofs.launcher.environment(old, output, 1)
        env.update(PATH=os.pathsep.join(map(str, (runtime / "usr/bin", old / "compiler/bin",
                                                  old / "bootstrap/usr/bin",
                                                  Path(os.environ["SystemRoot"]) / "System32"))),
                   HOME=msys_path(output / "home"), USERPROFILE=str(output / "home"),
                   TMP=str(output / "temp"), TEMP=str(output / "temp"), TMPDIR=msys_path(output / "temp"),
                   TCL_LIBRARY=msys_path(runtime / "usr/lib/tcl8.6"), TCLLIBPATH=msys_path(runtime / "usr/lib"),
                   WOARM64_NATIVE_TEST_ROOT=str(output))
        env["TMPDIR"] = str(output / "temp")
        capture = Path(__file__).with_name("capture-native-exception.py")

        def observed(name, command):
            step = {"name": name, "command": list(map(str, command))}
            step["process"] = run_observed(command, cwd=output / "work", env=env,
                                           log_path=output / f"{name}.log",
                                           result_path=output / f"{name}.native-job.json",
                                           relay_records=output / "native-exits", timeout=180,
                                           driver_prefix=old / "observer")
            report["steps"].append(step)
            return step

        def captured(name, executable, arguments, marker):
            directory = output / f"{name}.capture"
            step = observed(name, [sys.executable, "-B", capture, "--executable", executable,
                                   "--output", directory, "--path-directory", runtime / "usr/bin",
                                   "--runtime-directory", old / "bootstrap/usr/bin", "--tcl-environment",
                                   "--", *arguments])
            path = directory / "result.json"
            if not path.is_file():
                raise ContractError(f"Capture failed before producing target evidence: {name}")
            details = json.loads(path.read_text())
            text = (directory / "stdout.bin").read_text(encoding="utf-8", errors="replace")
            error = (directory / "stderr.bin").read_text(encoding="utf-8", errors="replace")
            step.update(raw_exit=details["exit_code"], stdout=text, stderr=error,
                        capture_sha256=digest(path), loaded_modules={})
            for module in details["modules"]:
                loaded = Path(module["path"].removeprefix("\\\\?\\")).resolve()
                if loaded.is_relative_to(runtime):
                    rel = loaded.relative_to(runtime).as_posix()
                    if digest(loaded) != runtime_before[rel]["sha256"]:
                        raise ContractError("Live consumer module differs from copied receipt")
                elif not loaded.is_relative_to(Path(os.environ["SystemRoot"])) and loaded != Path(executable):
                    raise ContractError(f"Unapproved live module in native consumer: {loaded}")
                step["loaded_modules"][loaded.name.lower()] = {"path": str(loaded), "sha256": digest(loaded)}
            step["passed"] = (step["process"]["passed"] and details["exit_code"] == 0
                              and not details["timed_out"] and not details["exception_limit_reached"]
                              and marker in text)
            proofs.launcher.write_json(output / f"{name}.result.json", step)
            return step

        exe = output / "sqlite-shell-pipe.exe"
        compilation = observed("compile-shell-pipe", [old / "compiler/bin/gcc.exe", "-O2", "-g",
                               "-fstack-protector-strong", "-D_FORTIFY_SOURCE=2",
                               output / "inputs/sqlite-shell-pipe.c", "-o", exe])
        if not compilation["process"]["passed"]:
            raise ContractError("Native shell-pipe fixture compilation failed")
        proofs.pe_identity(exe)
        pipe = captured("shell-pipe", exe, [], "text=native-sqlite-pipe")
        script = output / "inputs/shell5-import.sql"
        script.write_text(
            '.mode csv\n'
            '.import "|awk \'END{print \\"x,y\\";for(i=1;i<=5;i++){print i \\",this is \\" i}}\'" t1\n'
            'SELECT * FROM t1;\n', newline="\n")
        shell = captured("shell5-import", runtime / "usr/bin/sqlite3.exe",
                         ["-batch", msys_path(output / "work/import.sqlite"),
                          f".read {msys_path(script)}"], '5,"this is 5"')
        database = output / "work" / "tdbc-\u03bb.sqlite"
        tdbc = captured("tdbc", runtime / "usr/bin/tclsh8.6.exe",
                        [msys_path(output / "inputs/sqlite-tdbc-consumer.tcl"), msys_path(database)],
                        "native-msys-sqlite-tdbc-consumer-passed")
        if tdbc["passed"]:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                rows = db.execute("SELECT id,value FROM records ORDER BY id").fetchall()
            if rows != [(1, "native \u03bb \u96ea"), (3, "committed")]:
                raise ContractError("Native TDBC rows/Unicode Windows filename differ")
            report["tdbc_windows_readback"] = rows
        report.update(status="native-msys-sqlite-targeted-consumers-recorded",
                      shell_pipe_passed=pipe["passed"], shell5_import_passed=shell["passed"],
                      tdbc_passed=tdbc["passed"], runtime_files=runtime_before)
    finally:
        integrity_errors = []
        for name, sha in original.items():
            try:
                manifest = old / f"{name}.inventory.json"
                if digest(manifest) != sha:
                    raise ContractError("Frozen receipt changed")
                verify_tree(old / name, manifest)
            except (OSError, ContractError) as error:
                integrity_errors.append(f"{name}: {error}")
        if digest(HANDOFF) != HANDOFF_SHA:
            integrity_errors.append("Original handoff changed")
        if "runtime_before" in locals() and inventory(runtime) != runtime_before:
            integrity_errors.append("Private runtime payload changed")
        report["input_integrity_errors"] = integrity_errors
        report["driver_inputs"] = {str(p): digest(p) for p in
                                   (Path(__file__), capture if "capture" in locals() else Path(__file__))}
        proofs.launcher.write_json(output / "result.json", report)
        if integrity_errors:
            raise ContractError("Input integrity failure")
    print(json.dumps({"result": str(output / "result.json"),
                      "sha256": digest(output / "result.json"),
                      "shell_pipe_passed": report["shell_pipe_passed"],
                      "shell5_import_passed": report["shell5_import_passed"], "tdbc_passed": report["tdbc_passed"]}))
    if not all((report["shell_pipe_passed"], report["shell5_import_passed"], report["tdbc_passed"])):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
