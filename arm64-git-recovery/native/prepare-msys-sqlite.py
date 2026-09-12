"""Prepare the pinned seven-split MSYS SQLite source and documentation without building."""

import argparse
import json
import os
from pathlib import Path
import shutil

from bounded_process import run
from sources import ContractError, digest, inventory, verify_tree

ASSETS = {
    "PKGBUILD": "6db1e1013349ee4189c267edc2b6640ef39c477d2f62bbc0a2d0cc97338a01c8",
    "LICENSE": "0b76663a90e034f3d7f2af5bfada4cedec5ebc275361899eccc5c18e6f01ff1f",
    "0001-sqlite-pcachetrace-include-sqlite3.patch": "6518119034ceb2820d058afcb099d11f636271f55a41ffae22855af66a369166",
    "0002-sqlite3.32.3-Makefile.in-fix-rule-compiling-rbu.exe.patch": "2a3be75d6a0e8f7ea1a53f0434a9e1823fcb5965069f482083694388c7564f1c",
    "0031-use-packaged-lempar.c.patch": "9d51e267719f48454627860cf0529928b6711c053e3b930344d897e95a0810fa",
    "Makefile.ext.in": "8c169857b1c449fb7f4e31aaedccdb15435b2f8a83f0f4e744569894a86d8bbd",
    "README.md.in": "ef3a1faa02a88e05539d160d51679f164dfa23cc5a637ff36bc504bf04d6d7a6",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "docs", "docs-manifest", "recipe", "patch-program", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists():
        raise ContractError("SQLite preparation requires a fresh owned output")
    source_record = json.loads(args.manifest.read_text())
    docs_record = json.loads(args.docs_manifest.read_text())
    if (source_record["source"]["id"] != "sqlite-msys"
            or source_record["source"]["sha256"] != "d18fa15aec74d8c17e1463f861095adc01b5ad190256acb4f91d22f0368d232b"
            or docs_record["source"]["sha256"] != "a1d0f5de57485d062796ed7e67daff0758b50d00001a0f233a2c15aaf40bbdc8"
            or source_record["source"]["version"] != "3.53.4" or docs_record["source"]["version"] != "3.53.4"):
        raise ContractError("Both exact SQLite 3.53.4 source and documentation archives are required")
    verify_tree(args.source, args.manifest)
    verify_tree(args.docs, args.docs_manifest)
    for name, sha in ASSETS.items():
        if digest(args.recipe / name) != sha:
            raise ContractError(f"SQLite recipe input differs: {name}")
    immutable = {str(path): digest(path) for path in
                 (args.manifest, args.docs_manifest, args.patch_program, Path(__file__))}
    args.output.mkdir(parents=True)
    source, docs, recipe = (args.output / name for name in ("source", "docs", "recipe"))
    shutil.copytree(args.source, source)
    shutil.copytree(args.docs, docs)
    recipe.mkdir()
    for name in ASSETS:
        shutil.copyfile(args.recipe / name, recipe / name)
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": str(args.patch_program.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(args.output), "USERPROFILE": str(args.output), "TMP": str(args.output), "TEMP": str(args.output)})
    report = {"schema": 1, "status": "failed", "source": source_record["source"],
              "source_manifest_sha256": digest(args.manifest), "docs_manifest_sha256": digest(args.docs_manifest),
              "recipe_inputs": ASSETS, "input_identities": immutable, "steps": [],
              "target": "aarch64-pc-cygwin MSYS LP64", "dependencies": ["readline", "zlib-msys", "tcl-msys"],
              "scope": "Exact source preparation only; preserve all seven package splits, Tcl analyzer/bindings, extensions, lemon and docs"}
    try:
        for index, name in enumerate(name for name in ASSETS if name.endswith(".patch")):
            argv = [args.patch_program, "--batch", "--forward", "--fuzz=0", "-p1", "-i", recipe / name]
            with (args.output / f"patch-{index + 1}.log").open("xb") as log:
                process = run(argv, cwd=source, env=env, log=log, timeout=120)
            report["steps"].append({"command": list(map(str, argv)), "process": process, "patch_sha256": ASSETS[name]})
            if not process["passed"]:
                raise ContractError("Pinned SQLite patch application failed")
        report.update({"status": "prepared-msys-sqlite-full-source-and-docs",
                       "files": inventory(source), "docs_files": inventory(docs)})
    finally:
        try:
            if any(digest(path) != sha for path, sha in immutable.items()):
                raise ContractError("SQLite preparation input changed")
            verify_tree(args.source, args.manifest)
            verify_tree(args.docs, args.docs_manifest)
            if any(digest(args.recipe / name) != sha or digest(recipe / name) != sha for name, sha in ASSETS.items()):
                raise ContractError("SQLite recipe input changed while preparing")
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "source.prepare.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
