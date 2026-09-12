"""Seal native907 tool artifacts and exact evidence for independent intake."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path):
    return {"path": str(path), "sha256": sha(path), "size": path.stat().st_size}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--package", choices=("which", "dos2unix"), required=True)
    args = parser.parse_args()
    root, name = args.root, args.package
    base = root / name
    version = {"which": "2.25", "dos2unix": "7.5.7"}[name]
    destination = base / "delivery-01"
    if destination.exists():
        raise RuntimeError("Immutable delivery cannot be overwritten")
    package = load(base / "packages/packaging.json")
    readback = load(base / "package-readback.json")
    move = load(base / "actual-move.json")
    runtime = Path(move["After"])
    if Path(move["Before"]).exists() or not move["OldRootAbsent"]:
        raise RuntimeError("Old runtime root was not removed by the move")
    for item in package["payload"]:
        if sha(runtime / item["path"]) != item["sha256"]:
            raise RuntimeError("Moved package byte mismatch")
    phases = ("before02", "moved01") if name == "which" else ("before04", "moved01")
    for phase in phases:
        behavior = load(base / f"functional-{phase}/result.json")
        job = load(base / f"observed-functional-{phase}/native-job.json")
        if (not behavior["status"].endswith("-pass") or not all(case["passed"] for case in behavior["cases"])
                or not job["passed"] or job["unrelayed_high_exits"]):
            raise RuntimeError("Final behavior or process observation did not pass")
    spec = importlib.util.spec_from_file_location("existing_pe", root / "inputs/inspect-native-archive.py")
    pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pe)
    pending = [runtime / item["path"] for item in readback["pe"]]
    required = {"msys-2.0.dll": "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"}
    if name == "dos2unix":
        required.update({"msys-intl-8.dll": "44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c",
                         "msys-iconv-2.dll": "86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215"})
    nodes, edges, windows = {}, [], {}
    while pending:
        path = pending.pop()
        if str(path) in nodes:
            continue
        image = pe.pe(path.read_bytes())
        if image["machine"] != "0xAA64":
            raise RuntimeError("A payload or private DLL is not ordinary ARM64")
        nodes[str(path)] = {**bound(path), **image}
        for kind in ("imports", "delay_imports"):
            for imported in image[kind]:
                dll = imported["dll"].lower()
                if dll in required:
                    target = runtime / "usr/bin" / dll
                    if sha(target) != required[dll]:
                        raise RuntimeError("Private runtime/provider identity mismatch")
                    exports = pe.pe(target.read_bytes())["exports"]
                    for symbol in imported["symbols"]:
                        if not any(entry.get("name") == symbol["name"] if "name" in symbol else
                                   entry["ordinal"] == symbol["ordinal"] for entry in exports):
                            raise RuntimeError(f"Unsatisfied private IAT symbol: {dll} {symbol}")
                    pending.append(target)
                    scope = "private907"
                else:
                    target = Path(os.environ["SystemRoot"]) / "System32" / dll
                    if not target.is_file():
                        raise RuntimeError(f"Unresolved import: {dll}")
                    windows[dll] = bound(target)
                    scope = "Windows-System32"
                edges.append({"importer": str(path), "dll": dll, "target": str(target),
                              "scope": scope, "kind": kind, "symbol_count": len(imported["symbols"])})
    path_findings = []
    source_files = []
    with tarfile.open(root / "inputs" / f"{name}-{version}.tar.gz", "r:gz") as source:
        if name == "dos2unix":
            for member in source.getmembers():
                relative = member.name.partition("/")[2]
                if member.isfile() and (relative.endswith((".c", ".h", ".t")) or relative.startswith("test/")):
                    actual = base / "src" / f"{name}-{version}" / relative
                    original = hashlib.sha256(source.extractfile(member).read()).hexdigest()
                    if not actual.is_file() or sha(actual) != original:
                        raise RuntimeError(f"Original product source, test or expected fixture changed: {relative}")
                    source_files.append({"path": relative, "sha256": original})
        for finding in readback["private_path_hits"]:
            relative = finding["path"]
            source_name = Path(relative).name
            archive_name = f"{name}-{version}/{source_name}"
            if name != "which" or relative not in ("usr/share/info/which.info", "usr/share/man/man1/which.1"):
                raise RuntimeError("Unclassified private path in package")
            data = source.extractfile(archive_name).read()
            if hashlib.sha256(data).hexdigest() != sha(runtime / relative) or "/home/carlo/bin/q2" not in finding["context"]:
                raise RuntimeError("Documentation path was not the original upstream example")
            path_findings.append({**finding, "classification": "unchanged upstream documentation example, not a private build/runtime path"})
    mtree = gzip.decompress((base / "extracted/.MTREE").read_bytes()).decode()
    for item in readback["members"]:
        if item["path"] == ".MTREE":
            continue
        lines = [line for line in mtree.splitlines() if line.startswith("./" + item["path"] + " ")]
        expected_entry = ("link=" + item["link"] if item.get("type") == "symlink"
                          else "sha256digest=" + item["sha256"])
        if len(lines) != 1 or expected_entry not in lines[0]:
            raise RuntimeError("MTREE does not describe exact package bytes")
        if item.get("type") == "symlink" and "type=link" not in lines[0]:
            raise RuntimeError("Alias is not recorded as a link in MTREE")
    upstream = load(base / ("observed-check-01/native-job.json" if name == "which"
                            else "observed-check-04/native-job.json"))
    if not upstream["passed"] or upstream["parent_raw_exit"] or upstream["unrelayed_high_exits"]:
        raise RuntimeError("Authoritative original upstream check did not pass")
    if name == "dos2unix":
        log = (base / "observed-check-04/check.log").read_text()
        if "Files=9, Tests=174," not in log or "Result: PASS" not in log:
            raise RuntimeError("Original upstream suite is incomplete")
    destination.mkdir()
    for folder in ("packages", "source", "recipe", "maintained", "evidence"):
        (destination / folder).mkdir()
    original_archive = Path(package["package"])
    archive = destination / "packages" / original_archive.name
    shutil.copyfile(original_archive, archive)
    if sha(archive) != package["sha256"]:
        raise RuntimeError("Delivered archive differs from the exercised package")
    shutil.copyfile(root / "inputs" / f"{name}-{version}.tar.gz", destination / "source" / f"{name}-{version}.tar.gz")
    for path in (base / "recipe").iterdir():
        if path.is_file():
            shutil.copyfile(path, destination / "recipe" / path.name)
    if name == "which":
        shutil.copyfile(root / "inputs/msys2-allow-windows-mixed-absolute-paths.patch",
                        destination / "source/msys2-allow-windows-mixed-absolute-paths.patch")
    for path in (args.workspace / ".github/scripts/native-utilities").iterdir():
        if path.is_file():
            shutil.copyfile(path, destination / "maintained" / path.name)
    shutil.copyfile(args.workspace / ".github/scripts/less/invoke-private-command.ps1",
                    destination / "maintained/invoke-private-command.ps1")
    for filename in ("native-identity-helper.py", "inspect-native-archive.py", "bounded_process.py"):
        shutil.copyfile(root / "inputs" / filename, destination / "maintained" / filename)
    if name == "dos2unix":
        shutil.copyfile(args.workspace / "tests/native-utilities/native-utility-exec.c",
                        destination / "maintained/native-utility-exec.c")
    selected = [base / "package-readback.json", base / "actual-move.json", base / "packages/packaging.json",
                root / "evidence/compiler-copy.json", root / "evidence/downloads.json",
                root / "inputs/combined-sdk-inputs.json"]
    if name == "dos2unix":
        selected += [root / "evidence/nls-input-copy.json", root / "inputs/nls-build-inputs.json",
                     root / "host/var/cache/pacman/pkg/perl-5.42.2-1-x86_64.pkg.tar.zst",
                     root / "host/var/cache/pacman/pkg/perl-5.42.2-1-x86_64.pkg.tar.zst.sig"]
    for directory in base.iterdir():
        if directory.is_dir() and directory.name.startswith(("observed-", "functional-")):
            selected += [path for path in directory.rglob("*") if path.is_file()]
    selected += [path for path in (root / "observer").rglob("*") if path.is_file()]
    selected += [path for path in (root / "evidence").iterdir() if path.is_file()
                 and (name in path.name or path.name.startswith("source-extract"))]
    for path in (base / "src").rglob("*"):
        if path.is_file() and (path.name in ("Makefile", "config.log", "config.status", "config.h") or path.suffix == ".t"):
            selected.append(path)
    if name == "which":
        selected += [base / "failed-source-01/build-aarch64-pc-cygwin/config.log"]
    references = []
    for path in sorted(set(selected)):
        target = destination / "evidence" / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        references.append(bound(target))
    report = {
        "schema": 1, "status": f"native-msys-{name}-{version}-producer-complete-not-self-admitted",
        "package": {"name": name, "version": version + "-1", "architecture": "aarch64", **bound(archive)},
        "source": {"repository": "msys2/MSYS2-packages", "commit": "fc03a3300db9bcdd0ccc082749e006abf1a04414",
                   "archive": bound(destination / "source" / f"{name}-{version}.tar.gz"),
                   "signature": "Neither recipe contains detached-signature source entries. Original source SHA256 checks enforced; no detached-signature claim.",
                   "recipe_delta": "Only declared architecture changes from i686/x86_64 to aarch64.",
                   "product_delta": "Only the original MSYS2 mixed-absolute-path patch." if name == "which" else "No product feature reduction."},
        "unchanged_source_tests_and_fixtures": source_files,
        "target": {"triple": "aarch64-pc-cygwin", "pe_machine": "AA64 / 0xAA64", "lp64": True,
                   "runtime_sha256": required["msys-2.0.dll"], "d70_compatibility": False, "mingw": False},
        "compiler": bound(root / "compiler/bin/aarch64-pc-cygwin-gcc.exe"),
        "compiler_scope": "Exact scoped ED4 combined inventory with target fff0 driver and907 runtime; not blanket fff0 qualification.",
        "build_host": "Private x64/emulated orchestration, not packaged or represented as a native provider",
        "protections": "-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2",
        "workers": 1, "new_dependency_builds": False, "package_unsigned": True,
        "upstream": "Original make check completed; which2.25 registers no test cases." if name == "which"
                    else {"files": 9, "tests": 174, "status": "PASS", "created": 1094, "observed": 1094,
                          "parent_raw_exit": 0, "high_exits": 0, "golden_output_changes": False,
                          "driver": "Original prove with --exec loading NativeUtilityTransport.pm. It prefixes only exact converter command tokens with native-utility-exec, preserving original arguments, files, assertions and raw system status.",
                          "diagnostic": "Original x64-host launch lost alias argv[0] across the MSYS architecture boundary: 21/174 failed only on Mac aliases. Exact same product through native907 execv passed the byte-level Mac positive and full original suite.",
                          "locale_selection": "Original Makefile selected 9 suites including UTF16, symlink, binary and BOM. GB18030 locale-specific suites were not selected by the original host locale probe; no forced exclusion or feature macro reduction."},
        "behavior": {phase: {"cases": len(load(base / f"functional-{phase}/result.json")["cases"]),
                            "result": bound(base / f"functional-{phase}/result.json"),
                            "observer": bound(base / f"observed-functional-{phase}/native-job.json")} for phase in phases},
        "move": move, "payload": package["payload"], "new_provides": [],
        "static_closure": {"nodes": list(nodes.values()), "edges": edges, "windows": windows,
                           "unsatisfied_private_IAT": 0, "delay_descriptors": sum(edge["kind"] == "delay_imports" for edge in edges)},
        "private_paths": {"operational_hits": 0, "unchanged_upstream_documentation": path_findings},
        "package_metadata": {"dependencies": ["sh"] if name == "which" else ["libintl"],
                             "mtree_exact": True, "test_or_dependency_payload": False,
                             "removed_shared_info_index": package["excluded_shared_generated_metadata"]},
        "limitations": [
            "No dependency admission is invented. The original which sh dependency remains declared; intake reported no admitted907 Bash/sh provider." if name == "which"
            else "Native907 intl/iconv inputs are separately owned private build/test providers, never included in this package.",
            "A second independent reproducibility rebuild was not performed.",
            "Preserved failing host-path/layout/controller attempts are not recast as successful target tests.",
            "Producer qualification is not complete Git distribution admission; intake retains installation authority.",
        ],
        "reproduction": [
            "Use the exact native907 combined compiler inventory in a NEW root, plus the explicitly released native NLS inputs for dos2unix. Copy private host tools without modifying a provider prefix.",
            "Prepare only the aarch64 recipe declaration, then run extract-native-utilities.sh and build-native-utility.sh with NATIVE_UTILITY_ROOT.",
            "For dos2unix, prepare-native-utility-check.ps1 compiles the test-only native exec helper; supply its transport directory and a new NATIVE_UTILITY_TRANSPORT_LOG to check-native-utility.sh.",
            "Strip only regular staged PEs, preserve the recipe POSIX aliases, package, extract with MSYS tar/winsymlinks:sys, and verify all file/link metadata.",
            "Run the final maintained byte-level test script under the bound native observer before and after an actual move. Keep the test-only exec helper and dependency DLLs outside package ownership.",
        ],
        "evidence": references,
    }
    if name == "dos2unix":
        report["limitations"] += [
            "The private host originally omitted core_perl from PATH. Restoring signed x64 Perl5.42.2 preceded discovery of that PATH requirement; no native Perl/provider claim follows.",
            "Two initial final-package captures stopped on incomplete startup module snapshots (299/18). Bounded retries record errors and still require actual AA64 and all three exact DLLs; no failed snapshot is accepted.",
            "An initial independent -u expectation incorrectly included a BOM. The original upstream suite documents -u versus -u -b separately; both are now byte-checked without changing any upstream expected fixture.",
        ]
    handoff = destination / "handoff.json"
    handoff.write_text(json.dumps(report, indent=2) + "\n")
    export = destination / "export.json"
    export.write_text(json.dumps({"schema": 1, "packages": [{"name": name, "path": str(archive), "sha256": sha(archive)}],
                                  "handoff": bound(handoff), "runtime_cohort": required["msys-2.0.dll"]}, indent=2) + "\n")
    inventory = [bound(path) for path in sorted(destination.rglob("*")) if path.is_file()]
    (destination / "files.json").write_text(json.dumps(inventory, indent=2) + "\n")
    for item in inventory:
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Sealed evidence changed")
    print(json.dumps({"export": bound(export), "handoff": bound(handoff), "package": bound(archive)}))


if __name__ == "__main__":
    main()
