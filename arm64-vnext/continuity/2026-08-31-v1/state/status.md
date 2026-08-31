# Git for Windows Native ARM64 vNext

Updated: `2026-08-31T23:18:00Z`  
Verdict: **GO — RUNTIME-GENERATOR SESSION START ONLY**

## Top-level requirements

| Requirement | Status | Current position |
|---|---|---|
| Old programme quarantined | PASS | 122 open old PRs visibly quarantined |
| Clean source boundary | PASS | 127 old PRs, 348 denied refs, 173 denied heads |
| Clean base ancestry | PASS | 173/173 explicit checks |
| External build inputs | PASS for engineering scope | Every modeled node requirement admitted |
| Native BusyBox tools | DRAFT PR #4 | Two successful build checks |
| Native MSYS2 runtime | BUILDING GENERATOR BUNDLE | Source preaudit passed; final evidence pending |
| Native Bash | PENDING | Runtime MVP layer |
| Native Git and HTTPS | INPUT READY | Filtered ARM64 Git/Schannel closure |
| Native SSH | INPUT READY | Windows inbox ARM64 OpenSSH by reference |
| Ownership/provenance | DRAFT PR #29 | 1 success, 4 skipped; diagnostic only |
| Native process attestor | AUDIT PASS | ARM64 artifact `73777a4c…` |
| First Git Bash ZIP | NOT BUILT | Waits for runtime top and payload layer |
| Independent artifact replay | NOT STARTED | Waits for first ZIP |
| Release admission | NOT STARTED | Post-handoff work |
| Reformat continuity | PUBLISHING | Patch and sealed state exported; checkpoint PR in progress |

## Current work

| Work | Branch | PR | Session | Status |
|---|---|---:|---|---|
| BusyBox bootstrap tools | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | #4 | `4a203e57-e1e1-4c9f-a7fe-ad86d2c49149` | Draft; 2 successful checks |
| Ownership/SDK and attestor | `crutkas-arm64-vnext/build-extra/ownership-sdk` | #29 | `4605a44f-0643-4f66-b8d4-f85d0e119c60` | Draft; 1 pass / 4 skipped |
| Runtime generators | `crutkas-arm64-vnext/msys2-runtime/generator` | — | `76313824-571e-409c-b873-5eec261545ce` | Source preaudit pass; bundle build running |
| Reformat checkpoint | `crutkas-arm64-vnext/msys2-woarm64-build/reformat` | — | `eeb19970-7a05-44f6-8f8e-3b3de0ca2d9c` | Publishing exact state to draft PR |

Both first-layer PR authorities are consumed. Runtime-generator may investigate, implement, and produce local candidate outputs only. **Commit, push, PR, artifact-construction, and release authority remain blocked.**

## PRs and stacks

Two vNext PRs exist. No vNext native stack exists yet.

### BusyBox leaf

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| Leaf | #4 | `crutkas-arm64-vnext/busybox-w32/bootstrap-tools` | Native bootstrap shell and 31 supported applets | Clean `main` | Draft; 2 successful checks |

### MSYS2 runtime stack

| Position | PR | Branch | Purpose | Depends on | Status |
|---:|---:|---|---|---|---|
| 1 | — | `crutkas-arm64-vnext/msys2-runtime/generator` | Fresh native generators | BusyBox leaf | 3 paths staged at corrected tree `43aec2e` |
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

## Work pending

| Priority | Work | Unblocked by |
|---:|---|---|
| 1 | Monitor PR #4 checks and code review | Draft PR |
| 1 | Monitor PR #29 checks and code review | Draft PR |
| 1 | Publish reformat continuity checkpoint | Exact patch and sealed ledger exported |
| 2 | Implement runtime-generator candidate and local outputs | Session-start authority |
| 3 | Independently audit frozen staged tree before commit | Candidate completion |
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
| Tasks done | 49 |
| Tasks in progress | 6 |
| Tasks pending | 29 |
| Conditional tasks blocked | 3 |
| Verified evidence records | 66 |
| Superseded evidence retained | 22 |
| Rejected evidence retained | 14 |
| Open vNext PRs | 2 |
| Created vNext stacks | 0 |
| Fresh Git Bash artifacts | 0 |

## Current authority

| Authority | SHA-256 |
|---|---|
| Boundary | `97ce5396ff9f581c02f7207413d9803dbd219f6fa1764c87e73f2b1c4ed7b68d` |
| Release graph | canonical revision 8 `5d581d49b1ed3df931cd63048058bb8da9760f5c900698d49e6b6e05a601695a` |
| Input provenance | `9f4ed99e12d67ef026eb7fb85c783edc9d8211a1ea80f5447e3a7dd3e1a00999` |
| Branch amendment | `e477de0e24d84c40843a887a0b5b2268257e6373faa1c22ea6490227fdc93a8c` |
| Amendment review | `61ef7605fa913895566c9cd60cf702148dcd4128340e5e1a7f495c46a91c3848` |
| Staged verdict | Runtime-generator `session_start` only: `f13ec4e688f5f9c5e9c4de38c4fdb1174b6795c81acc00e2edd31d81c8bdf9f1` |

Machine truth: `arm64-vnext-release-graph.json`, `arm64-vnext-boundary.json`, task database, evidence registry, and live API readback.
