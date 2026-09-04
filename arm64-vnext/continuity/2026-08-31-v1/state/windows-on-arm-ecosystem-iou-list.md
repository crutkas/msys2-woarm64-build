# Windows on Arm — ecosystem IOU list

Epoch: `2026-08-31-v1`
Created: `2026-09-03T01:26:00Z`
Scope: upstream contributions this programme owes the ecosystem so that Windows on Arm is
properly supported, rather than locally patched.

**Read this first.** Everything below is currently staged in `crutkas/*` forks. Nothing here
has been filed against a real upstream project yet. The IOU is the upstream submission, not
the fork branch. Fork state is tracked so the debt is visible and does not quietly rot.

**Contribution channels differ by project and several do not take GitHub PRs at all.**
LLVM and the Git for Windows repos accept GitHub PRs. binutils, GCC, and Cygwin proper are
mailing-list projects (`binutils@sourceware.org`, `gcc-patches@gcc.gnu.org`,
`cygwin-patches@cygwin.com`). Any plan that assumes "open a PR" for those is wrong.

## 1. Data model — RESOLVED BY EVIDENCE: **LP64**

| Field | Value |
|---|---|
| Nature | Was framed as an ecosystem decision; **answered empirically 2026-09-03** |
| Status | **RESOLVED BY MEASUREMENT — LP64. Position B does not exist as an artifact anywhere.** |
| Unblocks | Item 2 (now unconditional); item 6 (the 11 sites stay unpatched) |
| Ratification | Evidence is decisive; **owner ratification still outstanding**. This entry records evidence, NOT a granted decision. |
| Detail | `state/llvm-aarch64-cygwin-targetinfo-upstream-requirement.md` |

**The premise that previously drove this entry was WRONG, and it was mine.** The
`aarch64-*-cygwin` target in `gcc-woarm64` does **not** produce LLP64. It produces **LP64 —
parity with `x86_64-pc-cygwin` on every data-model macro**. The target was built and
executed, not inferred: binutils and GCC configured, built and installed with exit 0
throughout, and `-fself-test` reported 7,660,717 passes.

Measured `aarch64-pc-cygwin-gcc -dM -E -x c /dev/null` (425 macros):

| Macro | Value | Macro | Value |
|---|---|---|---|
| `__CYGWIN__` | 1 | `__MINGW32__` / `__MINGW64__` | **undefined** |
| `__unix__` | 1 | `_WIN32` / `_WIN64` | **undefined** |
| `__SIZEOF_LONG__` | **8** | `__MSVCRT__` | **undefined** |
| `__SIZEOF_POINTER__` | 8 | `__SIZE_TYPE__` | `long unsigned int` |
| `_LP64` / `__LP64__` | 1 | `__WCHAR_TYPE__` | `short unsigned int` (2 bytes) |
| `__SIZEOF_LONG_DOUBLE__` | **8** | `__WINT_TYPE__` | `unsigned int` |
| `__LDBL_MANT_DIG__` | 53 | `__SEH__` | 1 |

Confirmed at **codegen**, not merely preprocessor: `_Static_assert`s for `sizeof(long)==8`,
`sizeof(void*)==8`, `sizeof(long double)==8` and `sizeof(wchar_t)==2` all pass, the negative
control `sizeof(long)==4` correctly fails, and the emitted object (`file format
pe-aarch64-little`) uses 64-bit `x` registers (`madd x0, x0, x1, x2`) where LLP64 would have
used `w` registers.

### `llp64` in `config.gcc` is a DEAD TOKEN

The `aarch64_multilibs="llp64"` line that previously drove this entry never reaches the
compiler. Four independent disproofs:

1. **The backend has no such ABI.** `-mabi=llp64` gives `error: unrecognized argument in
   option '-mabi=llp64'; valid arguments to '-mabi=' are: ilp32 lp64`.
2. **Configure discards it.** `gcc/configure.ac:4394` sets `TM_MULTILIB_CONFIG=lp64`, and the
   generated `gcc/Makefile` line 601 and `multilib.h` (`multilib_options = "mabi=lp64"`) were
   measured to carry `lp64`. *(Precision caveat, recorded deliberately: line 4394 is the only
   `TM_MULTILIB_CONFIG` assignment in `configure.ac` and it sits inside a conditional branch,
   so "unconditionally overrides" overstates the mechanism. The measured generated output is
   decisive regardless of which branch fired.)*
3. **Header override order.** `tm_file` ends `… i386/cygwin.h -> i386/cygwin-w64.h`; the last
   wins and defines `LONG_TYPE_SIZE (TARGET_64BIT ? 64 : 32)`. `config.gcc` adds
   `TARGET_64BIT=1 TARGET_CYGWIN64=1` — which the mingw block does **not** — precisely so the
   LP64 override fires. A deliberate act.
