#!/usr/bin/env python3
"""Enable shared libgcc only in the current owned runtime build SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not (root / "inputs.json").is_file():
        parser.error("Expected a new owned shared-runtime build root")
    output = root / "receipts" / "shared-libgcc-sdk.json"
    if output.exists():
        parser.error("Shared libgcc activation already sealed")
    source = root / "build" / "aarch64-pc-cygwin" / "libgcc"
    runtime = source / "shlib" / "msys-gcc_s-seh-1.dll"
    shared_import = source / "shlib" / "libgcc_s.dll.a"
    for path in (runtime, shared_import, source / "libgcc.a", source / "libgcc_eh.a"):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Real built libgcc input missing: {path}")
    selected = root / "sdk" / "lib" / "gcc" / "aarch64-pc-cygwin" / "15.0.1"
    changes = []
    for path in (shared_import, source / "libgcc.a", source / "libgcc_eh.a"):
        target = selected / path.name
        before = digest(target) if target.exists() else None
        shutil.copy2(path, target)
        changes.append({"path": target.relative_to(root).as_posix(), "before": before, "after": digest(target)})
    for destination in (root / "bootstrap" / "usr" / "bin", root / "sdk" / "bin"):
        target = destination / runtime.name
        if target.exists():
            raise ValueError("Never overwrite an existing shared runtime")
        shutil.copy2(runtime, target)
        changes.append({"path": target.relative_to(root).as_posix(), "before": None, "after": digest(target)})
    specs = selected / "specs"
    text = specs.read_text(encoding="utf-8")
    pattern = r"(?m)^(\*libgcc:\n)([^\n]*)$"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1 or matches[0].group(2).strip() != "-lgcc":
        raise ValueError("Expected the declared static-only driver libgcc spec")
    shutil.copy2(specs, root / "receipts" / "specs-static-original")
    before = digest(specs)
    new = r"%{static|static-libgcc:-lgcc -lgcc_eh;:-lgcc_s -lgcc}"
    specs.write_text(re.sub(pattern, lambda m: m.group(1) + new, text), encoding="utf-8", newline="\n")
    changes.append({"path": specs.relative_to(root).as_posix(), "before": before, "after": digest(specs)})
    output.write_text(json.dumps({
        "schema": 1, "status": "private-build-sdk-shared-libgcc-enabled-not-package-admission",
        "root": str(root), "changes": changes,
        "source_dll": {"path": str(runtime), "sha256": digest(runtime)},
        "source_import": {"path": str(shared_import), "sha256": digest(shared_import)},
        "scope": "Real shared libgcc + import and static companions; normal driver spec chooses shared unless explicitly static. No frozen compiler prefix changed."
    }, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
