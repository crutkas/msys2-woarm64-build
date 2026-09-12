"""Add verified native Tcl/Tk to a new Git root at the existing /usr/bin/wish contract."""

import argparse
import json
from pathlib import Path
import shutil

from package_tcl import finalize_tk, relocate_tcl_metadata
from sources import ContractError, digest, inventory, relative_path, verify_tree


def overlay_plan(base, component):
    result = dict(base)
    folded = {name.casefold(): name for name in base}
    for name, entry in component.items():
        relative_path(name)
        target = "usr/" + name
        if "sha256" not in entry:
            raise ContractError("Tcl/Tk overlay requires materialized files")
        if target.casefold() in folded and (folded[target.casefold()] != target or result[target] != entry):
            raise ContractError(f"Tcl/Tk overlay collision: {target}")
        result[target] = entry
        folded[target.casefold()] = target
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "component", "component-manifest", "tk-build", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh distribution root is required")
    verify_tree(args.root, args.manifest)
    verify_tree(args.component, args.component_manifest)
    verify_tree(args.tk_build / "stage", args.tk_build / "result.json")
    base, component = inventory(args.root), inventory(args.component)
    required = ("bin/wish.exe", "bin/tclsh.exe", "bin/tk86.dll", "bin/tcl86.dll", "bin/libz.dll")
    if any(name not in component for name in required):
        raise ContractError("Complete native Tcl/Tk runtime input is required")
    planned = overlay_plan(base, component)
    source = args.tk_build / "source"
    source_before = inventory(source)
    shutil.copytree(args.root, args.output)
    for name in component:
        destination = args.output / "usr" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.component / name, destination)
    if inventory(args.output) != planned:
        raise ContractError("Tcl/Tk distribution overlay differs from its input plan")
    required_directories = ("tmp", "var/tmp", "etc")
    for name in required_directories:
        (args.output / name).mkdir(parents=True, exist_ok=True)
    relocate_tcl_metadata(args.output / "usr")
    finalize_tk(source, args.output / "usr")
    after = inventory(args.output)
    changed = sorted(name for name in planned if after.get(name) != planned[name])
    expected = ["usr/lib/pkgconfig/tcl.pc", "usr/lib/pkgconfig/tk.pc",
                "usr/lib/tclConfig.sh", "usr/lib/tkConfig.sh"]
    if any(name not in expected for name in changed):
        raise ContractError(f"Unexpected Tcl/Tk metadata change set: {changed}")
    if any(not name.startswith("usr/include/tk8.6/tk-private/") for name in after.keys() - planned.keys()):
        raise ContractError("Unexpected file introduced during Tk development staging")
    if inventory(source) != source_before:
        raise ContractError("Original Tk source changed")
    verify_tree(args.root, args.manifest)
    verify_tree(args.component, args.component_manifest)
    report = {"schema": 1, "scope": "Native Tcl/Tk overlay; not complete Git distribution or package admission",
              "base_receipt_sha256": digest(args.manifest),
              "component_receipt_sha256": digest(args.component_manifest),
              "tk_build_receipt_sha256": digest(args.tk_build / "result.json"),
              "tk_private_header_source": str(source), "source_files": source_before,
              "required_directories": required_directories,
              "changed_metadata": changed, "files": after,
              "pending": ["Integrated GitGUI/gitk", "Perl", "SSH", "Full editor features", "Package admission"]}
    args.output.with_name(args.output.name + ".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Staged {len(after)} files; existing Git/POSIX executables unchanged")


if __name__ == "__main__":
    main()
