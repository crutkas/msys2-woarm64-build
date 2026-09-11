#!/usr/bin/env python3
"""Qualify a completed GMP build while preserving expected raw test exits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


EXPECTED_SUITES = {
    "tests/test-suite.log": (8, 8, 0, 0),
    "tests/mpn/test-suite.log": (53, 52, 1, 0),
    "tests/mpz/test-suite.log": (64, 64, 0, 0),
    "tests/mpq/test-suite.log": (15, 15, 0, 0),
    "tests/mpf/test-suite.log": (28, 28, 0, 0),
    "tests/rand/test-suite.log": (7, 7, 0, 0),
    "tests/misc/test-suite.log": (3, 3, 0, 0),
    "tests/cxx/test-suite.log": (22, 22, 0, 0),
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def pe_machine(path: Path) -> str:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise RuntimeError(f"Not a PE image: {path}")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise RuntimeError(f"Invalid PE signature: {path}")
        return f"0x{struct.unpack('<H', stream.read(2))[0]:04X}"


def suite_counts(path: Path) -> tuple[int, int, int, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    values = []
    for label in ("TOTAL", "PASS", "SKIP", "FAIL"):
        match = re.search(rf"^# {label}:\s+(\d+)$", text, flags=re.MULTILINE)
        if not match:
            raise RuntimeError(f"{path} omitted {label}")
        values.append(int(match.group(1)))
    error = re.search(r"^# ERROR:\s+(\d+)$", text, flags=re.MULTILINE)
    if not error or int(error.group(1)):
        raise RuntimeError(f"{path} has a nonzero or missing ERROR count")
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.build_root.resolve()
    output = root / "build-result-qualified.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite the GMP qualification result")

    original = json.loads((root / "build-result.json").read_text(encoding="utf-8"))
    native = json.loads((root / "native-job.json").read_text(encoding="utf-8"))
    if native.get("parent_raw_exit") != 0 or native.get("timed_out"):
        raise RuntimeError("The GMP makepkg parent did not complete successfully")
    if not native.get("observation_count_matches") or native.get("unobserved_process_ids"):
        raise RuntimeError("The native observer did not account for every process")

    source = root / "build/gmp/src/gmp-6.3.0"
    suites = {}
    totals = {"total": 0, "passed": 0, "skipped": 0, "failed": 0}
    for relative, expected in EXPECTED_SUITES.items():
        path = source / relative
        actual = suite_counts(path)
        if actual != expected:
            raise RuntimeError(f"Unexpected suite result for {relative}: {actual}")
        suites[relative] = {
            "path": str(path),
            "sha256": digest(path),
            "total": actual[0],
            "passed": actual[1],
            "skipped": actual[2],
            "failed": actual[3],
        }
        for key, value in zip(totals, actual):
            totals[key] += value
    if totals != {"total": 200, "passed": 199, "skipped": 1, "failed": 0}:
        raise RuntimeError(f"Unexpected aggregate GMP suite result: {totals}")

    packages = sorted((root / "packages").glob("*.pkg.tar.zst"))
    expected_names = {
        "gmp-6.3.0-1-aarch64.pkg.tar.zst",
        "gmp-devel-6.3.0-1-aarch64.pkg.tar.zst",
    }
    if {path.name for path in packages} != expected_names:
        raise RuntimeError("The expected GMP split package set was not produced")

    pe_images = []
    for path in sorted((root / "build").rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".exe", ".dll"):
            continue
        machine = pe_machine(path)
        if machine != "0xAA64":
            raise RuntimeError(f"Non-AA64 build image: {path}")
        pe_images.append(
            {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "machine": machine,
                "sha256": digest(path),
            }
        )

    raw_exit_counts: dict[str, int] = {}
    for record in native.get("unrelayed_high_exits", []):
        value = str(record["raw_exit"])
        raw_exit_counts[value] = raw_exit_counts.get(value, 0) + 1
    result = {
        "schema": 1,
        "status": "passed",
        "qualification": (
            "The makepkg parent completed successfully, all 200 upstream observations "
            "are accounted for by the eight Automake summaries, and every built PE is "
            "AA64. Raw child exits remain unchanged in native-job.json."
        ),
        "original_build_result": {
            "path": str(root / "build-result.json"),
            "sha256": digest(root / "build-result.json"),
            "status": original.get("status"),
        },
        "native_observer": {
            "path": str(root / "native-job.json"),
            "sha256": digest(root / "native-job.json"),
            "parent_raw_exit": native["parent_raw_exit"],
            "created_processes": native["created_processes"],
            "observed_processes": native["observed_processes"],
            "observation_count_matches": native["observation_count_matches"],
            "unrelayed_high_exit_counts": raw_exit_counts,
            "policy": (
                "Expected upstream negative child exits are recorded, not rewritten, "
                "suppressed, or admitted by executable name."
            ),
        },
        "upstream_tests": {"aggregate": totals, "suites": suites},
        "packages": [
            {"name": path.name, "path": str(path), "sha256": digest(path)}
            for path in packages
        ],
        "pe_images": pe_images,
    }
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"path": str(output), "sha256": digest(output), "tests": totals},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
