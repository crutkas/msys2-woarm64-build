#!/usr/bin/env python3
"""Stage a private full v12 Cygwin w32api header cohort from root06."""

import argparse
import json
from pathlib import Path
import runpy
import shutil

RECIPE = Path(__file__).resolve().parent
COMMON = runpy.run_path(str(RECIPE / "cygwin-w32api-common.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("overlay", "sdk", "sdk-receipt", "sdk-provenance", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    lock = COMMON["load_lock"]()
    overlay = args.overlay.resolve(strict=True)
    overlay_receipt_path = overlay.with_name(overlay.name + ".source.json")
    overlay_receipt = json.loads(overlay_receipt_path.read_text(encoding="utf-8-sig"))
    if (
        overlay_receipt["revision"] != lock["revision"]
        or overlay_receipt["sourceLock"]["sha256"]
        != COMMON["sha"](RECIPE / "cygwin-w32api-source-lock.json")
        or COMMON["inventory"](overlay) != overlay_receipt["files"]
    ):
        raise ValueError("Prepared source overlay differs")
    if len(overlay_receipt.get("patchEvidence", [])) != len(lock["patches"]):
        raise ValueError("Prepared source patch evidence is incomplete")
    for patch, evidence in zip(lock["patches"], overlay_receipt["patchEvidence"]):
        if evidence["canonicalPatch"]["sha256"] != patch["sha256"]:
            raise ValueError("Canonical applied patch differs")
        for entry in evidence.values():
            if COMMON["ref"](entry["path"]) != entry:
                raise ValueError("Prepared source patch evidence changed")
    COMMON["verify_patched_source"](lock, overlay)
    sdk = args.sdk.resolve(strict=True)
    provenance = COMMON["verify_sdk_inventory"](lock, sdk, args.sdk_provenance)
    sdk_receipt = json.loads(args.sdk_receipt.read_text(encoding="utf-8-sig"))
    if COMMON["sha"](args.sdk_receipt) != lock["sdk_contract"]["tool_receipt_sha256"]:
        raise ValueError("Pinned SDK tool receipt differs")
    receipt_files = {
        Path(entry["rel"]).as_posix(): entry["sha256"]
        for entry in sdk_receipt.get("compilerHashes", [])
    }
    if receipt_files != lock["sdk_contract"]["required_files"]:
        raise ValueError("Pinned SDK tool receipt has an unexpected file set")
    baseline = sdk / "aarch64-pc-cygwin/include/w32api"
    identity = COMMON["source_identity"](lock)
    relative = Path("psdk_inc/intrin-impl.h")
    if COMMON["sha"](baseline / relative) != identity["before_sha256"]:
        raise ValueError("Active header is not the exact pinned v12 intrinsic blob")
    abi = {}
    for installed, source in (
        ("_cygwin.h", "mingw-w64-headers/crt/_cygwin.h"),
        ("basetsd.h", "mingw-w64-headers/include/basetsd.h"),
    ):
        expected = overlay / source
        if COMMON["sha"](baseline / installed) != COMMON["sha"](expected):
            raise ValueError(f"Existing ARM64 Cygwin ABI overlay differs: {installed}")
        abi[installed] = COMMON["sha"](expected)
    before = COMMON["inventory"](baseline)
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(sdk) or out.is_relative_to(overlay):
        raise ValueError("Use a fresh private header-cohort path")
    out.mkdir(parents=True)
    include = out / "include"
    shutil.copytree(baseline, include)
    shutil.copy2(overlay / identity["file"], include / relative)
    after = COMMON["inventory"](include)
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    if changed != [relative.as_posix()]:
        raise ValueError(f"Unexpected private w32api changes: {changed}")
    if after[relative.as_posix()]["sha256"] != identity["after_sha256"]:
        raise ValueError("Staged intrinsic header differs")
    if COMMON["inventory"](baseline) != before:
        raise ValueError("Active SDK headers changed")
    COMMON["verify_sdk_inventory"](lock, sdk, args.sdk_provenance)
    manifest = out / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "target": "aarch64-pc-cygwin",
                "files": after,
                "baselineFiles": before,
                "changedFiles": changed,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    stage = {
        "schema": 1,
        "status": "private-v12-cygwin-interlocked-headers-staged-not-qualified",
        "target": "aarch64-pc-cygwin",
        "cohortRoot": str(out),
        "include": str(include),
        "source": {
            "repository": lock["repository"],
            "revision": lock["revision"],
        },
        "headerContract": identity,
        "sourceOverlayReceipt": COMMON["ref"](overlay_receipt_path),
        "previousCygwinABIOverlay": abi,
        "sdk": str(sdk),
        "sdkToolReceipt": COMMON["ref"](args.sdk_receipt),
        "sdkProvenance": COMMON["ref"](args.sdk_provenance),
        "sdkFullInventory": provenance["fullInventory"],
        "manifest": COMMON["ref"](manifest),
        "sourceLock": COMMON["ref"](RECIPE / "cygwin-w32api-source-lock.json"),
        "recipeInputs": {
            "stage": COMMON["ref"](__file__),
            "common": COMMON["ref"](RECIPE / "cygwin-w32api-common.py"),
        },
        "limits": (
            "Header-only successor. No root06, runtime907, compiler, Perl, OpenSSL, "
            "or admitted 70d63 MinGW provider bytes changed."
        ),
    }
    (out / "stage.json").write_text(
        json.dumps(stage, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(out / "stage.json")


if __name__ == "__main__":
    main()
