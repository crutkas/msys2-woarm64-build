# Recovery procedure

Run these commands from PowerShell 7 or Git Bash as indicated. They use only
repository-relative or operator-selected paths.

## Fetch this checkpoint and its PR

```powershell
gh repo clone crutkas/msys2-woarm64-build
Set-Location msys2-woarm64-build
git fetch origin refs/heads/crutkas-arm64-vnext/msys2-woarm64-build/reformat
git switch --detach FETCH_HEAD

$Pr = gh pr list `
  --repo crutkas/msys2-woarm64-build `
  --state open `
  --head "crutkas:crutkas-arm64-vnext/msys2-woarm64-build/reformat" `
  --json number `
  --jq '.[0].number'
if (-not $Pr) { throw "Continuity PR not found" }
gh pr view $Pr `
  --repo crutkas/msys2-woarm64-build `
  --json number,url,state,isDraft,baseRefName,headRefName,headRefOid,labels
```

Set the checkpoint directory after checking out the frozen head:

```powershell
$Checkpoint = Resolve-Path .\arm64-vnext\continuity\2026-08-31-v1
Set-Location $Checkpoint
```

## Verify file hashes and canonical JSON seals

Git Bash:

```sh
sha256sum --check SHA256SUMS
```

PowerShell 7 with Python 3:

```powershell
python -c "import glob,hashlib,json,sys; fs=glob.glob('state/*.json'); bad=[]; [(lambda o,p,e,a: bad.append((p,e,a)) if a != e else print('PASS',p,a))(json.load(open(p,encoding='utf-8')),p,(lambda o:o['seal']['payload_sha256'].lower())(json.load(open(p,encoding='utf-8'))),(lambda o:hashlib.sha256(json.dumps(o['payload'] if set(o)=={'payload','seal'} else {k:v for k,v in o.items() if k!='seal'},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())(json.load(open(p,encoding='utf-8')))) for p in fs]; sys.exit(str(bad) if bad else 0)"
```

Expected result: 14 `PASS` lines, including continuity payload SHA-256
`d2f16dc11c9cf917e2c51fdfb8da40859a9e85720bd06c79fd5701b78cf6d777`.

## Recreate the eight projects

Choose an empty parent directory and run:

```powershell
$Repos = @(
  "crutkas/binutils-woarm64",
  "crutkas/build-extra",
  "crutkas/busybox-w32",
  "crutkas/gcc-woarm64",
  "crutkas/mingw-w64",
  "crutkas/MSYS2-packages",
  "crutkas/msys2-runtime",
  "crutkas/msys2-woarm64-build"
)
foreach ($Repo in $Repos) { gh repo clone $Repo }
```

Add these local clones as projects in the Copilot app. Do not reuse old
worktrees or old vNext/POC refs.

## Fetch and verify the existing code PRs

```powershell
Set-Location busybox-w32
gh pr checkout 4
if ((git rev-parse HEAD) -ne "942be1cd339f2fa5c426d28a83dad62b2b366d5e") {
  throw "busybox-w32 PR #4 head mismatch"
}
gh pr view 4 --json isDraft,baseRefName,headRefName,headRefOid,labels,reviewRequests,autoMergeRequest,state,statusCheckRollup

Set-Location ..\build-extra
gh pr checkout 29
if ((git rev-parse HEAD) -ne "305d14d63db6073245ad4e3002f7400e58040c55") {
  throw "build-extra PR #29 head mismatch"
}
gh pr view 29 --json isDraft,baseRefName,headRefName,headRefOid,labels,reviewRequests,autoMergeRequest,state,statusCheckRollup
```

Both must remain draft and labeled only `arm64-vnext`. Stop on any identity or
authority drift.

## Replay the runtime patch in isolation

From Git Bash, set `CHECKPOINT` to this checkpoint directory:

```sh
CHECKPOINT="$(pwd)"
cd ..
gh repo clone crutkas/msys2-runtime runtime-generator-replay
cd runtime-generator-replay
git checkout --detach 8fbd9808447ee78ed485deead9b79cd1e40c07b7
test "$(git rev-parse 'HEAD^{tree}')" = fe1106187ef9aa842e1cff0ccc4f978b65c16613
test -z "$(git status --porcelain)"

