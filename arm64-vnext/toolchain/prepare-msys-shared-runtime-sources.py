#!/usr/bin/env python3
"""Prepare pinned target-library sources, without rebuilding compiler frontends."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess

RECIPE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency", required=True, type=Path)
    parser.add_argument("--generated-gcc", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    lock = runpy.run_path(str(RECIPE / "source-lock.py"))["load_lock"](RECIPE)
    pin = lock["sources"]["gcc"]["revision"]
    source = args.dependency.resolve(strict=True)
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != pin:
        raise ValueError("GCC dependency revision differs")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    tree = out / "source"
    tree.mkdir()
    archive = out / "pinned-gcc.tar"
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar",
                    f"--output={archive}", pin], check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(tree)], check=True)
    applied = []
    for patch in lock["sources"]["gcc"]["patches"]:
        path = RECIPE / patch["file"]
        subprocess.run(["git", "-C", str(tree), "apply", "--check", str(path)], check=True)
        subprocess.run(["git", "-C", str(tree), "apply", str(path)], check=True)
        applied.append(patch)
    # Apply the same target DLL prefix policy as the pinned MSYS2 gcc recipe,
    # only in the libraries produced here. Keep names correct at link time;
    # renaming a DLL afterward would leave stale import descriptors.
    changed = []
    delta = []
    for relative in ["libtool.m4"] + [
            name + "/configure" for name in ("libstdc++-v3", "libgomp", "libatomic", "libquadmath", "libvtv")]:
        path = tree / relative
        before = path.read_bytes()
        old = b"s/^lib/cyg/"
        if old not in before:
            raise ValueError(f"Expected upstream Cygwin soname policy in {relative}")
        path.write_bytes(before.replace(old, b"s/^lib/msys-/"))
        delta.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),
                                         path.read_text().splitlines(keepends=True),
                                         fromfile="a/" + relative, tofile="b/" + relative))
        changed.append({"path": relative, "before": hashlib.sha256(before).hexdigest(), "after": sha(path)})
    path = tree / "libgcc" / "config" / "i386" / "t-cygwin"
    before = path.read_bytes()
    if before.count(b"SHLIB_LC = -lcygwin") != 1 or before.count(b"SHLIB_SONAME = cyggcc_s") != 1:
        raise ValueError("Unexpected libgcc Windows ABI naming")
    path.write_bytes(before.replace(b"SHLIB_LC = -lcygwin", b"SHLIB_LC = -lmsys-2.0")
                     .replace(b"SHLIB_SONAME = cyggcc_s", b"SHLIB_SONAME = msys-gcc_s"))
    delta.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),
                                     path.read_text().splitlines(keepends=True),
                                     fromfile="a/libgcc/config/i386/t-cygwin",
                                     tofile="b/libgcc/config/i386/t-cygwin"))
    changed.append({"path": "libgcc/config/i386/t-cygwin",
                    "before": hashlib.sha256(before).hexdigest(), "after": sha(path)})
    patch = out / "gcc-msys-shared-runtime-names.patch"
    patch.write_text("".join(delta), encoding="utf-8", newline="\n")
    generated = out / "generated-gcc"
    generated.mkdir()
    for path in args.generated_gcc.glob("*.h"):
        shutil.copy2(path, generated)
    shutil.copy2(args.generated_gcc / "libgcc.mvars", generated)
    # GCC's top-level host Makefile normally creates these compiler metadata
    # files. They are not runtime object files and are retained by identity.
    for path in args.generated_gcc.glob("*.ver"):
        shutil.copy2(path, generated)
    report = {"schema": 1, "status": "pinned-runtime-library-sources-prepared",
              "gcc_revision": pin, "gcc_repository": lock["sources"]["gcc"]["repository"],
              "canonical_source_lock": sha(RECIPE / "source-lock.json"), "patches": applied,
              "msys_runtime_naming_changes": changed,
              "msys_runtime_patch": {"path": str(patch), "sha256": sha(patch)},
              "naming_reference": "msys2/MSYS2-packages@dbd17835da05daa9e70a0e16d01e97892928a157:gcc/0950,0951",
              "source_files": {p.relative_to(tree).as_posix(): sha(p)
                               for p in tree.rglob("*") if p.is_file()},
              "compiler_metadata_source": str(args.generated_gcc),
              "compiler_metadata": {p.name: sha(p) for p in generated.iterdir()},
              "limits": "GCC 15.0.1 sources, not upstream recipe's 15.3.0. Target libraries only, no source dependency writes."}
    (out / "sources.json").write_text(json.dumps(report, indent=2) + "\n")
    print(out / "sources.json")


if __name__ == "__main__":
    main()
