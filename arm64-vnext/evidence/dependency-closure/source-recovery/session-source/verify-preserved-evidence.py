"""Verify byte-exact preservation against both checkout bytes and staged/commit blobs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--revision", default="")
args = parser.parse_args()
base = Path("arm64-vnext") / "evidence" / "dependency-closure"
index = json.loads((base / "preservation-index.json").read_text(encoding="utf-8"))
files = {}
for row in index["files"]:
    path = base.joinpath(*row["stored_path"].split("/"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise RuntimeError(f"Working-tree bytes differ: {path}")
    key = path.as_posix()
    if key in files and files[key] != row["sha256"]:
        raise RuntimeError("Deduplicated originals differ")
    files[key] = row["sha256"]
requests = "".join(f"{args.revision}:{path}\n" for path in files).encode("utf-8")
result = subprocess.run(["git", "-c", "core.longpaths=true", "cat-file", "--batch"],
                        input=requests, capture_output=True, check=True)
position = 0
for path, expected in files.items():
    end = result.stdout.index(b"\n", position)
    header = result.stdout[position:end].split()
    if len(header) != 3 or header[1] != b"blob":
        raise RuntimeError(f"Missing Git blob: {path}: {header!r}")
    size = int(header[2])
    data = result.stdout[end + 1:end + 1 + size]
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError(f"Git blob changed original evidence bytes: {path}")
    position = end + 1 + size + 1
if position != len(result.stdout):
    raise RuntimeError("Unexpected Git batch output")
print(json.dumps({"verified_unique_evidence_blobs": len(files), "original_paths": len(index["files"]),
                  "revision": args.revision or "index", "total_evidence_bytes": sum(
                      (base.joinpath(*path[len(base.as_posix()) + 1:].split("/"))).stat().st_size for path in files),
                  "line_endings_and_all_bytes_unchanged": True}))
