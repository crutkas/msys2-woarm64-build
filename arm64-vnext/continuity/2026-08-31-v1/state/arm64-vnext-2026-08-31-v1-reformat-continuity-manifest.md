# ARM64 vNext Reformat Continuity Manifest

Epoch: `2026-08-31-v1`  
Checkpoint time: `2026-08-31T23:14:00Z`  
Programme goal: a clean-slate Git for Windows engineering build with native ARM64 binaries end to end.

## Durable remote state

| Repository | PR | Head | State |
|---|---:|---|---|
| `crutkas/busybox-w32` | #4 | `942be1cd339f2fa5c426d28a83dad62b2b366d5e` | Draft; two successful checks |
| `crutkas/build-extra` | #29 | `305d14d63db6073245ad4e3002f7400e58040c55` | Draft; one successful diagnostic suite |

Both PRs are labeled only `arm64-vnext`, have one matching PR for their head, and have no review request, merge queue, auto-merge, merge, or stack authority.

## Runtime generator transition

- Repository: `crutkas/msys2-runtime`
- Branch: `crutkas-arm64-vnext/msys2-runtime/generator`
- Clean base/HEAD: `8fbd9808447ee78ed485deead9b79cd1e40c07b7`
- Base tree: `fe1106187ef9aa842e1cff0ccc4f978b65c16613`
- Current staged tree: `43aec2ed8555b6f4a9866ae4b8605972062dff6d`
- Candidate commits: zero
- Staged paths:
  - `.github/workflows/build.yaml` mode `100644`
  - `winsup/autogen.sh`
  - `winsup/tests/autogen-contract.sh`
- Hosted MSYS and exact native ARM64 BusyBox contract tests pass.
- `git diff --cached --check` passes; no unstaged, unrelated, or untracked files were reported.
- Fresh native ARM64 generator-bundle build and reproducibility evidence are still running.
- Hard stop remains before the first commit. No runtime push, PR, stack, or GitHub mutation exists.

An exact full-index binary patch, sealed continuity JSON, and resumable build archive are being generated as emergency local exports. Record their final hashes here before the machine is reformatted or carry them as checkpoint attachments.

## Current authority chain

| Authority | SHA-256 |
|---|---|
| Clean boundary | `97ce5396ff9f581c02f7207413d9803dbd219f6fa1764c87e73f2b1c4ed7b68d` |
| Release graph revision 8 | `5d581d49b1ed3df931cd63048058bb8da9760f5c900698d49e6b6e05a601695a` |
| Complete ancestry report | `9aa7f43125c638751cfd805a4c318355db6702ea3cc8c772435feefbd04e30ac` |
| Consolidated input provenance | `9f4ed99e12d67ef026eb7fb85c783edc9d8211a1ea80f5447e3a7dd3e1a00999` |
| First-artifact definition | `f714a7f6cfd3302330351f436f96f9c10046c55a1fdd0a045c5f58d9c4fe9b73` |
| App branch-prefix amendment | `e477de0e24d84c40843a887a0b5b2268257e6373faa1c22ea6490227fdc93a8c` |
| Generator input ledger v2 | `14fea77370d75b50e826adc0c466f5a4ffc540c3412fe276f426fca877b57761` |
| Runtime session-start review v3 | `a323a61ced581a4cf9ccc8a1ae9619b9a583138e7917b71e7f2988daf089ddfb` |
| Runtime session-start verdict | `f13ec4e688f5f9c5e9c4de38c4fdb1174b6795c81acc00e2edd31d81c8bdf9f1` |
| Runtime session-start authorization receipt | `48ade7bd7ed52ec93692df5744875607a32399e310fb778cefeeea76923d8e30` |

The active verdict authorizes only `runtime-generator:[session_start]`: local investigation, implementation, and candidate-output production. It does not authorize commit, push, PR, artifact construction, release admission, or any other node.

## Frozen producer outputs

| Output | SHA-256 |
|---|---|
| BusyBox ARM64 bootstrap executable, 336,384 bytes | `4e510e35e642a32cc6b5a0e676e78513c91108df6143f33737ecf5c3eeeb0369` |
| BusyBox final evidence | `b36e429106fc9b2f51ff57921b171ab6410c1c8347c31cdb226420012d7fc658` |
| ARM64 process-attestor ZIP | `73777a4cf80c1e2f8256a3c52bd539e7201801c401e11fc77819701207c0e29f` |
| ARM64 process-attestor executable | `d5ae9700b42857d1e2bbd7d5383bb06a64b5821a383bdc2723150b53f5fac1c7` |

## Healthy shutdown target

Before reformat, prefer this sequence:

1. Let the runtime generator build and two-run replay finish.
2. Freeze and independently review the exact staged tree, patch, generator bundle, and evidence.
3. If review grants `before_commit`, create exactly one reviewed commit.
4. Independently audit the commit, then obtain separate `before_push` and `before_pr` authority.
5. Push only `crutkas-arm64-vnext/msys2-runtime/generator` and open one draft PR under `crutkas/msys2-runtime`, labeled only `arm64-vnext`.
6. Update this continuity checkpoint with that PR URL, exact head/tree, check state, and consumed authorities.
7. Stop all local builders and sessions only after every code change exists in a remote draft PR and this checkpoint is remote.

If time runs out before step 3, preserve the exact patch, sealed continuity JSON, build archive/logs, and hashes in the remote continuity checkpoint. Do not bypass review merely to push.

## Restart procedure after reformat

1. Sign in to the same GitHub/Copilot account and reopen the continuity-checkpoint draft PR/session.
2. Recreate the eight configured `crutkas/*` projects from their canonical remotes.
3. Fetch the exact draft PR heads and verify every commit/tree/hash in this manifest.
4. Restore the coordinator evidence bundle and replay all canonical JSON seals before issuing authority.
5. If runtime has a draft PR, resume with live check/review monitoring. If it has only a preserved patch, apply it to clean base `8fbd980...`, verify staged tree `43aec2e...` or the later recorded replacement, and rerun generator/build evidence from admitted inputs.
6. Resume only the next unconsumed phase. Never reuse a consumed verdict or infer authority from this manifest.
7. Continue the runtime stack in order: `generator -> abi -> linker-import -> signal-tls -> mvp -> fork-exec`, then build-extra `payload`.

## Permanent exclusions

- No old POC branch, commit, release, Actions artifact, or binary is a vNext build input.
- No upstream PR is created without explicit approval; all vNext PRs stay under `crutkas/*`.
- No merge, auto-merge, queue, review request, stack registration, or release admission is implied by this checkpoint.
- The first Git Bash ZIP remains a non-admitted engineering handoff until independent replay and later governance.
