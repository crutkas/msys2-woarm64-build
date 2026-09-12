# Native ARM64 Git programme: recover after the September 11 reformat

**Start here. The old machine and all `C:\ag-*`, `C:\ap*`, `C:\agtc-*`,
session-state and WSL paths are disposable historical locations. Repository
commits and their byte-preserved evidence are the recovery sources.**

The programme has a working native ARM64 runtime and substantial real Git
functionality. It does **not** have a fully admitted native Git distribution.
In particular, successful HTTPS used superseded, unadmitted OpenSSL bytes.
Read the failures beside the successes before rebuilding or publishing.

This is a preservation/restart document, not a merge, runner-registration,
credential, package-admission, or release authorization. Old worker grants
expired with their sessions. Obtain a new bounded allocation before building.

## 1. Recover repositories and evidence, not remembered local paths

The principal forks are `crutkas/msys2-woarm64-build` and
`crutkas/msys2-runtime`. Work is on PR branches, **not necessarily `main`**.
Fetch all relevant PR refs before assuming a file is missing. Use new owned
directories, never an old primary checkout or another session's worktree.

Example PowerShell sequence on a freshly prepared machine with Git installed:

```powershell
git -c core.autocrlf=false clone --branch crutkas-arm64-ruby-documentation `
  https://github.com/crutkas/msys2-woarm64-build.git .\build-recovery
