"""Seal completed native terminal stages without claiming package admission."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import struct

from pe_exports import export_names
from readline_chain_inputs import ROOT, HERE, SEALS, fresh
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import write_json

build = importlib.import_module("build-readline-chain")
VERSIONS = {"ncurses": "6.6-2", "readline": "8.3.003-1", "libedit": "20240808_3.1-1"}
DEPENDENCIES = {
    "ncurses": {"ncurses": ["gcc-libs"], "ncurses-devel": ["ncurses=6.6"]},
    "readline": {"libreadline": ["ncurses"], "libreadline-devel": ["libreadline=8.3.003", "ncurses-devel"]},
    "libedit": {"libedit": ["ncurses", "sh"], "libedit-devel": ["libedit=20240808_3.1", "ncurses-devel"]},
}


def raw_pe(file):
    data = file.read_bytes()
    if data[:2] != b"MZ" or len(data) < 64:
        raise ContractError(f"Not a PE image: {file}")
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0":
        raise ContractError(f"Invalid PE header: {file}")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    optional = struct.unpack_from("<H", data, offset + 24)[0]
    if machine != 0xAA64 or optional != 0x20B:
        raise ContractError(f"Non-native target payload: {file}")
    return {"sha256": digest(file), "machine": machine, "optional_magic": optional,
            "exports": export_names(data) if file.suffix.lower() == ".dll" else None}


def coff_archive(data):
    if data[:8] != b"!<arch>\n":
        raise ContractError("Expected a complete ordinary GNU archive")
    offset, members = 8, []
    while offset < len(data):
        if offset + 60 > len(data) or data[offset + 58:offset + 60] != b"`\n":
            raise ContractError("Malformed archive member header")
        name = data[offset:offset + 16].decode("ascii").strip()
        size = int(data[offset + 48:offset + 58])
        start, end = offset + 60, offset + 60 + size
        if size < 0 or end > len(data):
            raise ContractError("Archive member extends beyond its file")
        if name not in ("/", "//", "/SYM64/"):
            member = data[start:end]
            if len(member) < 20:
                raise ContractError("Truncated COFF archive member")
            import_or_bigobj = member[:4] == b"\0\0\xff\xff"
            machine = struct.unpack_from("<H", member, 6 if import_or_bigobj else 0)[0]
            if machine != 0xAA64:
                raise ContractError(f"Non-ARM64 COFF archive member: {name}")
            if not import_or_bigobj:
                sections = struct.unpack_from("<H", member, 2)[0]
                optional_size = struct.unpack_from("<H", member, 16)[0]
                if not sections or 20 + optional_size + sections * 40 > len(member):
                    raise ContractError("Invalid ordinary COFF section table")
            members.append({"archive_name": name, "offset": start, "size": size,
                            "machine": machine, "sha256": hashlib.sha256(member).hexdigest()})
        offset = end + size % 2
    if offset != len(data) or not members:
        raise ContractError("Incomplete or empty COFF archive")
    return members


def export(args):
    stage = ROOT / args.stage
    manifest = stage.parent / "stage.inventory.json"
    verify_tree(stage, manifest)
    stage_record = json.loads(manifest.read_text())
    if stage_record["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Export requires exact current native consumer cohort")
    build_result = Path(stage_record.get("closure_result", stage.parent / "result.json"))
    result = json.loads(build_result.read_text())
    package_link_gate = stage_record.get("package_link_gate")
    gated_ncurses = (args.package == "ncurses"
                     and result["status"] == "native-payload-upstream-checks-complete-package-link-gated"
                     and result.get("upstream_checks_completed") is True
                     and result.get("install_payload_complete") is True and package_link_gate)
    if not gated_ncurses and (result["status"] != "native-built-upstream-checks-not-yet-api-pty-admitted"
                              or not result["process"]["passed"]):
        raise ContractError("Build and upstream checks must be complete")
    proofs = {}
    for linkage, name in (("static", args.static_proof), ("shared", args.shared_proof)):
        proof = ROOT / name / "result.json"
        record = json.loads(proof.read_text())
        reuse = None
        if record["stage_manifest_sha256"] != digest(manifest):
            delta = stage_record.get("static_cpp_delta") or stage_record.get("static_library_delta", {})
            static_path = {"ncurses": "usr/lib/libncurses++w.a", "libedit": "usr/lib/libedit.a"}.get(args.package)
            if (linkage != "shared" or not static_path or delta.get("changed_files") != [static_path]
                    or record["stage_manifest_sha256"] != delta.get("base_manifest_sha256")):
                raise ContractError("Proof is not bound to this stage or its exact unchanged shared scope")
            base = Path(delta["base_manifest"])
            if digest(base) != delta["base_manifest_sha256"]:
                raise ContractError("Static C++ delta base receipt drift")
            base_files = json.loads(base.read_text())["files"]
            changed = sorted(name for name in stage_record["files"].keys() | base_files.keys()
                             if stage_record["files"].get(name) != base_files.get(name))
            if changed != [static_path]:
                raise ContractError("Shared-proof reuse crosses a changed shared input")
            reuse = {"base_manifest_sha256": digest(base), "unchanged_shared_inputs": True,
                     "only_changed_file": static_path,
                     "scope": "Reuse exact already-observed shared DLL/header/PTY bytes; no new shared producer claim"}
        if (record["status"] != "passed-native-static-shared-api-pty-loaded-modules"
                or record["linkage"] != linkage or record["package"] != args.package
                or record["compiler_receipt_sha256"] != SEALS["compiler"]
                or not record["process"]["passed"]):
            raise ContractError(f"Missing exact complete native {linkage} proof")
        proofs[linkage] = {"path": str(proof), "sha256": digest(proof),
                           "process": record["process"], "api": record["api"], "unchanged_scope_reuse": reuse}
    if args.package == "readline":
        for linkage, name in (("static", args.history_static_proof), ("shared", args.history_shared_proof)):
            if not name:
                raise ContractError("Separate real libhistory static/shared API and DLL proofs are required")
            proof = ROOT / name / "result.json"
            record = json.loads(proof.read_text())
            if (record["package"] != "history" or record["linkage"] != linkage
                    or record["stage_manifest_sha256"] != digest(manifest)
                    or record["status"] != "passed-native-static-shared-api-pty-loaded-modules"
                    or not record["process"]["passed"]):
                raise ContractError("Incomplete standalone native history-library proof")
            proofs["history-" + linkage] = {"path": str(proof), "sha256": digest(proof),
                                           "process": record["process"], "api": record["api"]}
    if args.package == "libedit":
        for debug, name in ((False, args.cells_proof), (True, args.cells_debug_proof)):
            if not name:
                raise ContractError("Normal and DEBUG_REFRESH native display-cell regressions are required")
            proof = ROOT / name / "result.json"
            record = json.loads(proof.read_text())
            if (record["package"] != "libedit-cells" or record["linkage"] != "static"
                    or record["debug_refresh"] is not debug
                    or record["stage_manifest_sha256"] != digest(manifest)
                    or record["compiler_receipt_sha256"] != SEALS["compiler"]
                    or record["status"] != "passed-native-static-shared-api-pty-loaded-modules"
                    or not record["process"]["passed"]):
                raise ContractError("Incomplete native mixed-width display-cell regression")
            proofs["display-cells-debug" if debug else "display-cells"] = {
                "path": str(proof), "sha256": digest(proof), "process": record["process"], "api": record["api"]}
    output = ROOT / args.output
    fresh(output)
    output.mkdir()
    native_files = {p.relative_to(stage).as_posix(): raw_pe(p)
                    for p in sorted(stage.rglob("*")) if p.is_file() and p.suffix.lower() in (".exe", ".dll")}
    if not native_files:
        raise ContractError("No native PE payload")
    write_json(output / "native-pe.json", native_files)
    archives = {p.relative_to(stage).as_posix(): {
        "sha256": digest(p), "members": coff_archive(p.read_bytes())}
        for p in sorted(stage.rglob("*.a"))}
    if not archives:
        raise ContractError("Native static/import archives are required")
    write_json(output / "native-archives.json", archives)
    files = inventory(stage)
    package_names = list(DEPENDENCIES[args.package])
    partitions = {name: [] for name in package_names}
    for name in files:
        if package_link_gate and name.startswith("usr/lib/terminfo/"):
            continue
        development = name.startswith(("usr/include/", "usr/lib/")) or name.endswith("-config")
        if name == "usr/lib/terminfo":
            development = False
        partitions[package_names[1 if development else 0]].append(name)
    metadata = {
        "schema": 1, "target": "aarch64-pc-cygwin", "architecture": "aarch64",
        "profile": "MSYS LP64/POSIX", "version": VERSIONS[args.package],
        "source_manifest_sha256": SEALS[args.package], "compiler_receipt_sha256": SEALS["compiler"],
        "packages": [{"name": name, "depends": dependencies, "files": partitions[name]}
                     for name, dependencies in DEPENDENCIES[args.package].items()],
        "backup": ["etc/inputrc"] if args.package == "readline" else [],
        "status": "package-ready-inventory-not-installed-signed-or-admitted",
        "runtime_provider": {"required_sha256": build.RUNTIME_SHA, "provided_by_this_package": False},
        "shared_provider_authority": "pipeline2160 only",
        "required_symlink_entries": ([{"path": "usr/lib/terminfo", "target": "../share/terminfo"}]
                                    if package_link_gate else []),
        "package_link_gate": package_link_gate,
    }
    if package_link_gate:
        metadata["status"] = "package-source-metadata-with-explicit-relative-symlink-creation-gate"
    write_json(output / "package-metadata.json", metadata)
    handoff = {
        "schema": 1, "package": args.package,
        "status": ("native-stage-upstream-static-shared-api-pty-dll-proofs-package-link-gated" if package_link_gate
                   else "native-stage-full-profile-upstream-checks-static-shared-api-pty-dll-proofs"),
        "stage": str(stage), "stage_manifest": str(manifest), "stage_manifest_sha256": digest(manifest),
        "build_result": {"path": str(build_result), "sha256": digest(build_result),
                         "process": result.get("process"), "actual_observer": result.get("actual_observer")},
        "launch": {"path": str(stage.parent / "launch.json"), "sha256": digest(stage.parent / "launch.json")},
        "source": {"path": str(ROOT / "sources" / args.package / "source"),
                   "manifest_sha256": SEALS[args.package],
                   "working_source_manifest": stage_record.get("working_source_manifest"),
                   "working_source_manifest_sha256": (
                       digest(stage_record["working_source_manifest"])
                       if stage_record.get("working_source_manifest") else None)},
        "compiler_receipt": {"path": str(build.COMPILER_RECEIPT), "sha256": SEALS["compiler"],
                             "scope": "Exact protected C/C++ frontend scopes, not blanket SDK",
                             "full_cpp_qualified": False},
        "proofs": proofs, "runtime_sha256": build.RUNTIME_SHA,
        "package_metadata_sha256": digest(output / "package-metadata.json"),
        "native_pe_sha256": digest(output / "native-pe.json"),
        "native_archives_sha256": digest(output / "native-archives.json"),
        "maintained_files": inventory(HERE),
        "consumer_requirements": ["Bash readline enabled plus separate gettext/NLS closure",
                                  "SQLite full readline-enabled recipe; Tcl remains parent-owned",
                                  "OpenSSH and Heimdal full libedit linkage remains parent-owned"],
        "remaining_gates": ["Provider-owned genuine packaging/signing/install/admission",
                            "Downstream Bash/SQLite/Heimdal/OpenSSH checks",
                            "No blanket compiler/SDK or shared-distribution admission"],
        "package_link_gate": package_link_gate,
        "static_cpp_delta": stage_record.get("static_cpp_delta"),
        "static_library_delta": stage_record.get("static_library_delta"),
    }
    write_json(output / "handoff.json", handoff)
    print(json.dumps({"path": str(output / "handoff.json"), "sha256": digest(output / "handoff.json"),
                      "stage": str(stage), "status": handoff["status"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=VERSIONS)
    for name in ("stage", "static-proof", "shared-proof", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--history-static-proof")
    parser.add_argument("--history-shared-proof")
    parser.add_argument("--cells-proof")
    parser.add_argument("--cells-debug-proof")
    export(parser.parse_args())
