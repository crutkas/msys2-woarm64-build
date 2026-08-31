# ARM64 vNext reformat continuity checkpoint

Epoch: `2026-08-31-v1`

This directory is the durable, documentation-and-evidence-only handoff for the
Git for Windows native ARM64 vNext programme. It preserves the exact coordinator
state and the uncommitted runtime-generator candidate without granting any new
implementation, commit, push, PR, stack, artifact, release, or admission
authority.

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
- Intended PR: one draft PR to `main`, titled
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

Both code PRs are labeled only `arm64-vnext`, uniquely match their head, and
have no review request, stack, queue, auto-merge, merge, or release authority.

The runtime-generator transition is local evidence only:

- Repository: `crutkas/msys2-runtime`
- Branch name reserved for later authorized publication:
  `crutkas-arm64-vnext/msys2-runtime/generator`
- Clean base/HEAD: `8fbd9808447ee78ed485deead9b79cd1e40c07b7`
- Base tree: `fe1106187ef9aa842e1cff0ccc4f978b65c16613`
- Candidate commits and remote PRs: zero
- Exact staged patch: `state/arm64-vnext-2026-08-31-v1-runtime-generator-staged-43aec2ed.patch`
- Patch bytes/SHA-256:
  `3204` / `0f2f3f9dfc7509d1d240f81a44a4c1700032478c51ff89d769a14c4b5ca022d8`
- Resulting staged tree: `43aec2ed8555b6f4a9866ae4b8605972062dff6d`
- Continuity ledger file bytes/SHA-256:
  `745514` / `6ff2bcc368087070a9070729e2ea888b6f466eafbffb8c083db8f2a23cd58b69`
- Continuity payload SHA-256:
  `d2f16dc11c9cf917e2c51fdfb8da40859a9e85720bd06c79fd5701b78cf6d777`
- Source preaudit: pass, with no blockers; it grants no commit authority.
- Generator bundle and two-run reproducibility evidence were still running at
  the frozen checkpoint.

The active authority permits only runtime-generator `session_start`: clean
investigation, implementation, and local candidate-output production. The hard
stop remains before the first runtime commit. This checkpoint grants no runtime
commit, push, PR, artifact-construction, stack, or release authority.

## Validation performed

- All 19 listed sources were present and independently SHA-256 hashed before
  copying.
- Every copied state file was rehashed against its source.
- All 14 canonical JSON payload seals replayed from recursively sorted,
  compact, UTF-8 JSON and matched.
- The runtime patch passed `git apply --check --index` against a fresh isolated
  clone at the exact clean base.
- Applying the patch to the index produced exactly tree
  `43aec2ed8555b6f4a9866ae4b8605972062dff6d`; `git diff --cached --check`
  passed and the changed paths were exactly `.github/workflows/build.yaml`,
  `winsup/autogen.sh`, and `winsup/tests/autogen-contract.sh`.
- A credential scan found no private key, GitHub/AWS/Google/Slack token, bearer
  credential, or populated password/secret/token field in the checkpoint
  sources.

See `RECOVERY.md` for exact verification and restart commands. `SHA256SUMS`
authenticates every file other than the checksum manifest itself; its own
identity is the Git blob/tree identity of the checkpoint commit and can also be
checked against the PR commit.

## State inventory

- `arm64-vnext-2026-08-31-v1-reformat-continuity-manifest.md`
- `status.md`
- `plan.md`
- `inbox.md`
- `arm64-vnext-release-graph.json`
- `arm64-vnext-boundary.json`
- `arm64-vnext-2026-08-31-v1-ancestry-report.json`
- `arm64-vnext-2026-08-31-v1-input-provenance.json`
- `arm64-vnext-2026-08-31-v1-first-artifact-definition.json`
- `arm64-vnext-2026-08-31-v1-app-branch-prefix-amendment.json`
- `arm64-vnext-2026-08-31-v1-live-readback-v5.json`
- `arm64-vnext-2026-08-31-v1-runtime-session-review-authority-correction.json`
- `arm64-vnext-2026-08-31-v1-phase0-verdict-runtime-generator-session-start.json`
- `arm64-vnext-2026-08-31-v1-runtime-generator-session-start-authorized.json`
- `arm64-vnext-2026-08-31-v1-runtime-generator-staged-43aec2ed.patch`
- `arm64-vnext-2026-08-31-v1-runtime-generator-continuity.json`
- `arm64-vnext-2026-08-31-v1-runtime-generator-session-review-v3.json`
- `arm64-vnext-2026-08-31-v1-runtime-generator-source-preaudit.json`
- `arm64-vnext-2026-08-31-v1-generator-input-ledger-v2.json`

The 135,519,451-byte local replay archive
`arm64-vnext-2026-08-31-v1-runtime-generator-continuity-replay.tar.gz`
(`e5113678ade3f4e79a63b473eafe55e164839a06dba20d8f8cf3a63996e6ffc1`)
is deliberately not committed. The admitted exact sources and sealed continuity
ledger preserve the identities required to rebuild it.

## Resume order

1. Verify this commit, `SHA256SUMS`, and all canonical JSON seals.
2. Recreate the eight projects and fetch the exact draft PR heads.
3. Read back live GitHub state; do not infer authority from this checkpoint.
4. Rebuild or recover the generator bundle from admitted inputs, then replay the
   staged patch and generated outputs twice.
5. Obtain a new independent `before_commit` review before any runtime commit.
6. Obtain separate, fresh `before_push` and `before_pr` authority before each
   corresponding mutation.
7. If a runtime-generator draft PR is later authorized and created, update this
   checkpoint with its exact URL, head, tree, checks, and consumed authorities.
8. Continue the runtime stack only in order:
   `generator -> abi -> linker-import -> signal-tls -> mvp -> fork-exec`;
   build-extra `payload` follows the frozen runtime top.

Never reuse a consumed verdict. No old POC branch, commit, release, Actions
artifact, or binary is a vNext input.
