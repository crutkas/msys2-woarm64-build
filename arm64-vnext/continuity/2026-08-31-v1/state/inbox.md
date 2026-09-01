# ARM64 vNext Inbox

Epoch: `2026-08-31-v1`  
Last updated: `2026-09-01T01:25:00Z`

This inbox tracks incoming audit reports, newly discovered work, blockers, and decisions. Items are triaged into `plan.md` and the durable `vnext-*` task graph.

## Awaiting reports

| Repository | Session | Expected input | State |
|---|---|---|---|
| BusyBox draft PR #4 | `4a203e57-e1e1-4c9f-a7fe-ad86d2c49149` | Live checks and review at frozen head `942be1c` | Two successful build checks |
| Ownership/SDK draft PR #29 | `4605a44f-0643-4f66-b8d4-f85d0e119c60` | Live checks and review at frozen head `305d14d` | One success; four skipped |
| Runtime generator draft PR #31 | `76313824-571e-409c-b873-5eec261545ce` | Live checks and review at frozen head `d890a845` | Draft; 3 pass / 8 running |
| Reformat continuity checkpoint | `dae16354-b5f6-4db5-9026-916a0fb3b03c` | Versioned off-machine state and restart procedure | Draft PR #10 remote; cloud handoff verifying |

## Latest authoritative snapshot

