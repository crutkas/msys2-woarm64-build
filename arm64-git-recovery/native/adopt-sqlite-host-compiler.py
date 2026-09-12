"""Adopt the explicitly authorized h1 compiler for host generators only."""

import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory

root = Path(r"C:\ag-sqlite-e138-01")
source = Path(r"C:\ap06-2160\h1")
manifest = Path(r"C:\ap06-2160\h1-manifest.json")
seal = "80e5dd2079f540bb1c0ee448ce27d211c8e3608b1f9e690edbd0c628b88f7739"
if digest(manifest) != seal:
    raise ContractError("Authorized host generator compiler receipt differs")
record = json.loads(manifest.read_text())
expected = {row["Path"].replace("\\", "/"): row["SHA256"] for row in record["Files"]}
before = inventory(source)
if {p: row["sha256"] for p, row in before.items()} != expected:
    raise ContractError("Host compiler inventory differs")
require_memory()
shutil.copytree(source, root / "host-compiler")
if inventory(source) != before or inventory(root / "host-compiler") != before or digest(manifest) != seal:
    raise ContractError("Host compiler copy integrity failed")
with (root / "host-compiler.inventory.json").open("x") as stream:
    json.dump({"scope": "Authorized native ARM64 MinGW host generators ONLY; no SQLite/Tcl/lemon target substitution",
               "upstream_sha256": seal, "epoch": record["Epoch"], "files": before}, stream, indent=2)
print("Private host-generator compiler copied; full before/copy/after equality")
