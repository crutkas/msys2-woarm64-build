"""Create only the fresh, private exit-provenance experiment input tree."""

import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(r"C:\ag-exit-e138-01")
SUPPORT = Path(r"C:\ag-e138920f\consumer-tools-03")
DRIVER = Path(r"C:\ag-e138920f\native-test-driver-02")
TC = Path(r"C:\ag-e138920f\tc-cpp-guard-01")
WIN_TC = Path(r"C:\ap06-2160\h1")
SOURCE = Path(r"\\wsl.localhost\Ubuntu\root\arm64-vnext-20260905\runtime\ucontext-20260907-03")
LOCKS = {
    str(DRIVER.with_suffix(".manifest.json")): "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa",
    r"C:\ap06-2160\parallel-v1\engine.json": "9e87d9c2b7235363ef14f407945078a1488bdca3bc8b3ef15fa26bbc0559f985",
    str(SUPPORT.with_suffix(".json")): "c237262f0e4bda779d25c8831a307b52dd5f02d14f57edaab6abdd184954032d",
    r"C:\Program Files\Python314-arm64\python.exe": "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29",
    str(TC.with_suffix(".copy.json")): "ed4fa0a4844ee05deca009dc9346320d701ae93cd9f299dc0185a5358001d41c",
    str(WIN_TC.with_name("h1-manifest.json")): "80e5dd2079f540bb1c0ee448ce27d211c8e3608b1f9e690edbd0c628b88f7739",
    r"C:\ag-e138920f\tcl-msys-api-03\result.json": "aefc02298614559c73aab69bfe790a31cf4b5cec11158b70b402e38d519ebacc",
    str(SOURCE / "source.SHA256SUMS"): "577aeab7449171c0edb092ccb019a8ee6b96c492c518e9395c396a73bbd14737",
    str(TC / r"share\toolchain\identities\runtime-cohort-receipt.json"): "92f0f896b3351b363e1e22225693ff37748fcb3476ad7dd6904a12001523896a",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def main():
    if ROOT.exists():
        raise RuntimeError("Experiment requires a fresh C:\\ag-exit-e138-01")
    for path, expected in LOCKS.items():
        if digest(path) != expected:
            raise RuntimeError(f"Locked input changed: {path}")
    ROOT.mkdir()
    records = []

    def copy(source, target, expected):
        source, target = Path(source), Path(target)
        before = digest(source)
        if before != expected:
            raise RuntimeError(f"Input mismatch: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        copied, after = digest(target), digest(source)
        records.append({"source": str(source), "copy": str(target),
                        "before": before, "copied": copied, "after": after})
        if copied != before or after != before:
            raise RuntimeError(f"Copy identity changed: {source}")

    for number, (path, expected) in enumerate(LOCKS.items()):
        if Path(path).suffix != ".exe":
            copy(path, ROOT / "locks" / f"{number:02d}-{Path(path).name}", expected)
    support_manifest = json.loads(SUPPORT.with_suffix(".json").read_text())
    for row in support_manifest["files"]:
        copy(SUPPORT / row["path"], ROOT / "support" / row["path"], row["sha256"])
    driver_manifest = json.loads(DRIVER.with_suffix(".manifest.json").read_text())
    for name, row in driver_manifest["files"].items():
        copy(DRIVER / name, ROOT / "driver" / name, row["sha256"])
    copy(DRIVER.with_suffix(".manifest.json"), ROOT / "driver.manifest.json",
         LOCKS[str(DRIVER.with_suffix(".manifest.json"))])
    runtime_manifest = json.loads(Path(r"C:\ag-e138920f\tcl-msys-api-03\result.json").read_text())
    runtime = Path(r"C:\ag-e138920f\tcl-msys-api-03\relocated")
    for name, row in runtime_manifest["stage_files"].items():
        copy(runtime / name, ROOT / "runtime" / name, row["sha256"])
    source_manifest = {}
    for line in (SOURCE / "source.SHA256SUMS").read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        source_manifest[name.lstrip("*").removeprefix("./")] = sha
    for name in (
        "winsup/cygwin/pinfo.cc", "winsup/cygwin/local_includes/pinfo.h",
        "winsup/cygwin/local_includes/child_info.h", "winsup/cygwin/local_includes/ntdll.h",
        "winsup/cygwin/dcrt0.cc", "winsup/cygwin/spawn.cc", "winsup/cygwin/sigproc.cc",
        "winsup/cygwin/include/cygwin/wait.h",
    ):
        copy(SOURCE / "source" / name, ROOT / "source-lock" / name, source_manifest[name])
    child_header = SOURCE / r"build\winsup\cygwin\child_info_magic.h"
    copy(child_header, ROOT / "source-lock" / child_header.name,
         "9c9b753f06e063b12ab6326c19544f84f21a0a38c176a1a3fd319ac188204ce6")
    win_manifest = json.loads(WIN_TC.with_name("h1-manifest.json").read_text())
    for row in win_manifest["Files"]:
        if row["Path"] in (r"aarch64-w64-mingw32\include\winnt.h",
                           r"aarch64-w64-mingw32\include\minwinbase.h",
                           r"aarch64-w64-mingw32\include\winternl.h"):
            copy(WIN_TC / row["Path"], ROOT / "windows-abi" / Path(row["Path"]).name, row["SHA256"])
    tool_inputs = {}
    for tree, manifest, rows in (
        (TC, TC.with_suffix(".copy.json"), None),
        (WIN_TC, WIN_TC.with_name("h1-manifest.json"), win_manifest["Files"]),
    ):
        expected = ({r["Path"]: r["SHA256"] for r in rows} if rows is not None else
                    {name: row["sha256"] for name, row in json.loads(manifest.read_text())["files"].items()})
        for name, sha in expected.items():
            actual = digest(tree / name)
            if actual != sha:
                raise RuntimeError(f"Toolchain input mismatch: {tree / name}")
            tool_inputs[str(tree / name)] = sha
    write_json(ROOT / "inputs.json", {"schema": 1, "status": "private-input-copy-only",
               "locks": LOCKS, "copies": records, "tool_inputs_before": tool_inputs,
               "host": "native Windows ARM64", "msys_target": "aarch64-pc-cygwin LP64",
               "windows_control_target": "aarch64-w64-mingw32", "full_cpp_qualified": False})
    print(json.dumps({"copied": len(records), "tool_inputs": len(tool_inputs), "root": str(ROOT)}))


if __name__ == "__main__":
    main()
