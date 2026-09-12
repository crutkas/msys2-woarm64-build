"""Apply pinned MSYS2 text-library patches to private dependency sources."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree


PATCHES = {
    "libiconv": ["0002-fix-cr-for-awk-in-configure.all.patch", "fix-pointer-buf.patch",
                "0003-add-cp65001-as-utf8-alias.patch"],
    "libidn2": [],
    "gettext": ["0005-Fix-compilation-of-pthread_sigmask.c.patch",
                "122-Use-LF-as-newline-in-envsubst.patch", "0021-replace-fsync.patch",
                "0022-libasprintf.patch", "0024-disable-gnu-format.patch",
                "0030-fix-build-with-mingw-w64-clang.patch"]
}
ADAPTED_GETTEXT_PATCHES = {
    "0005-Fix-compilation-of-pthread_sigmask.c.patch": "gettext-1.0-pthread-sigmask.patch",
    "0022-libasprintf.patch": "gettext-1.0-libasprintf.patch",
}


def prepare(package, source, manifest, recipes, output, runtime_only=False):
    if runtime_only and package != "gettext":
        raise ContractError("Runtime-only preparation is specific to gettext")
    source, manifest, recipes, output = map(Path, (source, manifest, recipes, output))
    if output.exists():
        raise ContractError("Private prepared output must not exist")
    verify_tree(source, manifest)
    verify_tree(recipes, recipes.with_name(recipes.name + ".inventory.json"))
    recipe = recipes / f"mingw-w64-{package}"
    text = (recipe / "PKGBUILD").read_text()
    checksums = re.findall(r"'([0-9a-f]{64})'", text)
    shutil.copytree(source, output)
    records = []
    with output.with_name(output.name + ".prepare.log").open("x") as log:
        for name in PATCHES[package]:
            patch = recipe / name
            sha = digest(patch)
            if sha not in checksums:
                raise ContractError("Patch does not match the pinned package recipe")
            original_sha = sha
            if package == "gettext" and name in ADAPTED_GETTEXT_PATCHES:
                patch = Path(__file__).resolve().parent / "patches" / ADAPTED_GETTEXT_PATCHES[name]
                sha = digest(patch)
            fuzz = 2 if package == "gettext" and original_sha == sha else 0
            result = subprocess.run(["patch", "--batch", "--forward", f"--fuzz={fuzz}", "-p1",
                                     "-i", str(patch.resolve())], cwd=output,
                                    stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ContractError(f"Patch failed: {name}; retain failed preparation")
            records.append({"file": name, "upstream_sha256": original_sha,
                            "applied_patch": str(patch), "sha256": sha, "maximum_fuzz": fuzz})
        if package == "libiconv":
            commands = [["make", "-f", "Makefile.devel", "all"]]
        elif package == "libidn2":
            # The pinned recipe retains the release's vendored gettext macros.
            commands = [["env", "AUTOPOINT=true", "autoreconf", "-ivf"]]
        elif not runtime_only:
            commands = [["libtoolize", "--automake", "--copy", "--force"],
                        ["./autogen.sh", "--skip-gnulib"]]
        else:
            # Runtime patches change C sources/header templates only. Its release
            # configure/Makefile.in remain valid; tools' changed Makefile.gnulib
            # must still be regenerated before a later gettext-tools build.
            commands = []
        for command in commands:
            result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ContractError(f"Source generation failed: {command}; inspect preparation log")
    record = json.loads(manifest.read_text())
    record["original_manifest_sha256"] = digest(manifest)
    record["recipe_inventory_sha256"] = digest(recipes.with_name(recipes.name + ".inventory.json"))
    record["patches"] = records
    record["generation_commands"] = commands
    record["scope"] = "gettext-runtime-only; gettext-tools regeneration pending" if runtime_only else "package preparation"
    record["files"] = inventory(output)
    with output.with_name(output.name + ".inventory.json").open("x") as dest:
        json.dump(record, dest, indent=2)
        dest.write("\n")
    print(f"Prepared {package}: {len(record['files'])} files")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", choices=PATCHES, required=True)
    p.add_argument("--runtime-only", action="store_true")
    for name in ("source", "manifest", "recipes", "output"):
        p.add_argument(f"--{name}", type=Path, required=True)
    a = p.parse_args()
    prepare(a.package, a.source, a.manifest, a.recipes, a.output, a.runtime_only)


if __name__ == "__main__":
    main()
