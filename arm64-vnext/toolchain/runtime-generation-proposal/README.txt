Runtime generation hardening proposal
=====================================

Application/publication owner: crutkas/msys2-runtime session 67ba2e76.
Base: published commit 563662010c2f2072ad90f28713611caabdf70dbb.
This directory is a proposal source, not an edit to that owner's worktree.

Changes
-------
The real cygwin Makefile routes TLS and signal generation through a Perl
guard, using the existing runtime build's Perl dependency. It validates the
selected generator/source/flags/header inputs and published output hashes on
every make invocation, independently of timestamps. Unchanged output bytes
retain their timestamps, so an unchanged make does not reassemble sigfe.o.

The selected generator runs against private output files. Before publication,
the guard requires a complete, aligned, paired TLS layout; the source-selected
export list; the matching assembly labels; and public exported providers.
Each artifact is renamed atomically. The hash-bound receipt is published last:
an interrupted multi-file publication cannot be accepted as a coherent pair.
This is not a claim of a filesystem-wide atomic transaction.

The current gentls_offsets already handles .word/.long, validates its compiler
inventory, and atomically renames its result. It is intentionally unchanged.
The outer guard also protects the build if an old .long-only generator is
selected. A matching receipt with changed/truncated output fails loudly;
remove the invalid artifact's receipt explicitly to request regeneration.

Actual make controls
--------------------
The proposed winsup/testsuite/build/runtime-generation-make.py operates only
on an explicitly supplied disposable layout:
  ROOT/source      copied runtime source with this patch and autogen outputs
  ROOT/prefix      copied qualified bootstrap compiler
  ROOT/build       configured build, including reused newlib

Run the existing winsup autogen/configure stages for this new layout first.
Never copy a configured Makefile and run it before rebasing its source and
prefix paths. Keep a byte-exact TLS backup before any make invocation.

The test requires a preserved old x86-only gendef; optionally supply the old
.long-only gentls_offsets. The latter is executed unchanged. A test adapter
only accommodates its basename-only output argument, reproducing the actual
56-byte zero-offset output; it does not repair or replace the old parser.

  python3 SOURCE/winsup/testsuite/build/runtime-generation-make.py \
    --root ROOT --output ROOT/make-controls \
    --stale-generator OLD_GENDEF \
    --stale-tls-generator OLD_GENTLS_OFFSETS

The old source blobs can be exported with git show from
d890a845e992638a6f09560efacc26d15b3ffe6a: winsup/cygwin/scripts/gendef and
winsup/cygwin/scripts/gentls_offsets.

The controls invoke the actual configured make targets, not extracted recipes:
successful creation; unchanged repeat; stale/empty/failing generation;
missing labels and exports; zero/malformed TLS; compiler failures; historical
parser corruption; corrupt files newer than their dependencies; and complete
clean regeneration. Failure cases require every prior output/receipt/object
hash to remain unchanged. Existing 40 gentls_offsets controls are retained.

Scope
-----
No runtime C/C++/assembly ABI source changes, DLL rebuild, observer decoding,
autoload/import fixes, CI check suppression, or edits to frozen cohorts.
The independent Python guard in the build repository enforces the same
source/TLS/export principles; the Perl implementation avoids introducing a
new Python prerequisite into the runtime's production bootstrap.
