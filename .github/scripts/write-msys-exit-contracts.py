"""Create image-locked contracts for the maintained MSYS exit fixture."""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--bash", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--base-contracts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = {"schema": 2, "contracts": {}}
    if args.base_contracts:
        result["contracts"].update(
            json.loads(args.base_contracts.read_text(encoding="utf-8"))["contracts"])

    source_sha256 = sha256(args.source)
    common = {
        "encoding": "msys-posix-wait-status-v1",
        "probe_source_sha256": source_sha256,
        "parent_raw_exit": 0,
    }
    result["contracts"].update({
        "msys-env-eacces-v1": {
            **common,
            "child_image_name": args.env.name,
            "image_sha256": sha256(args.env),
            "parent_image_name": args.helper.name,
            "parent_image_sha256": sha256(args.helper),
            "raw_exit": 126 << 8,
            "portable_exit": 126,
        },
        "msys-child-seven-v1": {
            **common,
            "child_image_name": args.helper.name,
            "image_sha256": sha256(args.helper),
            "parent_image_name": args.bash.name,
            "parent_image_sha256": sha256(args.bash),
            "raw_exit": 7 << 8,
            "portable_exit": 7,
        },
    })
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
