#!/usr/bin/env python3
"""Exercise fresh preparation, idempotency, and lossless drift rejection."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

RECIPE = Path(__file__).resolve().parent


def require_disjoint(path, protected):
    path = Path(path).resolve()
    for item in protected:
        item = Path(item).resolve(strict=True)
        if path == item or path.is_relative_to(item) or item.is_relative_to(path):
            raise ValueError(f"Output path overlaps protected input: {item}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Use a fresh overlay-control path")
    require_disjoint(out, (args.source, RECIPE))
    out.mkdir(parents=True)
    overlay = out / "source"
    command = [
        sys.executable,
        "-B",
        str(RECIPE / "prepare-cygwin-w32api-arm64-overlay.py"),
        "--source",
        str(args.source),
        "--output",
        str(overlay),
    ]
    header = overlay / "mingw-w64-headers/include/psdk_inc/intrin-impl.h"
    report = {"schema": 1, "status": "failed", "runs": []}
    report.update(
        output=str(out),
        source=str(args.source.resolve(strict=True)),
        recipeInputs={
            "test": {
                "path": str((RECIPE / "test-cygwin-w32api-overlay.py").resolve()),
                "sha256": hashlib.sha256(
                    (RECIPE / "test-cygwin-w32api-overlay.py").read_bytes()
                ).hexdigest(),
            },
            "prepare": {
                "path": str((RECIPE / "prepare-cygwin-w32api-arm64-overlay.py").resolve()),
                "sha256": hashlib.sha256(
                    (RECIPE / "prepare-cygwin-w32api-arm64-overlay.py").read_bytes()
                ).hexdigest(),
            },
            "common": {
                "path": str((RECIPE / "cygwin-w32api-common.py").resolve()),
                "sha256": hashlib.sha256(
                    (RECIPE / "cygwin-w32api-common.py").read_bytes()
                ).hexdigest(),
            },
            "sourceLock": {
                "path": str((RECIPE / "cygwin-w32api-source-lock.json").resolve()),
                "sha256": hashlib.sha256(
                    (RECIPE / "cygwin-w32api-source-lock.json").read_bytes()
                ).hexdigest(),
            },
        },
    )
    try:
        for case in ("fresh", "idempotent", "tracked-drift", "untracked-drift"):
            if case == "tracked-drift":
                good = header.read_bytes()
                header.write_bytes(good + b"\n/* owned drift */\n")
                drift = header.read_bytes()
            elif case == "untracked-drift":
                header.write_bytes(good)
                unknown = overlay / "unknown-file"
                unknown.write_text("private control\n", encoding="utf-8", newline="\n")
            result = subprocess.run(command, capture_output=True, timeout=180)
            (out / (case + ".stdout")).write_bytes(result.stdout)
            (out / (case + ".stderr")).write_bytes(result.stderr)
            report["runs"].append({"case": case, "exit": result.returncode})
            if case in ("fresh", "idempotent"):
                if result.returncode:
                    raise ValueError(f"Valid overlay failed: {case}")
            elif result.returncode == 0 or b"drift" not in result.stderr.lower():
                raise ValueError(f"Unknown overlay drift was not rejected: {case}")
            elif case == "tracked-drift" and header.read_bytes() != drift:
                raise ValueError("Rejected tracked drift was not preserved")
            elif case == "untracked-drift" and not unknown.is_file():
                raise ValueError("Rejected untracked file was not preserved")
        report["status"] = "v12-cygwin-w32api-overlay-controls-qualified"
    finally:
        (out / "result.json").write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(out / "result.json")


if __name__ == "__main__":
    main()
