"""Package only named, successful commands; never claim the full Coreutils provider."""

import io
import json
from pathlib import Path
import tarfile

from qualify import ROOT, CORE, CORE_NAMES, copy, digest, load, source_inventory, write

HELD_OUT = ["chmod", "stty", "false"]
NAME = "coreutils-mvp-projection"
VERSION = "8.32-1"


def main():
    inputs = load(ROOT / "inputs.json")
    candidates = {record["name"]: record for record in inputs["programs"]}
    names = [name for name in CORE_NAMES if name not in HELD_OUT]
    package_dir = ROOT / "package"
    package_dir.mkdir(exist_ok=False)
    payload = package_dir / "payload"
    records, ownership = [], {}
    for name in names:
        result = load(ROOT / "cases" / f"private-{name}-03" / "result.json")
        if result["status"] != "positive-control-passed":
            raise RuntimeError(f"Utility lacks a successful current scoped control: {name}")
        source = ROOT / "private/usr/bin" / f"{name}.exe"
        relative = f"usr/bin/{name}.exe"
        copy(source, payload / relative, candidates[name]["sha256"], records, "eligible-named-coreutils-command")
        ownership[relative] = {"source_package": "GNU coreutils", "version": "8.32", "source_program": f"src/{name}.c",
                               "source": str(CORE / "stage/coreutils" / relative), "sha256": digest(source),
                               "execution_receipt": str(ROOT / "cases" / f"private-{name}-03/result.json"),
                               "execution_sha256": digest(ROOT / "cases" / f"private-{name}-03/result.json")}
    license_source = ROOT / "licenses/coreutils/COPYING"
    license_relative = f"usr/share/licenses/{NAME}/COPYING"
    copy(license_source, payload / license_relative, digest(license_source), records, "GPL-3.0-or-later-license")
    ownership[license_relative] = {"source_package": "GNU coreutils", "source": str(CORE / "source/coreutils-8.32/COPYING"),
                                  "sha256": digest(license_source)}
    source_meta = {
        "schema": 1, "package": NAME, "version": VERSION, "commands": names, "held_out": HELD_OUT,
        "full_coreutils_provider": False, "provides": [], "candidate_only": True,
        "source_archive": {"path": str(CORE.parent / "inputs/coreutils-8.32.tar.xz"),
                           "sha256": "4458d8de7849df44ccab15e16b1548b285224dbba5f08fac070c1c0e0bcc4cfa"},
        "source_inventory": {"path": str(ROOT / "coreutils-source-inventory.json"),
                             "sha256": digest(ROOT / "coreutils-source-inventory.json")},
        "producer_scope": "Unchanged historical native13 executable bytes; current907 consumer validation, not a reproducible producer rebuild",
        "producer_provenance": "PARTIAL: no original PKGBUILD, no complete compiler-input manifest; prior full suite incomplete",
        "prior_suite": inputs["prior_suite"],
        "runtime_configuration": "LC_ALL=C; approved private fstab noacl; MSYS=winsymlinks:sys",
        "excluded_claims": ["full upstream Coreutils suite", "arbitrary POSIX chmod modes", "strict PTY default closure",
                            "negative native exit-domain classification", "translated locale behavior"],
    }
    if digest(source_meta["source_archive"]["path"]) != source_meta["source_archive"]["sha256"]:
        raise RuntimeError("Coreutils source archive changed")
    write(package_dir / "source-metadata.json", source_meta)
    copy(package_dir / "source-metadata.json", payload / f"usr/share/{NAME}/scope.json",
         digest(package_dir / "source-metadata.json"), records, "projection-scope")
    scope_relative = f"usr/share/{NAME}/scope.json"
    ownership[scope_relative] = {"source_package": NAME, "source": str(package_dir / "source-metadata.json"),
                                 "sha256": digest(package_dir / "source-metadata.json")}
    size = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file())
    metadata = "\n".join([
        f"pkgname = {NAME}", f"pkgbase = {NAME}", f"pkgver = {VERSION}",
        "pkgdesc = Explicit limited Git Bash MVP core utility projection; not the full Coreutils provider",
        "url = https://www.gnu.org/software/coreutils/", "builddate = 1788224411",
        "packager = Private ARM64 utility qualification", f"size = {size}", "arch = aarch64",
        "license = GPL-3.0-or-later", "depend = msys2-runtime", "depend = libintl",
        "depend = libiconv", "depend = gmp", "",
    ]).encode()
    archive = package_dir / f"{NAME}-{VERSION}-aarch64.pkg.tar.zst"
    inventory = {}
    with tarfile.open(archive, "w:zst") as package:
        for relative, data, mode in [(".PKGINFO", metadata, 0o644)] + [
            (path.relative_to(payload).as_posix(), path.read_bytes(), 0o755 if path.suffix == ".exe" else 0o644)
            for path in sorted(payload.rglob("*")) if path.is_file()
        ]:
            entry = tarfile.TarInfo(relative)
            entry.size, entry.mode, entry.uid, entry.gid, entry.mtime = len(data), mode, 0, 0, 1788224411
            package.addfile(entry, io.BytesIO(data))
    with tarfile.open(archive, "r:zst") as package:
        for entry in package.getmembers():
            if not entry.isfile() or entry.name in inventory or entry.name.startswith("/") or ".." in Path(entry.name).parts:
                raise RuntimeError("Package has unsafe or duplicate payload")
            stream = package.extractfile(entry)
            data = stream.read()
            import hashlib
            inventory[entry.name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "mode": entry.mode}
            if entry.name != ".PKGINFO" and data != (payload / entry.name).read_bytes():
                raise RuntimeError("Package readback does not match input bytes")
    write(package_dir / "ownership.json", ownership)
    write(package_dir / "inventory.json", inventory)
    write(package_dir / "candidate.json", {"schema": 1, "status": "limited-MVP-projection-candidate-not-admitted",
          "package_name": NAME, "version": VERSION, "archive": str(archive), "sha256": digest(archive),
          "files": len(inventory), "PE_count": len(names), "commands": names, "held_out": HELD_OUT,
          "coreutils_provides": False, "ownership": str(package_dir / "ownership.json"),
          "ownership_sha256": digest(package_dir / "ownership.json"),
          "inventory": str(package_dir / "inventory.json"), "inventory_sha256": digest(package_dir / "inventory.json"),
          "source_metadata": str(package_dir / "source-metadata.json"),
          "source_metadata_sha256": digest(package_dir / "source-metadata.json"), "copies": records})
    moved = ROOT / "moved"
    moved.mkdir(exist_ok=False)
    with tarfile.open(archive, "r:zst") as package:
        package.extractall(moved, filter="data")
    moved_copies = []
    for filename in ("msys-2.0.dll", "msys-intl-8.dll", "msys-iconv-2.dll", "msys-gmp-10.dll", "bash.exe",
                     "find.exe", "xargs.exe", "sed.exe"):
        source = ROOT / "private/usr/bin" / filename
        role = "separate-extra-command-test-only" if filename in ("find.exe", "xargs.exe", "sed.exe") else "separate-runtime-dependency-or-harness"
        copy(source, moved / "usr/bin" / filename, digest(source), moved_copies, role)
    copy(ROOT / "private/etc/fstab", moved / "etc/fstab", digest(ROOT / "private/etc/fstab"), moved_copies, "runtime-config")
    (moved / "home").mkdir()
    (moved / "tmp").mkdir()
    for relative, row in inventory.items():
        if digest(moved / relative) != row["sha256"]:
            raise RuntimeError("Moved extracted package bytes differ")
    write(ROOT / "moved-inputs.json", {"schema": 1, "archive_sha256": digest(archive), "extracted_inventory": inventory,
                                      "dependency_copies": moved_copies, "root": str(moved)})
    print(json.dumps({"archive": str(archive), "sha256": digest(archive), "commands": len(names), "held_out": HELD_OUT}))


if __name__ == "__main__":
    main()
