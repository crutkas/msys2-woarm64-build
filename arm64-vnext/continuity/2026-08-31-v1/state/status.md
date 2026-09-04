# Git for Windows Native ARM64 vNext

Updated: `2026-09-03T07:13:00Z`

Verdict: **ENGINEERING HANDOFF COMPLETE AND VERIFIED; PROGRAMME STOOD DOWN TO MONITOR-ONLY; NO PRODUCT PASS**

**TWO SEPARATIONS THAT MUST NOT BE COLLAPSED:**

1. **THE HANDOFF IS COMPLETE; THE WORK IS NOT.** `gendef`''s 990 `cannot export` entries (980
   `_sigfe_*`), `autoload.cc`''s 192 undefined references, the 8 orphan `cygwin.din` exports and
   the version-robust SEH correction **all remain, all behind the owner''s gate**, and
   **NOTHING HAS EVER EXECUTED ON ARM64.** Nothing links, no DLL exists.
   **"Handoff complete" must never be read as "port complete."**
2. **THE RECIPE IS DURABLE; THE BINARIES ARE NOT.** Losing the WSL guest costs a **multi-hour
   rebuild, not data.** That is the correct and sufficient outcome — not a gap.

**POSTURE, effective 2026-09-03T07:08Z: STOOD DOWN.** No further validation passes, no new
work, no session creation, no consolidation, no probes. Monitoring of PRs #4/#29/#31/#10
continues. **Report only on material change** — a PR check flips, a session errors or is
archived, the WSL guest disappears, or the owner acts on a gated item. **Silence is the correct
output otherwise.**

**THE FIVE AND ONLY REPORTABLE EVENTS:** (1) a PR check **flipping**; (2) a session **erroring
or being archived**; (3) the **WSL guest disappearing**; (4) the **owner acting on a gated
item**; (5) the **heartbeat prompt changing**. Nothing else.

**Heartbeat prompt — SINGLE STANDING ACKNOWLEDGEMENT.** The conflict between its "commission
work when CPU is idle" and this posture has been surfaced once and read. **Do not re-surface it
each cycle** — identical content every 5-15 minutes is noise that buries real signals.
**Identical prompt: silence. Altered prompt: report immediately and quote what changed**, since
a change means the owner has edited it.

**Conflict resolution, in writing:** the coordinator''s instruction **supersedes** the prompt —
**not** because it is wiser, but because **the prompt cannot be updated from inside the loop it
drives.** A standing instruction that cannot observe the present must yield to one that can.
**Idle CPU is the correct output, not a problem to solve.** Manufacturing work to fill cycles is
exactly how the unannounced session and the false negative happened.

**Heartbeat accounting — both halves.** Its findings were **real and several were load-bearing**:
the toolchain-recipe gap, the false "rebuild from the evidence directory alone" claim, and the
lost input provenance would all still be undetected. **The problem was never the quality of its
work** — it was that it could act and speak from a place nobody could see, so its errors arrived
wearing someone else''s credibility.

**Baseline at stand-down** (all four OPEN/draft, 0 reviews, no auto-merge): #10 `b0d9c343`
1 SUCCESS / 1 FAILURE / 20 SKIPPED / 7 CANCELLED; #4 `942be1cd` 2/2 SUCCESS; #29 `305d14d6`
1 SUCCESS / 4 SKIPPED; #31 `d890a845` 12 SUCCESS / 6 FAILURE (the documented external drift).

Pending and active work is shown first. Completed Phase 0 evidence remains
available in `plan.md` and `inbox.md` but no longer leads the operational view.

## Current critical path

| Priority | Work | State | Next action |
|---:|---|---|---|
| 0 | Runtime ABI session-start request | Terminal `GO_RUNTIME_ABI_SESSION_START_LOCAL_BUILD_ONLY` sealed by reviewer of record `8f09cf29...` (verdict payload `cca57c2c...`, sums `51b7dd74...`, receipt `cd8452b9...`); independently reverified 31/31 sums and 13/13 seals; `verdict.json` is itself the hash-bound receipt | Authority is consumed; do not re-review, re-request, or widen scope |
| 1 | Runtime ABI product layer | Bring-up complete at the scope boundary and sealed: 29 files / 785 insertions uncommitted, hard stop held, AA64 objects 12 to 266 with zero non-AA64, errors 885 to 64, nothing links and no DLL exists; two verified backups (`47059be6...`, `ec458637...`) | **LP64 is resolved by measurement, so this no longer gates engineering.** Owner ratifies LP64 and decides commit authority; do not restart any ABI session |
| 2 | Linker/import fixtures | Terminal sealed and independently replayed artifact-only packet; 672 inventoried files, 166 bounded receipts, 40/40 deterministic core outputs; no fixture/product execution | Preserve for separately authorized ABI/linker compile loops |
| 3 | Signal/TLS/fork/exec fixtures | Terminal sealed and independently replayed artifact-only packet; 1,082 host records pass; 15 future tests and 126 assertions prepared; runtime executions correctly deferred | Preserve for separately authorized owning runtime layers after exact heads/trees and a fresh sysroot exist |
| 4 | Payload assembly | P5 external inputs 34/34 and graph 73/80 after verified Schannel successor; seven produced placeholders remain | Preserve frozen inputs and wait for seven separately owned outputs; no ZIP early |
| 1a | Preservation chain | **CLOSED AND VALIDATED — a successor can rebuild from the evidence directory alone.** The sealed patch provably applies to `d890a845`: all **43/43** pre-image blobs match, plus forward `git apply --check` on an extracted tree, reverse-apply PASS, and pure-LF confirmed two ways. **The patch REFERENCES `longdouble.c` without CREATING it** — one mention at line 187 (`Makefile.am`), **zero** `diff --git` headers — so applying it alone yields a `Makefile.am` pointing at a nonexistent file and the tree fails at LINK, far from the cause. Shape re-measured: 29 headers / 785 insertions / 51 deletions, 0 CR bytes. | **CAVEAT: applicability is NOT content correctness** — this very diff contains the known-wrong P19 token swap and two false comments, and passes every check. **For untracked files use `c63ab774` `evidence/untracked/` (byte-exact); the backup bundle is content-equivalent but CRLF-converted.** Verify against the normalised hash `aaf9785b...`, never a raw byte count |
| 1b | Data model (LP64 vs LLP64) | **RESOLVED BY EVIDENCE: LP64.** Settled by BUILDING the `aarch64-pc-cygwin` GCC target and measuring predefines and codegen: `__CYGWIN__ 1`, `__SIZEOF_LONG__ 8`, `_LP64`/`__LP64__`, 64-bit `long double`, and `madd x0,...` codegen. `llp64` is a dead token the backend rejects. Clang's `__SIZEOF_LONG__ 4` is a **clang defect**, not a rival data model. **MEASURED: the 11 LLP64-artifact sites compile clean under LP64.** | Owner ratification only; cast prohibition on the 11 sites is PERMANENT |
| 1c | Usable cross-toolchain and link attempt | **REACHED THE LINKER; NOTHING LINKS; NO DLL.** Sealed port as-is = **row 3: 254/310 objects, 15 errors**. Higher figures (261/8, 265/3, 271/1-TU) are **CONDITIONAL** on three uncommitted throwaway diagnostics. Root blocker was never the port: `_cygwin.h` gates `_WIN64` on `#ifdef __x86_64__`, narrowing every pointer type on aarch64. 676 undefined refs split into **mechanical** (missing `netapi32`/`user32` import libs) and **genuine implementation** (`exception::myfault`, ARM64 SEH personality). | Report the FULL labelled progression, never a headline number; nothing authorised to fix |
| 1d | ARM64 SEH handler name | **SEALED-PORT DEFECT.** The port hard-codes a C++ mangled name, making `.seh_handler` silently header-set-dependent with failure deferred to link time. Verified census: **P25** = CLANGARM64, mingw-w64 master (genuine tag, no normalisation); **P19** = w32api v12.0.0, Windows SDK, widl (normalising `#define` rewrites the tag). | **Must be VERSION-ROBUST — derive the name; a token swap to either spelling is still wrong.** Also delete the two false comments |
| 5 | Git Bash engineering handoff | Not built | Assemble, move-extract, replay, and attest after runtime and payload completion |

