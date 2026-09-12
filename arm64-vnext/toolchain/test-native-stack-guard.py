#!/usr/bin/env python3
"""Stage and qualify an isolated C-frontend delta; never alter its f54 base."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct

RECIPE = Path(__file__).resolve().parent


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-receipt", required=True, type=Path)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--cc1", required=True, type=Path)
    parser.add_argument("--fido-build", required=True, type=Path,
                        help="Frozen FIDO build containing compile_commands.json and original objects")
    parser.add_argument("--cmocka-build", required=True, type=Path,
                        help="Frozen CMocka build containing compile_commands.json and original objects")
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--inspector", required=True, type=Path,
                        help="Hash-bound raw PE/COFF inspection module saved with the diagnosis")
    parser.add_argument("--inspector-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows qualification is required")
    for path, sha in ((args.base_receipt, args.base_sha256),
                      (args.runner, args.runner_sha256), (args.inspector, args.inspector_sha256)):
        if identity(path)["sha256"] != sha:
            parser.error(f"Input identity differs: {path}")
    base = json.loads(args.base_receipt.read_text(encoding="utf-8-sig"))
    if (base["status"] != "byte-identical-relocated-input-not-new-qualification"
            or base["source_target"]["Profile"] != "MSYS"):
        parser.error("Expected the frozen MSYS C compiler-copy receipt")
    old = Path(base["prefix"]).resolve(strict=True)
    if args.output.resolve().is_relative_to(old):
        parser.error("Cannot stage within the frozen base")
    frontend = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe"
    if identity(args.cc1)["sha256"] == base["files"][frontend]["sha256"]:
        parser.error("Candidate is identical to the failing frontend")

    def verify_base():
        for rel, spec in base["files"].items():
            path = old.joinpath(*rel.split("/"))
            if identity(path)["sha256"] != spec["sha256"] or path.stat().st_size != spec["size"]:
                raise ValueError(f"Frozen compiler input changed: {rel}")

    verify_base()
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    tc = out / "tc"
    shutil.copytree(old, tc)
    shutil.copy2(args.cc1, tc / frontend)
    probes = out / "probes"
    probes.mkdir()
    shutil.copy2(args.runner, out / "bounded_process.py")
    shutil.copy2(args.inspector, out / "inspect-pseudo-relocs.py")
    shutil.copy2(args.base_receipt, out / "base-receipt.json")
    run_bounded = runpy.run_path(str(out / "bounded_process.py"))["run"]
    inspector = runpy.run_path(str(out / "inspect-pseudo-relocs.py"))
    inspect_pe = inspector["inspect"]
    coff = inspector["coff"]
    native_process = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    cc = tc / "bin" / "gcc.exe"
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT")}
    env["PATH"] = str(tc / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    report = {"status": "failed", "base_receipt": identity(args.base_receipt),
              "prefix": str(tc), "candidate_cc1": identity(args.cc1),
              "target": base["source_target"], "changed_files": [frontend], "runs": []}

    def run(name, command, *, execute=False, expect=0):
        log = out / (name + ".log.bin")
        observed = []
        with log.open("wb") as stream:
            result = run_bounded(list(map(str, command)), cwd=probes, env=env,
                                 log=stream, timeout=20 if execute else 180,
                                 on_started=(lambda pid: observed.append(native_process(pid, Path(command[0]))))
                                 if execute else None)
        report["runs"].append({"name": name, "command": list(map(str, command)),
                               "process": result, "log": identity(log), "observed": observed,
                               "expected_exit": expect,
                               "nonzero_failure_control": expect is None})
        if result["timed_out"] or result["active_at_boundary"] or result["remaining_process_ids"]:
            raise ValueError(f"Timeout or undrained job: {name}")
        if expect is not None and result["exit"] != expect:
            raise ValueError(f"Unexpected exit: {name}: {result['exit']}")
        return result, log.read_bytes()

    def object_guard(name, path, allow_direct=False):
        data = path.read_bytes()
        sections, symbols, indices = coff(data, 0)
        records = []
        for section in sections:
            for i in range(section["nrelocs"]):
                offset, index, kind = struct.unpack_from("<IIH", data, section["relocations"] + i * 10)
                if indices[index]["name"] == "__stack_chk_guard":
                    records.append({"section": section["name"], "offset": offset, "kind": kind})
        if allow_direct:
            if not any(record["kind"] == 4 for record in records):
                raise ValueError("Old object did not reproduce direct PAGEBASE_REL21")
        elif not records or any(record["kind"] != 14 or ".refptr." not in record["section"] for record in records):
            raise ValueError(f"Guard references are not exclusively full-width local cells: {name}: {records}")
        report.setdefault("object_guards", {})[name] = {
            "object": identity(path), "guard_relocations": records}

    try:
        # Repeat exact original consumer compile commands, changing only the
        # compiler prefix and output; no language/optimization/defense changes.
        fixtures = [
            ("fido-aes", args.fido_build / "compile_commands.json",
             "fido2_shared.dir/aes256.c.o"),
            ("fido-dev", args.fido_build / "compile_commands.json",
             "regress_dev.dir/dev.c.o"),
            ("cmocka", args.cmocka_build / "compile_commands.json",
             "cmocka.dir/cmocka.c.o"),
        ]
        split = runpy.run_path(str(RECIPE / "test-fido-windows-import-link.py"))["split_command"]
        for name, database, suffix in fixtures:
            matches = [entry for entry in json.loads(database.read_text())
                       if entry["output"].replace("\\", "/").endswith(suffix)]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous frozen compile command: {name}")
            entry = matches[0]
            command = split(entry["command"])
            if Path(command[0]).resolve() != old / "bin" / "gcc.exe":
                raise ValueError("Original consumer compiler differs from base")
            source_before = identity(entry["file"])
            object_guard(name + "-old", Path(entry["output"]), allow_direct=True)
            target = probes / (name + ".o")
            command[0] = str(cc)
            command[command.index("-o") + 1] = str(target)
            run(name + "-compile", command)
            object_guard(name, target)
            if identity(entry["file"]) != source_before:
                raise ValueError("Frozen consumer source changed")
            report.setdefault("original_compiles", {})[name] = {
                "database": identity(database), "original": entry, "source": source_before}
        source = probes / "stack-guard-pe.c"
        shutil.copy2(RECIPE / "probes" / "stack-guard-pe.c", source)
        old_exe = probes / "old-guard.exe"
        # Use FIDO's protection profile for this new probe. Adding CMocka's
        # stack-clash flag to global -Werror conflicts with the MSYS driver's
        # default stack-check option; the exact CMocka command above is separate.
        flags = ["-O3", "-std=c99", "-Wall", "-Wextra", "-Werror", "-fstack-protector-all", source]
        run("old-probe-link", [old / "bin" / "gcc.exe", *flags, "-o", old_exe])
        old_table = inspect_pe(old_exe)
        if not any(e["bits"] == 21 and e["imported"]["symbol"] == "__stack_chk_guard"
                   for e in old_table["entries"]):
            raise ValueError("Old linked probe did not reproduce pseudo21")
        exe = probes / "guard.exe"
        run("probe-link", [cc, *flags, "-fdump-rtl-expand", "-o", exe])
        new_table = inspect_pe(exe)
        if any(e["bits"] in (12, 21) for e in new_table["entries"]):
            raise ValueError("Fixed probe still contains instruction pseudo-relocations")
        if not any(e["bits"] == 64 and e["imported"]["symbol"] == "__stack_chk_guard"
                   for e in new_table["entries"]):
            raise ValueError("Fixed probe did not use the ordinary guard64 pseudo-reloc")
        report["pseudo_relocations"] = {"old": old_table, "new": new_table}
        dump = list(probes.glob("*.expand"))
        if len(dump) != 1:
            raise ValueError("Expected one RTL expand dump")
        rtl = dump[0].read_text()
        salts = set(re.findall(
            r'\(const_int ([01]) \[[^\]]*\]\)\s*\]\s*UNSPEC_SALT_ADDR', rtl))
        if salts != {"0", "1"}:
            raise ValueError("The distinct SET/TEST salts were lost")
        report["rtl"] = identity(dump[0])
        _, stdout = run("native-protected", [exe], execute=True)
        if stdout.replace(b"\r\n", b"\n") != b"native-msys-protected-far-guard-ok\n":
            raise ValueError("Unexpected protected native consumer output")
        result, stdout = run("native-corrupt-guard", [exe, "--corrupt"], execute=True, expect=None)
        if result["exit"] == 0 or b"ERROR-guard-corruption-not-detected" in stdout or \
                b"corrupting-own-process-guard" not in stdout or b"stack smashing" not in stdout.lower():
            raise ValueError("Actual runtime stack-canary failure was not observed")
        verify_base()
        files = {p.relative_to(tc).as_posix(): {"sha256": identity(p)["sha256"], "size": p.stat().st_size}
                 for p in tc.rglob("*") if p.is_file()}
        if set(files) != set(base["files"]):
            raise ValueError("Compiler candidate file set differs")
        changed = [name for name, spec in files.items() if spec != base["files"][name]]
        if changed != [frontend]:
            raise ValueError(f"Unexpected compiler delta: {changed}")
        report.update(status="qualified-native-msys-stack-guard-c-compiler-delta",
                      files=files, baseline_unchanged=True, full_cpp_qualified=False,
                      scope="Only cc1 replaced; exact protected C codegen and native guard controls. "
                            "Retained drivers, C++ frontend, runtime, headers and libraries keep prior qualification.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Qualified C-only guard delta: {out / 'result.json'}")


if __name__ == "__main__":
    main()
