# Sealed-port reading: `cygwin.sc.in` and `mkimport` architecture conditionals

Status: **MEASURED**, read-only. Originated in **this verifier thread**.
Purpose: supply a **third, independent input** to a dispute between two parties who
were both reading the same post-fix tree. This file predates both.

---

## HEADLINE FINDING ABOUT THE SEAL ITSELF

**THE SEALED PORT WAS NEVER LINK-CAPABLE FOR AARCH64.**

`cygwin.sc.in` lines 1–10 end in `#else / #error unimplemented for this target /
#endif`. Any non-`__x86_64__` target **fails at preprocessing**. Therefore:

- the port as sealed could not have produced an ARM64 image at all;
- **every ARM64 link ever performed necessarily used a modified `cygwin.sc.in`**;
- **no such modified copy exists in any archive reachable from this session** —
  `__aarch64__` appears in **0 of 60** `cygwin.sc*` files.

This is a statement about the seal's completeness, independent of any dispute, and
it should appear in any future description of the port's true state. The seal is
not a link-capable ARM64 port; it is an x86_64 tree with ARM64 work alongside it.

---

## What was read, and its provenance

**58 copies** of `winsup/cygwin/cygwin.sc.in` and **58 copies** of
`winsup/cygwin/scripts/mkimport` across six session file-stores.

`cygwin.sc.in` resolves to only **two** SHA-256 values:

| sha256 | size | copies | line endings |
|---|---|---|---|
| `73979b6307f35fc2c9d3c272f531fb0a4950e4913bd6d82e009a3fcd041bb781` | 5,157 B | 56 | LF (CR=0, LF=165) |
| `2356556a0abb4d40da8eaa8c1397c38b24c3bc7225b7b554989f72323fe5eac2` | 5,322 B | 2 | CRLF (CR=165, LF=165) |

`5322 − 5157 = 165` = the LF count. `Compare-Object` reports **zero** content
differences. **The two hashes are the same file in different line endings, so all
58 copies are content-identical.**

Provenance anchors — all six verified **MATCH** to `73979b63…`:

- `v7-generator-oracle-probe/pristine/`
- `runtime-abi-v8-rehearsal-…/candidate-producer-run/source/base/`
- `runtime-abi-v8-rehearsal-…/final-staging-producer-run/source/work/`
- `runtime-generator-pr31-guarded-rebuild-2026-09-01-v1/source/`
- `runtime-generator-pr31-streaming-rebuild-2026-09-01-v2/source/`
- `runtime-generator-pr31-valid-stdin-rebuild-2026-09-01-v3/source/`

That set spans every sealed rehearsal input **and all three PR #31 rebuild
sources**. This is the port's baseline, not one party's working copy.

## 1. The constructor-list conditional — verbatim

`winsup/cygwin/cygwin.sc.in`, lines 24–35, sha256 `73979b63…`:

```
#ifdef __x86_64__
    . = ALIGN(8);
     ___CTOR_LIST__ = .; __CTOR_LIST__ = .;
			LONG (-1); LONG (-1); *(SORT(.ctors.*)); *(.ctors); *(.ctor); LONG (0); LONG (0);
     ___DTOR_LIST__ = .; __DTOR_LIST__ = .;
			LONG (-1); LONG (-1); *(SORT(.dtors.*)); *(.dtors); *(.dtor);  LONG (0); LONG (0);
#else
     ___CTOR_LIST__ = .; __CTOR_LIST__ = .;
			LONG (-1); *(SORT(.ctors.*)); *(.ctors); *(.ctor); LONG (0);
     ___DTOR_LIST__ = .; __DTOR_LIST__ = .;
			LONG (-1); *(SORT(.dtors.*)); *(.dtors); *(.dtor);  LONG (0);
#endif
```

**It reads `#ifdef __x86_64__`. It does NOT read `#if defined(__x86_64__) || defined(__aarch64__)`.**

**`__aarch64__` appears in 0 of 60 `cygwin.sc*` files** and in **0 of 58 `mkimport`
copies** in the entire corpus.

Structural consequence: on any non-`__x86_64__` target the `#else` branch emits a
**single 4-byte `LONG(-1)` / `LONG(0)` per list** — the 32-bit x86 layout — with no
`ALIGN(8)`. The paired 8-byte form exists only on the true branch. Corroborated
against the generated artifact: the preprocessed `cygwin.sc` from the PR #31
`x86_64-pc-cygwin` build carries the **paired** markers, confirming the true branch
behaves as read.