Version labels such as V4, V5, V6, and V7 refer only to evidence-packet revisions.
The operational work is the runtime ABI session-start request and implementation.

## Top-level requirements

| Requirement | Status | Current position |
|---|---|---|
| Old programme quarantined | PASS | 122 open old PRs visibly quarantined |
| Clean source boundary | PASS | 127 old PRs, 348 denied refs, 173 denied heads |
| Clean base ancestry | PASS | 173/173 explicit checks |
| External build inputs | POLICY PASS; MATERIALIZATION 34/34 | MinGit, Bash, and exact Schannel local-engineering input resolved |
| Native BusyBox tools | DRAFT PR #4 | Two successful build checks |
| Windows ARM64 build machine | PASS | MSVC/SDK capability and 18/18 native smoke commands passed |
| Native ARM64 `windmc` | LOCAL ENGINEERING PASS | Reproducible AA64 candidate `4893ee2a...`; unsigned and hash-pinned; signing deferred |
| Native MSYS2 runtime | GENERATOR DRAFT PR #31 | Generator frozen; ABI bring-up complete and sealed as evidence, not a shippable ABI; LP64 vs LLP64 TargetInfo gate pending owner decision |
| Native Bash | PENDING | Runtime MVP layer |
| Native Git and HTTPS | INPUT READY FOR LATER RUNTIME TEST | Schannel local-engineering evidence applied; no HTTPS behavior claim |
| Native SSH | INPUT READY | Windows inbox ARM64 OpenSSH by reference |
| Ownership/provenance | DRAFT PR #29 | 1 success, 4 skipped; diagnostic only |
| Native process attestor | LIMITED PASS | Direct-child/module attestation available; no full process-tree claim |
| First Git Bash ZIP | NOT BUILT | Waits for runtime top and payload layer |
| Independent artifact replay | NOT STARTED | Waits for first ZIP |
| Release admission | NOT STARTED | Post-handoff work |
| Reformat continuity | DRAFT PR #10 | Remote checkpoint is mergeable; CI has one unchanged `doc/bfd.info` Error 127 failure (ineffective in-repo `makeinfo` stub, not a missing one) and seven cancelled queued jobs |

## Current work

| Work | Branch | PR | Session | Status |
|---|---|---:|---|---|
| Runtime ABI session-start request | `crutkas-runtime-abi-request-v9` | — | Frozen V9 `16e0ae2b-076c-4c2a-83dc-4c674b4a86c`; completed review `e0624c3f-57a0-4dc2-9708-d72ae8627274`; contract matrix `8d840194-af0d-47bb-b4f4-bb5007d0a947` | Terminal NO-GO on comma-field linker forwarding; corpus pending; no authority, V10, or product mutation |
| Linker/import fixtures | `crutkas-arm64-linker-fixtures` | — | `473f3049-885c-495d-ad24-c4549786fe4b` | Terminal sealed and independently replayed artifact-only packet; no authority |
| Runtime behavior fixtures | `crutkas-arm64-runtime-fixtures` | — | `5e19eaff-8948-4f39-a0d7-daa13e4ee076` | Terminal sealed and independently replayed artifact-only packet; no runtime authority |
| Payload staging | `crutkas-arm64-payload-staging` | — | `5acb4426-d1c0-40f8-91fb-2daf0806488c` | Harness sealed; blocked on exact inputs and runtime outputs |
| Payload input materialization | `crutkas-payload-input-materialization` | — | Frozen materialization `b6d8b789-7781-42d7-8ffd-1d1e7e52624f`; review `e3ae4e76-32f6-4e38-84b6-0b0fa35e72e9`; successor `c6ce98ad-52c5-441e-886a-716db53a189a` | Complete at 34/34 and graph 73/80; seven placeholders unchanged |
| BusyBox bootstrap tools | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | #4 | `032439bc-767e-4cd9-8be1-4dcf140c9bf8` | Draft; 2 successful checks |
| Ownership/SDK and attestor | `crutkas-arm64-vnext/build-extra/ownership-sdk` | #29 | `f038cc22-e1ef-4943-afd9-6f1b0b8dcdcd` | Draft; 1 pass / 4 skipped |
| Runtime generators | `crutkas-arm64-vnext/msys2-runtime/generator` | #31 | `aabca41f-e845-47dd-97cd-bc99428bc7d4` | Draft; exact frozen head; 12 pass / 6 external failures |
| Reformat checkpoint | `crutkas-arm64-vnext/msys2-woarm64-build/reformat` | #10 | `ee27c231-950d-4128-9458-20ba8b9ce0e7` | Draft; exact head; one `doc/bfd.info` Error 127 failure from an ineffective in-repo `makeinfo` stub and seven queue-time cancellations; no source change |

Runtime-generator PR authority is consumed. PR #31 is exact, draft, and uniquely
bound. Runtime-ABI implementation authority is not yet granted. Signing is not a
local build prerequisite.

## PRs and stacks

Four vNext PRs exist: three product PRs and one continuity checkpoint. No vNext native stack exists yet.

### BusyBox leaf

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| Leaf | #4 | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | Native bootstrap shell and 31 supported applets | Clean `main` | Draft; 2 successful checks |

