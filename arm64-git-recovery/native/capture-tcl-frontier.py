"""Export a bounded preprocessor corpus from the real remaining Tcl make targets, without compiling or changing flags."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from bounded_process import run
from sources import ContractError, digest, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "bootstrap", "zlib", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Use a new corpus directory")
    before = inventory(args.build)
    compiler = args.prefix / "bin/gcc.exe"
    compiler_hash = digest(compiler)
    args.output.mkdir(parents=True)
    (args.output / "temp").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.bootstrap / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    env["TMP"] = env["TEMP"] = str(args.output / "temp")
    script = Path(__file__).with_suffix(".sh")
    dry_run = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.build, args.prefix, args.zlib]
    with (args.output / "make-dry-run.log").open("xb") as log:
        plan = run(dry_run, cwd=args.output, env=env, log=log, timeout=300)
    (args.output / "make-dry-run.result.json").write_text(json.dumps(plan, indent=2) + "\n")
    if not plan["passed"]:
        raise ContractError("The remaining Tcl make plan could not be obtained")
    records = []
    for line in (args.output / "make-dry-run.log").read_text().splitlines():
        if not line.startswith("gcc -c ") or len(records) == 20:
            continue
        argv = shlex.split(line)
        sources = [index for index, arg in enumerate(argv) if arg.endswith(".c")]
        if len(sources) != 1 or argv.count("-o") != 1:
            raise ContractError("Unexpected Tcl compiler command in make plan")
        source = Path(argv[sources[0]])
        if not source.resolve().is_relative_to((args.build / "source").resolve()):
            raise ContractError("Tcl compile input is outside the preserved source")
        output_index = argv.index("-o") + 1
        stem = Path(argv[output_index]).stem
        destination = args.output / f"{len(records):02d}-{stem}.i"
        original = [str(compiler), *argv[1:]]
        command = list(original)
        command[command.index("-c")] = "-E"
        command[output_index] = str(destination)
        result = subprocess.run(command, cwd=args.build / "build", env=env, capture_output=True, timeout=90)
        (args.output / f"{stem}.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise ContractError(f"Preprocessing failed: {source.name}; no target answers were substituted")
        replay = list(original)
        replay[sources[0]] = str(destination)
        replay[output_index] = str(args.output / f"{stem}.o")
        replay[1:1] = ["-x", "cpp-output"]
        records.append({"source": str(source), "source_sha256": digest(source), "input": str(destination),
                        "input_sha256": digest(destination), "original_compile": original, "replay_compile": replay})
    if not records or inventory(args.build) != before or digest(compiler) != compiler_hash:
        raise ContractError("Empty corpus or preserved build/compiler changed")
    report = {"schema": 1, "status": "remaining-Tcl-preprocessor-corpus-only", "cases": records,
              "compiler": str(compiler), "compiler_sha256": compiler_hash, "original_build_unchanged": True,
              "scope": "Up to20 actual remaining binaries/tcltest compile rules; only -c->-E for collection; no optimization changes or compile-pass claim"}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Exported {len(records)} unchanged-flag Tcl translation units")


if __name__ == "__main__":
    main()
