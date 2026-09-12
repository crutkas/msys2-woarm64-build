"""Verify preserved evidence without the destroyed original machine or paths."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="Also verify exact staged Git blob bytes before commit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    repository = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()) if args.index else None
    batch = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repository, stdin=subprocess.PIPE, stdout=subprocess.PIPE) if args.index else None
    count = 0
    try:
        for row in manifest["files"]:
            relative = Path(row["file"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe catalog path: {relative}")
            path = root / relative
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != row["sha256"] or path.stat().st_size != row["bytes"]:
                raise ValueError(f"Evidence bytes differ: {relative}")
            if batch:
                spec = ":" + path.relative_to(repository).as_posix()
                batch.stdin.write((spec + "\n").encode("utf-8"))
                batch.stdin.flush()
                header = batch.stdout.readline().split()
                if len(header) != 3 or header[1] != b"blob":
                    raise ValueError(f"Staged evidence missing: {relative}")
                size = int(header[2])
                remaining, hasher = size, hashlib.sha256()
                while remaining:
                    chunk = batch.stdout.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("Truncated Git blob")
                    hasher.update(chunk)
                    remaining -= len(chunk)
                if batch.stdout.read(1) != b"\n" or size != row["bytes"] or hasher.hexdigest() != row["sha256"]:
                    raise ValueError(f"Git changed staged evidence bytes: {relative}")
            count += 1
    finally:
        if batch:
            batch.stdin.close()
            if batch.wait(timeout=30) != 0:
                raise RuntimeError("Git batch reader failed")
    print(json.dumps({"verified_evidence_files": count, "staged_git_bytes_verified": args.index}))


if __name__ == "__main__":
    main()
