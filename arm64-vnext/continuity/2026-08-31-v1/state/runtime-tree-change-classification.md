# msys2-runtime working tree — change classification

Produced 2026-09-03 by measurement against `d890a845e992638a6f09560efacc26d15b3ffe6a`.
Scope: `/root/xc/runtime`, the SHARED tree every worker session configured from.

**Totals: 43 modified files, 1,693 insertions, 760 deletions**, plus one untracked
directory `winsup/cygwin/math/aarch64/`. Every line below is accounted for; the three
categories sum exactly to the totals.

| Category | Files | Insertions | Deletions |
|---|---:|---:|---:|
| **Real port work** | **32** | **841** | **52** |
| Throwaway diagnostics | 3 | 5 | 1 |
| Autotools regeneration noise | 8 | 847 | 707 |
| **Total** | **43** | **1,693** | **760** |

**Roughly half of all insertions are regeneration noise carrying no engineering content.**
Any headline diff size for this work is misleading unless attributed.

## 1. Autotools regeneration noise — 8 files, 847 / 707

`compile` · `config.guess` · `config.sub` · `depcomp` · `install-sh` · `missing` ·
`mkinstalldirs` · `test-driver`

`config.guess` alone is **645 / 591**, i.e. 38% of all insertions in the entire tree.
These are regenerated helper scripts. **Exclude from any review.**

## 2. Throwaway diagnostics — 3 files, 5 / 1

| File | +/- | Purpose |
|---|---|---|
| `winsup/cygwin/math/fabsl.c` | 1/1 | target-detection probe |
| `winsup/cygwin/cygwin.sc.in` | 3/0 | linker-script probe |
| `winsup/cygwin/local_includes/cygmalloc.h` | 1/0 | `MALLOC_ALIGNMENT` collision probe |

Made in scratch **only to prove the remaining failures were source-side rather than
toolchain**. **Not proposed patches; committed nowhere.** They are the reason the
"261/8" and "265/3" rows are conditional rather than achieved.

## 3. Real port work — 32 files, 841 / 52

### 3a. From the sealed port — 29 files, 792 / 51

All 29 files touched by the sealed `arm64-port.patch` are present. **Zero were dropped.**
**27 of the 29 are unchanged in size-of-change since the seal** (sealed total 785/51,
independently reproduced here to validate the counting method).

**Two have grown since the seal, +7 insertions total:**

| File | Sealed | Tree | What changed |
|---|---|---|---|
| `local_includes/exception.h` | 39/10 | 42/10 | **The known-wrong P19 SEH edit** |
| `thread.cc` | 11/3 | 15/3 | `pause` -> `yield` + AAPCS64 sp alignment — **correct port work** |

**`exception.h` carries the defect already on record.** Its added comment asserts
verbatim: *"the struct is plain `_DISPATCHER_CONTEXT` on every architecture -- there is
no `_DISPATCHER_CONTEXT_ARM64` -- hence the mangled handler name below uses
P19_DISPATCHER_CONTEXT"*. **That universal is false** — CLANGARM64 and mingw-w64 master
both define `_DISPATCHER_CONTEXT_ARM64` and mangle to P25. This is the
version-robustness item; the fix must derive the name and delete this comment.

### 3b. Added after the seal — 3 files, 49 / 1

| File | +/- | Purpose |
|---|---|---|
| `newlib/libc/machine/aarch64/asmdefs.h` | 31/1 | PE/COFF vs ELF directive guards |
| `newlib/libc/machine/aarch64/setjmp.S` | 12/0 | same |
| `newlib/libc/machine/aarch64/rawmemchr.S` | 6/0 | same |

These fix the recorded defect that newlib AArch64 assembly uses ELF-only `.type %function`
and `.size`, which the PE assembler rejects. **Genuine port work**, simply done after the
seal — not diagnostics.

## Review guidance

A reviewable change is **category 3 only: 32 files, 841 insertions, 52 deletions** — under
half the raw insertion count. Regenerate category 1 rather than reviewing it; drop or
justify category 2; and **fix `exception.h` before any submission**, since it currently
encodes a false universal as settled design.

## Method note

Per-file patch counts were first computed with a pattern that missed **blank added
lines**, which understated the sealed patch as 760 insertions and would have reported
**8** modified files instead of 2. The error was caught by validating the computed total
against the independently recorded 785/51 before trusting any per-file delta. Validate a
counting method against a known-good total before drawing conclusions from it.