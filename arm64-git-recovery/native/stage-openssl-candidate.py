"""Install already-built OpenSSL for dependent builds without asserting full test acceptance."""

import argparse
import json
import os
from pathlib import Path
import re

from bounded_process import run
from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "msys", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--library-directory", choices=("lib", "lib64", "lib-arm64"), required=True)
    parser.add_argument("--existing-install-receipt", type=Path)
    args = parser.parse_args()
    stage = args.build.parent / "stage"
    configured = re.search(r"^LIBDIR=(.+)$", (args.build / "Makefile").read_text(), re.MULTILINE)
    if not configured or configured[1].strip() != args.library_directory:
        raise ContractError("Explicit library directory must match the actual OpenSSL configuration")
    if args.report.exists() or (not args.existing_install_receipt and any(stage.iterdir())):
        raise ContractError("Use a new report and the original empty configured stage")
    before = {str(path): digest(path) for path in args.build.rglob("*")
              if path.is_file() and path.suffix.lower() in (".dll", ".exe", ".a")}
    if not before or not (args.build / "libcrypto-3.dll").is_file():
        raise ContractError("Expected the already-built native shared OpenSSL")
    recipe = Path(__file__).with_suffix(".sh").resolve()
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.msys / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    command = [args.msys / "usr/bin/bash.exe", "--noprofile", "--norc", recipe.as_posix(),
               args.build, args.prefix]
    report = {"status": "failed", "scope": "Dependent-build candidate, not full OpenSSL or Git admission",
              "pending": ["Full upstream suite closure", "Native TLS acceptance", "Relocation and full Git integration"],
              "inputs": before, "support": support, "recipe_sha256": digest(recipe),
              "library_directory": args.library_directory,
              "command": list(map(str, command))}
    try:
        if args.existing_install_receipt:
            previous = json.loads(args.existing_install_receipt.read_text())
            if (previous["inputs"] != before or previous["files"] != inventory(stage)
                    or previous["command"] != list(map(str, command))):
                raise ContractError("Previously installed source, payload or command differs")
            report["process"] = previous["process"]
            report["existing_install_receipt_sha256"] = digest(args.existing_install_receipt)
        else:
            with args.report.with_suffix(".log").open("xb") as log:
                report["process"] = run(command, cwd=args.build, env=env, log=log, timeout=900)
        if not report["process"]["passed"]:
            raise ContractError("OpenSSL supported installation failed")
        verify_support(support, compiler, args.prefix, env)
        if any(digest(path) != value for path, value in before.items()):
            raise ContractError("Installation rebuilt or changed a previously tested binary")
        report["files"] = inventory(stage)
        for rel in ("bin/openssl.exe", "bin/libcrypto-3.dll", "bin/libssl-3.dll",
                    "include/openssl/ssl.h", f"{args.library_directory}/libcrypto.dll.a",
                    f"{args.library_directory}/libssl.dll.a"):
            if rel not in report["files"]:
                raise ContractError(f"Required OpenSSL development payload missing: {rel}")
        report["status"] = "installed-dependent-build-candidate-not-fully-accepted"
    finally:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
