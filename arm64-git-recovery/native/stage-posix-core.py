"""Stage explicitly selected POSIX core executables, never a full package fallback."""

import argparse
import json
from pathlib import Path
import shutil

from runtime_readiness import verify
from sources import ContractError, digest, inventory, verify_tree


def stage(build_roots, prefix, output, acknowledge_core_only=False):
    if not acknowledge_core_only:
        raise ContractError("Explicit acknowledgement of core-only, incomplete package scope is required")
    prefix, output = Path(prefix).resolve(), Path(output).resolve()
    if output.exists():
        raise ContractError("Core staging requires a new output directory")
    inputs, selected, receipt_hash = {}, {}, None
    for build_root in map(Path, build_roots):
        build_root = build_root.resolve()
        record = json.loads((build_root / "build-inputs.json").read_text())
        package = record["package"]
        if package not in ("bash", "make") or package in inputs:
            raise ContractError(f"Unexpected or duplicate core package: {package}")
        if record["classification"] != "bootstrap" or record["target"] != "aarch64-pc-cygwin":
            raise ContractError("Expected a receipt-bound POSIX bootstrap input")
        receipt = record["runtime_receipt"]
        measured = verify(receipt["path"], prefix)
        if measured != receipt["sha256"] or (receipt_hash is not None and measured != receipt_hash):
            raise ContractError("Builds do not share the current coherent runtime receipt")
        receipt_hash = measured
        for name, tool in record["tools"].items():
            if digest(tool["path"]) != tool["sha256"]:
                raise ContractError(f"Build tool changed before core staging: {name}")
        source = Path(record["prepared_source"]["path"])
        manifest = source.with_name(source.name + ".prepare.json")
        if digest(manifest) != record["prepared_source"]["manifest_sha256"]:
            raise ContractError("Prepared source identity changed")
        verify_tree(source, manifest)
        binary = Path(record.get("build_directory", build_root / "build")) / f"{package}.exe"
        if not binary.is_file() or binary.stat().st_size == 0:
            raise ContractError(f"Missing linked core executable: {binary}")
        selected[f"usr/bin/{package}.exe"] = binary
        if package == "bash":
            selected["usr/bin/sh.exe"] = binary
        selected[f"usr/share/licenses/{package}/COPYING"] = source / "COPYING"
        inputs[package] = {
            "build_root": str(build_root), "build_inputs": record,
            "build_inputs_sha256": digest(build_root / "build-inputs.json"),
            "build_log_sha256": digest(build_root / "build.log"),
            "full_install_report_present": (build_root / "build-evidence.json").is_file()
        }
    if set(inputs) != {"bash", "make"}:
        raise ContractError("Both Bash and make core build inputs are mandatory")
    selected["usr/bin/msys-2.0.dll"] = prefix / "bin/msys-2.0.dll"
    expected = {}
    output.mkdir(parents=True)
    for rel, source in selected.items():
        expected[rel] = {"sha256": digest(source), "size": source.stat().st_size}
        destination = output / "payload" / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    files = inventory(output / "payload")
    if files != expected:
        raise ContractError("Core staging input changed during copy")
    report = {
        "schema": 1, "status": "core-staged-not-run", "classification": "bootstrap",
        "build_host": "linux-aarch64-cross", "target": "aarch64-pc-cygwin",
        "scope": "Bash/sh/make/runtime and licenses only; intentionally not a full package installation",
        "runtime_receipt_sha256": receipt_hash, "inputs": inputs, "files": files,
        "excluded": ["loadable examples", "headers", "documentation", "full readline/NLS closure"],
        "pending": ["native-core-behavior", "full-package-installation", "full-Git-distribution"]
    }
    with (output / "core-evidence.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, action="append", required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-core-only", action="store_true")
    args = parser.parse_args()
    print(f"Core-only files staged: {stage(args.build, args.prefix, args.output, args.acknowledge_core_only)}")


if __name__ == "__main__":
    main()
