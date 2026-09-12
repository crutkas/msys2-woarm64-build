"""Emergency source-only preservation; no measured-evidence or payload changes."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(r"C:\Users\crutkasLocal\.copilot\repos\copilot-worktrees\msys2-woarm64-build\crutkas-probable-lamp")
DEST = ROOT / "arm64-vnext/uncommitted-source/sqlite"
PREVIOUS = "cf14af6003dcecbd04cc1a794580c3cc4a8987d3"
REMOTE = "refs/heads/crutkas-native-sqlite-integration"
CONTROLLERS = Path(r"C:\ag-mvp-independent-sqlite-20260911")
SESSION = Path(r"C:\Users\crutkasLocal\.copilot\session-state\cef79b93-6630-4263-a181-35a10e8c9bba\files")
FILES = [
    ("external-mvp/final_failure_readback.py", CONTROLLERS / "final_failure_readback.py"),
    ("external-mvp/final_zip_replay.py", CONTROLLERS / "final_zip_replay.py"),
    ("external-mvp/fixed_verifier_replay.py", CONTROLLERS / "fixed_verifier_replay.py"),
    ("external-mvp/independent_replay.py", CONTROLLERS / "independent_replay.py"),
    ("preservation-tools/preserve_sqlite_evidence.py", SESSION / "preserve_sqlite_evidence.py"),
    ("preservation-tools/preserve_sqlite_source.py", Path(__file__).resolve()),
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


status = git("status", "--porcelain=v1", "--untracked-files=all")
if status:
    raise ValueError("Worktree changed since clean sweep; inspect rather than overwrite")
if git("rev-parse", "HEAD").decode().strip() != PREVIOUS:
    raise ValueError("Branch head changed; reconcile before preservation")
remote = git("ls-remote", "--heads", "origin", REMOTE).decode().split()
if not remote or remote[0] != PREVIOUS:
    raise ValueError("Remote source-preservation head differs")
reachable = {row.split(b" ", 1)[0].decode() for row in git("rev-list", "--objects", "--remotes").splitlines()}
tracked = []
for row in git("ls-tree", "-r", PREVIOUS, "--", "arm64-git-recovery/native").splitlines():
    metadata, name = row.split(b"\t", 1)
    mode, kind, oid = metadata.decode().split()
    if kind != "blob":
        raise ValueError("Unexpected source tree entry")
    path = ROOT / name.decode()
    data = path.read_bytes()
    tracked.append({"path": name.decode(), "remote_blob": oid, "working_bytes_sha256": sha(data),
                    "size": len(data), "byte_identical_to_remote_blob": blob(data) == oid})
if len(tracked) != 75:
    raise ValueError("Expected the independently reported75-file remote preservation commit")

DEST.mkdir(parents=True, exist_ok=False)
(DEST / ".gitattributes").write_bytes(b"* -text\n** -text\n")
rows = []
for relative, original in FILES:
    data = original.read_bytes()
    if original.suffix != ".py" or b"\0" in data or data.startswith((b"MZ", b"PK\x03\x04", b"MDMP")):
        raise ValueError(f"Not an expected pure Python source: {original}")
    if any(line.strip().startswith(b"-----BEGIN ") and line.rstrip().endswith(b"PRIVATE KEY-----")
           for line in data.splitlines()):
        raise ValueError("Unexpected private-key material")
    dest = DEST / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, dest)
    if dest.read_bytes() != data or original.read_bytes() != data:
        raise ValueError("Source changed while copying")
    oid = blob(data)
    normalized = blob(data.replace(b"\r\n", b"\n"))
    rows.append({
        "path": relative, "original_absolute_path": str(original), "size": len(data),
        "sha256": sha(data), "raw_git_blob_sha1": oid,
        "raw_blob_in_locally_known_remote_history": oid in reachable,
        "lf_normalized_blob_in_locally_known_remote_history": normalized in reachable,
        "classification": "UNCOMMITTED SOURCE: originally outside the project checkout; emergency custody snapshot only",
    })

record = {
    "schema": 1, "classification": "UNCOMMITTED SOURCE",
    "meaning": "Originally local-only source preserved in this emergency commit, not an integration/review/admission commit",
    "reviewed": False, "ci_tested": False, "part_of_qualified_artifact": False,
    "validation_claim": "None. Some scripts orchestrated recorded experiments, but this source snapshot itself is unreviewed and not artifact-qualified.",
    "worktree_status_at_sweep": status.decode(),
    "tracked_modifications_at_sweep": 0, "untracked_worktree_files_at_sweep": 0,
    "already_remote": {"commit": PREVIOUS, "branch": REMOTE, "file_count": len(tracked),
                       "scope": "75 recovery source files were already pushed by a separate preservation action; not duplicated here",
                       "files": tracked},
    "remote_search_scope": "Exact and LF-normalized blobs compared with locally known origin remote-tracking history; not a universal GitHub search",
    "source_files": rows,
    "evidence_tree_modified": False,
    "authoritative_sqlite_flags_unchanged": {"mvp_runtime_only": True, "provider_admitted": False,
                                          "historical_failures_waived": False},
    "rehydration": "Resolve hard-coded historical paths and inspect scripts before use. Do not execute merely because source was preserved.",
}
(DEST / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
intro = """# UNCOMMITTED SOURCE - SQLite and independent MVP controllers

