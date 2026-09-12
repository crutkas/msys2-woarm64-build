#!/usr/bin/env python3
"""Seal the local header-only successor, without publishing or replacing a prefix."""
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
    for name in ("root", "guard-proof", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    cohort = root / "cohort"
    native = load(root / "native-controls-final/result.json")
    applier = load(root / "applier-controls/result.json")
    guard = load(args.guard_proof)
    if native["status"] != "native-mingw-interlocked-header-cohort-qualified":
        raise ValueError("Native/code-generation qualification is incomplete")
    if applier["status"] != "frozen-interlocked-applier-controls-qualified" or not guard["passed"]:
        raise ValueError("Source/application controls are incomplete")
    stage = load(cohort / "stage.json")
    if ref(RECIPE / "source-lock.json")["sha256"] != stage["sourceLockSHA256"]:
        raise ValueError("The maintained lock changed after header staging")
    if native["stageReceipt"]["sha256"] != ref(cohort / "stage.json")["sha256"]:
        raise ValueError("Native proof used another cohort")
    verify = runpy.run_path(str(RECIPE / "test-mingw-interlocked-cohort.py"))["local_path"]
    manifest = load(cohort / "header-manifest.json")
    for directory, entries in ((cohort / "include", manifest["files"]),
                               (verify(manifest["baselineIncludeRoot"]), manifest["baselineFiles"])):
        actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        if actual != set(entries):
            raise ValueError("Header inventory changed")
        for name, entry in entries.items():
            if ref(directory / name)["sha256"] != entry["sha256"]:
                raise ValueError(f"Header identity changed: {name}")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    recipes = out / "recipes"
    recipes.mkdir()
    names = ("source-lock.json", "source-lock.py", "mingw-stages.sh", "bootstrap-cygwin.sh",
             "stage-mingw-interlocked-headers.py", "test-mingw-interlocked-cohort.py",
             "test-mingw-interlocked-applier.py", "seal-mingw-interlocked-cohort.py",
             "test-source-lock.py", "test-crt-source-guard.py",
             "test-msys-ucontext.py", "run-msys-library-stage.py", "README.md", ".gitattributes",
             "probes/interlocked-exchange-native.c")
    lock = load(RECIPE / "source-lock.json")
    for name in names:
        target = recipes / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RECIPE / name, target)
    for source in lock["sources"].values():
        for patch in source["patches"] + source.get("overlay_patches", []):
            shutil.copy2(RECIPE / patch["file"], recipes / patch["file"])
            if "transport" in patch:
                shutil.copy2(RECIPE / patch["transport"]["file"], recipes / patch["transport"]["file"])
    report = {
        "schema": 1, "status": "qualified-local-mingw-interlocked-header-successor",
        "source": stage["source"], "sourceLock": ref(recipes / "source-lock.json"),
        "orderedMinGWSourcePatches": stage["orderedPatches"],
        "producerReceipt": ref(root / "producer/handoff.json"),
        "includeRoot": str(cohort / "include"), "files": len(manifest["files"]),
        "manifest": ref(cohort / "header-manifest.json"), "stage": ref(cohort / "stage.json"),
        "changedFiles": manifest["changedFiles"], "header": ref(cohort / "include/psdk_inc/intrin-impl.h"),
        "proof": {"sourceGuard": ref(args.guard_proof), "frozenApplier": ref(root / "applier-controls/result.json"),
                  "nativeCodegenAndBehavior": ref(root / "native-controls-final/result.json")},
        "host": "Windows ARM64", "target": "aarch64-w64-mingw32",
        "semantics": "SEQ_CST exchange selects release-capable _acq_rel helpers; the old __sync_lock_test_and_set _sync helpers were acquire-only. Native behavior confirms exact old-value returns/new-value stores, not a weak-memory stress proof.",
        "consumerBoundary": "Select this includeRoot explicitly before the old native MinGW include root and rebuild affected consumers into a NEW package cohort. No header was copied into a qualified compiler prefix.",
        "unchanged": ["qualified compiler/runtime/OpenSSL prefixes and binaries",
                      "existing OpenSSL local MemoryBarrier", "old packages and receipts",
                      "v12 Cygwin w32api overlay", "PR11 published files and remote branch"],
        "scope": "Local recipe/header/code-generation integration only. No compiler build, runtime build, package relabeling, commit, push, PR, CI, authentication or settings changes for this task."
    }
    (out / "handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = {path.relative_to(out).as_posix(): {"sha256": ref(path)["sha256"], "bytes": path.stat().st_size}
             for path in out.rglob("*") if path.is_file()}
    out.with_name(out.name + ".manifest.json").write_text(
        json.dumps({"schema": 1, "files": files}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "handoff.json")


if __name__ == "__main__":
    main()
