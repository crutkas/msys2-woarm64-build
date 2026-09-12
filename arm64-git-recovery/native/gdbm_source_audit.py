"""Replay pinned source patches independently of the configured build trees."""

import argparse
import json
from pathlib import Path
import subprocess
import tarfile

from native_job_runner import noninteractive_error_mode
from sources import ContractError, digest, inventory
from ssh_bootstrap import write_json


def apply(root, source, patch, strip, log):
    with patch.open("rb") as stdin, log.open("xb") as output, noninteractive_error_mode():
        result = subprocess.run(
            [str(root / "bootstrap/usr/bin/patch.exe"), "--batch", "-p" + str(strip)],
            cwd=source, stdin=stdin, stdout=output, stderr=subprocess.STDOUT, timeout=60,
        )
    if result.returncode:
        raise ContractError(f"Pinned source patch replay failed: {patch}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-name", default="source-audit01")
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Explicit owned source-audit output required")
    if Path(args.run_name).name != args.run_name or args.run_name in (".", ".."):
        raise ContractError("An owned source-audit directory name is required")
    output = root / args.run_name
    output.mkdir()
    drivers = Path(__file__).parent
    report = {"schema": 1, "packages": {}}
    for name, archive, sha, subdir, working, patches in (
        ("gdbm", "gdbm-1.26.tar.gz", "6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e",
         "gdbm-1.26", root / "source",
         [(root / "downloads/1.10-no-undefined.patch", 2),
          (root / "downloads/0001-missing-include.patch", 1),
          (drivers / "patches/gdbm-1.26-preserved-include-dedup.patch", 1)]),
        ("expect", "expect5.45.4-blfs.tar.gz", "49a7da83b0bdd9f46d04a04deec19c7767bb9a323e40c4781f89caf760b92c34",
         "expect5.45.4", root / "test-tools/expect-source/expect5.45.4",
         [(root / "downloads/5.45-openpty.patch", 2),
          (drivers / "patches/expect-5.45.4-declared-configure-probes.patch", 1),
          (drivers / "patches/expect-5.45.4-tcl-delete-proc-type.patch", 1),
          (drivers / "patches/expect-5.45.4-c23-interfaces.patch", 1),
          (drivers / "patches/expect-5.45.4-cygwin-stty-stdin.patch", 1)]),
    ):
        path = root / "downloads" / archive
        if digest(path) != sha:
            raise ContractError("Pinned source archive changed")
        destination = output / name
        destination.mkdir()
        with tarfile.open(path) as stream:
            stream.extractall(destination, filter="data")
        tree = destination / subdir
        patch_records = []
        for index, (patch, strip) in enumerate(patches):
            apply(root, tree, patch, strip, destination / f"patch-{index}.log")
            patch_records.append({"path": str(patch), "sha256": digest(patch), "strip": strip})
        original = inventory(tree)
        checked, mismatches = {}, {}
        for filename, row in original.items():
            relative = Path(filename)
            selected = relative.suffix in (".c", ".h", ".at", ".test") or filename == "configure.in"
            if not selected:
                continue
            actual = working / filename
            current = digest(actual) if actual.is_file() else None
            checked[filename] = row
            if current != row["sha256"]:
                mismatches[filename] = {"expected": row["sha256"], "actual": current}
        report["packages"][name] = {
            "archive_sha256": sha, "patches": patch_records, "functional_source_files": checked,
            "mismatches": mismatches, "generated_configure_and_makefiles_excluded": True}
    report["passed"] = all(not row["mismatches"] for row in report["packages"].values())
    write_json(output / "result.json", report)
    print(json.dumps({"passed": report["passed"], "counts": {
        name: len(row["functional_source_files"]) for name, row in report["packages"].items()},
        "mismatches": {name: row["mismatches"] for name, row in report["packages"].items()}}), flush=True)
    if not report["passed"]:
        raise ContractError("Working functional sources differ from exact pinned patch replay")


if __name__ == "__main__":
    main()
