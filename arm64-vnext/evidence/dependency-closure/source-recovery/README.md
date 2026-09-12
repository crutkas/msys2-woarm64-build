# Unpublished producer source recovery - NOT a qualified merged change

This is a separate emergency source backup added after the sealed-evidence
commit `7368ba69e60e7092792c10ee5f1c5c8aea3923da`. Do not interpret it as a
blanket-reviewed or qualified build-engine change. The original working tree
contains imported pipeline changes as well as this session's completed and
experimental leaf work. The source is archived here rather than installed
into the repository's live build scripts.

## Captured state

- 158 current source files: 20 tracked modifications and 138 untracked files.
- 18 session-local analysis/qualification/diagnostic scripts.
- 99 checkpoint refs belonging to this session, with 115 additional distinct
  historical source blobs not in the current patch or visible remote refs.
- Zero staged changes, zero local-only commits reachable from HEAD, and zero
  stash entries at capture. The original dirty worktree is NOT called clean.

The 636,626-byte `current-working-tree.patch` has SHA256
`931096cb524f6c7d53ff1ba627fc47773d9aee32021e2486627703a8688e367a`.
Its base is exactly `7368ba69e60e7092792c10ee5f1c5c8aea3923da`.
The extra historical blobs total 537,094 bytes. Checkpoint blobs are explicitly
UNQUALIFIED intermediate states, not fixes validated by this source backup.

## Recovering the current working-tree state

`current-working-tree.patch` is a binary-capable, full-index Git patch against
the exact base commit recorded in `source-inventory.json`. It includes tracked
source modifications AND untracked source files. Raw file bytes were hashed
without clean/EOL filters, including Windows line endings. The original index
and working files were not changed when creating the patch.

In a NEW recovery checkout at that base, inspect the patch, run
`git apply --check --binary current-working-tree.patch`, then apply it with
`git apply --binary current-working-tree.patch`. Use an explicit path to the
patch if it is outside the checkout. Compare every restored file with the
SHA256 in `source-inventory.json`; a different base may need reconciliation.
The preservation process also applied the patch to an isolated temporary
index and verified the recovered Git blob SHA256 values.

`session-source/` preserves this session's standalone audit, qualification,
sealing, and diagnostic scripts from its original session-state `files`
directory. They are source, not evidence outcomes. Original absolute paths,
exact hashes and scope are recorded in the inventory. They contain historical
hard-coded local roots and must be reviewed/rebound before execution.

## Qualification by source area

| Area | Honest state and scope |
|---|---|
| `.github/scripts/less/`, `tests/native-less-*` | Used for the completed native MSYS less704 package on exact907 runtime, full upstream 18/18 and regular native PTY/moved/>4GiB controls. Test-layout failures were retained. Later helper edits not rerun are not independently requalified by this backup. |
| `.github/scripts/native-utilities/`, `tests/native-utilities/` | Used for native907 which2.25 and dos2unix7.5.7 producer/admission work. Which had 15 before/move controls; dos2unix had original174 checks plus30 before/move controls. Native argv transport is test-only. No d70/full-release claim. |
| `patches/pcre2/`, PCRE2 preparation/readback scripts | Full MinGW PCRE2 10.48-3 work retained normal widths/JIT/Unicode; source-bound upstream/static/shared checks passed. Its versioned DLL is not the retained Git10.48-1 unversioned DLL. |
| Session audit/qualification scripts | Produced the preserved libintl/PCRE2 consumer and closure/TLS receipts. Not product code and not general-purpose audited tools; original failed exploratory variants may remain. |
| Other `.github/scripts/`, `packages/`, `patches/makepkg/`, root configuration/README and generic tests | Mixed imported/pre-existing pipeline work. This leaf does not establish independent correctness, full integration, qualification, or upstream ownership. Preserve for review; do not treat as a validated new compiler/bootstrap fix. |
| Historical checkpoint variants | Recovery-only intermediate source states, including failed/unfinished approaches. They are NOT recommended replacements for the current snapshot or evidence-bound final versions. |

This backup does not rebuild anything. It is not a remote-ref uniqueness
claim for every included file: current source is preserved conservatively
even if a peer later pushed identical bytes. Local-only checkpoint variants
are compared against the remote-tracking objects visible at capture time.
No other session's worktree or source history is archived here.

The inventory records staged state, local-only branch commits, stash count,
this worktree's reflog, and this session's checkpoint-ref coverage. A clean
remote branch does not imply a clean working tree. These recovery artifacts
make the source remotely retrievable without discarding the original dirty
files or falsely claiming they were landed as qualified changes.

## Checkpoint recovery

`checkpoint-recovery.json` records the checkpoint refs scoped to producer
session `accd408a-aaf0-40b4-bc67-83995f29feec`. Additional historical source
blobs not already recoverable from the current snapshot or remote refs are
stored once in `checkpoint-source/`, keyed by their original Git blob ID.
The manifest maps each historical path/mode/commit to its blob and SHA256.
To inspect a historical file, copy that exact blob to the path recorded for
the selected checkpoint. Do NOT blindly overlay every version together.
This is source-state recovery, not preservation of executable payloads or a
claim that dangling objects belonging to other sessions have been swept.
