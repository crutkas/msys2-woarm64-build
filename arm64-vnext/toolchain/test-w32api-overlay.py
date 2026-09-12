#!/usr/bin/env python3
"""Exercise the maintained overlay's fresh export, idempotency and drift rejection."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

RECIPE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    overlay = out / "source"
    command = [sys.executable, "-B", str(RECIPE / "prepare-w32api-overlay.py"),
               "--source", str(args.source), "--output", str(overlay)]
    report = {"schema": 1, "status": "failed", "runs": []}
    header = overlay / "mingw-w64-headers/include/psdk_inc/intrin-impl.h"
    try:
        for case in ("fresh", "idempotent", "tracked-drift", "untracked-drift"):
            if case == "tracked-drift":
                header.write_bytes(header.read_bytes() + b"\n/* owned drift */\n")
                drift = sha(header)
            elif case == "untracked-drift":
                header.write_bytes(good)
                (overlay / "unknown-file").write_text("private control\n")
            before = sha(header) if header.exists() else None
            result = subprocess.run(command, capture_output=True, timeout=120)
            (out / (case + ".stdout")).write_bytes(result.stdout)
            (out / (case + ".stderr")).write_bytes(result.stderr)
            report["runs"].append({"case": case, "exit": result.returncode})
            if case in ("fresh", "idempotent"):
                if result.returncode:
                    raise ValueError(f"Valid overlay failed: {case}")
                if case == "fresh":
                    good = header.read_bytes()
                    first = sha(overlay.with_name("source.source.json"))
                elif sha(header) != before or sha(overlay.with_name("source.source.json")) != first:
                    raise ValueError("Idempotent overlay changed bytes or receipt")
            elif not result.returncode or b"drift" not in result.stderr:
                raise ValueError("Unknown overlay was not rejected")
            elif case == "tracked-drift" and sha(header) != drift:
                raise ValueError("Rejected source drift was not preserved")
            elif case == "untracked-drift" and not (overlay / "unknown-file").exists():
                raise ValueError("Rejected untracked file was removed")
        report["status"] = "v12-w32api-overlay-controls-qualified"
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
