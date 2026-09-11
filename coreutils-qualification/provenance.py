"""Persist available source/recipe lineage without inventing missing producer proof."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from qualify import ROOT, CORE, UTILS, copy, digest, load, source_inventory, write


def main():
    output = ROOT / "provenance"
    output.mkdir(exist_ok=False)
    records = []
    blobs = [
        ("641447a2cef092c0a26075c59584e972f515ce91", ".github/scripts/build-native-coreutils-recovery.sh",
         "60e2e82c42f26c6ff99e134f0e5ccba7dbcf17a2936d7ab498f8470e2c3cc74d"),
        ("22f800683372dc62e354d1ea683477ca1145e377", ".github/scripts/build-native-bash-test-utilities.sh",
         "5f2c6b39782a3fec3147d7216c7adc577537e6c8293a7d99bbbab850c5770f60"),
    ]
    for commit, path, expected in blobs:
        data = subprocess.run(["git", "show", f"{commit}:{path}"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, timeout=20).stdout
        sha = hashlib.sha256(data).hexdigest()
        if sha != expected:
            raise RuntimeError(f"Recipe blob identity differs: {path}")
        destination = output / Path(path).name
        with destination.open("xb") as stream:
            stream.write(data)
        records.append({"repository": "crutkas/msys2-woarm64-build", "commit": commit,
                        "path": path, "sha256": sha, "copy": str(destination)})
    patches = []
    for path in sorted((CORE.parent / "inputs").glob("*.patch")):
        copy(path, output / "coreutils-patches" / path.name, digest(path), patches, "retained-producer-input-patch")
    manifest = CORE.parent / "native-coreutils-consumer-01/consumer-manifest.json"
    copy(manifest, output / "consumer-manifest.json",
         "18eba16889967734e416d6822c557f823c420a353668f9b6f2c43eafe5baedab", patches, "historical-consumer-not-producer-admission")
    write(output / "recipes.json", {"schema": 1, "git_blobs": records, "patches": patches,
          "missing": ["original native13 PKGBUILD/package", "complete native13 compiler input manifest",
                      "completed upstream Coreutils suite"],
          "scope": "Retained producer recipes and source content, not a new native producer rebuild"})
    packages = []
    for package, version, names, archive_sha in (
        ("findutils", "4.11.0", ["find", "xargs"], "bfd19cb06cc71f3352d567e90284d8cdac02ac89774bbeadf0b533b0c11432fd"),
        ("sed", "4.9", ["sed"], "6e226b732e1cd739464ad6862bd1a1aba42d7982922da7a53519631d24975181"),
    ):
        source_root = UTILS.parent / "native-utilities-05/source" / f"{package}-{version}"
        source_archive = UTILS.parent / "inputs" / f"{package}-{version}.tar.xz"
        if digest(source_archive) != archive_sha:
            raise RuntimeError("Extra utility source archive changed")
        name = package + "-mvp-projection"
        folder = ROOT / name
        folder.mkdir(exist_ok=False)
        payload = folder / "payload"
        copies, ownership = [], {}
        for utility in names:
            result = load(ROOT / "cases" / f"moved-{utility}-01/result.json")
            if result["status"] != "positive-control-passed":
                raise RuntimeError(f"Missing moved positive evidence: {utility}")
            path = ROOT / "moved/usr/bin" / f"{utility}.exe"
            relative = f"usr/bin/{utility}.exe"
            expected = load(ROOT / "inputs.json")["programs"]
            sha = next(row["sha256"] for row in expected if row["name"] == utility)
            copy(path, payload / relative, sha, copies, "named-extra-projection-command")
            ownership[relative] = {"package": package, "version": version, "sha256": sha,
                                  "source": str(UTILS / "stage" / relative),
                                  "execution_receipt": str(ROOT / "cases" / f"moved-{utility}-01/result.json"),
                                  "execution_sha256": digest(ROOT / "cases" / f"moved-{utility}-01/result.json")}
        relative = f"usr/share/licenses/{name}/COPYING"
        copy(source_root / "COPYING", payload / relative,
             "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986", copies, "GPL-source-license")
        ownership[relative] = {"package": package, "source": str(source_root / "COPYING"),
                              "sha256": digest(source_root / "COPYING")}
        write(folder / "source-inventory.json", source_inventory(source_root))
        write(folder / "scope.json", {"schema": 1, "commands": names, "candidate_only": True, "provides": [],
              "source_archive": str(source_archive), "source_archive_sha256": archive_sha,
              "source_inventory_sha256": digest(folder / "source-inventory.json"),
              "recipe": records[1],
              "limitations": ["LC_ALL=C positive operations only", "NLS private operational paths not qualified",
                              "full upstream package suite not qualified", "no locatedb/updatedb payload or claim"]})
        scope_relative = f"usr/share/{name}/scope.json"
        copy(folder / "scope.json", payload / scope_relative, digest(folder / "scope.json"), copies, "projection-scope")
        ownership[scope_relative] = {"package": name, "source": str(folder / "scope.json"), "sha256": digest(folder / "scope.json")}
        metadata = (f"pkgname = {name}\npkgbase = {name}\npkgver = {version}-1\n"
                    f"pkgdesc = Limited C-locale MVP commands: {' '.join(names)}\n"
                    "builddate = 1788224411\narch = aarch64\nlicense = GPL-3.0-or-later\n"
                    "depend = msys2-runtime\ndepend = libintl\n").encode()
        archive = folder / f"{name}-{version}-1-aarch64.pkg.tar.zst"
        with tarfile.open(archive, "w:zst") as stream:
            for relative, data in [(".PKGINFO", metadata)] + [
                (path.relative_to(payload).as_posix(), path.read_bytes())
                for path in sorted(payload.rglob("*")) if path.is_file()
            ]:
                entry = tarfile.TarInfo(relative)
                entry.size, entry.mode, entry.uid, entry.gid, entry.mtime = len(data), 0o755 if relative.endswith(".exe") else 0o644, 0, 0, 1788224411
                stream.addfile(entry, io.BytesIO(data))
        inventory = {}
        with tarfile.open(archive, "r:zst") as stream:
            for entry in stream.getmembers():
                if not entry.isfile() or entry.name in inventory or ".." in Path(entry.name).parts:
                    raise RuntimeError("Invalid extra projection archive")
                data = stream.extractfile(entry).read()
                if entry.name != ".PKGINFO" and data != (payload / entry.name).read_bytes():
                    raise RuntimeError("Extra archive readback mismatch")
                inventory[entry.name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        write(folder / "ownership.json", ownership)
        write(folder / "inventory.json", inventory)
        record = {"schema": 1, "status": "limited-MVP-projection-candidate-not-admitted",
                  "package_name": name, "archive": str(archive), "sha256": digest(archive),
                  "commands": names, "copies": copies, "source_inventory": str(folder / "source-inventory.json"),
                  "ownership": str(folder / "ownership.json"), "ownership_sha256": digest(folder / "ownership.json"),
                  "inventory": str(folder / "inventory.json"), "inventory_sha256": digest(folder / "inventory.json"),
                  "scope": str(folder / "scope.json"), "scope_sha256": digest(folder / "scope.json")}
        write(folder / "candidate.json", record)
        packages.append(record)
    write(ROOT / "extra-candidates.json", packages)
    print(json.dumps([{"package": row["package_name"], "sha256": row["sha256"], "commands": row["commands"]} for row in packages]))


if __name__ == "__main__":
    main()
