"""Recreate and replay a nonpublication diagnostic archive from two independently extracted roots."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from artifact import ArtifactError, deterministic_zip, inventory, safe_path, sha256, write_json


def extract(archive, target, expected):
    if target.exists():
        raise ArtifactError("Moved extraction must be fresh")
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        if {item.filename for item in source.infolist() if not item.is_dir()} != set(expected):
            raise ArtifactError("Archive entries differ from the source manifest")
        for item in source.infolist():
            destination = target / safe_path(item.filename)
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as src, destination.open("xb") as dest:
                shutil.copyfileobj(src, dest)
    for name in ("tmp", "var/tmp", "etc", "home"):
        if not (target / name).is_dir():
            raise ArtifactError("Archive omitted a required runtime directory")
    if inventory(target) != expected:
        raise ArtifactError("Fresh extracted bytes differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--process-gate", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("A fresh deterministic recreation root is required")
    output.mkdir(parents=True)
    expected = inventory(root)
    archive = output / "NON-ADMITTED-experimental-diagnostic.zip"
    first = deterministic_zip(root, archive)
    moved = output / "first moved extraction"
    extract(archive, moved, expected)
    second_archive = output / "NON-ADMITTED-independent-recreation.zip"
    second = deterministic_zip(moved, second_archive)
    if first != second:
        raise ArtifactError("Independent archive recreation is not byte-identical")
    second_root = output / "second moved extraction"
    extract(second_archive, second_root, expected)
    script_root = Path(__file__).parent
    report = {"schema": 1, "classification": "NON-ADMITTED EXPERIMENTAL DIAGNOSTIC PROJECTION; PUBLICATION FORBIDDEN",
              "requested_mvp_artifact_created": False, "archive": first,
              "deterministic_recreation_identical": True, "replays": [],
              "scope": "Two local independently extracted byte-identical roots and fresh subprocess replays; not independent remote custody or provider admission"}
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA") if name in os.environ}
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    try:
        for index, extraction in enumerate((moved, second_root), 1):
            replay = output / f"behavior-{index}"
            command = [sys.executable, "-B", str(script_root / "run_behavior.py"), "--root", str(extraction), "--output", str(replay)]
            result = subprocess.run(command, env=env, capture_output=True, timeout=720)
            (output / f"behavior-{index}.stdout").write_bytes(result.stdout)
            (output / f"behavior-{index}.stderr").write_bytes(result.stderr)
            item = {"root": str(extraction), "raw_controller_exit": result.returncode,
                    "result_sha256": sha256(replay / "result.json") if (replay / "result.json").is_file() else None}
            report["replays"].append(item)
            if result.returncode:
                raise ArtifactError(f"Moved native behavior replay {index} failed")
        attestation = output / "moved-native-attestation"
        process = subprocess.run([sys.executable, "-B", str(script_root / "attest_entrypoints.py"),
                                  "--root", str(second_root), "--output", str(attestation), "--pwsh", str(args.pwsh),
                                  "--process-gate", str(args.process_gate)], env=env, capture_output=True, timeout=180)
        (output / "attestation.stdout").write_bytes(process.stdout)
        (output / "attestation.stderr").write_bytes(process.stderr)
        if process.returncode:
            raise ArtifactError("Moved native entrypoint/module attestation failed")
        report["attestation_sha256"] = sha256(attestation / "result.json")
        report["inputs_unchanged"] = inventory(root) == expected
        report["passed_local_diagnostic_replay"] = report["inputs_unchanged"]
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"archive_sha256": first["sha256"], "size": first["size"],
                      "deterministic": True, "fresh_moved_replays": len(report["replays"]),
                      "publication_authorized": False}))


if __name__ == "__main__":
    main()