git -c core.autocrlf=false clone --branch crutkas-arm64-runtime-integration `
  https://github.com/crutkas/msys2-runtime.git .\runtime-recovery

foreach ($n in 11,12,13,14,15,16,17) {
  git -C .\build-recovery fetch origin `
    "refs/pull/$n/head:refs/remotes/origin/recovery-pr$n"
  if ($LASTEXITCODE -ne 0) { throw "Could not recover build PR $n" }
}
foreach ($n in 32,33,34) {
  git -C .\runtime-recovery fetch origin `
    "refs/pull/$n/head:refs/remotes/origin/recovery-pr$n"
  if ($LASTEXITCODE -ne 0) { throw "Could not recover runtime PR $n" }
}
git -C .\build-recovery fetch origin crutkas-native-provider-intake
if ($LASTEXITCODE -ne 0) { throw 'Could not recover the provider branch (no PR)' }
git -C .\build-recovery fetch origin crutkas-native-git-helper-packages
if ($LASTEXITCODE -ne 0) { throw 'Could not recover the helper-package evidence branch' }
git -C .\build-recovery fetch origin crutkas-native-execution-recovery
if ($LASTEXITCODE -ne 0) { throw 'Could not recover the execution evidence branch' }
```

Read the evidence directory on each fetched branch. Do not merge branches just
to make evidence visible. An isolated detached worktree at a recorded commit
is sufficient, for example:

```powershell
git -C .\build-recovery worktree add --detach ..\verification-evidence `
  bfea25a4fe7703d602b8d4282b75fc064ee8ee59
git -C .\build-recovery worktree add --detach ..\closure-evidence `
  7368ba69e60e7092792c10ee5f1c5c8aea3923da
git -C .\build-recovery worktree add --detach ..\closure-source-evidence `
  0da6e92a060e11144ba2ded1a6962096963615a2
git -C .\build-recovery worktree add --detach ..\closure-published-source `
  e5f5b4c1ffb7c090fd38661b7b1be2458aeb2aea
git -C .\runtime-recovery worktree add --detach ..\generation-evidence `
  2af0ec0c244f522b65ace15be71deab4f3c528ad
git -C .\build-recovery worktree add --detach ..\provider-evidence `
  3ebc0c133105c77496ae80d4ea76fad7ed463c80
```

Those are evidence-publication identities, not substitutions for the qualified
source commits below. Public upstream sources may be re-downloaded only at
their recorded pins with their original verification requirements. A source
URL, recipe hash, or PE machine value alone is not proof of a recreated binary.

### Portable evidence index

Paths below are relative to the named repository at the **publication commit**.
Every topic README describes its inventory/hash scheme and original paths.
Original JSON paths are deliberately unchanged; resolve them through the
preservation index by path or SHA-256. An unlisted local file is **not backed up
merely because another receipt mentions it**.

**Discovery rule: evidence is NOT confined to `arm64-vnext/evidence/`.**
Search the contents of complete branch trees in both repositories, not only
canonical directory names. A missing canonical path is not a missing finding.
The non-canonical Berkeley DB report below is a directly verified counterexample.

| Topic / owner | Repository, branch / PR | Portable evidence and publication status |
|---|---|---|
| Master continuity, Ruby/Asciidoctor, merge-readiness (`ab17e048`) | `crutkas/msys2-woarm64-build`, `crutkas-arm64-ruby-documentation`, [PR 15](https://github.com/crutkas/msys2-woarm64-build/pull/15) | This branch: `arm64-vnext/evidence/ruby-asciidoctor/` and `arm64-vnext/evidence/programme-reconciliation/`. Complete original Ruby packet, six signed upstream runtime archives plus real Asciidoctor package, exact generated documentation, source archives, API/owner records and primary receipt backups. See their READMEs and `preservation-manifest.json`. |
| Independent moved Git/HTTPS/TLS/ZIP verification (`b1b1deaf`) | Same build repo, `crutkas-native-tcl-qualification`, [PR 16](https://github.com/crutkas/msys2-woarm64-build/pull/16) | **Published** `bfea25a4fe7703d602b8d4282b75fc064ee8ee59`: [`arm64-vnext/evidence/independent-verification/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/bfea25a4fe7703d602b8d4282b75fc064ee8ee59/arm64-vnext/evidence/independent-verification/README.md). 227 preservation files; original records indexed by `index.json`. This export deliberately excludes artifact ZIPs, binaries and extracted payloads. |
| Strict blocker and DLL closure audit (`accd408a`) | Same build repo, `crutkas-arm64-pcre2-package`, [PR 17](https://github.com/crutkas/msys2-woarm64-build/pull/17) | **Original sealed evidence** `7368ba69e60e7092792c10ee5f1c5c8aea3923da`: [`arm64-vnext/evidence/dependency-closure/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/7368ba69e60e7092792c10ee5f1c5c8aea3923da/arm64-vnext/evidence/dependency-closure/README.md). `preservation-index.json` maps 231 original paths to 230 exact evidence files. **Distinct source rescue** is published at successor `0da6e92a060e11144ba2ded1a6962096963615a2`, [`source-recovery/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/0da6e92a060e11144ba2ded1a6962096963615a2/arm64-vnext/evidence/dependency-closure/source-recovery/README.md); it does not alter the old evidence or qualify its mixed archived code. Start evidence review at `closure/delivery-03/report.md`; retain delivery-01/02. No runtime/package binaries are included. |
| Atomic runtime generation (`e6a17275`) | `crutkas/msys2-runtime`, `crutkas-atomic-runtime-generation`, [PR 34](https://github.com/crutkas/msys2-runtime/pull/34) | **Published standardized recovery root** at `2af0ec0c244f522b65ace15be71deab4f3c528ad`: [`arm64-vnext/evidence/atomic-generation/README.md`](https://github.com/crutkas/msys2-runtime/blob/2af0ec0c244f522b65ace15be71deab4f3c528ad/arm64-vnext/evidence/atomic-generation/README.md). Preserves original 50-file proposal baseline plus all 170 application files; baseline archive SHA `19d273f86f14b9b3beb5debaa9f1309683f79bff242e8bf78ab363632d8d85c5`. Application `proof.tar.gz` remains SHA `2abaa10780ef6e287a2bd90f424d599771aa7db1d72faf354ed81af7557f1c84` (269,076 bytes). The earlier `fb627b685141eea8bd7e7813837e4b21c754dc35` / `winsup/testsuite/build/evidence/runtime-generation-20260911/` locator remains valid. Qualified source remains `df7d66f9b1433c50dd7cd234b0d8bd1213418b22`; both later commits are evidence-only. |
| Combined runtime, Bash/PTY investigation (`67ba2e76`) | Runtime repo, `crutkas-arm64-runtime-integration`, PR 33 | Owner preservation requested; confirm its final evidence-publication commit/path before claiming the complete runtime/toolchain/build tree survives. A byte-exact `combined-runtime-handoff.json` backup is already in this branch's `programme-reconciliation/source-receipts/`. |
| Signal/myfault/Texinfo producer (`5b01b4e5`) | Build repo, `crutkas-arm64-toolchain-bootstrap`, PR 11 | Owner preservation requested. This branch already preserves exact Texinfo root-cause/success handoffs, actual successful binutils log, old TLS proposal handoff and known-good TLS offsets under `programme-reconciliation/source-receipts/`. Complete producer environment custody must come from the owner export. |
| Mechanical/runtime exit contracts (`0af73d1b`) | Runtime PR 32 and build `crutkas-native-exit-observer-contract`, PR 12 | Qualified source is pushed at the heads below. Complete native proof publication locator has not yet been confirmed to this document; inspect those branches' new evidence directories. Do not mistake source/tests alone for preserved native execution receipts. |
| Berkeley DB (`2f98bedd`) | Build repo, `crutkas-native-berkeley-db`, PR 13 | **Published non-canonical finding:** [`arm64-git-recovery/native/DB-MUTEX-TIMING.md`](https://github.com/crutkas/msys2-woarm64-build/blob/5350bc1e0ce39ee8bc3c5d9727660b3e5251949f/arm64-git-recovery/native/DB-MUTEX-TIMING.md) at `5350bc1e0ce39ee8bc3c5d9727660b3e5251949f`, **8,873 bytes**, SHA-256 **`391b48ffa4fa277511ea1b2310da9876af1c4d5db473bb480d2713f9c04824c7`**, independently downloaded/read. It preserves the complete timing finding, not an owner still awaiting publication of that finding. Earlier root-cause source is at `4ff861de52ae8ec5fb36fd1d853f916bb1b21640`; exact D70 matrix/timing handoffs also exist here in `programme-reconciliation/source-receipts/`. The report does not by itself prove custody of every package/SDK/build-tree binary. |
| MVP assembly and replacement-TLS candidate (`f6ea7713`) | Build repo, `crutkas-full-native-git-assembly`, draft PR 14 | Owner evidence publication requested. Qualified candidate/ZIP binary preservation is **not confirmed here**; do not assume the 186 MB named ZIP is in Git. Independent verification and dependency-closure exports above preserve measured identities and failures even if a binary must be rebuilt. |
| Provider ledger/admission (`a2dd0a44`, pipeline `2160ef10`) | Build repo, [`crutkas-native-provider-intake`](https://github.com/crutkas/msys2-woarm64-build/tree/crutkas-native-provider-intake); **NO PR** (creation returned 422 twice, per coordinator) | **Published and remote directories confirmed** at `3ebc0c133105c77496ae80d4ea76fad7ed463c80`: [`arm64-vnext/evidence/provider-intake/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/3ebc0c133105c77496ae80d4ea76fad7ed463c80/arm64-vnext/evidence/provider-intake/README.md) covers ordered contracts, rejected libintl-selection captures and limited roles; [`arm64-vnext/evidence/provider-admission/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/3ebc0c133105c77496ae80d4ea76fad7ed463c80/arm64-vnext/evidence/provider-admission/README.md) covers strict authority, OpenSSL/header scopes and ledger v20-v42. Provider-intake `manifest.json` SHA-256 `df94ef731519e129e1dde7b497be7b501726366c2326b85b3f0f9291b1f8c65e` was verified from GitHub bytes. **No archives or payload binaries** are included: replacement OpenSSL payload custody is still separate. Search this branch directly, not only the PR list. |
| Git helpers / GnuPG dependencies (`6b81b146`) | Build repo, [`crutkas-native-git-helper-packages`](https://github.com/crutkas/msys2-woarm64-build/tree/crutkas-native-git-helper-packages) | **Published and remote root confirmed** at `2460d9fbd50a894c774e938670fae27ece1202cf`: [`arm64-vnext/evidence/git-helper-packages/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/2460d9fbd50a894c774e938670fae27ece1202cf/arm64-vnext/evidence/git-helper-packages/README.md), with per-file SHA-256 and `ORIGINS.tsv`. Includes Git LFS/git-extra evidence, later runtime907 client-only MSYS OpenSSH admission, crypto/libxcrypt dependency records and GnuPG work. Ledger v42's runtime907 GMP versus d70 conflict remains explicit. The interrupted libgcrypt `1-04` run proves no completed test/package success. No archives, PE binaries, private keyrings or build trees are included. |
| Execution/CRT recovery (`efd00553`) | Build repo, [`crutkas-native-execution-recovery`](https://github.com/crutkas/msys2-woarm64-build/tree/crutkas-native-execution-recovery) | **Published** evidence commit `de2353205ee2aece40435047a89cc6377fe47460`: [`arm64-vnext/evidence/execution-recovery/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/de2353205ee2aece40435047a89cc6377fe47460/arm64-vnext/evidence/execution-recovery/README.md). Separately, the **uncommitted, unintegrated CRT source fix** survives in [gist `e5d1ddc3410c418069046455c99ad09b`](https://gist.github.com/crutkas/e5d1ddc3410c418069046455c99ad09b), not in that evidence commit or PR 11. See the exact source-recovery contract below. |

**Later direct source publication on PR 17:** commit
[`e5f5b4c1ffb7c090fd38661b7b1be2458aeb2aea`](https://github.com/crutkas/msys2-woarm64-build/commit/e5f5b4c1ffb7c090fd38661b7b1be2458aeb2aea)
also commits 153 rescued source files at their live repository paths, plus
the source-publication manifest. The old `7368ba69` evidence and `0da6e92a`
recovery archive remain distinct; see the direct-publication boundary below.

**Publication gaps require content-level evidence, not directory-name
inference.** Owners were pushing in parallel during shutdown. If an entry says
requested/unconfirmed, inspect the complete branch tree, including source/docs
paths outside `arm64-vnext/evidence/`, and record exact commits/hashes before
claiming presence or absence. Treat those labels as locator-confirmation limits,
not a current count of delinquent owners. Do not invent a completed backup.

### Coordinator fallback gist: duplicate custody, not owner authority

The coordinator published
[fallback gist `eb29a10918bb69ea0a0c0227b15950bb`](https://gist.github.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb)
at observed revision `fe8f58b3b7ab763f2da4954e54e6ee4732347988`
(`2026-09-12T05:12:35Z`). It contains **six evidence/reference artifacts plus
a README**, not an owner publication or an integrated fix. This guide's
publisher independently downloaded all six raw files and matched every size
and SHA-256 below; the coordinator also reports post-upload raw-byte readback.

**Why the fallback was made, and the custody correction:** the coordinator
reported three unanswered preservation requests over five hours, then found
their own local backup covered only one of sixty evidence roots. They report
repairing that backup and publishing these small files directly rather than
waiting longer. Those process/backup-coverage observations are attributed to
the coordinator, not independently audited here.

**COORDINATOR CORRECTION, CONFIRMED BY RAW-BYTE READBACK:** the statements that
`tlsoffsets.good` had reached **"no branch"** and was **"protected by nothing"**
were **FALSE**. The coordinator explicitly retracted them after independently
downloading the earlier copy already published in
[`bae18d68797a8bf129fbc5022071d8414f2779af`, this branch's `source-receipts/tlsoffsets.good`](https://github.com/crutkas/msys2-woarm64-build/blob/bae18d68797a8bf129fbc5022071d8414f2779af/arm64-vnext/evidence/programme-reconciliation/source-receipts/tlsoffsets.good).
Fresh downloads of that exact old commit matched **1,822 bytes** and
`49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566`.
**PR 15 has prior, canonical custody of this artifact; the gist is a
coordinator duplicate, not a rescue.** The coordinator reports having repeated
the false claim to the user and in three escalating messages to the signal
owner `5b01b4e5`, and withdraws the accusation that the owner failed to preserve
it. The search had counted evidence-directory **names** and checked the
coordinator's local backup, but never searched the **contents** of the remote
tree already counted as safe. That incomplete index could not establish absence.

This does not prove the producer's complete source/build environment was
preserved; it does establish prior remote custody of these particular bytes.
PR 17 likewise has prior owner custody of the closure report and CSVs. The
coordinator now reports that five of the six gist files were already preserved
by owners; that aggregate is attributed, not a fresh six-file custody census.
The fallback's role is **redundancy**, not newly granted authority or a claim
that an otherwise lost artifact was saved.

| Fallback file (immutable raw locator) | Bytes | SHA-256 |
|---|---:|---|
| [`tlsoffsets.good`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/549981d096aababc1bdaf46f8541fff357fa53f7/tlsoffsets.good) | 1,822 | `49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566` |
| [`db-mutex-timing-handoff.json`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/13d7f35537d2f3684dd23c82c0a8891092a82371/db-mutex-timing-handoff.json) | 8,146 | `406c1c7d6ee5242fe888140b132d452771677380d6b0b76323bc625922a1c34f` |
| [`independent-tls-evidence-01.json`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/3b2fe5e8918835f16dc594e7bba3621202429b5c/independent-tls-evidence-01.json) | 13,094 | `94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc` |
| [`mingw-closure-report.md`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/f7c05485fee602107cfb38d3201e3e86f719c867/mingw-closure-report.md) | 11,280 | `22b79d6d71afc5103a36efae48753debd02062de572ed9f7c97767a25bb517df` |
| [`dll-admission-table.csv`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/12ba00555d18a2782b74ca5617a63ae80ccab465/dll-admission-table.csv) | 12,385 | `ac964ec2e40b568128c060dc2b52c6ab8f67b5e5be5897563d7a0c5abb367644` |
| [`remaining-59-blockers.csv`](https://gist.githubusercontent.com/crutkas/eb29a10918bb69ea0a0c0227b15950bb/raw/e8cd4dfc1882f24d970b3c639dfb3c1e72c6d1fc/remaining-59-blockers.csv) | 4,731 | `bf30c9c0de6afe5bf5a52d29b3a35acff22fe3b06b956b29eb7f08d769d3dfaa` |

**Authority and access:** this is a **COORDINATOR FALLBACK**. Publication does
not integrate, fix, qualify or CI-validate anything. Original owner branch
evidence and its scoped receipts remain authoritative; when the owner
publishes matching bytes, that owner copy is canonical and this gist is a
duplicate. The gist README is coordinator navigation prose, not a successor
verdict. Preserve the DB result's D70-only scope and the strict audit's
81/22/conditional-59 meaning. **Unlisted/secret is not access-controlled:
anyone holding the URL can read it.** The coordinator explicitly accepted that
tradeoff. Do not place credentials or private keys in such a fallback.

### Corrected shutdown coverage: canonical paths are not the whole repository

In the coordinator's update received **2026-09-12T05:13:26Z** (September 11,
22:13 PDT), they reported "eleven evidence trees on GitHub" and "eight owners
pending": Bash job-control, Berkeley DB, OpenSSL/PCRE2, curl, MVP assembly,
signal-generation, runtime-integration and argv.
**COORDINATOR RETRACTION at 2026-09-12T05:20:38Z: that eight-owner figure was
wrong. It came from another directory-name sweep, not a content search.**
The earlier claim is preserved here only as a corrected statement; it is
**not a live publication-gap list** and must not send a reader hunting for
findings that are already published.

The coordinator then reports using the Git trees API recursively across every
branch of both repositories. The defensible result of that **date-stamped,
coordinator-reported content-level sweep** is **eleven canonical evidence trees
plus at least one confirmed non-canonical location**, with some work still in
flight. The approximate **9,890 file entries** break down as follows; this
guide's publisher has not repeated the entire cross-repository census:

| Coordinator's sweep category | Reported file entries |
|---|---:|
| SQLite | 5,904 |
| Coreutils | 2,108 |
| Ruby / reconciliation | 825 |
| Dependency closure | 373 |
| Independent verification | 227 |
| Git helper packages | 154 |
| Execution recovery | 100 |
| Provider intake / admission | 78 |
| Runtime request recovery | 72 |
| Compiler recovery | 34 |
| Atomic generation | 15 |
| **Approximate total** | **9,890** |

These categories are the coordinator's grouping of published entries, not a
claim of 9,890 unique observations, expanded archive members, or complete source,
binary and environment custody. The eleven-tree count groups some subtrees
together; it is not a substitute for the recorded file inventories.

**Known non-canonical location, directly checked here:** the Berkeley DB
[`DB-MUTEX-TIMING.md` at `5350bc1e0ce39ee8bc3c5d9727660b3e5251949f`](https://github.com/crutkas/msys2-woarm64-build/blob/5350bc1e0ce39ee8bc3c5d9727660b3e5251949f/arm64-git-recovery/native/DB-MUTEX-TIMING.md)
is already on GitHub outside the canonical evidence path. Its 8,873 raw bytes
match SHA-256
`391b48ffa4fa277511ea1b2310da9876af1c4d5db473bb480d2713f9c04824c7`.
It contains the original 900-second/9-of-24 timeout and 83/76 coverage,
completed 24/24 D70 matrix and 314/314 exits, per-case and per-yield timing
tables, the same-binary combined907 timing comparison, and unchanged
`.text`/`.data`/`.rdata`/`.pdata`/`.xdata`/`.idata`/**`.reloc`** sections.
The report identifies quantized waits as the cause of the inadequate budget;
it does not claim to exclude every ordering bug or report a full 907 matrix.
The coordinator's earlier classification of this owner as pending was false:
**the finding was preserved, and the search missed its location**.

For future audits, enumerate all relevant branch refs with API pagination,
then search each complete Git tree and inspect plausible files by content and
hash. Check the recursive-tree response's `truncated` flag and traverse omitted
subtrees before making any absence claim. Include source/docs locations,
embedded archives, and separately indexed patch/gist custody; do not infer an
archive's members merely from its filename. **Evidence-directory discovery is
an index-building aid, never proof that unindexed content does not exist.**

**Remaining custody decision:** the coordinator reports additional raw data
and work-in-flight backups on the local machine, but the retracted eight-owner
count does not establish which of those objects lack remote copies.
**That local backup is NOT reformat-safe unless the user verifies an
off-machine copy.** No independently verified off-machine destination
or complete backup manifest was supplied with this update. The user must copy
the required backup off the machine and verify its inventory/bytes before
wiping, or accept loss of anything not separately published. Neither the
9,890-entry count nor the six-file fallback establishes complete evidence,
source, binary, toolchain or build-tree custody. After reformat, mark any
unrecoverable record explicitly; do not reconstruct missing results from
summaries or assume an owner's later push occurred.

### Verify before trusting a recovered copy

For this branch's two evidence topics:

```powershell
$repo = (Resolve-Path .\build-recovery).Path
foreach ($topic in 'ruby-asciidoctor','programme-reconciliation') {
  $root = Join-Path $repo "arm64-vnext\evidence\$topic"
  $manifest = Get-Content -Raw (Join-Path $root 'preservation-manifest.json') |
    ConvertFrom-Json
  foreach ($entry in $manifest.Files) {
    $file = Get-Item -LiteralPath (Join-Path $root $entry.Path)
    $actual = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).
      Hash.ToLowerInvariant()
    if ($file.Length -ne $entry.Bytes -or $actual -ne $entry.SHA256) {
      throw "Preserved evidence mismatch: $($entry.Path)"
    }
  }
}
```

Other topics have their own `index.json`, `preservation-index.json` or archived
manifest; follow their README rather than guessing the schema. Keep `-text`
guards, do not pretty-print sealed JSON, normalize CRLF, strip embedded CR, or
rewrite old paths inside originals. Windows `git archive` can be affected by
autocrlf: use `git -c core.autocrlf=false archive` or raw Git blob reads when
proving exact source bytes. Preserve original and successor receipts separately.

## Uncommitted source is a separate loss category

**Evidence completeness does NOT imply source completeness.** The shutdown
sweeps looked for `arm64-vnext/evidence/` on remote branches. That finds receipts,
not necessarily the code that produced or fixed them. The dependency-closure
owner explicitly excluded uncommitted producer code from its evidence PR;
that was correct evidence scoping, not a source backup.

The CRT bootstrap fix is a concrete near-loss: according to its owner it
existed on **no remote Git ref**, survived only in local checkpoint objects,
and was invisible to evidence-directory sweeps. It is now preserved as a patch
in an unlisted gist. A future session must recover **both** evidence and source
locators; some fixes are patches/gists, not branch commits.

### Known source-only recovery: CRT bootstrap header closure

| Field | Preserved identity / state |
|---|---|
| Source owner | Execution-recovery session `efd00553` |
| Patch locator | [Unlisted gist](https://gist.github.com/crutkas/e5d1ddc3410c418069046455c99ad09b), file `pr11-crt-bootstrap-header-closure.patch` |
| Exact size and SHA-256 | **13,915 bytes**, **`4cc4f5387496e86911a56bef3c1fa1d690c57bf5f07888f441a9bd8747efe5d4`**; the coordinator reports two independent matching downloads, and this guide's publisher independently matched the raw download too |
| API-supplied raw URL | [`pr11-crt-bootstrap-header-closure.patch`](https://gist.githubusercontent.com/crutkas/e5d1ddc3410c418069046455c99ad09b/raw/2e289a9653932466afe56102fb8b713efae9d50c/pr11-crt-bootstrap-header-closure.patch) |
| Separate evidence | Commit `de2353205ee2aece40435047a89cc6377fe47460`, `arm64-vnext/evidence/execution-recovery/`, including `crt/closure-receipt.json` and its controls |
| Integration status | Source remains **UNCOMMITTED and NOT applied to PR 11** at preservation time. A remote patch copy is not an integrated source commit. |
| Qualification scope | **Locally qualified CRT bootstrap header closure only. No CI rerun claim.** Do not inherit the earlier Texinfo CI pass for this additional patch. |
| Access caveat | **Unlisted is not access-controlled:** anyone holding the gist URL can read it. This was an explicitly accepted preservation tradeoff, not a promise of private storage. Keep the URL in the recovery set; never use this method for credentials or secrets. |

Download without changing source, and fail closed on the exact identity:

```powershell
$url = 'https://gist.githubusercontent.com/crutkas/e5d1ddc3410c418069046455c99ad09b/raw/2e289a9653932466afe56102fb8b713efae9d50c/pr11-crt-bootstrap-header-closure.patch'
$patch = Join-Path (Get-Location) 'pr11-crt-bootstrap-header-closure.patch'
if (Test-Path -LiteralPath $patch) { throw 'Choose a fresh preservation path' }
Invoke-WebRequest $url -OutFile $patch
$hash = (Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant()
if ((Get-Item -LiteralPath $patch).Length -ne 13915 -or
    $hash -ne '4cc4f5387496e86911a56bef3c1fa1d690c57bf5f07888f441a9bd8747efe5d4') {
  throw 'CRT patch identity mismatch; do not apply'
}
```

Before any application, recover the producer's base/input contract, inspect
the patch and run `git apply --check` only in a new owned checkout at that base.
Clean application is not content correctness or qualification. Application,
commit, integration and a new CI run are separate future actions requiring
their own authority and evidence.

### Published source rescue: dependency-closure producer

The evidence-only exclusion was subsequently repaired by a **separate source
preservation**, not by pretending the earlier evidence commit contained code.
PR 17 successor **`0da6e92a060e11144ba2ded1a6962096963615a2`** adds
`arm64-vnext/evidence/dependency-closure/source-recovery/`; original evidence
commit **`7368ba69e60e7092792c10ee5f1c5c8aea3923da`** remains unchanged.

| Source-recovery item | Identity and scope |
|---|---|
| Current working-tree patch | `current-working-tree.patch`, **636,626 bytes**, SHA-256 **`931096cb524f6c7d53ff1ba627fc47773d9aee32021e2486627703a8688e367a`**, exact base **`7368ba69e60e7092792c10ee5f1c5c8aea3923da`**. Preserves **158 files: 20 tracked modifications + 138 untracked files**, including exact raw line endings. |
| Source inventory | `source-inventory.json`, SHA-256 **`5ddb66aca2fea065066027d710e9867b73439c5a0125e86d307aeb3cbf6a245f`**. Also inventories **18 session-local qualification/audit/diagnostic scripts** under `session-source/`. |
| Historical checkpoint rescue | `checkpoint-recovery.json`, SHA-256 **`aac88f842bd0977808391179b568e746824741a784385e90901e7e01d6da94bb`**; maps **99 own-session checkpoint refs** to ref/commit/path/mode/blob/SHA identities and **115 additional historical source blobs** under `checkpoint-source/`. |
| Captured Git state | Owner recorded zero staged changes, zero local-only HEAD commits and zero stashes; the dirty working files were preserved **without reset**, not declared clean. |
| Qualification boundary | **Archival patch, NOT a blanket qualified change.** Scoped completed PCRE2/native907 less/tools results remain separately evidenced. Imported generic pipeline code, diagnostic scripts and intermediate checkpoints are not independently qualified or recommended fixes merely because they were rescued. |

The patch and both manifest hashes above were independently verified from
immutable GitHub raw bytes by this guide's publisher. The producer reports
exact 158-file restoration via an isolated temporary index; that restore was
not rerun by the guide's publisher. Use the source README's binary/full-index
patch instructions in a **new checkout at the exact base**, then compare every
restored file against its source inventory. Do not apply the mixed patch to a
live toolchain/worktree or overlay every checkpoint version together.

### Subsequent direct source publication on the same PR

PR 17's later commit **`e5f5b4c1ffb7c090fd38661b7b1be2458aeb2aea`**, a direct
child of `0da6e92a060e11144ba2ded1a6962096963615a2`, publishes **153 live
source/script/documentation files: 15 tracked modifications + 138 additions**.
Including its manifest, this commit changes **154 files**, not 154 newly
qualified source files. These 153 files are now present directly at their
repository paths; the earlier mixed source patch remains an archival record.
**Do not reapply that whole patch over the direct-publication checkout.**
The earlier 158-file recovery snapshot and this 153-file direct publication
are different inventories; retain both rather than conflating their counts.

The portable manifest is
[`arm64-vnext/evidence/dependency-closure/source-recovery/direct-source-publication.json`](https://github.com/crutkas/msys2-woarm64-build/blob/e5f5b4c1ffb7c090fd38661b7b1be2458aeb2aea/arm64-vnext/evidence/dependency-closure/source-recovery/direct-source-publication.json),
SHA-256 **`d61a5610319d73cff336f8d9a32a5c086983f5d2d490ef26ffc2fcc4376e2c10`**.
It binds raw bytes, modes and Git blob IDs and records that all 153 files
already had byte-identical copies in the earlier recovery patch. This guide's
publisher downloaded and verified the manifest and matched its 153 paths to
the GitHub commit's changed-file list, not replayed every file restoration.

The owner reports fresh immutable-URL downloads of **all 154 published files**,
with byte counts/SHA-256 matching the originals, and reports remote-read
receipt SHA-256
`bd3cac1b243e17810835398c359cc84750b0dbd3ae1b4017b966cfe0a942bd15`.
No portable location for that separate readback receipt was supplied to this
guide; it is not independently verified here. The published manifest records
the verification procedure, not the subsequent result. **Published source is
not merged or newly qualified source**: no build/test rerun accompanied this
shutdown publication, imported generic pipeline code remains unqualified by
this leaf, and completed PCRE2/native907 less/tools outcomes remain bounded by
their separate original receipts.

### Source-custody checklist for each owner

Before a wipe, each owner must inventory its **own** tracked working-tree
changes, untracked/ignored source, staged changes, local-only commits, stashes,
reflogs and checkpoint objects. Merely checking remote branches or evidence
directories is insufficient. After a wipe these local objects may be gone;
the checklist is a discovery obligation, not a claim they can be reconstructed.
Preserve any required source with its base commit, exact path/mode/bytes/hash,
patch or archive, remote locator and explicit applied/unapplied status.
Review for secrets before publishing; do not sweep or modify other worktrees
without owner authority. **No known gap may be silently converted into "source
complete" because the evidence manifests verify.**

## 2. Source PR map and agreed merge order

These are the eight engineering/continuity PRs, still open at the pre-shutdown
snapshot, plus later evidence and source-rescue publications. Some commits only
add evidence; PR 17's direct source publication also changes live source paths
without newly qualifying them. Re-query the GitHub
API for live heads, bases, checks and mergeability; do not use stale counts as
merge authority.

| Repository / PR | Qualified or assessed source head | Base branch |
|---|---|---|
| [crutkas/msys2-runtime#32](https://github.com/crutkas/msys2-runtime/pull/32) | `c30a9e8993a9bf326fac4bd934028b327d935c91` | `crutkas-arm64-vnext/msys2-runtime/generator` |
| [crutkas/msys2-runtime#33](https://github.com/crutkas/msys2-runtime/pull/33) | `563662010c2f2072ad90f28713611caabdf70dbb` | `crutkas-arm64-vnext/msys2-runtime/generator` |
| [crutkas/msys2-runtime#34](https://github.com/crutkas/msys2-runtime/pull/34) | `df7d66f9b1433c50dd7cd234b0d8bd1213418b22`; evidence-only publications `fb627b685141eea8bd7e7813837e4b21c754dc35` then `2af0ec0c244f522b65ace15be71deab4f3c528ad` | `crutkas-arm64-runtime-integration` (PR 33) |
| [crutkas/msys2-woarm64-build#11](https://github.com/crutkas/msys2-woarm64-build/pull/11) | `a0b773dbd64b4542d9b8de05911d23af51e87c25` | `crutkas-arm64-vnext/msys2-woarm64-build/reformat` |
| [crutkas/msys2-woarm64-build#12](https://github.com/crutkas/msys2-woarm64-build/pull/12) | `3834bd94d142e070eecd791627c290febc1773f6` | `crutkas-e2e-arm64-git-roadmap` |
| [crutkas/msys2-woarm64-build#13](https://github.com/crutkas/msys2-woarm64-build/pull/13) | `4ff861de52ae8ec5fb36fd1d853f916bb1b21640`; earlier package head `ca76d555a6c10caeccd778fd9c105d581f82b19d` | `main` |
| [crutkas/msys2-woarm64-build#14](https://github.com/crutkas/msys2-woarm64-build/pull/14) | `d618c2d5d6d410b6e98b643d7262f4eb8d8072c5` | `crutkas-e2e-arm64-git-roadmap`; **DRAFT** |
| [crutkas/msys2-woarm64-build#15](https://github.com/crutkas/msys2-woarm64-build/pull/15) | Initial reconciliation `c60dd251533e85e15ab29fb43a9a5a7c0004bbe7`; this document/evidence are later preservation work | `crutkas-arm64-vnext/msys2-woarm64-build/reformat` |

**Runtime sequence: 32 -> reconciled 33 -> incremental 34.** PR 33 incorporates
PR 32's mechanical production changes through `846c26818d0594f8f872aae9258abb00f52d592a`
**by CONTENT, not ancestry**; their merge base is
`d890a845e992638a6f09560efacc26d15b3ffe6a`.
Five shared production files are identical, but not every test/helper is present.
`winsup/testsuite/Makefile.am` needs a **union, not a clobber**, retaining PR 32's
argv/exec-path/exit-contract registrations and helper files plus PR 33's
runtime/ARM64/import/host-test wiring. `winsup/cygwin/spawn.cc` in PR 33 retains
PR 32's fixes **and adds the foreign-architecture MSYS/Cygwin environment block**;
do not erase `newargv.same_arch` handling by taking PR 32's whole file.

PR 34 changes only `winsup/cygwin/Makefile.am`,
`winsup/cygwin/scripts/guard-runtime-generation`, and
`winsup/testsuite/build/runtime-generation-make.py` relative to qualified PR 33.
If PR 33 is rebased away from `563662`, restack only the incremental source
change (and preserve evidence separately), not the entire combined-runtime
commit. Source/base changes require fresh successor identity and appropriate
validation; old proofs cannot be rebound to new bytes.

**Build sequencing:** validate and propagate the isolated four-file Texinfo CI
fix, consume PR 12's exact observer contract, integrate DB with its explicit
scope, and leave the final MVP PR 14 until payload/provenance/behavior gates
close. PR 15 is independently mergeable documentation/evidence, not runtime
admission. Parent continuity PR 10 and runtime-generator PR 31 were still draft;
merging children into their feature bases is not landing everything on defaults.

**PR 13 / PR 14 conflict:** both add
`arm64-git-recovery/native/bounded_process.py` with different semantics.
The agreed resolution is **PR 14's retained child handles, `IsProcessInJob`
identity check and bounded process-teardown waits after job accounting drains**,
with both branches' focused tests run on the new integrated source. Do not
clobber whichever lands first. `test_bounded_process.py` differs only in raw
CRLF/LF bytes (66 CRLF in PR 13, LF in PR 14); preserve both receipt-bound
versions and record a new canonical hash. **Do not normalize sealed evidence
or use blanket `tr -d '\r'`**: only a deliberately specified trailing-CR
transport rule is allowed where required, since embedded CR may be meaningful.

Live-reader holds were per process generation, not permanent locks. DB's old
controller `12052` completed and drained; runtime-generation owner had a private
frozen copy and no live readers. Other outstanding owner acknowledgments were
not inferred. After reformat, reconstruct current state and obtain explicit
authority; none of these old PIDs or approvals grants a new merge/installation.

## 3. What is proven, with the correct scope

| Result | Evidence and boundary |
|---|---|
| Native ARM64 runtime links, runs and reproduces | Combined DLL SHA-256 `907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`; two independent 12-job builds yielded eight bit-identical artifacts. Exact handoff `f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b` is preserved here. Newlib/compiler backends were reused, not rebuilt; not universal ABI/SDK/product admission. |
| Real public Git HTTPS clone from a relocated path with spaces | Independent named-ZIP replay cloned `https://github.com/octocat/Hello-World.git`, raw **0**, commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`, clean status/fsck, five process generations observed. No verifier CA/PATH/artifact repairs. Its **shipped** `http.sslCAInfo=%(prefix)/etc/ssl/certs/ca-bundle.crt` worked. The superseded TLS pair still loaded; this is not replacement-TLS admission. |
| Exact named-archive recreation | Shipped tooling, executed independently from a fresh moved extraction, recreated SHA-256 **`7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854`**, **186,366,963 bytes**. Five observed copies matched. This is **archive repackaging determinism, not rebuilding Git/runtime binaries from source**. Archive binary custody is not established by a hash alone. |
| Static native shape | The distinct audited generations contained **333 and 327 ordinary AA64 PEs**, with zero unresolved static imports. The separately measured MinGW graph has zero MSYS imports. Do not combine static shape with complete dynamic module coverage or admission; live HTTPS reached the unadmitted crypto pair. |
| Exact documentation leaf | 273 HTML pages + 210 manpages generated with genuine native Ruby/Asciidoctor, installed/read back. Six original signed CLANGARM64 runtime packages, real Asciidoctor package and full original 758-member packet are preserved here. Ruby is honestly Clang-built; XML build drivers remain emulated MSYS. |
| DB long-matrix resolution | **24/24** completed in **3,733.7 seconds**, **314/314** process generations observed, CuTest raw **0**, no timeout, unchanged workload/input hashes. This is **D70 composition only**, not runtime `907afa` or full provider qualification. Preserve the original failure and resolution together below. |

Independent verification primary seals, under the PR 16 evidence root:
`records/independent-tls-evidence-01.json`
`94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc`,
and `records/report-01/report.json`
`c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b`.
Its README/index locates all original observations and failed harness attempts.
Tcl/Tk were excluded from that verifier's verdict for conflict-of-interest
reasons; do not count their presence as independently qualified functionality.

## 4. What is broken, withheld or not yet established

**OpenSSL provenance is a live defect, not a cosmetic manifest mismatch.**
Candidate-01, peer candidate-02 and the named ZIP were reported/observed to ship
the superseded pair; PR 16's own replay covers candidate-01 and named ZIP,
while the peer/assembly record supplies candidate-02. Live Git HTTPS loaded:

| Identity | Exact SHA-256 |
|---|---|
| Superseded `libssl-3-arm64.dll` | `819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` |
| Superseded `libcrypto-3-arm64.dll` | `0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a` |
| Superseded, unadmitted archive | `256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3` |
| Admitted replacement archive, **not established as substituted/replayed** | `02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab` |
| Replacement admission export | `4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62` |

The assembler (`f6ea7713`) owns constructing a **new** frozen candidate with
the admitted inputs. Intake retains admission authority. Do not patch old
evidence, silently swap DLLs in the tested generation, or claim the replacement
works because the old pair succeeded. Full payload/member hashes and independent
relocated HTTPS/live-module replay must bind the new candidate.

**CA behavior is generation- and program-specific.** Candidate-01 Git clone
failed raw **128**: `libcurl-4.dll` contains the absolute
`/mingwarm64/etc/ssl/certs/ca-bundle.crt` literal at byte offset **1,117,512**.
The named ZIP's shipped `%(prefix)` Git configuration avoids that path for Git.
Standalone shipped **`curl.exe` still failed HTTPS raw 77 in both independently
tested generations**. Git config does not configure the curl CLI. Never
disable certificate checking or give the verifier an undisclosed repair.

**Bash Ctrl-C remains unresolved.** The coordinator reports `$?` **0 rather
than 130** for Ctrl-C on `sleep 60 | cat`. The leading hypothesis is that exec'd
pipeline members fail to join the job process group. This is a hypothesis,
not a proven root cause or completed fix; recover the runtime owner's PTY/
process-group evidence and measure actual groups/forwarded signals/native exit
status before changing code. A successful redirected CMD launch is not PTY or
interactive job-control certification.

**Berkeley DB correction: the matrix did finish.** The earlier record says
**900-second timeout at case 9/24, 83-created/76-recorded partial coverage**.
That remains historical evidence. It is **RESOLVED as an insufficient bound**
for this unchanged workload: the complete D70 matrix needed **3,733.7 seconds**
within a 7,200-second bound, with approximately **15 ms timer quantization**
dominating microsecond-scale yield requests. Timing comparisons covered both
runtime compositions, but the **24/24 functional result is D70-scoped only**.
No mutex-alignment/contention correctness failure was observed; this does not
prove the absence of every ordering bug or qualify the full SDK/provider.
Preserved timing handoff:
`programme-reconciliation/source-receipts/db-d70-timing-handoff.json`,
SHA-256 `406c1c7d6ee5242fe888140b132d452771677380d6b0b76323bc625922a1c34f`.
Underlying full result:
`805143b08af0912ac6ff5701141763f26df8ec48364df0a4960e58ee7750bc2b`.
D70 is `d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d`,
not `907afa...`. Later briefings calling this unfinished were stale and corrected.

Keep these other limitations: no qualified Perl provider across the UCRT
compiler's raw `!<symlink>` file-access boundary; `core.symlinks=false` does not
fix that. Coreutils' retained 48 PASS / 41 FAIL / 23 SKIP / 4 ERROR is not a full
provider admission. Portable native Win32-OpenSSH is not a native MSYS provider.
Limited libintl admission is two C DLLs plus six licenses; its default
`/clangarm64/share/locale` CLI lookup failed before/after moves. Retained PCRE2
10.48-1 lacks a signed-source/repro receipt and cannot be replaced by renaming
10.48-3's incompatible `libpcre2-8-0.dll`.

**Later helper evidence, not a retroactive artifact upgrade:** the newly
published helper branch above records a separately admitted **runtime907,
exact-dependency-scoped, client-only native MSYS OpenSSH provider-03**. Preserve
this later scope rather than repeating the old global "no native MSYS provider"
snapshot as current. It does not show that the historically tested portable-SSH
artifact was replaced or that full GSSAPI/server/release integration completed.
Likewise its clean runtime907 GMP admission cannot be consumed with selected
d70 GMP: ledger v42 records that package conflict, and interrupted GnuPG/
libgcrypt work remains unfinished.

## 5. The strict blocker truth: 81, not 59

For the authoritative **historical v18 audit, the verdict remains 81**.
Exactly **22** rows are gettext-related: **21 DLL edges naming the one
`libintl-8.dll` plus one strict GNU gettext package-identity obligation**.
**59 is only a hypothetical remainder conditional on all 22 strict gates
genuinely resolving.** Limited libintl and PCRE2 projections do **not** clear
the strict package identity/transaction gate. The 59 are **overlapping provider,
file/path and evidence obligations**, not 59 independent implementations and
not an effort estimate. The programme is not one DLL away from a full release.

Use PR 17's immutable `closure/delivery-01/blocker-breakdown.json`,
`dll-admission-table.csv`, `remaining-59-blockers.csv`, and
`authority/ap11-native-provider-intake--audit-v18-qualified-openssl.json`.
Preserve later audits separately; a later ledger or unrelated admission does
not silently rewrite v18 or authorize subtraction from its count.

## 6. Two separate CI blockers; only one is fixed

**Verified cross-binutils success:** run **34571963232**, job **103176510972**,
head **`a0b773dbd64b4542d9b8de05911d23af51e87c25`**, conclusion **SUCCESS** at
**2026-09-11T07:21:17Z**. Genuine Texinfo `7.2-3` was installed; the non-empty
Info preflight passed; `MAKEINFO doc/bfd.info` ran; binutils `2.44dev-1` finished
and artifact `10188860473` uploaded. The exact success handoff/log are preserved
here (`texinfo-success-handoff.json` SHA
`1cce75264489dcec3e7afb48ca95e9f9f6da9095ca3bab8a889f090dc0ebdaeb`).

The `Makefile:1782`/Error 127 failure reproduced across five reported independent
commits; two old base/head logs were independently checked. The proven cause:
PKGBUILD `!ccache` overrides BUILDENV, hiding the old makeinfo-to-`true` stub
under `/usr/lib/ccache/bin`, while real Texinfo was missing. The `.lnk` and
cache-clobber theories were refuted, not left as open alternatives. The fix
installs real Texinfo, removes the stub and requires real non-empty Info output.

This closes that defect **on the verified fix branch/run only**. PR 11 targets
`reformat`; PR 13 targets `main`; PR 12/14 target `roadmap`. Merging PR 11 alone
cannot deliver the fix to those other bases. The coordinator chose isolated
CI-only propagation after real success (now satisfied), not moving parents or
ferrying all of PR 11. Confirm which branches actually incorporated it and
which new checks ran. Do not infer propagation or full downstream success.

**Hard infrastructure blocker, still separate:** the repository runners API
returned **zero registered self-hosted runners**. Seven native-toolchain jobs
require labels **`Windows`, `ARM64`, `MSYS2`** and cannot start while no matching
runner exists. They are **queued for infrastructure**, not the six downstream
cross jobs **skipped because binutils failed**. Native CI did not execute and
cannot be claimed verified. Resolution requires the **user/authorized
infrastructure owner** to register and operate a matching runner. No session
should register credentials/runners unilaterally.

## Shutdown triage: do not confuse diagnosis with completion

| State | Item | Exact boundary / next action |
|---|---|---|
| **RESOLVED** | Cross-binutils Texinfo failure | Actual run `34571963232` succeeded on `a0b773d`. Isolated propagation to other bases is separate and must be confirmed. |
| **RESOLVED, D70 ONLY** | Berkeley DB apparent hang / timeout | Unchanged 24/24 matrix finished in 3,733.7 seconds; approximately 15 ms yield timing explains the insufficient 900-second bound. Not a 907afa full matrix or provider admission. |
| **RESOLVED FOR NAMED ZIP, NOT CANDIDATE-01** | Git CA relocation | The named ZIP's shipped `%(prefix)` Git config works. Candidate-01 raw 128 remains a preserved failed generation. |
| **OPEN** | Superseded OpenSSL and standalone curl | Admitted-TLS candidate/replay not established; shipped curl HTTPS raw 77 is not fixed by Git's CA setting. |
| **OPEN** | Bash pipeline Ctrl-C | Wrong status 0 vs 130 is observed; exec/process-group membership is the leading hypothesis, not an implemented fix. |
| **OPEN** | Coreutils failures | Retained 41 failures were reported by the coordinator as clustering into approximately five causes. This is a reported diagnostic grouping, not 41 independent implementation tasks, an enumerated verified root-cause list, a completed fix, or provider admission. Recover the utility owner's evidence before acting on the grouping. |
| **AWAITING USER DECISION** | Native CI infrastructure | Zero matching self-hosted runners; registration/credentials and operation require user authorization. No native-CI pass is claimed. |
| **AWAITING USER DECISION** | Merge, admission and release | The sequence is agreed; performing merges, publishing an admitted artifact and changing infrastructure remain explicit decisions. Evidence preservation is not those decisions. |

## 7. Corrections and guardrails that must survive restart

- The "~500 lines of unwritten AArch64 trampoline assembly" critical-path
  diagnosis was **false**. ARM64 `gendef` already existed as abbreviated
  `180d3e`; wrong selection of x86-only `74f502` produced **zero-byte `sigfe.s`
  with Perl exit 0**. The original claim and adjacent correction are preserved
  in `plan.md`. Verify actual selected source/output, not just exit 0.
- `gentls_offsets` matched `.long` while ARM64 GCC emitted `.word`: correct
  1,822-byte/59-entry offsets (`49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566`)
  could become a **56-byte text file declaring two zero offsets**.
  **Wording correction:** earlier summaries called this "56 zero bytes" or
  "56 bytes of zeros"; it is **not 56 NUL bytes**. The text is
  `.equ _cygtls.local_clib, 0` followed by `.equ _cygtls.local_clib_p, 0`,
  each newline-terminated: plausible assembly with missing/nonrepresentative
  offsets, not an obvious binary-garbage file. The original 16-case guard also
  missed the changed-generator-plus-corrupt-prior-output case: old Make
  **silently replaced the corrupt prior `sigfe` and exited 0 rather than
  rejecting it**. The evidence does not say the replacement assembly remained
  corrupt. PR 34's successor validates prior
  output hashes **before** input comparison; 26 actual-Make + 40 TLS cases are
  distinct successor evidence, not a retroactive upgrade of the 16-case proof.
- Keep raw unsigned Windows DWORD exits. PR 12 interprets POSIX wait words
  only under source/image/parent/generation-bound contracts: raw 32256/1792
  passed when contracted and failed identically when uncontracted. No blanket
  normalization shim. The dedicated Bash-hook raw-256 fixture is separately
  bound; do not extend its permission to arbitrary descendants.
- The V10 `verdict.json` was unavailable on disk; its historical GO narrative
  is only secondhand via the original checkpoint `inbox.md` line 16. A mentioned
  hash is not a recovered authority receipt. Do not resurrect consumed grants.
- "Green retry" is not "all attached checks green": runtime PR 33's failed
  libpsl-signature mirror job remained attached beside the successful same-SHA
  rerun. API snapshots distinguish actual success, failure, skip and queue.
- Old absolute paths, PIDs, source identities and receipt bytes stay unchanged
  as history. New roots, source changes or rebuilt binaries need new identities
  and appropriately scoped evidence. No fake package provides, renamed
  incompatible DLLs, disabled signature/native gates or verifier repairs.
- **Receipts govern over summaries, including coordinator summaries.** Several
  shutdown briefings were stale or wrong and were corrected by the owners of
  the actual measurements. Keep those corrections visible, re-derive counts
  from the bound record, and retain explicit scope flags rather than defending
  an authoritative-sounding headline.
- **Absence from a coordinator's index is not evidence of absence.** The
  coordinator identifies the false `tlsoffsets.good` custody claim above as
  their ninth correction that day and second absence claim from an incomplete
  search. Inspect the contents and exact hashes of published trees before
  telling an owner they failed to preserve an artifact; counting directory
  names is not a content search.
- **The same error also produced the retracted "eight owners pending" count.**
  A recursive content-level sweep found the Berkeley DB timing finding at a
  non-canonical source-documentation path already on GitHub. Keep that
  correction prominent: canonical-path absence is not repository absence,
  and incomplete searches must not become accusations against owners.

## 8. First actions for a fresh session

1. Recover this branch and the evidence branches above; verify manifests and
   both the coordinator fallback and the separate patch/gist source-recovery
   set, plus any verified off-machine backup, then inventory what
   binary/toolchain/source custody actually survived. Record
   missing objects explicitly. Do not fabricate a successful rebuild from a
   recipe or a SHA-256 alone. Search complete branch-tree contents, including
   non-canonical source/documentation paths, before declaring anything missing.
2. Re-query current PR heads, bases, CI and runner availability. Preserve the
   runtime merge order and both shared-file hazards; request a new work budget
   and merge/admission decisions from the user before acting.
3. Obtain or rebuild a **new candidate from admitted OpenSSL inputs** with
   complete member provenance. Repeat independent moved-path public Git HTTPS
   and standalone curl tests, recording live loaded modules and raw exits.
   Keep the named ZIP's old success and old-crypto defect as the baseline.
4. Continue the Bash Ctrl-C/process-group investigation with owner evidence and
   proper positive/negative controls. Do not call redirected-shell success
   interactive job-control qualification.
5. Reassess the strict audit as a new explicit version; preserve the 81/22/
   conditional-59 explanation. Final archive admission/release, native runner
   registration, credential/GUI/Perl/native-MSYS-SSH completion remain separate
   decisions, not consequences of successful basic Git commands.