## 2. Bound on what this evidence can settle — stated explicitly

Lines 1–10 of the same file:

```
#ifdef __x86_64__
OUTPUT_FORMAT(pei-x86-64)
...
#else
#error unimplemented for this target
#endif
```

**An unmodified `cygwin.sc.in` cannot link for aarch64 at all — it hard-`#error`s.**
Therefore any ARM64 link necessarily used a *modified* copy, and no such copy exists
in this corpus.

So this settles exactly one thing, and I will not stretch it further:

- **The baseline is `#ifdef __x86_64__`.** The widened form is *not* original; it was
  introduced by someone at some point. The retraction's premise — that the file
  "already contained" the widened form and the fix was therefore a no-op — is **false
  as a statement about the port's baseline**.
- **It does not establish** what `/root/xc/w-link/…/cygwin.sc.in` contained at the
  moment the failing binary was linked. I did not observe that tree and make no claim
  about it. Adjudicating the A/B remains outside what I measured.

## 3. Third instance — `.xdata` is x86-gated

Lines 79–84:

```
#ifdef __x86_64__
  .xdata ALIGN(__section_alignment__) :
  {
    *(.xdata*)
  }
#endif
```

On a non-x86_64 target **the entire `.xdata` output-section rule disappears**.
ARM64 PE requires `.xdata` for unwind information, and `.pdata` (lines 76–78) is
*not* gated.

### RESOLVED — measured by me on four shipped ARM64 images

I raised this as unverified, so I closed it with my own measurement rather than on
report. Raw PE parse of the section table and `DataDirectory[3]`:

| Image | sha256 (16) | `.xdata` VMA | `.pdata` VMA | Exc dir → `.pdata` | DllChar |
|---|---|---|---|---|---|
| `msys-2.0.dll` | `b94889a0a725025c` | `0x180315000` | `0x180329000` | **YES** | `0x0160` |
| `msys-2.0-teb.dll` | `3cf8d39b8509b813` | `0x180315000` | `0x180329000` | **YES** | `0x0160` |
| `msys-2.0-fixedbase.dll` | `5914644f37789006` | `0x180315000` | `0x180329000` | **YES** | **`0x0100`** |
| `msys-2.0-ctorfix.dll` | `3d305115caccc509` | `0x180315000` | `0x180329000` | **YES** | `0x0160` |

`.xdata` **is** present in all four, sits **immediately before** `.pdata`, and the
PE exception directory (`RVA=0x2e9000`, `size=0xbab8`) points exactly at `.pdata`.
This **independently reproduces session `57224227`'s figures** — `0x180315000` and
`0x180329000` — on four images, from a raw parse.

**Mechanism confirmed as orphan placement, not rule.** `.rdata` ends at
`0x26f000 + 0x65900 = 0x2d4900`, and `.xdata` begins at the next page, `0x2d5000`.
With no output-section rule on ARM64, `.xdata` is an orphan and binutils placed it
adjacent to the section whose characteristics match (`0x40000040`, identical to
`.rdata` and `.pdata`).

**So unwind works today, but by heuristic rather than by rule.** The asymmetry is
the tell: `.pdata` ungated at 76–78 while `.xdata` is gated at 79 is not a choice
anyone would make deliberately. A link-order or binutils change could relocate
exception data silently, with no diagnostic. Worth fixing even though nothing is
broken now.

### Two incidental measurements from the same parse

1. **`.pdata` size `0xbab8` = 47,800 bytes. ÷ 8 = 5,975 exact; ÷ 12 = 3,983.33
   (remainder 4).** This re-confirms the ARM64 8-byte `RUNTIME_FUNCTION` from the PE
   data directory — an independent path to the same figure, on the shipped images.
2. **`ImageBase` is `0x180040000`, not `0x180000000`.** Any statement about the
   image's preferred base should use `0x180040000`.

### FLAG — possible ASLR regression, ordering assumed not verified

`msys-2.0-fixedbase.dll` carries `DllCharacteristics 0x0100` (dynamic-base cleared),
but `msys-2.0-ctorfix.dll` carries **`0x0160`** — `HIGH_ENTROPY_VA | DYNAMIC_BASE |
NX_COMPAT`, i.e. **ASLR back on**. If `ctorfix` was built after `fixedbase`, the
ASLR fix did **not** carry forward into it. **I did not establish build order** —
this is inferred from names only, and names are not evidence of content. Raised for
the owner of those trees to confirm or dismiss.

