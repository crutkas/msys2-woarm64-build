"""Recover GDBM in owned roots without mutating the original failed build."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import re
import tarfile

from db_native_checks import environment, observe
from db_channel_checks import own_birth
from db_package import pe_metadata
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json


OLD = Path(r"C:\ap06-78\perl-recovery-20260911-08")
SDK = Path(r"C:\ag-readline-e138-01\combined-20260911-01")
SDK_SHA = "69bde4474dc5c93660a598fac1ca8d3f97907cdabdbd4a454f51adeace711d34"
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
ARCHIVE_SHA = "6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e"


def copy_tree(source, destination, expected=None):
    before = inventory(source)
    directories = directory_names(source)
    if expected is not None and before != expected:
        raise ContractError(f"Sealed input tree differs: {source}")
    if destination.exists():
        raise ContractError("Recovery copies must use fresh destinations")
    shutil.copytree(source, destination)
    copied = inventory(destination)
    if copied != before or inventory(source) != before or directory_names(source) != directories:
        raise ContractError("Complete before/copy/after inventory equality failed")
    return {"source": str(source), "root": str(destination), "files": copied,
            "directories": directory_names(destination), "source_unchanged": True,
            "before_copy_after_equal": True}


def prepare(args):
    root = args.root
    if root.exists():
        raise ContractError("A new owned GDBM root is required")
    if digest(SDK / "inputs.json") != SDK_SHA:
        raise ContractError("Current native SDK receipt changed")
    sdk = json.loads((SDK / "inputs.json").read_text())
    source_inputs = json.loads((OLD / "gdbm-source-inputs-01.json").read_text())
    for row in source_inputs["inputs"]:
        if digest(row["path"]) != row["sha256"]:
            raise ContractError("Pinned GDBM source/recipe/patch input changed")
    if digest(OLD / "downloads/gdbm-1.26.tar.gz") != ARCHIVE_SHA:
        raise ContractError("Pinned GDBM archive mismatch")
    root.mkdir(parents=True)
    for name in ("receipts", "logs", "temp", "home", "native-exits"):
        (root / name).mkdir()
    report = {"schema": 1, "status": "copying", "pid": os.getpid(), "created": own_birth(),
              "command": [sys.executable, *sys.argv], "sdk_input_sha256": SDK_SHA,
              "minimum_free_gib": require_memory(), "source_inputs": source_inputs,
              "scope": "Read-only original failed GDBM build and current907 native input adoption; no admission"}
    write_json(root / "launch.json", report)
    print(json.dumps({"pid": report["pid"], "created": report["created"], "phase": "copying-original-GDBM"}), flush=True)
    source = copy_tree(OLD / "src/gdbm-1.26", root / "original-build")
    write_json(root / "receipts/original-build.json", source)
    for name in ("gdbm-source-inputs-01.json", "db-libxcrypt-stage-01.json"):
        shutil.copy2(OLD / name, root / "receipts" / name)
    shutil.copytree(OLD / "downloads", root / "downloads")
    for name in ("gdbm-check.log", "gdbm-configure.log", "gdbm-make.log", "gdbm-install.log"):
        shutil.copy2(OLD / "logs" / name, root / "logs" / ("original-" + name))
    product = copy_tree(OLD / "gdbm-dest", root / "original-stage")
    write_json(root / "receipts/original-stage.json", product)
    compiler = copy_tree(SDK / "compiler", root / "compiler", sdk["compiler_files"])
    write_json(root / "receipts/compiler.json", compiler)
    development = copy_tree(SDK / "sdk", root / "sdk", sdk["sdk_files"])
    write_json(root / "receipts/sdk.json", development)
    # Existing private native shell closure, not the x64 bootstrap and not DB payload.
    shell_root = Path(r"C:\ag-db-e138-01\combined-20260911\runtime")
    expected = json.loads((shell_root.parent / "runtime.manifest.json").read_text())["files"]
    actual = inventory(shell_root)
    if any(actual.get(name) != row for name, row in expected.items()):
        raise ContractError("Frozen native shell base payload changed")
    runtime = copy_tree(shell_root, root / "runtime")
    if runtime["files"]["usr/bin/msys-2.0.dll"]["sha256"] != RUNTIME_SHA:
        raise ContractError("Wrong native runtime cohort")
    (root / "runtime/tmp").mkdir(exist_ok=True)
    write_json(root / "receipts/runtime.json", runtime)
    observer_manifest = SDK / "observer.manifest.json"
    if digest(observer_manifest) != sdk["observer_manifest_sha256"]:
        raise ContractError("Current observer manifest changed")
    observer = copy_tree(SDK / "observer", root / "observer",
                         json.loads(observer_manifest.read_text())["files"])
    shutil.copy2(observer_manifest, root / "observer.manifest.json")
    report.update(status="gdbm-private-inputs-adopted", source_files=len(source["files"]),
                  product_files=len(product["files"]), runtime_files=len(runtime["files"]),
                  original_wrapper_sha256=digest(root / "original-build/tests/gtver.exe"),
                  original_target_sha256=digest(root / "original-build/tests/.libs/gtver.exe"),
                  source_signature_verified=False)
    write_json(root / "prepare.json", report)
    print(json.dumps({"status": report["status"], "root": str(root), "prepare_sha256": digest(root / "prepare.json")}), flush=True)


def reproduce(args):
    root = args.root
    prepared = json.loads((root / "prepare.json").read_text())
    if prepared["status"] != "gdbm-private-inputs-adopted":
        raise ContractError("Adopted inputs required")
    output = root / "reproduce01"
    output.mkdir()
    (output / "native-exits").mkdir()
    tests = output / "tests"
    (tests / ".libs").mkdir(parents=True)
    preserved_wrapper = OLD / "gdbm-wrapper-firstfault-03/tests/gtver.exe"
    if digest(preserved_wrapper) != "921ef3d6fc32830dc966d79f28a1238d6c5ef36c91cd1bab6fe943c02b6db325":
        raise ContractError("Preserved original libtool wrapper differs")
    for source, target in (
        (preserved_wrapper, tests / "gtver.exe"),
        (root / "original-build/tests/.libs/gtver.exe", tests / ".libs/gtver.exe"),
        (root / "original-build/src/.libs/cyggdbm-6.dll", tests / ".libs/cyggdbm-6.dll"),
    ):
        shutil.copy2(source, target)
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (root / "runtime/usr/bin", tests / ".libs",
                                          Path(os.environ["SystemRoot"]) / "System32")))
    report = {"schema": 1, "status": "incomplete", "pid": os.getpid(), "created": own_birth(),
              "cases": {}, "executable_identities": {str(path): digest(path)
                  for path in (tests / "gtver.exe", tests / ".libs/gtver.exe", tests / ".libs/cyggdbm-6.dll")},
              "unmodified_wrapper_and_target": True, "base_path": env["PATH"]}
    report["preserved_wrapper_input"] = {"path": str(preserved_wrapper), "sha256": digest(preserved_wrapper)}
    report["old_current_build_is_diagnostic_materialization"] = prepared["original_wrapper_sha256"] == prepared["original_target_sha256"]
    write_json(output / "launch.json", report)
    for name, executable, arguments, path in (
        ("wrapper-split-root", tests / "gtver.exe", ["--lt-debug"], env["PATH"]),
        ("direct-private-root", tests / ".libs/gtver.exe", [], env["PATH"]),
        ("wrapper-coherent-original-root", tests / "gtver.exe", ["--lt-debug"],
         os.pathsep.join(map(str, (Path(r"C:\ag-db-e138-01\combined-20260911\runtime\usr\bin"),
                                  tests / ".libs", Path(os.environ["SystemRoot"]) / "System32")))),
    ):
        case_env = {**env, "PATH": path}
        command = [sys.executable, "-I", root / "observer/native-target-exec.py", executable, *arguments]
        row = observe(command, tests, case_env, output, name, root / "observer", 45)
        report["cases"][name] = {**row, "path": path}
    if any(digest(path) != sha for path, sha in report["executable_identities"].items()):
        raise ContractError("Original reproducer bytes changed")
    report["status"] = "original-wrapper-installation-root-control-recorded"
    report["failure_is_not_admission"] = True
    write_json(output / "result.json", report)
    print(json.dumps({name: {"passed": row["process"]["passed"], "exit": row["process"]["exit"]}
                      for name, row in report["cases"].items()}), flush=True)


def isolated_observe(root, output, name, command, cwd, env, timeout=60):
    case = output / name
    case.mkdir()
    (case / "native-exits").mkdir()
    case_env = {**env, "WOARM64_NATIVE_EXIT_DIR": str(case / "native-exits")}
    return observe(command, cwd, case_env, case, "command", root / "observer", timeout)


def reproduce_mounts(args):
    root = args.root
    output = root / "reproduce02"
    output.mkdir()
    tests = output / "tests"
    (tests / ".libs").mkdir(parents=True)
    original = OLD / "gdbm-wrapper-firstfault-03/tests/gtver.exe"
    if digest(original) != "921ef3d6fc32830dc966d79f28a1238d6c5ef36c91cd1bab6fe943c02b6db325":
        raise ContractError("The original failing wrapper must be preserved")
    for source, target in ((original, tests / "gtver.exe"),
                          (root / "original-build/tests/.libs/gtver.exe", tests / ".libs/gtver.exe"),
                          (root / "original-build/src/.libs/cyggdbm-6.dll", tests / ".libs/cyggdbm-6.dll")):
        shutil.copy2(source, target)
    # Root06 had no fstab; retain that original private-root condition for the
    # negative discriminator rather than accepting invalid old /cygdrive paths.
    no_mount = output / "original-layout/usr/bin"
    no_mount.mkdir(parents=True)
    for name in ("msys-2.0.dll", "bash.exe", "sh.exe"):
        shutil.copy2(root / "runtime/usr/bin" / name, no_mount / name)
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    direct_path = os.pathsep.join(map(str, (no_mount, tests / ".libs",
                                          Path(os.environ["SystemRoot"]) / "System32")))
    fixed_source = output / "lt-gtver-coherent.c"
    source = (root / "original-build/tests/.libs/lt-gtver.c").read_text()
    def posix(path):
        return "/cygdrive/" + path.drive[0].lower() + "/" + path.relative_to(path.anchor).as_posix()
    for variable, value in (("EXE_PATH_VALUE", posix(no_mount) + ":"),
                            ("LIB_PATH_VALUE", posix(tests / ".libs") + ":")):
        source, count = re.subn(rf'const char \* {variable}\s+= "[^"]*";',
                              f'const char * {variable} = "{value}";', source)
        if count != 1:
            raise ContractError("Unexpected generated libtool wrapper fields")
    fixed_source.write_text(source, newline="\n")
    report = {"schema": 1, "status": "incomplete", "pid": os.getpid(), "created": own_birth(),
              "cases": {}, "original_wrapper_sha256": digest(original),
              "target_sha256": digest(tests / ".libs/gtver.exe"),
              "control_scope": "Original wrapper versus regenerated path constants only, no EXE_PATH removal or wrapper-to-real-PE replacement"}
    write_json(output / "launch.json", report)
    try:
        compile_env = environment(root / "compiler", output)
        compile_env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
        fixed = tests / "gtver-coherent.exe"
        row = isolated_observe(root, output, "compile-coherent-wrapper",
              [root / "compiler/bin/gcc.exe", "-O2", "-g", "-fstack-protector-strong",
               fixed_source, "-o", fixed], output, compile_env)
        report["cases"]["compile"] = row
        if not row["process"]["passed"]:
            raise ContractError("Coherent wrapper control failed to compile")
        # libtool's target filename remains gtver.exe in the unchanged wrapper.
        for name, executable, path in (
            ("original-wrapper", tests / "gtver.exe", direct_path),
            ("direct-target", tests / ".libs/gtver.exe", direct_path),
            ("coherent-wrapper", fixed, direct_path),
        ):
            case_env = {**env, "PATH": path}
            row = isolated_observe(root, output, name,
                [sys.executable, "-I", root / "observer/native-target-exec.py",
                 executable, "--lt-debug", "-lib", "-full", "-header", "-full"]
                if name != "direct-target" else
                [sys.executable, "-I", root / "observer/native-target-exec.py",
                 executable, "-lib", "-full", "-header", "-full"],
                tests, case_env)
            report["cases"][name] = row
        report["status"] = "original-root-and-generated-path-discriminator-recorded"
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({name: row["process"] for name, row in report["cases"].items()}), flush=True)


def prepare_build(args):
    root = args.root
    source = root / "source"
    if source.exists() and not args.resume_prepare:
        raise ContractError("Prepared GDBM source must be fresh")
    print(json.dumps({"pid": os.getpid(), "created": own_birth(), "phase": "preparing-full-profile",
                      "free_gib": require_memory(), "resume": args.resume_prepare}), flush=True)
    source.mkdir(exist_ok=args.resume_prepare)
    # Reuse the existing recipe-generated source, not configured Makefiles,
    # diagnostic atlocal overrides, wrapper substitutions, or old build products.
    original_manifest = json.loads((root / "receipts/original-build.json").read_text())
    verify_tree(root / "original-build", root / "receipts/original-build.json")
    if digest(root / "downloads/gdbm-1.26.tar.gz") != ARCHIVE_SHA:
        raise ContractError("The source archive changed")
    selected = {}
    with tarfile.open(root / "downloads/gdbm-1.26.tar.gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            name = Path(member.name).relative_to("gdbm-1.26").as_posix()
            old = root / "original-build" / name
            if not old.is_file():
                raise ContractError(f"Prepared source is missing an upstream input: {name}")
            destination = source / name
            if not args.resume_prepare:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, destination)
            selected[name] = original_manifest["files"][name]
    if inventory(source) != selected:
        raise ContractError("Prepared-only source adoption differs")
    source_receipt = {
        "files": selected, "source_archive_sha256": ARCHIVE_SHA,
        "prepared_source_inventory_sha256": digest(root / "receipts/original-build.json"),
        "scope": "Only archive-listed source/generator files from the original recipe-generated tree; no configured build output or diagnostic test overrides"}
    if args.resume_prepare:
        if json.loads((root / "receipts/build-source.json").read_text()) != source_receipt:
            raise ContractError("The sealed source receipt differs")
    else:
        write_json(root / "receipts/build-source.json", source_receipt)
    if not args.resume_prepare:
        copy_tree(root / "runtime", root / "build-runtime")
        copy_tree(root / "sdk", root / "dependencies")
    expected_runtime = dict(json.loads((root / "receipts/runtime.json").read_text())["files"])
    expected_dependencies = dict(json.loads((root / "receipts/sdk.json").read_text())["files"])
    receipts = []
    for label, stage, manifest, sha in (
        ("iconv", Path(r"C:\ag-bash-e138-01\iconv-full-recovery-02\stage"),
         Path(r"C:\ag-bash-e138-01\iconv-full-recovery-02\stage.inventory.json"),
         "ade429de6ca8ea1c6da0e9937ba4d52be1dc1b2250a04ed0901659b4c72635ca"),
        ("intl", Path(r"C:\ag-bash-e138-01\gettext-runtime-relocatable-03\stage"),
         Path(r"C:\ag-bash-e138-01\gettext-runtime-relocatable-03\stage.inventory.json"),
         "c89b98a0eab2f9efaa04272db5318543ed56bcf4d23d3ebd351d42621a64dd2b"),
    ):
        if digest(manifest) != sha:
            raise ContractError("NLS development input receipt changed")
        record = json.loads(manifest.read_text())
        declared = record.get("files", record)
        expected = {name: {field: row[field] for field in ("sha256", "size")}
                    for name, row in declared.items()}
        before = inventory(stage)
        if before != expected:
            raise ContractError(f"{label} stage differs from its inventory")
        for name, row in declared.items():
            if "machine" in row:
                if pe_metadata((stage / name).read_bytes())["machine"].lower() != row["machine"].lower():
                    raise ContractError("NLS input PE machine differs")
        changes = {}
        for name, row in expected.items():
            if name.startswith(("usr/include/", "usr/lib/")):
                target = root / "dependencies" / name
                expected_dependencies[name] = row
            elif name.startswith("usr/bin/") and name.endswith(".dll"):
                target = root / "build-runtime" / name
                expected_runtime[name] = row
            else:
                continue
            old_sha = digest(target) if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / name, target)
            if digest(target) != row["sha256"]:
                raise ContractError("Native dependency copy differs")
            changes[str(target.relative_to(root))] = {"before": old_sha, "after": row["sha256"]}
        if inventory(stage) != before:
            raise ContractError("Frozen native NLS source changed")
        receipts.append({"label": label, "source": str(stage), "manifest_sha256": sha, "changes": changes})
    if inventory(root / "build-runtime") != expected_runtime or inventory(root / "dependencies") != expected_dependencies:
        raise ContractError("The composed prefix contains unexplained changes")
    # Preserve the bootstrap as an explicit tool-only input, never a target PATH
    # substitute ahead of the private native runtime.
    bootstrap = Path(r"C:\ag-db-e138-01\inputs\msys64")
    bootstrap_manifest = Path(r"C:\ag-db-e138-01\inputs\msys64.copy.json")
    verify_tree(bootstrap, bootstrap_manifest)
    copied = copy_tree(bootstrap, root / "bootstrap",
                       json.loads(bootstrap_manifest.read_text())["files"])
    write_json(root / "receipts/bootstrap.json", copied)
    for name in ("build", "stage"):
        (root / name).mkdir()
    write_json(root / "receipts/build-inputs.json", {
        "schema": 1, "source": str(source), "source_manifest_sha256": digest(root / "receipts/build-source.json"),
        "native_runtime": {"root": str(root / "build-runtime"), "files": expected_runtime},
        "dependencies": {"root": str(root / "dependencies"), "files": expected_dependencies},
        "NLS_input_provenance": receipts, "compiler_manifest_sha256": digest(root / "receipts/compiler.json"),
        "bootstrap_manifest_sha256": digest(root / "receipts/bootstrap.json"),
        "status": "native-GDBM-full-profile-build-inputs-ready"})
    print("native-GDBM-full-profile-build-inputs-ready", flush=True)


def build(args):
    root = args.root
    target_loader(root)
    output = root / args.run_name
    output.mkdir()
    (output / "native-exits").mkdir()
    configured_before = {}
    objects_before = {}
    if args.phase == "configure":
        for name in ("autoconf.h", "config.log", "libtool", "tests/atconfig", "tests/atlocal"):
            path = root / "build" / name
            if path.exists():
                destination = output / "before" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                configured_before[name] = digest(path)
        objects_before = {str(path.relative_to(root)): digest(path)
                          for path in (root / "build").rglob("*.o")}
    mount = root / "host-target-runtime/etc/fstab"
    source_mount = root / "build-runtime/etc/fstab"
    if not mount.exists():
        mount.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_mount, mount)
    if digest(mount) != digest(source_mount):
        raise ContractError("Host-launched native target mount contract differs")
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (root / "build-runtime/usr/bin", root / "compiler/bin",
                                          root / "bootstrap/usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    script = Path(__file__).with_name("build-gdbm-native.sh").resolve()
    command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               root, args.phase]
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "command": list(map(str, command)), "phase": args.phase, "script_sha256": digest(script),
        "free_gib": require_memory(), "jobs_maximum": 2})
    row = isolated_observe(root, output, "build-check-install", command, root, env, 1800)
    configured_after = {name: digest(root / "build" / name) for name in configured_before}
    objects_after = ({str(path.relative_to(root)): digest(path)
                      for path in (root / "build").rglob("*.o")} if objects_before else {})
    write_json(output / "result.json", {"process": row, "script_sha256": digest(script),
        "status": "phase-completed" if row["process"]["passed"] else "failed",
        "phase": args.phase,
        "configuration_before": configured_before, "configuration_after": configured_after,
        "objects_before": objects_before, "objects_after": objects_after,
        "target_mount_sha256": digest(mount),
        "inputs": str(root / "receipts/build-inputs.json")})
    if not row["process"]["passed"] or objects_before != objects_after:
        raise ContractError("GDBM full-profile build/check/install failed; original evidence retained")


def target_loader(root):
    native = root / "host-target-runtime/usr/bin"
    native.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in (root / "build-runtime/usr/bin").glob("*.dll"):
        pe_metadata(path.read_bytes())
        sha = digest(path)
        if not (native / path.name).exists():
            shutil.copy2(path, native / path.name)
        if digest(path) != sha or digest(native / path.name) != sha:
            raise ContractError("Native target loader input changed")
        files[path.name] = {"sha256": sha, "size": path.stat().st_size}
    runtime_receipt = {
        "role": "DLL-only native target loader closure; all host programs remain in their x64 bootstrap",
        "source": str(root / "build-runtime/usr/bin"), "files": files}
    receipt_path = root / "host-target-runtime/input.json"
    if receipt_path.exists():
        if json.loads(receipt_path.read_text()) != runtime_receipt:
            raise ContractError("DLL-only target loader receipt changed")
    else:
        write_json(receipt_path, runtime_receipt)
    return native


def wrapper_paths(path):
    fields = re.findall(r'const char \* (?:EXE|LIB)_PATH_VALUE\s+= "([^"]*)";', path.read_text())
    return fields, len(fields) == 2 and not any(
        re.search(r"(?:^|:)[A-Za-z]:[\\/]", field) for field in fields)


def relink_wrapper(args):
    root = args.root
    output = root / args.run_name
    output.mkdir()
    native = target_loader(root)
    tests = root / "build/tests"
    before = {}
    for name in ("gtver.exe", "gtver.o", ".libs/gtver.exe", ".libs/lt-gtver.c"):
        path = tests / name
        before[name] = digest(path)
        target = output / "before" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (native, root / "bootstrap/usr/bin", root / "compiler/bin",
                                          Path(os.environ["SystemRoot"]) / "System32")))
    script = Path(__file__).with_name("relink-gdbm-wrappers.sh").resolve()
    selected = {"tools": [], "tests": []}
    if args.all_wrappers:
        for directory in selected:
            for source in (root / "build" / directory / ".libs").glob("lt-*.c"):
                stem = source.stem.removeprefix("lt-")
                if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
                    raise ContractError("Unexpected upstream wrapper target name")
                _, valid = wrapper_paths(source)
                for binary in (source.parent.parent / (stem + ".exe"), source.parent / (stem + ".exe")):
                    if not binary.is_file():
                        valid = False
                        continue
                    try:
                        pe_metadata(binary.read_bytes())
                    except ContractError:
                        valid = False
                if not valid:
                    selected[directory].append(stem)
        for directory, names in selected.items():
            (output / (directory + ".targets")).write_text("".join(name + "\n" for name in names), newline="\n")
    compat = root / "build/compat/libgdbm_compat.la"
    compat_relink = bool(re.search(r"[A-Za-z]:[\\/]", compat.read_text()))
    (output / "compat-relink").write_text("yes\n" if compat_relink else "no\n")
    command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), root,
               "all" if args.all_wrappers else "one", output]
    objects_before = {str(path.relative_to(root)): digest(path)
                      for path in (root / "build").rglob("*.o")}
    products_before = {str(path.relative_to(root)): digest(path)
                       for directory in ("src", "compat")
                       for path in (root / "build" / directory / ".libs").glob("*")
                       if path.is_file() and path.suffix in (".dll", ".a")}
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "command": list(map(str, command)), "before": before, "script_sha256": digest(script),
        "free_gib": require_memory(), "jobs": 1, "selected_wrappers": selected,
        "compat_relink": compat_relink, "objects_before": objects_before, "products_before": products_before})
    row = isolated_observe(root, output, "real-libtool-relink", command, tests, env, 1800)
    objects_after = {str(path.relative_to(root)): digest(path)
                     for path in (root / "build").rglob("*.o")}
    products_after = {name: digest(root / name) if (root / name).is_file() else None for name in products_before}
    after = {name: digest(tests / name) for name in before}
    wrappers = {}
    errors = []
    if args.all_wrappers:
        for path in (root / "build").rglob("lt-*.c"):
            fields, valid = wrapper_paths(path)
            if not valid:
                errors.append(f"Wrapper PATH still contains a converted Windows drive: {path}")
            wrappers[str(path.relative_to(root))] = {"sha256": digest(path), "path_fields": fields}
        if not wrappers:
            errors.append("No genuine generated wrappers were checked")
    log = (output / "real-libtool-relink/command.log").read_text(errors="replace")
    if re.search(r": error:|unknown option to|file format not recognized|: command not found", log):
        errors.append("Build tool reported an error even if its outer command returned zero")
    write_json(output / "result.json", {"process": row, "before": before, "after": after,
        "object_unchanged": before["gtver.o"] == after["gtver.o"],
        "real_target_unchanged": before[".libs/gtver.exe"] == after[".libs/gtver.exe"],
        "all_objects_before": objects_before, "all_objects_after": objects_after,
        "library_products_before": products_before, "library_products_after": products_after,
        "generated_wrapper_path_checks": wrappers, "errors": errors})
    if not row["process"]["passed"] or objects_before != objects_after or errors:
        raise ContractError("Real libtool wrapper regeneration failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "reproduce", "reproduce-mounts", "prepare-build", "build", "relink-wrapper"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--resume-prepare", action="store_true",
                        help="Resume the owned input composition after verifying the complete prepared source")
    parser.add_argument("--run-name", default="build-job")
    parser.add_argument("--phase", choices=("all", "configure", "resume", "check", "install"), default="all")
    parser.add_argument("--all-wrappers", action="store_true")
    args = parser.parse_args()
    args.root = args.root.resolve()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.run_name):
        raise ContractError("A simple owned run directory name is required")
    if not str(args.root).startswith("C:\\ag-gdbm-") or any(p.is_symlink() or p.is_junction() for p in args.root.parents):
        raise ContractError("Explicit fresh owned GDBM root required")
    {"prepare": prepare, "reproduce": reproduce, "reproduce-mounts": reproduce_mounts,
     "prepare-build": prepare_build, "build": build, "relink-wrapper": relink_wrapper}[args.operation](args)


if __name__ == "__main__":
    main()
