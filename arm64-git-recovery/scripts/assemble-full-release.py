"""Audit and assemble a hash-bound full native ARM64 Git for Windows release."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tarfile
import tempfile
import re
import zipfile


PE_SUFFIXES = {".exe", ".dll", ".pyd", ".ocx", ".cpl", ".scr"}
PACKAGE_METADATA = {".BUILDINFO", ".INSTALL", ".MTREE", ".PKGINFO"}
API_SET_PREFIXES = ("api-ms-win-", "ext-ms-win-")


class ContractError(RuntimeError):
    pass


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def safe_relative(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ContractError(f"Unsafe archive path: {value}")
    return path.as_posix()


def safe_symlink_target(link_path: str, target: str) -> str:
    target_path = PurePosixPath(target.replace("\\", "/"))
    if target_path.is_absolute():
        raise ContractError(f"Unsafe archive link target: {link_path} -> {target}")
    resolved = posixpath.normpath(
        (PurePosixPath(link_path).parent / target_path).as_posix()
    )
    try:
        return safe_relative(resolved)
    except ContractError as error:
        raise ContractError(
            f"Unsafe archive link target: {link_path} -> {target}"
        ) from error


def verify_reference(reference: dict, label: str) -> tuple[Path, dict]:
    path = Path(reference.get("path", ""))
    expected = reference.get("sha256", "").lower()
    if not path.is_file():
        raise ContractError(f"{label} is missing: {path}")
    actual = digest(path)
    if actual != expected:
        raise ContractError(f"{label} hash mismatch: expected {expected}, got {actual}")
    return path, read_json(path)


def verify_nested_reference(parent_path: Path, reference: dict,
                            label: str) -> tuple[Path, dict]:
    if not isinstance(reference, dict):
        raise ContractError(f"{label} must be a structured path/SHA-256 reference")
    relative = safe_relative(str(reference.get("path", "")))
    expected = str(reference.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ContractError(f"{label} must declare a full SHA-256")
    base = parent_path.parent.resolve()
    path = (base / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        path.relative_to(base)
    except ValueError as error:
        raise ContractError(f"{label} escapes its evidence directory: {relative}") from error
    if not path.is_file():
        raise ContractError(f"{label} is missing: {path}")
    actual = digest(path)
    if actual != expected:
        raise ContractError(f"{label} hash mismatch: expected {expected}, got {actual}")
    return path, read_json(path)


def validate_nested_evidence(
    document_path: Path,
    evidence_items: object,
    label: str,
    required_kinds: list[str],
    execution_targets: list[str],
    runtime_cohort: object,
    package: str | None = None,
    version: str | None = None,
) -> list[dict]:
    if not isinstance(runtime_cohort, str) or not runtime_cohort:
        raise ContractError(f"{label} must declare a runtime_cohort")
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ContractError(f"{label} must cite nonempty structured evidence")
    allowed_kinds = set(required_kinds)
    if not allowed_kinds:
        raise ContractError(f"{label} contract has no required evidence kinds")
    allowed_targets = set(execution_targets)
    if not allowed_targets:
        raise ContractError(f"{label} contract has no execution targets")
    found_kinds = set()
    receipts = []
    for index, reference in enumerate(evidence_items):
        receipt_path, receipt = verify_nested_reference(
            document_path, reference, f"{label} receipt {index + 1}"
        )
        kind = receipt.get("kind")
        if kind not in allowed_kinds:
            raise ContractError(f"{label} receipt has invalid kind: {kind!r}")
        if reference.get("kind") != kind:
            raise ContractError(f"{label} receipt kind does not match its reference")
        if receipt.get("schema") != 1 or receipt.get("status") != "verified":
            raise ContractError(f"{label} receipt is not schema-1 verified evidence")
        execution = receipt.get("execution")
        if not isinstance(execution, dict):
            raise ContractError(f"{label} receipt has no execution evidence")
        if execution.get("native_process") is not True:
            raise ContractError(f"{label} receipt did not execute as a native process")
        if execution.get("host_architecture") != "arm64":
            raise ContractError(f"{label} receipt did not execute on ARM64")
        if execution.get("target") not in allowed_targets:
            raise ContractError(
                f"{label} receipt has foreign execution target: "
                f"{execution.get('target')!r}"
            )
        runtime = receipt.get("runtime")
        if not isinstance(runtime, dict):
            raise ContractError(f"{label} receipt has no runtime evidence")
        if runtime.get("cohort") != runtime_cohort:
            raise ContractError(f"{label} receipt has a foreign runtime cohort")
        runtime_sha256 = str(runtime.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", runtime_sha256):
            raise ContractError(f"{label} receipt has no runtime SHA-256 identity")
        if package is not None and (
            receipt.get("package") != package or receipt.get("version") != version
        ):
            raise ContractError(f"{label} receipt package/version mismatch")
        found_kinds.add(kind)
        receipts.append({
            "kind": kind,
            "name": receipt_path.name,
            "sha256": reference["sha256"].lower(),
            "execution_target": execution["target"],
            "runtime_cohort": runtime_cohort,
            "runtime_sha256": runtime_sha256,
        })
    missing = allowed_kinds - found_kinds
    if missing:
        raise ContractError(f"{label} is missing evidence kinds: {sorted(missing)}")
    return receipts


def parse_pkginfo(data: bytes) -> dict:
    values: dict[str, list[str]] = {}
    for raw in data.decode("utf-8", errors="strict").splitlines():
        if " = " not in raw:
            continue
        key, value = raw.split(" = ", 1)
        values.setdefault(key, []).append(value)
    try:
        name = values["pkgname"][0]
        version = values["pkgver"][0]
    except (KeyError, IndexError) as exc:
        raise ContractError("Package archive has incomplete .PKGINFO") from exc
    return {
        "name": name,
        "version": version,
        "arch": values.get("arch", [""])[0],
        "depends": values.get("depend", []),
        "provides": values.get("provides", []),
        "conflicts": values.get("conflict", []),
        "licenses": values.get("license", []),
    }


def dependency_name(value: str) -> str:
    for operator in (">=", "<=", "=", ">", "<"):
        if operator in value:
            return value.split(operator, 1)[0]
    return value


def version_parts(value: str) -> tuple[int, str, str]:
    epoch_text, separator, remainder = value.partition(":")
    if separator:
        epoch = int(epoch_text)
    else:
        epoch = 0
        remainder = epoch_text
    version, separator, release = remainder.rpartition("-")
    if not separator:
        version, release = remainder, ""
    return epoch, version, release


def version_tokens(value: str) -> list[tuple[bool, str]]:
    return [
        (token[0].isdigit(), token)
        for token in re.findall(r"[A-Za-z]+|[0-9]+", value)
    ]


def compare_version_field(left: str, right: str) -> int:
    left_tokens = version_tokens(left)
    right_tokens = version_tokens(right)
    for index in range(max(len(left_tokens), len(right_tokens))):
        if index >= len(left_tokens):
            return -1
        if index >= len(right_tokens):
            return 1
        left_numeric, left_value = left_tokens[index]
        right_numeric, right_value = right_tokens[index]
        if left_numeric != right_numeric:
            return 1 if left_numeric else -1
        if left_numeric:
            left_value = left_value.lstrip("0") or "0"
            right_value = right_value.lstrip("0") or "0"
            if len(left_value) != len(right_value):
                return 1 if len(left_value) > len(right_value) else -1
        if left_value != right_value:
            return 1 if left_value > right_value else -1
    return 0


def compare_versions(left: str, right: str) -> int:
    left_epoch, left_version, left_release = version_parts(left)
    right_epoch, right_version, right_release = version_parts(right)
    if left_epoch != right_epoch:
        return 1 if left_epoch > right_epoch else -1
    comparison = compare_version_field(left_version, right_version)
    if comparison or not left_release or not right_release:
        return comparison
    return compare_version_field(left_release, right_release)


def version_satisfies(actual: str, requirement: str) -> bool:
    for operator in (">=", "<=", "=", ">", "<"):
        if operator not in requirement:
            continue
        _, expected = requirement.split(operator, 1)
        comparison = compare_versions(actual, expected)
        return {
            ">=": comparison >= 0,
            "<=": comparison <= 0,
            "=": comparison == 0,
            ">": comparison > 0,
            "<": comparison < 0,
        }[operator]
    return True


def pe_info(data: bytes) -> dict | None:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ContractError("Malformed PE image")
    machine, sections, _, _, _, optional_size = struct.unpack_from(
        "<HHIIIH", data, pe_offset + 4
    )
    optional = pe_offset + 24
    if optional + optional_size > len(data):
        raise ContractError("Truncated PE optional header")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        directory_offset = optional + 112
        image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10B:
        directory_offset = optional + 96
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ContractError(f"Unsupported PE optional header 0x{magic:04x}")
    section_offset = optional + optional_size
    section_rows = []
    for index in range(sections):
        offset = section_offset + index * 40
        if offset + 40 > len(data):
            raise ContractError("Truncated PE section table")
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        section_rows.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def rva_offset(rva: int) -> int:
        for virtual_address, size, raw_pointer in section_rows:
            if virtual_address <= rva < virtual_address + size:
                return raw_pointer + rva - virtual_address
        raise ContractError(f"PE RVA 0x{rva:x} is outside sections")

    imports = []
    managed = False
    if directory_offset + 15 * 8 <= optional + optional_size:
        import_rva, import_size = struct.unpack_from("<II", data, directory_offset + 8)
        clr_rva, clr_size = struct.unpack_from("<II", data, directory_offset + 14 * 8)
        managed = bool(clr_rva and clr_size)
        if import_rva and import_size:
            descriptor = rva_offset(import_rva)
            while descriptor + 20 <= len(data):
                fields = struct.unpack_from("<IIIII", data, descriptor)
                if not any(fields):
                    break
                name_offset = rva_offset(fields[3])
                end = data.find(b"\0", name_offset)
                if end < 0:
                    raise ContractError("Unterminated PE import name")
                imports.append(data[name_offset:end].decode("ascii", errors="strict"))
                descriptor += 20
        delay_rva, delay_size = struct.unpack_from(
            "<II", data, directory_offset + 13 * 8
        )
        if delay_rva and delay_size:
            descriptor = rva_offset(delay_rva)
            while descriptor + 32 <= len(data):
                fields = struct.unpack_from("<IIIIIIII", data, descriptor)
                if not any(fields):
                    break
                name_rva = fields[1] if fields[0] & 1 else fields[1] - image_base
                name_offset = rva_offset(name_rva)
                end = data.find(b"\0", name_offset)
                if end < 0:
                    raise ContractError("Unterminated PE delay-import name")
                imports.append(data[name_offset:end].decode("ascii", errors="strict"))
                descriptor += 32
    return {
        "machine": f"0x{machine:04x}",
        "optional_magic": f"0x{magic:04x}",
        "managed": managed,
        "imports": sorted(set(imports), key=str.casefold),
    }


def inspect_archive(path: Path, expected_sha256: str, declared_name: str | None = None) -> dict:
    if not path.is_file():
        raise ContractError(f"Package archive is missing: {path}")
    actual_hash = digest(path)
    if actual_hash != expected_sha256.lower():
        raise ContractError(
            f"Package hash mismatch for {path.name}: expected {expected_sha256}, got {actual_hash}"
        )
    files: dict[str, dict] = {}
    links: dict[str, str] = {}
    pkginfo = None
    with tarfile.open(path, "r:*") as archive:
        for member in archive.getmembers():
            rel = safe_relative(member.name)
            if rel in PACKAGE_METADATA:
                if rel == ".PKGINFO":
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise ContractError(f"Cannot read .PKGINFO from {path.name}")
                    pkginfo = parse_pkginfo(extracted.read())
                continue
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                links[rel] = {
                    "target": member.linkname,
                    "kind": "symlink" if member.issym() else "hardlink",
                }
                continue
            if not member.isfile():
                raise ContractError(f"Unsupported package member type: {path.name}:{rel}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ContractError(f"Cannot read package member: {path.name}:{rel}")
            data = extracted.read()
            files[rel] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "data": data,
            }
    if pkginfo is None:
        raise ContractError(f"Package archive has no .PKGINFO: {path.name}")
    if declared_name and pkginfo["name"] != declared_name:
        raise ContractError(
            f"Package identity mismatch for {path.name}: {declared_name} != {pkginfo['name']}"
        )
    return {
        **pkginfo,
        "archive": path,
        "archive_name": path.name,
        "archive_sha256": actual_hash,
        "files": files,
        "links": links,
    }


def generic_packages(export_path: Path, export: dict, role: str) -> list[dict]:
    if export.get("schema") != 1:
        raise ContractError(f"Provider export must use schema 1: {export_path.name}")
    status = str(export.get("status", "")).casefold()
    if not any(word in status for word in ("admitted", "complete", "exported", "verified")):
        raise ContractError(f"Provider export is not admitted: {export_path.name}")
    packages = export.get("packages")
    if not isinstance(packages, list):
        raise ContractError(f"Provider export has no package list: {export_path.name}")
    result = []
    for item in packages:
        if not isinstance(item, dict):
            raise ContractError(f"Provider package row must be an object: {export_path.name}")
        path_value = item.get("path")
        archive_value = item.get("archive")
        if path_value and archive_value and path_value != archive_value:
            raise ContractError(
                f"Provider package row has conflicting path/archive: {export_path.name}"
            )
        path_value = path_value or archive_value
        if not isinstance(path_value, str) or not path_value:
            raise ContractError(
                f"Provider package row has no path/archive: {export_path.name}"
            )
        name_value = item.get("name")
        package_name_value = item.get("packageName")
        if name_value and package_name_value and name_value != package_name_value:
            raise ContractError(
                f"Provider package row has conflicting name/packageName: {export_path.name}"
            )
        package_path = Path(path_value)
        if not package_path.is_absolute():
            package_path = export_path.parent / package_path
        declared_name = name_value or package_name_value
        if not isinstance(declared_name, str) or not declared_name.startswith(
            ("mingw-w64-", "msys2-runtime")
        ):
            declared_name = None
        sha256 = str(item.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ContractError(
                f"Provider package row has no full SHA-256: {export_path.name}"
            )
        result.append({
            "name": declared_name,
            "path": package_path,
            "sha256": sha256,
            "role": role,
        })
    return result


def git_package_records(git: dict) -> list[dict]:
    legacy = git.get("build", {}).get("packages")
    current = git.get("packages")
    if legacy is not None and current is not None:
        raise ContractError("Git handoff declares both legacy and current package lists")
    records = legacy if legacy is not None else current
    if not isinstance(records, list):
        raise ContractError("Git package handoff has no package list")
    return records


def git_package_identity(item: dict) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        raise ContractError("Git package handoff has invalid package entry")
    name = item.get("packageName") or item.get("name")
    path = item.get("file") or item.get("archive") or item.get("path")
    archive_hash = str(item.get("sha256", "")).lower()
    if not isinstance(name, str) or not name:
        raise ContractError("Git package handoff package has no name")
    if not isinstance(path, str) or not path:
        raise ContractError(f"Git package handoff package has no path: {name}")
    if not re.fullmatch(r"[0-9a-f]{64}", archive_hash):
        raise ContractError(f"Git package handoff package has invalid SHA-256: {name}")
    return name, path, archive_hash


def git_package_hashes(git: dict) -> dict[str, str]:
    result = {}
    for item in git_package_records(git):
        name, _, archive_hash = git_package_identity(item)
        if name in result:
            raise ContractError(f"Git package handoff repeats package: {name}")
        result[name] = archive_hash
    return result


def resolve_git_source_identity(git: dict) -> tuple[dict, list[dict]]:
    source = dict(git.get("source", {}))
    if source.get("recipeSha256"):
        return source, []
    prior_reference = git.get("immutablePriorHandoff")
    if not isinstance(prior_reference, dict) or prior_reference.get("preserved") is not True:
        raise ContractError(
            "Git handoff without recipe identity must bind an immutable preserved prior handoff"
        )
    prior_path, prior = verify_reference(prior_reference, "Prior Git package handoff")
    prior_source = prior.get("source", {})
    for field in ("tag", "commit", "makepkgArchiveSha256"):
        if source.get(field) != prior_source.get(field):
            raise ContractError(f"Corrected Git handoff changed source {field}")
    recipe_hash = prior_source.get("recipeSha256")
    if not isinstance(recipe_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", recipe_hash):
        raise ContractError("Prior Git package handoff has no recipe identity")
    prior_hashes = git_package_hashes(prior)
    current_hashes = git_package_hashes(git)
    if set(prior_hashes) != set(current_hashes):
        raise ContractError("Corrected Git handoff changed the exact Git split set")
    changed = sorted(
        name for name in current_hashes if current_hashes[name] != prior_hashes[name]
    )
    if changed:
        integration = git.get("gitP4Integration", {})
        if changed != ["mingw-w64-aarch64-git-p4"]:
            raise ContractError("Corrected Git handoff changed packages other than git-p4")
        if (
            integration.get("oldArchiveSha256") != prior_hashes[changed[0]]
            or integration.get("newArchiveSha256") != current_hashes[changed[0]]
            or integration.get("declaredDependency") != "mingw-w64-aarch64-python"
        ):
            raise ContractError("Corrected git-p4 provenance does not match package hashes")
    source["recipeSha256"] = recipe_hash.lower()
    return source, [{
        "role": "git-source-provenance",
        "name": prior_path.name,
        "sha256": prior_reference["sha256"].lower(),
    }]


def validate_source_identity(
    contract: dict, git: dict, network: dict, git_source: dict | None = None
) -> None:
    expected = contract.get("source_identity")
    if not expected:
        return
    git_source = git_source or git.get("source", {})
    checks = {
        "Git tag": (git_source.get("tag"), expected["git_tag"]),
        "Git commit": (git_source.get("commit"), expected["git_commit"]),
        "Git recipe": (git_source.get("recipeSha256"), expected["git_recipe_sha256"]),
        "network recipe commit": (
            network.get("pinned_recipe", {}).get("commit"),
            expected["network_recipe_commit"],
        ),
    }
    for label, (actual, wanted) in checks.items():
        if actual != wanted:
            raise ContractError(f"{label} identity mismatch: {actual!r} != {wanted!r}")


def collect_declared_packages(input_path: Path, input_data: dict,
                              contract: dict) -> tuple[list[dict], list[dict]]:
    if input_data.get("schema") != 1:
        raise ContractError("Release input must use schema 1")
    references = []
    declarations = []
    git_path, git = verify_reference(input_data["git_handoff"], "Git package handoff")
    references.append({"role": "git", "name": git_path.name,
                       "sha256": input_data["git_handoff"]["sha256"].lower()})
    git_records = git_package_records(git)
    package_dir = (
        git_path.parent / "git-packages"
        if git.get("build", {}).get("packages") is not None
        else git_path.parent
    )
    for item in git_records:
        name, archive_path, archive_hash = git_package_identity(item)
        declarations.append({
            "name": name,
            "path": package_dir / archive_path,
            "sha256": archive_hash,
            "role": "git-split",
        })
    runtime_dir = git_path.parent / "runtime-providers"
    for item in git.get("providers", {}).get("runtimePackages", []):
        declarations.append({
            "name": None,
            "path": runtime_dir / item["file"],
            "sha256": item["sha256"],
            "role": "network-runtime",
        })
    network_path, network = verify_reference(
        input_data["network_export"], "Network package export"
    )
    git_source, provenance_references = resolve_git_source_identity(git)
    references.extend(provenance_references)
    validate_source_identity(contract, git, network, git_source)
    references.append({"role": "network", "name": network_path.name,
                       "sha256": input_data["network_export"]["sha256"].lower()})
    declarations.extend(generic_packages(network_path, network, "network-runtime"))
    for reference in input_data.get("provider_exports", []):
        provider_path, provider = verify_reference(reference, "Additional provider export")
        references.append({"role": reference.get("role", "provider"),
                           "name": provider_path.name, "sha256": reference["sha256"].lower()})
        declarations.extend(generic_packages(
            provider_path, provider, reference.get("role", "provider")
        ))
    return declarations, references


def load_packages(declarations: list[dict]) -> dict[str, dict]:
    packages = {}
    archive_hashes = {}
    for declaration in declarations:
        package = inspect_archive(
            Path(declaration["path"]), declaration["sha256"], declaration.get("name")
        )
        name = package["name"]
        existing_hash = archive_hashes.get(name)
        if existing_hash and existing_hash != package["archive_sha256"]:
            raise ContractError(f"Conflicting archives declare package {name}")
        package["roles"] = sorted(set(
            packages.get(name, {}).get("roles", []) + [declaration["role"]]
        ))
        packages[name] = package
        archive_hashes[name] = package["archive_sha256"]
    return packages


def provider_index(packages: dict[str, dict]) -> dict[str, list[str]]:
    providers: dict[str, list[str]] = {}
    for name, package in packages.items():
        providers.setdefault(name, []).append(name)
        for value in package["provides"]:
            providers.setdefault(dependency_name(value), []).append(name)
    return providers


def resolve_packages(packages: dict[str, dict], roots: list[str],
                     preferred: dict[str, str]) -> tuple[set[str], list[str]]:
    providers = provider_index(packages)
    selected: set[str] = set()
    blockers: set[str] = set()
    pending = list(roots)
    while pending:
        requirement = dependency_name(pending.pop(0))
        candidates = providers.get(requirement, [])
        preferred_name = preferred.get(requirement)
        if preferred_name:
            candidates = [name for name in candidates if name == preferred_name]
        if not candidates:
            blockers.add(requirement)
            continue
        if len(candidates) != 1:
            raise ContractError(
                f"Ambiguous provider for {requirement}: {sorted(candidates)}"
            )
        name = candidates[0]
        if name in selected:
            continue
        selected.add(name)
        pending.extend(packages[name]["depends"])
    for name in selected:
        conflicts = packages[name]["conflicts"]
        for other in selected:
            if other == name:
                continue
            provided = {
                other: packages[other]["version"],
                **{
                    dependency_name(value): (
                        value.split("=", 1)[1] if "=" in value else packages[other]["version"]
                    )
                    for value in packages[other]["provides"]
                },
            }
            for conflict in conflicts:
                provider_version = provided.get(dependency_name(conflict))
                if provider_version and version_satisfies(provider_version, conflict):
                    raise ContractError(
                        f"Selected package conflict: {name} conflicts with {other}"
                    )
    return selected, sorted(blockers)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def include_payload_file(package: dict, rel: str, contract: dict) -> bool:
    if matches_any(rel, contract.get("excluded_payload_globs", [])):
        return False
    if "git-split" in package["roles"]:
        return True
    role_patterns = contract.get("provider_role_payload_globs", {})
    filtered_roles = [role for role in package["roles"] if role in role_patterns]
    if not filtered_roles:
        return True
    return (
        rel in contract["required_files"]
        or any(matches_any(rel, role_patterns[role]) for role in filtered_roles)
    )


def merge_payload(packages: dict[str, dict], selected: set[str],
                  contract: dict) -> tuple[dict, dict]:
    files = {}
    links = {}
    folded = {}
    for name in sorted(selected):
        package = packages[name]
        for rel, record in package["files"].items():
            if not include_payload_file(package, rel, contract):
                continue
            key = rel.casefold()
            if key in folded and folded[key] != rel:
                raise ContractError(f"Case-insensitive payload collision: {folded[key]} vs {rel}")
            folded[key] = rel
            if rel in files and files[rel]["sha256"] != record["sha256"]:
                raise ContractError(f"Conflicting package payload: {rel}")
            if rel not in files:
                files[rel] = {**record, "owners": [name]}
            else:
                files[rel]["owners"].append(name)
        for rel, link in package["links"].items():
            if not include_payload_file(package, rel, contract):
                continue
            if rel in files or (rel in links and links[rel]["target"] != link["target"]):
                raise ContractError(f"Conflicting package link: {rel}")
            links.setdefault(rel, {**link, "owners": []})["owners"].append(name)
    unresolved = dict(links)
    while unresolved:
        progress = False
        for rel, link in list(unresolved.items()):
            if link["kind"] == "hardlink":
                candidates = [safe_relative(link["target"])]
            else:
                candidates = [safe_symlink_target(rel, link["target"])]
            target = next((candidate for candidate in candidates if candidate in files), None)
            if target is not None:
                files[rel] = {
                    **files[target],
                    "owners": sorted(set(files[target]["owners"] + link["owners"])),
                    "materialized_from": target,
                }
                del unresolved[rel]
                progress = True
                continue

            directory_target = next(
                (
                    candidate
                    for candidate in candidates
                    if any(path.startswith(candidate.rstrip("/") + "/") for path in files)
                ),
                None,
            )
            if directory_target is None:
                continue
            target_prefix = directory_target.rstrip("/") + "/"
            linked_files = [
                (path, record)
                for path, record in files.items()
                if path.startswith(target_prefix)
            ]
            for source_path, record in linked_files:
                destination = safe_relative(
                    rel.rstrip("/") + "/" + source_path[len(target_prefix):]
                )
                if destination in files and files[destination]["sha256"] != record["sha256"]:
                    raise ContractError(f"Conflicting package payload: {destination}")
                existing_owners = files.get(destination, {}).get("owners", [])
                files[destination] = {
                    **record,
                    "owners": sorted(
                        set(existing_owners + record["owners"] + link["owners"])
                    ),
                    "materialized_from": source_path,
                }
            del unresolved[rel]
            progress = True
        if not progress:
            sample = next(iter(unresolved.items()))
            raise ContractError(f"Unresolved package link: {sample[0]} -> {sample[1]['target']}")
    links.clear()
    return files, links


def validate_git_splits(contract: dict, packages: dict[str, dict]) -> list[str]:
    expected = set(contract["expected_git_splits"])
    actual = {name for name in packages if name.startswith("mingw-w64-aarch64-git")}
    missing = sorted(expected - actual)
    unexpected = sorted(
        name for name in actual - expected
        if name not in {"mingw-w64-aarch64-git-extra",
                        "mingw-w64-aarch64-git-credential-manager",
                        "mingw-w64-aarch64-git-lfs"}
    )
    if unexpected:
        raise ContractError(f"Unexpected Git split packages: {unexpected}")
    return [f"missing-git-split:{name}" for name in missing]


def validate_payload(contract: dict, files: dict, selected: set[str],
                     self_hosting: dict | None) -> tuple[list[str], dict]:
    blockers = []
    required_files = contract["required_files"]
    for rel in required_files:
        if rel not in files or files[rel]["size"] == 0:
            blockers.append(f"payload-file-not-supplied:{rel}")
    for pattern in contract["required_documentation_globs"]:
        if not any(fnmatch.fnmatchcase(path, pattern) for path in files):
            blockers.append(f"missing-documentation:{pattern}")
    for pattern in contract["required_license_globs"]:
        if not any(fnmatch.fnmatchcase(path, pattern) for path in files):
            blockers.append(f"missing-license:{pattern}")
    managed_allow = set(contract.get("managed_files", []))
    classifications = {"native_pe_arm64": [], "managed_pe": [], "script": [], "data": []}
    dlls: dict[str, list[str]] = {}
    imports: dict[str, list[str]] = {}
    forbidden = [value.casefold().encode("utf-8")
                 for value in contract["forbidden_payload_markers"]]
    nonrelease = [value.casefold().encode("utf-8")
                  for value in contract["forbidden_nonrelease_markers"]]
    for rel, record in files.items():
        data = record["data"]
        info = pe_info(data)
        if info:
            lower_data = data.lower()
            for marker in nonrelease:
                if marker in lower_data:
                    blockers.append(
                        f"nonrelease-marker:{rel}:"
                        f"{marker.decode('utf-8', errors='replace')}"
                    )
            if info["managed"]:
                if rel not in managed_allow:
                    raise ContractError(f"Undeclared managed PE payload: {rel}")
                classifications["managed_pe"].append(rel)
            else:
                if info["machine"] != "0xaa64" or info["optional_magic"] != "0x020b":
                    raise ContractError(
                        f"Non-ARM64 shipped executable: {rel} "
                        f"{info['machine']} {info['optional_magic']}"
                    )
                classifications["native_pe_arm64"].append(rel)
                imports[rel] = info["imports"]
            if Path(rel).suffix.lower() == ".dll":
                dlls.setdefault(Path(rel).name.casefold(), []).append(rel)
        elif Path(rel).suffix.lower() in PE_SUFFIXES:
            raise ContractError(f"Executable extension without PE image: {rel}")
        else:
            is_text = b"\0" not in data[:8192]
            if is_text:
                try:
                    lower_data = data.decode("utf-8").casefold().encode("utf-8")
                except UnicodeDecodeError:
                    lower_data = b""
                for marker in (*forbidden, *nonrelease):
                    if marker in lower_data:
                        blockers.append(
                            f"private-path-or-marker:{rel}:"
                            f"{marker.decode('utf-8', errors='replace')}"
                        )
            if data.startswith(b"#!") or Path(rel).suffix.lower() in {
                ".sh", ".pl", ".pm", ".py", ".tcl", ".awk"
            }:
                classifications["script"].append(rel)
            else:
                classifications["data"].append(rel)
    system = {name.casefold() for name in contract["system_dlls"]}
    unresolved = {}
    for rel, names in imports.items():
        missing = []
        for name in names:
            folded = name.casefold()
            if folded.startswith(API_SET_PREFIXES) or folded in system:
                continue
            if folded not in dlls:
                missing.append(name)
            elif len({files[path]["sha256"] for path in dlls[folded]}) != 1:
                raise ContractError(f"Ambiguous DLL basename with different bytes: {name}")
        if missing:
            unresolved[rel] = sorted(missing, key=str.casefold)
    if unresolved:
        for rel, names in sorted(unresolved.items()):
            blockers.append(f"missing-dll:{rel}:{','.join(names)}")
    generated = contract["generated_gitconfig"]
    if generated["path"] in files:
        existing = files[generated["path"]]["data"].decode("utf-8", errors="replace")
        if "%(prefix)/mingwarm64/etc/ssl/certs/ca-bundle.crt" not in existing:
            blockers.append(f"non-relocatable-ca-config:{generated['path']}")
    if not self_hosting:
        blockers.append("missing-native-self-hosting-evidence")
    return sorted(set(blockers)), {
        key: sorted(values) for key, values in classifications.items()
    }


def validate_self_hosting(contract: dict, reference: dict) -> dict:
    evidence_path, evidence = verify_reference(
        reference, "Native self-hosting evidence"
    )
    expected = contract["self_hosting_evidence"]
    for key in ("schema", "status", "target"):
        if evidence.get(key) != expected[key]:
            raise ContractError(
                f"Native self-hosting evidence has invalid {key}: "
                f"{evidence.get(key)!r} != {expected[key]!r}"
            )
    receipts = validate_nested_evidence(
        evidence_path,
        evidence.get("evidence"),
        "Native self-hosting evidence",
        expected.get("required_evidence_kinds", []),
        expected.get("execution_targets", []),
        evidence.get("runtime_cohort"),
    )
    return {
        "name": evidence_path.name,
        "sha256": reference["sha256"].lower(),
        "status": evidence["status"],
        "target": evidence["target"],
        "runtime_cohort": evidence["runtime_cohort"],
        "receipts": receipts,
    }


def validate_managed_admissions(contract: dict, input_data: dict,
                                packages: dict[str, dict]) -> tuple[list[str], list[dict]]:
    supplied_references = input_data.get("managed_admissions", [])
    if not isinstance(supplied_references, list):
        raise ContractError("managed_admissions must be a list")
    references = {}
    for item in supplied_references:
        package_name = item.get("package")
        if package_name in references:
            raise ContractError(f"Duplicate managed admission: {package_name}")
        references[package_name] = item
    expected_packages = {
        component["package"] for component in contract.get("managed_components", [])
    }
    unknown = set(references) - expected_packages
    if unknown:
        raise ContractError(f"Unknown managed admissions: {sorted(unknown)}")
    blockers = []
    admitted = []
    for component in contract.get("managed_components", []):
        package_name = component["package"]
        reference = references.get(package_name)
        if not reference:
            blockers.append(f"managed-admission-not-supplied:{package_name}")
            continue
        path, evidence = verify_reference(reference, f"Managed admission {package_name}")
        if evidence.get("schema") != 1:
            raise ContractError(f"Managed admission must use schema 1: {package_name}")
        for key in (
            "admission_version", "status", "decision",
            "host_architecture", "runtime_support_status",
        ):
            if evidence.get(key) != component[key]:
                raise ContractError(
                    f"Managed admission {package_name} has invalid {key}: "
                    f"{evidence.get(key)!r} != {component[key]!r}"
                )
        package = packages.get(package_name)
        if not package:
            blockers.append(f"provider-not-supplied:{package_name}")
            continue
        if evidence.get("package") != package_name or evidence.get("version") != package["version"]:
            raise ContractError(f"Managed admission package/version mismatch: {package_name}")
        declared_files = evidence.get("files")
        if not isinstance(declared_files, list):
            raise ContractError(f"Managed admission has no file evidence: {package_name}")
        actual = {}
        for rel in component["files"]:
            record = package["files"].get(rel)
            if not record:
                blockers.append(f"payload-file-not-supplied:{rel}")
                continue
            actual[rel] = record["sha256"]
        supplied = {item.get("path"): item.get("sha256") for item in declared_files}
        if supplied != actual:
            raise ContractError(f"Managed admission file hashes differ: {package_name}")
        receipts = validate_nested_evidence(
            path,
            evidence.get("evidence"),
            f"Managed admission {package_name}",
            component.get("required_evidence_kinds", []),
            component.get("execution_targets", []),
            evidence.get("runtime_cohort"),
            package_name,
            package["version"],
        )
        admitted.append({
            "package": package_name,
            "version": package["version"],
            "name": path.name,
            "sha256": reference["sha256"].lower(),
            "host_architecture": evidence["host_architecture"],
            "runtime_support_status": evidence["runtime_support_status"],
            "runtime_cohort": evidence["runtime_cohort"],
            "receipts": receipts,
        })
    return blockers, admitted


def audit(input_path: Path, contract_path: Path) -> tuple[dict, dict, dict, set[str]]:
    contract = read_json(contract_path)
    if contract.get("schema") != 1:
        raise ContractError("Distribution contract must use schema 1")
    input_data = read_json(input_path)
    declarations, references = collect_declared_packages(input_path, input_data, contract)
    packages = load_packages(declarations)
    blockers = validate_git_splits(contract, packages)
    managed_blockers, managed_admissions = validate_managed_admissions(
        contract, input_data, packages
    )
    blockers.extend(managed_blockers)
    tls = input_data.get("tls")
    alternatives = contract["tls_alternatives"]
    if tls not in alternatives:
        raise ContractError(f"Select exactly one TLS alternative: {sorted(alternatives)}")
    chosen_curl = alternatives[tls]
    roots = [*contract["expected_git_splits"], *contract["required_packages"], chosen_curl]
    preferred = {"mingw-w64-aarch64-curl": chosen_curl}
    selected, missing_packages = resolve_packages(packages, roots, preferred)
    blockers.extend(f"provider-not-supplied:{name}" for name in missing_packages)
    selected_tls = set(alternatives.values()) & selected
    if selected_tls != {chosen_curl}:
        raise ContractError(f"TLS alternative collision: {sorted(selected_tls)}")
    files, links = merge_payload(packages, selected, contract)
    self_hosting = None
    if input_data.get("self_hosting_evidence"):
        self_hosting = validate_self_hosting(
            contract, input_data["self_hosting_evidence"]
        )
    payload_blockers, classifications = validate_payload(
        contract, files, selected, self_hosting
    )
    blockers.extend(payload_blockers)
    package_manifest = []
    for name in sorted(selected):
        package = packages[name]
        package_manifest.append({
            "name": name,
            "version": package["version"],
            "archive": package["archive_name"],
            "sha256": package["archive_sha256"],
            "depends": package["depends"],
            "provides": package["provides"],
            "conflicts": package["conflicts"],
            "file_count": len(package["files"]) + len(package["links"]),
        })
    report = {
        "schema": 1,
        "profile": contract["profile"],
        "status": "ready-to-assemble" if not blockers else "incomplete",
        "tls": tls,
        "input_manifests": references,
        "selected_packages": package_manifest,
        "selected_package_count": len(selected),
        "git_split_count": len(set(contract["expected_git_splits"]) & selected),
        "payload_file_count": len(files) + len(links),
        "classification_counts": {
            key: len(values) for key, values in classifications.items()
        },
        "classification_examples": {
            key: values[:20] for key, values in classifications.items()
        },
        "shipping_payload_status": "complete" if not [
            item for item in blockers if item != "missing-native-self-hosting-evidence"
        ] else "incomplete",
        "native_build_self_hosting_status": "verified" if self_hosting else "missing",
        "managed_component_admissions": managed_admissions,
        "managed_component_admission_status": (
            "verified" if not managed_blockers else "missing"
        ),
        "blockers": sorted(set(blockers)),
    }
    return report, packages, {**files, **links}, selected


def assemble(input_path: Path, contract_path: Path, output: Path) -> Path:
    report, packages, payload, selected = audit(input_path, contract_path)
    if report["blockers"]:
        raise ContractError("Release is incomplete: " + "; ".join(report["blockers"]))
    if output.exists():
        raise ContractError(f"Assembly output must be new: {output}")
    contract = read_json(contract_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{output.name}.assembling-", dir=output.parent))
    try:
        stage = work / "root"
        package_dir = work / "packages"
        stage.mkdir()
        package_dir.mkdir()
        owners: dict[str, list[str]] = {}
        for name in sorted(selected):
            package = packages[name]
            shutil.copyfile(package["archive"], package_dir / package["archive_name"])
        for rel, record in sorted(payload.items()):
            destination = stage / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(record["data"])
            if digest(destination) != record["sha256"]:
                raise ContractError(f"Payload changed during assembly: {rel}")
            owners[rel] = sorted(record["owners"])
        generated = contract["generated_gitconfig"]
        gitconfig = stage / generated["path"]
        if gitconfig.exists():
            text = gitconfig.read_text(encoding="utf-8")
            if generated["content"].strip() not in text:
                with gitconfig.open("a", encoding="utf-8", newline="\n") as stream:
                    if text and not text.endswith("\n"):
                        stream.write("\n")
                    stream.write(generated["content"])
        else:
            gitconfig.parent.mkdir(parents=True, exist_ok=True)
            gitconfig.write_text(generated["content"], encoding="utf-8", newline="\n")
        owners.setdefault(generated["path"], []).append("release-assembler")
        archive = work / contract["archive_name"]
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    zipped.write(path, path.relative_to(stage).as_posix())
        payload_manifest = {}
        managed = set(contract["managed_files"])
        for path in sorted(stage.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(stage).as_posix()
            data = path.read_bytes()
            info = pe_info(data)
            if info:
                kind = "managed-pe" if rel in managed else "native-pe-arm64"
            elif data.startswith(b"#!") or path.suffix.lower() in {
                ".sh", ".pl", ".pm", ".py", ".tcl", ".awk"
            }:
                kind = "script"
            else:
                kind = "data"
            payload_manifest[rel] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "kind": kind,
                "owners": sorted(owners[rel]),
            }
        report["status"] = "assembled-complete"
        report["archive"] = {
            "name": archive.name,
            "sha256": digest(archive),
            "bytes": archive.stat().st_size,
        }
        report["package_bundle"] = [
            {
                "name": packages[name]["archive_name"],
                "sha256": packages[name]["archive_sha256"],
            }
            for name in sorted(selected)
        ]
        report["payload"] = payload_manifest
        manifest = work / "release-manifest.json"
        write_json(manifest, report)
        work.replace(output)
        return output / manifest.name
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def verify_release(manifest_path: Path) -> dict:
    manifest = read_json(manifest_path)
    if manifest.get("status") != "assembled-complete":
        raise ContractError("Release manifest is not complete")
    root = manifest_path.parent
    archive_info = manifest["archive"]
    archive = root / archive_info["name"]
    if not archive.is_file() or digest(archive) != archive_info["sha256"]:
        raise ContractError("Release archive is missing or changed")
    expected = manifest["payload"]
    with zipfile.ZipFile(archive) as zipped:
        names = {name for name in zipped.namelist() if not name.endswith("/")}
        if names != set(expected):
            raise ContractError("Release archive path inventory differs")
        for rel, record in expected.items():
            data = zipped.read(rel)
            if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ContractError(f"Release archive payload changed: {rel}")
            info = pe_info(data)
            if record["kind"] == "native-pe-arm64":
                if not info or info["machine"] != "0xaa64" or info["optional_magic"] != "0x020b":
                    raise ContractError(f"Release native PE classification changed: {rel}")
            elif record["kind"] == "managed-pe":
                if not info or not info["managed"]:
                    raise ContractError(f"Release managed PE classification changed: {rel}")
    package_dir = root / "packages"
    expected_packages = {item["name"]: item["sha256"]
                         for item in manifest["package_bundle"]}
    actual_packages = {path.name: digest(path) for path in package_dir.iterdir()
                       if path.is_file()}
    if actual_packages != expected_packages:
        raise ContractError("Release package bundle inventory differs")
    return {
        "status": "verified",
        "archive": archive_info,
        "payload_files": len(expected),
        "packages": len(expected_packages),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract", type=Path,
        default=Path(__file__).resolve().parents[1] / "contracts" / "full-release-v1.json"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--input", type=Path, required=True)
    audit_parser.add_argument("--report", type=Path, required=True)
    assemble_parser = sub.add_parser("assemble")
    assemble_parser.add_argument("--input", type=Path, required=True)
    assemble_parser.add_argument("--output", type=Path, required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "audit":
            report, _, _, _ = audit(args.input, args.contract)
            write_json(args.report, report)
            print(args.report)
            return 0 if report["status"] == "ready-to-assemble" else 2
        if args.command == "assemble":
            manifest = assemble(args.input, args.contract, args.output)
            print(manifest)
        else:
            print(json.dumps(verify_release(args.manifest), sort_keys=True))
        return 0
    except (ContractError, KeyError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
