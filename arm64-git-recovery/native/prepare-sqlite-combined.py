"""Bind existing native SQLite payloads to the new combined runtime privately."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import sealed_json, verify_files, merge_files
from sqlite_pe import inspect_pe
from ssh_bootstrap import require_memory

COMBINED = Path(r"C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a\files\combined-runtime-20260911\handoff\combined-runtime-handoff.json")
COMBINED_SHA = "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b"
HANDOFF_SHA = "9bfa0f82b6456b546e654e53da68661555fee0d8a9656b592258a052c2edf718"
PROOF_SHA = "6218b1a6aee5e8f6544ee44fc7511b1da5570639ce5f315d8c3a5eb57452fdd5"


def wsl_path(value):
    if not value.startswith("/root/arm64-vnext-20260905/runtime/combined-20260911-02/"):
        raise ContractError("Combined runtime path is outside its exact approved source root")
    return Path("\\\\wsl.localhost\\Ubuntu" + value.replace("/", "\\"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = Path(r"C:\ag-sqlite-combined-01")
    output = args.output.resolve()
    if (output == project or not output.is_relative_to(project) or output.exists()
            or any(p.is_symlink() or p.is_junction() for p in output.parents)):
        raise ContractError("Fresh private combined-runtime qualification root required")
    combined = sealed_json(COMBINED, COMBINED_SHA)
    if (combined["status"] != "combined-arm64-runtime-reproducible-scoped-qualified-and-published"
            or not combined["results"]["headers_and_jump_abi_unchanged"]):
        raise ContractError("Expected the scoped qualified ABI-compatible combined runtime")
    old = Path(r"C:\ag-sqlite-e138-01")
    handoff = sealed_json(old / "handoff-01/result.json", HANDOFF_SHA)
    proof = sealed_json(old / "proof-04/result.json", PROOF_SHA)
    if proof["status"] != "native-sqlite-unit-proofs-passed" or proof["errors"]:
        raise ContractError("Existing complete SQLite unit proof required")
    output.mkdir(parents=True)
    report = {"schema": 1, "status": "failed", "project_root": str(project),
              "native_processes_launched": 0, "minimum_free_ram_gib": require_memory(),
              "combined_receipt_sha256": COMBINED_SHA, "combined_receipt": combined,
              "sqlite_handoff_sha256": HANDOFF_SHA, "original_proof_sha256": PROOF_SHA,
              "existing_sqlite_rebuilt": False, "runtime_rebuilt": False}
    try:
        (output / "evidence").mkdir()
        shutil.copyfile(COMBINED, output / "evidence/combined-runtime-handoff.json")
        binary_inputs = {}
        for name in ("runtime", "import_library", "startup"):
            row = combined[name]
            path = wsl_path(row["path"])
            if digest(path) != row["sha256"]:
                raise ContractError(f"Combined runtime input differs: {name}")
            destination = output / "evidence" / path.name
            shutil.copyfile(path, destination)
            if digest(destination) != row["sha256"] or digest(path) != row["sha256"]:
                raise ContractError(f"Combined runtime copy/source changed: {name}")
            binary_inputs[name] = {"path": str(destination), "source_path": str(path),
                                   "sha256": row["sha256"], "size": destination.stat().st_size}
        report["combined_binaries"] = binary_inputs
        runtime = output / "runtime"
        runtime.mkdir()
        verify_files(old / "proof-04/runtime", proof["runtime_files"])
        merge_files(old / "proof-04/runtime", runtime, proof["runtime_files"], omit=("usr/bin/msys-2.0.dll",))
        shutil.copyfile(binary_inputs["runtime"]["path"], runtime / "usr/bin/msys-2.0.dll")
        (runtime / "tmp").mkdir(exist_ok=True)
        report["runtime_sha256"] = combined["runtime"]["sha256"]
        report["runtime_path"] = str(runtime)
        report["runtime_files"] = inventory(runtime)
        report["runtime_pe"] = {p: inspect_pe(runtime / p) for p in report["runtime_files"]
                                if Path(p).suffix.lower() in (".exe", ".dll")}
        consumers = output / "consumers"
        consumers.mkdir()
        report["consumer_files"] = {}
        for name, step_name in (("sqlite-api-shared.exe", "api-shared"), ("sqlite-api-static.exe", "api-static"),
                                ("sqlite-helper-apis.exe", "helper-apis")):
            step = next(s for s in proof["steps"] if s["name"] == step_name)
            row = step["loaded_modules"][name]
            source = Path(row["path"])
            if digest(source) != row["sha256"]:
                raise ContractError(f"Existing native consumer changed: {name}")
            shutil.copyfile(source, consumers / name)
            report["consumer_files"][name] = inspect_pe(consumers / name)
        payloads = {}
        for name, row in handoff["payloads"].items():
            verify_files(row["stage"], row["files"])
            payloads[name] = {p: inspect_pe(Path(row["stage"]) / p)
                              for p in row["files"] if Path(p).suffix.lower() in (".exe", ".dll")}
        report["all_seven_split_pe"] = payloads
        report["all_seven_split_files"] = sum(p["file_count"] for p in handoff["payloads"].values())
        verify_files(old / "proof-04/runtime", proof["runtime_files"])
        if digest(COMBINED) != COMBINED_SHA:
            raise ContractError("Combined runtime receipt changed")
        report["status"] = "native-sqlite-combined-runtime-private-inputs-prepared"
    finally:
        (output / "prepare.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "manifest": str(output / "prepare.json"),
                      "sha256": digest(output / "prepare.json"), "runtime_sha256": report["runtime_sha256"]}))


if __name__ == "__main__":
    main()