4. **Upstream agrees.** Upstream GCC master's merged `aarch64-*-mingw*` block has the
   `aarch64_multilibs` / `TM_MULTILIB_CONFIG` lines **removed**, and `llp64` returns **zero
   hits** in master's `gcc/config.gcc` (independently verified here). Reviewers already judged
   the token a no-op.

Corroborating intent: `f7c91f8df62` deliberately *deletes* `__MINGW32__`, `_WIN32`, `_WIN64`,
`WIN32`, `WINNT`, `__MSVCRT__` and `__MINGW64__` from `aarch64/cygming.h`, delegating to
`EXTRA_OS_CPP_BUILTINS()` so `i386/cygwin.h` supplies `__CYGWIN__` + `unix`. It also adds
`config.guess: aarch64:CYGWIN*) echo aarch64-pc-cygwin` (self-host intent) and a full
`libgcc/config.host` arm. Careful de-MinGW-ification, not blind copying.

### One deliberate ARM64 divergence — `long double`

`b3295b9e383` (2025-01-28, PR #3) adds `TARGET_LONG_DOUBLE_64` and `__NO_BINARY80__` to
`aarch64-coff.h`. So the correct model is **not** "ARM64 Cygwin == x86_64 Cygwin". It is
**LP64 like x86_64 Cygwin, but 64-bit `long double` unlike it** (x86_64 Cygwin carries 80-bit
x87, `__SIZEOF_LONG_DOUBLE__ 16`). A dated, deliberate, ARM64-specific ABI decision that
converges exactly with the independently measured `sizeof(long double)==8`, and it places the
sealed branch's long-double wrapper work on the right side of the line.

### Consequences

- **Clang's `aarch64-pc-cygwin` is a defect, not a competing data model.** Its
  `__SIZEOF_LONG__ 4` and missing `__CYGWIN__` are now conclusively a clang bug.
- **The 11 recorded sites stay unpatched — permanently.** See item 6.
- Cygwin's documented, architecture-neutral contract is LP64: *"While the Mingw and Microsoft
  compilers use the LLP64 data model, Cygwin compilers use the LP64 data model, just like
  Linux."* — verbatim in our own tree at `winsup/doc/gcc.xml:37-46`.
- No LLP64 branch exists anywhere in winsup; `winsup/utils/getconf.c` selects between exactly
  two models on `__LP64__`, and an LLP64 ARM64 Cygwin would make `getconf` report ILP32.

## 2. LLVM — AArch64 Cygwin `TargetInfo` (UNCONDITIONAL — data-model-neutral)

| Field | Value |
|---|---|
| Upstream | `llvm/llvm-project` (GitHub PR) |
| Status | **Scoped; patch drafted and validated. NOT filed. Awaiting owner upstream-contribution authority.** |
| Depends on | **Nothing. Explicitly NOT gated on items 1/8.** |
| Scope | Give `aarch64-pc-cygwin` a `CygwinARM64TargetInfo`, mirroring the `case llvm::Triple::Cygnus:` every peer architecture already has |

**Re-scoped 2026-09-03: this is now UNCONDITIONAL and DATA-MODEL-NEUTRAL.** It was
previously recorded as "conditional on position A" and gated on item 1. That was wrong.
Microsoft C++ mangling on a Cygwin target is incorrect under LP64 **and** under LLP64, so
unlike item 8 this needs no ABI decision to be actionable. **It is the single most
upstreamable artifact the programme holds.**

### The defect is a CONTRADICTORY identity, not an absent one

`aarch64-pc-cygwin` is constructed from `MicrosoftARM64TargetInfo` **without MSVC-compat
mode** — a hybrid. Measured:

| Triple | `_M_ARM64` | `_MSC_VER` | `_MSC_EXTENSIONS` | `_WIN32`/`_WIN64` | `__GNUC__` | `__CYGWIN__` |
|---|---|---|---|---|---|---|
| `aarch64-pc-cygwin` | 1 | absent | absent | 1 / 1 | 4 | **absent** |
| `aarch64-pc-windows-msvc` | 1 | 1933 | 1 | 1 / 1 | — | absent |

It does not merely *lack* Cygwin identity; it *positively claims* to be an MSVC ARM64
target while being driven by a Cygwin/GNU toolchain.

### DEMONSTRATED ABI break — tested, not inferred

Compiling `namespace n { struct S { int f(int); }; } int n::S::f(int x)` per target and
reading the emitted symbol:

| Triple | Mangling | Symbol |
|---|---|---|
| `x86_64-pc-cygwin` | Itanium/GNU | `_ZN1n1S1fEi` |
| `aarch64-w64-mingw32` | Itanium/GNU | `_ZN1n1S1fEi` |
| `aarch64-pc-windows-msvc` | **Microsoft** | `?f@S@n@@QEAAHH@Z` |
| `aarch64-pc-cygwin` | **Microsoft** | `?f@S@n@@QEAAHH@Z` |

`aarch64-pc-cygwin` **actually emits Microsoft-mangled C++ symbols today.** Because the
msys2 runtime is C++, every C++ symbol would be incompatible with the Cygwin/GNU
ecosystem, with libstdc++, and with the existing x86_64 Cygwin runtime. This converts an
abstract macro discrepancy into a demonstrated ABI break.

### Why the upstream argument is strong

- The Driver is **already** aarch64-Cygwin-aware: `Driver.cpp:7319` maps `Cygnus` to
  `toolchains::Cygwin` for all arches, and `Cygwin.cpp:53` / `:159-165` enumerate
  `llvm::Triple::aarch64` and emit `-m arm64pe`.
- The frontend nonetheless describes a Microsoft target. That is an **internal
  inconsistency inside `Basic`**, not a feature request.
- **Every peer architecture already carries the `case llvm::Triple::Cygnus:` that AArch64
  alone lacks**: ARM32 `Targets.cpp:242-253`, x86-32 `:612`, x86-64 `:674`. Verified
  against `llvm-project` main — exactly three such cases exist and AArch64 is not one.
- Mechanism: `Targets.cpp:185-192` dispatches `Win32` on environment, handling only `GNU`
  and `MSVC`, with `default: // Assume MSVC for unknown environments`, so `Cygnus` falls
  through to `MicrosoftARM64TargetInfo`. `_M_ARM64` is emitted at `AArch64.cpp:1839`.
- Upstream carries no `CygwinARM64TargetInfo` on main, `release/21.x` or `release/22.x`;
  commit search `cygwin aarch64` returns zero hits; the only issue hit, PR #134494,
  concerns *building* LLVM on x86_64 Cygwin and is unrelated, closed and unmerged.

### Restraint recorded as the STANDARD for this class of work

The drafted patch (43 insertions, 0 deletions, 3 files) derives from
`WindowsARM64TargetInfo` **specifically so that nothing about the type model changes**:
`__SIZEOF_LONG__` stays 4, and every width, alignment and the data-layout string stay
bit-for-bit identical. It omits `__CYGWIN64__` (which denotes the LP64 flavour) and flags
`_WIN32`/`_WIN64` retention as data-model-coupled.

Stated plainly: mirroring `CygwinX86_64TargetInfo`'s **plain-arch base** would have
supplied LP64 and dropped `_WIN32`, and would therefore have **silently answered an
undecided question** (item 8). The work identified that tension and refused to resolve it.
That is exactly right, and it is the standard for this class of work.

### v2 — the LP64 patch (CURRENT), with v1 frozen as the audit record

Once items 1 and 8 resolved to LP64, v1's neutrality became obsolete. **v2** derives from
`AArch64leTargetInfo` — the plain non-Windows base, mirroring `CygwinX86_64TargetInfo` — which
is precisely the branch v1's own "Explicitly left open" section had named. 49 insertions, 0
deletions, 3 files; applies cleanly to the same pristine `llvm-project` main. The two are
**mutually exclusive**; v1 is retained solely as the audit record.

Delta v1 -> v2: base `WindowsARM64TargetInfo` -> `AArch64leTargetInfo`; `__SIZEOF_LONG__` 4 ->
8; `_LP64`/`__LP64__` absent -> defined; `_WIN32`/`_WIN64` retained -> absent; `wint_t`
`unsigned short` -> `unsigned int`; `va_list` 8-byte `char*` -> 32-byte AAPCS64.

**The `va_list` change is a SECOND, INDEPENDENT defect that v1 would have carried.** The GCC
oracle shows an AAPCS64 32-byte `__va_list`, so `WindowsARM64TargetInfo`'s 8-byte `char*` was
wrong **regardless of `long` width**. The LP64 rebase therefore corrected something the
data-model decision alone would never have surfaced — the base-class choice mattered for more
reasons than were known when it was made.

Validated against the real GCC cross (GCC 15.0.1): 26/29 target values exact, 3 cosmetic only.
A control (clang vs GCC on `aarch64-linux`) resolves the raw 418-name diff into 380 entries of
baseline clang/GCC noise plus 38 Cygwin-specific entries, all individually accounted for.
Honest gap, flagged not claimed: `_GNU_SOURCE` for C++ is unverifiable on a C-only cross.

### `__CYGWIN64__` — omission is DOCUMENTED UPSTREAM POLICY, not preference

v2 does not define `__CYGWIN64__`. That is **compliance with stated Cygwin project policy**,
not merely oracle-matching. From our own tree, `winsup/doc/faq-programming.xml:269-278`:

> *"Why is `__CYGWIN64__` not defined for 64 bit?"* — *"There is no `__CYGWIN64__` because we
> would like to have a unified way to handle Cygwin code in portable projects. Using
> `__CYGWIN32__` and `__CYGWIN64__` only complicates the code for no good reason. Along the
> same lines you won't find predefined macros `__linux32__` and `__linux64__` on Linux."*

Verified verbatim at those exact lines. The GCC oracle complies (`__CYGWIN64__` absent,
`__CYGWIN__` defined). **Clang's shipping `x86_64-pc-cygwin` does NOT comply** — it defines
`__CYGWIN64__ 1`, confirmed from the sealed macro dump. This materially strengthens the
upstream argument: v2 follows documented policy that an existing clang target violates.

### Adjacent pre-existing clang defects — found, NOT fixed, NOT to be bundled

Three, all pre-existing, all deliberately left alone so this item stays identity-scoped:

1. `__ARM_SIZEOF_WCHAR_T` is 4 on every clang AArch64 target with a 2-byte `wchar_t`, so
   `aarch64-w64-mingw32` and `aarch64-pc-windows-msvc` contradict themselves today.
2. `_INTEGRAL_MAX_BITS` is missing on all clang Cygwin targets.
3. `CygwinX86_64TargetInfo` defines `__CYGWIN64__`, a macro the Cygwin project explicitly
   states should not exist.

**None is a regression from our patches.** Fixing them would widen an identity-scoped change
into unrelated territory and weaken the upstream argument.
**Not filed upstream. No contributor contact. LLVM contribution is a separate owner
decision that has not been granted.**


## 2b. binutils — native ARM64 `windmc`

| Field | Value |
|---|---|
| Upstream | binutils (`binutils@sourceware.org` mailing list — **not** a GitHub PR) |
| Fork | `crutkas/binutils-woarm64` |
| Status | Built and reproducible locally; **upstream scope not yet determined** |

Produced a native AA64 `windmc.exe`, 1,589,248 bytes, SHA-256
`4893ee2a9368e6089bab3fdc7d8afdb049935459fa6536b2d3eb749e39b579e5`, PE machine `0xAA64`,
COFF timestamp 0, byte-identical across two clean builds. Unsigned and hash-pinned for
local engineering use.

**Honest gap:** it has not been established whether upstream needs a code change here or
whether this was purely a build-configuration matter on this host. Determine that before
drafting any submission, or the IOU is unactionable.

## 3. BusyBox-w32 — ARM64 bootstrap tools

| Field | Value |
|---|---|
| Upstream | `rmyorston/busybox-w32` (confirm before filing) |
| Fork PR | `crutkas/busybox-w32#4` — OPEN, draft, mergeable (verified 2026-09-03) |
| Status | Two successful build checks; not filed upstream |

## 4. Git for Windows build-extra — packaging ownership and SDK foundation

| Field | Value |
|---|---|
| Upstream | `git-for-windows/build-extra` |
| Fork PR | `crutkas/build-extra#29` — OPEN, draft, mergeable (verified 2026-09-03) |
| Status | One determining job passed, four non-applicable jobs skipped; not filed upstream |

## 5. msys2-runtime — ARM64 runtime generator

| Field | Value |
|---|---|
| Upstream | `msys2/msys2-runtime`, which itself tracks Cygwin (`cygwin-patches@cygwin.com`) |
| Fork PR | `crutkas/msys2-runtime#31` — OPEN, draft, mergeable (verified 2026-09-03) |
| Status | 12 checks pass; 6 failures are external MinGW package/test drift, not caused by this patch |

## 6. msys2-runtime — the ARM64 ABI port itself

**SUPERSEDING UPDATE 2026-09-03 — read item 9 first.** Our base at `d890a845` is materially
behind an active, partly-merged upstream aarch64 Cygwin port, and parts of the 785-line diff
re-derive work already merged upstream — notably the `_CX_`/`_MC_` register mapping, which now
lives in upstream `winsup/cygwin/local_includes/register.h`. **Do not schedule further porting
against this base.**

**PERMANENT, not provisional:** the 11 recorded LLP64 sites stay **UNPATCHED**, and the
prohibition on silencing them with casts is now **PERMANENT**. Estimated remaining work on
them: **ZERO**. They are the correct, load-bearing failure signal of an unimplemented clang
target. Under LP64 a silencing cast would corrupt `off_t`, `ssize_t`, `ino_t` and `blkcnt_t`
silently, at runtime, on large files. Nobody should "clean up" that list.
| Field | Value |
|---|---|
| Upstream | `msys2/msys2-runtime` → Cygwin |
| Status | **Uncommitted.** 29 files, 785 insertions, 51 deletions. Hard stop held at 0 commits. |
| Blocked by | Item 1 |

Bring-up measured at the scope boundary: AArch64 objects 12 → 266 with zero non-AA64,
compile errors 885 → 64, Clang crashes 19 → 0, `#error unimplemented` sites 16 → 1.
Nothing links, no DLL exists, no product PASS claimed. Two verified backups exist.

The AArch64 assembly, `CONTEXT`/`mcontext` layout, SEH fixes, TLS via `tpidr_el0`, stack
alignment, autoload trampoline, release barriers, and long-double wrappers are all
data-model-neutral and survive either resolution of item 1. Only the 11 recorded
LLP64-artifact sites are toolchain-specific, and they must stay unpatched — casting them
away would corrupt `off_t`, `ssize_t`, `ino_t`, and `blkcnt_t` at runtime.

## 7. GCC `aarch64-pc-cygwin` cross — ANSWERED: it builds, it works, it is LP64, it is fork-only

**ANSWERED 2026-09-03 — built and measured.** The triple is not hypothetical: an
`aarch64-*-cygwin*` target **already exists** in `crutkas/gcc-woarm64` branch
`woarm64` at `gcc/config.gcc:1275`. Verified verbatim from a local checkout.

It pulls `aarch64/aarch64-abi-ms.h`, `aarch64/aarch64-coff.h`,
`aarch64/cygming.h`, `i386/cygwin.h`, `i386/cygwin-w64.h`,
`i386/cygwin-stdint.h`, `mingw/winnt.h`, and `mingw/winnt-dll.h`, and sets
`TARGET_64BIT=1 TARGET_CYGWIN64=1 TARGET_64BIT_MS_ABI=1 TARGET_AARCH64_MS_ABI=1`.

**CORRECTED 2026-09-03 — the earlier reading recorded here was WRONG.** Line 1295 does set
`aarch64_multilibs="llp64"` and line 1302 does append it to `TM_MULTILIB_CONFIG`, but that
token is **DEAD** and never reaches the compiler. The target was built and measured: it is
**LP64**, not LLP64. See item 1 for the four independent disproofs and the 425-macro dump.
The inference "config.gcc says llp64, therefore the target is LLP64" was drawn from reading
`config.gcc` in isolation; `gcc/configure.ac` and the header override order both discard it.

**Provenance**, confirmed from git history: added 2024-12-03 by Radek Bartoň in
`f7c91f8df62`; the `aarch64-w64-mingw32` target it builds on came from Zac
Walker in `13bad1ac7a6` (2024-03-01); branch HEAD is `5688a17320e`, 2025-06-23,
also by Radek Bartoň. Evgeny Karpov contributed the rebased `woarm64`
`aarch64-pe` prototype (2025-04-17). This is an active, named effort to align
with rather than duplicate. The same branch also carries `b3295b9e383`
(2025-01-28) "Change long double to 64bit", which bears directly on the data
model and on our own long-double wrapper work.

**NOW VERIFIED 2026-09-03**, closing all three caveats:

- **It builds.** binutils and GCC configured, built and installed with exit 0 at every step;
  `make -j8 all-gcc` completed in 4m04s; `-fself-test` reported 7,660,717 passes. Built in
  WSL2 Ubuntu aarch64 from `crutkas/gcc-woarm64` @ `5688a17320e775944bbe795010ebe7e89fc7a628`
  and `crutkas/binutils-woarm64` @ `44335833f8f`.
- **It works.** It emits real `pe-aarch64-little` objects with correct LP64 codegen, and
  yields a full `aarch64-pc-cygwin-{as,ld,ar,objdump,windmc,dlltool,...}` set with `aarch64pe`
  emulation.
- **Upstream does NOT carry it.** Independently verified against `gcc-mirror/gcc` master
  `gcc/config.gcc`: the complete aarch64 case list is `aarch64*-*-*` x2, `freebsd`, `netbsd`,
  `linux`, `gnu`, **`aarch64-*-mingw*`**, `wrs-vxworks` — **no cygwin arm** — and the only
  cygwin cases are `i[34567]86-*-cygwin*` and `x86_64-*-cygwin*`. Upstream **binutils**
  likewise carries only `aarch64*-*-pe*|aarch64*-*-mingw*`. `aarch64-w64-mingw32` landed in
  GCC 15; `aarch64-*-cygwin*` is **fork-only in both projects** and was never posted to
  gcc-patches.

**This target is now the reference oracle for item 2**, installed at
`\\wsl$\Ubuntu\root\xc\inst\bin\aarch64-pc-cygwin-gcc` and surviving cleanup.

**SCOPE CAVEAT — do not let this be overstated.** The build was a **stage-1 bootstrap cross**
(`--without-headers --with-newlib --disable-multilib`, C only, no threads, no shared
libraries). It conclusively **proves the target's data model and identity**, which is exactly
what was needed. It does **NOT** prove that a full Cygwin-targeting toolchain builds, nor that
it can compile the real runtime.
## 8. Intended aarch64 Cygwin data model — RESOLVED: **LP64**

**Same question as item 1. Answered 2026-09-03 by building the target and measuring it.**

The prior framing — "if LLP64 is a deliberate ecosystem choice then the 11 recorded sites are
the future ABI, not defects" — is **CLOSED**. `llp64` was a placeholder token that never
reaches the compiler, and the ecosystem's actual aarch64 Cygwin target is LP64. **Position B
was never available**: there is no LLP64 artifact anywhere to be compatible with.

Structural reason it could never have been available: newlib's `sys/_types.h` — the header
Cygwin actually uses — defines `_off_t`, `__blkcnt_t`, `__blksize_t`, `_ssize_t`, `time_t`,
`_fpos_t` and `clock_t` in terms of bare `long`, and `__ino_t`/`__mode_t` as `unsigned long`.
Under a 32-bit `long` these do not become "work items"; they become a **silent platform-wide
ABI break** — a 2 GB file-size ceiling, Y2038 in `time_t`, truncated inode numbers and block
counts, and `ssize_t` narrower than `size_t`. Nothing in winsup is conditioned to handle it.

Ecosystem corroboration: the AArch64 Cygwin port is real, live and **upstream-accepted**.
Radek Bartoň's *"Cygwin: configure: allow configuring winsup for AArch64"* (2025-06-12) drew
Corinna Vinschen's *"This and the other patches you sent today are fine, thanks."* and was
pushed 2025-06-18; upstream `winsup/configure.ac` now carries `aarch64) ;;`, exactly what the
sealed worktree already has. `Windows-on-ARM-Experiments/newlib-cygwin` CI builds and
`make check`s the real Cygwin DLL with `--target=aarch64-pc-cygwin` on `windows-11-arm`, and
its failure triage (issue #303) lists signal/cygserver/pointer-validation failures — **not one
type-size failure**, which is what a 32-bit `long` would produce everywhere.

Downstream consumer is explicitly **MSYS2 -> Git for Windows on ARM64**. MSYS2's own
`msys-w64.h` is a byte-identical analogue of `cygwin-w64.h`, so `aarch64-pc-msys` inherits the
same LP64 chain; no `aarch64-*-msys*` block exists in MSYS2-packages yet.

**Owner ratification is still outstanding.** This entry records decisive evidence; it does not
itself constitute a granted decision.
## 9. msys2-runtime — update the fork onto current upstream `newlib-cygwin` (DO THIS FIRST)

| Field | Value |
|---|---|
| Upstream | sourceware `newlib-cygwin` (mailing list; does not accept GitHub PRs) |
| Status | **NOT STARTED. Ordered BEFORE any further ARM64 porting work.** |
| Why | Our fork at `d890a845` is materially behind an active, partly-merged upstream aarch64 port |

**HEADLINE FINDING 2026-09-03: there is an ACTIVE, PARTLY-MERGED UPSTREAM aarch64 Cygwin port,
and our fork is MATERIALLY BEHIND IT.** Verified directly against sourceware `newlib-cygwin`
HEAD:

1. **`winsup/configure.ac` already accepts aarch64 upstream** — `case "$target_cpu" in
   x86_64) ;; aarch64) ;; *) AC_MSG_ERROR([Invalid target processor "$target_cpu"]) ;;`, plus
   `AM_CONDITIONAL(TARGET_AARCH64, [test $target_cpu = "aarch64"])`. Merged 2025-06-18 from
   Radek Bartoň, reviewed by Corinna Vinschen. This is **exactly** what the ABI session wrote
   independently, against a stale base.
2. **Upstream `exceptions.cc` no longer contains the `_CX_`/`_MC_` macro block or any
   `#error`.** It now includes `"register.h"` and `"gcc_seh.h"` — **files that do not exist in
   our tree at `d890a845`**.
3. **Upstream `winsup/cygwin/local_includes/register.h` carries an aarch64 block that is
   BYTE-FOR-BYTE IDENTICAL** to what the ABI session derived from the real ARM64 `CONTEXT`
   layout and AAPCS64 — including the non-obvious callee-saved `_MC_uclinkReg x19` choice.

**Interpretation, recorded deliberately in both directions.** This *validates the engineering
quality spectacularly*: a first-principles derivation matched merged upstream exactly, down to
a non-obvious register choice. It simultaneously shows the effort **partly duplicated work
that was already merged**, because it was written against a stale base.

**Consequence: the correct next action is NO LONGER "keep porting."** It is to update onto
current upstream `newlib-cygwin`, re-assess what genuinely remains, and only then resume. No
further porting should be scheduled until that update and re-assessment have happened.

**CORRECTED 2026-09-03 — the first framing of this item OVERSTATED how far ahead upstream is.**
Upstream `winsup/cygwin/aarch64/` contains **only** `cygwin.din` and `fastcwd.cc`, and upstream's
`if TARGET_AARCH64` sets `TARGET_FILES = aarch64/fastcwd.cc` **alone**. So **upstream has
SCAFFOLDING, NOT THE PORT** — it does not carry the 10 `.S` routines or most of the ARM64 work.
The three specific duplications listed above are real and still stand, but the earlier wording
*"the real gap may be far smaller than the 785-line diff suggests"* is **WITHDRAWN**. The rebase
remains correct and still comes first, because it removes genuine duplication and moves us onto a
supported base — but **it will NOT eliminate most of the work.**

### Status update — a USABLE cross now exists

A usable `aarch64-pc-cygwin` cross-toolchain now exists: one that **compiles real
Cygwin/msys2-runtime source**, not merely reports predefines.

**THE SEALED PORT AS-IS REACHES ROW 3: 254 of 310 objects, 15 errors.** Rows 4 and 5 below
depend on three **throwaway diagnostic** fixes (`fabsl.c`, `cygwin.sc.in`, `MALLOC_ALIGNMENT`)
made in a WSL scratch clone purely to prove the remaining failures were source-side rather than
toolchain. They are **not proposed patches and are committed nowhere**. So **265/310 (85%) is
"achievable once three further fixes land"**, not a current result — citing it unqualified
overstates the sealed port.

*Figure correction: an earlier relay recorded "254 objects / 8 errors". That pairing was a
**conflation** matching no single configuration. True progression, out of 310:*

| # | Configuration | objects | `error:` lines |
|---|---|---|---|
| 1 | w32api master, no fixes | 116 | 314 |
| 2 | + `_WIN64` fix | 116 | 285 |
| 3 | + released w32api **v12.0.0** | 254 | 15 |
| 4 | + 3 throwaway diagnostic fixes (NOT committed/proposed) | 261 | 8 |
| 5 | warnings non-fatal | **265** | **3** |

**Rows 4-5 are conditional, not achieved.** At row 5 the only hard error left is `fatal error: new: No such file or directory` — libstdc++
headers were never installed, i.e. **toolchain completeness, not a port gap**.

**Root cause, verified verbatim at source.** `mingw-w64-headers/crt/_cygwin.h` lines 32-34 are
`#ifdef __x86_64__` / `#define _WIN64` / `#endif`. `__x86_64__` is undefined on
`aarch64-pc-cygwin`, so `_WIN64` is never set, so `basetsd.h` silently takes its **32-bit**
branch and `UINT_PTR`/`INT_PTR`/`LONG_PTR`/`ULONG_PTR`/`SOCKET`/`DWORD_PTR` all become 32-bit —
producing a flood of pointer-truncation errors **that look exactly like ARM64 port defects and
are not**. One-line fix: `#if defined(__x86_64__) || defined(__aarch64__)`. This is an upstream
mingw-w64 defect affecting **any** non-x86_64 64-bit Cygwin target.

**DECISIVE for item 6: the 11 sites COMPILE CLEAN UNDER LP64.** Every pointer-width error
vanished the instant `_WIN64` was correct, and a direct probe compiled clean asserting
`sizeof(UINT_PTR)==8 && sizeof(void*)==8 && sizeof(long)==8` against real `<w32api/windows.h>`.
This converts "estimated remaining work: zero" from an **inference into a measured result**.

**NOT a product pass:** nothing links, no DLL exists, and no authority is created by it.

**Do NOT reinstate the `mbstate_t` shim.** It was working around a **mingw-w64 MASTER
REGRESSION** — commit `8c4baed92` (2026-08-17, in **no release tag**) — which collides with
newlib on **every** Cygwin target, including x86_64. It was never an ARM64 problem. The correct
mitigation is released **w32api v12.0.0**, not a shim. Anyone seeing `mbstate_t` breakage should
check the mingw-w64 revision in use before touching the port.

Note the contrast that keeps items 2 and 7 genuinely open: upstream **binutils and GCC still
lack `aarch64-*-cygwin*` entirely**, so those remain real outstanding debt — and they are the
**LP64** flavour.
## 10. CANDIDATE (INVESTIGATION-ONLY) — mingw-w64 headers do not normalise the ARM64 SEH tag

| Field | Value |
|---|---|
| Upstream | `mingw-w64` (mailing list) |
| Status | **HYPOTHESIS with good supporting evidence — NOT an established defect. NOT AUTHORISED to raise with anyone.** |
| Gate | Investigation first: check mingw-w64 history and any prior discussion |

**Microsoft deliberately makes the mangled name architecture-independent.** The
`push_macro`/`pop_macro` bracketing scopes the rewrite to exactly the struct definition, so the
*typedef* name stays `DISPATCHER_CONTEXT_ARM64` (SDK line 7143) while the underlying *tag*
becomes `_DISPATCHER_CONTEXT`. That is engineering effort spent for a specific outcome. The
census therefore stops being "2 versus 3" and becomes a **conformance question, with P25 as the
deviation** — the first principled reason to prefer one value over the other.

**mingw-w64 is INTERNALLY INCONSISTENT — proven from one checkout at one commit**
(`b0c3cce6a14965dbac1713e619c811a149044dcd`, 2026-08-27):

| Copy | Bytes | Normalising `#define` | Declaration | Derived result |
|---|---:|---|---|---|
| `mingw-w64-headers/include/winnt.h` | 415,567 | **none** | 2465 (genuine tag) | **P25** |
| `mingw-w64-tools/widl/include/winnt.h` | 321,232 | **2030** | 2072 (tag rewritten) | **P19** |

Same project, same commit, two copies, two treatments of the same identifier. An *external*
divergence from Microsoft could plausibly be deliberate; an **internal disagreement inside one
project is much harder to explain as a choice**, and is the strongest single argument that the
headers omission is an oversight.

**MANDATORY CAUTION:** mingw-w64 may have a reason not yet found — ARM64EC interactions, or a
deliberate choice to keep the ARM64 struct distinct for cross-arch tooling, are both plausible.
**Check history and prior discussion before claiming anything upstream. No contributor contact.**

### MEASURED BY COMPILER 2026-09-03 — Variant C settles it

Reproduced independently with **clang++ 22.1.8** (`...\aabca41f-...\toolchain-root\clangarm64\bin\clang++.exe`,
`--target=aarch64-w64-mingw32 -S`), the same compiler family that would build this runtime. Identical
function signature in all three; only the `PDISPATCHER_CONTEXT` construction differs:

| Variant | Construction | Mangled result |
|---|---|---|
| A | plain `struct _DISPATCHER_CONTEXT` (w32api v12.0.0 shape) | `...P19_DISPATCHER_CONTEXT` |
| B | genuine `_DISPATCHER_CONTEXT_ARM64` tag, aliased (CLANGARM64 / mingw-w64 master shape) | `...P25_DISPATCHER_CONTEXT_ARM64` |
| **C** | **Microsoft shape — ARM64-*named* typedef whose *tag* is normalised by `#define`** | **`...P19_DISPATCHER_CONTEXT`** |

**An ARM64-named typedef whose tag has been normalised mangles to P19** — precisely the inference
that was originally drawn backwards, now settled by measurement rather than by argument.

**Confidence labelling — THREE TIERS, not one word:** byte counts, sha256s, presence/absence of the
normalising `#define`, and all line numbers are **MEASURED** from the files. The "P19/P25"
column is now **MEASURED BY COMPILER** for all three constructions (table above), no longer merely derived from the Itanium ABI rule. **The only remaining inferential step is the COMPOSITION** — that each named header set, when actually compiled, uses the construction read from its text. `winnt.h` itself was compiled for no set.
**Only the w32api v12.0.0 row is empirically confirmed** by a real `exceptions.o`. The other
rows are sound derivations that have not been compiled — labelled as such precisely because the
*previous* derivation (from occurrence counts) inverted the answer.

**WHAT MUST NOT MOVE:** the port **still cannot hard-code either value**. It must compile
against whichever header set is present, and **two in active use produce P25**.
**Version-robustness remains mandatory.** All that changes is that the record can now explain
*why* P19 is the Microsoft-aligned answer instead of presenting the two as symmetric.
## Ordering

**ITEM 9 COMES FIRST.** Our msys2-runtime fork at `d890a845` is materially behind an active,
partly-merged upstream aarch64 Cygwin port. Update onto current upstream `newlib-cygwin` and
re-assess before scheduling any further porting work; the genuine remaining gap may be far
smaller than the 785-line diff implies.
**Items 1 and 8 are RESOLVED BY EVIDENCE: LP64**, measured 2026-09-03 by building the
`aarch64-pc-cygwin` GCC target and reading its predefines and codegen. They are **no longer a
gate**. Owner ratification remains outstanding, but no engineering path now waits on an
undecided data model.

**Item 2 (LLVM) is unconditional and unblocked**, on two independent grounds: Microsoft C++
mangling on a Cygwin target is wrong under LP64 *and* LLP64, and the data model is now
answered anyway. It is **parity work, not design**, and it is the programme's single most
upstreamable artifact. Note the drafted patch is deliberately data-model-NEUTRAL
(`__SIZEOF_LONG__` stays 4); now that LP64 is established, the correct upstream shape mirrors
`CygwinX86_64TargetInfo`'s plain-arch base — LP64, `__CYGWIN__`, `_LP64`/`__LP64__`, `__SEH__`,
16-bit `wchar_t`, `wint_t` = `unsigned int`, **and 64-bit `long double`**. The neutral draft
was correct while the question was open and is now superseded in scope.

**Item 6: the 11 recorded sites stay unpatched, PERMANENTLY.** They are the correct,
load-bearing failure signal of an unimplemented clang target, not porting work. The
prohibition on silencing them with casts remains in force permanently, not provisionally.

**Item 7 (GCC) is not a competing path.** It is the reference implementation that answered
items 1 and 8, and it is a usable oracle for item 2.

Items 2b, 3, 4 and 5 are independent of the data model and can be filed upstream at any time.

**Numbering note:** this document previously contained two sections numbered `2` (LLVM and
binutils `windmc`). "Item 2" throughout means **LLVM**; the binutils entry is now `2b`.

The real outstanding debt is **upstream submission**: `aarch64-*-cygwin*` is fork-only in
**both** GCC and binutils, and all four programme PRs remain staged in `crutkas/*` forks.

No filing, contributor contact, or further build is authorized against any of this.