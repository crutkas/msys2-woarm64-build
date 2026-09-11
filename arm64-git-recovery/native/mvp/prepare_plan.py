"""Derive a runtime-only MVP assembly plan from explicit package handoffs; no installed bootstrap copy."""

import argparse
import json
from pathlib import Path
import tarfile

from artifact import ArtifactError, bound_json, safe_path, sha256, write_json


def runtime_file(name, group):
    low = name.lower()
    if low.endswith((".a", ".la", ".pdb", ".debug", ".o", ".obj", ".pc")):
        return False
    if "/include/" in low or "/cmake/" in low or "/libexec/gcc/" in low or "/lib/gcc/" in low or "/aarch64-w64-mingw32/" in low:
        return False
    if group == "git":
        return True
    if group == "network":
        return (low.endswith(".dll") or "/share/licenses/" in low or "/share/ca-certificates/" in low or
                "/ssl/certs/" in low or "/etc/ssl/" in low or "/etc/pki/" in low or
                low in ("mingwarm64/bin/curl.exe", "mingwarm64/bin/openssl.exe"))
    if group == "python":
        return (runtime_file(name, "network") or low.startswith(("mingwarm64/lib/python3.", "mingwarm64/lib/tcl",
                                                               "mingwarm64/lib/tk", "mingwarm64/share/zoneinfo")) or
                low.startswith("mingwarm64/bin/python"))
    if group == "msys":
        return low.startswith(("usr/bin/", "usr/share/licenses/", "usr/share/terminfo/", "etc/")) and not low.endswith("msys-2.0.dll")
    raise ArtifactError("Unknown package selection group")


def add_package(plan, package, receipt, group, source, skip=()):
    path = Path(package["path"])
    if not path.is_absolute():
        path = Path(receipt["path"]).parent / path
    if sha256(path) != package["sha256"]:
        raise ArtifactError("Package input does not match published receipt")
    names, links = [], []
    with tarfile.open(path, "r:*") as archive:
        for item in archive:
            if item.isdir() or item.name.startswith("."):
                continue
            name = safe_path(item.name)
            if runtime_file(name, group) and name not in skip:
                names.append(name)
                if item.issym():
                    links.append(name)
    if not names:
        return
    plan["components"].append({
        "id": package.get("name", path.name), "kind": "package", "path": str(path),
        "sha256": package["sha256"], "include_files": names, "materialize_symlinks": links,
        "receipts": [receipt], "provenance": {"package": package.get("name", path.name),
            "archive_sha256": package["sha256"], "source": source,
            "admission_receipt_sha256": receipt["sha256"], "scope": "Published package payload; new-runtime and workflow qualification is recorded separately"}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    plan = {"schema": 1, "top_source": spec["top_source"], "components": [], "limitations": spec["limitations"],
            "classification": spec.get("classification", "assembled-not-behavior-qualified")}
    git = bound_json(spec["git"])
    for package in git["build"]["packages"]:
        add_package(plan, {"name": package["packageName"], "path": str(Path(spec["git"]["path"]).parent / "git-packages" / package["file"]),
                          "sha256": package["sha256"]}, spec["git"], "git",
                    {"repository": "https://github.com/git-for-windows/git", "commit": git["source"]["commit"],
                     "ref": git["source"]["tag"], "tree": spec["git_source_tree"]})
    network = bound_json(spec["network"])
    rejected = {"mingw-w64-aarch64-gettext", "mingw-w64-aarch64-libiconv", "mingw-w64-aarch64-libssh2",
                "mingw-w64-aarch64-curl-gnutls", "mingw-w64-aarch64-curl-winssl", "rust", "cmake", "pkgconf"}
    seen = {component["sha256"] for component in plan["components"]}
    for package in network["packages"]:
        if package["name"] in rejected:
            continue
        add_package(plan, package, spec["network"], "network",
                    {"repository": "https://github.com/Windows-on-ARM-Experiments/MINGW-packages",
                     "commit": network["pinned_recipe"]["commit"], "tree": None,
                     "identity_role": "pinned recipe; upstream archive identities remain in admission receipt"})
        seen.add(package["sha256"])
    python = bound_json(spec["python"])
    for package in python["packages"]:
        if package["sha256"] in seen or package["name"] in rejected:
            continue
        add_package(plan, package, spec["python"], "python",
                    {"repository": "https://github.com/Windows-on-ARM-Experiments/MINGW-packages",
                     "commit": git["providers"]["runtimeRecipeCommit"], "tree": None,
                     "identity_role": "provider recipe; exact upstream archive in package admission"})
    for item in spec["msys_exports"]:
        export = bound_json(item)
        for package in export["packages"]:
            if "name" not in package:
                package = dict(package)
                path = Path(package["path"])
                if not path.is_absolute():
                    path = Path(item["path"]).parent / path
                if sha256(path) != package["sha256"]:
                    raise ArtifactError("Unnamed package identity differs")
                with tarfile.open(path, "r:*") as archive:
                    info = archive.extractfile(".PKGINFO").read().decode("utf-8")
                names = [line.split(" = ", 1)[1] for line in info.splitlines() if line.startswith("pkgname = ")]
                if len(names) != 1:
                    raise ArtifactError("Package does not identify exactly one real pkgname")
                package["name"] = names[0]
            if package["name"].endswith(("-devel", "-debug")) or package["name"] == "msys2-runtime":
                continue
            add_package(plan, package, item, "msys", item["source"])
    for component in spec["extra_components"]:
        plan["components"].append(component)
    write_json(args.output, plan)
    print(f"Prepared {len(plan['components'])} explicitly sourced runtime components")


if __name__ == "__main__":
    main()
