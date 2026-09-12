"""Record actual compatibility-path semantics without manufacturing a package link."""

import argparse
import os
from pathlib import Path

from sources import ContractError, inventory
from ssh_bootstrap import write_json


def main(root):
    stage = root / "stage"
    canonical = stage / "usr/share/terminfo"
    if not canonical.is_dir():
        raise ContractError("Native canonical terminfo payload is missing")
    link = stage / "usr/lib/terminfo"
    if link.is_symlink():
        kind = "real-directory-symlink"
        qualified = link.resolve() == canonical.resolve() and os.readlink(link).replace("\\", "/") == "../share/terminfo"
    elif link.is_dir() and not link.is_junction():
        kind = "directory-created-by-upstream-install"
        qualified = False
    elif not link.exists():
        kind = "not-created-by-upstream-install"
        qualified = False
    else:
        raise ContractError("Unsupported terminfo compatibility-path representation")
    gate = {
        "path": "usr/lib/terminfo", "required_target": "../share/terminfo",
        "actual": kind, "qualified_as_symlink": qualified,
        "reason": "Destination type/order boundary; native symlink privilege availability was not measured",
        "canonical_files": len(inventory(canonical)),
        "remaining_gate": None if qualified else "Provider-owned creation of the genuine relative package symlink",
    }
    write_json(root / "package-link-gate.json", gate)
    print(f"terminfo compatibility path: {kind}; package symlink qualified={qualified}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    main(parser.parse_args().root)
