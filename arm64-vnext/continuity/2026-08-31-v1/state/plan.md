# Git for Windows Native ARM64 vNext Plan

Epoch: `2026-08-31-v1`  
Last updated: `2026-09-01T01:25:00Z`

## Goal

Produce the next clean-slate Git for Windows engineering build with a supported runtime path that is native ARM64 end to end: MSYS2 runtime, Bash, Git, HTTPS transport, SSH client, and required tools. The first milestone is a reproducible team handoff artifact, not RTM.

## Current gate

**NO ACTIVE VERDICT.** Runtime-generator draft PR #31 is open at exact audited head `d890a845e992638a6f09560efacc26d15b3ffe6a`, labeled only `arm64-vnext`; checks are running and no review/stack/merge authority exists. The effective physical prefix is `crutkas-arm64-vnext/`; logical programme namespace remains `arm64-vnext/`.

The durable machine-readable tracker is the session `todos`/`todo_deps` graph. This file and `inbox.md` are updated whenever work starts, completes, blocks, or changes scope.

## Phase 0

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

## Provisional implementation backlog

These layers are backlog, not authorization to start. Phase 0 will remove unnecessary layers and set exact same-repository stacks and cross-repository dependencies.

| Repository / area | Ordered backlog | Status |
|---|---|---|
| BusyBox | `vnext-implement-busybox-tools`; later `vnext-remove-busybox-bootstrap-dependency` | Draft PR #4; frozen audited head |
| binutils | `vnext-implement-binutils-source` -> `vnext-implement-binutils-hardening`; `vnext-capture-binutils-evidence` only if workflow source changes | **HOLD** unless LLVM/GNU behavior requires fallback |
| MSYS2 runtime | `vnext-implement-runtime-generator` -> `vnext-implement-runtime-abi` -> `vnext-implement-runtime-linker` -> `vnext-implement-runtime-signal-tls` -> `vnext-implement-runtime-mvp` -> `vnext-implement-runtime-fork-exec`; post-handoff utilities and `vnext-implement-runtime-cpu-topology` | Generator draft PR #31 exact/open; checks running; later layers blocked |
| GCC | zero layers with admitted compiler, otherwise `vnext-implement-gcc-foundations` -> `vnext-implement-gcc-preflight`; `vnext-implement-gcc-seh` post-MVP | **HOLD** unless LLVM/LLD fallback activates |
| mingw-w64 | `vnext-implement-mingw-source` | **HOLD**; canonical source is currently zero-delta |
| MSYS2 packages | `vnext-implement-packages-bdb` -> `vnext-implement-packages-locators` -> conditional admission | Deferred until self-hosting/package-native/RTM |
| Bootstrap/Gettext | `vnext-implement-bootstrap-foundation` -> `vnext-implement-gettext` -> `vnext-implement-boundary-diagnostics` | Deferred until self-hosting/NLS/RTM |
| Packaging | Pre-artifact: `vnext-implement-packaging-foundation` -> `vnext-implement-packaging-payload`; post-handoff: checks -> governance -> protection | Ownership/SDK draft PR #29; attestor complete |

## Integration and handoff backlog

| Task | Deliverable | Status |
|---|---|---|
| `vnext-build-first-artifact` | Epoch-named native ARM64 Git for Windows engineering archive and complete manifest | Pending implementation |
| `vnext-rebuild-process-attestor` | Epoch-native attestor; old executable is oracle only | Done - native ARM64 artifact audited |
| `vnext-admit-llvm-toolchain-inputs` | Exact official LLVM/LLD/Make/Perl/package and executable identities | Done - engineering epoch lock |
| `vnext-admit-bootstrap-generator-inputs` | Fresh generator sources/tools and explicit official controls | Done - external inputs admitted |
| `vnext-admit-handoff-payload-inputs` | Exact Bash, Git/HTTPS, OpenSSH, CA/data, and helper provenance | Done - filtered native engineering closure |
| `vnext-protect-runtime-base` | Enable runtime protection after base-controlled checks are observed | Pending runtime stack |
| `vnext-protect-gcc-base` | Enable GCC protection only if GCC enters the MVP graph | Conditional |
| `vnext-replay-first-artifact` | Deterministic recreation and independent fresh moved-extraction replay | Pending artifact |
| `vnext-protect-build-extra-main` | Enable exact admission protection only after base-controlled check observation | Pending governance |
| `vnext-publish-team-handoff` | Artifact, `README-HANDOFF.md`, exact source identity, evidence, and limitations | Pending replay |
| `vnext-build-admitted-artifact` | Fresh superseding artifact after protected base-controlled admission exists | Pending protection |
| `vnext-plan-rtm` | Remaining correctness, protection, governance, and release plan | Pending team handoff |
| `vnext-preserve-reformat-continuity` | Versioned checkpoint PR with exact patch, sealed state, hashes, and portable restart instructions | Draft PR #10 remote; cloud verification active |

## First artifact acceptance

Filename: `arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip`

- Native ARM64 `msys-2.0.dll`, Bash, Git, HTTPS transport, SSH, and required supported-path tools.
- No recurring x64 PE dependency on supported paths; controls or one-time emulation must be explicit.
- Local Git, HTTPS, controlled SSH, fork/pipeline/subshell, filesystem, signal, and moved-extraction tests.
- Manifest records path, size, SHA-256, PE machine, source commit/tree, and admitted provenance.
- Native process attestation and deterministic archive recreation.
- Fresh independent replay from a moved extraction.
- `README-HANDOFF.md` and one exact top-of-stack source identity.

## Current totals

`50 done` · `6 in progress` · `29 pending` · `3 blocked`
