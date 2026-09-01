# Git for Windows Native ARM64 vNext

Updated: `2026-09-01T01:25:00Z`  
Verdict: **NO ACTIVE VERDICT**

## Top-level requirements

| Requirement | Status | Current position |
|---|---|---|
| Old programme quarantined | PASS | 122 open old PRs visibly quarantined |
| Clean source boundary | PASS | 127 old PRs, 348 denied refs, 173 denied heads |
| Clean base ancestry | PASS | 173/173 explicit checks |
| External build inputs | PASS for engineering scope | Every modeled node requirement admitted |
| Native BusyBox tools | DRAFT PR #4 | Two successful build checks |
| Native MSYS2 runtime | DRAFT PR #31 | 3 checks passed; 8 running |
| Native Bash | PENDING | Runtime MVP layer |
| Native Git and HTTPS | INPUT READY | Filtered ARM64 Git/Schannel closure |
| Native SSH | INPUT READY | Windows inbox ARM64 OpenSSH by reference |
| Ownership/provenance | DRAFT PR #29 | 1 success, 4 skipped; diagnostic only |
| Native process attestor | AUDIT PASS | ARM64 artifact `73777a4c…` |
| First Git Bash ZIP | NOT BUILT | Waits for runtime top and payload layer |
| Independent artifact replay | NOT STARTED | Waits for first ZIP |
| Release admission | NOT STARTED | Post-handoff work |
| Reformat continuity | DRAFT PR #10 | Remote exact-byte checkpoint; cloud verification active |

## Current work

| Work | Branch | PR | Session | Status |
|---|---|---:|---|---|
| BusyBox bootstrap tools | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | #4 | `4a203e57-e1e1-4c9f-a7fe-ad86d2c49149` | Draft; 2 successful checks |
| Ownership/SDK and attestor | `crutkas-arm64-vnext/build-extra/ownership-sdk` | #29 | `4605a44f-0643-4f66-b8d4-f85d0e119c60` | Draft; 1 pass / 4 skipped |
| Runtime generators | `crutkas-arm64-vnext/msys2-runtime/generator` | #31 | `76313824-571e-409c-b873-5eec261545ce` | Draft; exact frozen head |
| Reformat checkpoint | `crutkas-arm64-vnext/msys2-woarm64-build/reformat` | #10 | `dae16354-b5f6-4db5-9026-916a0fb3b03c` | Remote; cloud handoff verifying |

Runtime PR authority is consumed. PR #31 is exact, draft, and uniquely bound. **Review, stack, merge, artifact, and release authority remain blocked.**

## PRs and stacks

Four vNext PRs exist: three product PRs and one continuity checkpoint. No vNext native stack exists yet.

### BusyBox leaf

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| Leaf | #4 | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | Native bootstrap shell and 31 supported applets | Clean `main` | Draft; 2 successful checks |

### MSYS2 runtime stack

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| 1 | #31 | `crutkas-arm64-vnext/msys2-runtime/generator` | Fresh native generators | BusyBox leaf | Draft; 3 pass / 8 running |
| 2 | — | `crutkas-arm64-vnext/msys2-runtime/abi` | ARM64 ABI and startup foundation | Generator | Blocked |
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
| #10 | `crutkas/msys2-woarm64-build` | `d27a45a` / tree `6e102e7` | Exact authorities, runtime patch, sealed state, and restart procedure | Draft; cloud verification active |

## Work pending

| Priority | Work | Unblocked by |
|---:|---|---|
| 1 | Monitor PR #4 checks and code review | Draft PR |
| 1 | Monitor PR #29 checks and code review | Draft PR |
| 1 | Complete cloud verification of continuity PR #10 | Remote exact-byte checkpoint |
| 1 | Monitor PR #31 checks and code review | Draft PR |
| 2 | Update reformat checkpoint with final runtime identity | Exact PR readback |
| 7 | Build runtime stack positions 1–6 | Each lower layer frozen |
| 8 | Build payload layer | Runtime top + ownership layer |
| 9 | Produce Git Bash MVP ZIP | Payload head |
| 10 | Independently replay moved extraction | MVP ZIP |
| 11 | Publish non-admitted engineering handoff | Replay pass |
| 12 | Add aggregate checks and protected governance | First handoff |

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
| Parallel builds | Use `-j20` or equivalent; record timing and failures |

## Programme state

| Item | Count |
|---|---:|
| Tasks done | 50 |
| Tasks in progress | 6 |
| Tasks pending | 29 |
| Conditional tasks blocked | 3 |
| Verified evidence records | 109 |
| Superseded evidence retained | 25 |
| Rejected evidence retained | 22 |
| Open vNext PRs | 4 |
| Created vNext stacks | 0 |
| Fresh Git Bash artifacts | 0 |

## Current authority

| Authority | SHA-256 |
|---|---|
| Boundary | `97ce5396ff9f581c02f7207413d9803dbd219f6fa1764c87e73f2b1c4ed7b68d` |
| Release graph | canonical revision 12 `8ac61bcb3aa71ac15065e5bb5b72ece8269c2a24399942efee6a39e6b3ea2605` |
| Input provenance | `9f4ed99e12d67ef026eb7fb85c783edc9d8211a1ea80f5447e3a7dd3e1a00999` |
| Branch amendment | `e477de0e24d84c40843a887a0b5b2268257e6373faa1c22ea6490227fdc93a8c` |
| Amendment review | `61ef7605fa913895566c9cd60cf702148dcd4128340e5e1a7f495c46a91c3848` |
| Staged verdict | None active; runtime PR authority consumed |

Machine truth: `arm64-vnext-release-graph.json`, `arm64-vnext-boundary.json`, task database, evidence registry, and live API readback.
