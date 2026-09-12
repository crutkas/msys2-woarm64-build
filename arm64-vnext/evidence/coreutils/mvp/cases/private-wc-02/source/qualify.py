"""Current-runtime, private-PATH evidence for the explicitly selected MVP utilities."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from pe_closure import Image, dependency_closure

ROOT = Path(r"C:\ag-exit-e138-01\coreutils-20260910-01")
OLD = Path(r"C:\ag-exit-e138-01\resume-20260909-01")
CORE = Path(r"C:\ag-coreutils-e138-01\coreutils-native-13")
UTILS = Path(r"C:\ag-utils-e138-01\native-utilities-06")
RUNTIME_BASE = Path(r"C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a\files\combined-runtime-20260911")
RUNTIME = RUNTIME_BASE / "native-01/usr/bin/msys-2.0.dll"
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
CORE_NAMES = "cat cp mkdir mv rm rmdir ln readlink pwd env uname dd wc sort uniq head tail cut tr sleep true false test stat touch chmod basename dirname tee printf expr install ls stty timeout realpath od".split()
EXTRA_NAMES = ["find", "xargs", "sed"]
LOCKS = {
    str(CORE / "stage-coreutils.sha256"): "ccef88dcf9d454a278c3beb0e1c8844e1cd3ff4f6b81dc54d56338b1f405b4ec",
    str(CORE / "build.log"): "3c8434c393ee9716816c938a98a127951dee307441f334c38e44e3816d8adc4a",
    str(UTILS / "native-bash-test-utilities.manifest.json"): "300bda77f05606c6f49390297695d0507d769b2dc527843c746b0f6e1b72c9aa",
    str(RUNTIME_BASE / "handoff/combined-runtime-handoff.json"): "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b",
    str(RUNTIME): RUNTIME_SHA,
    str(OLD / "driver.SHA256SUMS"): "b46ccab632b0ef2e29301e9118481188cf705c39d278f3e6d1ec12cf0bb6bd42",
    str(OLD / "handoff/debug_tree.py"): "ab73aaef5d52bc67dad6b8572bf0a63c67fa96f3575363c9ee5d993c4eb64762",
    r"C:\Program Files\Python314-arm64\python.exe": "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29",
    r"C:\ap11-native-provider-intake\gettext-runtime-relocatable-v2\handoff.json": "76e5b6701d4c1ad246a564db530e3406d9dc58a9e0af0be5f7a1fac03d7d5c4a",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def copy(source, target, expected, records, role):
    before = digest(source)
    if before != expected:
        raise ValueError(f"Input mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open("rb") as src, target.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    copied, after = digest(target), digest(source)
    if before != copied or before != after:
        raise ValueError(f"Copy changed: {source}")
    records.append({"source": str(source), "copy": str(target), "before": before,
                    "copied": copied, "after": after, "role": role})


def source_inventory(root):
    return {str(path.relative_to(root)): {"sha256": digest(path), "size": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()}


def operational_paths(path):
    image = Image(path)
    records = []
    for section in image.sections:
        data = image.data[section["raw"]:section["raw"] + section["raw_size"]]
        strings = re.findall(rb"[ -~]{8,}", data)
        for raw in strings:
            lower = raw.lower()
            if not any(value in lower for value in
                       (b"ag-coreutils", b"ag-utils", b"ag-bash", b"host-bootstrap",
                        b"/root/", b"\\users\\", b"/share/locale", b"/var/", b"locatedb")):
                continue
            text = raw.decode("ascii")
            debug = section["name"].startswith(".debug")
            assertion = bool(re.search(r"\.(?:c|h|cc|cpp)$", text))
            canonical = text.startswith(("/usr/", "/var/", "/etc/")) and b"ag-" not in lower
            role = "debug-source-path" if debug else "assertion-source-path" if assertion else "canonical-runtime-path" if canonical else "operational-path-review"
            records.append({"section": section["name"], "value": text, "classification": role})
    return records


def prepare():
    for path, sha in LOCKS.items():
        if digest(path) != sha:
            raise ValueError(f"Locked input changed: {path}")
    ROOT.mkdir(exist_ok=False)
    records, missing, programs = [], [], []
    for index, (path, sha) in enumerate(LOCKS.items()):
        if Path(path).suffix not in (".exe", ".dll"):
            copy(path, ROOT / "input-receipts" / f"{index:02d}-{Path(path).name}", sha, records, "source-receipt")
    manifest = load(UTILS / "native-bash-test-utilities.manifest.json")
    core_manifest = {}
    for line in (CORE / "stage-coreutils.sha256").read_text().splitlines():
        sha, relative = line.split(maxsplit=1)
        core_manifest[relative] = sha
    for name in CORE_NAMES + EXTRA_NAMES:
        relative = f"usr/bin/{name}.exe"
        source = (CORE / "stage/coreutils" if name in CORE_NAMES else UTILS / "stage") / relative
        if not source.is_file() or relative not in manifest["files"]:
            missing.append(name)
            continue
        sha = manifest["files"][relative]["sha256"]
        if name in CORE_NAMES and core_manifest.get(relative) != sha:
            raise ValueError(f"Assembly candidate is not current coreutils stage: {name}")
        copy(source, ROOT / "private" / relative, sha, records, "coreutils" if name in CORE_NAMES else "extra")
        image = Image(ROOT / "private" / relative)
        programs.append({"name": name, "package": "coreutils" if name in CORE_NAMES else "findutils" if name in ("find", "xargs") else "sed",
                         **image.summary(), "imports": image.imports(),
                         "path_strings": operational_paths(ROOT / "private" / relative)})
    private_bin = ROOT / "private/usr/bin"
    dependency_sources = [
        (RUNTIME, "msys-2.0.dll", RUNTIME_SHA, "current-runtime"),
        (Path(r"C:\ag-bash-e138-01\gettext-runtime-relocatable-03\stage\usr\bin\msys-intl-8.dll"),
         "msys-intl-8.dll", "44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c", "current-gettext-dependency"),
        (Path(r"C:\ag-bash-e138-01\iconv-full-recovery-02\stage\usr\bin\msys-iconv-2.dll"),
         "msys-iconv-2.dll", "86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215", "current-iconv-dependency"),
        (UTILS / "stage/usr/bin/msys-gmp-10.dll", "msys-gmp-10.dll",
         manifest["files"]["usr/bin/msys-gmp-10.dll"]["sha256"], "admitted-gmp-dependency"),
        (UTILS / "stage/usr/bin/bash.exe", "bash.exe",
         "0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c", "test-harness-only"),
    ]
    for source, name, sha, role in dependency_sources:
        copy(source, private_bin / name, sha, records, role)
    copy(OLD / "baseline/etc/fstab", ROOT / "private/etc/fstab",
         "387ca1e86c1a18a143eb077ca194ad44c0a2faf98795a0d437f2d210d5a6df18", records, "runtime-configuration")
    (ROOT / "private/tmp").mkdir()
    (ROOT / "private/home").mkdir()
    for name in ("bounded_process.py", "native_job_runner.py", "sources.py"):
        expected = next(row["copied"] for row in load(OLD / "inputs.json")["copies"]
                        if row["copy"] == str(OLD / "support" / name))
        copy(OLD / "support" / name, ROOT / "support" / name, expected, records, "sealed-helper")
    for line in (OLD / "driver.SHA256SUMS").read_text().splitlines():
        sha, name = line.split()
        copy(OLD / "driver" / name, ROOT / "driver" / name, sha, records, "sealed-observer")
    for name, sha in (("windows-abi.json", "6f57ce24ccbeb751addb7a8f2550ed22ce93b12ddf8d069f296d564b85873e9e"),
                      ("bootstrap-lock.json", "7d26c79265871a88774224de4d424c217555d04beb661756506251ebc3d18d00")):
        copy(OLD / name, ROOT / name, sha, records, "sealed-debug-abi")
    copy(CORE / "source/coreutils-8.32/COPYING", ROOT / "licenses/coreutils/COPYING",
         digest(CORE / "source/coreutils-8.32/COPYING"), records, "license")
    write(ROOT / "coreutils-source-inventory.json", source_inventory(CORE / "source/coreutils-8.32"))
    write(ROOT / "inputs.json", {"schema": 1, "locks": LOCKS, "copies": records,
          "core_names": CORE_NAMES, "extra_names": EXTRA_NAMES, "missing": missing, "programs": programs,
          "core_source_inventory_sha256": digest(ROOT / "coreutils-source-inventory.json"),
          "prior_suite": {"PASS": 48, "FAIL": 41, "SKIP": 23, "ERROR": 4, "completed": False,
                          "log": str(CORE / "build.log"), "sha256": LOCKS[str(CORE / "build.log")]},
          "not_admitted": True, "full_package_qualified": False})
    print(json.dumps({"core_programs": len(CORE_NAMES), "extra_programs": len(EXTRA_NAMES),
                      "present": len(programs), "missing": missing, "root": str(ROOT)}))


def scan(label, expand_system_delay):
    inputs = load(ROOT / "inputs.json")
    for row in inputs["copies"]:
        if digest(row["copy"]) != row["copied"] or digest(row["source"]) != row["before"]:
            raise ValueError(f"Source or copied input changed: {row['source']}")
    private = ROOT / "private/usr/bin"
    images = sorted(private.glob("*.exe")) + sorted(private.glob("*.dll"))
    result = dependency_closure(images, private, Path(os.environ["SystemRoot"]) / "System32", expand_system_delay)
    result["shipped_programs"] = inputs["programs"]
    result["missing_required"] = inputs["missing"]
    write(ROOT / f"closure-{label}.json", result)
    print(json.dumps({"images": len(result["images"]), "edges": len(result["edges"]),
                      "failures": len(result["failures"]), "details": result["failures"][:8]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "scan"))
    parser.add_argument("--label", default="02")
    parser.add_argument("--required-loader-closure", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        scan(args.label, not args.required_loader_closure)
