"""Replace diagnostic candidates with exact, explicitly admitted limited-MVP projections."""

import argparse
import json
from pathlib import Path
import subprocess

from artifact import ArtifactError, bound_json, safe_path, sha256, write_json


def receipt(path):
    path = Path(path)
    return {"path": str(path), "sha256": sha256(path)}


def add_projection(plan, item):
    export = bound_json(item)
    accepted = {"admitted-limited-mvp-only-final", "admitted-limited-native-utilities-only-final"}
    if export.get("status") not in accepted:
        raise ArtifactError("Limited projection has no final admission")
    verdict = export.get("currentVerdict", export.get("verdict", {}))
    if verdict.get("limitedGitMvp", verdict.get("limitedArtifactProjection")) != "ADMITTED":
        raise ArtifactError("The limited artifact verdict is not admitted")
    files = export["payload"]["files"]
    for row in files:
        original = Path(export["exportRoot"]) / safe_path(row["path"])
        name = safe_path(row["path"].removeprefix("payload/"))
        if (row["path"] == name or not original.resolve().is_relative_to(Path(export["exportRoot"]).resolve() / "payload") or
                sha256(original) != row["sha256"]):
            raise ArtifactError("Admitted payload file changed or lacks its exact payload mapping")
        plan["components"].append({
            "id": export["exportRole"] + ":" + name, "kind": "file", "path": str(original),
            "sha256": row["sha256"], "destination": name, "receipts": [item],
            "provenance": {"source": {"repository": "published provider sources",
                                      "commit": None, "tree": None,
                                      "identity_role": "See exact admission source/archive records; unavailable commits are not inferred"},
                           "admission_receipt_sha256": item["sha256"], "admission_role": export["exportRole"],
                           "source_records": export.get("provenance", export.get("package", {})),
                           "limitations": export.get("limitations", [])}})
    plan["limitations"].extend(export.get("limitations", []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-plan", type=Path, required=True)
    parser.add_argument("--gettext-export", type=Path, required=True)
    parser.add_argument("--pcre-export", type=Path, required=True)
    parser.add_argument("--utilities-export", type=Path, required=True)
    parser.add_argument("--ssh-mode", choices=("portable-win32", "native-msys"), required=True)
    parser.add_argument("--ssh-handoff", type=Path)
    parser.add_argument("--ssh-admission", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    actual_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    actual_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "arm64-git-recovery/native/mvp",
                                     "arm64-git-recovery/native/bounded_process.py"], cwd=repository, text=True)
    if dirty or actual_commit != args.source_commit or actual_tree != args.source_tree:
        raise ArtifactError("A final limited assembly plan requires the exact clean committed recipe identity")
    plan = json.loads(args.base_plan.read_text(encoding="utf-8"))
    blocked_ids = {"native-coreutils-candidate", "official-win32-openssh-arm64",
                   "mingw-w64-clang-aarch64-gettext-runtime-1.0-1-any.pkg.tar.zst",
                   "mingw-w64-clang-aarch64-libiconv-1.19-1-any.pkg.tar.zst",
                   "mingw-w64-aarch64-pcre2"}
    plan["components"] = [component for component in plan["components"]
                          if component["id"] not in blocked_ids and not component["id"].startswith("mvp-entrypoints-")]
    plan["classification"] = "LIMITED-NATIVE-ENGINEERING-MVP-CANDIDATE-NOT-YET-END-TO-END-ACCEPTED"
    plan["top_source"] = {"repository": "https://github.com/crutkas/msys2-woarm64-build",
                          "commit": args.source_commit, "tree": args.source_tree}
    plan["limitations"] = [
        "Limited native engineering artifact, not RTM or a strict full-release package transaction.",
        "No native Perl provider: Perl-dependent commands, git-svn, git-send-email and related integrations are unsupported.",
        "GCM, mintty, full editors, service integration and installer/signing are not supplied.",
        "Use Git-Bash-Native.cmd for the supported console entry; upstream git-bash.exe expects the absent mintty.",
        "POSIX chmod/stty/false utility providers are withheld; Bash builtins remain available.",
        "Utility supported locale is LC_ALL=C with explicit MSYS system-file symlinks and noacl mounts.",
        "Source-specific commit/tree and reproducibility evidence is incomplete for some retained package providers; no identity is fabricated.",
    ]
    for path in (args.gettext_export, args.pcre_export, args.utilities_export):
        add_projection(plan, receipt(path))
    # Admission policy remains external; never infer it from a producer's self-reported booleans.
    admission = bound_json(receipt(args.ssh_admission))
    if args.ssh_mode == "portable-win32":
        if (admission.get("status") != "artifact-owner-qualified-portable-win32-arm64-ssh-limited-fallback" or
                admission.get("native_msys_provider_claim") is not False):
            raise ArtifactError("An explicit artifact-owner portable SSH fallback decision is required")
        for item in admission["evidence"]:
            proof = bound_json(item)
            if proof.get("passed") is not True:
                raise ArtifactError("Portable SSH functional evidence failed")
        signed = bound_json(admission["signature_receipt"])
        archive = Path(admission["archive"]["path"])
        if sha256(archive) != admission["archive"]["sha256"]:
            raise ArtifactError("Official portable SSH ZIP changed")
        if any(row.get("authenticode_status") != "Valid" for row in signed["signatures"]):
            raise ArtifactError("Official portable SSH signature qualification is incomplete")
        plan["components"].append({
            "id": "portable-win32-arm64-ssh-limited-fallback", "kind": "zip",
            "path": str(archive), "sha256": admission["archive"]["sha256"],
            "include_files": list(admission["projection"]), "map": admission["projection"],
            "receipts": [receipt(args.ssh_admission), admission["signature_receipt"]],
            "provenance": {"source": admission["source"], "role": "artifact-owner-qualified portable Win32 fallback",
                           "native_msys_provider_claim": False, "limitations": admission["limitations"]}})
        plan["limitations"].extend(admission["limitations"])
    else:
        if args.ssh_handoff is None:
            raise ArtifactError("Native MSYS SSH needs the producer handoff and independent admission")
        ssh = bound_json(receipt(args.ssh_handoff))
        if (admission.get("status") != "admitted-limited-native-msys-openssh-client-only-final" or
                admission.get("verdict", {}).get("limitedArtifactProjection") != "ADMITTED"):
            raise ArtifactError("A separate explicit limited SSH admission is required")
        package = ssh["packages"][0]
        archive = args.ssh_handoff.parent / package["path"]
        if sha256(archive) != package["sha256"]:
            raise ArtifactError("Admitted native MSYS SSH archive changed")
        plan["components"].append({
            "id": "native-msys-openssh-client-limited", "kind": "zip", "path": str(archive),
            "sha256": package["sha256"],
            "include_files": [row["path"] for row in ssh["files"] if row["path"] != "usr/bin/msys-2.0.dll"],
            "receipts": [receipt(args.ssh_handoff), receipt(args.ssh_admission)],
            "provenance": {"source": {"repository": "https://github.com/openssh/openssh-portable",
                                      "commit": ssh["source"]["upstream_commit"],
                                      "tree": ssh["source"]["prepared_tree_manifest_sha256"],
                                      "archive_sha256": ssh["source"]["archive_sha256"]},
                           "admission": "Explicit limited native MSYS client scope",
                           "features": ssh["features"], "limitations": ssh["limitations"]}})
        plan["limitations"].extend(ssh["limitations"])
    payload = Path(__file__).parent / "payload"
    for path in sorted(payload.rglob("*")):
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            plan["components"].append({"id": "mvp-entrypoints:" + name, "kind": "file",
                                       "path": str(path.resolve()), "sha256": sha256(path),
                                       "destination": name, "replace": [name],
                                       "provenance": {"source": plan["top_source"], "role": "relocatable MVP entrypoint/configuration"}})
    write_json(args.output, plan)
    print(f"Prepared {len(plan['components'])} exact runtime components with limited-admission boundaries")


if __name__ == "__main__":
    main()
