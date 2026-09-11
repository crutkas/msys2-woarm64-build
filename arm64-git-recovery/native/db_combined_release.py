"""Requalify the full native DB stage on the combined runtime and produce split packages."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from db_build_inputs import copy_sealed_tree, require_db_cpp_receipt
from db_channel_checks import HANDOFF_SHA, own_birth, sealed_json
from db_native_checks import environment, observe, require_exit
from db_native_driver import held_cpp
from db_package import create_package, pe_metadata, split_inventory
from native_job_runner import verify_driver
from sources import ContractError, digest, inventory, relative_path, verify_tree
from ssh_bootstrap import require_memory, write_json
from ssh_crypt_consumer import arm64_pe


COMBINED_SHA = "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b"
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
SHELL_MANIFEST_SHA = "8a190bb53c72490d4daa163120f4d6f42537279ece27e5103b2a334e6b1803a1"
HERE = Path(__file__).resolve().parent
LIMITATIONS = [
    "Unchanged full-load MutexAlignment timed out after900seconds during configuration9of24; "
    "83created/76recorded exit coverage was partial. Not a full-matrix or full-upstream-suite pass.",
    "The original channel race was addressed in a test-only synchronization patch with deterministic controls "
    "and three ordinary passes on the historical cohort; no claim of rerunning the full suite on907.",
    "Optional native Tcl test instrumentation remains disabled by the pinned package recipe and was not added.",
    "Historical debugger-only C++ exception limitation retained; qualification here uses ordinary held-process exceptions.",
    "Unsigned local package creation/readback is not repository signature/provider, full-SDK, Perl, SSH or Git artifact admission.",
]


def native_path(value):
    if value.startswith("/root/"):
        return Path("\\\\wsl.localhost\\Ubuntu" + value.replace("/", "\\"))
    return Path(value)


def manifest_rows(path):
    rows = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ContractError("Malformed runtime source inventory")
        name = match[2]
        relative_path(name)
        if name in rows:
            raise ContractError("Duplicate runtime source inventory entry")
        rows[name] = match[1]
    if not rows:
        raise ContractError("Empty runtime input inventory")
    return rows


def receipt_ref(path):
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def require_package_proof(prepare_path, prepared, proof):
    if (proof.get("status") != "native-db-combined907-api-cli-and-modules-passed"
            or proof.get("inputs_unchanged") is not True
            or proof.get("prepare", {}).get("sha256") != digest(prepare_path)
            or proof.get("runtime_sha256") != RUNTIME_SHA
            or prepared.get("combined_handoff", {}).get("sha256") != COMBINED_SHA
            or prepared.get("combined_runtime", {}).get("runtime", {}).get("sha256") != RUNTIME_SHA):
        raise ContractError("Package proof does not qualify this exact stage/runtime preparation")


def require_continuation_runtime(runtime, manifest, previous):
    if previous.get("input_identities", {}).get(str(manifest.resolve())) != digest(manifest):
        raise ContractError("Continuation runtime manifest is not the original receipt-bound input")
    base = json.loads(manifest.read_text())["files"]
    additions = previous.get("proof_executable_files")
    if not isinstance(additions, dict) or len(additions) != 4:
        raise ContractError("Continuation requires recorded proof-executable identities; an inventory taken now is not prior proof")
    if set(base) & set(additions):
        raise ContractError("Proof executables may not override runtime inputs")
    expected = {**base, **additions}
    if inventory(runtime) != expected:
        raise ContractError("Runtime files changed between proof attempts")
    for name in additions:
        pe_metadata((runtime / name).read_bytes())
    return expected


def prepare(args):
    root = args.output
    if root.exists() or not root.is_relative_to(Path(r"C:\ag-db-e138-01")):
        raise ContractError("A fresh owned DB release root is required")
    base = sealed_json(args.db_handoff, HANDOFF_SHA)
    combined = sealed_json(args.runtime_handoff, COMBINED_SHA)
    if combined.get("runtime", {}).get("sha256") != RUNTIME_SHA:
        raise ContractError("Combined runtime identity changed")
    producer_root = native_path(combined["prefix"])
    verified = {}
    for key in ("runtime", "import_library", "startup", "header", "generated_header",
                "public_headers", "runtime_libraries", "source_manifest", "pair_manifest"):
        path = native_path(combined[key]["path"])
        if digest(path) != combined[key]["sha256"]:
            raise ContractError(f"Combined runtime artifact seal differs: {key}")
        verified[key] = receipt_ref(path)
    source_runtime = native_path(combined["runtime"]["path"])
    pe_metadata(source_runtime.read_bytes())
    root.mkdir(parents=True)
    report = {"schema": 1, "status": "preparing", "pid": os.getpid(), "creation_filetime": own_birth(),
              "command": [sys.executable, *sys.argv], "combined_runtime": combined,
              "combined_handoff": receipt_ref(args.runtime_handoff), "base_db_handoff": receipt_ref(args.db_handoff),
              "verified_runtime_inputs": verified, "minimum_free_gib": require_memory(),
              "scope": "Unchanged built DB payload; separately composed compiler/runtime inputs for new consumer qualification",
              "full_cpp_qualified": False, "provider_admitted": False, "db_payload_rebuilt": False}
    write_json(root / "launch.json", report)
    print(json.dumps({"pid": report["pid"], "created": report["creation_filetime"], "phase": "copying-sealed-inputs"}), flush=True)
    old_stage = Path(base["stage"])
    build_receipt = Path(base["build"]["receipt"]["path"])
    built = sealed_json(build_receipt, base["build"]["receipt"]["sha256"])
    stage_copy = copy_sealed_tree(old_stage, build_receipt, root / "stage")
    old_compiler_receipt = Path(base["compiler_receipt"]["path"])
    old_compiler = sealed_json(old_compiler_receipt, base["compiler_receipt"]["sha256"])
    require_db_cpp_receipt(old_compiler)
    sdk_copy = copy_sealed_tree(Path(old_compiler["prefix"]), old_compiler_receipt, root / "compiler")
    shell_manifest = args.shell_root.parent / "runtime.manifest.json"
    sealed_json(shell_manifest, SHELL_MANIFEST_SHA)
    shell_copy = copy_sealed_tree(args.shell_root, shell_manifest, root / "runtime")
    replacements = {}
    sdk_files = dict(sdk_copy["files"])
    runtime_files = dict(shell_copy["files"])
    selected = {}
    for key in ("public_headers", "runtime_libraries"):
        selected.update(manifest_rows(native_path(combined[key]["path"])))
    for name, sha in selected.items():
        source = producer_root / name
        if digest(source) != sha:
            raise ContractError(f"Combined prefix input differs: {name}")
        destination = root / "compiler" / name
        before = sdk_files.get(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        after = {"sha256": digest(destination), "size": destination.stat().st_size}
        if after["sha256"] != sha or digest(source) != sha:
            raise ContractError("Runtime/header changed during copy")
        sdk_files[name] = after
        if before != after:
            replacements[name] = {"before": before, "after": after}
    # Canonical runtime-root layout for native system()/fork children, not the emulated build driver.
    runtime_dll = root / "runtime/usr/bin/msys-2.0.dll"
    shutil.copy2(source_runtime, runtime_dll)
    runtime_files["usr/bin/msys-2.0.dll"] = {"sha256": digest(runtime_dll), "size": runtime_dll.stat().st_size}
    if runtime_files["usr/bin/msys-2.0.dll"]["sha256"] != RUNTIME_SHA:
        raise ContractError("Combined runtime copy mismatch")
    for path, row in stage_copy["files"].items():
        if path.startswith("usr/bin/"):
            destination = root / "runtime" / path
            if destination.exists() and digest(destination) != row["sha256"]:
                raise ContractError(f"Runtime composition DB collision: {path}")
            if not destination.exists():
                shutil.copy2(root / "stage" / path, destination)
            runtime_files[path] = row
    if inventory(root / "compiler") != sdk_files or inventory(root / "runtime") != runtime_files:
        raise ContractError("New runtime/compiler composition differs beyond declared changes")
    compiler = {**sdk_copy, "files": sdk_files, "prefix": str(root / "compiler"),
                "status": "combined-runtime-private-compiler-composition-not-whole-SDK-admission",
                "combined_handoff_sha256": COMBINED_SHA, "replacements": replacements, "full_cpp_qualified": False}
    write_json(root / "compiler.manifest.json", compiler)
    write_json(root / "runtime.manifest.json", {"files": runtime_files, "prefix": str(root / "runtime"),
               "combined_handoff_sha256": COMBINED_SHA, "required_runtime_directories": ["tmp"]})
    metadata = {}
    for path, row in stage_copy["files"].items():
        data = (root / "stage" / path).read_bytes()
        if data[:2] == b"MZ" or path.endswith((".exe", ".dll", ".pyd")):
            metadata[path] = {**row, **pe_metadata(data)}
    if len(metadata) != 17 or sum(not row["is_dll"] for row in metadata.values()) != 15:
        raise ContractError("Full DB payload does not contain the exact native utilities and libraries")
    copied_source_manifest = root / "source.prepare.json"
    shutil.copyfile(base["prepared_source"]["path"], copied_source_manifest)
    if digest(copied_source_manifest) != base["prepared_source"]["sha256"]:
        raise ContractError("DB source provenance changed")
    shutil.copyfile(base["recipe"]["path"], root / "PKGBUILD")
    source = json.loads(copied_source_manifest.read_text())
    report["source_provenance"] = {
        "upstream": source["source"], "upstream_commit": None,
        "upstream_commit_reason": "Pinned Oracle release archive, not a Git checkout",
        "prepared_tree_inventory": receipt_ref(copied_source_manifest),
        "upstream_original_inventory_sha256": source["original_manifest_sha256"],
        "recipe_repository": "https://github.com/msys2/MSYS2-packages",
        "recipe_commit": "9154e8a73cf7813e3e4b87df14e6aea5776dc571",
        "recipe_archive_sha256": "7cfab11653116d518f45011b3c699e2db13d19d61de56b7c0bd4d10a31890c4d",
        "recipe_sha256": source["recipe_sha256"], "recipe_collection_inventory_sha256": source["recipe_manifest_sha256"],
        "build_receipt": receipt_ref(build_receipt), "native_build_patches": built["working_source_db_customization"],
        "recipe_driver_files": {p.name: digest(p) for p in (HERE / "build-msys-library.py", HERE / "build-msys-library.sh")},
        "recipe_worktree_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "recipe_worktree_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip(),
        "uncommitted_recipe_changes_bound_by_file_hashes": True,
    }
    report.update(status="combined-runtime-db-release-prepared", files=stage_copy["files"],
                  pe_images=metadata, compiler_manifest=receipt_ref(root / "compiler.manifest.json"),
                  runtime_manifest=receipt_ref(root / "runtime.manifest.json"),
                  base_shell_manifest=receipt_ref(shell_manifest), base_build_receipt=receipt_ref(build_receipt))
    for key, row in verified.items():
        if digest(row["path"]) != row["sha256"]:
            raise ContractError(f"Read-only combined runtime artifact changed: {key}")
    verify_tree(old_stage, build_receipt)
    verify_tree(args.shell_root, shell_manifest)
    verify_tree(Path(old_compiler["prefix"]), old_compiler_receipt)
    report["inputs_unchanged"] = True
    write_json(root / "prepare.json", report)
    print(json.dumps({"status": report["status"], "db_pe_images": len(metadata),
                      "sdk_replacements": len(replacements), "prepare": receipt_ref(root / "prepare.json")}), flush=True)


def validate(args):
    root = args.output
    prepared = json.loads((root / "prepare.json").read_text())
    if prepared["status"] != "combined-runtime-db-release-prepared" or not prepared["inputs_unchanged"]:
        raise ContractError("Combined runtime preparation did not pass")
    for name in ("compiler", "runtime"):
        manifest = root / f"{name}.manifest.json"
        if digest(manifest) != prepared[f"{name}_manifest"]["sha256"]:
            raise ContractError(f"Prepared {name} manifest changed")
        verify_tree(root / name, manifest)
    verify_tree(root / "stage", root / "prepare.json")
    output = root / "proof"
    output.mkdir()
    (output / "native-exits").mkdir()
    (output / "temp").mkdir()
    sdk, runtime = root / "compiler", root / "runtime"
    observer = Path(r"C:\ag-e138920f\native-test-driver-02")
    verify_driver(observer)
    report = {"schema": 1, "status": "failed", "pid": os.getpid(), "creation_filetime": own_birth(),
              "command": [sys.executable, *sys.argv], "prepare": receipt_ref(root / "prepare.json"),
              "commands": {}, "minimum_free_gib": require_memory(), "runtime_sha256": RUNTIME_SHA,
              "scope": "Ordinary DB API/CLI and exact DLL closure on combined907runtime; not full upstream/provider admission",
              "qualification_limitations": LIMITATIONS}
    write_json(output / "launch.json", report)
    identities = {str(path): digest(path) for path in (root / "prepare.json", root / "compiler.manifest.json",
                  root / "runtime.manifest.json", Path(__file__), HERE / "db_native_driver.py",
                  HERE / "db_native_checks.py", HERE / "native_job_runner.py")}
    env = environment(sdk, output)

    def run(name, command, cwd=output, timeout=120, target_env=None):
        row = observe(command, cwd, target_env or env, output, name, observer, timeout)
        report["commands"][name] = row
        report["minimum_free_gib"] = min(report["minimum_free_gib"], require_memory())
        if not row["process"]["passed"]:
            raise ContractError(f"Native combined-runtime phase failed: {name}")
        return row

    runtime_before = json.loads((root / "runtime.manifest.json").read_text())["files"]
    additions = {}
    try:
        for name, source, language, library in (
            ("c", "native-db-consumer.c", "gcc", "db"),
            ("cpp", "native-db-consumer.cpp", "g++", "db_cxx"),
            ("185", "native-db-185.c", "gcc", "db"),
            ("process", "db-native-driver-process.c", "gcc", None),
        ):
            fixture = HERE / "fixtures" / source
            identities[str(fixture)] = digest(fixture)
            binary = runtime / "usr/bin" / ("db907-proof-" + name + ".exe")
            command = [sdk / "bin" / (language + ".exe"), "-O2", "-g", "-Werror",
                       "-fstack-protector-strong", "-I" + str(root / "stage/usr/include"), fixture,
                       "-L" + str(root / "stage/usr/lib"), "-Wl,--no-insert-timestamp", "-o", binary]
            if library:
                command.append("-l" + library)
            run("compile-" + name, command)
            additions[binary.relative_to(runtime).as_posix()] = {"sha256": digest(binary), "size": binary.stat().st_size}
        env = environment(sdk, output)
        env["PATH"] = os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
        env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
        env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(runtime / "tmp")
        report["native_target_path"] = env["PATH"]
        report["test_runtime"] = {p.name: receipt_ref(p) for p in (runtime / "usr/bin").glob("*.dll")}
        # Reject emulated binaries throughout the private execution closure before any target is run.
        report["runtime_pe"] = {p.name: pe_metadata(p.read_bytes()) for p in (runtime / "usr/bin").iterdir()
                                if p.is_file() and p.suffix.lower() in (".exe", ".dll")}
        for name, marker in (("c", b"DB C PASS:"), ("185", b"DB 185 PASS:"), ("process", b"DB native driver PASS:")):
            cwd = output / name
            cwd.mkdir()
            exe = runtime / f"usr/bin/db907-proof-{name}.exe"
            row = run(name, [sys.executable, "-I", observer / "native-target-exec.py", exe], cwd, 60)
            if name != "process":
                require_exit(row, exe)
            if marker not in (output / f"{name}.log").read_bytes() or any(e["raw_exit"] != 0 for e in row["evidence"]["native_target_exits"]):
                raise ContractError("Native API/process behavior or nested exit failed")
        cwd = output / "cpp"
        cwd.mkdir()
        expected = {name: {"path": str(runtime / "usr/bin" / name), "sha256": digest(runtime / "usr/bin" / name)}
                    for name in ("msys-db_cxx-6.2.dll", "msys-2.0.dll")}
        held_cpp(runtime / "usr/bin/db907-proof-cpp.exe", cwd, env, output, observer, expected, report)
        for exe in sorted((root / "stage/usr/bin").glob("*.exe")):
            if exe.stem == "db_tuner":
                continue
            command = [sys.executable, "-I", observer / "native-target-exec.py", runtime / "usr/bin" / exe.name, "-V"]
            run("version-" + exe.stem, command, output, 30)
            if b"Berkeley DB 6.2.32" not in (output / ("version-" + exe.stem + ".log")).read_bytes():
                raise ContractError(f"Version execution did not identify DB6.2.32: {exe.name}")
        cli = output / "cli"
        cli.mkdir()
        (cli / "input.txt").write_text("alpha\none\nbeta\ntwo\n", newline="\n")
        def tool(name, *arguments):
            return [sys.executable, "-I", observer / "native-target-exec.py", runtime / "usr/bin" / (name + ".exe"), *arguments]
        run("cli-load", tool("db_load", "-T", "-t", "btree", "-f", "input.txt", "roundtrip.db"), cli)
        run("cli-verify", tool("db_verify", "roundtrip.db"), cli)
        run("cli-tuner", tool("db_tuner", "-d", "roundtrip.db"), cli)
        run("cli-dump", tool("db_dump", "-p", "-f", "dump.txt", "roundtrip.db"), cli)
        run("cli-reload", tool("db_load", "-f", "dump.txt", "restored.db"), cli)
        run("cli-redump", tool("db_dump", "-p", "-f", "redump.txt", "restored.db"), cli)
        if (cli / "dump.txt").read_bytes() != (cli / "redump.txt").read_bytes():
            raise ContractError("Installed CLI database round trip differs")
        report["cli_roundtrip_sha256"] = digest(cli / "dump.txt")
        # Capture the ordinary C target's exact module paths using the existing debugger helper.
        capture = HERE / "capture-native-exception.py"
        identities[str(capture)] = digest(capture)
        row = run("c-modules", [sys.executable, "-B", capture, "--executable", runtime / "usr/bin/db907-proof-c.exe",
                               "--path-directory", runtime / "usr/bin", "--output", output / "capture-c"], output, 60)
        require_exit(row, runtime / "usr/bin/db907-proof-c.exe")
        captured = json.loads((output / "capture-c/result.json").read_text())
        if captured["exit_code"] != 0 or captured["timed_out"]:
            raise ContractError("C module/behavior proof failed")
        loaded = {Path(m["path"]).name.lower(): m["path"] for m in captured["modules"]}
        for name, sha in (("msys-2.0.dll", RUNTIME_SHA),
                          ("msys-db-6.2.dll", prepared["files"]["usr/bin/msys-db-6.2.dll"]["sha256"])):
            actual = Path(loaded.get(name, "").removeprefix("\\\\?\\")).resolve()
            if actual != (runtime / "usr/bin" / name).resolve() or digest(actual) != sha:
                raise ContractError(f"C API loaded the wrong runtime/library: {name}")
        report["c_loaded_modules"] = loaded
        report["status"] = "native-db-combined907-api-cli-and-modules-passed"
    except (OSError, ContractError) as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            verify_tree(sdk, root / "compiler.manifest.json")
            verify_tree(root / "stage", root / "prepare.json")
            if inventory(runtime) != {**runtime_before, **additions}:
                raise ContractError("Native runtime composition changed beyond new proof executables")
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("Release proof inputs changed")
            verify_driver(observer)
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update(status="failed", inputs_unchanged=False, integrity_error=str(error))
            raise
        finally:
            report["input_identities"] = identities
            report["proof_executable_files"] = additions
            write_json(output / "result.json", report)
    print(report["status"], flush=True)


def complete_validation(args):
    """Retain completed API proof when a CLI's unsupported version option stopped the run."""
    root = args.output
    previous_path = root / "proof/result.json"
    previous = json.loads(previous_path.read_text())
    if (previous.get("error") != "Native combined-runtime phase failed: version-db_tuner"
            or not previous.get("inputs_unchanged")
            or previous["commands"]["version-db_tuner"]["process"]["exit"] != 1):
        raise ContractError("This continuation requires the exact unsupported db_tuner version-option result")
    required = ["compile-c", "compile-cpp", "compile-185", "compile-process", "c", "185", "process", "cpp-held"]
    if any(not previous["commands"][name]["process"]["passed"] for name in required):
        raise ContractError("The independent new-runtime API proof must already have passed")
    output = root / "proof-complete"
    output.mkdir()
    (output / "native-exits").mkdir()
    runtime, sdk = root / "runtime", root / "compiler"
    before = require_continuation_runtime(runtime, root / "runtime.manifest.json", previous)
    if previous["prepare"]["sha256"] != digest(root / "prepare.json") or previous["runtime_sha256"] != RUNTIME_SHA:
        raise ContractError("Continuation proof preparation/runtime identity differs")
    verify_tree(root / "stage", root / "prepare.json")
    compiler_manifest = root / "compiler.manifest.json"
    if previous["input_identities"].get(str(compiler_manifest)) != digest(compiler_manifest):
        raise ContractError("Continuation compiler manifest changed")
    verify_tree(sdk, compiler_manifest)
    report = {**previous, "status": "failed", "prior_attempt": receipt_ref(previous_path),
              "commands": {k: v for k, v in previous["commands"].items() if v["process"]["passed"]},
              "retained_failed_commands": {"unsupported-db_tuner-V": previous["commands"]["version-db_tuner"]},
              "continuation_pid": os.getpid(), "continuation_creation_filetime": own_birth(),
              "continuation_source": receipt_ref(Path(__file__)),
              "correction": "db_tuner accepts -d, not -V; exercise its real database analysis instead"}
    report.pop("error", None)
    write_json(output / "launch.json", report)
    env = environment(sdk, output)
    env["PATH"] = os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(runtime / "tmp")
    observer = Path(r"C:\ag-e138920f\native-test-driver-02")

    def run(name, command, cwd=output):
        row = observe(command, cwd, env, output, name, observer, 60)
        report["commands"][name] = row
        if not row["process"]["passed"]:
            raise ContractError(f"Native continuation failed: {name}")
        return row

    def tool(name, *arguments):
        return [sys.executable, "-I", observer / "native-target-exec.py", runtime / "usr/bin" / (name + ".exe"), *arguments]

    try:
        for name in ("db_upgrade", "db_verify"):
            run("version-" + name, tool(name, "-V"))
            if b"Berkeley DB 6.2.32" not in (output / ("version-" + name + ".log")).read_bytes():
                raise ContractError("Remaining utility version does not match")
        cli = output / "cli"
        cli.mkdir()
        (cli / "input.txt").write_text("alpha\none\nbeta\ntwo\n", newline="\n")
        run("cli-load", tool("db_load", "-T", "-t", "btree", "-f", "input.txt", "roundtrip.db"), cli)
        run("cli-verify", tool("db_verify", "roundtrip.db"), cli)
        run("cli-tuner", tool("db_tuner", "-d", "roundtrip.db"), cli)
        run("cli-dump", tool("db_dump", "-p", "-f", "dump.txt", "roundtrip.db"), cli)
        run("cli-reload", tool("db_load", "-f", "dump.txt", "restored.db"), cli)
        run("cli-redump", tool("db_dump", "-p", "-f", "redump.txt", "restored.db"), cli)
        if (cli / "dump.txt").read_bytes() != (cli / "redump.txt").read_bytes():
            raise ContractError("Installed CLI round trip differs")
        report["cli_roundtrip_sha256"] = digest(cli / "dump.txt")
        capture = HERE / "capture-native-exception.py"
        row = run("c-modules", [sys.executable, "-B", capture, "--executable", runtime / "usr/bin/db907-proof-c.exe",
                               "--path-directory", runtime / "usr/bin", "--output", output / "capture-c"])
        require_exit(row, runtime / "usr/bin/db907-proof-c.exe")
        captured = json.loads((output / "capture-c/result.json").read_text())
        loaded = {Path(m["path"]).name.lower(): m["path"] for m in captured["modules"]}
        if captured["exit_code"] != 0 or captured["timed_out"]:
            raise ContractError("C module/behavior proof failed")
        prepared = json.loads((root / "prepare.json").read_text())
        for name, sha in (("msys-2.0.dll", RUNTIME_SHA),
                         ("msys-db-6.2.dll", prepared["files"]["usr/bin/msys-db-6.2.dll"]["sha256"])):
            actual = Path(loaded.get(name, "").removeprefix("\\\\?\\")).resolve()
            if actual != (runtime / "usr/bin" / name).resolve() or digest(actual) != sha:
                raise ContractError("C API loaded a non-matching DLL")
        report["c_loaded_modules"] = loaded
        report["status"] = "native-db-combined907-api-cli-and-modules-passed"
    except (OSError, ContractError) as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            verify_tree(root / "stage", root / "prepare.json")
            verify_tree(sdk, root / "compiler.manifest.json")
            if inventory(runtime) != before or digest(previous_path) != report["prior_attempt"]["sha256"]:
                raise ContractError("Continuation mutated runtime or original proof")
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update(status="failed", inputs_unchanged=False, integrity_error=str(error))
            raise
        finally:
            write_json(output / "result.json", report)
    print(report["status"], flush=True)


