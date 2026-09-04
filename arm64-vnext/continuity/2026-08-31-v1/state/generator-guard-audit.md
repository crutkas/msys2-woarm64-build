# gentls_offsets / gendef — generator guard audit (verifier, primary-source read)

Scope: read of the **pristine sealed source** at
`0a1e87db.../v9-review-restarted-scratch/producer-replay/source/base/winsup/cygwin/`.
The live ARM64 build tree (`/root/xc/w-link`) is **not reachable from here**; nothing
below is a claim about that tree.

## 1. CONFIRMED — the `.long` match is real, locations exact

`scripts/gentls_offsets` (3251 B, 40 identical copies across all sealed trees):

- line 65  `/\s*\.long\s+/`  — extracts `start_offset`
- line 88  `/\s*\.long\s+/`  — extracts every member offset
- line 81  `/\s*\.space\s*4/` — separate branch for zero-valued members

The heartbeat's mechanism and line locations are **correct**.

## 2. MEASURED — the script's only guard FAILS OPEN

Lines 103-109:

    MOD=$(awk '/_cygtls.context_p/{ print $3 % 16; }' "${output_file}")
    if [ $MOD -ne 0 ]
    then ... rm "${output_file}"; exit 1
    fi

If the `.long` branch never fires, `_cygtls.context_p` is absent, so `MOD` is **empty**.
Executed under bash 5 (Git for Windows):

    MOD=[]
    BRANCH_NOT_TAKEN_script_continues
    [: -ne: unary operator expected      <- stderr only
    final exit code: 0

`[ -ne 0 ]` is a **unary-operator error returning 2**, so the `if` is FALSE, the file is
**not** deleted and the script **exits 0**. The guard cannot detect the failure it exists
to detect — a detector that returns the same answer in both arms.

**Consequence:** `c63ab774`'s external before/after sha check was not belt-and-braces, it
was **the only thing on that path capable of catching the corruption.**

## 3. FLAGGED — a contradiction that must be resolved before the hazard is recorded as real

Two reported facts cannot both hold alongside "aarch64 never emits `.long`":

- `gentls_offsets` emits **`const uint32_t`** (lines 22 and 44) — **4-byte** objects.
  A probe measuring a **64-bit long** (`.xword`) measured the **wrong width**; the
  directive for a 4-byte object is a different one. A fix keyed on `.xword` would
  silently still fail for every member here.
- The tlsoffsets actually produced is reported **1822 B, intact, good content**
  (`49ac682b8f5e`). A file whose `.long` branch never fired would be **degenerate**
  (only `.space 4` members, all zero). **A good 1822-byte file is positive evidence
  that `.long` WAS matched.**

Status: **NOT ESTABLISHED** that the hazard materialised. Cheap resolution: compile
`extern "C" const uint32_t x = 42;` with the aarch64 cross-compiler and read the directive.

## 4. NEW — `scripts/gendef` also fails open on non-x86_64 (ninth x86-only construct)

`scripts/gendef` (11360 B, 485 lines) gates on `my $is_x86_64 = $cpu eq 'x86_64';`
(line 24), with branches at 92, 97, 113, 350.

In `fefunc` (88-111): `my $res;` is assigned **only** inside `if ($is_x86_64)`. On any
other cpu it stays **undef** for every symbol — **no `die`, no `#error`, no warning**.

Critically, **`.include "tlsoffsets"` is itself inside the `$is_x86_64` guard** (line 115).
So in the pristine generator an aarch64 build **never consumes** tlsoffsets at all, and
emits a degenerate `sigfe.s` with **exit 0**.

Body is pure x86_64: `leaq`, `movq`, `%r10`-`%r15`, `xchgl`, `xaddq`, `cpuid`, `fxsave64`.
`.\x86_64` is the **only** arch directory present; there is **no `aarch64` directory**.

Corroborates the standing finding that the sealed port was never link-capable for
aarch64, and implies the live tree carries an **unarchived** `gendef` modification.

## Standing observation

**Both generators on the tlsoffsets/sigfe path fail open with exit 0.** Neither can
detect its own failure. On this path, external artifact checks are not optional.
