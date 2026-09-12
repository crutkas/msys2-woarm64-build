"""Preserve unexpected private cache writes without blessing an altered bootstrap."""

import json
from pathlib import Path
import shutil

from sources import ContractError, inventory, verify_tree


root = Path(r"C:\ag-sqlite-e138-01")
bootstrap = root / "bootstrap"
manifest = root / "bootstrap.inventory.json"
expected = json.loads(manifest.read_text())["files"]
actual = inventory(bootstrap)
if any(actual.get(p) != v for p, v in expected.items()):
    raise ContractError("An original bootstrap file changed; do not restore automatically")
added = {p: v for p, v in actual.items() if p not in expected}
if not added or any(not p.startswith("home/crutkasLocal/.cache/ccache/") for p in added):
    raise ContractError("Unexpected bootstrap delta outside the observed private ccache")
out = root / "unexpected-bootstrap-cache-01"
out.mkdir()
for p in added:
    dest = out / p
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(bootstrap / p, dest)
if inventory(out) != added:
    raise ContractError("Preserved cache evidence differs")
verify_tree(bootstrap, manifest)
with (root / "unexpected-bootstrap-cache-01.json").open("x") as stream:
    json.dump({"status": "unexpected-private-cache-files-preserved-original-files-unchanged",
               "files": added, "bootstrap_restored_to_exact_expected_inventory": True}, stream, indent=2)
print(f"Preserved {len(added)} generated cache files; original bootstrap inventory restored")
