"""Adopt sealed SSH-only sources and reject configured feature loss."""

import json
from pathlib import Path
import re
import shutil

from sources import ContractError, digest, load_lock, verify_tree


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "ssh-recipes.json"


def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def prerequisite_closure(lock):
    rules = contract()
    pins = {row["id"]: row for row in lock["sources"]}
    graph = rules["transitive_source_closure"]
    visited, active, ordered = set(), set(), []

    def visit(name):
        if name in active:
            raise ContractError("SSH prerequisite graph contains a cycle")
        if name in visited:
            return
        if name not in pins or name not in graph:
            raise ContractError(f"SSH prerequisite lacks a canonical source pin: {name}")
        active.add(name)
        for dependency in graph[name]:
            visit(dependency)
        active.remove(name)
        visited.add(name)
        ordered.append(name)

    visit("openssh")
    test_ids = rules["parent_owned_test_source_ids"]
    if any(name not in pins for name in test_ids):
        raise ContractError("SSH closure lacks its parent-owned native test prerequisite pin")
    ancillary = []
    for requirement in rules["ancillary_source_requirements"]:
        matches = [pin for pin in pins.values()
                   if pin["sha256"] == requirement["sha256"] and pin["file"] == requirement["file"]
                   and ("id" not in requirement or pin["id"] == requirement["id"])]
        ancillary.append({**requirement, "status": "locked" if matches else "missing-from-canonical-lock",
                          "matching_source_ids": [pin["id"] for pin in matches]})
    return {
        "scope": "Exact source prerequisite closure and full-recipe gates; not native binary admission",
        "topological_build_order": ordered,
        "source_pins": [pins[name] for name in ordered],
        "parent_owned_test_source_pins": [pins[name] for name in test_ids],
        "source_dependencies": graph,
        "readline_package_version": rules["transitive_recipe_requirements"]["readline"]["package_version"],
        "ancillary_sources": ancillary,
        "tcl_recipe_binding": rules["transitive_recipe_requirements"]["tcl"],
        "nonlibrary_requirements": rules["nonlibrary_requirements"],
        "execution_boundary": rules["execution_boundary"],
    }


def validate_preparation(package, record, lock):
    rules = contract()
    profile = rules["profiles"].get(package)
    if profile is None:
        raise ContractError("Unsupported SSH source profile")
    pins = {row["id"]: row for row in lock["sources"]}
    recipes = rules["recipe_collection"]
    recipe_pin = pins.get(recipes["id"], {})
    if any(recipe_pin.get(key) != recipes[key] for key in ("version", "sha256")):
        raise ContractError("SSH recipe collection differs from the canonical source lock")
    if (record.get("source") != pins.get(package) or
            record.get("source", {}).get("version") != profile["version"] or
            record.get("recipe_sha256") != profile["recipe_sha256"] or
            record.get("recipe_manifest_sha256") != recipes["prepared_inventory_sha256"]):
        raise ContractError("SSH preparation does not match the pinned source and recipe")
    if (record.get("scope") != "prepared MSYS-target sources, not built" or
            record.get("dependency_abi") != "MSYS runtime; MinGW/UCRT libraries are not substitutes" or
            record.get("dependencies") != profile["dependencies"]):
        raise ContractError("SSH preparation changed its scope, ABI or dependency closure")
    generator = record.get("libtool_dependency")
    if profile.get("libtool_required") and (not isinstance(generator, dict) or not
            re.fullmatch("[0-9a-f]{64}", generator.get("manifest_sha256", ""))):
        raise ContractError("SSH shared-library preparation lacks a sealed MSYS libtool generator")
    steps = record.get("steps", [])
    if not steps or any(step.get("exit") != 0 for step in steps):
        raise ContractError("SSH preparation contains failed or incomplete generation")
    patches = [step for step in steps if "patch_sha256" in step]
    if len(patches) != len(profile["patches"]):
        raise ContractError("SSH patch sequence differs from the pinned preparation")
    for actual, expected in zip(patches, profile["patches"]):
        if (actual.get("patch_sha256") != expected["sha256"] or
                actual.get("upstream_patch_sha256") != expected["upstream_sha256"]):
            raise ContractError("SSH patch identity or order differs")
        if expected.get("local") and digest(HERE / "patches" / expected["local"]) != expected["sha256"]:
            raise ContractError("Maintained SSH patch bytes changed")
    if not any(step.get("command") == profile["generation"] for step in steps):
        raise ContractError("SSH source generation command is missing")
    files = record.get("files", {})
    if not files or any("symlink" in row for row in files.values()):
        raise ContractError("SSH adoption requires nonempty regular-file inputs; no symlink materialization")
    if "configure" not in files:
        raise ContractError("SSH preparation has no generated configure script")
    return profile