### MSYS2 runtime stack

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| 1 | #31 | `crutkas-arm64-vnext/msys2-runtime/generator` | Fresh native generators | BusyBox leaf | Draft; frozen; build jobs pass |
| 2 | — | `crutkas-arm64-vnext/msys2-runtime/abi` | ARM64 ABI and startup foundation | Generator | Blocked by terminal V9 NO-GO; product work not started |
| 3 | — | `crutkas-arm64-vnext/msys2-runtime/linker-import` | Linker, imports, autoload, pseudo-reloc | ABI | Blocked |
| 4 | — | `crutkas-arm64-vnext/msys2-runtime/signal-tls` | Signals, SEH, threads, TLS | Linker/import | Blocked |
| 5 | — | `crutkas-arm64-vnext/msys2-runtime/mvp` | Runtime, Bash, Git/HTTPS/SSH integration | Signal/TLS + BusyBox | Blocked |
| 6 | — | `crutkas-arm64-vnext/msys2-runtime/fork-exec` | Fork/exec correctness and final runtime rebuild | MVP | Blocked |

Planned native stack: positions 1–6, bottom-to-top. Stack number: **unassigned**.

### Build-extra stack

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| 1 | #29 | `crutkas-arm64-vnext/build-extra/ownership-sdk` | Source ownership, SDK/input provenance, attestor | Clean `main` | Draft; not stacked |
| 2 | — | `crutkas-arm64-vnext/build-extra/payload` | Assemble native Git Bash payload | Ownership/SDK + runtime top | Blocked |
| 3 | — | TBD | Fixed aggregate checks | First handoff | Post-handoff |
| 4 | — | TBD | Protected admission and governance | Aggregate checks | Post-handoff |

Pre-artifact native stack: positions 1–2. Stack number: **unassigned**.

### Reformat continuity

| PR | Repository | Head | Purpose | Status |
|---:|---|---|---|---|
| #10 | `crutkas/msys2-woarm64-build` | `b0d9c34` / tree `57e31d7` | Exact authorities, runtime patch, sealed state, CI triage, and restart procedure | Draft; mergeable; one unchanged `doc/bfd.info` Error 127 failure (ineffective in-repo `makeinfo` stub) and seven queue-time cancellations |

## Work pending

| Priority | Work | Unblocked by |
|---:|---|---|
| 0 | Complete comprehensive argument contract matrix | Terminal sealed corpus from artifact-only session `8d840194...` |
| 1 | Decide whether to commission a comprehensive successor request | Sealed corpus plus explicit user direction; no V10 currently exists |
| 2 | Create the ABI product session and begin compile/test | Future exact hash-bound independent session-start GO and authorization receipt |
| 3 | Consume frozen linker/import fixture harness | Exact authorized ABI parent and future runtime output prefix |
| 4 | Consume frozen signal/TLS/fork fixture harness | Exact authorized later-node heads/trees and fresh ARM64 runtime sysroot |
| 5 | Wait for seven node-produced payload/runtime outputs | Exact runtime top and separately owned payload outputs |
| 6 | Build runtime stack positions 2–6 | Each lower layer frozen |
| 7 | Complete payload layer and Git Bash MVP ZIP | Runtime top + ownership layer + exact inputs |
| 8 | Independently replay moved extraction and publish handoff | MVP ZIP |
| 9 | Add aggregate checks, release signing, and protected governance | First engineering handoff |

## Conditional and deferred work

| Repository/work | Decision |
|---|---|
| Binutils source stack | HOLD unless LLVM/LLD fails required GNU/BFD behavior |
| GCC source stack | HOLD unless LLVM/LLD fails ABI, unwind, linking, or execution |
| mingw-w64 source | HOLD unless integration finds a concrete upstream gap |
| MSYS2-packages | Deferred to package-native/self-hosting/RTM |
| Bootstrap/Gettext | Deferred to self-hosting, NLS, or RTM |
| Broad runtime utilities | Deferred after first handoff |
| Remove BusyBox dependency | Deferred until native package replacements exist |

## Current decisions

| Area | Decision |
|---|---|
| Compiler/linker | LLVM/LLD first; GCC/Binutils are fallbacks |
| BusyBox | Required now for bootstrap and supported tools |
| Git input | Use only 15 ARM64 PE files and 16 template files from MinGit |
| HTTPS | Schannel; GCM disabled for MVP tests |
| SSH | Windows inbox ARM64 OpenSSH by reference |
| Trust | Selected Windows certificate store |
| Branch prefix | Physical `crutkas-arm64-vnext/`; logical `arm64-vnext/` |
| First artifact | Non-admitted engineering handoff |
| Parallel builds | Keep ready critical work active; divide 20 logical CPUs across independent workloads and retain memory/process guards |
| Signing | Git for Windows release-pipeline responsibility; never blocks local engineering builds |

## Live execution state

| Item | Current value |
|---|---:|
| Active critical-path independent reviewers | 0 |
| Reserved idle independent reviewers | 0 |
| Active artifact-only driver contract matrices | 1 |
| Active artifact-only fixture owners | 0 |
| Terminal artifact-only fixture packets | 2 |
| Active Schannel request-only reviewers | 0 |
| Active Schannel re-admission executors | 0 |
| Resolved P5 external inputs | 34/34 |
| Frozen payload harnesses waiting on produced inputs | 1 |
| Runtime layers implemented after generator | 0/5 |
| Open vNext PRs | 4 |
| Created vNext stacks | 0 |
| Fresh Git Bash artifacts | 0 |

Historical Phase 0 task totals are retained in `plan.md`; they are not the live
execution count.

## Current authority

| Authority | SHA-256 |
|---|---|
| Boundary | `97ce5396ff9f581c02f7207413d9803dbd219f6fa1764c87e73f2b1c4ed7b68d` |
| Release graph | canonical revision 12 `8ac61bcb3aa71ac15065e5bb5b72ece8269c2a24399942efee6a39e6b3ea2605` |
| Input provenance | `9f4ed99e12d67ef026eb7fb85c783edc9d8211a1ea80f5447e3a7dd3e1a00999` |
| Branch amendment | `e477de0e24d84c40843a887a0b5b2268257e6373faa1c22ea6490227fdc93a8c` |
| Amendment review | `61ef7605fa913895566c9cd60cf702148dcd4128340e5e1a7f495c46a91c3848` |
| Staged verdict | None active; runtime PR authority consumed |
| Runtime ABI session start | None; V9 verdict `bcdd8d3f...` is terminal NO-GO with no authorization receipt |

Machine truth: `arm64-vnext-release-graph.json`, `arm64-vnext-boundary.json`, task database, evidence registry, and live API readback.