**Emergency source-custody snapshot, NOT reviewed integration source.**
These files were originally local-only and outside the project checkout.
This preservation commit makes them durable; it does not make them reviewed,
CI-tested, validated, or part of any qualified artifact. Some scripts drove
recorded experiments, but their presence here grants no qualification claim.

This source snapshot is deliberately separate from `arm64-vnext/evidence/sqlite/`.
No measured receipt, result, or failure was changed. The existing SQLite scope
remains authoritative: **`mvp_runtime_only: true`, `provider_admitted: false`,
`historical_failures_waived: false`**.

## Sweep result

`git status --porcelain=v1 --untracked-files=all` was empty: no remaining tracked
modifications or untracked files in the worktree. The intervening remote commit
`cf14af6003dcecbd04cc1a794580c3cc4a8987d3` had already preserved all **75**
`arm64-git-recovery/native/` source files. That was a separate preservation
action, not an implementation/admission verdict.

Four additional authored MVP replay controllers and the evidence-preservation
script were still outside the checkout. They are copied here along with this
source-preservation tool itself. No copied producer payload trees, binaries,
archives, generated repositories, private keys, or evidence files are included.

`source-manifest.json` records original paths, SHA-256, size, raw Git blob ID,
and whether an exact or LF-normalized blob was already reachable through
locally known remote-tracking history. This is not a universal GitHub search.
It also indexes the75 recovery files already on the confirmed remote commit.

## Byte identity and safe recovery

The recursive `-text` guard prevents newline conversion. Copy bytes unchanged
and check the hashes below. Absolute paths are historical provenance, not
instructions to create or trust those paths. Review and adapt the scripts
before executing anything: they contain host-specific paths, old input seals,
test-fixture orchestration, and preservation-only assumptions.

## Preserved source

| Snapshot path | Original absolute path | Bytes | SHA-256 |
|---|---|---:|---|
"""
lines = [intro]
for row in rows:
    lines.append(f"| `{row['path']}` | `{row['original_absolute_path']}` | {row['size']} | `{row['sha256']}` |\n")
(DEST / "README.md").write_text("".join(lines), encoding="utf-8", newline="\n")
print(json.dumps({"destination": str(DEST), "source_files": len(rows),
                  "bytes": sum(row["size"] for row in rows), "already_remote_files": len(tracked),
                  "local_only_before_snapshot": sum(not row["raw_blob_in_locally_known_remote_history"]
                                                    and not row["lf_normalized_blob_in_locally_known_remote_history"]
                                                    for row in rows),
                  "manifest_sha256": sha((DEST / "source-manifest.json").read_bytes())}))
