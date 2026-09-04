# Required upstream fix: LLVM/Clang has no AArch64 Cygwin TargetInfo

Epoch: `2026-08-31-v1`
Recorded: `2026-09-03T01:22:00Z`
Status: **BLOCKS A SHIPPABLE NATIVE ARM64 `msys-2.0.dll` — BUT THE REQUIRED DATA MODEL IS
CONTESTED, SEE "Ecosystem data model is not settled" BELOW**
Classification: external toolchain gap. Not a defect in this programme's source, and not
fixable inside `msys2-runtime`.

## One-line statement

Clang accepts the triple `aarch64-pc-cygwin` but has no `TargetInfo` registered for it, so
the triple silently resolves to a generic Windows LLP64 target with **no Cygwin identity at
all**. Whether the correct fix is an LP64 `TargetInfo` (parity with `x86_64-pc-cygwin`) or
an LLP64 / Microsoft-ABI target (parity with existing GCC work) is an **open ecosystem
question recorded below**, and it must be answered before any LLVM work begins.

## Ecosystem data model is not settled

This document originally asserted LP64 as the required target, reasoning from
`x86_64-pc-cygwin`. That assertion is **contested by verified evidence** and is downgraded
to one of two candidate positions.

Verified 2026-09-03 via the GitHub API against `crutkas/gcc-woarm64`, a fork of
**`Windows-on-ARM-Experiments/gcc-woarm64`**, branch `woarm64`, HEAD
`5688a17320e775944bbe795010ebe7e89fc7a628` dated 2025-06-23. In `gcc/config.gcc`:

```
1275: aarch64-*-cygwin*)
1276:   tm_file="${tm_file} aarch64/aarch64-abi-ms.h"
1295:   aarch64_multilibs="llp64"
1301:   tm_defines="${tm_defines} TARGET_64BIT=1 TARGET_CYGWIN64=1 TARGET_64BIT_MS_ABI=1 TARGET_AARCH64_MS_ABI=1"
1302:   TM_MULTILIB_CONFIG="${TM_MULTILIB_CONFIG},llp64"
```

An existing Windows-on-Arm ecosystem effort has therefore already implemented
`aarch64-*-cygwin` and deliberately chosen **LLP64 with the Microsoft ABI**. That is a
coherent design position, not an oversight: it aligns ARM64 Cygwin with the native Windows
ARM64 ABI rather than with x86_64 Cygwin.

The two candidate positions are:

| | **A — LP64** | **B — LLP64 + MS ABI** |
|---|---|---|
| Parity with | `x86_64-pc-cygwin` | existing `Windows-on-ARM-Experiments/gcc-woarm64` |
| LLVM work needed | new AArch64 Cygwin `TargetInfo` | possibly none |
| The 11 recorded sites | genuine artifacts; leave unpatched | **real work items to fix properly** |
| `long` | 8 bytes | 4 bytes |

**This changes what the 11 LLP64-artifact sites mean.** Under A they are correct failures
that must not be touched. Under B they are legitimate porting work. Do not act on either
interpretation until the data model is decided.

## Verified evidence — Clang has no AArch64 Cygwin target


Host compiler: `clang version 22.1.8`, default target `aarch64-w64-windows-gnu`, from
`...\arm64-local-workload\toolchain-root\clangarm64\bin\clang.exe`.

Probe: `clang -target <triple> -dM -E -x c <empty.c>`, filtered to data-model and platform
identity macros. Executed 2026-09-03; results reproduced verbatim.

| Macro | `aarch64-pc-cygwin` | `x86_64-pc-cygwin` | `aarch64-w64-mingw32` |
|---|---|---|---|
| `__CYGWIN__` | **absent** | `1` | absent |
| `_LP64` / `__LP64__` | **absent** | `1` / `1` | absent |
| `__SIZEOF_LONG__` | **4** | **8** | 4 |
| `__SIZEOF_POINTER__` | 8 | 8 | 8 |
| `_WIN32` | 1 | absent | 1 |
| `__MINGW32__` | absent | absent | 1 |

Two independent conclusions follow, and the second is the more damaging one.

1. **Data model differs from x86_64 Cygwin.** `aarch64-pc-cygwin` yields `long` = 4 bytes
   with 8-byte pointers, i.e. LLP64, whereas `x86_64-pc-cygwin` gives `__SIZEOF_LONG__ 8`
   and `_LP64 1`. Whether this divergence is a defect (position A) or the intended ARM64
   design (position B) is the open question above.