## clangarm64 native userland — availability (MEASURED, this verifier thread)

| Claim | Verdict |
|---|---|
| `awk` `m4` `bison` `automake` `autoconf` absent | **CONFIRMED** on 4 axes with sensitivity+specificity controls |
| `sh` absent | **FALSE AS STATED** — `brush` 0.4.0-2 is a native ARM64 shell (COFF `0xaa64`, runs, 24/25 POSIX constructs) |
| `sh` gate still real | **YES** — autoconf 2.71 rejects brush; missing builtin `exec` (1 of 13) |
| `make` present | **YES but ships as `mingw32-make.exe`; `make.exe` does not exist** |
| `libtool` present | misleading — ships **zero** executables, shell scripts only |
| Perl `Locale::Maketext::Simple` / `Params::Check` | **BOTH PRESENT** in core_perl 5.44.0-3 |

Corpus: `clangarm64.db` `30ae0994...`, `clangarm64.files` `7734e9f7...`, 3,806 packages, 1,435,885 file entries, 5,051 distinct `bin/*.exe`.
Detail: `state/clangarm64-native-userland-availability.md`.


## Seal completeness (MEASURED, this verifier thread)

**The sealed port was never link-capable for aarch64.** `cygwin.sc.in` lines 1-10 end in `#else / #error unimplemented for this target / #endif`, so any non-`__x86_64__` target fails at preprocessing. Every ARM64 link necessarily used a modified copy, and no such copy exists in any reachable archive (`__aarch64__` in **0 of 60** `cygwin.sc*`). The seal is an x86_64 tree with ARM64 work alongside it, not a link-capable ARM64 port.

All four x86-gated conditionals (`cygwin.sc.in` ctor lists / `OUTPUT_FORMAT` / `.xdata` / `mkimport`) are **original defects present in the seal**, not regressions introduced later.

`.xdata` resolution: measured on four shipped ARM64 images - `.xdata` VMA `0x180315000` immediately before `.pdata` `0x180329000`, exception directory points at `.pdata`. Unwind works **by orphan-section placement, not by rule**. `.pdata` size `0xbab8` = 47,800 / 8 = **5,975 exact**. `ImageBase` is `0x180040000`.

Detail: `state/sealed-port-arch-conditionals.md`.


## ASLR is a Windows-on-ARM platform rule (MEASURED, this verifier thread)

`--disable-dynamicbase` is a NON-FIX and was retracted. Independently reproduced here on 6 stock ARM64 system DLLs with full controls:

| Variant | Result |
|---|---|
| A pristine copy | LOADED (6/6) - harness positive control |
| B byte-identical rewrite | LOADED (6/6) - rewrite pipeline is not the variable |
| C `DYNAMIC_BASE` cleared | **FAILED err=193 ERROR_BAD_EXE_FORMAT (6/6)** |
| D C + checksum zeroed | FAILED err=193 (6/6) - not a checksum artefact |
| E `HIGH_ENTROPY_VA` cleared only | **LOADED (5/6)** |

**Refinement beyond the original claim: only `DYNAMIC_BASE` is mandated. `HIGH_ENTROPY_VA` is NOT** - clearing it alone still loads. (`bcrypt.dll` E returns 577 `ERROR_INVALID_IMAGE_HASH` - signature enforcement, not an ASLR counterexample.) So `DllCharacteristics 0x0160` on the runtime is CORRECT and REQUIRED, and `msys-2.0-fixedbase.dll` at `0x0100` is unloadable by construction. My earlier ASLR-regression flag is CLOSED: no regression exists.

## Fifth pattern class: x86 assumptions encoded as data

`import_address()` matching `0x25ff` has no `#ifdef`, no `x86` token - **ungreppable by every method used for instances 1-4**. Sweep of 938 sealed sources found the defect plus one benign hit. `path.cc` `find_fast_cwd_pointer()` carries NINE x86-64 byte patterns but its caller IS ARM64-guarded at runtime - a true negative. **The codebase guarded one machine-code scanner and missed the other; the correct idiom already exists in the same tree.** Detail: `state/x86-assumptions-as-data-audit.md`.


## Native ARM64 git.exe VERIFIED (MEASURED, this verifier thread)

Artefact `gcc-native/git-2.47.1/git.exe` sha256 `1ec7f3b2782619bd46883113e29c2c0d9229156400170334427fecfbda7a6397`, 4,723,261 B.

| Point | Result |
|---|---|
| Raw COFF | `Machine=0xaa64`, PE32+, console |
| Live `IsWow64Process2` | `ProcessMachine=0x0000` -> **native** |
| Bound modules | 36 across `git` + `git-remote-https`; **no schannel, no ncrypt** |
| Controlled PATH | `sh.exe` ABSENT - control valid |
| Negative control | `git submodule status` -> exit 128 |
| Toolchain | **LinkerVersion 2.44**, no `.buildid`, **0 clang strings** (retired clang build: 14.0 + `.buildid` + 42 clang strings) |
| Known-SHA clone | `rev-parse HEAD` = `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d` **exact**; `fsck` exit 0 |

**TLS positive control**: Windows `curl.exe` on the same URL loads `schannel.DLL`, `ncrypt.dll`, `ncryptsslp.dll` - the detector demonstrably fires, so the absent result for git is a NEGATIVE, not an absence.

**Caveat, precisely stated**: `driver-bin/mingw32-make.exe` is **LinkerVersion 14.0 with .buildid** = the clangarm64 package make, NOT from the WoA GCC chain. Everything the build PRODUCES is single-toolchain GNU; the build DRIVER is not.

**A strings audit would have been wrong**: `git-remote-http.exe` contains 351 `ncrypt` and 5 `schannel` strings, yet neither DLL ever loads.

Detail: `state/native-arm64-git-verification.md`.


## cygheap x86_64 differential (MEASURED, this verifier thread)

Instrument: Git for Windows `msys-2.0.dll` 3.6.9, sha256 `2ea49553e4c03055dcf1c4a2bef54668081a07663fba283f4b34cf70f2157191`, Machine `0x8664`, **DllCharacteristics `0x0000`** (upstream ships NO ASLR - independent corroboration of the inherited-ASLR finding).

Walked externally with `ReadProcessMemory`; chain-head offset DERIVED not assumed, by testing every 8-byte slot in the first `0x40` bytes.

| Measurement | x86_64 (fork works) |
|---|---|
| `offsetof(chain)` | **+0x08** confirmed empirically |
| chain entries | **33**, deterministic over 2 processes |
| terminates at NULL | **yes** |
| all entries in heap | **yes** |
| **lowest entry** | **cygheap + `0x48A0`** = exactly `sizeof(init_cygheap)` |
| username allocation | **IS on the chain** (entry `0x8000050b0`, `b=15`, 32,768 B, at data+0x1820) |

