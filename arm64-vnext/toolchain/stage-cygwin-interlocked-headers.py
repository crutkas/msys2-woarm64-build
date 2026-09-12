#!/usr/bin/env python3
"""Stage the separate pinned v12 Cygwin w32api header successor, never a runtime."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

RECIPE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(RECIPE / "stage-mingw-interlocked-headers.py"))
sha, inventory = helpers["sha"], helpers["inventory"]


def verify_sdk_inventory(sdk, provenance_path, expected_sha):
    if sha(provenance_path) != expected_sha:
        raise ValueError("Selected SDK provenance receipt differs")
    provenance = json.loads(provenance_path.read_text())
    if Path(provenance["root06Toolchain"]).resolve() != sdk:
        raise ValueError("Provenance does not bind the selected SDK")
    manifest = Path(provenance["fullInventory"]["path"])
    if sha(manifest) != provenance["fullInventory"]["sha256"]:
        raise ValueError("SDK inventory receipt differs")
    entries = json.loads(manifest.read_text())
    if len(entries) != provenance["fullInventory"]["fileCount"]:
        raise ValueError("SDK inventory count differs")
    expected = set()
    for entry in entries:
        path = (sdk / entry["rel"]).resolve(strict=True)
        if not path.is_relative_to(sdk) or path in expected or sha(path) != entry["sha256"]:
            raise ValueError(f"SDK inventory file changed: {entry['rel']}")
        expected.add(path)
    actual = {path.resolve() for path in sdk.rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("SDK has uninventoried or missing files")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("overlay", "sdk", "sdk-receipt", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--sdk-provenance", required=True, type=Path)
    parser.add_argument("--sdk-provenance-sha256", required=True)
    args = parser.parse_args()
    lock_api = runpy.run_path(str(RECIPE / "source-lock.py"))
    lock = lock_api["load_lock"](RECIPE)
    config = lock["sources"]["mingw-w64"]
    contract = config["overlay_patches"][-1]["source_identity"]
    overlay = args.overlay.resolve(strict=True)
    overlay_receipt = overlay.with_name(overlay.name + ".source.json")
    prepared = json.loads(overlay_receipt.read_text())
    if prepared["contract"]["revision"] != config["revision"] or prepared["contract"]["patches"] != config["overlay_patches"]:
        raise ValueError("Wrong v12 overlay recipe")
    for name, digest in prepared["files"].items():
        if sha(overlay / name) != digest:
            raise ValueError(f"Source overlay changed: {name}")
    lock_api["verify_patched_source"](lock, "mingw-w64", overlay)
    sdk = args.sdk.resolve(strict=True)
    sdk_provenance = verify_sdk_inventory(sdk, args.sdk_provenance, args.sdk_provenance_sha256)
    receipt = json.loads(args.sdk_receipt.read_text())
    # This receipt binds tool binaries only, not the original header lineage.
    for entry in receipt["compilerHashes"]:
        if sha(sdk / entry["rel"]) != entry["sha256"]:
            raise ValueError("Selected active SDK tool input differs")
    baseline = sdk / "aarch64-pc-cygwin/include/w32api"
    if sha(baseline / "psdk_inc/intrin-impl.h") != contract["before_sha256"]:
        raise ValueError("Active header is not the unmodified pinned v12 intrinsic blob")
    abi = {}
    for installed, source in (("_cygwin.h", "crt/_cygwin.h"), ("basetsd.h", "include/basetsd.h")):
        expected = overlay / "mingw-w64-headers" / source
        if sha(baseline / installed) != sha(expected):
            raise ValueError(f"Existing Cygwin ABI overlay differs: {installed}")
        abi[installed] = sha(expected)
    original = inventory(baseline)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    if out.is_relative_to(sdk) or out.is_relative_to(overlay):
        raise ValueError("Use a new private header cohort outside active SDK/source")
    include = out / "include"
    shutil.copytree(baseline, include)
    shutil.copy2(overlay / contract["file"], include / "psdk_inc/intrin-impl.h")
    final = inventory(include)
    changed = sorted(name for name in set(original) | set(final) if original.get(name) != final.get(name))
    if changed != ["psdk_inc/intrin-impl.h"]:
        raise ValueError("Unexpected private w32api header changes")
    if inventory(baseline) != original:
        raise ValueError("Active SDK headers changed")
    verify_sdk_inventory(sdk, args.sdk_provenance, args.sdk_provenance_sha256)
    manifest = out / "manifest.json"
    manifest.write_text(json.dumps({"schema": 1, "files": final, "baselineFiles": original,
                                    "baseline": str(baseline), "include": str(include),
                                    "changedFiles": changed}, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "source-lock.json").write_bytes((RECIPE / "source-lock.json").read_bytes())
    report = {"schema": 1, "status": "private-v12-cygwin-interlocked-headers-staged-not-qualified",
              "target": "aarch64-pc-cygwin", "source": config, "headerContract": contract,
              "sourceOverlayReceipt": {"path": str(overlay_receipt), "sha256": sha(overlay_receipt)},
              "previousCygwinABIOverlay": abi,
              "sdk": str(sdk), "sdkToolReceipt": {"path": str(args.sdk_receipt), "sha256": sha(args.sdk_receipt)},
              "sdkProvenance": {"path": str(args.sdk_provenance), "sha256": sha(args.sdk_provenance)},
              "sdkFullInventory": sdk_provenance["fullInventory"],
              "sdkToolReceiptScope": "Compiler/backend/assembler/CRT/import identity only, not header-source provenance.",
              "headerProvenance": "Intrinsic header exactly matches upstream v12 blob; installed _cygwin.h and basetsd.h exactly match the separate locked ARM64-Cygwin ABI overlay. Other installed header bytes retained under inventory.",
              "manifest": {"path": str(manifest), "sha256": sha(manifest)},
              "sourceLockSHA256": sha(out / "source-lock.json"),
              "limits": "Only one w32api header changed. No active root06/907/runtime/compiler/Perl/OpenSSL or sealed 70d63 MinGW cohort change."}
    (out / "stage.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "stage.json")


if __name__ == "__main__":
    main()