- Canonical release graph revision 8 is SHA-256 `5d581d49b1ed3df931cd63048058bb8da9760f5c900698d49e6b6e05a601695a`.
- Exactly two vNext PRs are open: `crutkas/busybox-w32#4` and `crutkas/build-extra#29`; both are draft, uniquely bound to their reviewed heads, labeled only `arm64-vnext`, and have no queue, auto-merge, review request, or stack membership.
- Runtime-generator is clean at commit `8fbd9808447ee78ed485deead9b79cd1e40c07b7`, tree `fe1106187ef9aa842e1cff0ccc4f978b65c16613`, on `crutkas-arm64-vnext/msys2-runtime/generator`.
- Runtime-generator external requirements are admitted. Fresh ARM64 M4, Sprut, Shilka, Autotools outputs, and `devices.cc` replay are node outputs, not pre-existing external inputs. Fresh BusyBox is the exact release-graph dependency.
- Independent session-start review v2 correctly returned NO-GO on a revision-7 hash transcription and issuer-incompatible live fields. Both coordinator artifacts are repaired and a fresh replacement review is active; the rejected review remains preserved.
- Runtime-generator session-start verdict `f13ec4e688f5f9c5e9c4de38c4fdb1174b6795c81acc00e2edd31d81c8bdf9f1` and strict authorization receipt `48ade7bd7ed52ec93692df5744875607a32399e310fb778cefeeea76923d8e30` permit clean investigation, implementation, and local candidate-output production only. Hard stop before commit.
- Runtime source candidate currently changes exactly `winsup/autogen.sh`, `winsup/tests/autogen-contract.sh`, and `.github/workflows/build.yaml`. Hosted MSYS and exact native BusyBox contract tests pass; `git diff --cached --check` passes; staged tree is `43aec2ed8555b6f4a9866ae4b8605972062dff6d`. The provisional `092bb2b` tree is superseded after correcting an index-only workflow executable-mode error; `.github/workflows/build.yaml` is restored to mode `100644`. Fresh ARM64 generator-bundle build and reproducibility evidence remain in progress.
- Independent source preaudit `cb76badf249ea5b2844b5fab608072edb90cc00f3a949959c0cba112e0bbd71b` passes with zero blockers and grants no commit authority. Final review still requires the generator bundle, 10-output replay, provenance/process/PE/import/module records, and two-build byte reproducibility evidence.
- Emergency runtime continuity is frozen as exact patch `0f2f3f9dfc7509d1d240f81a44a4c1700032478c51ff89d769a14c4b5ca022d8`, sealed state ledger `6ff2bcc368087070a9070729e2ea888b6f466eafbffb8c083db8f2a23cd58b69`, and local replay archive `e5113678ade3f4e79a63b473eafe55e164839a06dba20d8f8cf3a63996e6ffc1`. Patch and ledger are remote in continuity draft PR #10; the 135 MB archive remains a reproducible local fallback.
- Continuity draft PR `crutkas/msys2-woarm64-build#10` is remote at commit `d27a45a135d28042f8b34c70e91f82fec4611903`, tree `6e102e71fe93fc02a1ad9bbca877299e4c16354a`. It contains 23 files/2,606,505 bytes, exact byte-preserving state, `SHA256SUMS` SHA `30b15351162284da52a61fa573a11fdffae92f638e2e8f9ae509f7493b86f77d`, 14/14 seal replay, secret-scan pass, and exact runtime patch-to-tree replay. Cloud handoff session `dae16354-b5f6-4db5-9026-916a0fb3b03c` is verifying it read-only.
- Runtime before-commit review `0e88bb5e997b2a437faada948376fb9559a23ecb653567dc3111efd1718057d7` returned NO-GO on one closure defect: native `tools/make.exe` imports admitted `libintl-8.dll` SHA `31db0d0e7780cf28dca1309a894cb775b2ab130c4ba777c546a206970ca47320`, but the DLL was absent from the bundle/manifest/ZIP. An isolated bundle PATH reproduces `STATUS_DLL_NOT_FOUND`; ambient CLANGARM64 PATH had masked it. The writer is rebuilding candidate outputs and evidence with recursive isolated import closure. Staged source tree `43aec2ed...` and zero-commit hard stop remain unchanged.
- Revision-2 repair bundles that exact admitted DLL. Two independently written ZIPs are byte-identical at SHA `bf5e5cfae801f5e6c5a79acbf25e99b7a26ea9bed3c67895ceed979a28ca49e1`; 119/119 PEs are AA64 and 1,348 recursive import edges have zero unresolved entries. The missing-DLL control still reproduces `0xC0000135`, while repaired `make.exe` and all required generator tools pass under bundle-only PATH plus System32. Strict diagnostic `2f2ec26efe0b7b59e6c60db7c0d363a0caff2b6a57ae660a29c12d79f7e05c14` passes; fresh independent re-review is active.
- Replacement review `c286ab7afc584c0102797afe5a94ccf8a4598f65897e191121edb74afbe67dff` confirmed every runtime source/artifact gate but returned NO-GO because it resolved the canonical controls path to preserved earlier Phase-0 controls. The old `d11d2a1...` file is archived unchanged; exact revision-8 controls `95d907f4...` are now canonical under sealed promotion `35cb98a81feeb0626c9ee6ed35fbd7c62224da8f2d09ba0a6fc02b93851e08ec`. Runtime artifacts did not change; a narrow carry-forward review is active.
- Carry-forward review `bd7d6f358583833b76388e9e453ca24735804029a493b0bc1ec3a6ec3c6084e6` is zero-blocker GO for exactly `runtime-generator:[before_commit]`. Issuer verdict `ee4bdd0592b689bedece731d384c59854657f459c8bc7e2cfa527ce89922ce22` and strict receipt `00711096c30d6e3aa6c0d5ef05c41ae0af252e604adb4924842d13e376801cc7` permit one commit of tree `43aec2ed...`; push and PR remain forbidden.
- Authorized commit `d890a845e992638a6f09560efacc26d15b3ffe6a` was created exactly once with tree `43aec2ed8555b6f4a9866ae4b8605972062dff6d`, parent `8fbd9808447ee78ed485deead9b79cd1e40c07b7`, required trailers once, and clean worktree. Remote branch and matching PR counts remain zero. Graph revision 9 SHA `9a3b3fd88582b0201efb1b5dd943936976d8c4224ed7b2c608c041be6cb34b72` is staged with passing controls; independent HEAD audit is active.
- Independent HEAD audit `05a1d065ae87b6b4160af3802fb5f3745e64d5ebea3b15cb61f7001b166035d8` is `GO_FOR_PUSH_REVIEW` with zero blockers. Canonical graph revision 10 `e18c31f5958ea66a52472a13ac126c064f86b51e461ac1eafb0521b5223b6003` records `audited_waiting_push`; controls and strict push diagnostic pass. Remote branch/PR remain absent while separate before-push review runs.
- Before-push review `b0b3c78c3afc68fb492b517da79497cbedcd595e737fcf08fe67c501fea6d593`, issuer verdict `b3b76eeeaf5a31722e110c31db6a13708a00753e27937ad9f94093d67c53a45f`, and strict receipt `567922eea1dff103f65ddda2635c6df7cdf92f7b37668f8545ce92cac4fae8b8` authorize one normal non-force creation push at exact head `d890a845...`; no PR authority.
- One normal non-force push created only `refs/heads/crutkas-arm64-vnext/msys2-runtime/generator`; remote commit/tree/parent read back exact, local upstream matches, worktree is clean, and PR count remains zero. Push receipt SHA is `f89e56d88a333322cf0fef278698aa6fc13751f00def7c7941c1cf799ad8f3a1`. Canonical graph revision 11 records `pushed_awaiting_pr`; exact title/body and independent before-PR review are active.
- Before-PR review `86a27db3e67abb301adb4760bb5eefd37fafd24bf890aec46cd341784791f7c7`, issuer verdict `61c26a2e44f9ad09b7c2fa2d4a4d058e3b049a78619d1a50cd89bd315cc3a6ce`, and strict receipt `69f33b882236e895758623e4cdca8cd22020e0eaacfa3cbae3e5d33521feeeba` authorize exactly one draft PR with body SHA `f29ca2873dd21c9ce23877daf70454cfec201ce8c6781652d92b5548a1932f9d` and only `arm64-vnext`.
- Runtime draft PR `crutkas/msys2-runtime#31` is open at commit `d890a845e992638a6f09560efacc26d15b3ffe6a`, tree `43aec2ed8555b6f4a9866ae4b8605972062dff6d`, base `msys2-3.6.10`, exact reviewed body, label only `arm64-vnext`, unique head count 1, no reviews/queue/auto-merge/stack/merge. PR receipt SHA is `ee7b28eb7db94e1b848359d3f49bfc85bc3856610755ee5303e8b4cee8e36262`; graph revision 12 and four-PR live readback are sealed.

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
