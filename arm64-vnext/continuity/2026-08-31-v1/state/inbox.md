# ARM64 vNext Inbox

Epoch: `2026-08-31-v1`  
Last updated: `2026-08-31T23:18:00Z`

This inbox tracks incoming audit reports, newly discovered work, blockers, and decisions. Items are triaged into `plan.md` and the durable `vnext-*` task graph.

## Awaiting reports

| Repository | Session | Expected input | State |
|---|---|---|---|
| BusyBox draft PR #4 | `4a203e57-e1e1-4c9f-a7fe-ad86d2c49149` | Live checks and review at frozen head `942be1c` | Two successful build checks |
| Ownership/SDK draft PR #29 | `4605a44f-0643-4f66-b8d4-f85d0e119c60` | Live checks and review at frozen head `305d14d` | One success; four skipped |
| Runtime generator implementation | `76313824-571e-409c-b873-5eec261545ce` | Fresh generator layer from clean runtime base | Three paths staged at corrected tree `43aec2e`; bundle build running |
| Reformat continuity checkpoint | `eeb19970-7a05-44f6-8f8e-3b3de0ca2d9c` | Versioned off-machine state and restart procedure | Publishing on accepted app-native branch `.../reformat` |

## Latest authoritative snapshot

- Canonical release graph revision 8 is SHA-256 `5d581d49b1ed3df931cd63048058bb8da9760f5c900698d49e6b6e05a601695a`.
- Exactly two vNext PRs are open: `crutkas/busybox-w32#4` and `crutkas/build-extra#29`; both are draft, uniquely bound to their reviewed heads, labeled only `arm64-vnext`, and have no queue, auto-merge, review request, or stack membership.
- Runtime-generator is clean at commit `8fbd9808447ee78ed485deead9b79cd1e40c07b7`, tree `fe1106187ef9aa842e1cff0ccc4f978b65c16613`, on `crutkas-arm64-vnext/msys2-runtime/generator`.
- Runtime-generator external requirements are admitted. Fresh ARM64 M4, Sprut, Shilka, Autotools outputs, and `devices.cc` replay are node outputs, not pre-existing external inputs. Fresh BusyBox is the exact release-graph dependency.
- Independent session-start review v2 correctly returned NO-GO on a revision-7 hash transcription and issuer-incompatible live fields. Both coordinator artifacts are repaired and a fresh replacement review is active; the rejected review remains preserved.
- Runtime-generator session-start verdict `f13ec4e688f5f9c5e9c4de38c4fdb1174b6795c81acc00e2edd31d81c8bdf9f1` and strict authorization receipt `48ade7bd7ed52ec93692df5744875607a32399e310fb778cefeeea76923d8e30` permit clean investigation, implementation, and local candidate-output production only. Hard stop before commit.
- Runtime source candidate currently changes exactly `winsup/autogen.sh`, `winsup/tests/autogen-contract.sh`, and `.github/workflows/build.yaml`. Hosted MSYS and exact native BusyBox contract tests pass; `git diff --cached --check` passes; staged tree is `43aec2ed8555b6f4a9866ae4b8605972062dff6d`. The provisional `092bb2b` tree is superseded after correcting an index-only workflow executable-mode error; `.github/workflows/build.yaml` is restored to mode `100644`. Fresh ARM64 generator-bundle build and reproducibility evidence remain in progress.
- Independent source preaudit `cb76badf249ea5b2844b5fab608072edb90cc00f3a949959c0cba112e0bbd71b` passes with zero blockers and grants no commit authority. Final review still requires the generator bundle, 10-output replay, provenance/process/PE/import/module records, and two-build byte reproducibility evidence.
- Emergency runtime continuity is frozen as exact patch `0f2f3f9dfc7509d1d240f81a44a4c1700032478c51ff89d769a14c4b5ca022d8`, sealed state ledger `6ff2bcc368087070a9070729e2ea888b6f466eafbffb8c083db8f2a23cd58b69`, and local replay archive `e5113678ade3f4e79a63b473eafe55e164839a06dba20d8f8cf3a63996e6ffc1`. The patch and ledger are being committed to a dedicated continuity draft PR; the 135 MB archive remains a local fallback and is reproducible from admitted inputs.

## Coordinator work

