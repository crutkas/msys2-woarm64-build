"""Create genuine unsigned GDBM split archives; never claim provider admission."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time

from db_package import escape_mtree, parse_metadata, pe_metadata, validate_mtree
from sources import ContractError, digest, inventory, relative_path
from ssh_bootstrap import write_json


VERSION = "1.26-2"
RECIPE_SHA = "b71512f7c277c809188dd54254eec417a2c39612dee562517700a506c0e10a33"
PROFILES = {
    "gdbm": {"description": "GNU database library", "depends": ["libgdbm=1.26"]},
    "libgdbm": {"description": "GNU database library",
                "depends": ["gcc-libs", "libreadline", "libiconv", "libintl", "ncurses"]},
    "libgdbm-devel": {"description": "libgdbm headers and libraries",
                      "depends": ["libgdbm=1.26", "libreadline-devel"]},
}


def split_files(files):
    result = {name: {} for name in PROFILES}
    for name, row in files.items():
        relative_path(name)
        if name.startswith("usr/bin/") and name.endswith(".exe"):
            target = "gdbm"
        elif name.startswith("usr/bin/") and name.endswith(".dll"):
            target = "libgdbm"
        elif name.startswith(("usr/include/", "usr/lib/")):
            target = "libgdbm-devel"
        elif name.startswith("usr/share/licenses/"):
            target = "libgdbm"
        elif name.startswith(("usr/share/info/", "usr/share/man/", "usr/share/locale/")):
            target = "gdbm"
        else:
            raise ContractError(f"Unassigned GDBM package file: {name}")
        result[target][name] = row
    if any(not group for group in result.values()):
        raise ContractError("A required genuine GDBM split is empty")
    return result


def metadata(name, files, epoch):
    profile = PROFILES[name]
    common = [f"pkgname = {name}", "pkgbase = gdbm", f"pkgver = {VERSION}"]
    pkg = common + [
        f"pkgdesc = {profile['description']}", "url = https://www.gnu.org/software/gdbm/gdbm.html",
        f"builddate = {epoch}", "packager = Native ARM64 recovery (unsigned local artifact)",
        f"size = {sum(row['size'] for row in files.values())}", "arch = aarch64",
        "license = spdx:GPL-3.0-or-later", *[f"depend = {value}" for value in profile["depends"]],
    ]
    build = ["format = 2", *common, "pkgarch = aarch64", f"pkgbuild_sha256 = {RECIPE_SHA}",
             "packager = Native ARM64 recovery (unsigned local artifact)", f"builddate = {epoch}",
             "builddir = /usr/src/packages/gdbm", "startdir = /usr/src/packages/gdbm",
             "buildtool = gdbm_package.py", "buildtoolver = 1",
             "buildenv = !distcc", "buildenv = !ccache", "buildenv = !sign",
             "options = staticlibs", "options = strip"]
    return {".PKGINFO": ("\n".join(pkg) + "\n").encode(),
            ".BUILDINFO": ("\n".join(build) + "\n").encode()}


def readback(path, name, expected, wanted_metadata):
    actual, observed_metadata, seen, images = {}, {}, set(), []
    with tarfile.open(path, "r:zst") as archive:
        for member in archive:
            relative_path(member.name)
            if member.name in seen or not member.isfile():
                raise ContractError("Duplicate or non-file GDBM package entry")
            seen.add(member.name)
            mode = 0o755 if member.name.endswith((".exe", ".dll")) else 0o644
            if member.uid != 0 or member.gid != 0 or member.mode != mode:
                raise ContractError("GDBM archive ownership or mode mismatch")
            data = archive.extractfile(member).read()
            if any(token.encode(encoding) in data.lower()
                   for token in ("ag-gdbm-20260911-01", "ap06-78", "crutkaslocal")
                   for encoding in ("ascii", "utf-16le")):
                raise ContractError("Private machine path remains in a shipped package member")
            if member.name in (".PKGINFO", ".BUILDINFO", ".MTREE"):
                observed_metadata[member.name] = data
                continue
            actual[member.name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            if data.startswith(b"MZ") or member.name.endswith((".exe", ".dll")):
                images.append({"path": member.name, **actual[member.name], **pe_metadata(data)})
    if actual != expected or set(observed_metadata) != {".PKGINFO", ".BUILDINFO", ".MTREE"}:
        raise ContractError("Complete GDBM package payload/metadata differs")
    for key, value in wanted_metadata.items():
        if observed_metadata[key] != value:
            raise ContractError(f"GDBM package metadata changed: {key}")
    pkg = parse_metadata(observed_metadata[".PKGINFO"])
    build = parse_metadata(observed_metadata[".BUILDINFO"])
    if pkg["pkgname"] != [name] or pkg["pkgver"] != [VERSION] or pkg["arch"] != ["aarch64"]:
        raise ContractError("GDBM package identity mismatch")
    if any(key in pkg for key in ("provides", "replaces", "conflict")) or pkg.get("depend") != PROFILES[name]["depends"]:
        raise ContractError("Unexpected GDBM provider or dependency metadata")
    if build["pkgbuild_sha256"] != [RECIPE_SHA] or build["builddir"] != ["/usr/src/packages/gdbm"]:
        raise ContractError("GDBM source or canonical build metadata differs")
    validate_mtree(observed_metadata[".MTREE"], actual, observed_metadata, pkg["builddate"][0])
    if b"ag-gdbm-" in gzip.decompress(observed_metadata[".MTREE"]).lower():
        raise ContractError("Private path remains in package MTREE metadata")
    return {"name": name, "path": str(path), "sha256": digest(path), "size": path.stat().st_size,
            "version": VERSION, "arch": "aarch64", "files": actual, "pe_images": images,
            "depends": pkg["depend"], "signed": False, "provider_admitted": False,
            "archive_and_mtree_readback_complete": True, "private_root_occurrences": 0}


def create_archive(stage, directory, name, files, epoch):
    path = directory / f"{name}-{VERSION}-aarch64.pkg.tar.zst"
    entries = metadata(name, files, epoch)
    lines = ["#mtree", "/set type=file uid=0 gid=0 mode=644"]
    for filename, data in entries.items():
        lines.append(f"./{filename} time={epoch}.0 size={len(data)} sha256digest={hashlib.sha256(data).hexdigest()}")
    for filename, row in sorted(files.items()):
        mode = "755" if filename.endswith((".exe", ".dll")) else "644"
        lines.append(f"./{escape_mtree(filename)} mode={mode} time={epoch}.0 size={row['size']} sha256digest={row['sha256']}")
    original_metadata = dict(entries)
    entries[".MTREE"] = gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)
    with tarfile.open(path, "x:zst", level=10, format=tarfile.PAX_FORMAT) as archive:
        for filename, data in entries.items():
            member = tarfile.TarInfo(filename)
            member.size, member.mode, member.mtime = len(data), 0o644, epoch
            archive.addfile(member, io.BytesIO(data))
        for filename, row in sorted(files.items()):
            source = stage / filename
            if digest(source) != row["sha256"] or source.stat().st_size != row["size"]:
                raise ContractError("GDBM source stage changed during packaging")
            member = tarfile.TarInfo(filename)
            member.size, member.mtime = row["size"], epoch
            member.mode = 0o755 if filename.endswith((".exe", ".dll")) else 0o644
            with source.open("rb") as stream:
                archive.addfile(member, stream)
    return readback(path, name, files, original_metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--api-result", required=True, type=Path)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--strip-receipt", type=Path, required=True)
    parser.add_argument("--static-api-result", type=Path, required=True)
    parser.add_argument("--archive-audit", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01") or Path(args.output_name).name != args.output_name or args.output_name in (".", ".."):
        raise ContractError("Explicit owned package output required")
    proof = json.loads(args.api_result.read_text())
    if not proof.get("passed"):
        raise ContractError("Fresh independent native installed/moved-root API proof required")
    if digest(root / "downloads/PKGBUILD") != RECIPE_SHA:
        raise ContractError("Pinned genuine GDBM recipe changed")
    stage = (args.stage or root / "stage").resolve()
    if not stage.is_relative_to(root):
        raise ContractError("Package stage must be an owned GDBM output")
    files = inventory(stage)
    if files != proof["stage_files"]:
        raise ContractError("GDBM stage is not the independently tested stage")
    stripping = json.loads(args.strip_receipt.read_text())
    static = json.loads(args.static_api_result.read_text())
    archive_audit = json.loads(args.archive_audit.read_text())
    if (stripping.get("files") != files or not stripping.get("non_debug_code_equal")
            or not stripping.get("imports_exports_equal") or stripping.get("remaining_private_paths")
            or not stripping.get("original_unchanged") or not stripping["process"]["process"]["passed"]):
        raise ContractError("Exact genuine stripped-successor evidence required")
    if any(not row["process"]["passed"] for row in stripping.get("static_processes", {}).values()):
        raise ContractError("Native COFF debug stripping failed")
    if not static.get("passed") or static.get("linkage") != "static-gdbm" or static.get("stage_files") != files:
        raise ContractError("The exact stripped static archives require a native API/moved-root proof")
    if any("gdbm" in name.lower() for name in static["client"]["imports"]):
        raise ContractError("Static API client still imports a GDBM DLL")
    for evidence in (args.api_result, args.static_api_result):
        compiler_log = evidence.parent / "compile/command.log"
        if b"warning" in compiler_log.read_bytes().lower():
            raise ContractError("Successor native consumer link emitted a warning")
    if not archive_audit.get("passed") or any(
        row["after_sha256"] != digest(stage / "usr/lib" / name)
        for name, row in archive_audit["archives"].items()
    ):
        raise ContractError("Exact static member/symbol/relocation audit required")
    output = root / args.output_name
    output.mkdir()
    epoch = int(time.time())
    packages = [create_archive(stage, output, name, group, epoch)
                for name, group in split_files(files).items()]
    if inventory(stage) != files:
        raise ContractError("GDBM stage changed after archive readback")
    write_json(output / "packages.json", {
        "schema": 1, "status": "genuine-native-GDBM-package-candidates",
        "packages": packages, "provider_admitted": False,
        "api_result": {"path": str(args.api_result), "sha256": digest(args.api_result)},
        "static_api_result": {"path": str(args.static_api_result), "sha256": digest(args.static_api_result)},
        "strip_receipt": {"path": str(args.strip_receipt), "sha256": digest(args.strip_receipt)},
        "archive_audit": {"path": str(args.archive_audit), "sha256": digest(args.archive_audit)},
        "source_recipe_commit": "fc03a3300db9bcdd0ccc082749e006abf1a04414",
        "source_archive_sha256": "6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e",
        "recipe_sha256": RECIPE_SHA, "producer_sha256": digest(Path(__file__)),
        "qualification_note": "Package readback and independent API scope only; full upstream and provider decisions are separate receipts"})
    print(json.dumps([{"name": row["name"], "path": row["path"], "sha256": row["sha256"]} for row in packages]), flush=True)


if __name__ == "__main__":
    main()
