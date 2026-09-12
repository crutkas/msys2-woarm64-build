#!/usr/bin/env python3
"""Seal the distinct v12 w32api public-Interlocked successor and consumer boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil

RECIPE = Path(__file__).resolve().parent


def ref(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "overlay-proof", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    stage = load(root / "cohort/stage.json")
    manifest = load(root / "cohort/manifest.json")
    proof = load(root / "native-controls-final/result.json")
    overlay_proof = load(args.overlay_proof)
    if proof["status"] != "v12-cygwin-public-interlocked-header-successor-qualified":
        raise ValueError("Public API qualification is incomplete")
    if overlay_proof["status"] != "v12-w32api-overlay-controls-qualified":
        raise ValueError("Overlay identity controls are incomplete")
    if ref(RECIPE / "source-lock.json")["sha256"] != stage["sourceLockSHA256"]:
        raise ValueError("Source lock changed after staging")
    if proof["stage"]["sha256"] != ref(root / "cohort/stage.json")["sha256"]:
        raise ValueError("Qualification used another header cohort")
    helper = runpy.run_path(str(RECIPE / "stage-cygwin-interlocked-headers.py"))
    provenance = stage["sdkProvenance"]
    helper["verify_sdk_inventory"](Path(stage["sdk"]), Path(provenance["path"]), provenance["sha256"])
    for name, entry in manifest["files"].items():
        if ref(root / "cohort/include" / name)["sha256"] != entry["sha256"]:
            raise ValueError("Private header cohort changed")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    recipes = out / "recipes"
    recipes.mkdir()
    names = ("source-lock.py", "source-lock.json", "bootstrap-cygwin.sh", "prepare-w32api-overlay.py",
             "stage-cygwin-interlocked-headers.py", "stage-mingw-interlocked-headers.py",
             "test-w32api-overlay.py", "test-cygwin-interlocked-cohort.py",
             "seal-cygwin-interlocked-cohort.py", "test-source-lock.py", "test-msys-ucontext.py",
             "run-msys-library-stage.py", "README.md", "probes/cygwin-public-interlocked-native.c")
    for name in names:
        target = recipes / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RECIPE / name, target)
    lock = load(RECIPE / "source-lock.json")
    for source in lock["sources"].values():
        for patch in source["patches"] + source.get("overlay_patches", []):
            shutil.copy2(RECIPE / patch["file"], recipes / patch["file"])
            if "transport" in patch:
                shutil.copy2(RECIPE / patch["transport"]["file"], recipes / patch["transport"]["file"])
    report = {
        "schema": 1, "status": "qualified-local-v12-cygwin-w32api-interlocked-successor",
        "target": "aarch64-pc-cygwin", "source": stage["source"],
        "sourceLock": ref(recipes / "source-lock.json"), "sdkProvenance": stage["sdkProvenance"],
        "sdkFullInventory": stage["sdkFullInventory"], "sourceOverlayReceipt": stage["sourceOverlayReceipt"],
        "existingAbiOverlay": stage["previousCygwinABIOverlay"],
        "cohort": str(root / "cohort"), "include": str(root / "cohort/include"),
        "header": ref(root / "cohort/include/psdk_inc/intrin-impl.h"),
        "manifest": ref(root / "cohort/manifest.json"), "files": len(manifest["files"]),
        "changedFiles": manifest["changedFiles"],
        "proof": {"publicCodegenAndNative": ref(root / "native-controls-final/result.json"),
                  "peImports": ref(root / "native-controls-final/pe-identities.json"),
                  "overlayControls": ref(args.overlay_proof)},
        "publicFixture": proof["publicFixture"], "baselineCodegen": proof["codegen"]["baseline"],
        "patchedCodegen": proof["codegen"]["patched"], "x64Control": proof["x64Control"],
        "runtime": proof["runtime"],
        "consumerSelection": proof["headerSelection"],
        "consumerBoundary": "Use the exact measured -isysroot COHORT header-only selection with root06's native MSYS-target compiler, or install the locked overlay into a NEW complete SDK's normal w32api location. Rebuild consumers into explicit new identities; no previous package is relabeled.",
        "limits": "Separate from the sealed 70d63 native MinGW header packet. No root06/907/compiler/Perl/OpenSSL modification or rebuild, no forced intrinsic macros in ARM public-API probes, no weak-memory stress or native x64 execution claim, and no remote publication."
    }
    (out / "handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = {p.relative_to(out).as_posix(): {"sha256": ref(p)["sha256"], "bytes": p.stat().st_size}
             for p in out.rglob("*") if p.is_file()}
    out.with_name(out.name + ".manifest.json").write_text(
        json.dumps({"schema": 1, "files": files}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "handoff.json")


if __name__ == "__main__":
    main()
