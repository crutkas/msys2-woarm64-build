# The Last Mile — from `git.exe` to an installable native ARM64 Git for Windows

**Session:** ea1641ea. Read-only on all `.copilot\repos\`. Local measurement only. No commits/
pushes/PRs/CI/upstream contact. Labels: `[M]` measured first-hand this session · `[M*]` measured by
a cited prior session · `[D]` derived · `[P]` presumed.

---

## 0. HEADLINE

A native `git.exe` from Track A is **~90% of an installable Git**, not a demo. Its **entire
dependency closure is MINGW-target** — 23 packages, of which exactly **one** non-MINGW package
(`nano`, an optional editor) appears, and that is trivially droppable. **Nothing in the core Git
binary + its DLL closure needs `msys-2.0.dll`.** The MSYS2 runtime is required only for the *bash
porcelain* (a specific, enumerable set of subcommands) and for the MinGit "rebase" tail. So a
genuinely usable, installable ARM64 Git — capable of `clone`/`fetch`/`push` over HTTPS, `commit`,
`log`, `diff`, `merge`, branching — can be assembled **today**, before the runtime lands.

Measured proof: I downloaded the ARM64 dependency packages that already exist and **assembled a
173-file partial install tree**, every DLL verified ARM64 PE (machine 0xAA64). See
`files/staged-closure/`.

---

## 1. WHAT A MINIMAL USABLE ARM64 GIT INSTALL REQUIRES `[M]`

Source of truth: MSYS2 official `clangarm64` git package (git 2.55.0.5), which is exactly this
"native ARM64 Git" built as PE. Direct depends (`evidence/git-clangarm64-direct-depends.txt`):

```
curl  ca-certificates  expat>=2.0  openssl  pcre2  nano
```

**Full transitive closure = 23 MINGW-target packages + 1 non-MINGW**
(`evidence/git-transitive-closure.txt`):

- Compression/format: `zlib(-ng)`, `zstd`, `bzip2`, `brotli`
- TLS/crypto/net: `openssl`, `curl(-winssl)`, `libssh2(-wincng)`, `c-ares`, `libpsl`, `libidn2`,
  `libtasn1`, `libunistring`, `p11-kit`, `ca-certificates`
- Text/regex/i18n: `pcre2`, `expat`, `libiconv`, `gettext-runtime`
- Runtime libs: `libffi`, `wineditline`, and **`libc++`/`libunwind`** *(clang-runtime only — under
  WoA's GCC toolchain these become `libstdc++`/`libgcc`, which WoA already ships)* `[D]`
- `git` itself
- **Non-MINGW: `nano`** (editor) — optional, droppable for a minimal install.

**Core binaries actually shipped** (`evidence/git-separate-binaries.txt`) `[M]`:
- `bin/`: `git.exe`, `git-receive-pack`, `git-shell`, `git-upload-archive`, `git-upload-pack`
- `libexec/git-core/`: only **11** separate `git-*.exe` — modern Git is overwhelmingly *builtin*
  (one `git.exe` multiplexes ~130 subcommands). The separate ones: `git-daemon`,
  `git-http-backend`, `git-imap-send`, `git-remote-ftp`, **`git-remote-http`**, **`git-remote-https`**,
  plus the 4 pack/shell exes above.
- **`git-remote-https.exe` is a genuine separate binary and links curl** — it is what makes
  `git clone https://…` work, and it is MINGW-target (unblocked). `[M]`
- **Cert bundle:** `etc/ssl/certs/ca-bundle.crt` from `ca-certificates` (also full `etc/pki/…`). `[M]`
- **Templates:** `share/git-core/templates/` (hooks, description) ship in the git package. `[M]`

**Add-ons (separate packages, all MINGW-target):**
- `git-lfs` depends only on `git` — self-contained Go binary. `[M]`
- `git-credential-manager` is **Git-for-Windows-specific, not in MSYS2 clangarm64** — a .NET app;
  separate track, not on the critical path. `[M]`

---