2. **No Cygwin identity whatsoever.** `aarch64-pc-cygwin` defines neither `__CYGWIN__` nor
   `__MINGW32__`. It is not "the mingw target under another name" — it is an unclaimed
   fallback to a bare `_WIN32` target. Every `#ifdef __CYGWIN__` in the runtime source is
   therefore silently skipped, and the failure is quiet rather than diagnosed. This
   supersedes the earlier working description that the triple was byte-identical to plain
   mingw; on preprocessor identity it is measurably distinct from both mingw and Cygwin.
   **This second finding holds under either position A or B** — a Cygwin target that does
   not define `__CYGWIN__` is wrong regardless of the chosen `long` width, and it is the
   more damaging of the two because it fails silently.

## The 11 recorded sites — do not act until the data model is decided

Under **position A (LP64)**: the Cygwin ABI fixes `long` at 64 bits, so `off_t`, `ssize_t`,
`ino_t`, and `blkcnt_t` are silently mis-sized under a 32-bit `long`. Any cast inserted to
silence the resulting diagnostics would be wrong under the real ABI and would corrupt
large-file offsets, inode numbers, and block counts at runtime rather than at build time.
The 11 sites are correct as failures and must not be touched.

Under **position B (LLP64 + MS ABI)**: the 11 sites are not artifacts at all. They are
legitimate porting work to be completed properly against an LLP64 ABI.

The bring-up session left all 11 unpatched, which is the correct conservative choice under
either position — it preserves optionality. **The standing prohibition on silencing them
with casts remains in force until the data model is decided**, because a cast is wrong
under A and is not a real fix under B.

## Scope of the change, if position A (LP64) is chosen

This would be **parity with an already-supported target**, not novel design.
`x86_64-pc-cygwin` already exists upstream; the AArch64 equivalent is missing. Expected
parity sites, to be confirmed against the pinned LLVM revision before any work starts:

- `clang/lib/Basic/Targets/AArch64.h` / `AArch64.cpp` — add a Cygwin AArch64 `TargetInfo`
  alongside the existing MinGW / Microsoft / Windows AArch64 variants, setting the LP64
  data layout and defining `__CYGWIN__`, `_LP64`, `__LP64__`.
- `clang/lib/Basic/Targets.cpp` — register the new class in the triple-to-`TargetInfo`
  dispatch so `aarch64-pc-cygwin` stops falling through to the generic Windows target.
- `clang/lib/Driver/ToolChains/` — Cygwin toolchain driver support for AArch64.
- `llvm/lib/TargetParser/Triple.cpp` — confirm environment/OS parsing for the triple.

The `x86_64-pc-cygwin` implementation is the reference to mirror throughout.

## Scope of the change, if position B (LLP64 + MS ABI) is chosen

The GCC side already exists in `Windows-on-ARM-Experiments/gcc-woarm64`. The remaining
questions are whether that fork is being upstreamed to GCC proper, whether Clang parity is
wanted at all, and — regardless of `long` width — whether Clang should still be taught to
define `__CYGWIN__` for the triple, since finding 2 above is a defect under either
position.


## GCC path — partially answered

Cygwin upstream is built with **GCC**, not Clang, so a GCC `aarch64-pc-cygwin` cross would
sidestep LLVM entirely. Since this document was first written, that question has been
**partially answered**: such a target already exists in
`Windows-on-ARM-Experiments/gcc-woarm64` (see the evidence block above), configured for
LLP64 + Microsoft ABI. Still open: whether that fork builds a working cross on this host,
whether it is being upstreamed to GCC proper, and whether binutils has matching support.

## What is unaffected either way

The completed ARM64 bring-up work is data-model-neutral and retains its value under either
position: AArch64 assembly, `CONTEXT`/`mcontext` layout, SEH fixes, TLS via `tpidr_el0`,
stack alignment, the autoload trampoline, release barriers, and long-double wrappers. Only
the 11 recorded sites are data-model-dependent.

Measured bring-up state at the scope boundary: AArch64 objects 12 to 266 with zero
non-AA64, compile errors 885 to 64, Clang crashes 19 to 0, `#error unimplemented` sites 16
to 1. Nothing links, no DLL exists, and no product PASS is claimed.

## Consequence for the programme

The native ARM64 Git Bash engineering handoff cannot be completed until the ecosystem data
model is decided and a corresponding working toolchain exists — either an LLVM AArch64
Cygwin `TargetInfo` (position A) or a validated GCC cross from the existing LLP64 work
(position B). This is an external dependency; no amount of additional local porting effort
closes it, and picking the wrong position wastes the effort spent under it.

**Next action is a decision, not engineering:** settle A versus B with the Windows-on-Arm
ecosystem before committing to either toolchain path.

