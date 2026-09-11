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
```

Read the evidence directory on each fetched branch. Do not merge branches just
to make evidence visible. An isolated detached worktree at a recorded commit
is sufficient, for example:

```powershell
git -C .\build-recovery worktree add --detach ..\verification-evidence `
  bfea25a4fe7703d602b8d4282b75fc064ee8ee59
git -C .\build-recovery worktree add --detach ..\closure-evidence `
  7368ba69e60e7092792c10ee5f1c5c8aea3923da
git -C .\runtime-recovery worktree add --detach ..\generation-evidence `
  2af0ec0c244f522b65ace15be71deab4f3c528ad
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

| Topic / owner | Repository, branch / PR | Portable evidence and publication status |
|---|---|---|
| Master continuity, Ruby/Asciidoctor, merge-readiness (`ab17e048`) | `crutkas/msys2-woarm64-build`, `crutkas-arm64-ruby-documentation`, [PR 15](https://github.com/crutkas/msys2-woarm64-build/pull/15) | This branch: `arm64-vnext/evidence/ruby-asciidoctor/` and `arm64-vnext/evidence/programme-reconciliation/`. Complete original Ruby packet, six signed upstream runtime archives plus real Asciidoctor package, exact generated documentation, source archives, API/owner records and primary receipt backups. See their READMEs and `preservation-manifest.json`. |
| Independent moved Git/HTTPS/TLS/ZIP verification (`b1b1deaf`) | Same build repo, `crutkas-native-tcl-qualification`, [PR 16](https://github.com/crutkas/msys2-woarm64-build/pull/16) | **Published** `bfea25a4fe7703d602b8d4282b75fc064ee8ee59`: [`arm64-vnext/evidence/independent-verification/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/bfea25a4fe7703d602b8d4282b75fc064ee8ee59/arm64-vnext/evidence/independent-verification/README.md). 227 preservation files; original records indexed by `index.json`. This export deliberately excludes artifact ZIPs, binaries and extracted payloads. |
| Strict blocker and DLL closure audit (`accd408a`) | Same build repo, `crutkas-arm64-pcre2-package`, [PR 17](https://github.com/crutkas/msys2-woarm64-build/pull/17) | **Published** `7368ba69e60e7092792c10ee5f1c5c8aea3923da`: [`arm64-vnext/evidence/dependency-closure/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/7368ba69e60e7092792c10ee5f1c5c8aea3923da/arm64-vnext/evidence/dependency-closure/README.md). `preservation-index.json` maps 231 original paths to 230 exact evidence files. Start at `closure/delivery-03/report.md`, preserving delivery-01/02 and their older seals. No runtime/package binaries are included. |
| Atomic runtime generation (`e6a17275`) | `crutkas/msys2-runtime`, `crutkas-atomic-runtime-generation`, [PR 34](https://github.com/crutkas/msys2-runtime/pull/34) | **Published standardized recovery root** at `2af0ec0c244f522b65ace15be71deab4f3c528ad`: [`arm64-vnext/evidence/atomic-generation/README.md`](https://github.com/crutkas/msys2-runtime/blob/2af0ec0c244f522b65ace15be71deab4f3c528ad/arm64-vnext/evidence/atomic-generation/README.md). Preserves original 50-file proposal baseline plus all 170 application files; baseline archive SHA `19d273f86f14b9b3beb5debaa9f1309683f79bff242e8bf78ab363632d8d85c5`. Application `proof.tar.gz` remains SHA `2abaa10780ef6e287a2bd90f424d599771aa7db1d72faf354ed81af7557f1c84` (269,076 bytes). The earlier `fb627b685141eea8bd7e7813837e4b21c754dc35` / `winsup/testsuite/build/evidence/runtime-generation-20260911/` locator remains valid. Qualified source remains `df7d66f9b1433c50dd7cd234b0d8bd1213418b22`; both later commits are evidence-only. |
| Combined runtime, Bash/PTY investigation (`67ba2e76`) | Runtime repo, `crutkas-arm64-runtime-integration`, PR 33 | Owner preservation requested; confirm its final evidence-publication commit/path before claiming the complete runtime/toolchain/build tree survives. A byte-exact `combined-runtime-handoff.json` backup is already in this branch's `programme-reconciliation/source-receipts/`. |
| Signal/myfault/Texinfo producer (`5b01b4e5`) | Build repo, `crutkas-arm64-toolchain-bootstrap`, PR 11 | Owner preservation requested. This branch already preserves exact Texinfo root-cause/success handoffs, actual successful binutils log, old TLS proposal handoff and known-good TLS offsets under `programme-reconciliation/source-receipts/`. Complete producer environment custody must come from the owner export. |
| Mechanical/runtime exit contracts (`0af73d1b`) | Runtime PR 32 and build `crutkas-native-exit-observer-contract`, PR 12 | Qualified source is pushed at the heads below. Complete native proof publication locator has not yet been confirmed to this document; inspect those branches' new evidence directories. Do not mistake source/tests alone for preserved native execution receipts. |
| Berkeley DB (`2f98bedd`) | Build repo, `crutkas-native-berkeley-db`, PR 13 | Root-cause source is published at `4ff861de52ae8ec5fb36fd1d853f916bb1b21640`. Owner evidence publication requested. Exact completed D70 matrix and timing handoffs are backed up here in `programme-reconciliation/source-receipts/`; complete package/SDK custody requires the owner's export. |
| MVP assembly and replacement-TLS candidate (`f6ea7713`) | Build repo, `crutkas-full-native-git-assembly`, draft PR 14 | Owner evidence publication requested. Qualified candidate/ZIP binary preservation is **not confirmed here**; do not assume the 186 MB named ZIP is in Git. Independent verification and dependency-closure exports above preserve measured identities and failures even if a binary must be rebuilt. |
| Provider ledger/admission (`a2dd0a44`, pipeline `2160ef10`) | Build repo, `crutkas-native-provider-intake` | **Published and remote directories confirmed** at `3ebc0c133105c77496ae80d4ea76fad7ed463c80`: [`arm64-vnext/evidence/provider-intake/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/3ebc0c133105c77496ae80d4ea76fad7ed463c80/arm64-vnext/evidence/provider-intake/README.md) covers ordered contracts, rejected libintl-selection captures and limited roles; [`arm64-vnext/evidence/provider-admission/README.md`](https://github.com/crutkas/msys2-woarm64-build/blob/3ebc0c133105c77496ae80d4ea76fad7ed463c80/arm64-vnext/evidence/provider-admission/README.md) covers strict authority, OpenSSL/header scopes and ledger v20-v42. Provider-intake `manifest.json` SHA-256 `df94ef731519e129e1dde7b497be7b501726366c2326b85b3f0f9291b1f8c65e` was verified from GitHub bytes. **No archives or payload binaries** are included: replacement OpenSSL payload custody is still separate. |

**Publication gaps are explicit, not absence claims.** Owners were pushing in
parallel during shutdown. If an entry says requested/unconfirmed, inspect that
branch's latest `arm64-vnext/evidence/` or documented alternate directory and
record its exact commit/hash before using it. Do not invent a completed backup.

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

## 2. Source PR map and agreed merge order

These are the eight engineering/continuity PRs, still open at the pre-shutdown
snapshot, plus later evidence-only publications. A preservation commit can
advance a PR head without changing its qualified source. Re-query the GitHub
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
  could become 56 bytes of zeros. The original 16-case guard also missed the
  changed-generator-plus-corrupt-output case. PR 34's successor validates prior
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

## 8. First actions for a fresh session

1. Recover this branch and the evidence branches above; verify manifests and
   inventory what binary/toolchain/source custody actually survived. Record
   missing objects explicitly. Do not fabricate a successful rebuild from a
   recipe or a SHA-256 alone.
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
