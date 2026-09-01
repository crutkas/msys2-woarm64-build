# ARM64 vNext reformat continuity checkpoint

Epoch: `2026-08-31-v1`

This directory is the durable, documentation-and-evidence-only handoff for the
Git for Windows native ARM64 vNext programme. It preserves the exact coordinator
state, the published runtime-generator identity, its repaired generator bundle,
and fallback source evidence without granting any new implementation, review,
stack, artifact, merge, release, or admission authority.

## Checkpoint identity

- Repository: `crutkas/msys2-woarm64-build`
- Clean base commit: `77f0d56cdf4c063c1b3af37f551e01c3a012c8bb`
- Clean base tree: `a031061a532b57adf447fcb7df478d9b37a071a6`
- Requested logical branch:
  `arm64-vnext/msys2-woarm64-build/reformat-continuity`
- App-native returned branch:
  `crutkas-arm64-vnext/msys2-woarm64-build/reformat`
- Accepted truncation: after the app-native rename returned the shorter name,
  fresh coordinator authority explicitly accepted it as unambiguous and inside
  the required physical `crutkas-arm64-vnext/` namespace. It is the effective
  branch for this checkpoint and must not be renamed again.
- Checkpoint PR: [crutkas/msys2-woarm64-build#10](https://github.com/crutkas/msys2-woarm64-build/pull/10),
  draft against `main`, titled
  `[ARM64 vNext] Reformat continuity checkpoint`, labeled only
  `arm64-vnext`.

`state/` contains exact byte-preserving copies of the source artifacts. Some
machine evidence intentionally records its original absolute paths; those bytes
are evidence and were not normalized. All human recovery instructions use
repository-relative paths.

## Durable programme state

| Repository | PR | Frozen head | State |
|---|---:|---|---|
| `crutkas/busybox-w32` | [#4](https://github.com/crutkas/busybox-w32/pull/4) | `942be1cd339f2fa5c426d28a83dad62b2b366d5e` | Draft; two successful checks |
| `crutkas/build-extra` | [#29](https://github.com/crutkas/build-extra/pull/29) | `305d14d63db6073245ad4e3002f7400e58040c55` | Draft; one success and four skipped checks |
| `crutkas/msys2-runtime` | [#31](https://github.com/crutkas/msys2-runtime/pull/31) | `d890a845e992638a6f09560efacc26d15b3ffe6a` | Draft; checks running |
| `crutkas/msys2-woarm64-build` | [#10](https://github.com/crutkas/msys2-woarm64-build/pull/10) | This checkpoint branch | Draft continuity PR |

All four PRs are draft and labeled only `arm64-vnext`. Each product head
uniquely matches its PR. No native vNext stack exists, and no review request,
merge queue, auto-merge, merge, or release authority is granted.

The runtime-generator transition is now durable:

- Repository: `crutkas/msys2-runtime`
- Primary recovery identity: draft PR
  [#31](https://github.com/crutkas/msys2-runtime/pull/31)
- Branch: `crutkas-arm64-vnext/msys2-runtime/generator`
- Clean base: `msys2-3.6.10` at
  `8fbd9808447ee78ed485deead9b79cd1e40c07b7`
- Base tree: `fe1106187ef9aa842e1cff0ccc4f978b65c16613`
- Head commit: `d890a845e992638a6f09560efacc26d15b3ffe6a`
- Head tree: `43aec2ed8555b6f4a9866ae4b8605972062dff6d`
- Authorized PR body SHA-256 prefix: `f29ca287`; normalized live body
  SHA-256 prefix: `122fe6fb`
- PR state: draft/open; label only `arm64-vnext`; matching-head count one;
  checks running; no review, queue, auto-merge, stack, or merge.
- Primary preserved bundle:
  `state/arm64-vnext-2026-08-31-v2-generator-bundle.zip`
- Bundle bytes/SHA-256:
  `24478030` / `bf5e5cfae801f5e6c5a79acbf25e99b7a26ea9bed3c67895ceed979a28ca49e1`
- The bundle is a continuity-only, non-admitted engineering artifact, not a
  release.
- Fallback exact patch:
  `state/arm64-vnext-2026-08-31-v2-runtime-generator-before-commit.patch`
- Patch bytes/SHA-256:
  `3204` / `0f2f3f9dfc7509d1d240f81a44a4c1700032478c51ff89d769a14c4b5ca022d8`
- PR receipt bytes/file SHA-256/payload SHA-256:
  `6966` /
  `ee7b28eb7db94e1b848359d3f49bfc85bc3856610755ee5303e8b4cee8e36262` /
  `876f9d826812885c7ea7cc24fdd527cea4cfc54cb080de9c5d5758b5695ec553`.

Canonical release graph revision 12 is file SHA-256
`8ac61bcb3aa71ac15065e5bb5b72ece8269c2a24399942efee6a39e6b3ea2605`
and payload SHA-256
`18eb4e9da1194bae88c167d626a0108d24fe432466b5fdc16787a23ac4393276`.
All prior runtime `session_start`, `before_commit`, `before_push`, and
`before_pr` verdicts and authorizations are consumed and cannot be reused. This
checkpoint grants no new runtime authority.

## Validation performed

- All listed original and final sources were present and independently SHA-256
  hashed before copying.
- Every copied state file was rehashed against its source.
- Every canonical JSON payload seal replayed from recursively sorted, compact,
  UTF-8 JSON and matched. Manifest-style JSON without a canonical seal remains
  authenticated by `SHA256SUMS`.
- The runtime patch passed `git apply --check --index` against a fresh isolated
  clone at the exact clean base.
- Applying the patch to the index produced exactly tree
  `43aec2ed8555b6f4a9866ae4b8605972062dff6d`; `git diff --cached --check`
  passed and the changed paths were exactly `.github/workflows/build.yaml`,
  `winsup/autogen.sh`, and `winsup/tests/autogen-contract.sh`.
- A credential scan found no private key, GitHub/AWS/Google/Slack token, bearer
  credential, or populated password/secret/token field in the checkpoint
  sources.
- The repaired ZIP passed full entry decompression. Its manifest contains
  exactly `runtime/bin/libintl-8.dll`, 268,288 bytes, SHA-256
  `31db0d0e7780cf28dca1309a894cb775b2ab130c4ba777c546a206970ca47320`,
  and the ZIP member matches that identity.

See `RECOVERY.md` for exact verification and restart commands. `SHA256SUMS`
authenticates every file other than the checksum manifest itself; its own
identity is the Git blob/tree identity of the checkpoint commit and can also be
checked against the PR commit.

## State inventory

`state/` retains every file from the initial checkpoint and adds the exact
revision-12 graph, controls, live v9 readback, artifact index, controls
promotion, consumed runtime verdicts/authorizations, both preserved
`before_commit` NO-GO reviews, final GO review, head audit, push/PR reviews,
writer receipts, compact/rich continuity records, repaired bundle, and final
generator evidence. `state/runtime-generator-v2-evidence/` contains the exact
manifest, runtime/import closure, process attestation, bundle evidence,
dual-generation, relocation, COCOM replay, focused-contract, and hosted
validation records. `SHA256SUMS` is the complete filename and digest inventory.

The 135,519,451-byte local replay archive
`arm64-vnext-2026-08-31-v1-runtime-generator-continuity-replay.tar.gz`
(`e5113678ade3f4e79a63b473eafe55e164839a06dba20d8f8cf3a63996e6ffc1`)
and the later 180 MB replay archive are deliberately not committed. The exact
repaired bundle, admitted sources, manifest, and sealed evidence are sufficient
for recovery.

## Resume order

1. Verify this commit, `SHA256SUMS`, and all canonical JSON seals.
2. Recreate the eight projects and fetch the exact draft PR heads.
3. Fetch runtime PR #31, verify its exact commit/tree, and monitor its checks and
   reviews. Use the preserved patch only if the primary PR recovery fails.
4. Read back live GitHub state; do not infer authority from this checkpoint.
5. Start runtime `abi` only after fresh independent review and exact
   session-start authority for that node and identity.
6. Continue the runtime stack only in order:
   `generator -> abi -> linker-import -> signal-tls -> mvp -> fork-exec`;
   build-extra `payload` follows the frozen runtime top.

All preserved phase verdicts are consumed and cannot be reused. No old POC
branch, commit, release, Actions artifact, or binary is a vNext input.
