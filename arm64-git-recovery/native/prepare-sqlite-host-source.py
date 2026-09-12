"""Apply only pinned-compatible host-driver fixes to a fresh private source copy."""

import json
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory

root = Path(r"C:\ag-sqlite-e138-01")
source, output = root / "prepared/source", root / "host-source-05"
verify_tree(root / "prepared", root / "prepared.inventory.json")
before = inventory(source)
expected = {
    "autosetup/proj.tcl": "bc8fe137fcddbdc8613ffe8652ec686a78895dcb1090dff900415d510ad6041f",
    "test/testrunner_data.tcl": "5347e163e963a4578d2c9918fe751ee908dc88b191e92b50806bb0159aaa1bfd",
    "test/testrunner.tcl": "9f456c1d0b30e66b9dcbfdc7753ad885226cb7d3468bce5426d28c7fb08249ce",
}
if any(before[p]["sha256"] != sha for p, sha in expected.items()):
    raise ContractError("Pinned host-driver source differs")
require_memory()
shutil.copytree(source, output)
patch = Path(__file__).parent / "patches/sqlite-3.53.4-private-host-driver.patch"
command = [root / "bootstrap/usr/bin/patch.exe", "--batch", "--forward", "--fuzz=0",
           "--no-backup-if-mismatch", "-p1", "-i", patch.resolve()]
result = subprocess.run(list(map(str, command)), cwd=output, capture_output=True, timeout=30)
(root / "host-source-05.patch.log").write_bytes(result.stdout + result.stderr)
if result.returncode:
    raise ContractError("Pinned host-driver patch failed")
after = inventory(output)
changed = {p: {"before": before.get(p), "after": after.get(p)}
           for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
if set(changed) != set(expected):
    raise ContractError("Unexpected host-driver source changes")
verify_tree(root / "prepared", root / "prepared.inventory.json")
with (root / "host-source-05.inventory.json").open("x") as stream:
    json.dump({"scope": "Only host/path/actual-executable-name hooks and opt-in standard verbose-to-persistent-file output; no test, assertion, diagnostics or feature removal",
               "patch_sha256": digest(patch), "command": list(map(str, command)), "changes": changed,
               "files": after}, stream, indent=2)
print("Pinned source-only host driver patch prepared; original complete source unchanged")