**`sizeof(init_cygheap) = 0x48A0` is now independently confirmed** on a different architecture, version and build - it is a property of the structure, not of one build. The ARM64 chain reportedly starts `0x2050` higher, so that gap corresponds to ~8 KB of orphaned early allocations; **the measured healthy baseline is what makes that number mean anything.**

**Verdict: the corruption is NOT an upstream defect** - x86_64 terminates cleanly. ARM64 attribution is **supported by differential**.

**Limitation**: this is upstream 3.6.9, which we did not build. Establishes upstream-x86_64-healthy, not our-sources-healthy. Attribution is **strong, not definitive** until our own tree is built for x86_64 and re-walked.

Detail: `state/cygheap-x86_64-differential.md`.


## INSTALLED TREE VERIFIED (MEASURED, this verifier thread) - the tree that becomes the package

**`bin/git.exe` sha256 = `69b1e704729cf69f0a0c029aa189eb9d38f74fc16ef37823048cb6a98b1523d1`** (4,723,261 B). Re-read at report time 10:13:13 - **unchanged**. THIS IS THE HASH THE VERIFICATION COVERS.

| Check | Result |
|---|---|
| `.exe` audited | **158** (6 in `bin`, 152 in `libexec/git-core`) |
| symlinks / hardlinks | **0 / 0** - `NumberOfLinks` histogram `1->158`, 158 distinct NTFS indexes, on-disk = full logical sum |
| PE machine | **`0xaa64` x 158**, zero exceptions |
| COFF | PE32+, Subsystem 3, `ImageBase=0x140000000` |
| Toolchain | **LinkerVersion 2.44**, 0 clang strings, no `.buildid` |
| Live `IsWow64Process2` | `git` and `git-remote-https` both **native** |
| Bound modules | 36; **schannel absent, ncrypt absent** (Windows `curl.exe` positive control FIRES) |
| Negative control | `git-submodule` present, no `sh` -> **exit 128** |
| SHA-1 known-answer | **3/3 match** |
| Known-SHA clone | `rev-parse HEAD` = `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`; `fsck` exit 0 |

**THE TREE IS NOT FROZEN**: 0 read-only, 220 writable, no `SHA256SUMS` manifest inside. I anchored to my own snapshot: 158 files, 158 unchanged, 0 changed across the verification window. Any consumer must pin `69b1e704...` and self-refuse if it moves.

**`NO_INSTALL_HARDLINKS=1` confirmed working** - 11 distinct contents across 158 real files, so `pacman -Ql` will enumerate all of them.

Detail: `state/git-install-tree-verification.md`.


## cygheap wild value - layout check REDIRECTS the hunt (MEASURED, this verifier thread)

Source citation confirmed exact: `mm/malloc.cc:1670` `win32mmap` and `:1676` `win32direct_mmap`, located by content then cross-checked to the quoted lines.

**But the reported 512-887 GiB range is not producible and is not in the layout.**

| Probe | Measured on this host |
|---|---|
| `MEM_RESERVE\|MEM_COMMIT` (as :1670) | **0.70 - 1.45 GiB** |
| `+ MEM_TOP_DOWN` (as :1676) | **~131,019 GiB** |

Sealed `memory_layout.h` (sha `5d5fef7229a7c038`): `CYGHEAP_STORAGE_LOW` 32 GiB, **`CYGHEAP_STORAGE_INITIAL` `0x800300000` = 32.003 GiB**, `CYGHEAP_STORAGE_HIGH` 40 GiB, `USERHEAP_START` 40 GiB, `MMAP_STORAGE_LOW` 64 GiB. **Nothing at 512 GiB.**

**The `.003` occurs exactly ONCE in the whole layout - at the cygheap initial commit limit, at 32.003 GiB, which is 512.003/16.** Corroborated by my own live measurement: the x86_64 cygheap commits `0x800000000..0x800300000`, upper bound exactly `CYGHEAP_STORAGE_INITIAL`.

**If the captured figures are one hex digit wide, the wild value is the cygheap COMMIT LIMIT, not a ptmalloc segment base** - which changes the hunt from 'who stored a malloc pointer' to 'who stored a named constant', a much smaller candidate set. NOT asserted: I did not see the raw capture. The capture owner should confirm the value width.

Detail: `state/cygheap-wild-value-layout-check.md`.


## RETRACTION - the cygheap 'wild value' redirect was WRONG (this verifier thread)

Raw bytes measured `00 A0 2C 00 80 00 00 00` = **`0x80002CA000` = 512.0027 GiB at full width**. My one-hex-digit hypothesis is FALSIFIED.

Three errors, all mine:
1. **`MMAP_STORAGE` spans 64 GiB .. 114,688 GiB and CONTAINS 512 GiB.** I read the layout as point values when it is a list of RANGES. My claim 'nothing in the layout is at 512 GiB' was false.
2. **The `.003` was never a fingerprint** - `0x300000` = 0.00293 GiB and `0x2CA000` = 0.00272 GiB BOTH display as `.003`. I derived an identifier from a ROUNDED RENDERING instead of raw bytes.
3. **My `VirtualAlloc` probe refuted nothing** - it measured raw `VirtualAlloc` in a plain Win32 process, while Cygwin's `mmap` layer places allocations into `MMAP_STORAGE` by its own base selection. Wrong mechanism.

**The original ptmalloc/mmap-segment attribution is consistent with the layout. My redirect was wrong and went to two sessions; both corrected.**

**This breaks the pattern I had asserted about myself.** The four earlier self-catches were INSTRUMENT bugs; this was a REASONING error, and no harness precondition would have caught it. 'My errors are in the instrument, not the reading' was an over-generalisation from four points and is withdrawn.


## GOVERNANCE: the ARM64 port source exists in no reachable archive (MEASURED)

Widest sweep across both reachable roots, all `.h/.cc/.c/.S` under 400 KB, for any file containing `__getreent` together with `__aarch64__`, `x18` or `tpidr`: **zero hits**. All **63** reachable copies of `cygwin/include/cygwin/config.h` resolve to ONE version (sealed `0a664264d08b`, 2,576 B LF, plus a 2,662 B CRLF twin with **zero content differences**), carrying only `#error unimplemented for this target`.

| ARM64-specific source | copies in any reachable archive |
|---|---|
| modified `cygwin.sc.in` (with `__aarch64__`) | **0 of 60** |
| ARM64 `__getreent` | **0** |

**The ARM64 port's actual source lives only on `/root/xc/runtime` - unarchived, on a host no Windows-side session can reach, nothing committed.** Beside the `--disable-dynamicbase` retraction note being uncommitted in a single worktree, the pattern is consistent rather than incidental: **the programme's ARM64-specific work product is single-copy and unarchived.**

