# Git for Windows Native ARM64 vNext Plan

**Reformat recovery entry point: [REHYDRATE.md](REHYDRATE.md).** Evidence is now
being preserved on owning PR branches. Embedded old `C:`/WSL paths are history,
not surviving custody; use repository-relative preservation indexes.

Epoch: `2026-08-31-v1`  
Last reconciled: `2026-09-11` (UTC)

Previous update label: `2026-09-03T07:13:00Z`

**Current outcome: the native ARM64 runtime links, runs, and rebuilds
reproducibly. The full native Git distribution is NOT complete.** The current
work is integrating exact qualified inputs and closing the remaining behavior,
provenance, and final-artifact gates, not writing a missing ARM64 runtime from
scratch. A limited-MVP projection is not a full package/provider admission.

This dated reconciliation supersedes the scheduling statements in the preserved
September 3 record below. It does not mutate sealed evidence, grant runtime
implementation/release authority, or allocate workers. V4 through V10 are
evidence-packet revisions, not product milestones. Source PR state was read at
the heads listed below; local receipts were re-hashed read-only. Local paths are
evidence locators, not portable inputs or permission to modify an owner's tree.

## Live hazard: ordinary make can destroy valid TLS offsets

**OPEN ON THE COMBINED-RUNTIME BASE; FIX PUBLISHED IN PR 34.** `gentls_offsets` greps `.long`, while ARM64
GCC emits `.word` for these 32-bit constants. A plain `make` can silently
overwrite the correct **1,822-byte / 59-entry** `tlsoffsets` with **56 bytes of
zeros**, despite the parser returning success. The known-good SHA-256 is
`49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566`.
This is a measured failure, not an unresolved hypothesis about directive width.

