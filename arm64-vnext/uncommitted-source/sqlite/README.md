# UNCOMMITTED SOURCE - SQLite and independent MVP controllers

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
| `external-mvp/final_failure_readback.py` | `C:\ag-mvp-independent-sqlite-20260911\final_failure_readback.py` | 2990 | `dec052b37f857432b548cc68ac19ae8563ca272622585014e44368f58dcb3035` |
| `external-mvp/final_zip_replay.py` | `C:\ag-mvp-independent-sqlite-20260911\final_zip_replay.py` | 19128 | `2692d1a32033afefa0fde351fbdb2f6dbcf2796666c33b3ea637481c13fee0ec` |
| `external-mvp/fixed_verifier_replay.py` | `C:\ag-mvp-independent-sqlite-20260911\fixed_verifier_replay.py` | 5743 | `a6154aab9950d77e46927ddbc5a257939abc7aaf78e9957f1969cd69a64c3571` |
| `external-mvp/independent_replay.py` | `C:\ag-mvp-independent-sqlite-20260911\independent_replay.py` | 18480 | `13271edc6c0700882508e2559d1d75c067f215dafd6d956ec664a5d7e4ad59a2` |
| `preservation-tools/preserve_sqlite_evidence.py` | `C:\Users\crutkasLocal\.copilot\session-state\cef79b93-6630-4263-a181-35a10e8c9bba\files\preserve_sqlite_evidence.py` | 13456 | `ee410809520cacd963797a4e593327bb37da11bbe2c8ec5362bd9f55c2fc9e10` |
| `preservation-tools/preserve_sqlite_source.py` | `C:\Users\crutkasLocal\.copilot\session-state\cef79b93-6630-4263-a181-35a10e8c9bba\files\preserve_sqlite_source.py` | 8589 | `8ae1961027cd8e2b594de728d04997bc0ca8cfeed406ddba45413286b1b50510` |