| Item | State | Next action |
|---|---|---|
| Independently replay `arm64-old-world-quarantine.json` | Active | Verify aggregate seal, per-repository receipts, and ambiguous-PR result |
| Maintain task graph, inbox, and plan | Active | Update on every report, blocker, decision, or status transition |
| Reconcile superseded kickoff digests in sealed receipts | Active | Preserve old receipts and issue a new epoch mapping to the final policy |
| Complete omitted build-extra forbidden inventory | Done | Two supplemental files independently rehashed and replayed |
| Complete omitted runtime forbidden inventory | Done | Corrected epoch-named fragment and 823-artifact ledger verified |
| Resolve BusyBox dependency | Done | Fresh bootstrap-tools layer is required now; permanent dependency deferred |
| Collect normalized owner fragments | Done | All eight fragments and sealed index independently verified |
| Generate boundary, graph, ancestry, POC ledger, and artifact contract | Reopened | v1 preserved; v2 fixes head overbreadth, utility edge, and staged identities |
| Implement mechanical boundary verifier | Reopened | v1 rejected as fail-open; v2 requires source equality and authoritative readback |
| Verify real first-layer session starts | Rejected | v1 receipts omitted invocation and complete object-coverage evidence |
| Maintain authoritative status | Active | Keep `arm64-vnext-status.md`, this inbox, and `plan.md` synchronized |

## Triaged

### `crutkas/busybox-w32`

- Report received from session `b6e4a22b-4030-4c25-9f1c-63985633cbeb`.
- Repository Phase 0 verdict: **GO**.
- Clean base: commit `d8d8bb397f1e200ba5a871dc6aa4af819b23f32a`, tree `37fb55f5335e63c9f14c44208ed08a6e9aad4f91`.
- Quarantine and receipt seals matched; ambiguous open ARM64 PR count is zero.
- A fresh `busybox-w32/bootstrap-tools` layer is **required for the current first artifact** because it supplies the native bootstrap shell/core applets and current command payload.
- BusyBox is not a permanent product dependency; replacement with native runtime/package tools is post-handoff backlog.
- Old BusyBox commits, branches, workflow artifacts, and binary hashes remain forbidden inputs and reference-only evidence.

### `crutkas/msys2-woarm64-build`

- Report and correction received from session `02dddb73-7cc1-42bd-84b0-5c91974bb175`.
- Repository Phase 0 verdict: **GO**.
- Clean base: commit `77f0d56cdf4c063c1b3af37f551e01c3a012c8bb`, tree `a031061a532b57adf447fcb7df478d9b37a071a6`.
- Quarantine replay passed; ambiguous open ARM64 PR count is zero.
- Old native stack `8`, the stale Gettext edge, all non-main refs, 16 old/candidate heads, synthetic merge commits, workflows, and 39 Actions artifacts are forbidden. Exactly five artifacts remain unexpired; expiration does not change the deny.
- Proposed new stack: `bootstrap-foundation` -> `gettext-source-build` -> `protected-boundary`.
- Implementation remains blocked on exact admitted GCC/binutils identities, package-recipe identities, official Gettext/libiconv sources and digests, and downstream runtime/packaging identities.

### `crutkas/binutils-woarm64`

- Report received from session `b2500699-4946-421b-a30e-1208d18239d5`.
- Repository technical verdict: **GO after Phase 0 evidence repair**.
- Clean base: commit `44335833f8f734f978211b082b15aed14efcf958`, tree `1164c74fe058fd8a561ee16670e674562649b5f8`.
- Live quarantine, zero-ambiguity query, and all old-head ancestry exclusions pass.
- The exact source applied receipt and its payload seal pass. The aggregate embedded copy changed three timestamp spellings and does not replay its declared payload seal.
- Proposed new stack: `source` -> `hardening-tests`. Build evidence is an epoch artifact by default, not a third source PR.
- The exact cross-repository consumer edges remain to be established by the aggregate release graph.

### `crutkas/mingw-w64`

- Report and clean-base follow-up received from session `4df7471a-2de2-4f43-a000-bfb897e17ce2`.
- Visible quarantine passes with the sealed `viewerCanLabel=false` exception for upstream PR #184.
- Canonical upstream base `6df76fa527c36e770217ddd763adaaf37bd2887f`, tree `c1a129a1537210b8decf2f8292338526684435af`, is now independently present and verified in isolated storage with no final live drift.
- Both old heads are excluded from canonical-base ancestry.
- The applied receipt seals against a superseded kickoff digest and must be reconciled by new vNext evidence.
- Current minimum-MVP proposal is zero mingw source delta. Workflow-pin maintenance is separate and not on the first-artifact critical path.

