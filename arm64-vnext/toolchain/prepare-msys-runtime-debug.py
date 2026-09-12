#!/usr/bin/env python3
"""Copy the qualified capture inputs; relocate only the collector's owned root."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

INPUTS = {
    "handoff/debug_tree.py": "ab73aaef5d52bc67dad6b8572bf0a63c67fa96f3575363c9ee5d993c4eb64762",
    "driver.SHA256SUMS": "b46ccab632b0ef2e29301e9118481188cf705c39d278f3e6d1ec12cf0bb6bd42",
    "support/bounded_process.py": "226360eeabe3d7f89a7b77378ec1ee15524287eea8df3ccb84a6a5b79cedb619",
    "support/native_job_runner.py": "ce76f288e329df76138fc0e54ba65b68cf29ed2bdaf332ef659261b9c39e0799",
    "support/sources.py": "85a5e8e9bace1e0d04c04fc8d7e969f1e439376612fad246c7d8c612dfc8e7aa",
    "windows-abi.json": "6f57ce24ccbeb751addb7a8f2550ed22ce93b12ddf8d069f296d564b85873e9e",
    "bootstrap-lock.json": "7d26c79265871a88774224de4d424c217555d04beb661756506251ebc3d18d00",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    inputs = dict(INPUTS)
    if sha(source / "driver.SHA256SUMS") != inputs["driver.SHA256SUMS"]:
        raise ValueError("Observer manifest changed")
    for line in (source / "driver.SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        if Path(name).name != name:
            raise ValueError("Observer filename must be a single path component")
        inputs["driver/" + name] = digest
    for name, digest in inputs.items():
        if sha(source / name) != digest:
            raise ValueError(f"Capture input differs: {name}")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    files = {}
    for name, digest in inputs.items():
        destination = out / ("debug_tree.py" if name == "handoff/debug_tree.py" else name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
        files[destination.relative_to(out).as_posix()] = {
            "source": str(source / name), "before": digest, "sha256": sha(destination)}
    collector = out / "debug_tree.py"
    before = collector.read_text()
    original = 'ROOT = Path(r"C:\\ag-exit-e138-01\\resume-20260909-01")'
    if before.count(original) != 1:
        raise ValueError("Unexpected collector root boundary")
    collector.write_text(before.replace(original, f"ROOT = Path({str(out)!r})"),
                         encoding="utf-8", newline="\n")
    files["debug_tree.py"]["sha256"] = sha(collector)
    lock = json.loads((out / "bootstrap-lock.json").read_text())
    if sha(Path(lock["control_receipt"])) != lock["control_receipt_sha256"]:
        raise ValueError("Historical loader-breakpoint control has changed")
    (out / "inputs.json").write_text(json.dumps({
        "schema": 1, "status": "source-bound-zero-write-capture-inputs-prepared",
        "files": files, "source_root": str(source), "root": str(out),
        "relocation": "Only debug_tree.py ROOT literal changes; no forwarding/instrumentation/exit-decoding changes.",
        "scope": "Not proof of any newly produced runtime; --unwind-probes must never be passed."
    }, indent=2) + "\n")
    print(out / "inputs.json")


if __name__ == "__main__":
    main()