## 4. Fourth instance — `mkimport`

`winsup/cygwin/scripts/mkimport`, sha256 `27bb7cdcbb30…` (56 copies; the other 2 are
the same file in CRLF — `2464 − 2358 = 106` = its LF count):

```perl
26: my $is_x86_64 = ($cpu eq 'x86_64' ? 1 : 0);
...
61: 	if ($is_x86_64) {
62: 	    print $as_fd <<EOF;
63: 	.text
64: 	.extern	$imp_sym
65: 	.global	$glob_sym
66: $glob_sym:
67: 	jmp	*$imp_sym(%rip)
68: EOF
69: 	} else {
70: 	    print $as_fd <<EOF;
71: 	.text
72: 	.extern	$imp_sym
73: 	.global	$glob_sym
74: $glob_sym:
75: 	jmp	*$imp_sym
76: EOF
77: 	}
```

Confirmed as described: `$cpu eq 'x86_64'` with a **32-bit x86 `jmp *$imp_sym`
fallback**. That fallback is x86 assembly and is not valid AArch64 — on ARM64 it
would be fed to an AArch64 assembler.

## Answer to the bounding question

**All four instances of the pattern were present in the seal. None is aarch64-aware.
None was introduced later.**

| # | Location | Seal state |
|---|---|---|
| 1 | `cygwin.sc.in:24` ctor/dtor lists | `#ifdef __x86_64__` — present in seal |
| 2 | `cygwin.sc.in:1` `OUTPUT_FORMAT` + `#error` | present in seal |
| 3 | `cygwin.sc.in:79` `.xdata` section | present in seal |
| 4 | `mkimport:26,61` `$cpu eq 'x86_64'` | present in seal |

## Labelling

- **Measured**: every hash, copy count, line-ending count, verbatim quotation, the
  zero-hit `__aarch64__` searches, the paired markers in the generated x86_64
  `cygwin.sc`, and the full PE parse of all four ARM64 images (`.xdata`/`.pdata`
  VMAs, exception-directory target, `.pdata` size arithmetic, `ImageBase`,
  `DllCharacteristics`).
- **Derived**: that the `#else` branch yields 4-byte markers on ARM64 (read from the
  script text; no ARM64 link was produced or inspected by me); that `.xdata`
  placement is orphan-driven (inferred from the absence of a rule plus adjacency to
  identically-charactered sections).
- **Presumed**: nothing.
- **Explicitly not established**: the contents of `w-link` at link time; the merits
  of either disputant's A/B; the build order of the four ARM64 images, and therefore
  whether the `0x0160` on `ctorfix` is a regression or simply an earlier build.


---

## DLL ASLR is per-image-per-boot, not per-process (MEASURED)

Added because a second session (`68c032ba`, fork diagnosis) independently re-derived `--disable-dynamicbase` as the fix, on the premise that **the child receives a different DLL base than the parent**. That premise is false.

**My first attempt at this test had no sensitivity and was discarded.** I used Git for Windows' `msys-2.0.dll` and saw one identical base across 4 concurrent processes - but that DLL carries `DllCharacteristics=0x0000`, ASLR **disabled**, so the result said nothing about ASLR. A detector that cannot vary cannot report a negative.

Re-run with a copy of a stock ARM64 DLL carrying **`DllCharacteristics=0x4160`**, `DYNAMIC_BASE` **set**:

| Condition | Base |
|---|---|
| 5 concurrent processes | `0x7ffe4ed60000` - **all five identical** |
| 3 sequential loads after full unload | `0x7ffe4ed60000` - identical |
| distinct bases observed | **1** |

**The address is not the preferred base**, so the image *was* relocated and ASLR is demonstrably in effect - yet every process received the same address. **Windows randomises a given image once per boot, not per process.**

Consequence: `fork` requires *same base in parent and child*, **not** *fixed base*, and ASLR satisfies that. What the port loses is the guarantee **by construction**; the invariant must now be verified rather than inherited.

Combined with the six-DLL `err 193` result, `--disable-dynamicbase` is **both** premised on a false mechanism **and** actively harmful: it yields an image that cannot load at all.
