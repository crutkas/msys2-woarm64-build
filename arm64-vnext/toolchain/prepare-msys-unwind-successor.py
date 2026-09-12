#!/usr/bin/env python3
"""Copy the existing libgcc object cache and source closure into a new epoch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

RECIPE = Path(__file__).resolve().parent
BEFORE = "1980a757de9b1798fd659d6bda39906c7e10c7513d9dec0ecc6094c2a8ab5ef4"
AFTER = "acfad2dc93fb97eca6e054a3d1654d5cba40eb89d3881bdf9440605e0999f2b8"
PATCH = "ac5811c62b8f12e8cf20d92a8c650fe56ff0b9490298b39523e06b58535adff0"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    source = base / "source" / "libgcc" / "unwind-seh.c"
    patch = RECIPE / "libgcc-arm64-unwind-context.patch"
    if sha(source) != BEFORE or sha(patch) != PATCH:
        raise ValueError("Exact qualified source/patch identities differ")
    metadata = ("gcc/BASE-VER", "gcc/DATESTAMP", "gcc/DEV-PHASE",
                "install-sh", "mkinstalldirs", "move-if-change", "config.sub", "config.guess")
    for name in metadata:
        if not (base / "source" / name).is_file():
            raise ValueError(f"Missing genuine build metadata: {name}")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    out = args.output.resolve()
    if out == base or out.is_relative_to(base) or (out / "receipts" / "inputs.json").exists():
        raise ValueError("Use a distinct, unpublished successor epoch")
    copied = {}

    def copy_input(original):
        relative = original.relative_to(base)
        target = out / relative
        digest = sha(original)
        if target.exists():
            permitted = {digest}
            if relative.as_posix() == "source/libgcc/unwind-seh.c":
                permitted.add(AFTER)
            if not args.resume or sha(target) not in permitted:
                raise ValueError(f"Existing successor input differs: {relative}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            if sha(target) != digest:
                raise ValueError(f"Input changed while copied: {relative}")
        copied[relative.as_posix()] = digest

    directories = ("source/libgcc", "source/include", "source/gcc/config",
                   "build/gcc", "build/aarch64-pc-cygwin/libgcc")
    for directory in directories:
        original = base / directory
        (out / directory).mkdir(parents=True, exist_ok=True)
        for file in original.rglob("*"):
            if file.is_file():
                copy_input(file)
    for original in (base / "source" / "gcc").glob("*.h"):
        copy_input(original)
    for name in metadata:
        original = base / "source" / name
        if not original.is_file():
            raise ValueError(f"Missing genuine build input: {original}")
        copy_input(original)
    actual = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    if actual != set(copied):
        raise ValueError("Unexpected files in unpublished successor source/cache closure")
    if sha(out / "source" / "libgcc" / "unwind-seh.c") == BEFORE:
        command = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                   "-C", str(out / "source"), "apply"]
        subprocess.run(command + ["--check", str(patch)], check=True)
        subprocess.run(command + [str(patch)], check=True)
    if sha(out / "source" / "libgcc" / "unwind-seh.c") != AFTER:
        raise ValueError("Patched libgcc source differs from the qualified source")
    for relative, digest in copied.items():
        if sha(base / relative) != digest:
            raise ValueError(f"Preserved producer input changed: {relative}")
    (out / "logs").mkdir()
    (out / "receipts").mkdir()
    report = {"schema": 1, "status": "private-libgcc-unwind-successor-prepared",
              "base": str(base), "output": str(out), "copied_inputs": copied,
              "source_before": BEFORE, "source_after": AFTER,
              "patch": {"path": str(patch), "sha256": PATCH},
              "source_lock": {"path": str(RECIPE / "source-lock.json"),
                              "sha256": sha(RECIPE / "source-lock.json")},
              "compiler_runtime_policy": "Use base native compiler and exact d70 trio read-only; no frontend/runtime/header rebuild."}
    (out / "receipts" / "inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(out / "receipts" / "inputs.json")


if __name__ == "__main__":
    main()
