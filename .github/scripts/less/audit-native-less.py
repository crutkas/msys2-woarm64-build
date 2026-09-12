"""Bind the shipped less members, private DLL imports, and original test layouts."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path):
    return {"path": str(path), "sha256": sha(path), "size": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Audit output must be new")
    root = args.root.resolve()
    spec = importlib.util.spec_from_file_location("existing_pe_reader", root / "inputs/inspect-native-archive.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    package = json.loads((root / "evidence/final-package-readback.json").read_text())
    if package["private_path_hits"] or len(package["pe"]) != 3:
        raise RuntimeError("Shipped package has private path hits or an unexpected PE set")
    for member in package["members"]:
        if member["path"].startswith("usr/"):
            if sha(args.readback / member["path"]) != member["sha256"]:
                raise RuntimeError(f"Shipped readback member changed: {member['path']}")
    mtree = gzip.decompress((root / "extracted-package-01/.MTREE").read_bytes()).decode()
    for member in package["members"]:
        if member["path"] == ".MTREE":
            continue
        expected = f"sha256digest={member['sha256']}"
        rows = [line for line in mtree.splitlines() if line.startswith("./" + member["path"] + " ")]
        if len(rows) != 1 or expected not in rows[0] or f"size={member['size']}" not in rows[0]:
            raise RuntimeError("MTREE content differs from its real package member")
    required = {
        "msys-2.0.dll": "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c",
        "msys-ncursesw6.dll": "e2d03ae2ac264d8788f3cd7ea4917c51c9b26ac59ee574e4cade633a96de3585",
        "msys-pcre2-8-0.dll": "a99ed3e081f94f0f588076c57879a3b91280f5b6813d8bf79f2b567a1ab87043",
    }
    pending = [args.readback / image["path"] for image in package["pe"]]
    nodes, edges, system = {}, [], {}
    while pending:
        path = pending.pop()
        if str(path) in nodes:
            continue
        image = reader.pe(path.read_bytes())
        if not image["ordinary_arm64"]:
            raise RuntimeError(f"Non-AA64 package or private DLL: {path}")
        nodes[str(path)] = {**bound(path), **image}
        for kind in ("imports", "delay_imports"):
            for imported in image[kind]:
                name = imported["dll"].lower()
                target = args.readback / "usr/bin" / name
                if target.is_file():
                    if name not in required or sha(target) != required[name]:
                        raise RuntimeError(f"Unexpected private DLL or changed cohort: {name}")
                    exports = reader.pe(target.read_bytes())["exports"]
                    missing = [symbol for symbol in imported["symbols"] if not any(
                        entry.get("name") == symbol["name"] if "name" in symbol
                        else entry["ordinal"] == symbol["ordinal"] for entry in exports)]
                    if missing:
                        raise RuntimeError(f"Unsatisfied private IAT entries: {name}: {missing}")
                    pending.append(target)
                    classification = "exact907-private-provider"
                else:
                    target = Path(os.environ["SystemRoot"]) / "System32" / name
                    if not target.is_file():
                        raise RuntimeError(f"Unresolved import; no API-set guessing: {name}")
                    system[name] = bound(target)
                    classification = "Windows-System32"
                edges.append({"importer": str(path), "name": name, "kind": kind,
                              "target": str(target), "class": classification,
                              "symbols": len(imported["symbols"])})
    if {Path(name).name.lower() for name in nodes if name.lower().endswith(".dll")} != set(required):
        raise RuntimeError("Unexpected transitive native MSYS DLL set")
    source = root / "src/less-704"
    check = root / "check-source/less-704"
    source_files, fixtures = [], []
    with tarfile.open(root / "inputs/less-704.tar.gz", "r:gz") as archive:
        for item in archive:
            relative = item.name.partition("/")[2]
            if not item.isfile() or not relative:
                continue
            original = hashlib.sha256(archive.extractfile(item).read()).hexdigest()
            if relative.startswith("lesstest/lt/") and relative.endswith(".lt"):
                if sha(check / relative) != original:
                    raise RuntimeError("An original fixture or expected screen was changed")
                fixtures.append({"path": relative, "original_sha256": original, **bound(check / relative)})
            elif relative.endswith((".c", ".h")) and (source / relative).is_file():
                if sha(source / relative) != original or sha(check / relative) != original:
                    raise RuntimeError(f"Original product/test source changed: {relative}")
                source_files.append({"path": relative, "sha256": original})
    if len(fixtures) != 18:
        raise RuntimeError("Wrong original upstream fixture count")
    layout = []
    for original, name in ((check / "less.exe", "less.exe"),
                           (check / "lesstest/lesstest.exe", "lesstest.exe"),
                           (check / "lesstest/lt_screen.exe", "lt_screen.exe")):
        relocated = root / "check-runtime/usr/bin" / name
        if sha(original) != sha(relocated):
            raise RuntimeError("Relocated LESSTEST executable bytes changed")
        layout.append({"before": bound(original), "after": bound(relocated)})
    for name, expected in required.items():
        before = [check / name, check / "lesstest" / name]
        after = root / "check-runtime/usr/bin" / name
        if any(sha(path) != expected for path in before + [after]):
            raise RuntimeError("Test runtime DLL bytes changed")
        layout.append({"before": [bound(path) for path in before], "after": bound(after)})
    log = (root / "observed-check-06/check.log").read_text()
    cases = [{"name": name, "steps": int(steps)} for name, steps in
             re.findall(r"^PASS: (.+) \((\d+) steps\)$", log, re.MULTILINE)]
    job = json.loads((root / "observed-check-06/native-job.json").read_text())
    if (len(cases) != 18 or "RAN  18 tests with 0 errors" not in log or not job["passed"]
            or job["parent_raw_exit"] != 0 or job["created_processes"] != 169
            or job["observed_processes"] != 169 or job["unrelayed_high_exits"]):
        raise RuntimeError("Strict original upstream result did not satisfy its contract")
    for mode, count in (("text", 8), ("large", 4)):
        for phase in ("before02", "moved"):
            result = json.loads((root / f"final-{phase}-{mode}/result.json").read_text())
            if (not result["process"]["passed"] or not result["assertions"]["passed"]
                    or result["assertions"]["assertions"] != count
                    or result["product_sha256"] != sha(args.readback / "usr/bin/less.exe")
                    or result["pager"]["ProcessMachine9"] != "0xAA64"
                    or "TERMINFO" in result["environment"]):
                raise RuntimeError(f"Final stripped regular pager control failed: {phase} {mode}")
    report = {
        "schema": 1, "status": "native-less907-static-and-final-member-contract-passed",
        "scope": "Native MSYS less704, not MinGW, d70 compatibility or full Git admission",
        "package_readback": bound(root / "evidence/final-package-readback.json"),
        "mtree_verified": True, "private_path_hits": [],
        "nodes": list(nodes.values()), "edges": edges, "windows_leaves": system,
        "counts": {"package_pes": 3, "private_dlls": len(required), "iat_unsatisfied": 0,
                   "import_descriptors": len(edges), "windows_dlls": len(system),
                   "delay_import_descriptors": sum(edge["kind"] == "delay_imports" for edge in edges)},
        "original_source_c_h_files": source_files, "original_fixtures": fixtures,
        "upstream_cases": cases, "upstream_steps": sum(case["steps"] for case in cases),
        "upstream_ordinary_pass": bound(root / "observed-check-06/native-job.json"),
        "preserved_split_runtime_failure": bound(root / "observed-check-05/native-job.json"),
        "only_test_layout_delta": layout,
        "supported_test_layout": "One coherent check-runtime/usr/bin MSYS installation; original executable and DLL bytes. No claim of arbitrary cross-install fork/exec support.",
        "dynamic_scope": "Static imports exclude process launches. Shell escapes and the original OSC8 helper require native /bin/sh; remote file-host detection may invoke bash/uname, and man: links invoke man. Those helpers are not supplied or functionally admitted by this less package.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "upstream_steps": report["upstream_steps"]}))


if __name__ == "__main__":
    main()
