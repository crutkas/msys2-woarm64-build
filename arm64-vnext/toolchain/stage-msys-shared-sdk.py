#!/usr/bin/env python3
"""Create an independent SDK with the exact final shared runtime/header cohorts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): {"sha256": sha(p), "size": p.stat().st_size}
            for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--unwind", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, unwind = args.base.resolve(strict=True), args.unwind.resolve(strict=True)
    original = base / "sdk"
    cpp = base / "dev-raw-cxx" / "usr"
    gcc = unwind / "dev" / "usr"
    version = Path("lib/gcc/aarch64-pc-cygwin/15.0.1")
    replacements = [
        (gcc / "bin/msys-gcc_s-seh-1.dll", Path("bin/msys-gcc_s-seh-1.dll")),
        (gcc / "lib/libgcc_s.dll.a", version / "libgcc_s.dll.a"),
        (gcc / version / "libgcc.a", version / "libgcc.a"),
        (gcc / version / "libgcc_eh.a", version / "libgcc_eh.a"),
        (cpp / "bin/msys-stdc++-6.dll", Path("bin/msys-stdc++-6.dll")),
        (cpp / version / "libstdc++.dll.a", Path("aarch64-pc-cygwin/lib/libstdc++.dll.a")),
        (cpp / version / "libstdc++.a", Path("aarch64-pc-cygwin/lib/libstdc++.a")),
        (cpp / version / "libsupc++.a", Path("aarch64-pc-cygwin/lib/libsupc++.a")),
        (base / "dev/usr/lib/libgomp.spec", version / "libgomp.spec"),
        (base / "dev/usr/lib/libgomp.a", Path("aarch64-pc-cygwin/lib/libgomp.a")),
        (base / "dev/usr/lib/libatomic.a", Path("aarch64-pc-cygwin/lib/libatomic.a")),
        (base / "dev/usr" / version / "include/acc_prof.h", version / "include/acc_prof.h"),
    ]
    headers = cpp / version / "include/c++"
    if not (headers / "aarch64-pc-cygwin/bits/c++config.h").is_file():
        raise ValueError("Missing new configured C++ header closure")
    replacements.extend((p, Path("aarch64-pc-cygwin/include/c++/15.0.1") / p.relative_to(headers))
                        for p in headers.rglob("*") if p.is_file())
    for source, _ in replacements:
        if not source.is_file() or not source.stat().st_size:
            raise ValueError(f"Missing actual installed input: {source}")
    before = inventory(original)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    sdk = out / "sdk"
    shutil.copytree(original, sdk, copy_function=shutil.copy2)
    if inventory(sdk) != before:
        raise ValueError("Copied SDK does not match its complete input inventory")
    changes = []
    for source, relative in replacements:
        target = sdk / relative
        previous = sha(target) if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changes.append({"source": str(source), "path": relative.as_posix(),
                        "before": previous, "after": sha(target)})
    if inventory(original) != before:
        raise ValueError("Original producer SDK changed during staging")
    after = inventory(sdk)
    actual_changes = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    if not actual_changes.issubset({row["path"] for row in changes}):
        raise ValueError("Unaccounted SDK changes")
    report = {"schema": 1, "status": "shared-runtime-sdk-staged-awaiting-native-qualification",
              "base": str(original), "source_base_files": before,
              "changes": changes, "files": after, "unwind_epoch": str(unwind),
              "compiler_frontends_changed": False, "runtime_header_crt_changed": False}
    (out / "inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(out / "inputs.json")


if __name__ == "__main__":
    main()