Every artefact verified today - sealed port, rehearsal trees, installed git tree - is a build INPUT or a build OUTPUT. **The ARM64 port changes are neither, and exist nowhere else.** Losing that host loses the port; losing the worktree loses the retraction that prevents an unloadable image being rebuilt.

**Related outcome**: the one-read `__getreent` discriminator returned a NEGATIVE - `__getreent` and the signal trampolines are now eliminated by measurement, the `tpidr_el0` contradiction dissolved, and the OS loader during lazy DLL load is the sole surviving candidate. A discriminating test that eliminates is doing its job; 
"
measured and eliminated
"
 is a stronger state than 
"
never tested
"
.


## RESOLVED: fork and command-line corruption both root-caused, fixes validated, P3 now 7/7 (supervisor 290c9aaf, 2026-09-03)

Two independent defects, both caught on hardware, both with validated corrections. **This supersedes the prior conclusion that "the OS loader during lazy DLL load is the sole surviving candidate" and closes the `sizeof(_cygtls) > __CYGTLS_PADSIZE__` line - neither was the cause.**

### 1. fork() - insufficient stack headroom at the ARM64 main-thread stack switch

`create_new_main_thread_stack` (`create_posix_thread.cc:276`) returns `StackBase - 16`. The x86_64 arm of `dcrt0.cc:1046-1052` then subtracts a further 32 bytes; **the ARM64 arm at `dcrt0.cc:1054-1060` subtracts nothing**, justified by a comment stating that Windows ARM64 has no shadow space so nothing need be subtracted.

That reasoning is wrong for an architectural reason: **x86_64 addresses locals at negative offsets from `rbp` (below `StackBase`), while AArch64 addresses them at positive offsets from `sp`.** With only 16 bytes of headroom the compiler's ordinary spill `str x4,[sp,#24]` at `0x180046cd8` writes to `StackBase + 8` - which **is** `cygheap->chain`, because `THREAD_STORAGE_HIGH == CYGHEAP_STORAGE_LOW == 0x800000000` with no guard region.

It is not a stray store. It is a correct compiler-generated spill into a frame that has nowhere to live.

| evidence | result |
|---|---|
| faulting `Pc` captured by page-protection debugger | `0x180046cd8`, identical 3/3 runs |
| chain walk | WILD at depth 39, victim entry `0x8000068f0` - matches the previously recorded `0x8000068F8` |
| wild value identity | `== TEB` exactly, 3/3, tracking ASLR |
| frame requirement (measured) | max reach above `sp` = **32 bytes**; available = **16**; shortfall = **16** |
| `sub sp,x0,#16` | fork **PASS 3/3** |
| `sub sp,x0,#256` | fork **PASS 3/3** |

**Recommended fix:** subtract **32** to match the x86_64 arm - the measured 16 is exact-fit with zero margin, and frame size is compiler-determined, so it can grow silently and reintroduce this in a form invisible until `fork()` fails. **Additionally add a guard page** between `THREAD_STORAGE_HIGH` and `CYGHEAP_STORAGE_LOW`, which converts any future overrun from silent heap-chain corruption into an immediate fault.

### 2. Command-line argument corruption - overlapping `strcpy` (previously unknown)

`quoted()` strips quotes in place via `strcpy (cmd, cmd + 1)` (`dcrt0.cc:165`) and `strcpy (p, p + 1)` (`:167`). **Source and destination overlap, which is undefined behaviour** - `memmove` is the defined call.

This is an **upstream Cygwin latent bug that ARM64 merely exposed**: x86_64's byte-forward `strcpy` happens to produce the intended left-shift, while ARM64's implementation aligns the source down to a 16-byte boundary and loads NEON blocks (`and x2,x1,#0xff..f0` / `ld1 {v0.16b},[x2]` at `0x1801ec4c4`), re-reading bytes its own stores already overwrote.

Reproduced byte-for-byte outside the runtime: input `"...cmdprobe.exe" abcdefghijklmnop` gives `strcpy` -> `acdeefghijklmnop` versus `memmove` -> `abcdefghijklmnop`, identical to the corrupted `argv[1]` measured live. Confirmed by A/B with return to baseline (corrupt / clean / corrupt, same directory, only the DLL swapped). A tree-wide sweep finds **exactly these two sites**.

**Fix:** `memmove (dst, src, strlen (src) + 1)` at both call sites. The fix belongs at the callers - `strcpy` is behaving correctly.

**Impact:** this corrupts essentially every quoted invocation, and is very likely why higher-level testing had not been achievable.

### Combined result

**P3 is 7/7 PASS with both fixes applied** (`malloc file setjmp sigsetjmp tls signal fork`), against a **5/7** baseline. `sigsetjmp` had appeared to fail only because the argv defect corrupted the test name to `sigsetjmpp` -> "unknown test"; with argv fixed it runs and passes, which independently confirms the argv diagnosis.

**Status of the corrections themselves:** both were validated as guarded binary patches, which are hypothesis tests and **not** deliverables. Landing the two source changes and re-verifying against a properly built DLL remains open and belongs to the runtime owner.

### Instrument findings worth preserving

**Hardware watchpoints do not work on Windows-on-ARM64.** `Wvr`/`Wcr` are accepted and retained across every debug event, on multiple addresses and all threads - and never fire. **Page protection (`PAGE_READONLY` + `EXCEPTION_ACCESS_VIOLATION`, filtering on `ExceptionInformation[1]`) is the working substitute** and is what caught this bug. Three further traps cost real time and are recorded so they need not be rediscovered: the `DEBUG_EVENT` union sits at offset **16**, not 12, on 64-bit; Windows ARM64 requires `brk #0xF000` (`brk #0` is delivered as `ILLEGAL_INSTRUCTION`) and reports `Pc` **past** the breakpoint; and PowerShell parses `0x80000003` as a **negative Int32**, silently failing every exception-code comparison until written in decimal.

### Sibling sweep - clean

No second overlapping `str*`/`mem*` exists in the tree. `slashify`/`backslashify` are called with the same buffer twice but are byte-lockstep loops and therefore safe. `mount.cc:889,910` copy between distinct buffers (every caller checked). `math/pow.def.h`'s x87 asm is properly guarded with an `#else` fallback. All 18 sampled long-double symbols are exported and `math/aarch64/longdouble.o` exists - **present and linking, though numerical correctness on ARM64 remains untested** and would make a reasonable P4 fixture.

## BUILD REPRODUCIBILITY: the ARM64 runtime cannot currently be rebuilt (supervisor 290c9aaf, 2026-09-03)