## 2. THE SPLIT — MINGW (unblocked) vs MSYS2-runtime (blocked) `[M/D]`

| Component | Target | Runtime-blocked? |
|---|---|---|
| `git.exe` + 23-pkg DLL closure (curl/openssl/expat/pcre2/zlib/…) | MINGW `aarch64-w64-mingw32` | **No — buildable today** |
| `git-remote-https`, `git-remote-http`, http-backend, daemon, pack/shell exes | MINGW | **No** |
| cert bundle, templates, gitconfig | data | **No** |
| `git-lfs` | MINGW (Go) | **No** |
| **bash porcelain** — `git rebase -i`, `git add -p`/`-i`, `git stash` (script paths), `git filter-branch`, `git bisect`, `git submodule` (older), `git request-pull`, `git send-email`, `git mergetool`, `git difftool`, hook execution via `/bin/sh` | needs `sh`/`bash` → **msys2-runtime** | **YES** |
| `bash`, `sh`, `dash`, coreutils (`sed/grep/awk/find`), `rebase.exe`, `getopt` | MSYS2 | **YES** (MinGit still lists `msys2-runtime` + `dash`/`busybox` + `rebase.exe`) |
| MSYS2 `git` *package* (WoA MSYS2-packages@woarm64) | MSYS2 | **YES** |

**What works WITHOUT the runtime** (native git.exe only): `init, clone (https/ssh/file), fetch,
pull, push, commit, add, rm, mv, status, log, show, diff, branch, checkout, switch, restore, merge,
rebase (non-interactive), reset, tag, stash (builtin in modern Git), cherry-pick, revert, remote,
config, cat-file, ls-files, rev-parse, worktree, sparse-checkout, maintenance, gc, fsck, blame,
grep, describe`. This is the large majority of everyday Git.

**What genuinely STOPS without the runtime:** anything that shells out to `/bin/sh` — chiefly
**`rebase -i`, `add -p`/`add -i` (older Git), `git bisect` (script), `filter-branch`, `send-email`,
`request-pull`, `mergetool`/`difftool`, and any repo hook written as a shell script.** Modern Git
has moved many of these to builtins (interactive add and much of rebase are now C), which *narrows*
the blocked set — worth measuring against the exact Track-A git version once built. `[D]`

---

## 3. WHAT build-extra / MinGit ALREADY PROVIDE `[M]`

Read read-only from `C:\Users\crutkasLocal\.copilot\repos\build-extra`.

- **`mingit/release.sh`** already has an **`aarch64` branch** (`MSYSTEM=CLANGARM64` → `ARCH=aarch64`,
  prefix `mingw-w64-clang-aarch64`, suffix `arm64`). MinGit-for-ARM64 is **already wired** — but it
  targets the **MSYS2 CLANGARM64** toolchain, *not* WoA's `mingw-w64-aarch64` (MINGWARM64). `[M]`
- **`make-file-list.sh`** maps `ARCH=aarch64 → MSYSTEM_LOWER=clangarm64, PACMAN_ARCH=clang-aarch64`.
  It is the whole install-closure engine: it runs `pactree`/`pacman -Ql` over an **installed**
  `mingw-w64-<arch>-git` package and applies a large exclude filter. `[M]`
- **`check-for-missing-dlls.sh`** also already knows CLANGARM64/aarch64 → Git-for-Windows tooling
  has ARM64 awareness. `[M]`
- MinGit assembly avoids the full shell where possible: it can substitute **`git-wrapper.exe`** for
  `git-remote-http.exe` and **`busybox.exe`** for `ash`/`sh` (`--busybox` mode drops bash, sh,
  coreutils, openssl, ncurses). `[M]`

