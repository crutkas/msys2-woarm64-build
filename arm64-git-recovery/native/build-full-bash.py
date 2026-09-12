"""Build the full pinned native Bash profile; upstream/PTY acceptance is a separate explicit phase."""

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from bash_chain_inputs import ROOT, HERE, PREPARED, fresh
from readline_chain_inputs import SEALS, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

nls = importlib.import_module("build-bash-nls")


def main(args):
    output = ROOT / args.output
    fresh(output)
    source = ROOT / "sources/bash/source"
    manifest = source.with_name("source.prepare.json")
    sdk = ROOT / args.sdk
    sdk_manifest = sdk.parent / "stage.inventory.json"
    sealed(manifest, PREPARED["bash"][1])
    verify_tree(source, manifest)
    verify_tree(sdk, sdk_manifest)
    sdk_record = json.loads(sdk_manifest.read_text())
    if (sdk_record["compiler_receipt_sha256"] != SEALS["compiler"]
            or sdk_record["classification"] != "final-coherent-native-Bash-development-view"):
        raise ContractError("Full Bash requires the final coherent native SDK, not a temporary cycle view")
    profiles = {row.get("profile"): row for row in sdk_record["components"] if row.get("profile")}
    if any(profiles.get(profile, {}).get("nls_enabled") is not True for profile in ("iconv-full", "gettext-runtime")):
        raise ContractError("Full Bash cannot inherit a bootstrap iconv/NLS omission")
    for required in ("usr/include/readline/readline.h", "usr/lib/libreadline.a", "usr/lib/libhistory.a",
                     "usr/include/libintl.h", "usr/lib/libintl.a", "usr/lib/libiconv.a", "usr/lib/libncurses.a"):
        if required not in sdk_record["files"]:
            raise ContractError(f"Missing actual full Bash dependency: {required}")
    sealed(nls.terminal.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(nls.terminal.COMPILER, nls.terminal.COMPILER_RECEIPT)
    sealed(nls.BOOTSTRAP_RECEIPT, nls.BOOTSTRAP_RECEIPT_SHA)
    verify_tree(nls.BOOTSTRAP, nls.BOOTSTRAP_RECEIPT)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    script = HERE / "build-full-bash.sh"
    if b"\r" in script.read_bytes():
        raise ContractError("Native Bash shell recipe must use LF")
    for path in (script, HERE / "build-full-bash.py", ROOT / "sources/bash/PKGBUILD"):
        shutil.copyfile(path, output / "recipes" / path.name)
    command = [nls.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               source, nls.terminal.COMPILER, sdk, output, str(args.jobs)]
    report = {"schema": 1, "status": "launched", "package": "bash", "version": "5.3.015-2",
              "pid": os.getpid(), "creation_filetime": nls.terminal.current_birth(),
              "command": list(map(str, command)), "jobs": args.jobs, "minimum_free_gib": require_memory(),
              "source_manifest_sha256": digest(manifest), "compiler_receipt_sha256": SEALS["compiler"],
              "runtime_sha256": nls.terminal.RUNTIME_SHA, "sdk_manifest_sha256": digest(sdk_manifest),
              "bootstrap_manifest_sha256": nls.BOOTSTRAP_RECEIPT_SHA,
              "required_features": ["installed readline/history", "NLS", "multibyte", "job-control", "signals",
                                    "static-link", "WORD_EXPRESSION", "libbash/devel", "full install/manual tails"],
              "upstream_checks_completed": False, "package_admission": False}
    write_json(output / "launch.json", report)
    print(json.dumps(report), flush=True)
    try:
        with nls.cpu_budget(args.jobs) as budget:
            report["cpu_budget"] = budget
            report["process"] = nls.run_observed(command, cwd=ROOT, env=nls.environment(output, args.jobs),
                                                 log_path=output / "observed.log", result_path=output / "native-job.json",
                                                 relay_records=output / "native-exits", timeout=14400,
                                                 driver_prefix=nls.terminal.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Full native Bash build/install failed")
        files = inventory(output / "stage")
        for name in ("usr/bin/bash.exe", "usr/bin/sh.exe", "usr/lib/libbash.dll.a",
                     "usr/include/bash/shell.h", "usr/share/man/man1/bash.1"):
            if name not in files:
                raise ContractError(f"Full native Bash package output missing: {name}")
        if files["usr/bin/bash.exe"] != files["usr/bin/sh.exe"]:
            raise ContractError("sh must be the actual byte-identical native Bash executable")
        report["status"] = "full-native-Bash-built-installed-upstream-and-PTY-proof-pending"
        write_json(output / "stage.inventory.json", {"schema": 1, "package": "bash", "version": "5.3.015-2",
                   "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": nls.terminal.RUNTIME_SHA,
                   "status": report["status"], "files": files})
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(source, manifest)
        verify_tree(sdk, sdk_manifest)
        verify_tree(nls.terminal.COMPILER, nls.terminal.COMPILER_RECEIPT)
        verify_tree(nls.BOOTSTRAP, nls.BOOTSTRAP_RECEIPT)
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "stage_manifest_sha256": digest(output / "stage.inventory.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--jobs", required=True, type=int, choices=(1, 2))
    main(parser.parse_args())
