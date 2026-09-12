"""Export selected helper or build-driver subtrees after full source verification."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory, verify_tree


SCOPES = {
    "git-full": ("contrib/credential/wincred", "COPYING"),
    "build-extra": ("git-extra", "LICENSE.txt"),
    "meson": ("meson.py", "mesonbuild", "COPYING"),
    "mingw-recipes": ("mingw-w64-git",),
    "stage": (),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=SCOPES, nargs="+", default=["git-full", "build-extra"])
    parser.add_argument("--full-source", action="store_true", help="Export every file, not just selected subtrees")
    parser.add_argument("--manifest", type=Path, help="Explicit manifest for one selected tree, including a completed build stage")
    parser.add_argument("--materialize-file-links", action="store_true",
                        help="Record and materialize bounded internal source links for Windows build inputs")
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh helper-source export is required")
    if args.manifest and len(args.only) != 1:
        raise ContractError("An explicit manifest must identify exactly one tree")
    if "stage" in args.only and (not args.manifest or not args.full_source):
        raise ContractError("Stage export requires an explicit complete build manifest")
    args.output.mkdir(parents=True)
    for name in args.only:
        paths = SCOPES[name]
        source = args.sources / name
        manifest = args.manifest or args.sources / f"{name}.inventory.json"
        verify_tree(source, manifest)
        original = json.loads(manifest.read_text())
        selected = {rel: row for rel, row in original["files"].items()
                    if args.full_source or any(rel == path or rel.startswith(path + "/") for path in paths)}
        if not selected:
            raise ContractError("Source export must be nonempty")
        destination = args.output / name
        exported, transformations = {}, []
        folded = set()

        def copy_entry(rel, destination_rel, ancestry):
            record = original["files"][rel]
            target = destination / destination_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            original_path = source / rel
            if "symlink" in record:
                resolved = original_path.resolve()
                if not args.materialize_file_links or not resolved.is_relative_to(source.resolve()):
                    raise ContractError(f"Unsupported source link: {rel}")
                if resolved.is_dir():
                    if resolved in ancestry:
                        raise ContractError(f"Cyclic source directory link: {rel}")
                    prefix = resolved.relative_to(source.resolve()).as_posix() + "/"
                    children = [child for child in original["files"] if child.startswith(prefix)]
                    if not children:
                        raise ContractError(f"Source directory link has no inventoried contents: {rel}")
                    transformations.append({"path": destination_rel, "operation": "materialize-internal-directory-link",
                                            "original_target": record["symlink"], "inventoried_entries": len(children)})
                    for child in children:
                        copy_entry(child, destination_rel + "/" + child[len(prefix):], (*ancestry, resolved))
                    return
                if not resolved.is_file():
                    raise ContractError(f"Unsupported source link target: {rel}")
                expected_hash = digest(resolved)
                transformations.append({"path": destination_rel, "operation": "materialize-internal-file-link",
                                        "original_target": record["symlink"], "content_sha256": expected_hash})
                original_path = resolved
            else:
                expected_hash = record["sha256"]
            if destination_rel.casefold() in folded:
                raise ContractError(f"Colliding expanded source path: {destination_rel}")
            folded.add(destination_rel.casefold())
            shutil.copyfile(original_path, target)
            if digest(target) != expected_hash:
                raise ContractError("Source changed during helper export")
            exported[destination_rel] = {"sha256": expected_hash, "size": target.stat().st_size}

        for rel in selected:
            copy_entry(rel, rel, (source.resolve(),))
        if inventory(destination) != exported:
            raise ContractError("Helper export file set differs")
        original["original_manifest_sha256"] = digest(manifest)
        original["export_scope"] = "full-source-file-contents" if args.full_source else list(paths)
        if name == "stage":
            original["export_scope"] = "full-built-stage-file-contents"
        original["transformations"] = transformations
        original["files"] = exported
        (args.output / f"{name}.inventory.json").write_text(json.dumps(original, indent=2) + "\n")
        print(f"{name}: exported {len(exported)} files; scope={original['export_scope']}; materialized links={len(transformations)}")


if __name__ == "__main__":
    main()