The guarded, atomic-generation proposal is published in
[crutkas/msys2-woarm64-build#11](https://github.com/crutkas/msys2-woarm64-build/pull/11)
at `cc56765f058339cbe018ad4b8330db552576ebac`, under
`arm64-vnext/toolchain/runtime-generation-proposal`. Its handoff [E8] records
16 actual-Make cases and 40 existing TLS cases. **Correction to the earlier
"not yet applied to the runtime repository" status:** an independent successor
is now published as
[crutkas/msys2-runtime#34](https://github.com/crutkas/msys2-runtime/pull/34),
head `df7d66f9b1433c50dd7cd234b0d8bd1213418b22`, based on combined-runtime
`563662010c2f2072ad90f28713611caabdf70dbb`. It has not been merged into that base.

The old 16-case proposal incorrectly returned 0 for a newly exercised case with
**both changed generator inputs and corrupt `sigfe.s`**. The successor validates
the prior output set/hashes **before comparing inputs**, and its producer
reports **26 actual-Make + 40 TLS cases**, including rejection of the known
56-byte zero output. Application handoff [E16] identifies this distinct
successor; the old 16-case proof is not relabeled as covering the new case.
This is generation/ARM64 object proof, not another full runtime rebuild.
Landing must preserve the parent source/evidence and active-reader boundaries.

## Explicit correction: the ARM64 generator already existed

**RETRACTED INFERENCE, NOT A SILENT STATUS EDIT.** Historical row 2e said:

> **ENDORSED JUDGEMENT:** it did NOT write gendef's ~500 lines of AArch64 trampoline assembly, on the grounds that turning the link green with unexecutable trampolines would satisfy `ld` while leaving the runtime broken. Correct, and consistent with the standing ban on papering over failures.

That endorsement, and the framing of roughly 500 lines of unwritten AArch64
trampolines as the critical path, were **false**. The ARM64 `gendef` port already
existed as **`180d3e`**. The build selected HEAD's **x86-only `74f502`** instead:
Perl exited **0** while producing an **exactly 0-byte `sigfe.s`**. The selected
input was wrong; the implementation was not missing. These are abbreviated
generator identifiers supplied by the producer, not invented full commit IDs.
The combined-runtime handoff [E1] records this selection correction and that
signal assembly/object generation was rerun from source, **without substituting
the independent prebuilt native signal object**.

The reasoning failure was inferring absence of an implementation from the wrong
selected generator and treating exit 0 as evidence of a usable artifact. This
silent, clean-looking failure cost the programme days. The ban on fake
trampolines remains correct; its use to endorse the missing-port diagnosis did
not. The original row remains verbatim below, with an adjacent correction.
Bind the selected producer and check actual generated contents before sizing
new implementation work.

## Hard limitations and non-admissions

| Area | What must remain explicit |
|---|---|
| **libintl: limited MVP only** | Admission [E4] covers **two unchanged C DLLs** (`libintl-8.dll`, `libiconv-2.dll`) and **six license files**, not a GNU package alias, full gettext provider, CLI, C++ libraries, docs, or catalogs. The full CLI/default-domain projection **FAILED**: `bindtextdomain` returns the compiled-in `/clangarm64/share/locale`; the CLI remained English **before and after real moves**. Bound-domain qualification does not erase this failure. All 21 blocked consumers in [E9] are MinGW-side PEs; none imports `msys-2.0.dll`. This is not evidence for a native MSYS libintl provider. |
| **PCRE2: current-byte limited MVP only** | Admission [E5] retains **63ca004e / 10.48-1** (`63ca004e` is an abbreviated identifier), projecting only `libpcre2-8.dll` and its license. **No PCRE2 signed-source or independently reproducible-build receipt exists**; no fresh build/full upstream-suite claim is supported. The newer 10.48-3 `libpcre2-8-0.dll` is incompatible with current Git imports; no renamed alias or replacement package admission is allowed. |
| **Berkeley DB: timeout cause RESOLVED on D70, not full provider admission** | Preserve the original **900-second timeout at 9/24, 83-created/76-recorded partial**. Later unchanged full matrix **24/24 passed in 3,733.7 seconds, 314/314 observed, CuTest 0**, within 7,200 seconds. Approximately **15 ms timer quantization** on microsecond yields explains the inadequate old bound; no alignment/contention correctness failure was observed. Exact timing handoff `406c1c7d6ee5242fe888140b132d452771677380d6b0b76323bc625922a1c34f` is preserved under `arm64-vnext/evidence/programme-reconciliation/source-receipts/db-d70-timing-handoff.json`. Functional matrix is **D70 composition only**, not combined 907afa/full SDK/provider qualification. |
| **Core utilities: NO current admission** | Owner-reported retained suite, **not independently verified here**: **48 PASS / 41 FAIL / 23 SKIP / 4 ERROR**. The 37-command constrained projection described by the draft assembly PR is not a full Coreutils provider admission and does not turn this suite green. |
| **Perl: NO qualified provider** | UCRT-hosted GCC reads the raw **`!<symlink>` cookie as source/header content** [E6]. MSYS link predicates can work while the non-MSYS compiler cannot consume those links. **`core.symlinks=false` was proposed and correctly rejected**: it changes written link text, not this compiler file-access boundary. No miniperl/XS/full upstream qualification follows from the current handoff. |
| **SSH: NO native MSYS provider** | The limited artifact relies on the separately qualified portable non-MSYS Microsoft ARM64 Win32-OpenSSH fallback. Do not relabel it as an MSYS OpenSSH package or include the rejected native-MSYS candidate's bytes. |
| **Runtime: scoped success, not universal exit/SDK admission** | **Historical [E1] observer:** rejected raw 32256/1792 despite expected env126/fork7 semantics. **Current resolution: PR 12** preserves those exact DWORDs and classifies only source/image/parent/generation-bound relay contracts, with contracted-positive and identical-uncontracted-negative replay. This supersedes that specific blocker **without a normalization shim**; it does not rewrite [E1], admit arbitrary high exits, or close the distinct raw-256 hook contract. Newlib and compiler backends were reused, not rebuilt. The historical 12:24 DLL/link invocation remains unrecovered/unproven. |
| **SQLite/Tcl: compatibility is not a full-suite rerun** | SQLite's real `libsqlite` package is scoped to the MVP runtime; its receipt says `provider_admitted:false` and `full_upstream_qualified:false`. Tcl's combined-runtime result says scoped-qualified and `full_suite:false`. The producer-reported replay of 33 unchanged Tcl core files yielded **7,702 PASS / 7,957 total / 255 upstream SKIP / 0 semantic FAIL**; these counts are reported, not independently re-derived here, and are not a full-suite rerun implied by the ZIP hash. Native MSYS Tcl is not GUI Tcl/Tk. |
| **V10 authority: primary receipt unavailable** | The V10 ABI `verdict.json` **does not exist on disk** in the coordinator's reported recovery check. The GO narrative is citable only **secondhand through `inbox.md` line 16 in the original checkpoint** [E10]. This reconciliation does not claim to have re-hashed or recovered that verdict and does not reuse it as new authority. |
| **Cross-binutils: real CI PASS on the fix branch only** | The old `makeinfo command not found` / `Makefile:1782: doc/bfd.info` **Error 127** failures remain preserved: five commits are coordinator-reported, two base/head logs independently checked by the CI owner. **PKGBUILD `!ccache` hid the stub; genuine Texinfo was missing.** Fix head `a0b773dbd64b4542d9b8de05911d23af51e87c25` now has actual binutils job **SUCCESS at 07:21:17Z** [E17]. PR 13/14 still need explicit fix integration and reruns. Downstream/native/whole-workflow success is not claimed. |
| **Native CI: HARD INFRASTRUCTURE BLOCKER** | The repository runner API reports **`total_count:0`**, and all seven queued native-toolchain jobs require **`Windows`, `ARM64`, `MSYS2`**. They cannot start under the current runner configuration. This is **not** the cross-binutils/Texinfo dependency failure. These native jobs have not executed, so native-toolchain CI qualification is unsupported. Registration of an appropriately labeled self-hosted runner requires an explicit infrastructure/credentials decision; no session is authorized to do it unilaterally. |

## Infrastructure correction: skipped cross jobs are not queued native jobs

**CORRECTION RECORDED 2026-09-11.** The coordinator's earlier briefing said the
Texinfo fix would unblock roughly seven skipped jobs across PRs 11, 13 and 14.
That blanket statement was **wrong**: it combined two different mechanisms.

| Job class | Observed state and cause | What resolves it |
|---|---|---|
| GitHub-hosted cross-compilation chain | Failed binutils causes **six downstream cross jobs to be SKIPPED** on the observed PR 12/13/14 runs. Binutils on fix run `34571963232` **succeeded at 07:21:17Z**; its GCC stage 1 is now in progress. | The actual-binutils validation gate is satisfied for this fix head. The coordinator-authorized isolated CI-only fix must still reach each affected base/head and its checks run again. |
| Self-hosted native-toolchain chain | **Seven jobs are QUEUED**, requesting `["Windows","ARM64","MSYS2"]`, with **zero registered repository runners**. They are neither slow nor waiting for binutils; they cannot start while this configuration is unchanged. | An explicitly authorized infrastructure owner must register and operate a self-hosted Windows ARM64 MSYS2 runner with all three labels, then execute the native lane. No credential or runner registration action is taken by this plan. |

The seven native jobs are `mingw-w64-zstd`, `mingw-w64-gmp`,
`mingw-w64-libiconv`, `mingw-w64-windows-default-manifest`, `mingw-w64-libtre`,
`mingw-w64-bzip2`, and `mingw-w64-headers-git`. The repository
`actions/runners` API was read as zero by this assessment and independently by
the coordinator; the coordinator also checked the exact job labels. An
organization-level lookup returned 404, not an alternative confirmed runner
pool. **Do not describe the native lane as CI-verified, or count queued/skipped
jobs as passes.** The user retains the infrastructure decision.

**Separate propagation constraint:** PR 11 targets the continuity `reformat`
branch; PR 13 targets `main`, while PRs 12/14 target `roadmap`. Merging PR 11
alone cannot carry Texinfo to those other bases. The coordinator has chosen
isolated CI-only propagation by the CI owner **after actual binutils success**.
That validation prerequisite is now satisfied by [E17]; propagation itself is
not inferred or performed here. Do not ferry all of PR 11 or reparent active
branches. No merges or pushes are authorized by this assessment.

## New resolutions that supersede earlier blockers

**Mechanical exit encoding: source-bound contracts, not normalized status.**
[crutkas/msys2-woarm64-build#12](https://github.com/crutkas/msys2-woarm64-build/pull/12)
at `3834bd94d142e070eecd791627c290febc1773f6` retains the exact unsigned Windows
DWORD. Its published native proof reports that the **contracted** replay kept
raw **32256 and 1792**, classified both, and passed with no unrelayed high exits;
the **identical uncontracted** replay kept the same values and **failed** with
both unrelayed. Twenty observer tests passed; the ARM64 relay helper compiled
with `-Wall -Wextra -Werror` against runtime `907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`.
The documented runtime/`waitpid`/`WEXITSTATUS`/Bash
`WEXITSTATUS_OFFSET=8` boundary explains the encoding; source, image, parent and
process-generation binding determine whether interpretation is permitted.
These are the PR's published results, not tests rerun for this document.
The old handoff's rejection remains true for its unchanged observer, but is
**not the current missing implementation**. No normalization shim was used.

**Cross-binutils: confirmed input/environment cause, not a symlink mystery.**
The pinned package checkout `2cf651dad50d39951a182dea91c68c8ab62a36f6` has
`!ccache` in PKGBUILD line 23. This overrides BUILDENV: the actual makepkg
`buildenv/compiler.sh` hook prepends `/usr/lib/ccache/bin` only when
`check_buildoption ccache` is `y`. The makeinfo-to-`true` stub in that directory
was therefore never searched. Genuine Texinfo was missing from `makedepends`
and the CROSS `base-devel` inputs.

**Corrections to competing hypotheses:** the bare-`winsymlinks` `.lnk` theory
was refuted by same-version MSYS `-L`, `-x`, `command -v` and direct execution
all succeeding on the 768-byte `makeinfo.lnk` when its directory was on PATH.
Cache clobber was refuted by the recorded **CACHE MISS** for
`workspace/ccache`, not `/usr/lib/ccache/bin`. These theories remain in the
historical notes; they are not unresolved current causes.

The now-published fix in PR 11 installs **real Texinfo**, **removes the empty
`true` stub**, and requires a **non-empty Info artifact**. Receipt [E15] records
genuine Texinfo 7.2 passing and missing/no-op/version-only fakes rejected.
[Run 34571963232](https://github.com/crutkas/msys2-woarm64-build/actions/runs/34571963232)
was in progress at the receipt's `2026-09-11T06:56:15Z` snapshot.
**Subsequent measured result:** [actual job 103176510972](https://github.com/crutkas/msys2-woarm64-build/actions/runs/34571963232/job/103176510972)
completed **SUCCESS at 2026-09-11T07:21:17Z** on the same fix head. Receipt [E17]
records Texinfo `7.2-3` installed, non-empty Info preflight at `06:59:30Z`,
`MAKEINFO doc/bfd.info` at `07:06:35Z`, binutils `2.44dev-1` finished at
`07:21:04Z`, and uploaded artifact `10188860473`. The API independently reports
that exact head/job success. **Only this branch/run is qualified.** The PR
remains API `UNSTABLE` with GCC stage 1 in progress and seven native jobs queued;
no full-workflow success or success on another PR is inherited.
[The attribution report](https://github.com/crutkas/msys2-woarm64-build/pull/11#issuecomment-5628925808)
binds the two independently checked failing base/head logs; the broader five
commit comparison remains coordinator-reported.

## Achievements since the stale plan

| Deliverable | Actual result and evidence | Scope boundary |
|---|---|---|
| Combined native ARM64 `msys-2.0.dll` | **Links, executes, and reproduces:** two independent **12-job** controlled builds produced **eight bit-identical artifacts**. DLL SHA-256 `907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`; sealed handoff [E1]. | This replaces the old "nothing links/no DLL/nothing executed" state; it does not close the plain-Make hazard or the exit-domain limitations above. |
| Runtime source publication | Argv and mechanical link closure are published in runtime PR 32; the coherent combined runtime is published in runtime PR 33. | Source review surfaces remain separate. Current peer heads must not be substituted for the historical peer commits bound inside the combined receipt. |
| SQLite | `libsqlite-3.53.4-1-aarch64.pkg.tar.zst`, SHA-256 [E2]; [E12] records **63 captured native positive steps plus three ordinary API passes**, bound to the exact private combined runtime and with no foreign bootstrap in the execution path. | Runtime-only package, not CLI/devel/docs/extensions or full upstream/provider admission. |
| Tcl | Combined-runtime ZIP [E3], scoped native API/alias/module qualification. Separate **producer-reported 33-core-file replay**: **7,702 passed, 255 upstream skips, zero semantic failures out of 7,957**. | Counts are not independently re-derived here. The ZIP's own bound test receipt explicitly does not claim a new full-suite run. |
| Readline | Sealed combined-runtime qualification reports **10/10**, with **12 interrupt cycles and 12 SIGWINCH cycles**. | These are the reported scoped controls, not an inferred complete upstream or whole-artifact result. |
| Berkeley DB | Genuine unsigned `db`, `libdb`, `libdb-devel`, and `db-docs` archives; native API/C++/utility and load/verify/dump/reload results, with actual archive readback. | Full-load MutexAlignment remains incomplete at 9/24; see PR 13 and hard limitation above. |
| libintl and PCRE2 | Exact unchanged payloads admitted for the **limited MVP** by [E4] and [E5]. | Preserve their failed/missing qualification and provenance scopes, not a full provider headline. |
| Git documentation | Earlier Ruby/Asciidoctor leaf produced and installed **273 HTML + 210 man = 483 exact Git targets**. Pipeline admission [E11] preserves original signed native CLANGARM64 Ruby host identity. | XML drivers remain explicitly x64/emulated MSYS build tools; this is documentation closure, not proof that every distribution path is native. |
| MVP assembly tooling | Draft PR 14 publishes exact-receipt assembly, moved-root replay, real Git/HTTPS/native-SSH controls and measured progression. | The final named ZIP remains gated: diagnostic/projection replay is not final-ZIP custody or a full native Git release. |

## Published source and CI snapshot

The initial five delivery PRs are listed together with the newly reported
exit-contract PR 12, not as an exhaustive open-PR inventory. They are **crutkas fork
PRs**, not upstream acceptance. Open/green is not merged or release-admitted.

| PR | Observed head | State at reconciliation |
|---|---|---|
| [crutkas/msys2-runtime#32](https://github.com/crutkas/msys2-runtime/pull/32) | `c30a9e8993a9bf326fac4bd934028b327d935c91` | Open; argv/mechanical link closure; reported checks green. |
| [crutkas/msys2-runtime#33](https://github.com/crutkas/msys2-runtime/pull/33) | `563662010c2f2072ad90f28713611caabdf70dbb` | Open; combined runtime. [Successful run 34557303521](https://github.com/crutkas/msys2-runtime/actions/runs/34557303521) is green. [Earlier run 34557253836](https://github.com/crutkas/msys2-runtime/actions/runs/34557253836) retains a transient pacman libpsl-signature mirror timeout; it was not a runtime source failure. |
| [crutkas/msys2-woarm64-build#11](https://github.com/crutkas/msys2-woarm64-build/pull/11) | `a0b773dbd64b4542d9b8de05911d23af51e87c25` | Open; actual binutils **SUCCESS at 07:21:17Z** [E17]. API still `UNSTABLE`: four successful checks, GCC stage 1 in progress, seven native jobs queued. Old guard/myfault/TLS work and failed-CI evidence are retained. Independent runtime guard successor PR 34 remains separate and unmerged. |
| [crutkas/msys2-runtime#34](https://github.com/crutkas/msys2-runtime/pull/34) | `df7d66f9b1433c50dd7cd234b0d8bd1213418b22` | Open, stacked on PR 33's branch; three-file atomic-generation successor. Its own CI is in progress at the merge-readiness snapshot. Land after reconciled PR 33, not by widening its diff onto the old generator base. |
| [crutkas/msys2-woarm64-build#12](https://github.com/crutkas/msys2-woarm64-build/pull/12) | `3834bd94d142e070eecd791627c290febc1773f6` | Open; exact raw DWORDs plus bound wait-word contracts; two-sided native replay resolves the specific mechanical exit-encoding blocker without a normalization shim. |
| [crutkas/msys2-woarm64-build#13](https://github.com/crutkas/msys2-woarm64-build/pull/13) | `ca76d555a6c10caeccd778fd9c105d581f82b19d` | Open; Berkeley DB packaging and scoped combined-runtime qualification, not a clean stress-suite claim. |
| [crutkas/msys2-woarm64-build#14](https://github.com/crutkas/msys2-woarm64-build/pull/14) | `d618c2d5d6d410b6e98b643d7262f4eb8d8072c5` | **Draft**; MVP assembly tooling. Final seal/publication/replay gates remain; the distinct negative-hook Bash raw `256` needs its dedicated source/argv-bound contract. |

## Current executable work and closure gates

This is the current scheduling view; the original numeric rows below are audit
history. Owners must obtain current resource grants rather than reusing old
session allocations or V10 authority.

| Priority | Responsible workstream | Next executable action | Closure condition |
|---|---|---|---|
| 1 | Runtime owner (`67ba2e76`), independent generation owner (`e6a17275`) | Reconcile runtime PR 33 after PR 32, then land only PR 34's incremental generation successor [E16]. Preserve prior-output validation before changed-input handling; coordinate any update to active parent branches. | Plain Make cannot silently publish bad TLS/signal artifacts; the correct source/output bindings and distinct successor proof survive integration. |
| 2 | Runtime/observer owner and MVP integrator | Consume the published PR 12 mechanical contracts without rewriting the old receipt; close the separate negative-hook raw `256` contract still listed by the draft MVP PR. | Original raw statuses, exact process generations and contracted/uncontracted negative controls remain visible; no universal decoder or waived failure. |
| 3 | Provider owners and MVP integrator | Consume only the admitted [E4]/[E5] bytes and scope; preserve the Coreutils, Perl, SSH and BDB limitations. Fix actual unsupported file-access/behavior boundaries rather than adding aliases or link-text workarounds. | Every included path has an honest provider/projection contract; withheld features remain withheld. |
| 4 | Build/CI owner | Actual binutils success [E17] now satisfies the validation prerequisite. Propagate only the CI fix to each required base as directed, respecting owner/readers and without moving active parents; observe downstream cross jobs separately. | Each affected PR has the genuine fix and fresh applicable checks. This does not resolve the seven native jobs' missing runner or assert propagation has already happened. |
| 4b | User / authorized infrastructure owner | Decide whether to register and operate the missing self-hosted runner labeled `Windows`, `ARM64`, `MSYS2`. No session acts on credentials or registration without separate authority. | The native jobs actually execute and produce results. Until then native CI remains unavailable, regardless of the Texinfo result. |
| 5 | MVP assembly and independent replay owners | Complete the gated named ZIP, exact provenance manifest, independent fresh moved extraction, deterministic recreation, entrypoint/Git/HTTPS/SSH and exit/module checks. | Evidence names the final sealed archive, not only a diagnostic directory or a prior projection. No full Git/SDK/Perl/native-MSYS-SSH claim is inferred. |
| 6 | Documentation/coordination owner | Refresh this view with each new accepted receipt or measured blocker; preserve corrections adjacent to their original claims. | `plan.md`, `inbox.md`, `status.md` and their checksum entries agree on the dated current view; historical authority does not become a live grant. |

## Evidence locators and identity boundaries

The following full SHA-256 values were supplied with exact paths and re-hashed
for this reconciliation; no identifier was expanded from a prefix. Historical
generator IDs `180d3e`/`74f502` and PCRE2 `63ca004e` remain explicitly abbreviated.
Readline counts, the five-commit CI comparison, the 33-core-file Tcl replay
totals, Coreutils suite counts, the rejected `core.symlinks=false` proposal and
the missing V10 file are coordinator/producer-reported observations unless a
primary locator below says otherwise. BDB stress and PR 12 replay counts are
attributed to their published PR reports, not independently rerun local receipts.
**Explicit receipt scope flags govern over every prose summary, including the
coordinator's briefing.**
No new package, runtime, or suite was built to update this document.

| Ref | Artifact / local locator | SHA-256 |
|---|---|---|
| [E1] | Combined-runtime handoff: `C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a\files\combined-runtime-20260911\handoff\combined-runtime-handoff.json` | `f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b` |
| [E2] | SQLite archive: `C:\ag-sqlite-combined-01\package-01\libsqlite-3.53.4-1-aarch64.pkg.tar.zst` | `1144d93cba23cffdfd485f36b90499dbe1a9a88871567ea7aa44fd3616aa4a2e` |
| [E3] | Tcl archive: `C:\ag-tcl-e138-01\combined-20260911-01\tcl-msys-8.6.12-arm64-combined-907afa.zip` | `7451173521d6422f1cd20b9042aaca875bbf01ff841be35c7db3503fd2bb9f14` |
| [E4] | Limited libintl admission: `C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1\export.json` | `ac7849fd9934f5773ab1aa9a49aba30e78c371645af13944cf06d65c6c6661f1` |
| [E5] | Limited PCRE2 admission: `C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1\export.json` | `77837f952344405b330ee730169b83f45ce300a8a74a5cc32b498752f55dbee8` |
| [E6] | Perl compiler/symlink boundary: `C:\ag-perl-f6-20260909\perl-system-symlink-boundary-handoff.json` | `9fdd71e29217602d5f4c5b57eec02636c069563e48e03cbb00a50defa2525cb4` |
| [E7] | Known-good TLS offsets: `C:\agtc-signal-01\build-hardening-proposal-01\tlsoffsets.good` (1,822 bytes) | `49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566` |
| [E8] | Runtime generation proposal: `C:\agtc-signal-01\build-hardening-proposal-01\handoff.json` | `f8429c52a5599f4f1e4601358b564f3dd3d2ee2774dce2ee91760477726f0fed` |
| [E9] | libintl consumer boundary: `C:\ag-mvp-f6-20260911\libintl-consumer-boundary-01.json` | `ecaa96a91879c81ec43ea3f51b359994881f08510ce58fb74d45fd6c56d88718` |
| [E10] | [Original `inbox.md` line 16 at checkpoint commit `50a973c`](https://github.com/crutkas/msys2-woarm64-build/blob/50a973ce610083b44aa684a0418445df72b547ee/arm64-vnext/continuity/2026-08-31-v1/state/inbox.md#L16) | **Secondhand V10 narrative only; the absent `verdict.json` was not verified.** |
| [E11] | Earlier Ruby/Asciidoctor pipeline admission: `C:\ap06-2160\ruby-intake-01\provider-admission.json` | `8e5cf5d15886784252384eab64195b00a6a04a307022124de16eb392e2d7ff84` |
| [E12] | SQLite scoped package receipt: `C:\ag-sqlite-combined-01\package-01\receipt.json` | `1022ac1d857f8768dffd052ea62c0e355680fb21cae4e98e50cc63424efc06d3` |
| [E13] | Tcl scoped combined result: `C:\ag-tcl-e138-01\combined-20260911-01\result.json` | `9cbdbd8e93129ffbef853d03ed7b020e5438aed3ef9d05b73f21b10895318658` |
| [E14] | Tcl bound scoped tests (`full_suite:false`): `C:\ag-tcl-e138-01\combined-20260911-01\tests.json` | `56513d30fb66e1e7fcc44cc5096d13b358a35da837dbc1b5737e45ba3b1eeee8` |
| [E15] | Texinfo root-cause/fix-published receipt: `C:\agtc-ci-texinfo-01\root-cause-handoff-01.json` | `9a3f0803679bd7a1147cd9c93c8dcafa8f0db30657f79c1cdb20e48e3732f577` |
| [E16] | Independent runtime-generation application handoff: `C:\agtc-signal-01\runtime-generation-application-3fc49c8a\handoff.json` | `5fd646b577eec81083f31fe1e532b0387f0e02d509ec457c3f8b1fce306c078b` |
| [E17] | Actual cross-binutils success handoff: `C:\agtc-ci-texinfo-01\success-handoff.json` | `1cce75264489dcec3e7afb48ca95e9f9f6da9095ca3bab8a889f090dc0ebdaeb` |

## Preserved September 3 execution record (superseded)

**Not the current plan or a current authority grant.** The old record mixed
source fixes, unavailable receipts, conditional compile counts and stale
"nothing links" claims. Those statements and their original reasoning remain
below for audit; they are not silently rewritten into later successes. In
particular, old rows 0b, 1, 2c, 2e, 5 and 6 and the old live totals must not be
used to schedule September 11 work. Row 2e has an adjacent explicit correction.
The old V10 claims remain historical secondhand assertions, subject to [E10].

<details>
<summary>Original September 3 scheduling and authority narrative, with adjacent correction</summary>

## Current critical path (historical)

| Priority | Outcome | Current state | Owner | Next executable action |
|---:|---|---|---|---|
| **0c** | **exec() ROOT-CAUSED AND FIXED AT SOURCE — ARM64 PE machine-type allowlist in `hookapi.cc` made `iscygwin()` false, so `spawn.cc:597` stripped `HANDLE_FLAG_INHERIT` from our own binary** | **ROOT-CAUSED AND FIXED AT SOURCE 2026-09-03 23:47 by ``c63ab774``; no workaround.** ``hookapi.cc:43-51`` ``PEHeaderFromHModule`` switches on ``FileHeader.Machine`` with an allowlist containing ONLY ``IMAGE_FILE_MACHINE_AMD64``; an 0xAA64 PE hits ``default: return NULL``, so ``hook_or_detect_cygwin`` returns NULL, ``set_cygexec(NULL)`` runs, ``iscygwin()`` evaluates FALSE for our own ARM64 binary, and ``spawn.cc:597`` strips ``HANDLE_FLAG_INHERIT``. Live measurement at the ``CreateProcessW`` instant: flags=0x0; clear-site instrumentation gave before-clear flags=0x1 iscygwin=0 will_clear=1 -> after-clear flags=0x0. Fix is ONE added case label, and the ``get_parent_handle()`` workaround was REVERTED with the upstream guard restored verbatim: rung14 exec works, rung15 execv and execl both 77, rung19 direct 77, rung18 non-Cygwin 66, full regression clean. **SUPERVISOR MISS, RECORDED: this is the mechanism the supervisor ELIMINATED — status.md 'Eliminated by measurement' listed handle inheritance first. The pure-Win32 replica measured the API shape's CAPABILITY, not the live path's BEHAVIOUR, and a general capability test cannot eliminate a specific instance; separately ``spawn.cc:597`` was dismissed by reasoning about what ``iscygwin()`` SHOULD mean rather than what it EVALUATES TO.** Historical isolation retained below for audit. `exec` fails on ARM64 and was previously invisible because the fork defect blocked before reaching it — fixing fork moved the failure to exec, which is what a real fix does. P3 had **no exec coverage at all**; fixture `p4exec.c` now closes that gap. Failure: `child_copy: cygheap read copy failed, 0x800000000..0x800025A60, done 0, Win32 error 6`, deterministic 6/6. **Measured 3/3 by breakpointing `bl ReadProcessMemory` in `child_copy` and enumerating the child's handle space from a debugger:** on the **fork** path `child_info.parent` always equals the handle actually inherited (`0x204/0x204`, `0x20c/0x20c`, `0x19c/0x19c`); on the **exec** path it never does (`0x1a8` vs real `0x200`; `0x1a0` vs `0x208`; `0x1a4` vs `0x198`). **RETRACTED 2026-09-03 23:15 — the claim that a valid parent handle IS present in the exec'd child (so `child_info` merely names the wrong one) DOES NOT STAND.** It inferred **identity** from **validity** with no negative control; `state/handle-identity-vs-validity.md` measures that at ±4/8/12 from a true inherited handle a probe reads VALID in nearly every arm and SIGNALLED in **5 of 6**, while being a **different kernel object**, because handle values allocate densely at 4-byte granularity and the child's own table populates the same range. **What still stands:** fork's recorded value functionally works (`ReadProcessMemory` through it succeeds) and exec's recorded value is genuinely invalid (`DuplicateHandle` returns err 6). **Eliminated by measurement:** handle-inheritance mechanism on WoA (verified with the exact exec permission set), the permission set, `bInheritHandles`, `child_info` structural integrity (intro/magic/`cb`/`fhandler_union_cb` all validate), source region mapped and `PAGE_READWRITE` in the parent at the moment of the copy, destination region committed (the runtime's own printed argument), and a timing race. The reported `ERROR_INVALID_HANDLE` is **genuine** — `res == FALSE` captured at the call return, so `__seterrno()` did run. | Unowned; findings from supervisor `290c9aaf` | **IDENTITY BRANCH SETTLED 2026-09-03 23:25 — and it kills the `_CH_EXEC` population lead, which was the supervisor's proposed target.** `c63ab774` instrumented the mint site and the child's read: CTOR type=1 parent=0x190 minted_in_pid=14816; CHILD got parent=0x190 usable=0 err=6 parent_winpid=14816. **The child receives EXACTLY the value minted, minted in the process that calls CreateProcessW, for this spawn** — so `child_info.parent` is populated CORRECTLY and whatever populates it is NOT the defect. The surviving fact: a handle for which bInheritHandle=TRUE was REQUESTED at DuplicateHandle and which was passed with bInheritHandles=TRUE **arrives with the correct numeric value and is ABSENT from the child's handle table.** **PRECISION CORRECTION 2026-09-03 23:36 — the earlier phrasing "a handle DUPLICATED bInheritHandle=TRUE" stated an API REQUEST as an OBSERVED STATE. DuplicateHandle was CALLED with that flag (verified in source), but nobody had called GetHandleInformation on the handle at the CreateProcessW instant. The overclaim was the supervisor's and is corrected here. SUBSEQUENTLY MEASURED — but in a PURE-WIN32 REPLICATION faithful to sigproc.cc:938, NOT in the live runtime: HANDLE_FLAG_INHERIT IS actually set (flags=0x1) under BOTH permission sets, the child receives the handle valid at the same value, and ReadProcessMemory SUCCEEDS (64 bytes, pattern intact) — child_copy's core operation works. So the pure-Win32 call shape does NOT reproduce the failure, and the flag's state on the LIVE runtime's handle at the CreateProcessW instant remains UNMEASURED.** Two further candidates died: storage-class-implies-lifetime (`child_info_spawn () {};` is EMPTY, the real ctor runs via placement-new in `set()`, so construction is per-spawn) and fork-ancestry-of-the-minting-process (the `direct` arm has no fork in its ancestry and fails identically). Signature since reproduced in pure Win32: inheritance IS transitive when every generation passes TRUE, and a second arm reproduced INVALID err6 at the correct transmitted value. **A FIX IS CONFIRMED WORKING in execfix.dll 8ffe979b — direct exit 42 (was 2816), forked PASS (was SIGSEGV), stderr clean — verified on exit-code criteria, not banners.** Supervisor-owned instrument hygiene is done: p4exec.c verdicts are exit-code based, its decode handles signal deaths, and the successor-stdout trap is documented in the file. Two latent defects found alongside and worth fixing independently: `child_copy` prints a **stale** Win32 error on the short-count path (`fork.cc:753-767` — it misdirected this investigation for two cycles), and both `VirtualAlloc` returns are **unchecked** before use (`cygheap.cc:92-100`). |
| **0b** | **Restore build reproducibility — the ARM64 runtime cannot currently be rebuilt** | **FIVE DEFECTS CONFIRMED BY EXECUTION** (one further item escalated and then **retracted**). Found by attempting the rebuild in a `cp -a` copy; the link session's tree was never modified and was verified byte-identical throughout. **(1)** `Makefile.am` `TARGET_AARCH64` lists **11 `aarch64/*.S` files that do not exist** (x86_64: 11/11 present) — `make` dies immediately. **(2)** `scripts/gentls_offsets` greps `\.long` at lines 65/88 but **ARM64 GCC emits `.word`**, so `tlsoffsets` regenerates as **56 bytes of zeros** instead of 1,822 B/59 entries and `sigfe.s` then cannot assemble — **live hazard: running `make` in the real tree silently destroys a working `tlsoffsets`.** **(3)** the `windres` invocation lacks include paths (`cygwin/version.h` not found). **(4)** the link rule at `Makefile:3247` uses `$(CXX) $(CXXFLAGS)` and **never references `$(LDFLAGS)`**, while the required `-L` paths exist **nowhere** in the build system. **(5) MOST SERIOUS AND SILENT:** `__MSYS__` is not predefined (the compiler defines `__CYGWIN__`), not in `config.h`, and not added by the Makefile, so `dcrt0.cc:1102` compiles `cygwin_dll_init` where the shipped DLL exports `msys_dll_init` — **clean compile, no warning, wrong exported symbol.** **SIZED: this is programme-wide, not one symbol — 38 occurrences across 18 files, defined NOWHERE in the tree.** It gates `environ.cc` (10 sites: `MSYSTEM=`, `setenv("MSYS",…)`, **different environment index tables**), `fhandler/pty.cc` (6), process startup (`crt0.c`, `cygwin_crt0.c`, `cygwin_attach_dll.c`), `dtable.cc` (recognising `msys-` DLLs), and — most significantly — **`mm/cygheap.cc`'s `init_installation_root()`, where the MSYS build backs up TWO directories and the non-MSYS build backs up one AND writes registry keys.** That runs inside `setup_cygheap()`, the same startup path as the fork defect. A rebuild from the recorded command therefore produces a materially different runtime that compiles and links cleanly. **RETRACTED:** "`fenv_aarch64.o` has no source" was escalated and is **false** — the source is at `math/aarch64/fenv_extern_aarch64.c`, named by the object's own DWARF. | Whoever performed the 12:24 link; defects found by supervisor `290c9aaf` | **Record the link command used to produce `new-msys-2.0.dll` at 12:24.** Every measurable input was compared against that build and matches — `cygwin.sc`, `version.o`, `uname_version.o`, `tlsoffsets` identical; `libdll.a` 250 members each differing only in the fenv object's filename; `sigfe.o` and `winver.o` each tested and **eliminated**; `CXXFLAGS` identical; entry point in both resolves to `dll_entry` with a byte-identical prologue — **and a rebuild still crashes `0xC0000005`.** The only remaining variable is the unrecorded link invocation. **This blocks row 0a**: the fork/argv fixes cannot be validated in a real build until the runtime can be rebuilt at all. Fix defect 5 independently and urgently. |
| **0a** | **Land the two root-caused runtime fixes (fork + argv)** | **BOTH FIXES APPLIED BY `de02421a` AND VALIDATED IN A REAL FROM-SOURCE BUILD (2026-09-03 22:44).** fork landed 22:23 (DLL `54e464d0`), argv landed 22:44 (DLL `90bfb483`), both compiled and linked by the link session itself — superseding all earlier binary-patch validation. **Measured against `90bfb483`: P3 7/7** (`malloc file setjmp sigsetjmp tls signal fork`) against a **5/7** baseline, and **argv corruption is gone** (`abcdefg`→`abcdefg`, and clean at 16 and 24 characters). Supersedes the prior "OS loader during lazy DLL load" and `sizeof(_cygtls)` lines — **neither was the cause**. **(1) fork:** `dcrt0.cc:1054-1060`, the ARM64 arm of the main-thread stack switch, subtracted nothing where x86_64 subtracts 32, on the stated but incorrect grounds that ARM64 has no shadow space. x86_64 addresses locals at NEGATIVE offsets from `rbp`; AArch64 uses POSITIVE offsets from `sp`. With `create_new_main_thread_stack` returning `StackBase-16`, the ordinary spill `str x4,[sp,#24]` at `0x180046cd8` wrote `StackBase+8` — which **is** `cygheap->chain`. Faulting `Pc` captured on hardware 3/3. `de02421a` fixed it with `sub sp, sp, #64` (measured requirement was 32; more margin, safer direction). **(2) argv:** `dcrt0.cc:165,167` called `strcpy` on OVERLAPPING buffers (undefined behaviour). Upstream Cygwin latent bug: x86_64's byte-forward `strcpy` tolerates it; ARM64's aligns the source down 16 bytes and loads NEON blocks, re-reading bytes its own stores overwrote. Reproduced byte-for-byte outside the runtime; fixed with `memmove` at both call sites. | `de02421a` (implemented); root causes from supervisor `290c9aaf` | **Effectively closed — remaining work is owner sign-off and commit.** One caveat recorded so it is not misread: in the intermediate 22:24 build the fork fix alone gave P3 7/7 **while argv was still corrupt**, because the corruption position tracks total command-line length and happened to land outside `sigsetjmp`'s argument in that directory. **A 7/7 P3 did not imply argv was fixed**; only the direct argv probe establishes that, and it now passes. Still worth landing independently: a guard page between `THREAD_STORAGE_HIGH` and `CYGHEAP_STORAGE_LOW` so any future overrun faults loudly rather than silently corrupting the heap chain. |
| 0 | Authorize the runtime ABI implementation session | **GRANTED, NARROW AND LOCAL-BUILD-ONLY.** Terminal review `8f09cf29...` sealed `GO_RUNTIME_ABI_SESSION_START_LOCAL_BUILD_ONLY` (verdict payload `cca57c2c...`, manifest `c788707a...`, sums `51b7dd74...`, external receipt `cd8452b9...`), independently reverified at 33 read-only files, 31/31 sums and 13/13 seals. Decisive proof: applying sealed diff `4b6ce05e...` to frozen V9 wrapper `524ada84...` reproduces V10 wrapper `e34cb967...` byte-for-byte. 145-case suite 145 PASS with 0 compiler/linker children; 251-case matrix across three roots with 0 mismatches; 49 uncanned probes with 0 deviations. `verdict.json` is itself the hash-bound receipt; no product PASS is claimed. | Frozen V10 owner `e18a4fba-d649-4757-801c-f6560c9ffc13`; reviewer of record `8f09cf29-8022-4d43-81c7-f223baaa6143`; superseded first review `797d4709-75a2-4bb3-8b36-b5e482f17a5c` preserved | Authority is consumed by exactly one child ABI session. Do not re-review, re-request, or widen scope; any product-closure claim additionally requires the frozen step-runner production-dispatch fix. |
| 1 | Start runtime ABI implementation and continuous compile/test | **COMPLETE AT THE SCOPE BOUNDARY; NO PRODUCT PASS.** Sole authorized session `724ee2e9-51c7-40d7-b303-e6fcbfe78490` finished with the hard stop held: HEAD `d890a845...`, tree `43aec2ed...`, 0 commits ahead, nothing staged, empty stash, 29 files at 785 insertions / 51 deletions uncommitted. AA64 objects went 12 to 266 with zero non-AA64, errors 885 to 64, clang frontend crashes 19 to 0, and `#error unimplemented for this target` sites 16 to 1. Nothing links and no DLL exists. Two sealed backups verify with zero checksum failures: primary sums `47059be6...` and redundant sums `ec458637...`; the patch carries 29 diff headers and passes `git apply --check --reverse`. | Work sealed; owner decisions pending | **RESTORE WARNING:** `winsup/cygwin/math/aarch64/longdouble.c` is untracked and therefore absent from the patch, so it must be copied separately from the backup `untracked\` path or the tree fails at link with the long double symbols missing. No commit authority exists; do not create or restart any ABI session. |
| 2 | Decide the LP64 versus LLP64 runtime path | **RESOLVED BY EVIDENCE: LP64. Owner ratification still outstanding.** Settled 2026-09-03 by BUILDING the `aarch64-pc-cygwin` GCC target and measuring predefines and codegen, not by reading config fragments. It yields `__CYGWIN__ 1`, `__unix__ 1`, `__SIZEOF_LONG__ 8`, `_LP64`/`__LP64__ 1`, `__SIZEOF_LONG_DOUBLE__ 8`, with `__MINGW32__`/`_WIN32`/`_WIN64` all undefined, and emits `madd x0, x0, x1, x2` where LLP64 would use `w` registers. **Position B never existed as an artifact:** `aarch64_multilibs="llp64"` is a DEAD TOKEN — the backend rejects `-mabi=llp64`, `gcc/configure.ac:4394` sets `TM_MULTILIB_CONFIG=lp64`, the `i386/cygwin-w64.h` override wins last, and upstream master has ZERO `llp64` hits. Clang's `__SIZEOF_LONG__ 4` is therefore a CLANG DEFECT, not a competing data model. One deliberate ARM64 divergence: 64-bit `long double` (`TARGET_LONG_DOUBLE_64`), unlike x86_64 Cygwin's 80-bit x87 — which independently validates the sealed long double wrapper work. **MEASURED, not inferred: the 11 LLP64-artifact sites COMPILE CLEAN under LP64**, every pointer-width error having vanished once `_WIN64` was correctly set. | Programme owner (ratification only) | Ratify LP64. The decision no longer gates engineering: item 2 of the IOU list (LLVM `TargetInfo`) is unblocked on two independent grounds, and a v2 LP64-based clang patch already exists as an additive sibling with v1 frozen. **PERMANENT: never silence the 11 sites with casts** — wrong under LP64, and would silently corrupt `off_t`, `ssize_t`, `ino_t` and `blkcnt_t` at runtime on large files. Estimated remaining work on them: ZERO. |
| 2b | Prepare linker/import validation | **TERMINAL, SEALED, INDEPENDENTLY REPLAYED, ARTIFACT-ONLY.** The packet contains 672 inventoried files, 11 positive and 7 negative fixture contracts, 166 bounded receipts, 40/40 deterministic core outputs, and synthetic normal/delay/import/export/relocation/unwind/resource/pseudo-reloc controls. Fixture and product runtime executions are zero. Root digest `09f78c61...`. | `473f3049-885c-495d-ad24-c4549786fe4b` | Preserve the frozen packet for separately authorized runtime-ABI and linker/import compile loops. Retain its explicit non-job-containment limitation. |
| 2c | Build a USABLE `aarch64-pc-cygwin` cross and compile the real runtime | **IN PROGRESS, LOCAL-BUILD-ONLY, NO PRODUCT PASS.** A usable cross now exists that compiles real `winsup/cygwin` C++ source, not merely reports predefines. **REPORT THE FULL LABELLED PROGRESSION, NEVER A HEADLINE NUMBER** (two figure errors have already occurred on this result): row 1 w32api master = 116/310 objects, 314 errors; row 2 + `_WIN64` fix = 116/310, 285; **row 3 + released w32api v12.0.0 = 254/310, 15 errors — THIS IS WHAT THE SEALED PORT REACHES AS-IS**; row 4 + three THROWAWAY DIAGNOSTIC fixes (`fabsl.c`, `cygwin.sc.in`, `MALLOC_ALIGNMENT`, committed nowhere and NOT proposed) = 261/310, 8; row 5 warnings non-fatal = 265/310, 3. **Rows 4-5 are CONDITIONAL — "achievable once three further fixes land", not achieved.** Root blocker was never the port: `mingw-w64-headers/crt/_cygwin.h:32-34` gates `_WIN64` on `#ifdef __x86_64__`, so on aarch64 `basetsd.h` silently takes its 32-bit branch and every pointer-width type narrows, manufacturing errors indistinguishable from ARM64 port defects. Reaching the LINKER is a qualitative shift: ARM64 codegen, the LP64 header world and C++ compilation of `winsup/cygwin` now work end to end. | `1e64365a-8e29-4b6b-80ea-34408c4d868b` (complete); `c63ab774-a023-4e57-9bc4-53f727507ada` (link attempt, in progress) | **CAVEATS THAT MUST NOT SOFTEN: nothing has linked, no DLL exists, nothing has been executed on ARM64, and NO product PASS is claimed.** Treat all counts as in-progress until `c63ab774` reports with the full labelled progression plus explicit verification that the sysroot still carries the `_cygwin.h` fix and v12.0.0 headers. The 676 undefined references separate into TWO buckets that must never be merged into one homogeneous wall: **bucket 1** missing `netapi32`/`user32` import libraries, MECHANICAL; **bucket 2** `exception::myfault` and the ARM64 SEH personality routine, GENUINE IMPLEMENTATION WORK. |
| 2e | Attempt to LINK a native ARM64 `msys-2.0.dll` | **NO — IT DID NOT LINK. No `.dll` exists**, so there is no PE machine type, size or sha256. **Nothing was executed. Nothing was stubbed. No product PASS.** But the build **reached the link stage for the first time in this programme**, with real `libc.a`/`libm.a`/`libgcc.a`, real ARM64 import libs, a real linker script and a real `.def` — and `ld` produced a FINITE remaining-work list. Compile state **271/310 objects, ZERO `error:` lines, exactly ONE failing TU (`autoload.o`)** — but that 271 **INHERITS the three uncommitted throwaway diagnostics and is CONDITIONAL; the sealed port as-is remains ROW 3 = 254/310, 15 errors.** Link failures concentrate in two components: **`gendef`/empty `sigfe.s`** = 990 `cannot export` (980 `_sigfe_*`, plus `sigsetjmp`/`siglongjmp`) and 4 undefined (`_sigbe`, `sigdelayed`, `_sigdelayed_end`, `_sigfe_malloc`); **`autoload.cc`** = 192 undefined, verified individually so that **192 of the 196 total undefined refs are exactly what `autoload.cc` would have defined**, the other 4 being gendef's. Plus 8 orphan `cygwin.din` exports with no aarch64 implementation (`fegetprec`, `fesetprec`, `_fe_nomask_env` — x87 precision control is meaningless on ARM64 — `fedisableexcept`, `fegetexcept`, `__alloca`, `_ctype_`, `msys_dll_init`). **libstdc++ gap CLOSED:** freestanding headers suffice; a hosted libstdc++ is impossible (`configure` dies on `GCC_NO_EXECUTABLES` — the target libc IS the DLL being built) and unnecessary (the whole tree includes exactly ONE C++ standard header, `<new>` at `cygwin-cxx.h:17`). | `c63ab774-a023-4e57-9bc4-53f727507ada` | **ENDORSED JUDGEMENT:** it did NOT write gendef's ~500 lines of AArch64 trampoline assembly, on the grounds that turning the link green with unexecutable trampolines would satisfy `ld` while leaving the runtime broken. Correct, and consistent with the standing ban on papering over failures. Sysroot trap handled correctly: `_cygwin.h` verified INTACT rather than reinstalling w32api. Self-disclosed and corrected its own error (blanking `libm_machine_dir` dropped `s_fma.c`/`sf_fma.c`/fenv; restored and re-verified). |
| **2e CORRECTION (2026-09-11)** | **The missing-trampoline diagnosis above was FALSE.** | ARM64 `gendef` **already existed as `180d3e`**; the build wrongly selected HEAD's **x86-only `74f502`**, which emitted an **exactly 0-byte `sigfe.s` with Perl exit 0**. These generator identifiers are abbreviated. The wrong source selection, not ~500 lines of unwritten assembly, was the defect. The original endorsement is preserved immediately above so the reasoning failure remains visible. | Reconciled from combined-runtime handoff [E1] | The runtime now links, runs and reproduces. Bind the real selected producer and require meaningful generated output; do not revive the missing-port estimate or erase the separate live TLS hazard. |
| 2f | ARM64 SEH handler name is hard-coded and WRONG for the pinned w32api | **SEALED-PORT DEFECT — highest-value finding of the link attempt.** `local_includes/exception.h` and `local_includes/cygtls.h` **hard-code a C++ mangled name** into `.seh_handler`.

**PRIMARY ARGUMENT — BY CONSTRUCTION, NOT BY PRESENCE.** C++ mangling uses the **underlying struct tag**, not the typedef name. Some header sets **alias `PDISPATCHER_CONTEXT` to a DIFFERENTLY-TAGGED struct**, which therefore **MUST** change the mangled name of any function taking that parameter. CLANGARM64 `winnt.h` defines `typedef struct _DISPATCHER_CONTEXT_ARM64 {` at 2480 and then, at 2495-2497, `#if defined(_ARM64_)` / `typedef DISPATCHER_CONTEXT_ARM64 DISPATCHER_CONTEXT, *PDISPATCHER_CONTEXT` / `#endif` — so `PDISPATCHER_CONTEXT` **necessarily** resolves to `struct _DISPATCHER_CONTEXT_ARM64 *` and the mangled name is **necessarily P25**. mingw-w64 master carries the same alias at 2481. Released w32api v12.0.0 has **no such struct**, so it **necessarily yields P19**. This is not "some headers happen to mention a name" (circumstantial) — it is a structural necessity, and **it definitively rules out any token-swap fix.**

**MICROSOFT'S OWN SDK RESOLVES TO P19 — and counting gives the WRONG answer here.** Windows SDK `10.0.26100.0\um\winnt.h` (876,232 B, sha `8693f0ad...`) *textually* contains `_DISPATCHER_CONTEXT_ARM64` six times (word-boundary, excluding `ARM64EC`), which naively suggests the P25 camp. **It does not.** Five of the six are preprocessor plumbing. Under `#if defined(_ARM64_) || defined(_CHPE_X86_ARM64_)`, line **7101** does `#define _DISPATCHER_CONTEXT_ARM64 _DISPATCHER_CONTEXT`, so when line **7130** writes `typedef struct _DISPATCHER_CONTEXT_ARM64 {` **the preprocessor rewrites the tag** and the compiler actually sees `struct _DISPATCHER_CONTEXT`; line **7147** then aliases `PDISPATCHER_CONTEXT` to it, and 7149-7150 `#undef`/`pop_macro` so the rewrite cannot leak. **On an ARM64 target the number of struct declarations surviving as `_DISPATCHER_CONTEXT_ARM64` is ZERO, and Microsoft mangles to P19.** So **w32api v12.0.0 AGREES with Microsoft**, while **CLANGARM64 and mingw-w64 master are the DIVERGENCE**. On non-ARM64 the guard is false, no rewrite happens, and the ARM64 struct exists as a distinct cross-arch type — which is exactly why a textual grep on a non-ARM64 machine reports its presence and misleads. **DO NOT OVER-CORRECT: the fix requirement is UNCHANGED.** The name still varies by header set, so it must be **derived, not hard-coded**, and a token swap to P19 is still wrong. Only *which spelling is authoritative* flips. Note also that `exception.h:16-18` turns out to be **closer to Microsoft's actual behaviour than to mingw-w64's while still being wrong as a universal** — a comment can be **accidentally near-right and still dangerous**, because it asserts a universality it never established, and being right by luck about the common case survives casual checking. (A fourth substring source sits at SDK line 7115, `_DISPATCHER_CONTEXT_NONVOLREG_ARM64`.)

*Supporting detail (occurrence counts, secondary — and note the SDK case proves counts can invert the truth):* v12.0.0 (10,390 lines) has three plain `struct _DISPATCHER_CONTEXT` blocks at 2074/2310/2974 and zero `_DISPATCHER_CONTEXT_ARM64`; CLANGARM64 has 8 plain plus **one genuine** `_DISPATCHER_CONTEXT_ARM64` (a second substring hit at 3126 is `_DISPATCHER_CONTEXT_ARM64EC`, a **different struct**).

Under v12.0.0 `exceptions.o` defines `...P19_DISPATCHER_CONTEXT`, so `.seh_handler` names a symbol that never exists. Silent, link-time-only. | Recorded, not scheduled | **RETRACTION:** an earlier entry recorded the linker's `P25...` symbol as independent cross-validation of the ABI session's mangling analysis. That was **COMMON-CAUSE, not independent** — the linker echoed a token the source hard-codes (sealed patch line 1035). **Generalised rule: a downstream tool repeating a string an upstream artifact hard-coded is NOT independent corroboration; establish whether the second source DERIVED the value or merely REPEATED it.** The ABI session's measurement was correct FOR THE HEADERS IT USED and its measure-don't-guess method stands; only my inference was wrong. **NOT a one-token fix, and must not be recorded as one.** Swapping `P25_DISPATCHER_CONTEXT_ARM64` for `P19_DISPATCHER_CONTEXT` fixes released w32api v12.0.0 **and then breaks under any header set that DOES define `_DISPATCHER_CONTEXT_ARM64` — including the CLANGARM64 toolchain this programme also uses**, whose `winnt.h` carries 2 occurrences of it. A token swap reintroduces the identical bug in the opposite direction. The actual defect is that the port **hard-codes a mangled name at all**, making `.seh_handler` silently header-version-dependent with failure deferred to link time. **The fix must be VERSION-ROBUST: derive the name, or condition on whether the struct exists.** **Scope also includes DELETING TWO FALSE COMMENTS:** `exception.h:16-18` asserts *"plain `_DISPATCHER_CONTEXT` on every architecture — there is no `_DISPATCHER_CONTEXT_ARM64`"*, false as a universal and stated with the confidence of settled design; and `cygtls.h:365` still claims the opposite while the code three lines later emits P19 — comment and code contradicting each other in one file. **HEADER-SET-DEPENDENT AS VERIFIED FACT:** CLANGARM64 (405,341 B, sha `51f9430b...`) defines the ARM64 struct at 2480 and aliases it at 2496 under `#if defined(_ARM64_)` => P25; released w32api v12.0.0 has ZERO occurrences and three plain blocks (2074/2310/2974) => P19; mingw-w64 master aliases at 2481 => P25; and two headers *inside the same checkout* disagree (`inst/.../w32api` 387,345 B ZERO ARM64 vs `widl/include` 264,325 B FOUR). Both measurements were correct for their own header set; neither party mismeasured. |
| 2g | **BINDING: never write `x18` on Windows ARM64** | **HARD RULE from the sealed ABI session, verified by audit across every file it touched.** `x18` is the **reserved platform register holding the TEB**. A stray write is **catastrophic and near-undiagnosable**. **Reading `x18` is fine; writing it is not.** The ABI session's actual implementation reads the TEB via `mrs x16, tpidr_el0` then loads `[x16, #8]`. | All future ARM64 assembly work | Use this formulation verbatim: **"read the TEB via `tpidr_el0` (or read-only from `x18`); NEVER write `x18`."** Describing the port of TEB access as "`%gs:8` -> `x18`" is accurate about *where the TEB lives* but reads as an instruction to use `x18` as a destination, inviting exactly the catastrophic write this rule forbids. **This must survive into whoever does the `gendef` trampoline work** — the largest remaining item (980 `_sigfe_*` exports from an empty `sigfe.s`) and the code most likely to touch platform registers. |
| 2h | Preservation chain — VERIFIED RECOVERABLE | **The sealed patch PROVABLY APPLIES to `d890a845` — verified by pre-image blob comparison, read-only.** For all **43** `index <pre>..<post>` headers in `runtime-uncommitted.diff` (137,762 B), the pre-image blob was compared against `git rev-parse d890a845:<path>`: **43/43 MATCH, zero mismatches, zero new-file pre-images.** No checkout, no apply, no worktree, no index change. The `ASSETS-README.md` recipe (`git checkout d890a845` then `git apply`) is therefore **verified, not merely written down** — an unverified recovery procedure is indistinguishable from a working one until the moment it is needed, which is exactly when the source state no longer exists. | Read-only validation; nothing mutated | **CRITICAL CAVEAT — APPLICABILITY IS NOT CONTENT CORRECTNESS.** These checks answer only *"will this apply cleanly to this commit"*. **The live counterexample is inside this very diff**, which is *known* to contain wrong content: the P19 token swap plus its two false comments. The artifact is simultaneously **provably applicable and known to be partly wrong** — the cleanest demonstration the two properties are independent. Recovery guarantees you can reconstruct the tree exactly; it does **not** guarantee what you reconstruct is correct. **`longdouble.c` — VARIANCE RESOLVED BY A FOURTH ROW:** live tree 3,368/LF/`aaf9785b…`; `c63ab774` evidence 3,368/152 bare LF/`aaf9785b…`; `724ee2e9` backup 3,520/152 CRLF/`52d89409…` normalising to `aaf9785b…`. **The LF copies are byte-faithful to the live tree; the CRLF copy was converted Windows-side. Nothing altered.** Without the source of truth as a row, a variance analysis can show copies differ but cannot show which is faithful. **The patch REFERENCES `longdouble.c` without CREATING it** — verified: one mention, line 187, a `Makefile.am` entry, and **zero `diff --git` headers** name it. Applying the patch alone yields a `Makefile.am` pointing at a nonexistent file and the tree fails at LINK, far from the cause. Shape re-measured: **29 headers / 785 insertions / 51 deletions**, and **0 CR bytes** — pure LF because it was written with `git diff --output=` rather than through a shell pipeline. **DISCREPANCY CORRECTED:** the two `longdouble.c` copies are **NOT byte-identical**. The `c63ab774` evidence copy is **3,368 B, 152 bare LF**; the `724ee2e9` sealed-backup copy is **3,520 B, 152 CRLF** — delta exactly one byte per line. **Content is safe:** identical after LF normalisation, both `aaf9785b...`. **Prefer the LF copy for restore** (the build tree is LF), or normalise before use, and **verify against the normalised hash, never a raw byte count**. Same CRLF hazard tracked all day, surfacing in the artifact meant to guarantee recovery. |
| 2i | Toolchain custody — CONSOLIDATED | **The evidence directory preserved the SOURCE state completely but NOT the TOOLCHAIN, which is a precondition it did not contain. `/root/xc/inst` was listed under "preserved assets" — which reads like custody but confers none. LISTING IS NOT PRESERVING.** The compiler existed only as live WSL filesystem state: in no diff, no repo, no archive, with its build recipe in session directories the README never mentioned. **RESOLVED (copying + documentation only):** 31 files copied into `evidence/toolchain-recipe/` as `from-fca94a35/` and `from-1e64365a/` so provenance survives; **31/31 verified byte-identical**, originals unmodified. `PROVENANCE.md` records each file's origin session, original path, bytes and sha256. `ASSETS-README.md` amended at the point of discovery (`8ade9950...`->`9e0ca8ac...`); `SHA256SUMS` regenerated (`47443361...`->`54103a5f...`), **47 records, 47 PASS / 0 FAIL**. | Read-only preservation; no build, no repo mutation | **LIMITATION: replay is UNTESTED — consolidation makes the recipe FINDABLE, not VERIFIED.** A rebuild remains an owner decision, now well-posed. **CORRECTION: a preserved script DOES build `aarch64-pc-cygwin-g++`** — `from-1e64365a/gcc-cxx.sh` configures `--enable-languages=c,c++` and runs `make all-gcc` into `/root/xc/inst`, so the earlier "none produces g++" assessment was wrong. It narrows the RECIPE gap, not the CUSTODY gap; the preservation finding stands. Scope deviation disclosed: the **complete** `s1`-`s22` chain was copied rather than the named subset, because a sequential recipe with holes is the same trap this removes — and the extras contained the most important script. |
| 2d | Sysroot integrity trap | **ACTIVE HAZARD, RECORDED NOT ACTIONED.** `/root/xc/inst/aarch64-pc-cygwin/include/w32api` CARRIES the one-line `_cygwin.h` fix. A naive header reinstall from unpatched mingw-w64 sources SILENTLY REGRESSES it, dropping the build from 254 objects back to 116 with no obvious cause. | Any session touching the sysroot | Recognition symptom: object count collapsing to 116 with `UINT_PTR`/`INT_PTR`/`LONG_PTR`/`SOCKET`/`DWORD_PTR` becoming 32-bit. Re-apply the fix or pin a mingw-w64 tree that already contains it. Also do NOT reinstate the `mbstate_t` shim: that was a mingw-w64 MASTER regression (`8c4baed92`, in no release tag) colliding with newlib on EVERY Cygwin target including x86_64; the correct mitigation is released w32api v12.0.0. |
| 3 | Prepare signal/TLS and fork/exec validation | **TERMINAL, SEALED, INDEPENDENTLY REPLAYED, ARTIFACT-ONLY.** Fifteen future tests, 126 assertions, 1,082 host records, seven byte-reproducible AA64 helpers, and bounded stream/timeout/residual/wrong-architecture controls are sealed. All 3,304 checksum entries replayed; no candidate runtime test executed and no authority is claimed. | `5e19eaff-8948-4f39-a0d7-daa13e4ee076` | Preserve the frozen packet for separately authorized signal/TLS, MVP, and fork/exec implementation after exact later heads/trees and a fresh runtime sysroot exist. |
| 4 | Prepare Git Bash payload assembly | **P5 EXTERNAL INPUTS 34/34; GRAPH 73/80.** Exact Schannel local-engineering transition is applied in immutable successor `c435e6f5...` after review and immediate double recapture. Execution receipt `a24562ee...` and external receipt `1ec2ef77...` pass. Seven node-produced runtime/payload outputs remain exact placeholders; no ZIP or product claim exists. | Frozen harness `5acb4426-d1c0-40f8-91fb-2daf0806488c`; frozen materialization `b6d8b789-7781-42d7-8ffd-1d1e7e52624f`; frozen Schannel successor `c6ce98ad-52c5-441e-886a-716db53a189a` | Preserve all frozen input packets. Wait for the seven separately owned runtime/payload outputs; do not create the final ZIP early. |
| 5 | Integrate Bash, Git/Schannel, and OpenSSH | **PENDING RUNTIME MVP.** Input selections are defined, but no fresh native runtime/Bash closure exists. | Future runtime MVP and payload sessions | Assemble and test after ABI, linker/import, and signal/TLS layers produce a runnable runtime. |
| 6 | Produce and replay the engineering handoff | **PENDING.** | Future payload/replay sessions | Build the ZIP, move-extract it, replay independently, attest architecture/import closure, and publish the non-admitted handoff. |

## Active blockers

| Blocker | Effect | Resolution |
|---|---|---|
| First V10 review reached NO-GO on reviewer-environment gaps, not on any defect | No authority exists even though every executed check against the V10 change passed | Coordinator independently verified the exact paths: frozen harness `runtime-abi-v9-driver-harness.py` 38,279 bytes sha `3738473c...`, plus bundle `libexec\autoreconf`/`autoconf`/`automake`/`aclocal`, `bin\m4.exe`, `tools\make.exe`, `tools\sh.exe`, `runtime\bin\perl.exe`. Sole reviewer of record `8f09cf29...` must independently satisfy the 145-case suite and the 48-step/134-postcondition closure, naming any truly unrunnable step by exact ID, command, and reason. |
| Split `-include` and `-imacros` accept arbitrary sanctioned file content | Non-blocking observation under the explicit V9 contract | Preserve current behavior in the surgical V10 correction; retain the observations for later hardening rather than expanding this request. |
| No FURTHER runtime-ABI authority exists; the V10 GO is CONSUMED | No ABI source edit, ref, commit, PR, stack, or product PASS may exist | The V10 `GO_RUNTIME_ABI_SESSION_START_LOCAL_BUILD_ONLY` was granted and is CONSUMED by session `724ee2e9...`, which completed at its scope boundary. It MUST NOT be reused as authority. Preserve the zero-product state; any new phase needs fresh, explicitly reviewed session_start authority. |
| Runtime, Bash, and recursive ARM64 closure do not exist | Prevents payload completion | Complete runtime stack positions 2-6. |

## Scheduling rules

- A 10-minute supervisor heartbeat checks workers, host utilization, and handoffs.
- A critical worker with no material progress for 15 minutes is nudged or replaced.
- CI, review, and evidence waits do not idle the host when safe artifact-only work is ready.
- Gates restrict source promotion, commit, push, PR, stack, and release admission;
  they do not block bounded local fixtures, baseline builds, or command validation.
- Signing is release-pipeline work for Git for Windows. It is not on the local
  engineering-build critical path.
- `git archive` is NOT LF-safe here: system `core.autocrlf=true` is applied
  during export and `.gitattributes` carries no text/eol rules, so a plain
  `git archive` emits CRLF while stored blobs are LF. Verified on
  `winsup/autogen.sh` at `d890a845`: plain export is 263 bytes / 13 CRLF /
  `eaf4e90f...`, while `git -c core.autocrlf=false archive` is 250 bytes /
  0 CRLF / `4b21ed0f...`. All future identity work must use
  `git -c core.autocrlf=false archive`, or derive identity from stored blob
  bytes via `git cat-file blob`; prefer binding blob OID plus the SHA-256 of
  those blob bytes, which is export-independent. Corrections must record both
  the old and new values rather than silently replacing a recorded identity.
- The autocrlf flag is operation-dependent, so the archive rule must NOT be
  generalised to `git diff`. Because the index is LF and the worktree is CRLF,
  `git diff` needs the repository default normalisation to compare them;
  forcing `core.autocrlf=false` removes it and yields a degenerate whole-file
  patch. Measured on the ABI worktree: default is 29 files / 785 insertions /
  51 deletions, while forced is 29 files / 13,736 insertions / 13,002
  deletions. Use the flag when exporting bytes, never when comparing against
  the index.
- An unvalidated patch artifact is not evidence. Write patches with
  `git diff --output=<file>` and never pipe patch text through the PowerShell
  pipeline, which silently collapsed one backup to a single line with zero
  changed lines. Validate by round-trip or at minimum
  `git apply --check --reverse`.
- Session identity: one project session can present several underlying session
  IDs, and cross-session messages may arrive under any of them. Resolve IDs with
  `get_session` or the local session store before concluding a session is
  unknown, foreign, or misattributed; never infer misattribution from absence of
  memory alone. This checkpoint has messaged under `ee27c231...`, `290c9aaf...`,
  and `adeb3cc9...`, and the ABI create-race was a genuine act of this project
  session under a different context rather than an unattributed session.
- Exactly one live independent reviewer may exist per authority version. When a
  version reaches terminal status, every superseded or parallel reviewer for it
  is archived, never deleted, so it cannot wake and emit a competing verdict.

## Goal

Produce the next clean-slate Git for Windows engineering build with a supported runtime path that is native ARM64 end to end: MSYS2 runtime, Bash, Git, HTTPS transport, SSH client, and required tools. The first milestone is a reproducible team handoff artifact, not RTM.

## Current authority boundary

**NO ACTIVE RUNTIME-ABI IMPLEMENTATION VERDICT.** Runtime-generator draft PR
#31 remains open at exact audited head
`d890a845e992638a6f09560efacc26d15b3ffe6a`. The generator layer is frozen.
The existing V6 request root is permanently withdrawn after post-freeze drift.
The distinct V6-R2 sibling remains atomically finalized and exact at manifest
`b3080df1...` and sums `9440faf1...`; its external finalization receipt is
`6134c10d...`. Independent review `a48221b2...` returned terminal
`NO_GO_RUNTIME_ABI_SESSION_START`. V7 also returned terminal NO-GO under review
`0033b760...` and cannot be repaired in place. Explicit user direction
commissioned one V8 request-only successor in a fresh session. That request is
terminal and immutable at content inventory `47a630e7...`, manifest
`05e11550...`, sums `5b6e2e23...`, and external receipt `b3dfdec0...`.
Independent review `8e2bda60...` returned terminal
`NO_GO_RUNTIME_ABI_SESSION_START`; verdict `f14ece13...` binds the direct
`-Wp,`/`-Wa,` forwarding blocker and explicitly records no authorization
receipt. Review manifest `034b988f...`, sums `b15192ec...`, and external
receipt `df69b792...` independently replay. A commissioned V9 sibling closes
the reported forwarding gap and is frozen at content inventory `0c3ef507...`,
verifier mtime inventory `efa9ae5e...`, immutability inventory `193a842c...`,
manifest `61b1cb5c...`, and sums `1d84f06f...`. The corrected external receipt
SHA is `7096d19c98a7...`; additive reconciliation `ecac32cc...` proves the
earlier `7096d19cd984...` value was a handoff transcription error and the two
mtime hashes differ only by the explicit `readonly` field. Replacement
independent review `522e65c4...` returned terminal
`NO_GO_RUNTIME_ABI_SESSION_START`; verdict `bcdd8d3f...`, manifest
`e52f4433...`, sums `3a8f9853...`, and external receipt `93a4e0ed...`
independently replay. The sole contract violation is comma-field forwarding
through sanctioned `--out-implib`. No implementation authority, product
session, or V10 request is active.
Commit, push, PR,
stack, merge, artifact-admission, and release authority remain separate.

The durable machine-readable tracker is the session `todos`/`todo_deps` graph.
This file, `inbox.md`, and `status.md` must be refreshed in the same continuity
change whenever work starts, completes, blocks, or changes scope.

## Completed foundation history

| Task | Work | Status |
|---|---|---|
| `vnext-verify-quarantine` | Independently replay the old-world quarantine and ambiguous-PR result | Done |
| `vnext-resolve-binutils-receipt-seal` | Seal a new replay for the aggregate embedded-receipt timestamp defect | Done - new epoch fragment verified |
| `vnext-reconcile-policy-digests` | Map receipts sealed under superseded kickoff digests to the final policy | Done - strict v2 reconciliation verified |
| `vnext-supplement-build-extra-boundary` | Add omitted PR #2, 1,612 artifacts, releases, and assets to new sealed evidence | Done - independently replayed |
| `vnext-supplement-runtime-boundary` | Add omitted PR #20, 823 artifacts, releases, refs, and evidence to new sealed evidence | Done - corrected files verified |
| `vnext-refresh-mingw-clean-base` | Fetch canonical upstream in isolated storage and prove local identity/ancestry | Done - exact identity proven |
| `vnext-resolve-busybox-runtime-edge` | Decide whether BusyBox is required, control-only, optional, or deferred | Done - one fresh layer required now |
| `vnext-decide-runtime-linker-path` | Prove LLVM/LLD-only MVP feasibility or require binutils/GCC producers | Done - LLVM/LLD first, conditional fallback |
| `vnext-decide-gcc-provenance` | Admit an exact compiler or select the two-layer GCC path | Done - GCC deferred behind LLVM fallback |
| `vnext-decide-packages-critical-path` | Prove package layers are required by the first artifact or defer them | Done - entire repo deferred |
| `vnext-decide-bootstrap-critical-path` | Prove bootstrap/Gettext layers are required by the first artifact or defer them | Done - entire repo deferred |
| `vnext-decide-packaging-critical-path` | Separate engineering-artifact construction from later admission authority | Done - two pre-artifact layers |
| `vnext-collect-boundary-fragments` | Collect canonical sealed JSON from all eight repository owners | Done - strict runtime/index v2 accepted |
| `vnext-maintain-program-tracker` | Keep inbox, plan, structured tasks, and evidence registry synchronized | In progress |
| `vnext-generate-status` | Maintain `arm64-vnext-status.md` from sealed evidence and task state | In progress |
| `vnext-audit-busybox` | Audit `busybox-w32`; determine minimum-artifact need | Done - required bootstrap leaf |
| `vnext-audit-binutils` | Audit `binutils-woarm64` clean base, ancestry, and layers | Done - repo ready after evidence repair |
| `vnext-audit-runtime` | Audit `msys2-runtime` clean base, ancestry, and runtime stack | Done - supplement and graph decisions remain |
| `vnext-audit-gcc` | Audit `gcc-woarm64`, old stack 14, and first-artifact need | Done - conditional producer |
| `vnext-audit-mingw` | Audit `mingw-w64` fork/upstream bases and CRT need | Done - canonical base proven, zero-delta proposal |
| `vnext-audit-packages` | Audit `MSYS2-packages` source and admission layers | Done - two-layer source proposal |
| `vnext-audit-bootstrap` | Audit bootstrap/Gettext lineage and official inputs | Done - repo GO, three-layer stack proposed |
| `vnext-audit-packaging` | Audit packaging/governance and define artifact requirements | Done - clean base GO, boundary supplement required |
| `vnext-build-boundary-manifest` | Create `arm64-vnext-boundary.json` | Done - lossless 127 PRs, 173 commit heads |
| `vnext-build-release-graph` | Create the minimum `arm64-vnext-release-graph.json` | Done - staged nine-node graph |
| `vnext-prove-clean-ancestry` | Produce complete positive/negative ancestry evidence | Done - 173/173 |
| `vnext-define-first-artifact` | Define payload, manifest, attestation, replay, and custody | Done - BusyBox is explicit utility provider |
| `vnext-select-poc-rederivations` | Record accepted facts/tests and rejected POC material | Done |
| `vnext-implement-boundary-verifier` | Implement mechanical checks and negative controls | Done - v2 and 14/14 controls |
| `vnext-define-staged-identity-gates` | Freeze first layers and block each dependent layer until its parent is frozen | Done |
| `vnext-review-phase0` | Independently review frozen Phase 0 outputs and admitted inputs | Done - two independent GO reviews |
| `vnext-phase0-verdict` | Issue aggregate implementation GO/NO-GO | Done - first layers only |

## Remaining implementation backlog

The current critical path above controls execution. This table preserves the
full layer ordering and deferred work.

| Repository / area | Ordered backlog | Status |
|---|---|---|
| BusyBox | `vnext-implement-busybox-tools`; later `vnext-remove-busybox-bootstrap-dependency` | Draft PR #4; frozen audited head |
| binutils | Native `windmc` capability; conditional source/hardening stack only if broader GNU/BFD behavior is required | Reproducible local AA64 `windmc.exe` PASS and hash-pinned for engineering use; signing deferred; broader source stack on HOLD |
| MSYS2 runtime | `vnext-implement-runtime-generator` -> `vnext-implement-runtime-abi` -> `vnext-implement-runtime-linker` -> `vnext-implement-runtime-signal-tls` -> `vnext-implement-runtime-mvp` -> `vnext-implement-runtime-fork-exec`; post-handoff utilities and `vnext-implement-runtime-cpu-topology` | Generator draft PR #31 exact/open; V6-R2, V7, V8, and V9 preserved under terminal NO-GO; argument contract matrix active; ABI source work not started |
| GCC | zero layers with admitted compiler, otherwise `vnext-implement-gcc-foundations` -> `vnext-implement-gcc-preflight`; `vnext-implement-gcc-seh` post-MVP | **HOLD** unless LLVM/LLD fallback activates |
| mingw-w64 | `vnext-implement-mingw-source` | **HOLD**; canonical source is currently zero-delta |
| MSYS2 packages | `vnext-implement-packages-bdb` -> `vnext-implement-packages-locators` -> conditional admission | Deferred until self-hosting/package-native/RTM |
| Bootstrap/Gettext | `vnext-implement-bootstrap-foundation` -> `vnext-implement-gettext` -> `vnext-implement-boundary-diagnostics` | Deferred until self-hosting/NLS/RTM |
| Packaging | Pre-artifact: `vnext-implement-packaging-foundation` -> `vnext-implement-packaging-payload`; post-handoff: checks -> governance -> protection | Ownership/SDK draft PR #29; P5 external inputs 34/34 and graph 73/80; seven node-produced placeholders remain |

## Integration and handoff backlog

| Task | Deliverable | Status |
|---|---|---|
| `vnext-build-first-artifact` | Epoch-named native ARM64 Git for Windows engineering archive and complete manifest | Harness ready; all 34 external inputs resolved; blocked on runtime top and seven produced outputs |
| `vnext-rebuild-process-attestor` | Epoch-native attestor; old executable is oracle only | Done - native ARM64 artifact audited |
| `vnext-admit-llvm-toolchain-inputs` | Exact official LLVM/LLD/Make/Perl/package and executable identities | Done - engineering epoch lock |
| `vnext-admit-bootstrap-generator-inputs` | Fresh generator sources/tools and explicit official controls | Done - external inputs admitted |
| `vnext-admit-handoff-payload-inputs` | Exact Bash, Git/HTTPS, OpenSSH, CA/data, and helper provenance | Done - filtered native engineering closure |
| `vnext-protect-runtime-base` | Enable runtime protection after base-controlled checks are observed | Pending runtime stack |
| `vnext-protect-gcc-base` | Enable GCC protection only if GCC enters the MVP graph | Conditional |
| `vnext-replay-first-artifact` | Deterministic recreation and independent fresh moved-extraction replay | Test harness prepared; waits for first complete ZIP |
| `vnext-protect-build-extra-main` | Enable exact admission protection only after base-controlled check observation | Pending governance |
| `vnext-publish-team-handoff` | Artifact, `README-HANDOFF.md`, exact source identity, evidence, and limitations | Pending replay |
| `vnext-build-admitted-artifact` | Fresh superseding artifact after protected base-controlled admission exists | Pending protection |
| `vnext-plan-rtm` | Remaining correctness, protection, governance, and release plan | Pending team handoff |
| `vnext-preserve-reformat-continuity` | Versioned checkpoint PR with exact patch, sealed state, hashes, and portable restart instructions | Draft PR #10 exact/open/mergeable; one unchanged `doc/bfd.info` Error 127 failure and seven queue-time cancellations; no source-causal signal, confirmed 2026-09-03 — the in-repo `makeinfo` stub at `enable-ccache.sh:44` exists but never reaches the build environment |

## First artifact acceptance

Filename: `arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip`

- Native ARM64 `msys-2.0.dll`, Bash, Git, HTTPS transport, SSH, and required supported-path tools.
- No recurring x64 PE dependency on supported paths; controls or one-time emulation must be explicit.
- Local Git, HTTPS, controlled SSH, fork/pipeline/subshell, filesystem, signal, and moved-extraction tests.
- Manifest records path, size, SHA-256, PE machine, source commit/tree, and admitted provenance.
- Native process attestation and deterministic archive recreation.
- Fresh independent replay from a moved extraction.
- `README-HANDOFF.md` and one exact top-of-stack source identity.

## Live execution summary

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
| Native runtime stacks registered | 0 |
| Fresh Git Bash artifacts | 0 |

The earlier `50 done / 6 in progress / 29 pending / 3 blocked` figures described
the sealed Phase 0 task graph at checkpoint time. They are historical and must
not be used as the live execution summary.

</details>
