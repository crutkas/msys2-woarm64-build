"""Copy verified portable MSYS libtool generator inputs without installing a package."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory, relative_path


def verify_rows(root, rows):
    expected = {}
    folded = set()
    for row in rows:
        name = row["Path"].replace("\\", "/")
        relative_path(name)
        if name.casefold() in folded:
            raise ContractError("Duplicate libtool generator inventory path")
        folded.add(name.casefold())
        expected[name] = row["SHA256"]
    measured = inventory(root)
    if {name: row.get("sha256") for name, row in measured.items()} != expected:
        raise ContractError("The complete libtool input inventory differs")
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or digest(args.handoff) != args.sha256:
        raise ContractError("A fresh output and the exact published libtool handoff hash are required")
    record = json.loads(args.handoff.read_text())
    if (record.get("Status") != "official-msys-libtool-generator-signature-and-coherence-verified" or
            record.get("Package") != "libtool" or record.get("Version") != "2.6.2-1" or
            record["Archive"]["SignatureExit"] != 0 or record["Coherence"]["ExitCode"] != 0 or
            record["Coherence"]["GeneratedLtmainAndFiveMacrosMatch"] is not True):
        raise ContractError("Unexpected libtool package signature/coherence boundary")
    package, data = Path(record["PackageExtraction"]), Path(record["GeneratorData"])
    package_files = verify_rows(package, record["PackageFiles"])
    generator_files = verify_rows(data, record["GeneratorFiles"])
    expected = {f"generator-data/{name}": row for name, row in generator_files.items()}
    selected = {"bin/libtoolize": "usr/bin/libtoolize",
                "share/licenses/libtool/COPYING": "usr/share/licenses/libtool/COPYING"}
    for destination, source in selected.items():
        expected[destination] = package_files[source]
    shutil.copytree(data, args.output / "generator-data")
    for destination, source in selected.items():
        target = args.output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package / source, target)
    if inventory(args.output) != expected:
        raise ContractError("Portable libtool generator copy differs")
    verify_rows(package, record["PackageFiles"])
    verify_rows(data, record["GeneratorFiles"])
    report = {"schema": 1, "status": "byte-identical-msys-libtool-generator",
              "source_handoff_sha256": args.sha256, "package_version": record["Version"],
              "archive": record["Archive"], "prefix": str(args.output), "files": expected,
              "scope": "Portable scripts/macros from verified x64 bootstrap package; not target library or native Windows tool qualification",
              "target_contract": "Use actual aarch64-pc-cygwin producer; MSYS-patched cygwin rules supply msys DLL naming"}
    args.output.with_name(args.output.name + ".copy.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Copied {len(expected)} exact generator files; no prefix installation")


if __name__ == "__main__":
    main()
