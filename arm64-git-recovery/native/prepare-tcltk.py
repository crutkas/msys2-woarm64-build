"""Prepare the pinned Windows ARM64 Tcl/Tk recipes without compiling or installing."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=("tcl", "tk"), required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Fresh Tcl/Tk preparation output required")
    source = args.sources / args.package
    manifest = args.sources / f"{args.package}.inventory.json"
    recipes = args.sources / "mingw-upstream-recipes"
    verify_tree(source, manifest)
    verify_tree(recipes, recipes.with_name(recipes.name + ".inventory.json"))
    record = json.loads(manifest.read_text())
    recipe = recipes / f"mingw-w64-{args.package}"
    recipe_text = (recipe / "PKGBUILD").read_text()
    if record["source"]["version"] != "8.6.18" or record["source"]["sha256"] not in recipe_text:
        raise ContractError("Source differs from the pinned Tcl/Tk package")
    shutil.copytree(source, args.output, symlinks=True)
    changes = []
    with args.output.with_name(args.output.name + ".prepare.log").open("x") as log:
        if args.package == "tcl":
            for name in ("005-no-xc.mingw.patch", "010-win-non-x86.patch"):
                path = recipe / name
                if digest(path) not in recipe_text:
                    raise ContractError("Unpinned Tcl patch")
                subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(path)],
                               cwd=args.output, stdout=log, stderr=subprocess.STDOUT, check=True)
                changes.append({"patch": name, "sha256": digest(path)})
            shutil.copyfile(args.output / "unix/tcl.pc.in", args.output / "win/tcl.pc.in")
        for path in args.output.rglob("*"):
            if path.is_file() and (path.name == "tcl.m4" or path.name.startswith("configure")):
                data = path.read_bytes()
                if b"-static-libgcc" in data:
                    before = digest(path)
                    path.write_bytes(data.replace(b"-static-libgcc", b""))
                    changes.append({"path": path.relative_to(args.output).as_posix(),
                                    "operation": "pinned-shared-GCC-runtime-policy",
                                    "before_sha256": before, "after_sha256": digest(path)})
        subprocess.run(["autoreconf", "-fi"], cwd=args.output / "win",
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    record.update({"original_manifest_sha256": digest(manifest),
                   "recipe_sha256": digest(recipe / "PKGBUILD"), "changes": changes,
                   "scope": "Prepared Windows ARM64 source; not built; Tcl stub tables are legitimate ABI dispatch libraries",
                   "pending": ["Native GCC SEH repair", "Verify shared GCC runtime contract", "Build and native interpreter/GUI tests"],
                   "files": inventory(args.output)})
    args.output.with_name(args.output.name + ".prepare.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Prepared {args.package} 8.6.18: {len(record['files'])} files")


if __name__ == "__main__":
    main()