Attempting to validate the fork/argv fixes in a real build surfaced that **the ARM64 `msys-2.0.dll` cannot be rebuilt from its own build tree**. Five defects are confirmed by execution, in a `cp -a` copy; the link session's tree was never modified and was verified byte-identical throughout.

| # | defect | status |
|---|---|---|
| 1 | `Makefile.am` `TARGET_AARCH64` lists **11 `aarch64/*.S` files that do not exist** (x86_64: 11/11 present) | workaround verified |
| 2 | `gentls_offsets` greps `\.long` (lines 65, 88); **ARM64 GCC emits `.word`** -> `tlsoffsets` regenerates as 56 bytes of zeros vs 1,822 B | **live hazard: `make` silently destroys a working `tlsoffsets`** |
| 3 | `windres` invocation lacks include paths -> `cygwin/version.h` not found | fixed with `-I` |
| 4 | link rule (`Makefile:3247`) uses `$(CXX) $(CXXFLAGS)`, **never `$(LDFLAGS)`**; required `-L` paths exist nowhere in the build system | injectable via `CXXFLAGS` |
| 5 | **`__MSYS__` undefined by the documented build** -> `dcrt0.cc:1102` compiles `cygwin_dll_init` where the DLL exports `msys_dll_init`. Clean compile, no warning, **wrong exported symbol** | **most serious; silent ABI change** |

A sixth item - "`fenv_aarch64.o` has no source" - **was escalated and is RETRACTED**: the source exists at `math/aarch64/fenv_extern_aarch64.c`, named by the object's own DWARF. The error was checking the parent directory and generalising to "anywhere on the host" before searching exhaustively.

### The fixes themselves are not implicated

A DLL built from the fixed source links but crashes `0xC0000005`. **A control experiment - same tree, same workarounds, original `dcrt0.o` - crashes identically**, so the crash comes from a build workaround, not from the fork/argv changes.

Every measurable link input was then compared against the working 12:24 build: `cygwin.sc`, `version.o`, `uname_version.o` and `tlsoffsets` **identical**; `libdll.a` 250 members each differing only in the fenv object's filename; `sigfe.o` and `winver.o` each **tested and eliminated**; `CXXFLAGS` identical; entry point in both resolves to `dll_entry` with a byte-identical prologue; section tables equivalent.

**Every measurable input matches and the output still crashes.** The only remaining variable is the link command used at 12:24, which exists nowhere in the tree, the logs, or any script. The inability to rebuild while matching every measurable input is itself the demonstration of the reproducibility problem.

### Consequence

The two source fixes are ready to land, but **cannot be validated in a real build until the runtime can be rebuilt at all**. Build reproducibility should be sequenced ahead of them. Defect 5 warrants attention independently: any rebuild following the recorded command silently produces a runtime missing `msys_dll_init`.

## exec() IS BROKEN ON ARM64 - isolated to a wrong handle value in child_info (supervisor 290c9aaf, 2026-09-03)

Fixing `fork` moved the failure to `exec`, which is what a real fix does: on the unfixed runtime `exec` was never reachable, so this defect had never been observed. P3 also had **no exec coverage at all** - the fixture tested `malloc file setjmp sigsetjmp tls signal fork` and nothing else. `p4exec.c` now closes that gap, and the result is that `exec` **fails**.

### Symptom

```
child_copy: cygheap read copy failed, 0x800000000..0x800025A60, done 0, Win32 error 6
fatal error - couldn't create signal pipe, Win32 error 5
child exit code 0 (expected 42)
```
Deterministic, 6/6. The signal-pipe error is a downstream consequence of `child_copy`'s failure path calling `TerminateProcess`, not an independent fault.

### The isolation

`child_copy` (`fork.cc:731`) performs `ReadProcessMemory (hp, here, here, todo, &done)` where `hp` is `child_info.parent`. Breakpointing that call to capture `x0`, and then enumerating the process's real handle space from the debugger, gives an unambiguous differential:

| run | path | `child_info.parent` | nearby VALID handle (identity NOT established — see retraction below) | recorded value usable? |
|---|---|---|---|---|
| A | fork | `0x204` | `0x204` -> parent | **yes** |
| A | exec | `0x1a8` (invalid, DuplicateHandle err 6) | `0x200` valid — object NOT identified | **no** |
| B | fork | `0x20c` | `0x20c` -> parent | **yes** |
| B | exec | `0x1a0` (invalid, DuplicateHandle err 6) | `0x208` valid — object NOT identified | **no** |
| C | fork | `0x19c` | `0x19c` -> parent | **yes** |
| C | exec | `0x1a4` (invalid, DuplicateHandle err 6) | `0x198` valid — object NOT identified | **no** |

**WHAT STANDS.** On the **fork** path the recorded value is demonstrably the parent: `ReadProcessMemory` through it **succeeds**, which is a functional identity test, not a validity test. On the **exec** path the recorded value is genuinely **invalid** — tested positively by attempting `DuplicateHandle` on it and getting err 6. Those two halves are solid.

**RETRACTED 2026-09-03 23:15 (supervisor `290c9aaf`, refuted by `state/handle-identity-vs-validity.md`).** The further claim that *"a valid parent handle **is** present in the exec'd child at `0x200`/`0x208`/`0x198`, so `child_info` simply names a different one"* **DOES NOT STAND.** It inferred **identity** from **validity** with no negative control — the same error pattern recorded elsewhere in this file. The controlled instrument measures the coincidence rate directly: at ±4/8/12 from a true inherited handle a probe reads **VALID in nearly every arm and SIGNALLED in 5 of 6**, while being a **different kernel object**, because handle values are allocated densely at 4-byte granularity and the child's **own** table populates the same range. The "nearby VALID handle" column above may therefore be measuring **nothing**, and the "57 valid vs 59" population count carries no identity weight either.