PATCH="$CHECKPOINT/state/arm64-vnext-2026-08-31-v1-runtime-generator-staged-43aec2ed.patch"
printf '%s  %s\n' \
  0f2f3f9dfc7509d1d240f81a44a4c1700032478c51ff89d769a14c4b5ca022d8 \
  "$PATCH" | sha256sum --check
git apply --check --index "$PATCH"
git apply --index "$PATCH"
git diff --cached --check
test "$(git write-tree)" = 43aec2ed8555b6f4a9866ae4b8605972062dff6d
git diff --cached --name-status
```

The final command must show only:

```text
M	.github/workflows/build.yaml
M	winsup/autogen.sh
A	winsup/tests/autogen-contract.sh
```

This creates no commit and grants no authority to create one.

## Rebuild and replay generator outputs

The admitted source identities, URLs, hashes, Windows image lock, LLVM/toolchain
lock, runtime source identities, and 78 runtime-generator requirements are in
`state/arm64-vnext-2026-08-31-v1-generator-input-ledger-v2.json`. The exact
prior bundle file inventory and hashes are in
`state/arm64-vnext-2026-08-31-v1-runtime-generator-continuity.json`. Reacquire
inputs only from the ledger URLs and reject every digest mismatch. The five
generator source archives are:

```text
4ca3801454abad7ce1da22bf4a7c9dbf1786e054438fa0ee3c35e5cc8559c6cb  autoconf2.73-2.73-1.src.tar.zst
81e2e5ecddc3b6aa133cd6432323c371ccdb8b7e558fdba2fca3b6dc780f50bb  automake1.18-1.18.1-1.src.tar.zst
900254a188958ff127a459ba14ef07f27fa968a6d26e54b18baf0f9fba9a4ee2  bison-3.8.2-5.src.tar.zst
627bd88b97a782ac6f45e7ada8b95713446584c57e2b8a363ac634a8308d5eee  cocom-0.996-6.src.tar.zst
f4e7ce3a074e5d63dcee75855cf80950f8885d0885e09c5aaa3eb64f10a4f33a  m4-1.4.21-1.src.tar.zst
```

After reconstructing an admitted native ARM64 generator bundle at `BUNDLE`,
run the source contract and regeneration from Git Bash in each of two fresh,
identically patched runtime clones:

```sh
export BUNDLE=/absolute/path/to/rebuilt-generator-bundle
export PATH="$BUNDLE/bin:$BUNDLE/runtime/bin:$PATH"
export PERL5LIB="$BUNDLE/runtime/lib/perl5/core_perl"

cd /absolute/path/to/runtime-generator-replay
TEST_SHELL=/bin/sh winsup/tests/autogen-contract.sh
(
  cd winsup
  ACLOCAL="$BUNDLE/bin/aclocal.exe" \
  AUTOCONF="$BUNDLE/bin/autoconf.exe" \
  AUTOMAKE="$BUNDLE/bin/automake.exe" \
  RM=/bin/rm \
  ./autogen.sh
)
(
  cd winsup/cygwin
  perl scripts/gendevices devices.in devices.cc
)
```

Capture and compare the declared outputs from both runs:

```sh
sha256sum \
  winsup/aclocal.m4 \
  winsup/configure \
  winsup/Makefile.in \
  winsup/cygwin/Makefile.in \
  winsup/cygserver/Makefile.in \
  winsup/doc/Makefile.in \
  winsup/utils/Makefile.in \
  winsup/utils/mingw/Makefile.in \
  winsup/testsuite/Makefile.in \
  winsup/testsuite/mingw/Makefile.in \
  winsup/cygwin/devices.cc > generated-output-sha256.txt
```

The two manifests must be byte-identical. Also recreate canonical provenance,
process, PE/import/module, relocation, and bundle inventory evidence and compare
it to the sealed continuity ledger. A new independent `before_commit` review
must evaluate the patch, both output runs, and all final evidence before any
runtime commit.

## Authority boundary

After recovery, query live state again. Do not commit, push, open a runtime PR,
request review, register a stack, enable auto-merge, enter a queue, merge, or
create a release without the separately sealed authority for that exact phase
and identity.
