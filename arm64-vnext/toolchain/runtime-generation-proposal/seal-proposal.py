#!/usr/bin/env python3
"""Seal a runtime patch proposal and its actual-make evidence without applying it."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

FILES = ("winsup/cygwin/Makefile.am", "winsup/cygwin/scripts/guard-runtime-generation",
         "winsup/testsuite/build/runtime-generation-make.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "root", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    root, base = args.root.resolve(strict=True), args.base.resolve(strict=True)
    proof_path = root / "make-controls-03/result.json"
    proof = json.loads(proof_path.read_text())
    if proof["status"] != "actual-runtime-make-generation-guards-qualified" or proof["casesPassed"] != 16:
        raise ValueError("Actual make negative controls are incomplete")
    if proof["historical_tls_payload"]["bytes"] != 56:
        raise ValueError("Historical TLS corruption was not reproduced")
    if sha(root / "source/winsup/cygwin/scripts/guard-runtime-generation") != proof["guard_sha256"]:
        raise ValueError("Guard changed after actual-make tests")
    if sha(root / "source/winsup/cygwin/Makefile.am") != proof["source_makefile_sha256"]:
        raise ValueError("Makefile changed after actual-make tests")
    tls = root / "inputs/tlsoffsets.good"
    if sha(tls) != "49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566":
        raise ValueError("Good TLS backup differs")
    if sha(root / "build/winsup/cygwin/tlsoffsets") != sha(tls):
        raise ValueError("Actual make changed the real TLS layout")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    patch = out / "runtime-generation-guards.patch"
    changes, patch_lines = [], []
    for name in FILES:
        source, original = root / "source" / name, base / name
        old = original.read_bytes() if original.exists() else b""
        new = source.read_bytes()
        if old == new:
            raise ValueError(f"No proposed change in {name}")
        patch_lines.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),
                                              new.decode().splitlines(keepends=True),
                                              fromfile="a/" + name if original.exists() else "/dev/null",
                                              tofile="b/" + name))
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changes.append({"path": name, "before": hashlib.sha256(old).hexdigest() if original.exists() else None,
                        "after": sha(source)})
    patch.write_text("".join(patch_lines), encoding="utf-8", newline="\n")
    subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(base),
                    "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(root / "source"),
                    "apply", "--reverse", "--check", str(patch)], check=True)
    shutil.copytree(root / "make-controls-03", out / "make-controls")
    shutil.copy2(root / "logs/existing-tls-controls.log", out / "existing-tls-controls.log")
    shutil.copy2(tls, out / "tlsoffsets.good")
    shutil.copy2(Path(__file__).with_name("README.txt"), out / "README.txt")
    report = {
        "schema": 1, "status": "runtime-generation-hardening-proposal-actual-make-qualified",
        "baseRepository": "https://github.com/crutkas/msys2-runtime.git",
        "baseCommit": "563662010c2f2072ad90f28713611caabdf70dbb",
        "baseSource": str(base), "proposalSource": str(root / "source"),
        "applicationOwner": "67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a",
        "patch": ref(patch), "changes": changes, "actualMakeProof": ref(out / "make-controls/result.json"),
        "actualMakeCases": 16, "existingTlsCases": 40, "failuresAcceptedAsSuccess": False,
        "historicalBadTls": proof["historical_tls_payload"],
        "goodTls": ref(out / "tlsoffsets.good"), "generated": proof["generated"],
        "atomicity": "Each output is atomically renamed; receipt is published last. Every make validates inputs/output hashes, rejecting partial publication or corruption.",
        "limits": "Proposal only: no runtime owner worktree/branch changes, no runtime DLL rebuild or ABI change. Owner must apply/publish the patch to the runtime repository."
    }
    (out / "handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = {p.relative_to(out).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size}
             for p in out.rglob("*") if p.is_file()}
    out.with_name(out.name + ".manifest.json").write_text(
        json.dumps({"schema": 1, "files": files}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "handoff.json")


if __name__ == "__main__":
    main()