### `crutkas/MSYS2-packages`

- Report and corrected PR #22 identity received from session `6105ed30-3b5e-4e9a-8ad1-5f2e94f72893`.
- Clean base: commit `73248abe6bc25e73486c29f876094b3eeab79547`, tree `fed85f3aa739acc838617b2561c81147a70ac9ad`.
- Quarantine and all ancestry controls pass.
- Exact deny inventory includes 45 PRs, three old stacks, 21 releases, 106 release assets, and 451 relevant live workflow artifacts.
- Proposed MVP stack: `berkeley-db-c23` -> `bounded-source-locators`. Admission policy is separate and conditional.
- Base-controlled admission remains unavailable because `master` is unprotected and no independent code owner exists.
- Minimum-DAG review found no exact first-artifact dependency. The entire package stack is deferred to self-hosting, package-native builds, or RTM.

### `crutkas/gcc-woarm64`

- Report received from session `2877160a-3fdb-4cad-90d6-c173b8d04eb0`.
- Clean base: commit `5688a17320e775944bbe795010ebe7e89fc7a628`, tree `fbab8c5cc25083a857a15bb1240879497da66b02`.
- Quarantine and all old-head ancestry exclusions pass; old stacks `8` and `14` remain forbidden.
- GCC contributes zero layers only if an exact official MSYS-target compiler is admitted. Otherwise the minimum is `runtime-foundations` -> `c-bootstrap-preflight`.
- Extended SEH, C++, libffi, LTO/plugins, and generic plugin argv handling are post-MVP or explicitly blocked.
- The first path now selects admitted LLVM/LLD and defers GCC; the two-layer GCC path remains the explicit fallback.

### `crutkas/msys2-runtime`

- Report, corrected fragment, and exact 823-artifact ledger received from session `2c5e9beb-2617-4e37-a8e0-b835010b6205`.
- Clean base: commit `8fbd9808447ee78ed485deead9b79cd1e40c07b7`, tree `fe1106187ef9aa842e1cff0ccc4f978b65c16613`.
- Quarantine and ancestry pass. Closed PR #20, expanded refs/heads, two releases, and all 823 artifact IDs require new sealed evidence.
- Proposed MVP stack: `generator` -> `abi` -> `linker-import` -> `signal-tls` -> `mvp` -> `fork-exec`.
- Utilities and CPU topology are deferred. LLVM/LLD is the selected first path; binutils/GCC become fallbacks if required behavior fails.
- Initial non-epoch/insertion-order evidence remains rejected and unchanged. Corrected epoch-named files independently replay.

### `crutkas/build-extra`

- Report and sealed supplemental evidence received from session `0f21bfbc-b7ec-472c-98fa-cf80e4ccc1ad`.
- Clean base passes at commit `7acc5756b94a0a0ab8d0cd06642c8c8254e1bf40`, tree `08e34404480e5fd67cfdbce904a09e5a35c49871`.
- The aggregate omitted closed/unmerged old ARM64 PR #2, 1,612 Actions artifacts, two ARM64 releases, and their assets. Embedded source seals also fail after timestamp reserialization.
- Proposed stack: `ownership-sdk` -> `payload` -> `aggregate-check` -> `governance`.
- Exact first artifact: `arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip`.
- `main` currently has no protection or ruleset; protection must follow merged base-controlled checks and observation on a fresh harmless PR.
- Supplemental boundary file SHA-256 `a253025ce6f3dd8c1e51834c5a164526b95e42fc0f13695a17b7bd151a60f676`; 1,612-artifact ledger SHA-256 `b0fb454762368f5d6e27e8b287ee1c217eb0a203b4d27c3b404d53eb1c3ef7f6`. Both payload seals replay independently.
- Minimum-DAG review permits `ownership-sdk` -> `payload` -> artifact -> independent replay as a loudly **NON-ADMITTED ENGINEERING HANDOFF**. Aggregate checks, governance, protection, and a fresh superseding artifact follow before any authority claim.

## Decisions and blockers