def adopt_source(package, source, manifest, expected_sha256, output, lock_path):
    source, manifest, output = map(Path, (source, manifest, output))
    if not re.fullmatch("[0-9a-f]{64}", expected_sha256) or digest(manifest) != expected_sha256:
        raise ContractError("SSH source receipt seal differs")
    if (output.exists() or output.is_symlink() or
            output.resolve().is_relative_to(source.resolve()) or
            source.resolve().is_relative_to(output.resolve())):
        raise ContractError("A fresh disjoint SSH adoption root is required")
    if any(path.is_symlink() or path.is_junction() for path in (output.parent, *output.parents)):
        raise ContractError("SSH adoption output may not traverse a link or junction")
    lock_sha = digest(lock_path)
    contract_sha = digest(CONTRACT_PATH)
    record = json.loads(manifest.read_text(encoding="utf-8"))
    profile = validate_preparation(package, record, load_lock(lock_path))
    verify_tree(source, manifest)
    output.mkdir(parents=True)
    report = {
        "schema": 1,
        "status": "failed",
        "scope": "Byte-identical SSH source adoption only; no native build/test/package admission",
        "package": package,
        "source": str(source.resolve()),
        "source_manifest": str(manifest.resolve()),
        "source_manifest_sha256": expected_sha256,
        "source_lock_sha256": lock_sha,
        "contract_sha256": contract_sha,
        "adopter_sha256": digest(HERE / "ssh_build_inputs.py"),
        "target_processes_launched": 0,
        "profile": profile,
    }
    try:
        shutil.copytree(source, output / "source", symlinks=True)
        shutil.copyfile(manifest, output / "source.prepare.json")
        if digest(output / "source.prepare.json") != expected_sha256:
            raise ContractError("SSH receipt changed during copy")
        verify_tree(output / "source", output / "source.prepare.json")
        verify_tree(source, manifest)
        if (digest(manifest) != expected_sha256 or digest(lock_path) != lock_sha or
                digest(CONTRACT_PATH) != contract_sha):
            raise ContractError("SSH sealed inputs changed during adoption")
        report.update(status="sealed-ssh-source-private-copy",
                      copied_files=len(record["files"]), old_source_unchanged=True)
    finally:
        with (output / "adoption.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    return report


def validate_openssh_configuration(config_text, makefile_text):
    """Inspect generated configuration only; never execute SSH or its tests."""
    required = contract()["profiles"]["openssh"]["required_defines"]
    defines = {}
    uncommented = re.sub(r"/\*.*?\*/", "", config_text, flags=re.DOTALL)
    for line in uncommented.splitlines():
        match = re.fullmatch(r"\s*#\s*(define|undef)\s+([A-Za-z_]\w*)(?:\s+(.*?))?\s*", line)
        if match:
            if match[1] == "define":
                defines[match[2]] = (match[3] or "").strip()
            else:
                defines.pop(match[2], None)
    missing = [name for name in required if name not in defines or defines[name] not in ("", "1")]
    if missing:
        raise ContractError(f"Configured OpenSSH lost required features: {missing}")
    variables = {}
    for line in makefile_text.replace("\\\n", " ").splitlines():
        match = re.fullmatch(r"([A-Z0-9_]+)\s*=\s*(.*)", line)
        if match:
            variables[match[1]] = match[2].split()
    requirements = {
        "LIBEDIT": ("-ledit",),
        "LIBFIDO2": ("-lfido2",),
        "K5LIBS": ("-lkrb5",),
        "GSSLIBS": ("-lgssapi",),
        "LIBS": ("-lcrypto", "-lz"),
        "SSHDLIBS": ("-lcrypt",),
    }
    for variable, libraries in requirements.items():
        if any(library not in variables.get(variable, []) for library in libraries):
            raise ContractError(f"Configured OpenSSH lost required {variable} link inputs: {libraries}")
    return {
        "scope": "Generated configuration/link intent only; not native binary, loaded-module or authentication acceptance",
        "required_defines": required,
        "link_inputs": {name: variables[name] for name in requirements},
    }
