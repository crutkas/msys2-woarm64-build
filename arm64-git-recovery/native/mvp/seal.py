"""Seal a first-artifact directory only after explicit functional, observer and admission gates pass."""

import argparse
import copy
import json
import os
import re
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


def bind_plan(assembly, plan):
    components = {component["id"]: component for component in plan["components"]}
    if len(components) != len(plan["components"]):
        raise ArtifactError("Duplicate component identity in the assembly plan")
    if plan["top_source"] != assembly["top_source"] or plan.get("limitations", []) != assembly["limitations"]:
        raise ArtifactError("Assembly source or limitations differ from the exact input plan")
    for name, row in assembly["files"].items():
        owners = row["components"]
        if not owners or not set(owners).issubset(components):
            raise ArtifactError(f"Assembly file has no exact input-plan component: {name}")
        if row["provenance"] != components[owners[0]]["provenance"]:
            raise ArtifactError(f"Assembly file provenance differs from its input plan: {name}")
    receipts = {}
    for component in components.values():
        for item in component.get("receipts", []):
            receipts[item["sha256"]] = bound_json(item)
    return receipts, {name: component["provenance"] for name, component in components.items()}


def bind_evidence(results, files, manifest_sha256):
    observer = results["observer"]
    if observer.get("source_manifest") != {name: row["sha256"] for name, row in files.items()}:
        raise ArtifactError("Observer evidence does not describe this exact payload")
    if (observer.get("observer_passed") is not True or not observer.get("created_processes")
            or observer["created_processes"] != observer.get("observed_processes")):
        raise ArtifactError("Observer evidence has incomplete process-generation coverage")
    for name in ("behavior", "observer"):
        cases = results[name].get("cases", [])
        if len(cases) != 12 or any(len(row) < 2 or row[1] != "PASS" for row in cases):
            raise ArtifactError(f"The complete twelve-case {name} result is required")
    independent = results["independent_replay"]
    if (independent.get("candidate_manifest_sha256") != manifest_sha256
            or any(independent.get(key) is not True for key in
                   ("original_candidate_unchanged", "private_candidate_unchanged", "owned_jobs_drained"))):
        raise ArtifactError("Independent replay is not bound to this unchanged payload")
    if results["behavior"].get("runtime_sha256") != files["usr/bin/msys-2.0.dll"]["sha256"]:
        raise ArtifactError("Behavior evidence used a different runtime")
    if results["ssh"].get("client_sha256") != files["usr/bin/ssh.exe"]["sha256"]:
        raise ArtifactError("SSH evidence used a different client")
    cases = results["entrypoints"].get("cases", [])
    if len(cases) != 4 or {case["name"] for case in cases} != {"bash", "git", "https-helper", "python"}:
        raise ArtifactError("Four responsive native entrypoint checkpoints are required")
    for case in cases:
        if not case.get("modules") or case.get("native_process", {}).get("Passed") is not True:
            raise ArtifactError("Entrypoint process or module evidence is missing")
        payload_modules = [module for module in case["modules"] if module["location"] == "payload"]
        if not payload_modules:
            raise ArtifactError("Entrypoint checkpoint has no measured payload module")
        for module in payload_modules:
            row = files.get(module["payload_path"])
            if not row or row["sha256"] != module["sha256"] or module["machine"] != "0xAA64":
                raise ArtifactError("Entrypoint loaded a different or non-native payload module")


