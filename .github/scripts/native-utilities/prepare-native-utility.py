"""Prepare only an aarch64 architecture declaration in an exact pinned recipe."""
import argparse
import hashlib
import json
from pathlib import Path


PINS = {
    "which": "79e850817cc47b53c2c66c5044f65e84f1658edac49963ac4927c2e625da8057",
    "dos2unix": "39cd2632f3021e1815ad19aed6a1c41059bd38b185d4e2412c84f8e30a96029f",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package", choices=tuple(PINS), required=True)
    args = parser.parse_args()
    for relative in ("host/tmp", "temp", "home"):
        (args.root / relative).mkdir(parents=True, exist_ok=True)
    directory = args.root / args.package / "recipe"
    source = directory / "PKGBUILD.pinned"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != PINS[args.package]:
        raise RuntimeError("Original recipe does not match its recovered pin")
    original = b"arch=('i686' 'x86_64')"
    if data.count(original) != 1:
        raise RuntimeError("Unexpected original architecture declaration")
    target = directory / "PKGBUILD"
    if target.exists():
        raise RuntimeError("Do not overwrite a prepared recipe")
    prepared = data.replace(original, b"arch=('aarch64')")
    target.write_bytes(prepared)
    (directory / "preparation.json").write_text(json.dumps({
        "schema": 1, "repository": "msys2/MSYS2-packages",
        "commit": "fc03a3300db9bcdd0ccc082749e006abf1a04414",
        "source_recipe": str(source), "source_recipe_sha256": PINS[args.package],
        "prepared_recipe": str(target),
        "prepared_recipe_sha256": hashlib.sha256(prepared).hexdigest(),
        "only_change": "arch=('i686' 'x86_64') -> arch=('aarch64')",
        "required_features_reduced": False,
        "source_signing": "Neither pinned recipe includes a detached signature source entry; source hashes are enforced, no detached-signature claim.",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
