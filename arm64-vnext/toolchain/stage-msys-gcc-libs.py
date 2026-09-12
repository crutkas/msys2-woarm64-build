#!/usr/bin/env python3
"""Split only genuinely installed GCC runtime payload for the provider packager."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unwind", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    dev = root / "dev"
    args.output.mkdir(parents=True, exist_ok=False)
    stage = args.output.resolve()
    expected = ["msys-gcc_s-seh-1.dll", "msys-stdc++-6.dll", "msys-gomp-1.dll", "msys-atomic-1.dll"]
    dlls = [args.unwind.resolve(strict=True) / "dev/usr/bin/msys-gcc_s-seh-1.dll",
            root / "dev-raw-cxx/usr/bin/msys-stdc++-6.dll",
            dev / "usr/bin/msys-gomp-1.dll", dev / "usr/bin/msys-atomic-1.dll"]
    if (dev / "usr/bin/msys-quadmath-0.dll").exists():
        dlls.append(dev / "usr/bin/msys-quadmath-0.dll")
    if any(not path.is_file() or not path.stat().st_size for path in dlls):
        raise ValueError("Required real installed shared runtime is missing")
    actual = {path.name for path in dlls}
    if not set(expected).issubset(actual) or actual - set(expected) - {"msys-quadmath-0.dll"}:
        raise ValueError(f"Unexpected runtime DLL surface: {actual}")
    outputs = []
    for source in dlls:
        target = stage / "usr" / "bin" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        outputs.append({"path": str(target), "sha256": sha(target), "kind": "runtime-dll", "soname": source.name})
    for folder, kind, extension in (("locale", "locale", "*.mo"), ("info", "info", "*.info*")):
        directory = dev / "usr" / "share" / folder
        if directory.exists():
            for source in directory.rglob(extension):
                target = stage / source.relative_to(dev)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                outputs.append({"path": str(target), "sha256": sha(target), "kind": kind})
    licenses = stage / "usr" / "share" / "licenses" / "gcc-libs"
    licenses.mkdir(parents=True)
    for source_name, name in (("COPYING.RUNTIME", "RUNTIME.LIBRARY.EXCEPTION"),
                              ("COPYING3", "GPL-3.0"), ("COPYING3.LIB", "LGPL-3.0")):
        source = root / "source" / source_name
        target = licenses / name
        shutil.copy2(source, target)
        outputs.append({"path": str(target), "sha256": sha(target), "kind": "license"})
    files = {p.relative_to(stage).as_posix(): {"sha256": sha(p), "size": p.stat().st_size}
             for p in stage.rglob("*") if p.is_file()}
    manifest = stage.with_name(stage.name + ".manifest.json")
    if manifest.exists():
        raise ValueError("Never replace a published runtime manifest")
    manifest.write_text(json.dumps({
        "schema": 1, "status": "gcc-libs-runtime-payload-awaiting-producer-qualification",
        "packageCandidate": {"name": "gcc-libs", "version": "15.0.1-1", "target": "aarch64-pc-cygwin"},
        "stage": str(stage), "files": files, "outputs": outputs,
        "development_output": str(dev / "usr" / "lib"),
        "ownership": "Runtime DLLs/locales/info/licenses only; generated import/static libraries and headers remain a separate devel/producer export."
    }, indent=2) + "\n")
    print(manifest)


if __name__ == "__main__":
    main()