def source_enricher(plan, resolution, receipt_sha256):
    selected = {(row["provenance"]["source"].get("repository"), row["provenance"]["source"].get("commit"))
                for row in plan["components"]}
    identities = {}
    for record in resolution["records"]:
        key = record["repository"], record["commit"]
        if (key not in selected or key in identities
                or not re.fullmatch(r"[0-9a-f]{40}", record["commit"])
                or not re.fullmatch(r"[0-9a-f]{40}", record["tree"])):
            raise ArtifactError("Source resolution has an unknown, duplicate or malformed Git identity")
        identities[key] = record

    def enrich(provenance):
        result = copy.deepcopy(provenance)
        source = result["source"]
        record = identities.get((source.get("repository"), source.get("commit")))
        if record:
            if source.get("tree") not in (None, record["tree"]):
                raise ArtifactError("Source resolution contradicts an existing tree identity")
            result["source_identity_enrichment"] = {
                "original_tree": source.get("tree"), "receipt_sha256": receipt_sha256,
                "lookup": record["lookup"], "scope": resolution["scope"]}
            source["tree"] = record["tree"]
        return result

    return enrich


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    results = require_evidence(spec)
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Final artifact output must be fresh")
    assembly = bound_json({"path": str(args.manifest), "sha256": spec["assembly_manifest_sha256"]})
    plan = bound_json({"path": str(args.plan), "sha256": spec["assembly_plan_sha256"]})
    receipt_records, component_records = bind_plan(assembly, plan)
    resolution = None
    enrich = copy.deepcopy
    if "source_resolution" in spec:
        resolution = bound_json(spec["source_resolution"])
        if resolution["assembly_plan_sha256"] != spec["assembly_plan_sha256"]:
            raise ArtifactError("Source identity resolution belongs to a different assembly plan")
        enrich = source_enricher(plan, resolution, spec["source_resolution"]["sha256"])
    files = inventory(root)
    if {name: row["sha256"] for name, row in files.items()} != {name: row["sha256"] for name, row in assembly["files"].items()}:
        raise ArtifactError("Final payload differs from its exact assembly manifest")
    bind_evidence(results, files, spec["assembly_manifest_sha256"])
    source = spec.get("top_source", assembly["top_source"])
    if not source.get("commit") or not source.get("tree"):
        raise ArtifactError("The artifact must name one exact top-of-stack source identity")
    repository = Path(__file__).resolve().parents[3]
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    current_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "arm64-git-recovery/native/mvp",
                                     "arm64-git-recovery/native/bounded_process.py"], cwd=repository, text=True)
    if dirty or source["commit"] != current_commit or source["tree"] != current_tree:
        raise ArtifactError("Artifact sealing requires the exact committed, clean recipe top")
    for file in (Path(__file__).parent / "payload").rglob("*"):
        if file.is_file():
            name = file.relative_to(Path(__file__).parent / "payload").as_posix()
            if name not in files or sha256(file) != files[name]["sha256"]:
                raise ArtifactError("Committed entrypoint bytes differ from the independently replayed payload")
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
                  "assembly_plan_sha256": sha256(args.plan),
                  "original_assembly_source": assembly["top_source"],
                  "evidence": {name: {"file": f"evidence/{name}.json", "sha256": item["sha256"]}
                               for name, item in spec["evidence"].items()},
                  "limitations": assembly["limitations"], "publication_authority": spec["publication_authority"]}
    provenance["evidence_limitations"] = spec.get("evidence_limitations", [])
    provenance["admission_and_producer_receipts"] = receipt_records
    provenance["components"] = {name: enrich(record) for name, record in component_records.items()}
    if resolution is not None:
        provenance["source_identity_resolution"] = resolution
        provenance["source_identity_resolution_sha256"] = spec["source_resolution"]["sha256"]
    write_json(payload / "provenance.json", provenance)
    write_json(payload / "replay-results.json", {name: {"passed": result.get("passed", result.get("Passed")), "source_sha256": spec["evidence"][name]["sha256"]}
                                              for name, result in results.items()})
    with (payload / "process-attestation.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for case in results["entrypoints"].get("cases", []):
            stream.write(json.dumps(case, sort_keys=True) + "\n")
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
        "Admission scopes and independent moved-root replay are in `provenance.json` and `evidence/`.\n"
        "Use `git commit -m` and non-paged commands: an interactive editor, terminal emulator,\n"
        "Git GUI/gitk launch workflow, and interactive credential services are not qualified.\n\n"
        "The configured `winsymlinks:sys` links have MSYS POSIX semantics. Windows/UCRT\n"
        "applications do not necessarily dereference them: do not treat them as native\n"
        "Windows symlinks or claim Git symlink checkout/compiler-source-link compatibility.\n\n"
        "## Explicit limitations\n\n" + "".join(f"- {item}\n" for item in assembly["limitations"]) +
        "".join(f"- {item}\n" for item in spec.get("evidence_limitations", [])) +
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
        row["entry_type"] = "regular-file"
        row["archive_mode"] = "0100644"
        row["reparse_point"] = False
        if name in assembly["files"]:
            row["provenance"] = enrich(assembly["files"][name]["provenance"])
            row["original_alias"] = assembly["files"][name].get("alias")
        else:
            row["provenance"] = {"source": source, "role": "artifact manifest, evidence or recreation tooling"}
            row["original_alias"] = None
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
               "limitations": assembly["limitations"] + spec.get("evidence_limitations", [])})
    print(json.dumps(first))


if __name__ == "__main__":
    main()
