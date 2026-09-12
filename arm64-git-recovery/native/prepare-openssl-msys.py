"""Prepare the real MSYS OpenSSL patch stack and a distinct LP64 ARM64 target profile."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "recipes", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("New MSYS OpenSSL preparation root required")
    verify_tree(args.source, args.manifest)
    verify_tree(args.recipes, args.recipes.with_name(args.recipes.name + ".inventory.json"))
    record = json.loads(args.manifest.read_text())
    recipe = args.recipes / "openssl"
    recipe_text = (recipe / "PKGBUILD").read_text()
    if record["source"]["version"] != "3.6.4" or record["source"]["sha256"] not in recipe_text:
        raise ContractError("OpenSSL source differs from the pinned MSYS recipe")
    shutil.copytree(args.source, args.output, symlinks=True)
    patches = []
    with args.output.with_name(args.output.name + ".prepare.log").open("x") as log:
        for name in ("0001-Use-usr-ssl-as-ca-dir-instead-of-.-demoCA.patch",
                     "0002-Support-MSYS2.patch", "0004-Override-engines-directory.patch"):
            path = recipe / name
            upstream_hash = digest(path)
            if upstream_hash not in recipe_text:
                raise ContractError("MSYS OpenSSL patch is not checksum-pinned")
            if name == "0001-Use-usr-ssl-as-ca-dir-instead-of-.-demoCA.patch":
                path = Path(__file__).parent / "patches/openssl-3.6-msys-ca-directory.patch"
            subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(path)],
                           cwd=args.output, stdout=log, stderr=subprocess.STDOUT, check=True)
            patches.append({"path": str(path), "sha256": digest(path), "upstream_sha256": upstream_hash})
        cpu_patch = Path(__file__).parent / "patches/openssl-msys-arm64-windows-capabilities.patch"
        subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(cpu_patch)],
                       cwd=args.output, stdout=log, stderr=subprocess.STDOUT, check=True)
        patches.append({"path": str(cpu_patch), "sha256": digest(cpu_patch),
                        "scope": "Use upstream Windows CPU feature APIs on Windows-hosted Cygwin/MSYS ARM64; no global _WIN32, ABI, thread or algorithm changes"})
        profile = Path(__file__).with_name("openssl-msys-arm64.conf")
        shutil.copyfile(profile, args.output / "Configurations/99-msys-arm64.conf")
        subprocess.run(["perl", "-c", str(args.output / "Configurations/99-msys-arm64.conf")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    record.update({"source_manifest_sha256": digest(args.manifest), "recipe_sha256": digest(recipe / "PKGBUILD"),
                   "msys_patches": patches, "target_profile": "Cygwin-aarch64", "target_profile_sha256": digest(profile),
                   "scope": "MSYS LP64/pthreads/dlfcn and MSYS DLL naming; ARM64 PE assembly. Not MinGW/UCRT or execution acceptance.",
                   "files": inventory(args.output)})
    args.output.with_name(args.output.name + ".prepare.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Prepared MSYS OpenSSL 3.6.4 with {len(record['files'])} files")


if __name__ == "__main__":
    main()
