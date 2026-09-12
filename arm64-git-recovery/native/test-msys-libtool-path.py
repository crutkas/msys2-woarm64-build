"""Discriminate an uninstalled libtool DLL-path failure without changing wrappers or test bodies."""

import argparse
import json
import os
from pathlib import Path

from bounded_process import run
from compiler_tools import require_msys_jump_receipt
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "compiler-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh DLL-path control directory is required")
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_jump_receipt(producer)
    if Path(producer["prefix"]).resolve() != args.prefix.resolve():
        raise ContractError("Compiler receipt identifies a different prefix")
    before = inventory(args.build)
    args.output.mkdir(parents=True)
    wrapper = args.build / "test/crypt-badargs.exe"
    dll = args.build / ".libs/msys-crypt-2.dll"
    report = {"passed": False, "wrapper_sha256": digest(wrapper), "dll_sha256": digest(dll),
              "compiler_receipt_sha256": digest(args.compiler_receipt), "cases": [],
              "scope": "Same upstream C wrapper and test body; only explicit uninstalled DLL search directory differs"}
    try:
        for name, dll_path in (("missing-uninstalled-directory", False), ("explicit-uninstalled-directory", True)):
            env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
            paths = ([dll.parent] if dll_path else []) + [args.prefix / "bin",
                                                         Path(os.environ["SystemRoot"]) / "System32"]
            env.update({"PATH": os.pathsep.join(map(str, paths)), "HOME": str(args.output),
                        "TMP": str(args.output), "TEMP": str(args.output)})
            with (args.output / f"{name}.log").open("xb") as log:
                result = run([wrapper, "--lt-debug"], cwd=args.build, env=env, log=log, timeout=30)
            expected = 0 if dll_path else 127
            report["cases"].append({"name": name, "process": result, "expected_exit": expected,
                                     "dll_search_directories": list(map(str, paths))})
            if result["timed_out"] or result["active_at_boundary"] or result["exit"] != expected:
                raise ContractError("Uninstalled DLL-path discriminator did not match")
        if inventory(args.build) != before:
            raise ContractError("Original library/test artifacts changed")
        verify_tree(args.prefix, args.compiler_receipt)
        report["passed"] = True
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Unchanged native crypt-badargs succeeds with explicit uninstalled DLL closure")


if __name__ == "__main__":
    main()
