"""Consolidate a verified multi-stage candidate into one native runtime root, without claiming full closure."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory, relative_path, verify_tree


def plan_files(files):
    mapped, folded = {}, {}
    for relative, record in files.items():
        relative_path(relative)
        if relative.startswith("git-stage/"):
            destination = relative.removeprefix("git-stage/")
        elif relative.startswith("posix-root/payload/"):
            destination = relative.removeprefix("posix-root/payload/")
        elif relative.startswith("git-build-dependencies/bin/") and relative.lower().endswith(".dll"):
            destination = "clangarm64/bin/" + Path(relative).name
        elif relative.startswith("git-build-dependencies/share/licenses/"):
            destination = "clangarm64/" + relative.removeprefix("git-build-dependencies/")
        else:
            continue
        if destination.casefold() in folded and folded[destination.casefold()] != destination:
            raise ContractError(f"Case-colliding same-root payload: {destination}")
        folded[destination.casefold()] = destination
        if "sha256" not in record:
            raise ContractError("Source links need explicit resolution before assembly")
        if destination in mapped and mapped[destination]["record"] != record:
            raise ContractError(f"Conflicting same-root payload: {destination}")
        mapped.setdefault(destination, {"record": record, "sources": []})["sources"].append(relative)
    if not mapped:
        raise ContractError("No shipping content selected")
    runtime_hashes = {row["record"]["sha256"] for path, row in mapped.items()
                      if Path(path).name.lower() == "msys-2.0.dll"}
    if len(runtime_hashes) != 1:
        raise ContractError("Missing or mixed native runtime cohort")
    return mapped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.assembly / "assembly.json"
    if args.output.exists():
        raise ContractError("A new consolidated root is required")
    verify_tree(args.assembly / "ship", manifest)
    before = json.loads(manifest.read_text())
    mapped = plan_files(before["files"])
    for path, row in mapped.items():
        destination = args.output / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.assembly / "ship" / row["sources"][0], destination)
        if digest(destination) != row["record"]["sha256"]:
            raise ContractError("Source changed while assembling")
    for relative in ("tmp", "var/tmp", "etc"):
        (args.output / relative).mkdir(parents=True, exist_ok=True)
    after = inventory(args.output)
    if after != {path: row["record"] for path, row in mapped.items()}:
        raise ContractError("Consolidated output file set differs")
    verify_tree(args.assembly / "ship", manifest)
    report = {"schema": 1, "status": "consolidated-native-candidate-not-full-distribution",
              "input_manifest_sha256": digest(manifest), "sources": mapped, "files": after,
              "runtime_readiness_sha256": before["runtime_readiness_sha256"],
              "scope": "One primary runtime root plus exact native dependency DLLs and licenses; no cross-root PATH fallback",
              "pending": ["Native execution of consolidated root", "Perl/SSH/Tcl/editor components",
                          "Full expected package/feature closure and admission"]}
    args.output.with_name(args.output.name + ".assembly.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Assembled {len(after)} files into a same-root native candidate")


if __name__ == "__main__":
    main()
