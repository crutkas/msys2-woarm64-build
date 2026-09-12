#!/usr/bin/env python3
"""Prepare an exact, idempotent v12 Cygwin w32api overlay without building headers."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

RECIPE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Unexpected link in pinned w32api export: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--identity-only", action="store_true")
    args = parser.parse_args()
    api = runpy.run_path(str(RECIPE / "source-lock.py"))
    lock = api["load_lock"](RECIPE)
    source_lock = lock["sources"]["mingw-w64"]
    contract = {"repository": source_lock["repository"], "revision": source_lock["revision"],
                "patches": source_lock["overlay_patches"]}
    identity = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if args.identity_only:
        print(identity)
        return
    if args.source is None or args.output is None:
        parser.error("--source and --output are required")
    source = args.source.resolve(strict=True)

    def git(*command):
        return subprocess.check_output(["git", "-C", str(source), *command])

    if git("rev-parse", "HEAD").decode().strip() != contract["revision"]:
        raise ValueError("Not the pinned v12 w32api source")
    original_status = git("status", "--porcelain", "--untracked-files=all")
    for patch in contract["patches"]:
        if "source_identity" in patch:
            expected = patch["source_identity"]
            before = git("show", contract["revision"] + ":" + expected["file"])
            if hashlib.sha256(before).hexdigest() != expected["before_sha256"]:
                raise ValueError("Pinned w32api source blob differs from the patch contract")
    output = args.output.resolve()
    receipt = output.with_name(output.name + ".source.json")
    if output.exists():
        if not receipt.is_file():
            raise ValueError("Incomplete existing w32api overlay; preserving it")
        old = json.loads(receipt.read_text())
        if old["identity"] != identity or old["contract"] != contract or inventory(output) != old["files"]:
            raise ValueError("Unknown w32api overlay drift; preserving it")
        api["verify_patched_source"](lock, "mingw-w64", output)
        print(receipt)
        return
    if receipt.exists() or output.is_relative_to(source):
        raise ValueError("Use a new independent w32api overlay path")
    output.mkdir(parents=True)
    archive = output.with_name(output.name + ".tar")
    if archive.exists():
        raise ValueError("Do not overwrite a preserved source archive")
    with archive.open("xb") as stream:
        subprocess.run(["git", "-C", str(source), "archive", contract["revision"]], stdout=stream, check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(output)], check=True)
    for patch in contract["patches"]:
        command = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-C", str(output), "apply"]
        subprocess.run(command + ["--check", str(RECIPE / patch["file"])], check=True)
        subprocess.run(command + [str(RECIPE / patch["file"])], check=True)
    api["verify_patched_source"](lock, "mingw-w64", output)
    if git("status", "--porcelain", "--untracked-files=all") != original_status:
        raise ValueError("Original dependency changed during overlay preparation")
    receipt.write_text(json.dumps({"schema": 1, "identity": identity, "contract": contract,
                                  "source": str(source), "output": str(output), "files": inventory(output),
                                  "source_archive_sha256": sha(archive),
                                  "original_source_status_sha256": hashlib.sha256(original_status).hexdigest()},
                                 indent=2) + "\n", encoding="utf-8", newline="\n")
    print(receipt)


if __name__ == "__main__":
    main()
