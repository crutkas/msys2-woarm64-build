"""Merge explicit native library stages without silently replacing conflicting files."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree

INFO_DIRECTORIES = ("share/info", "usr/share/info", "clangarm64/share/info")


def directories(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir())


def bound_inputs(roots, manifests, compiler_receipt):
    if manifests is None and compiler_receipt is None:
        return None
    if manifests is None or compiler_receipt is None or len(roots) != len(manifests):
        raise ContractError("A coherent merge requires one manifest per stage and an explicit compiler receipt")
    compiler_sha = digest(compiler_receipt)
    records = []
    for root, path in zip(roots, manifests):
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if (record.get("status") not in ("native-msys-library-built-checked-bootstrap-driver",
                                         "native-msys-cmake-built-tested") or
                record.get("compiler_receipt_sha256") != compiler_sha):
            raise ContractError("Dependency stage is failed, unqualified, or from a different compiler/runtime cohort")
        verify_tree(root, path)
        records.append({"path": str(Path(path).resolve()), "sha256": digest(path),
                        "status": record["status"], "limitations": record.get("limitations", []),
                        "pending": record.get("pending", []),
                        "source_manifest_sha256": record.get("source_manifest_sha256")})
    return {"compiler_receipt": str(Path(compiler_receipt).resolve()),
            "compiler_receipt_sha256": compiler_sha, "input_manifests": records}


def merge(roots, output, install_info=None, *, manifests=None, compiler_receipt=None):
    output = Path(output).resolve()
    manifest_path = output.with_name(output.name + ".manifest.json")
    roots = [Path(root).resolve() for root in roots]
    if output.exists() or manifest_path.exists() or not roots:
        raise ContractError("A nonempty stage list and a new output directory are required")
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots):
        raise ContractError("Merged output must be separate from every source stage")
    qualification = bound_inputs(roots, manifests, compiler_receipt)
    records, files = [], {}
    for root in map(lambda p: Path(p).resolve(), roots):
        measured = inventory(root)
        records.append({"root": str(root), "files": measured, "directories": directories(root)})
        for rel, entry in measured.items():
            if rel in {f"{path}/dir" for path in INFO_DIRECTORIES} and install_info is not None:
                continue
            if "sha256" not in entry:
                raise ContractError(f"Resolve stage links explicitly before merging: {rel}")
            if rel in files:
                if files[rel]["identity"] == entry:
                    continue
                # Separate upstream static/shared CMake metadata describe the
                # same installation. Keep the final stage's explicit metadata.
                if not (rel.startswith("lib/cmake/") or rel.startswith("share/cmake/")
                        or rel.endswith((".pc", ".la"))):
                    raise ContractError(f"Conflicting library payload: {rel}")
                previous = files[rel]["root"]
            else:
                previous = None
            files[rel] = {"root": str(root), "identity": entry, "replaces_metadata_from": previous}
    output.mkdir(parents=True)
    for rel in sorted({rel for record in records for rel in record["directories"]}):
        (output / rel).mkdir(parents=True, exist_ok=True)
    for rel, item in files.items():
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(item["root"]) / rel, target)
        if digest(target) != item["identity"]["sha256"]:
            raise ContractError("Input changed during native dependency merge")
    for item in records:
        if inventory(item["root"]) != item["files"] or directories(Path(item["root"])) != item["directories"]:
            raise ContractError("Input stage changed during merge")
    info_generation = None
    if install_info is not None:
        install_info = Path(install_info).resolve()
        generator_hash = digest(install_info)
        manuals = sorted(manual for directory in INFO_DIRECTORIES for manual in (output / directory).glob("*.info"))
        if not manuals:
            raise ContractError("Info-index regeneration requires actual installed manuals")
        environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
        system_path = str(Path(os.environ["SystemRoot"]) / "System32") if os.name == "nt" else "/usr/bin:/bin"
        environment["PATH"] = str(install_info.parent) + os.pathsep + system_path
        commands = []
        for manual in manuals:
            info_dir = manual.parent
            command = [str(install_info), "--dir-file=" + str(info_dir / "dir"), str(manual)]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
            commands.append({"command": command, "stdout": result.stdout, "stderr": result.stderr})
        if digest(install_info) != generator_hash or any(not (manual.parent / "dir").is_file() for manual in manuals):
            raise ContractError("Info generator changed or did not produce an index")
        info_generation = {"generator": str(install_info), "sha256": generator_hash, "commands": commands,
                           "scope": "Explicit metadata generator; no native-tool qualification inferred"}
    report = {"schema": 1, "scope": "Build dependency prefix only, not full Git distribution",
              "inputs": records, "origins": files, "info_generation": info_generation,
              "directories": directories(output), "files": inventory(output)}
    if qualification is not None:
        if bound_inputs(roots, manifests, compiler_receipt) != qualification:
            raise ContractError("Dependency qualification changed during merge")
        report.update(qualification)
        report["status"] = "cohort-bound-build-dependencies-not-distribution"
        report["limitations"] = sorted({limitation for row in qualification["input_manifests"]
                                        for limitation in row["limitations"]})
        report["qualification_scope"] = "Input receipt scope retained; no new build, execution, or package admission"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as dest:
        json.dump(report, dest, indent=2)
        dest.write("\n")
    return len(report["files"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", action="append", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--install-info", type=Path, help="Explicitly regenerate, rather than overwrite, a combined Info index")
    p.add_argument("--manifest", action="append", type=Path,
                   help="One original build result per --stage, in the same order")
    p.add_argument("--compiler-receipt", type=Path,
                   help="Require every stage to bind this exact compiler/runtime receipt")
    a = p.parse_args()
    print(f"Dependency files merged: {merge(a.stage, a.output, a.install_info, manifests=a.manifest, compiler_receipt=a.compiler_receipt)}")


if __name__ == "__main__":
    main()
