# Programme reconciliation and merge-readiness evidence

These are read-only API snapshots, exact source comparisons, owner-gate records
and small primary receipts used by the September 11 continuity reconciliation.
`preservation-manifest.json` maps each copied file to its original absolute path,
size and SHA-256. All copied bytes are preserved under `-text`; no historical
receipt is rewritten to claim a different source, runtime or observation date.

`merge-readiness-20260911/` contains the eight-PR API snapshots, changed-file
lists and the two versions of the shared `bounded_process.py` helper and test.
The helper has a real semantic conflict; the test has only CRLF/LF differences.
Both raw copies remain preserved. `owner-gates.json` is a dated operational
record, not permission to change a branch on a new machine.

`source-receipts/` retains small evidence records that the plan cites, including
the combined-runtime handoff, limited libintl/PCRE2 admissions, the Perl symlink
boundary, the old TLS proposal and its independent successor, verified Texinfo
CI success, and the completed D70 Berkeley DB matrix/timing resolution. The
original package/runtime producers own complete evidence exports on their
branches; copying these receipts is not a substitute for their payload,
source, toolchain and reproducibility evidence.

`rehydration-20260911/` captures the PR/API state during preservation. Remote
heads and CI can change after these snapshots. Re-query GitHub before making
merge/readiness claims; `mergeable:true` never implied green checks, joint
conflict-free integration or release admission.

Known limits remain explicit: native CI has no registered matching runner;
the 81 strict blocker verdict is not reduced by limited-MVP admissions;
successful Git HTTPS does not admit the superseded OpenSSL payload it loaded;
the 24-case DB matrix used D70, not the newer combined runtime. The current
repository-only recovery instructions are in
`arm64-vnext/continuity/2026-08-31-v1/state/REHYDRATE.md`.
