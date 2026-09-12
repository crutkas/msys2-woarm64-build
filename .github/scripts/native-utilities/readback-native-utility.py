"""Read every archive member, including genuine MSYS alias links, without executing."""
import argparse
from compression import zstd
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    base = args.root / args.package
    spec = importlib.util.spec_from_file_location("existing_pe", args.root / "inputs/inspect-native-archive.py")
    pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pe)
    output = base / "package-readback.json"
    if output.exists():
        raise RuntimeError("Readback output must be new")
    report = {"schema": 1, "members": [], "pe": [], "private_path_hits": [], "status": "failed"}
    archive_path = base / "packages" / f"{args.package}-{args.version}-aarch64.pkg.tar.zst"
    seen = set()
    with zstd.open(archive_path, "rb") as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or ":" in member.name or "\\" in member.name:
                raise RuntimeError("Unsafe archive path")
            if member.isdir():
                continue
            if member.name.casefold() in seen:
                raise RuntimeError("Duplicate archive member")
            seen.add(member.name.casefold())
            extracted = base / "extracted" / member.name
            if member.issym():
                raw = extracted.read_bytes()
                if (not raw.startswith(b"!<symlink>\xff\xfe")
                        or raw[10:].decode("utf-16").rstrip("\0") != member.linkname):
                    raise RuntimeError("Extracted MSYS alias differs from archive link")
                report["members"].append({"path": member.name, "type": "symlink",
                                          "link": member.linkname, "sha256": sha(raw)})
                continue
            if not member.isfile():
                raise RuntimeError("Unsupported archive member type")
            data = archive.extractfile(member).read()
            if extracted.read_bytes() != data:
                raise RuntimeError("Extracted member differs from archive")
            report["members"].append({"path": member.name, "type": "file", "sha256": sha(data), "size": len(data)})
            if data.startswith(b"MZ"):
                image = pe.pe(data)
                if image["machine"] != "0xAA64":
                    raise RuntimeError("Non-AA64 package executable")
                report["pe"].append({"path": member.name, "sha256": sha(data), **image})
            for encoding in ("latin1", "utf-16-le"):
                text = data.decode(encoding, errors="replace")
                for match in re.finditer(r"(?i)([a-z]:[\\/](?:users|ap\d[^\\/ \x00]*|ag-[^\\/ \x00]*)[\\/]|copilot-worktrees|session-state|/home/[^/ \x00]+/)", text):
                    report["private_path_hits"].append({"path": member.name, "encoding": encoding,
                                                        "offset": match.start(),
                                                        "context": text[max(0, match.start() - 20):match.end() + 120].split("\0")[0]})
    actual = {path.relative_to(base / "extracted").as_posix().casefold()
              for path in (base / "extracted").rglob("*") if path.is_file()}
    if actual != seen:
        raise RuntimeError("Extracted file set differs from package")
    report["status"] = "exact-native-package-members-and-alias-links-readback-pass"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "members": len(seen), "pe": len(report["pe"]),
                      "links": sum(item["type"] == "symlink" for item in report["members"]),
                      "private_path_hits": len(report["private_path_hits"])}))


if __name__ == "__main__":
    main()
