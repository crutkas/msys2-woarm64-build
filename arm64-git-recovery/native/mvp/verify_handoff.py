"""Read back, recreate and execute an exact sealed Git Bash archive in a fresh moved directory."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bounded_process import run
from artifact import ArtifactError, bound_json, inventory, safe_path, sha256, write_json
from moved_replay import extract


def read_archive(archive, receipt):
    if sha256(archive) != receipt["sha256"] or archive.stat().st_size != receipt["size"]:
        raise ArtifactError("Archive differs from the detached artifact receipt")
    with zipfile.ZipFile(archive) as source:
        entries, seen = {}, set()
        for item in source.infolist():
            name = safe_path(item.filename)
            if name.casefold() in seen:
                raise ArtifactError("Duplicate or case-colliding ZIP entry")
            seen.add(name.casefold())
            expected_type = stat.S_IFDIR if item.is_dir() else stat.S_IFREG
            if stat.S_IFMT(item.external_attr >> 16) != expected_type or item.flag_bits & 1:
                raise ArtifactError("Encrypted or non-regular ZIP entry")
            entries[item.filename] = item
        for name in ("tmp/", "var/tmp/", "etc/", "home/"):
            if name not in entries or not entries[name].is_dir():
                raise ArtifactError("ZIP lacks an explicit required runtime directory")
        if "manifest.json" not in entries or entries["manifest.json"].is_dir():
            raise ArtifactError("ZIP has no file manifest")
        manifest_bytes = source.read("manifest.json")
        if hashlib.sha256(manifest_bytes).hexdigest() != receipt["manifest_sha256"]:
            raise ArtifactError("ZIP manifest differs from its detached digest")
        manifest = json.loads(manifest_bytes)
        if manifest["top_source"] != receipt["source"]:
            raise ArtifactError("ZIP and detached receipt name different source tops")
        names = {name for name, item in entries.items() if not item.is_dir()}
        if names != set(manifest["files"]) | {"manifest.json"} or "manifest.json" in manifest["files"]:
            raise ArtifactError("ZIP file inventory differs from its manifest")
        fields = ("size", "sha256", "format", "machine", "imports", "delay_imports", "managed")
        expected = {name: {key: row[key] for key in fields if key in row}
                    for name, row in manifest["files"].items()}
        for name, row in expected.items():
            if row.get("size") != entries[name].file_size:
                raise ArtifactError("ZIP entry size differs from its manifest")
            if row.get("machine") not in (None, "0xAA64"):
                raise ArtifactError("ZIP manifest contains a non-ARM64 payload")
        expected["manifest.json"] = {
            "size": len(manifest_bytes), "sha256": receipt["manifest_sha256"],
            "format": "non-PE", "machine": None, "imports": [], "delay_imports": []}
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    args = parser.parse_args()
    archive, output = args.archive.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Final archive readback requires a fresh output directory")
    receipt = bound_json({"path": str(args.receipt), "sha256": args.receipt_sha256})
    expected = read_archive(archive, receipt)
    output.mkdir(parents=True)
    moved = output / "fresh moved Git Bash extraction"
    report = {"schema": 1, "passed": False, "archive_sha256": receipt["sha256"],
              "receipt_sha256": args.receipt_sha256, "manifest_sha256": receipt["manifest_sha256"],
              "source": receipt["source"], "steps": [],
              "scope": "Fresh final-ZIP readback, byte-identical shipped-archiver recreation and actual moved native behavior/launcher; separate SSH and module proofs remain byte-bound prior evidence"}
    try:
        extract(archive, moved, expected)
        for name in ("usr/bin/bash.exe", "usr/bin/msys-2.0.dll", "usr/bin/ssh.exe",
                     "mingwarm64/bin/git.exe", "mingwarm64/bin/python.exe",
                     "mingwarm64/libexec/git-core/git-remote-https.exe"):
            if expected.get(name, {}).get("machine") != "0xAA64":
                raise ArtifactError(f"Required native entrypoint missing from final ZIP: {name}")
        environment = {name: os.environ[name] for name in
                       ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA") if name in os.environ}
        environment["PATH"] = os.pathsep.join(map(str, (moved / "mingwarm64/bin", moved / "usr/bin",
                                                         Path(os.environ["SystemRoot"]) / "System32")))
        environment.update({"HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                            "TMP": str(output), "TEMP": str(output)})
        recreated = output / "recreated.zip"
        tools = Path(__file__).resolve().parent
        commands = [
            ("recreation", [args.pwsh, "-NoProfile", "-File", moved / "recreate.ps1", "-Output", recreated], 600),
            ("behavior", [sys.executable, "-B", tools / "run_behavior.py",
                          "--root", moved, "--output", output / "behavior"], 660),
            ("launcher", [sys.executable, "-B", tools / "check_launcher.py",
                          "--root", moved, "--output", output / "launcher"], 60)]
        for name, command, timeout in commands:
            with (output / f"{name}.log").open("xb") as log:
                result = run(command, cwd=output, env=environment, log=log, timeout=timeout)
            step = {"name": name, "process": result, "command": list(map(str, command))}
            report["steps"].append(step)
            if not result["passed"]:
                raise ArtifactError(f"Final extracted {name} failed or did not drain")
            if name == "recreation":
                if sha256(recreated) != receipt["sha256"] or recreated.stat().st_size != receipt["size"]:
                    raise ArtifactError("The extracted recreation script did not recreate the exact ZIP")
            else:
                evidence = output / name / "result.json"
                if json.loads(evidence.read_text())["passed"] is not True:
                    raise ArtifactError(f"The extracted {name} has no passing evidence")
                step["result_sha256"] = sha256(evidence)
        report["extraction_unchanged"] = inventory(moved) == expected
        report["archive_unchanged"] = sha256(archive) == receipt["sha256"]
        report["receipt_unchanged"] = sha256(args.receipt) == args.receipt_sha256
        report["file_count"] = len(expected)
        report["arm64_pe_count"] = sum(row["machine"] == "0xAA64" for row in expected.values())
        report["deterministic_recreation"] = True
        report["passed"] = all(report[key] for key in
                               ("extraction_unchanged", "archive_unchanged", "receipt_unchanged"))
    finally:
        write_json(output / "result.json", report)
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
