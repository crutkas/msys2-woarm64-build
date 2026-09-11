"""Seal a first-artifact directory only after explicit functional, observer and admission gates pass."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from artifact import ArtifactError, bound_json, inventory, sha256, write_json

ARTIFACT_NAME = "arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip"


def require_evidence(spec):
    results = {name: bound_json(item) for name, item in spec["evidence"].items()}
    for name in ("behavior", "observer", "ssh", "entrypoints", "independent_replay"):
        if name not in results or results[name].get("passed") is not True:
            raise ArtifactError(f"The first artifact has no complete passing {name} evidence")
    if spec.get("publication_authorized") is not True:
        raise ArtifactError("The artifact owner has not authorized publication")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    results = require_evidence(spec)
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Final artifact output must be fresh")
    assembly = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = inventory(root)
    if {name: row["sha256"] for name, row in files.items()} != {name: row["sha256"] for name, row in assembly["files"].items()}:
        raise ArtifactError("Final payload differs from its exact assembly manifest")
    source = assembly["top_source"]
    if not source.get("commit") or not source.get("tree"):
        raise ArtifactError("The artifact must name one exact top-of-stack source identity")
    output.mkdir(parents=True)
    payload = output / "payload"
    shutil.copytree(root, payload)
    evidence_dir = payload / "evidence"
    evidence_dir.mkdir()
    # Keep original measurements unchanged; ship their referenced paths as provenance,
    # not as operational search paths or an instruction to access the producer.
    for name, item in spec["evidence"].items():
        shutil.copyfile(item["path"], evidence_dir / f"{name}.json")
    provenance = {"schema": 1, "artifact": ARTIFACT_NAME, "milestone": "limited native engineering MVP, not RTM",
                  "top_source": source, "assembly_manifest_sha256": sha256(args.manifest),
                  "evidence": {name: {"file": f"evidence/{name}.json", "sha256": item["sha256"]}
                               for name, item in spec["evidence"].items()},
                  "limitations": assembly["limitations"], "publication_authority": spec["publication_authority"]}
    write_json(payload / "provenance.json", provenance)
    write_json(payload / "replay-results.json", {name: {"passed": result.get("passed"), "source_sha256": spec["evidence"][name]["sha256"]}
                                              for name, result in results.items()})
    readme = (
        "# Native ARM64 Git Bash engineering MVP\n\n"
        "**Limited engineering handoff, not RTM or full Git for Windows release admission.**\n\n"
        f"Assembly source: `{source['repository']}` commit `{source['commit']}`, tree `{source['tree']}`.\n\n"
        "Extract to a writable directory on Windows 11 ARM64. Launch `Git-Bash-Native.cmd`.\n"
        "The upstream `git-bash.exe` mintty entry is not the supported entrypoint in this artifact.\n"
        "All supported application payload PEs are ordinary ARM64. Windows system components and\n"
        "one-time validation tooling are recorded separately; no x64 bootstrap is shipped.\n\n"
        "Verify the detached ZIP SHA-256 before extraction, then the file hashes in `manifest.json`.\n"
        "A ZIP cannot embed its own final digest; its exact artifact hash is in the adjacent receipt.\n\n"
        "Supported evidence covers native Bash, local Git/hooks/recursive clones, verified HTTPS,\n"
        "controlled SSH public-key/host-key checks, fork/pipeline/subshell, filesystem and signals.\n"
        "Admission scopes and independent moved-root replay are in `provenance.json` and `evidence/`.\n\n"
        "## Explicit limitations\n\n" + "".join(f"- {item}\n" for item in assembly["limitations"]) +
        "\nIssue/contact route: the linked assembly source pull request in the crutkas fork.\n"
    )
    (payload / "README-HANDOFF.md").write_text(readme, encoding="utf-8", newline="\n")
    recipe_dir = payload / "recreation"
    recipe_dir.mkdir()
    shutil.copyfile(Path(__file__).with_name("artifact.py"), recipe_dir / "artifact.py")
    (payload / "recreate.ps1").write_text(
        "param([Parameter(Mandatory)][string]$Output)\n"
        "$ErrorActionPreference='Stop'\n"
        "& \"$PSScriptRoot\\mingwarm64\\bin\\python.exe\" -B \"$PSScriptRoot\\recreation\\artifact.py\" zip --root $PSScriptRoot --output $Output\n"
        "exit $LASTEXITCODE\n", encoding="utf-8", newline="\n")
    final_files = inventory(payload)
    for name, row in final_files.items():
        if name in assembly["files"]:
            row["provenance"] = assembly["files"][name]["provenance"]
        else:
            row["provenance"] = {"source": source, "role": "artifact manifest, evidence or recreation tooling"}
    write_json(payload / "manifest.json", {"schema": 1, "scope": "Every archive file except this self-describing manifest",
                                          "top_source": source, "files": final_files,
                                          "manifest_self_hash": "Provided in the detached artifact receipt"})
    archiver = payload / "mingwarm64/bin/python.exe"
    archiver_sha = sha256(archiver)
    environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PROGRAMDATA") if name in os.environ}
    environment["PATH"] = str(archiver.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")

    def archive_with_shipped_python(source_root, destination):
        command = [archiver, "-B", recipe_dir / "artifact.py", "zip", "--root", source_root, "--output", destination]
        result = subprocess.run(list(map(str, command)), env=environment, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ArtifactError(f"The shipped, hash-pinned native Python archive step failed: {result.stderr}")
        return json.loads(result.stdout)

    first = archive_with_shipped_python(payload, output / ARTIFACT_NAME)
    check_root = output / "independent-recreation-input"
    shutil.copytree(payload, check_root)
    second = archive_with_shipped_python(check_root, output / "independent-recreation.zip")
    if first != second:
        raise ArtifactError("Final artifact recreation is not byte-identical")
    write_json(output / "artifact-receipt.json", {"schema": 1, "artifact": ARTIFACT_NAME, **first,
               "manifest_sha256": sha256(payload / "manifest.json"), "source": source,
               "archiver": {"payload_path": "mingwarm64/bin/python.exe", "sha256": archiver_sha},
               "deterministic_recreation": True, "publication_authorized": True,
               "limitations": assembly["limitations"]})
    print(json.dumps(first))


if __name__ == "__main__":
    main()
