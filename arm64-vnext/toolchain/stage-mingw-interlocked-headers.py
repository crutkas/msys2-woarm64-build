#!/usr/bin/env python3
"""Export pinned MinGW sources and stage a new installed-header-only cohort."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess

RECIPE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Header export requires regular files, not links: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    if not files:
        raise ValueError("Empty installed header cohort")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "baseline-include", "producer-receipt", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--producer-receipt-sha256", required=True)
    args = parser.parse_args()
    api = runpy.run_path(str(RECIPE / "source-lock.py"))
    lock = api["load_lock"](RECIPE)
    config = lock["sources"]["mingw-woarm64"]
    patch = next(p for p in config["patches"] if p["file"] == "mingw-woarm64-interlocked-exchange-ordering.patch")
    contract = patch["source_identity"]
    if (sha(args.producer_receipt) != args.producer_receipt_sha256 or
            args.producer_receipt_sha256 != patch["transport"]["handoff_sha256"]):
        raise ValueError("Frozen producer receipt differs")
    producer = json.loads(args.producer_receipt.read_text())
    if (producer["upstream_source"]["commit"] != config["revision"] or
            producer["upstream_source"]["original_sha256"] != contract["before_sha256"] or
            producer["upstream_source"]["patched_sha256"] != contract["after_sha256"]):
        raise ValueError("Producer and maintained MinGW source contract differ")
    original_source = args.source.resolve(strict=True)

    def git(*argv):
        return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-C", str(original_source), *argv])

    def source_state():
        return {"head": git("rev-parse", "HEAD").decode().strip(),
                "diff": hashlib.sha256(git("diff", "--binary", "HEAD")).hexdigest(),
                "untracked": hashlib.sha256(git("ls-files", "--others", "--exclude-standard")).hexdigest()}

    original_state = source_state()
    if original_state["head"] != config["revision"]:
        raise ValueError("Expected the pinned native MinGW dependency, not v12 Cygwin w32api")
    blob = git("show", config["revision"] + ":" + contract["file"])
    if hashlib.sha256(blob).hexdigest() != contract["before_sha256"]:
        raise ValueError("Pinned source blob differs from producer evidence")
    baseline = args.baseline_include.resolve(strict=True)
    header_relative = Path("psdk_inc/intrin-impl.h")
    if sha(baseline / header_relative) != contract["before_sha256"]:
        raise ValueError("Baseline header is not the exact unpatched native MinGW cohort")
    before = inventory(baseline)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    if out.is_relative_to(baseline) or out.is_relative_to(original_source):
        raise ValueError("Use an independent new header cohort")
    logs = out / "logs"
    logs.mkdir()
    source = out / "source"
    source.mkdir()
    archive = out / "pinned-source.tar"
    with archive.open("xb") as stream:
        subprocess.run(["git", "-C", str(original_source), "archive", config["revision"]],
                       stdout=stream, check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(source)], check=True)
    changes = []
    for entry in config["patches"]:
        file = RECIPE / entry["file"]
        command = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-C", str(source), "apply"]
        for suffix, options in (("check", ["--check"]), ("apply", [])):
            with (logs / (file.stem + "-" + suffix + ".log")).open("xb") as stream:
                subprocess.run(command + options + [str(file)], stdout=stream, stderr=subprocess.STDOUT, check=True)
        changes.append(entry)
    api["verify_patched_source"](lock, "mingw-woarm64", source)
    candidate = out / "include"
    shutil.copytree(baseline, candidate)
    shutil.copy2(source / contract["file"], candidate / header_relative)
    after = inventory(candidate)
    changed = [name for name in set(before) | set(after) if before.get(name) != after.get(name)]
    if changed != [header_relative.as_posix()]:
        raise ValueError(f"Unexpected installed-header delta: {changed}")
    if after[header_relative.as_posix()]["sha256"] != contract["after_sha256"]:
        raise ValueError("Staged header does not have the validated producer bytes")
    if inventory(baseline) != before or source_state() != original_state:
        raise ValueError("Original source or qualified installed headers changed")
    (out / "source-lock.json").write_bytes((RECIPE / "source-lock.json").read_bytes())
    (out / "header-manifest.json").write_text(json.dumps({
        "schema": 1, "target": "aarch64-w64-mingw32", "includeRoot": str(candidate),
        "files": after, "baselineIncludeRoot": str(baseline), "baselineFiles": before,
        "changedFiles": changed
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    report = {"schema": 1, "status": "private-mingw-interlocked-header-cohort-staged-not-qualified",
              "source": {"repository": config["repository"], "commit": config["revision"],
                         "blob": contract["file"], "blobSHA1": git("rev-parse", config["revision"] + ":" + contract["file"]).decode().strip(),
                         "originalState": original_state},
              "sourceLockSHA256": sha(out / "source-lock.json"), "orderedPatches": changes,
              "producerReceipt": {"path": str(args.producer_receipt), "sha256": sha(args.producer_receipt)},
              "header": {"path": str(candidate / header_relative), **contract},
              "manifest": {"path": str(out / "header-manifest.json"), "sha256": sha(out / "header-manifest.json")},
              "compilerAndLibraryBinariesChanged": False,
              "scope": "Header-only successor of explicitly inventoried native MinGW includes; no v12 Cygwin overlay, package rebuild or implicit consumer admission."}
    (out / "stage.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "stage.json")


if __name__ == "__main__":
    main()
