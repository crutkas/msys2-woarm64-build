"""Compose a checked native development/runtime view; never claim a replacement package."""

import argparse
import json
from pathlib import Path
import shutil

from bash_chain_inputs import ROOT, fresh
from readline_chain_inputs import SEALS
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import write_json


def selected(name):
    path = Path(name)
    return (name.startswith("usr/include/")
            or name.startswith(("usr/share/locale/", "usr/share/terminfo/"))
            or (name.startswith("usr/lib/") and path.suffix in (".a", ".la", ".pc"))
            or (name.startswith("usr/bin/") and path.suffix == ".dll"))


def main(args):
    output = ROOT / args.output
    fresh(output)
    components, merged, origins = [], {}, {}
    for stage in args.stage:
        stage = stage.resolve()
        manifest = stage.parent / "stage.inventory.json"
        verify_tree(stage, manifest)
        record = json.loads(manifest.read_text())
        if record["compiler_receipt_sha256"] != SEALS["compiler"]:
            raise ContractError("Bash SDK components do not share the approved native cohort")
        temporary = (record.get("classification", "").startswith("temporary-")
                     or any(row.get("profile") == "iconv-bridge" for row in record.get("components", [])))
        if temporary and not args.allow_iconv_bridge:
            raise ContractError("Temporary bridge cannot enter the final Bash SDK")
        components.append({"stage": str(stage), "manifest": str(manifest), "sha256": digest(manifest),
                           "package": record.get("package"), "profile": record.get("profile"),
                           "nls_enabled": record.get("nls_enabled")})
        for name, row in record["files"].items():
            if not selected(name):
                continue
            if "sha256" not in row:
                raise ContractError("Development view does not synthesize source links")
            if name in merged and merged[name] != row:
                raise ContractError(f"Conflicting native SDK file: {name}")
            merged[name] = row
            origins.setdefault(name, []).append(str(stage))
    output.mkdir()
    stage_out = output / "stage"
    for name, row in merged.items():
        target = stage_out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(origins[name][0]) / name, target)
        if digest(target) != row["sha256"]:
            raise ContractError("Native development-view copy changed")
    if inventory(stage_out) != merged:
        raise ContractError("Native development-view inventory differs")
    for component in components:
        verify_tree(component["stage"], component["manifest"])
    report = {"schema": 1, "compiler_receipt_sha256": SEALS["compiler"],
              "files": merged, "components": components, "origins": origins,
              "classification": "temporary-NLS-cycle-development-view" if args.allow_iconv_bridge else "final-coherent-native-Bash-development-view",
              "scope": "Headers/static/import libraries/pkgconfig/native DLLs/locale/terminfo input view; original complete package stages retained, no package/provides/admission claim"}
    write_json(output / "stage.inventory.json", report)
    print(json.dumps({"stage": str(stage_out), "files": len(merged),
                      "manifest_sha256": digest(output / "stage.inventory.json"), "classification": report["classification"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stage", type=Path, action="append", required=True)
    parser.add_argument("--allow-iconv-bridge", action="store_true")
    main(parser.parse_args())
