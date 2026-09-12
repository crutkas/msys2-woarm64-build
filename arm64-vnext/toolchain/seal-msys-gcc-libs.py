#!/usr/bin/env python3
"""Seal actual qualified target-runtime payload for the separate package owner."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

RECIPE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "unwind", "sdk", "stage", "proof", "debug-proof", "package-recipe", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root, unwind, sdk = args.root.resolve(strict=True), args.unwind.resolve(strict=True), args.sdk.resolve(strict=True)
    stage = args.stage.resolve(strict=True)
    manifest_path = stage.with_name(stage.name + ".manifest.json")
    manifest, native, debug = load(manifest_path), load(args.proof), load(args.debug_proof)
    if native["status"] != "native-msys-shared-gcc-runtimes-qualified":
        raise ValueError("Ordinary shared-runtime qualification is missing")
    if debug["status"] != "native-shared-cpp-ordinary-debug-parity-qualified":
        raise ValueError("Actual shared-libgcc debugger qualification is missing")
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]):
        raise ValueError("Runtime payload file set differs")
    for relative, record in manifest["files"].items():
        if sha(stage / relative) != record["sha256"]:
            raise ValueError(f"Runtime payload changed: {relative}")
    sdk_record = load(sdk.parent / "inputs.json")
    sdk_actual = {p.relative_to(sdk).as_posix() for p in sdk.rglob("*") if p.is_file()}
    if sdk_actual != set(sdk_record["files"]):
        raise ValueError("Development SDK file set differs")
    for relative, record in sdk_record["files"].items():
        if sha(sdk / relative) != record["sha256"]:
            raise ValueError(f"Development SDK changed: {relative}")
    for entry in manifest["outputs"]:
        if entry["kind"] == "runtime-dll":
            filename = Path(entry["path"]).name
            if sha(sdk / "bin" / filename) != entry["sha256"] or sha(args.proof.parent / filename) != entry["sha256"]:
                raise ValueError(f"Runtime stage is not the qualified DLL cohort: {filename}")
    for name, digest in debug["files"].items():
        if sha(args.proof.parent / name) != digest:
            raise ValueError("Debugger and ordinary proof fixtures differ")
    if debug["ordinary_proof"]["sha256"] != sha(args.proof):
        raise ValueError("Debugger proof references another ordinary result")
    if sha(args.package_recipe) != "55b022218c2519bfa1ca50224a2cd7e03dec0f9feada54c19354f8ef3408a1c8":
        raise ValueError("Pinned package ownership recipe differs")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    sources_dir = out / "source"
    sources_dir.mkdir()
    lock = load(RECIPE / "source-lock.json")
    patches = []
    for patch in lock["sources"]["gcc"]["patches"]:
        source = RECIPE / patch["file"]
        if sha(source) != patch["sha256"]:
            raise ValueError("Canonical source patch changed")
        shutil.copy2(source, sources_dir / source.name)
        patches.append(reference(sources_dir / source.name))
    naming = root / "receipts/gcc-msys-shared-runtime-names.patch"
    shutil.copy2(naming, sources_dir / naming.name)
    patches.append(reference(sources_dir / naming.name))
    shutil.copy2(RECIPE / "source-lock.json", sources_dir / "source-lock.json")
    shutil.copy2(args.package_recipe, sources_dir / "upstream-PKGBUILD")
    recipes = out / "recipes"
    recipes.mkdir()
    for name in ("prepare-msys-shared-runtime-sources.py", "prepare-msys-shared-runtime-inputs.py",
                 "prepare-msys-unwind-successor.py", "build-msys-shared-runtimes.sh",
                 "run-msys-library-stage.py", "stage-msys-shared-sdk.py",
                 "build-msys-runtime-docs.sh", "test-shared-msys-runtimes.py",
                 "prepare-msys-runtime-debug.py", "test-msys-shared-debug.py",
                 "stage-msys-gcc-libs.py", "seal-msys-gcc-libs.py", "source-lock.py",
                 "activate-msys-shared-libgcc.py", "activate-msys-runtime-library.py",
                 "native-loaded-modules.py", "test-msys-ucontext.py", "Get-ToolchainPeIdentity.ps1"):
        shutil.copy2(RECIPE / name, recipes / name)
    for source in (RECIPE / "probes").glob("shared-gcc-*"):
        shutil.copy2(source, recipes / source.name)
    runtime = {"runtimeSha256": sha(sdk / "bin/msys-2.0.dll"),
               "importLibrarySha256": sha(sdk / "aarch64-pc-cygwin/lib/libmsys-2.0.a"),
               "crt0Sha256": sha(sdk / "aarch64-pc-cygwin/lib/crt0.o")}
    expected = {"runtimeSha256": "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d",
                "importLibrarySha256": "fac7ee56bb99f1c8aa06fd04c164f3b95e71a2fe3168e0b55db5fa02275bf32c",
                "crt0Sha256": "3f1d5aed644750ca496008c6c2bc5206da144da3e633065e0a41d0ef07dfeb0e"}
    if runtime != expected:
        raise ValueError("The qualified coherent runtime pair changed")
    outputs = list(manifest["outputs"])
    for library in ("gcc_s", "stdc++", "gomp", "atomic"):
        imports = list(sdk.rglob("lib" + library + ".dll.a"))
        if len(imports) != 1:
            raise ValueError(f"Ambiguous development import surface: {library}")
        outputs.append({**reference(imports[0]), "kind": "import-library", "importName": "lib" + library + ".dll.a"})
    report = {
        "schema": 1, "status": "native-msys-gcc-libs-producer-export-qualified",
        "packageCandidate": {"name": "gcc-libs", "version": "15.0.1-1", "target": "aarch64-pc-cygwin"},
        "source": {"repository": lock["sources"]["gcc"]["repository"], "commit": lock["sources"]["gcc"]["revision"],
                   "pinnedRecipe": {"repository": "https://github.com/msys2/MSYS2-packages.git",
                                    "commit": "dbd17835da05daa9e70a0e16d01e97892928a157", "path": "gcc/PKGBUILD",
                                    "sha256": sha(sources_dir / "upstream-PKGBUILD")},
                   "patches": patches, "sourceInventory": reference(root / "sources.json"),
                   "unwindSuccessor": reference(unwind / "receipts/inputs.json"),
                   "effectiveSourceOverride": {"relativePath": "libgcc/unwind-seh.c",
                                               **reference(unwind / "source/libgcc/unwind-seh.c")},
                   "scope": "Pinned GCC 15.0.1 target libraries; recipe 15.3.0 supplies ownership policy only."},
        "runtimeCohort": runtime,
        "stage": {"path": str(stage), "manifest": reference(manifest_path), "files": len(manifest["files"])},
        "development": {"path": str(sdk), "manifest": reference(sdk.parent / "inputs.json"),
                        "scope": "Separate full native development SDK export, not files owned by runtime gcc-libs package."},
        "outputs": outputs,
        "validation": {"nativeProcess": True, "hostArchitecture": "arm64", "targetTriple": "aarch64-pc-cygwin",
                       "normalLinkProof": reference(args.proof), "dynamicLoadProof": reference(args.proof),
                       "sharedDebuggerParityProof": reference(args.debug_proof),
                       "libgccExportABI": reference(unwind / "receipts/export-abi.json"),
                       "commandsResults": [
                           reference(root / "logs" / name) for name in (
                               "libgcc-build-03.json", "libgcc-install-04.json",
                               "libstdcxx-configure-raw-cxx-02.json", "libstdcxx-build-raw-cxx-02.json",
                               "libgomp-configure-02.json", "libgomp-build-02.json",
                               "libatomic-configure-02.json", "libatomic-build-01.json",
                               "libquadmath-configure-01.json")] + [
                           reference(unwind / "logs/libgcc-unwind-build-02.json")],
                       "scope": native["scope"], "compilerHost": "Native Windows ARM64 UCRT-hosted GCC; MSYS LP64 target libraries."},
        "documentation": {"host": "aarch64 Linux, existing makeinfo 7.1 and msgfmt 0.21",
                          "files": reference(root / "logs/docs/generated.sha256"),
                          "scope": "Host-only generation of genuine upstream info and PO catalogs, not native compiler evidence."},
        "unsupported": [
            {"component": "libquadmath", "reason": "Pinned target rejects __float128; real upstream feature compile disabled BUILD_LIBQUADMATH.",
             "sourceEvidence": reference(root / "source/libquadmath/configure.ac"),
             "configureEvidence": reference(root / "build/aarch64-pc-cygwin/libquadmath/config.log")},
            {"component": "libvtv", "reason": "Pinned configure.tgt does not support aarch64 Cygwin.",
             "sourceEvidence": reference(root / "source/libvtv/configure.tgt")},
            {"component": "named-non-C-libstdc++-locales", "reason": "Pinned generic locale backend only supports C facets; C runtime C.UTF-8 separately exercised. Catalogs do not enable NLS.",
             "sourceEvidence": reference(root / "source/libstdc++-v3/config/locale/generic/c_locale.cc")}
        ],
        "license": "LGPL-3.0-or-later AND GPL-3.0-or-later WITH GCC-exception-3.1",
        "limitations": "Producer export only. Packaging owner must perform archive/readback admission. No general exit-domain collector, whole GCC testsuite, MinGW runtime or full-distribution claim.",
    }
    (out / "handoff.json").write_text(json.dumps(report, indent=2) + "\n")
    inventory = {p.relative_to(out).as_posix(): {"sha256": sha(p), "size": p.stat().st_size}
                 for p in out.rglob("*") if p.is_file()}
    out.with_name(out.name + ".manifest.json").write_text(json.dumps({"schema": 1, "files": inventory}, indent=2) + "\n")
    print(out / "handoff.json")


if __name__ == "__main__":
    main()