**Verdict on "is an ARM64 MinGit mostly a package-list change?"**
**Mostly yes, but with one real substitution.** The assembly logic is already ARM64-aware. Two
concrete deltas: (1) MinGit's `clangarm64`/`clang-aarch64` prefix must be pointed at a repo that
actually has an ARM64 `git` package — either MSYS2's clangarm64 (exists upstream) or, to use the
*WoA GCC* toolchain, a new `mingw-w64-aarch64` (MINGWARM64) prefix + a `git` package built there;
(2) even minimal MinGit still lists `msys2-runtime` + `dash`/`busybox` + `rebase.exe`, so a
**fully runtime-free** MinGit needs the `--busybox` path *and* dropping the `rebase.exe`/`dash`
tail — a small, enumerable edit to `make-file-list.sh`, not a redesign. `[M/D]`

---

## 4. STAGED TODAY `[M]`

From WoA `woarm64-native`, I downloaded and **assembled a partial closure tree** — `files/
staged-closure/`, manifest `STAGED-MANIFEST.txt` (**173 files**). Every DLL verified ARM64 PE:
`zlib1, libbz2-1, libzstd, libiconv-2, libintl-8, libcharset-1, libasprintf-0` — all `0xAA64`.

**Closure gap measured** (`evidence/closure-vs-woarm64-gap.txt`): of the 23-pkg git.exe closure,
**4 already exist** in woarm64-native (`bzip2, gettext-runtime, libiconv, zstd`; `zlib` also
present) and **~19 are missing** — led by the ones Track A is building now (`curl, openssl, expat,
pcre2`) plus `ca-certificates, brotli, c-ares, libidn2, libpsl, libssh2, libtasn1, libunistring,
p11-kit, libffi, wineditline`. `libc++`/`libunwind` fall away under a GCC build. **These 19 are the
concrete remaining build-today list.**

---

## 5. THE LAST-MILE PLAN — what stands between Track A's git.exe and an installable Git

Ranked, all except the last **not** runtime-gated:

1. **Finish Track A's 4 deps** (curl, openssl, expat, pcre2) — in progress in session 2918d1f1.
2. **Build the rest of the 19-pkg closure for `aarch64-w64-mingw32`** — ca-certificates (cert
   bundle!), brotli, c-ares, libidn2, libpsl, libssh2, libtasn1, libunistring, p11-kit, libffi,
   wineditline. Straight ports; recipes exist in MSYS2/MINGW-packages. **Nobody owns this — commission it.**
3. **Package `git` for the WoA MINGW target** (or reuse MSYS2 clangarm64 git) so `make-file-list.sh`
   has an installed `mingw-w64-<arch>-git` to walk.
4. **Produce an ARM64 MinGit** via the already-ARM64-aware `release.sh --busybox`, pointing the
   prefix at the ARM64 repo, and trim the `msys2-runtime`/`dash`/`rebase.exe` tail. Result: a
   runtime-free, installable, native ARM64 Git that does clone/commit/push/log/diff/merge.
5. **(Runtime-gated, Track B)** For *full* Git-for-Windows parity — `rebase -i`, script hooks, the
   bash shell, `git-bash.exe` — assemble on top of the finished `msys-2.0.dll` + WoA MSYS2 `git`
   package. This is the only part that waits.

**What #1–4 demonstrate:** a genuinely native, installable ARM64 Git a person can unzip and use for
real work over HTTPS. **What they do NOT:** the Git Bash shell and the handful of shell-script
subcommands (§2) — those need the runtime.

---

## 6. READY-TO-COMMISSION (last-mile)

- **L1 — ARM64 git.exe closure completion:** build the 19-pkg MINGW closure (§4) for
  `aarch64-w64-mingw32`; verify each DLL 0xAA64; produce `ca-bundle.crt`. Depends on nothing.
- **L2 — ARM64 git package:** build/obtain a `mingw-w64-aarch64 git` so MinGit tooling can walk it.
- **L3 — ARM64 MinGit:** adapt `release.sh`/`make-file-list.sh` (already aarch64-aware) with
  `--busybox` and a runtime-free trim; emit `MinGit-<ver>-arm64.zip`; unzip + run `git clone https`
  on this ARM64 host as the acceptance test.
- **L4 — (Track B) full Git-for-Windows arm64** once `msys-2.0.dll` links.
