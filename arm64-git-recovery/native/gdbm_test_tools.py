"""Restore real private test-tool inputs without rebuilding Tcl or runtime."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile

from db_channel_checks import own_birth
from db_native_checks import environment
from db_package import pe_metadata
from gdbm_recovery import copy_tree, isolated_observe
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json


def compose_host(root):
    output = root / "test-tools"
    before = inventory(root / "bootstrap")
    if before != json.loads((root / "receipts/bootstrap.json").read_text())["files"]:
        raise ContractError("Private bootstrap baseline differs")
    expected = dict(before)
    additions = {}
    for name in ("autoconf-host", "automake-host"):
        source = output / name
        original = json.loads((output / (name + ".json")).read_text())["files"]
        if inventory(source) != original:
            raise ContractError("Extracted host generator package changed")
        for filename, row in original.items():
            if not filename.startswith("usr/"):
                continue
            destination = root / "bootstrap" / filename
            if destination.exists() and digest(destination) != row["sha256"]:
                raise ContractError(f"Host tool addition would overwrite different bytes: {filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / filename, destination)
            additions[filename] = row
            expected[filename] = row
        if inventory(source) != original:
            raise ContractError("Host generator source changed during adoption")
    if inventory(root / "bootstrap") != expected:
        raise ContractError("Private host generator composition differs")
    write_json(output / "host-composition.json", {
        "schema": 1, "role": "Explicit x64/emulated host source generation only",
        "baseline_sha256": digest(root / "receipts/bootstrap.json"),
        "signature_log_sha256": digest(root / "logs/host-tool-signatures03.log"),
        "additions": additions, "files": expected})
    print(f"Composed {len(additions)} genuine host-generator files", flush=True)


def compose_runtime(root):
    output = root / "test-tools"
    baseline = json.loads((output / "tcl.copy.json").read_text())["files"]
    if not (output / "runtime").exists():
        copy_tree(output / "tcl", output / "runtime", baseline)
    else:
        current = inventory(output / "runtime")
        if any(current.get(name) != row for name, row in baseline.items()):
            raise ContractError("The native Tcl baseline changed during runtime composition")
    expected = dict(baseline)
    source = root / "build-runtime" / "usr/bin"
    before = inventory(source)
    for filename, row in before.items():
        name = "usr/bin/" + filename
        destination = output / "runtime" / name
        if name in expected and expected[name] != row:
            raise ContractError(f"Different existing native test runtime file: {name}")
        if destination.exists():
            if digest(destination) != row["sha256"]:
                raise ContractError("Existing native test-tool file differs")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / filename, destination)
        expected[name] = row
    if inventory(source) != before or inventory(output / "runtime") != expected:
        raise ContractError("Native test-tool runtime composition differs")
    for name in ("expect-build", "expect-stage", "dejagnu-build", "dejagnu-stage"):
        (output / name).mkdir()
    write_json(output / "runtime-inputs.json", {
        "schema": 1, "role": "Coherent native907 Tcl/Expect build and test driver",
        "tcl_receipt_sha256": digest(output / "tcl.copy.json"),
        "added_native_bin_source": str(source), "source_files": before, "files": expected})
    print("Coherent native Tcl/Expect runtime input prepared", flush=True)


def build_expect(root, run_name, phase):
    output = root / "test-tools" / run_name
    output.mkdir()
    (output / "native-exits").mkdir()
    runtime = root / "test-tools/runtime"
    expected = json.loads((root / "test-tools/runtime-inputs.json").read_text())["files"]
    if inventory(runtime) != expected:
        raise ContractError("Native test-tool runtime changed before build")
    script = Path(__file__).with_name("build-gdbm-expect.sh").resolve()
    env = environment(root / "compiler", output)
    env["PATH"] = os.pathsep.join(map(str, (runtime / "usr/bin", root / "compiler/bin",
                                root / "bootstrap/usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               root, phase]
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "command": list(map(str, command)), "free_gib": require_memory(), "jobs": 1,
        "source_files": inventory(root / "test-tools/expect-source"), "script_sha256": digest(script)})
    row = isolated_observe(root, output, "expect-native", command, root, env, 1800)
    write_json(output / "result.json", {"process": row, "script_sha256": digest(script),
        "passed": row["process"]["passed"], "phase": phase})
    if not row["process"]["passed"]:
        raise ContractError("Real native Expect restoration failed; evidence retained")


def termios_control(root):
    output = root / "test-tools/termios-control01"
    output.mkdir()
    log = root / "test-tools/expect-build/config.log"
    section = log.read_text().split("checking for struct termios\n", 1)[1]
    section = section.split("checking if TCGETS", 1)[0]
    original = "\n".join(line[2:] for line in section.splitlines() if line.startswith("| ")) + "\n"
    if original.count("  main()") != 1 or original.count("#  include <termios.h>") != 1:
        raise ContractError("The exact retained termios conftest was not recovered")
    (output / "original.c").write_text(original, newline="\n")
    corrected = original.replace("  main()", "  int main(void)", 1).replace(
        "#  include <termios.h>", "#  include <termios.h>\n#  include <stdlib.h>", 1)
    (output / "declarations-corrected.c").write_text(corrected, newline="\n")
    shutil.copy2(Path(__file__).parent / "fixtures/native-termios-header.c", output / "known-good.c")
    posix = "/c/" + root.relative_to(root.anchor).as_posix()
    env = environment(root / "compiler", output)
    runtime = root / "test-tools/runtime/usr/bin"
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (runtime, root / "compiler/bin",
                                          Path(os.environ["SystemRoot"]) / "System32")))
    report = {"schema": 1, "config_log_sha256": digest(log), "cases": {},
              "compiler_sha256": digest(root / "compiler/bin/gcc.exe"),
              "scope": "Exact original failed probe versus declaration-only correction and independent same-invocation header/API control"}
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(),
        "jobs": 1, "free_gib": require_memory(), "scope": report["scope"]})
    for name in ("original", "declarations-corrected", "known-good"):
        base = posix + "/test-tools/termios-control01/" + name
        body = (f'exec "{posix}/compiler/bin/gcc.exe" -o "{base}.exe" '
                f'-O2 -g -fstack-protector-strong -pipe '
                f'-I{posix}/test-tools/zlib/usr/include '
                f'-L{posix}/test-tools/zlib/usr/lib -Wl,--no-insert-timestamp "{base}.c"')
        compiled = isolated_observe(root, output, name + "-compile",
                    [runtime / "bash.exe", "--noprofile", "--norc", "-c", body], output, env)
        report["cases"][name] = {"compile": compiled, "source_sha256": digest(output / (name + ".c"))}
        if name == "original":
            if compiled["process"]["exit"] != 1:
                raise ContractError("Original rejected conftest did not reproduce compiler exit 1")
        else:
            if not compiled["process"]["passed"]:
                raise ContractError("Declaration-correct or known-good termios control did not compile")
            run = isolated_observe(root, output, name + "-run",
                [sys.executable, "-I", root / "observer/native-target-exec.py", output / (name + ".exe")],
                output, env)
            report["cases"][name]["run"] = run
            if not run["process"]["passed"]:
                raise ContractError("Same-invocation termios control failed native execution")
    write_json(output / "result.json", report)
    print("Original compiler exit1; declaration-correct and known-good native controls0", flush=True)


def build_dejagnu(root, run_name):
    output = root / "test-tools" / run_name
    output.mkdir()
    (output / "native-exits").mkdir()
    script = Path(__file__).with_name("build-gdbm-dejagnu.sh").resolve()
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    env["PATH"] = os.pathsep.join(map(str, (root / "host-target-runtime/usr/bin",
                    root / "bootstrap/usr/bin", root / "compiler/bin",
                    Path(os.environ["SystemRoot"]) / "System32")))
    command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), root]
    write_json(output / "launch.json", {"pid": os.getpid(), "created": own_birth(), "jobs": 1,
        "command": list(map(str, command)), "script_sha256": digest(script), "free_gib": require_memory()})
    row = isolated_observe(root, output, "dejagnu-build-install", command, root, env, 1200)
    write_json(output / "result.json", {"process": row,
        "files": inventory(root / "test-tools/dejagnu-stage"),
        "scope": "Genuine DejaGNU scripts restored for original GDBM tests; no DejaGNU C++ self-test or provider admission claim"})
    if not row["process"]["passed"]:
        raise ContractError("Real DejaGNU test-driver restoration failed")


def compose_check_runtime(root):
    source = root / "test-tools/runtime"
    destination = root / "check-runtime"
    destination.mkdir()
    baseline = json.loads((root / "test-tools/runtime-inputs.json").read_text())["files"]
    for name, row in baseline.items():
        if digest(source / name) != row["sha256"]:
            raise ContractError("Frozen native test-runtime input changed")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        if digest(target) != row["sha256"] or digest(source / name) != row["sha256"]:
            raise ContractError("Native check-runtime copy differs")
    (destination / "tmp").mkdir(exist_ok=True)
    additions = {}
    expect = root / "test-tools/expect-stage"
    for original, name in (
        (expect / "usr/bin/expect.exe", "usr/bin/expect.exe"),
        (expect / "usr/lib/expect5.45.4/libexpect5.45.4.dll", "usr/bin/libexpect5.45.4.dll"),
        (expect / "usr/lib/expect5.45.4/pkgIndex.tcl", "usr/lib/expect5.45.4/pkgIndex.tcl"),
    ):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ContractError("Unexpected existing Expect test-driver file")
        sha = digest(original)
        shutil.copy2(original, target)
        if digest(target) != sha or digest(original) != sha:
            raise ContractError("Real Expect driver copy changed")
        additions[name] = {"source": str(original), "sha256_before_relocation": sha}
        if target.suffix in (".exe", ".dll"):
            additions[name]["pe"] = pe_metadata(target.read_bytes())
    index = destination / "usr/lib/expect5.45.4/pkgIndex.tcl"
    text = index.read_text()
    if text.count("$dir") != 1:
        raise ContractError("Unexpected genuine Expect package index")
    index.write_text(text.replace("$dir", "$dir .. .. bin"), newline="\n")
    additions["usr/lib/expect5.45.4/pkgIndex.tcl"]["after_recipe_dll_relocation"] = digest(index)
    dejagnu = root / "test-tools/dejagnu-stage"
    before = inventory(dejagnu)
    for name, row in before.items():
        if not name.startswith(("usr/bin/", "usr/share/dejagnu/")):
            continue
        target = destination / name
        if target.exists():
            raise ContractError(f"Unexpected DejaGNU test-driver collision: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dejagnu / name, target)
        if digest(target) != row["sha256"]:
            raise ContractError("Genuine DejaGNU script copy differs")
        additions[name] = {"source": str(dejagnu / name), **row}
    if inventory(dejagnu) != before:
        raise ContractError("Frozen DejaGNU stage changed during copy")
    write_json(root / "check-runtime.json", {
        "schema": 1, "scope": "Private coherent native Tcl/Expect/DejaGNU test driver only",
        "files": inventory(destination), "additions": additions, "provider_admitted": False,
        "runtime_input_sha256": digest(root / "test-tools/runtime-inputs.json")})
    print("Genuine coherent native Expect/DejaGNU check runtime composed", flush=True)


def extract(archive, expected, destination):
    if digest(archive) != expected:
        raise ContractError(f"Pinned test-tool archive mismatch: {archive}")
    destination.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter="data")
    return {"archive": str(archive), "sha256": expected, "files": inventory(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--compose-host", action="store_true")
    parser.add_argument("--compose-runtime", action="store_true")
    parser.add_argument("--build-expect", action="store_true")
    parser.add_argument("--termios-control", action="store_true")
    parser.add_argument("--build-dejagnu", action="store_true")
    parser.add_argument("--compose-check-runtime", action="store_true")
    parser.add_argument("--run-name", default="expect-job01")
    parser.add_argument("--phase", choices=("all", "resume"), default="all")
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01") or root.is_symlink() or root.is_junction():
        raise ContractError("Only the explicitly owned GDBM root is authorized")
    if args.compose_host:
        compose_host(root)
        return
    if args.compose_runtime:
        compose_runtime(root)
        return
    if args.build_expect:
        if Path(args.run_name).name != args.run_name or args.run_name in (".", ".."):
            raise ContractError("A simple owned Expect run name is required")
        build_expect(root, args.run_name, args.phase)
        return
    if args.termios_control:
        termios_control(root)
        return
    if args.build_dejagnu:
        if Path(args.run_name).name != args.run_name or args.run_name in (".", ".."):
            raise ContractError("An owned DejaGNU run name is required")
        build_dejagnu(root, args.run_name)
        return
    if args.compose_check_runtime:
        compose_check_runtime(root)
        return
    output = root / "test-tools"
    output.mkdir()
    tcl = Path(r"C:\ag-tcl-e138-01\combined-20260911-01")
    if digest(tcl / "inputs.json") != "326ca46e7b50fc710af4821b384b80f8b26a96845f141d1395deeb29cc95fa28":
        raise ContractError("Frozen native Tcl receipt changed")
    tcl_record = copy_tree(tcl / "runtime", output / "tcl",
                          json.loads((tcl / "inputs.json").read_text())["runtime_files"])
    write_json(output / "tcl.copy.json", tcl_record)
    zlib = Path(r"C:\Users\crutkasLocal\.copilot\session-state\f6ea7713-2cec-41d5-b3f9-b4373e60fa33\files\resume-20260907\zlib-msys-01")
    receipt = zlib.with_name("zlib-msys-01.result.json")
    if digest(receipt) != "e206df14f9a4aa12dca6c88e13427e03ca2d0233100f243426c7cd9b5bfe4960":
        raise ContractError("Qualified zlib development receipt changed")
    zlib_record = copy_tree(zlib / "stage", output / "zlib",
                           json.loads(receipt.read_text())["files"])
    write_json(output / "zlib.copy.json", zlib_record)
    for name, filename, sha in (
        ("expect-source", "expect5.45.4-blfs.tar.gz", "49a7da83b0bdd9f46d04a04deec19c7767bb9a323e40c4781f89caf760b92c34"),
        ("dejagnu-source", "dejagnu-1.6.3.tar.gz", "87daefacd7958b4a69f88c6856dbd1634261963c414079d0c371f589cd66a2e3"),
        ("autoconf-host", "autoconf2.72-2.72-3-any.pkg.tar.zst", "e11d605053e8f059e503d163c2a87724ef15e50463fccd6e7802ffc7129d7b8e"),
        ("automake-host", "automake1.17-1.17-1-any.pkg.tar.zst", "bb069dbb6f580c2346d2f6d74268b5e12e625f7ba57299426f9cd6c0fa714191"),
    ):
        record = extract(root / "downloads" / filename, sha, output / name)
        write_json(output / (name + ".json"), record)
        print(f"Restored {name}: {len(record['files'])} files", flush=True)
    write_json(output / "inputs.json", {
        "schema": 1, "scope": "Private real test-tool restoration; not a delivered provider",
        "tcl": str(output / "tcl.copy.json"), "zlib": str(output / "zlib.copy.json"),
        "no_Tcl_runtime_or_compiler_rebuild": True})


if __name__ == "__main__":
    main()
