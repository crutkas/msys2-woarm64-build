"""Preserve the runtime-owned qualified cygpath payload for a future coherent native root."""

import argparse
import json
from pathlib import Path
import shutil

from compiler_tools import require_msys_ucontext_receipt
from sources import ContractError, digest, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("handoff", "compiler-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.output.exists() or digest(args.handoff) != args.sha256:
        raise ContractError("A fresh utility copy and exact producer handoff hash are required")
    record = json.loads(args.handoff.read_text())
    compiler = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(compiler)
    if (record.get("status") != "native-msys-cygpath-utility-qualified" or
            record.get("target") != "aarch64-pc-cygwin/MSYS" or
            record["results"]["cases"] != 32 or record["results"]["passed"] != 32 or
            record["results"]["active_native_processes"] != 0 or
            record["results"]["no_fake_shell_or_launcher"] is not True):
        raise ContractError("Unexpected native cygpath qualification")
    if record["paired_runtime"]["sha256"] != compiler["files"]["bin/msys-2.0.dll"]["sha256"]:
        raise ContractError("Cygpath does not match the intended coherent runtime")
    for name in ("payload", "license", "paired_runtime", "runtime_receipt", "sdk_receipt",
                 "native_summary", "native_cases", "native_process", "native_loaded_modules"):
        proof = record[name]
        if digest(proof["path"]) != proof["sha256"]:
            raise ContractError(f"Qualified cygpath evidence changed: {name}")
    source = Path(record["payload_root"])
    files = inventory(source)
    expected = {
        "usr/bin/cygpath.exe": record["payload"]["sha256"],
        "usr/share/licenses/cygpath/CYGWIN_LICENSE": record["license"]["sha256"],
    }
    if {name: row["sha256"] for name, row in files.items()} != expected:
        raise ContractError("Cygpath payload includes missing, extra or changed files")
    shutil.copytree(source, args.output)
    if inventory(args.output) != files or inventory(source) != files:
        raise ContractError("Cygpath input changed during copy")
    report = {"schema": 1, "status": "byte-identical-qualified-cygpath-input",
              "source_handoff_sha256": args.sha256,
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "required_runtime_sha256": record["paired_runtime"]["sha256"], "files": files,
              "scope": "Only cygpath and license; integrate only into a freshly rebuilt coherent MSYS root. Not a GitGUI execution claim."}
    args.output.with_name(args.output.name + ".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Qualified native cygpath payload copied; coherent shell/root integration remains required")


if __name__ == "__main__":
    main()
