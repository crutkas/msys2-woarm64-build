#!/usr/bin/env python3
"""Export and patch the exact pinned v12 Cygwin w32api source."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tarfile

RECIPE = Path(__file__).resolve().parent
COMMON = runpy.run_path(str(RECIPE / "cygwin-w32api-common.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    lock = COMMON["load_lock"]()
    source = args.source.resolve(strict=True)

    def git(*command):
        return subprocess.check_output(["git", "-C", str(source), *command])

    if git("rev-parse", "HEAD").decode().strip() != lock["revision"]:
        raise ValueError("Not the pinned v12 Cygwin w32api source")
    source_status = git("status", "--porcelain", "--untracked-files=all")
    if source_status:
        raise ValueError("Pinned dependency checkout must be clean")
    identity = COMMON["source_identity"](lock)
    original = git("show", lock["revision"] + ":" + identity["file"])
    if hashlib.sha256(original).hexdigest() != identity["before_sha256"]:
        raise ValueError("Pinned upstream intrinsic blob differs")
    out = args.output.resolve()
    receipt = out.with_name(out.name + ".source.json")
    if out.exists():
        if not receipt.is_file():
            raise ValueError("Incomplete existing overlay; preserving it")
        previous = json.loads(receipt.read_text(encoding="utf-8-sig"))
        if (
            previous.get("status") != "pinned-v12-cygwin-w32api-overlay-prepared"
            or previous.get("revision") != lock["revision"]
            or previous.get("sourceLock", {}).get("sha256")
            != COMMON["sha"](RECIPE / "cygwin-w32api-source-lock.json")
            or COMMON["inventory"](out) != previous.get("files")
        ):
            raise ValueError("Existing overlay drift; preserving it")
        COMMON["verify_patched_source"](lock, out)
        if git("status", "--porcelain", "--untracked-files=all") != source_status:
            raise ValueError("Pinned dependency checkout changed")
        print(receipt)
        return
    if out.is_relative_to(source):
        raise ValueError("Use a fresh independent overlay path")
    out.mkdir(parents=True)
    archive = out.with_name(out.name + ".tar")
    if archive.exists():
        raise ValueError("Preserved source archive already exists")
    with archive.open("xb") as stream:
        subprocess.run(
            [
                "git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                "-C", str(source), "archive", lock["revision"],
            ],
            stdout=stream,
            check=True,
        )
    with tarfile.open(archive, "r:") as source_archive:
        source_archive.extractall(out, filter="data")
    logs = out.with_name(out.name + "-logs")
    logs.mkdir()
    patch_evidence = []
    for patch in lock["patches"]:
        canonical_patch = logs / patch["file"]
        canonical_patch.write_bytes(
            (RECIPE / patch["file"]).read_bytes().replace(b"\r\n", b"\n")
        )
        if COMMON["sha"](canonical_patch) != patch["sha256"]:
            raise ValueError(f"Canonical patch identity differs: {patch['file']}")
        command = [
            "git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
            "-C", str(out), "apply",
        ]
        recorded = {"canonicalPatch": COMMON["ref"](canonical_patch)}
        for suffix, extra in (("check", ["--check"]), ("apply", [])):
            log = logs / f"{Path(patch['file']).stem}-{suffix}.log"
            with log.open("xb") as stream:
                subprocess.run(
                    command + extra + [str(canonical_patch)],
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            recorded[suffix + "Log"] = COMMON["ref"](log)
        patch_evidence.append(recorded)
    COMMON["verify_patched_source"](lock, out)
    if git("status", "--porcelain", "--untracked-files=all") != source_status:
        raise ValueError("Pinned dependency checkout changed during export")
    receipt.write_text(
        json.dumps(
            {
                "schema": 1,
                "status": "pinned-v12-cygwin-w32api-overlay-prepared",
                "repository": lock["repository"],
                "revision": lock["revision"],
                "source": str(source),
                "output": str(out),
                "sourceStatusSHA256": hashlib.sha256(source_status).hexdigest(),
                "sourceArchive": COMMON["ref"](archive),
                "sourceLock": COMMON["ref"](RECIPE / "cygwin-w32api-source-lock.json"),
                "recipeInputs": {
                    "prepare": COMMON["ref"](__file__),
                    "common": COMMON["ref"](RECIPE / "cygwin-w32api-common.py"),
                },
                "patches": [
                    COMMON["ref"](RECIPE / patch["file"]) for patch in lock["patches"]
                ],
                "patchEvidence": patch_evidence,
                "files": COMMON["inventory"](out),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(receipt)


if __name__ == "__main__":
    main()