def package(args):
    root = args.output
    prepared = json.loads((root / "prepare.json").read_text())
    proof_path = root / ("proof-complete/result.json" if (root / "proof-complete/result.json").exists() else "proof/result.json")
    proof = json.loads(proof_path.read_text())
    require_package_proof(root / "prepare.json", prepared, proof)
    verify_tree(root / "stage", root / "prepare.json")
    out = root / "packages"
    out.mkdir()
    epoch = int(Path(prepared["base_build_receipt"]["path"]).stat().st_mtime)
    report = {"schema": 1, "status": "failed", "packages": [], "source_provenance": prepared["source_provenance"],
              "prepare": receipt_ref(root / "prepare.json"), "combined_runtime_proof": receipt_ref(proof_path),
              "runtime_sha256": RUNTIME_SHA, "buildtool": receipt_ref(HERE / "db_package.py"),
              "unsigned_local_packages": True, "provider_admitted": False, "full_upstream_qualified": False,
              "qualification_limitations": LIMITATIONS,
              "mutex_timeout_evidence": receipt_ref(Path(r"C:\ag-db-e138-01\resume-20260909\mutex01\matrix-handoff.json"))}
    for name, files in split_inventory(prepared["files"]).items():
        path = out / f"{name}-6.2.32-6-aarch64.pkg.tar.zst"
        packaged = create_package(root / "stage", path, name, files, epoch,
                                  prepared["source_provenance"]["recipe_sha256"], str(Path(prepared["base_build_receipt"]["path"]).with_name("build03") / "build"))
        packaged["qualification_limitations"] = LIMITATIONS
        report["packages"].append(packaged)
    runtime_stage = root / "runtime-only"
    runtime_stage.mkdir()
    files = split_inventory(prepared["files"])["libdb"]
    for name in files:
        target = runtime_stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "stage" / name, target)
    if inventory(runtime_stage) != files:
        raise ContractError("MVP runtime-only payload differs")
    report.update(status="native-db-combined907-packaged-unsigned-provider-pending", runtime_only={
                  "root": str(runtime_stage), "files": files}, full_stage={"root": str(root / "stage"), "files": prepared["files"]})
    write_json(root / "package-receipt.json", report)
    print(json.dumps({"status": report["status"], "receipt": receipt_ref(root / "package-receipt.json"),
                      "packages": [{k: p[k] for k in ("path", "size", "sha256")} for p in report["packages"]]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "validate", "complete-validation", "package"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db-handoff", type=Path)
    parser.add_argument("--runtime-handoff", type=Path)
    parser.add_argument("--shell-root", type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.operation == "prepare" and any(getattr(args, name) is None for name in ("db_handoff", "runtime_handoff", "shell_root")):
        parser.error("prepare requires explicit DB, runtime and frozen shell inputs")
    {"prepare": prepare, "validate": validate, "complete-validation": complete_validation, "package": package}[args.operation](args)


if __name__ == "__main__":
    main()
