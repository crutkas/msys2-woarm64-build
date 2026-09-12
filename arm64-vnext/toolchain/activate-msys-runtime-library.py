#!/usr/bin/env python3
"""Expose an actually installed target library in the owned build SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--library", choices=("stdc++", "gomp", "atomic", "quadmath"), required=True)
    parser.add_argument("--revision")
    parser.add_argument("--previous-receipt", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not (root / "receipts" / "shared-libgcc-sdk.json").is_file():
        parser.error("Activate the verified shared libgcc first")
    if args.revision and not re.fullmatch(r"[a-z0-9-]+", args.revision):
        parser.error("Use a simple versioned receipt suffix")
    if bool(args.revision) != bool(args.previous_receipt) or (args.revision and args.library != "stdc++"):
        parser.error("Only an explicit libstdc++ successor may replace the private build inputs")
    suffix = "-" + args.revision if args.revision else ""
    report = root / "receipts" / f"shared-{args.library}-sdk{suffix}.json"
    if report.exists():
        parser.error("This component is already activated")
    installed = root / ("dev-raw-cxx" if args.library == "stdc++" else "dev") / "usr"
    dlls = list((installed / "bin").glob(f"msys-{args.library}-*.dll"))
    if len(dlls) != 1:
        raise ValueError(f"Expected one genuinely installed {args.library} DLL: {dlls}")
    imports = list(installed.rglob(f"lib{args.library}.dll.a"))
    if len(imports) != 1:
        raise ValueError(f"Expected one genuinely installed import archive: {imports}")
    changes = []
    sources = [(dlls[0], root / "bootstrap" / "usr" / "bin" / dlls[0].name),
               (dlls[0], root / "sdk" / "bin" / dlls[0].name),
               (imports[0], root / "sdk" / "aarch64-pc-cygwin" / "lib" / imports[0].name)]
    if args.library == "gomp":
        sources.append((installed / "lib" / "libgomp.spec", root / "sdk" / "lib" / "gcc" /
                        "aarch64-pc-cygwin" / "15.0.1" / "libgomp.spec"))
    for filename in {"gomp": ("omp.h", "openacc.h", "acc_prof.h"), "quadmath": ("quadmath.h", "quadmath_weak.h")}.get(args.library, ()):
        candidates = list(installed.rglob(filename))
        if len(candidates) != 1:
            raise ValueError(f"Expected the installed public header {filename}")
        sources.append((candidates[0], root / "sdk" / "lib" / "gcc" / "aarch64-pc-cygwin" /
                        "15.0.1" / "include" / filename))
    if args.library == "stdc++":
        headers = installed / "lib" / "gcc" / "aarch64-pc-cygwin" / "15.0.1" / "include" / "c++"
        if not (headers / "aarch64-pc-cygwin" / "bits" / "c++config.h").is_file():
            raise ValueError("Missing the newly configured public C++ header closure")
        sources.extend((source, root / "sdk" / "aarch64-pc-cygwin" / "include" /
                        "c++" / "15.0.1" / source.relative_to(headers))
                       for source in headers.rglob("*") if source.is_file())
    previous = None
    if args.previous_receipt:
        previous = json.loads(args.previous_receipt.read_text())
        if previous["library"] != args.library:
            raise ValueError("Wrong predecessor component")
        for entry in previous["changes"]:
            path = Path(entry["path"])
            if not path.resolve().is_relative_to(root) or sha(path) != entry["sha256"]:
                raise ValueError("Predecessor private-library bytes have changed")
    for source, target in sources:
        if target.exists() and previous is None:
            if args.library == "stdc++" and target.suffix != ".dll" and sha(source) == sha(target):
                continue
            # C++ headers intentionally replace the input SDK's configured
            # header cohort; the DLL/import replacement needs a predecessor.
            if not (args.library == "stdc++" and target.is_relative_to(
                    root / "sdk" / "aarch64-pc-cygwin" / "include" / "c++")):
                raise ValueError(f"Additive library input already exists: {target}")
    backup = root / "receipts" / f"shared-{args.library}-sdk{suffix}-predecessor"
    backup.mkdir(exist_ok=False)
    for source, target in sources:
        before = None
        if target.exists():
            before = sha(target)
            preserved = backup / target.relative_to(root)
            preserved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, preserved)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changes.append({"source": str(source), "path": str(target), "sha256": sha(target), "before": before})
    report.write_text(json.dumps({"schema": 1, "status": "private-build-shared-library-enabled",
                                  "predecessor": {"path": str(args.previous_receipt),
                                                  "sha256": sha(args.previous_receipt)} if previous else None,
                                  "preserved_inputs": str(backup),
                                  "library": args.library, "changes": changes}, indent=2) + "\n")
    print(report)


if __name__ == "__main__":
    main()
