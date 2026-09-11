#!/usr/bin/env python3
"""Generate signal assembly in a new directory without invoking runtime make."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def validate_offsets(text):
    constants = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"\.equ\s+(_cygtls\.[A-Za-z_]\w*)\s*,\s*(-?\d+)", line)
        if not match:
            raise ValueError(f"Malformed TLS offset at line {number}")
        name, value = match.groups()
        if name in constants:
            raise ValueError(f"Duplicate TLS offset: {name}")
        constants[name] = int(value)
    required = ("start_offset", "initialized", "stacklock", "stackptr", "stack",
                "incyg", "current_sig", "saved_errno", "errno_addr")
    if not all("_cygtls." + name in constants for name in required):
        raise ValueError("TLS offsets do not contain the signal ABI fields")
    start = constants["_cygtls.start_offset"]
    if start >= 0 or start % 16:
        raise ValueError("TLS start offset must be negative and 16-byte aligned")
    for name, value in constants.items():
        if name == "_cygtls.start_offset":
            continue
        if name.endswith("_p"):
            if name[:-2] not in constants:
                raise ValueError(f"TLS positive offset has no field: {name}")
            continue
        if not start <= value < 0 or constants.get(name + "_p") != value - start:
            raise ValueError(f"Inconsistent TLS relative/positive offset pair: {name}")
    for field, alignment in (("initialized", 4), ("stacklock", 4), ("incyg", 4),
                             ("current_sig", 4), ("saved_errno", 4), ("stackptr", 8),
                             ("stack", 8), ("errno_addr", 8), ("context", 16)):
        name = "_cygtls." + field
        if name in constants and constants[name] % alignment:
            raise ValueError(f"Misaligned TLS field: {name}")
    stack_size = constants["_cygtls.initialized"] - constants["_cygtls.stack"]
    if constants["_cygtls.stackptr"] + 8 != constants["_cygtls.stack"] or stack_size < 16 or stack_size % 8:
        raise ValueError("Invalid TLS signal-stack layout")
    return constants


def validate_assembly(text, exports):
    labels = re.findall(r"^([A-Za-z_.$][\w.$]*):", text, re.M)
    if len(labels) != len(set(labels)):
        raise ValueError("Duplicate generated assembly label")
    needed = set(re.findall(r"=\s*(_sigfe\w+)\s*$", exports, re.M))
    core = {"_sigfe", "_sigfe_maybe", "_sigbe", "sigdelayed", "_sigdelayed_end",
            "sigsetjmp", "siglongjmp", "setjmp", "longjmp", "stabilize_sig_stack"}
    missing = sorted((needed | core) - set(labels))
    if not needed or missing:
        raise ValueError(f"Generated export/trampoline symbols missing: {missing}")
    public = set(re.findall(r"^\s*\.(?:global|globl)\s+([A-Za-z_.$][\w.$]*)\s*$", text, re.M))
    missing_public = sorted((needed | {"_sigbe", "sigdelayed", "_sigdelayed_end",
                                      "sigsetjmp", "siglongjmp", "setjmp", "longjmp"}) - public)
    if missing_public:
        raise ValueError(f"Generated symbols are not externally visible: {missing_public}")
    return needed, set(labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--offsets", type=Path, required=True)
    parser.add_argument("--offsets-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--perl", type=Path, required=True)
    parser.add_argument("--cpu", choices=("aarch64", "x86_64"), default="aarch64")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    generator = source / "winsup/cygwin/scripts/gendef"
    exports = source / "winsup/cygwin/cygwin.din"
    offsets = args.offsets.resolve(strict=True)
    if digest(offsets) != args.offsets_sha256:
        raise ValueError("TLS offsets differ from the explicitly selected source/build cohort")
    constants = validate_offsets(offsets.read_text())
    before = {str(p): identity(p) for p in (generator, exports, offsets, args.perl)}
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    preserved = out / "inputs"
    preserved.mkdir()
    for path, name in ((generator, "gendef"), (exports, "cygwin.din"), (offsets, "tlsoffsets.good")):
        shutil.copy2(path, preserved / name)
    shutil.copy2(offsets, out / "tlsoffsets")
    report = {"schema": 1, "status": "failed", "cpu": args.cpu, "inputs": before,
              "tls_fields": constants, "commands": [], "make_invoked": False}
    command = [str(args.perl.resolve(strict=True)), str(preserved / "gendef"),
               "--cpu=" + args.cpu, "--output-def=" + str(out / "runtime.def"),
               str(preserved / "cygwin.din")]
    try:
        with (out / "generator.stdout").open("xb") as stdout, (out / "generator.stderr").open("xb") as stderr:
            result = subprocess.run(command, cwd=out, stdout=stdout, stderr=stderr, timeout=60)
        report["commands"].append({"argv": command, "exit": result.returncode})
        if result.returncode:
            raise ValueError("Signal generator failed; raw logs retained")
        assembly = out / "sigfe.s"
        if not assembly.is_file() or not assembly.stat().st_size:
            raise ValueError("Signal generator produced no assembly")
        needed, labels = validate_assembly(assembly.read_text(), (out / "runtime.def").read_text())
        for path, expected in before.items():
            if identity(Path(path)) != expected:
                raise ValueError(f"Source input changed during generation: {path}")
        if digest(out / "tlsoffsets") != args.offsets_sha256:
            raise ValueError("Working TLS offsets changed during generation")
        report.update(status="signal-source-generation-complete-not-runtime-qualified",
                      export_trampolines=len(needed), generated_labels=len(labels),
                      outputs={p.name: identity(p) for p in (assembly, out / "runtime.def", out / "tlsoffsets")},
                      limits="Generation and export coverage only. Assembly, linked runtime and native signal semantics require separate evidence.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