- Product implementation remains **NO-GO** until the aggregate Phase 0 boundary, release graph, ancestry report, verifier, artifact contract, and independent review pass.
- Independent review SHA-256 `eb3777a9a2b69324439ed1876db6d75038e632e3e532a6cfc3a86c558e113ff1` found four blockers: fail-open verifier, incomplete ancestry coverage, contradictory utility ownership, and unfrozen source/input identities.
- The v1 `300`-head boundary was overbroad. The corrected model retains all `348` denied branch-ref records but only `173` actual POC/candidate commit heads.
- Payload ledger v2 SHA-256 `857984d61f37862eb0ada5c92bb21699e301c5a861c65c8abe3829978cb33f7b` selects 31 files with 15 ARM64 PEs, 16 data files, and zero x64/x86/ARM64EC/unknown PE.
- Public HTTPS uses Schannel with GCM disabled; trust uses the selected Windows store; SSH uses inbox ARM64 OpenSSH by reference with artifact-owned bounded configuration.
- Final consolidated provenance SHA-256 `ad691d7d5683d5caee6ffb7abbb5c430eabb492cfc5d52ca01bbb5453579972a`: 184 records, 174 admitted, five blocked exclusions, five reference-only, and every required node group admitted.
- Final staged v2 boundary, graph, ancestry, artifact definition, 14 controls, and strict BusyBox/build-extra diagnostics all pass; independent re-review is active.
- `vnext-resolve-binutils-receipt-seal` is active. Old evidence stays unchanged; the resolution is a new sealed vNext replay referencing the exact source receipt and live state.
- BusyBox dependency reconciliation is complete: one fresh layer is in the minimum graph; old BusyBox commits and archives remain forbidden.
- Package and bootstrap critical-path decisions are complete: both repositories have zero first-artifact nodes.
- LLVM/LLD is the first runtime linker/compiler path. GCC and binutils remain explicit fallback paths only.
- `vnext-collect-boundary-fragments` and `vnext-reconcile-policy-digests` are active.
- Verified owner fragments currently exist for binutils, runtime, GCC, mingw-w64, MSYS2-packages, bootstrap, and build-extra.
- Coordinator quarantine replay SHA-256: `f68df17b1d7945f667885291240773207b0f53481e061f504131423953e1f020`; it proves all 16 referenced source files hash correctly and records 44 lexical differences across seven embedded copies.
- Boundary/release/verifier v1 hashes remain preserved as rejected or superseded evidence; do not use them for writer authorization.
- Final boundary SHA-256 `db1fe7fb9dcc133e637d9fb7d53ec4c37236c026c0941cddb58d274ff55e4439`.
- Final graph SHA-256 `101e58d029b1e3d21269adbf68624fd6e8fdaf74b57c2dd90f6fdc7430478509`.
- Independent review SHA-256 `583709d37676f7a9e3163dd38403f939224e79c138d6e453b51051a61d333281`; corroborating review `e524bfc563c8cf3d71c71fb0936243920acda078ce4609a8fd7c80c95175c57e`.
- Phase 0 verdict SHA-256 `8dede4ade80cfa9b17366a7ec521803d2e79d5adc5dd68d382c0269a5c5aab25`.
- Only BusyBox and build-extra ownership may edit and commit. Neither may push or open a PR until a new graph and authorization are sealed.
- That authorization is temporarily invalidated. Both sessions proved exact clean bases, then stopped because app-native rename enforced `crutkas-`; no source edits or commits exist.
- Amendment SHA-256 `e477de0e24d84c40843a887a0b5b2268257e6373faa1c22ea6490227fdc93a8c` is independently reviewed.
- Amendment review SHA-256 `61ef7605fa913895566c9cd60cf702148dcd4128340e5e1a7f495c46a91c3848` passes with no blockers.
- Replacement verdict SHA-256 `67b8b06d4a051998c2d64a7b65c526378c751c53f6e049743c98e8195b4adcc9`.
- Actual branch authorizations: BusyBox `e7107b1d41f59a056a68dab1f9161daf93babfa9280f23bce8b4f595664dea34`; build-extra `dbb8ea5294015f03a705c5440aa179f000c871aecb64550f06ec39830785ac33`.
- No old-world object may be mutated or consumed as a vNext build input.
- Any newly discovered task must receive a `vnext-*` ID before work begins.