**THIS CHANGES THE NEXT ACTION, which is why it is not merely a filing correction.** If the child really does hold the inherited handle elsewhere, the defect is *"the recorded value is wrong"* and the `_CH_EXEC` population path is the right target. If it does not, the defect is *"the handle was never inherited"* — different code, different fix, and the hunt below would be aimed at the wrong place. **Settle it with the identity discriminator, not another validity test:** the parent signals exactly one of several inheritable objects and the child must report **that** slot signalled, across at least two different choices (arms A and B of the controlled instrument do exactly this and the answer moves with the parent's choice).

### Eliminated by measurement, not argument

Handle inheritance as a mechanism on Windows-on-ARM64 (reproduced in pure Win32 with the exact exec permission set `0x101018`, deliberately without the fork-only `PROCESS_DUP_HANDLE`); the permission set itself; `bInheritHandles` at process creation; `child_info` structural integrity (`intro`, `magic`, `cb`, `fhandler_union_cb` all validate, so none of the `multiple_cygwin_problem` diagnostics fire); the source region, measured `COMMIT`/`PAGE_READWRITE` in the parent at the moment of the copy; the destination region, proven committed by the runtime's own printed argument; and a timing race, refuted by determinism.

**FALSIFIED 2026-09-03 23:47 — THE FIRST ITEM IN THE LIST ABOVE IS WRONG, AND IT WAS THE ROOT CAUSE.** `exec` is now root-caused to exactly the mechanism this paragraph eliminated: **handle inheritance**. `hookapi.cc:43-51` `PEHeaderFromHModule` switches on `pNTHeader->FileHeader.Machine` with an allowlist containing **only `IMAGE_FILE_MACHINE_AMD64`**; an `0xAA64` PE falls to `default: return NULL`, so `hook_or_detect_cygwin` returns NULL, `set_cygexec(NULL)` runs, **`iscygwin()` evaluates false for our own ARM64 binary**, and `spawn.cc:597` therefore **strips `HANDLE_FLAG_INHERIT`** from the parent handle. Live measurement at the `CreateProcessW` instant: **`flags=0x0`**; instrumenting the clear site gave `before-clear flags=0x1, iscygwin=0, will_clear=1` -> `after-clear flags=0x0`.

**WHY MY ELIMINATION FAILED, PRECISELY — it is the same axis error twice over.** I reproduced in pure Win32 that inheritance **can** work with the exact exec permission set `0x101018`, and concluded inheritance was not the mechanism. **That measured the API shape's CAPABILITY, not the live path's BEHAVIOUR.** The replica was right and irrelevant to the question: the shape works, and the runtime then threw the bit away. **A general capability test cannot eliminate a specific instance.** Separately I dismissed `spawn.cc:597` by reading control flow — `SetHandleInformation` sits inside `if (!iscygwin ())`, "not taken when exec'ing a Cygwin program, which is this case" — which reasoned about **what `iscygwin()` SHOULD mean rather than what it EVALUATES TO**. It is an accurately-named predicate returning a wrong value, which is more dangerous than a misleading name because nothing about it looks suspicious.

**Both halves of the localisation were needed.** The pure-Win32 replica returning `flags=0x1` excluded "Windows anomaly at this API shape"; the live path returning `flags=0x0` located the loss inside the runtime. **A replica that reproduces a failure names a mechanism; a replica that does not reproduce it excludes one** — and neither measurement alone reaches `spawn.cc:597`.

**FIXED AT SOURCE, NO WORKAROUND.** `c63ab774` added the single `IMAGE_FILE_MACHINE_ARM64` case label **and reverted its `get_parent_handle()` workaround**, restoring the upstream guard verbatim: `rung14` exec works, `rung15` execv and execl both 77, `rung19` direct 77, `rung18` non-Cygwin 66, full regression clean. **The real fix alone is sufficient.** This is the third root-cause fix with no workarounds (fork stack headroom, argv `memmove`, hookapi ARM64 classification) and a sixth class of x86 assumption: **an explicit machine allowlist that fails silently by returning NULL.**

The reported `ERROR_INVALID_HANDLE` is **genuine**: `res == FALSE` was captured at the call's return, so `__seterrno()` did run and `%E` reports the true error.

### Two latent defects found alongside, worth fixing independently

**`child_copy` prints a stale Win32 error on the short-count path** (`fork.cc:753-767`): `__seterrno()` is called only when `res` is false, so a successful-but-short read reports an unrelated earlier error. It did not fire in this failure, but it misdirected the investigation for two cycles and will misreport any short-count failure in both `fork` and `exec`.

**Both `VirtualAlloc` returns are unchecked** (`cygheap.cc:92-100`): neither the `MEM_RESERVE`/`PAGE_NOACCESS` nor the `MEM_COMMIT`/`PAGE_READWRITE` result is tested before `child_copy` consumes `cygheap`. A failed reservation would produce a copy into a null range rather than a diagnosable error.

### Next executable action

**SETTLED 2026-09-03 23:25 — identity resolved, and the answer removes the target this section proposed.** `c63ab774` instrumented the mint site and the child's read rather than probing validity: `CTOR: type=1 parent=0x190 minted_in_pid=14816` / `CHILD: got parent=0x190 usable=0 err=6 parent_winpid=14816`. **The child receives exactly the value minted, minted in the very process that calls `CreateProcessW`, for this spawn.** So `child_info.parent` is populated **correctly** — chasing what populates it for `_CH_EXEC` was the **wrong target**, and that was the supervisor's proposal. The defect is that a handle for which `bInheritHandle=TRUE` was **requested** at `DuplicateHandle`, passed with `bInheritHandles=TRUE`, **arrives with the correct numeric value and is absent from the child's handle table.** **PRECISION CORRECTION 2026-09-03 23:36 — the earlier phrasing "a handle DUPLICATED bInheritHandle=TRUE" stated an API REQUEST as an OBSERVED STATE. DuplicateHandle was CALLED with that flag (verified in source), but nobody had called GetHandleInformation on the handle at the CreateProcessW instant. The overclaim was the supervisor's and is corrected here. SUBSEQUENTLY MEASURED — but in a PURE-WIN32 REPLICATION faithful to sigproc.cc:938, NOT in the live runtime: HANDLE_FLAG_INHERIT IS actually set (flags=0x1) under BOTH permission sets, the child receives the handle valid at the same value, and ReadProcessMemory SUCCEEDS (64 bytes, pattern intact) — child_copy's core operation works. So the pure-Win32 call shape does NOT reproduce the failure, and the flag's state on the LIVE runtime's handle at the CreateProcessW instant remains UNMEASURED.** Two more candidates died with it: **storage class is not construction lifetime** (`child_info_spawn () {};` is empty; the real constructor runs via placement-new in `set()`, so construction is per-spawn), and **fork-ancestry of the minting process** (the `direct` arm has no fork in its ancestry and fails identically). Reproduced in pure Win32: inheritance **is** transitive when every generation passes `TRUE`, and a second arm reproduced `INVALID(err6)` at the correct transmitted value. **A fix is confirmed working in `execfix.dll` `8ffe979b` — `direct` exit 42 (was 2816), `forked` PASS (was SIGSEGV), stderr clean.**

**THEN, only if identity confirms the handle IS present:** inspect whatever populates `child_info.parent` for `_CH_EXEC` and why it diverges from the handle the child inherits, given the fork path is correct in the same run. **If identity shows it is NOT present, this is the wrong target** — the defect is that the handle was never inherited. Reproduce with `hscan.ps1`, `rpm2.ps1` and `p4exec.c` — **none of which require a rebuild**, so this is not blocked by the build-reproducibility defects.
