#!/usr/bin/env python3
"""Assemble the generated ARM64 signal object with a bounded native tool."""
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
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("generated", "output", "assembler", "nm", "runner"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--offsets-sha256", required=True)
    args = parser.parse_args()
    if identity(args.runner)["sha256"] != args.runner_sha256:
        raise ValueError("Bounded process runner differs")
    generated = args.generated.resolve(strict=True)
    if identity(generated / "tlsoffsets")["sha256"] != args.offsets_sha256:
        raise ValueError("Wrong TLS offsets before assembly")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    inputs = [identity(path) for path in (args.assembler, args.nm, args.runner)]
    for name in ("sigfe.s", "runtime.def", "tlsoffsets"):
        inputs.append(identity(generated / name))
        shutil.copy2(generated / name, out / name)
    bounded = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")}
    env["PATH"] = str(args.assembler.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    commands = [
        [str(args.assembler), "-I", str(out), str(out / "sigfe.s"), "-o", str(out / "sigfe.o")],
        [str(args.nm), "--extern-only", "--defined-only", str(out / "sigfe.o")],
    ]
    report = {"schema": 1, "status": "failed", "inputs": inputs, "runs": [], "make_invoked": False}
    try:
        for name, argv in zip(("assemble", "symbols"), commands):
            log = out / (name + ".log")
            machines = []
            with log.open("xb") as stream:
                process = bounded(argv, cwd=out, env=env, log=stream, timeout=60,
                                  on_started=lambda pid: machines.append(native(pid, Path(argv[0]))))
            report["runs"].append({"argv": argv, "process": process, "native": machines, "log": identity(log)})
            if not process["passed"]:
                raise ValueError(f"Native {name} or child drain failed")
        raw = (out / "sigfe.o").read_bytes()
        if len(raw) < 20 or struct.unpack_from("<H", raw)[0] != 0xaa64:
            raise ValueError("Signal object is not ARM64 COFF")
        symbols = {line.split()[-1] for line in (out / "symbols.log").read_text().splitlines() if line.split()}
        needed = set(re.findall(r"=\s*(_sigfe\w+)\s*$", (out / "runtime.def").read_text(), re.M))
        needed |= {"_sigbe", "sigdelayed", "_sigdelayed_end", "_sigfe_malloc", "sigsetjmp", "siglongjmp"}
        missing = sorted(needed - symbols)
        if missing:
            raise ValueError(f"Signal object does not define required exports: {missing}")
        for item in inputs:
            if identity(Path(item["path"])) != item:
                raise ValueError("Input changed during native assembly")
        report.update(status="native-arm64-signal-object-qualified-for-link",
                      object=identity(out / "sigfe.o"), defined_symbols=sorted(symbols),
                      core_providers=sorted(needed & {"_sigbe", "sigdelayed", "_sigdelayed_end",
                                                     "_sigfe_malloc", "sigsetjmp", "siglongjmp"}),
                      limits="Native assembler execution and raw COFF/export closure only. Not linked-runtime signal semantics.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
