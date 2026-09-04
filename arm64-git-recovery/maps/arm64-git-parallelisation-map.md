# Native ARM64 Git for Windows — End-to-End Path & Parallelisation Map

**Session:** ea1641ea (roadmap). Read-only on all `.copilot\repos\`. Local investigation + local
measurement only. No commits/pushes/PRs/CI/upstream contact.

**Evidence classes:** `[M]` measured first-hand this session · `[M*]` measured by a prior session
(cited) · `[D]` derived · `[P]` presumed.

---

## 0. THE ONE-LINE ANSWER

The **MINGW half** of the toolchain (`aarch64-w64-mingw32`) is **done and proven to run on ARM64
Windows today**; the **MSYS2 runtime half** (`aarch64-pc-msys` / `msys-2.0.dll`) is the only real
blocker, and it is one WIP session away from a first link. **Almost every Git dependency can be
built for native ARM64 right now without waiting for the runtime**, because Git's libraries are
MINGW-target (`aarch64-w64-mingw32`) code, not MSYS2-runtime code. **This host is itself ARM64**, so
built binaries can be executed here.

---

## 1. FULL DEPENDENCY CHAIN — runtime → git.exe, per layer

Denominator note: "Git for Windows" ships two kinds of binaries — the **MSYS2/runtime** binaries
(bash, coreutils, the git *wrapper* shell layer, some helpers that need fork/signals) and the
**MINGW** binaries (`git.exe` core and most libraries, which are plain Win32 PE and do **not** link
`msys-2.0.dll`). This split is the whole basis of the parallelisation answer.

| Layer | ARM64 build exists today? | What builds it | Actual blocker |
|---|---|---|---|
| **msys-2.0.dll runtime** | **No DLL yet** `[M*]` | `aarch64-pc-cygwin` cross GCC 15.0.1 in WSL `/root/xc/inst` `[M]` | The last-mile runtime link. Two historic blockers (`gendef` AArch64 sigfe backend; `autoload.cc` thunks) reported **just cleared** — sigfe.s 0→294,545 B, 272/310 objects `[M* per kickoff; live WSL in session c63ab774]`. Sealed pre-clear state I verified: 271/310, sigfe.s=0, 990 export fails + 196 undefs `[M]`. **This is the critical path and the only true blocker.** |
| **MINGW toolchain** (`aarch64-w64-mingw32`) — binutils, gcc, crt, winpthreads, headers | **YES, native ARM64, published** `[M]` | WoA `msys2-woarm64-build` CI → pacman repo | **None.** gcc 15.0.1, binutils 2.45, crt-git, winpthreads all in the live `woarm64-native` repo. |
| **MINGW cross toolchain** (x86_64-msys host → aarch64 target) | **YES, published** `[M]` | same | **None.** Lets an x64 box cross-build ARM64 MINGW artifacts. |
| **core utilities** (bash, coreutils, busybox) | **No** | need msys2-runtime | **Blocked on runtime** — these are the runtime-hosted binaries. `busybox-w32` is MINGW-target and may be an exception (see §2). |
| **Git library deps — zlib** | **YES native ARM64** `[M]` | woarm64-native repo | **None.** `zlib1.dll` verified machine=0xAA64. |
| **Git library deps — zstd, bzip2, libiconv, gettext, ncurses, gmp/mpfr** | **YES native ARM64** `[M]` | woarm64-native repo | **None** — present in db. |
| **Git library deps — curl, openssl, expat, pcre2** | **NO** `[M]` (absent from both dbs) | MINGW-packages recipes exist upstream | **Not yet built for aarch64.** No runtime needed — **buildable today.** Highest-value parallel work. |
| **Git itself** | **No** | MSYS2 `git` PKGBUILD (WoA MSYS2-packages@woarm64 has it) `[M]` | Needs its deps (curl/openssl/expat/pcre2) + a working runtime for the shell layer. The *core `git.exe`* is MINGW and needs only the libs. |
| **MinGit assembly / installer / packaging** | **No** | build-extra (Git-for-Windows) | Downstream of a built git; not started. |

---

## 2. THE PARALLELISATION ANSWER — what can start RIGHT NOW (ranked)

Everything here is **not gated on the runtime**. Ranked by value ÷ cost.

1. **Build curl, openssl, expat, pcre2 for native ARM64 (`aarch64-w64-mingw32`).** `[M: absent]`
   These are the only missing Git library deps. They are MINGW-target, need **zero** MSYS2 runtime,
   and the toolchain to build them is already published and proven. **Commission this first.**
   Needs: the `woarm64-native` pacman repo + MINGW-packages recipes. Can build on this ARM64 host
   (native) or any x64 box (cross).

2. **Assemble a MINGW-only `git.exe` linked only against `aarch64-w64-mingw32` libs.** `[D]`
   Git's core compiles as Win32; Git-for-Windows already does this on x86_64. Once dep #1 lands,
   `git.exe` + core builtins can link **without `msys-2.0.dll`**. This is the shortest route to *a*
   Git binary that runs on ARM64. Needs: dep #1 done.

3. **Prove the published toolchain end-to-end on this ARM64 host.** Install the `woarm64-native`
   repo, `pacman -S mingw-w64-aarch64-gcc`, compile+run a real program natively. WoA's own
   `check-repository.yml` already builds *and runs* `hello-world.exe` on `[Windows, GCC, ARM64]`
   `[M]`; reproduce locally to convert their CI evidence into our own. Needs: MSYS2 install on host.

4. **Port curl/openssl test suites & pcre2 JIT-for-aarch64 validation.** Independent of runtime.

5. **build-extra / MinGit packaging dry-run for arm64** — scaffold the assembly now against x86_64
   so it's ready the moment ARM64 git binaries exist. Pure scripting, no toolchain dependency.

6. **The runtime residue items that are NOT the sigfe/autoload critical path** and can proceed in
   parallel to the link: the 8 orphan `cygwin.din` exports (implement/exclude for aarch64), the 10
   `aarch64/*.S` string routines (droppable for first link — newlib provides working memcpy etc.),
   and the newlib `ld128`/`_fpmath.h` long-double fixes. `[M* RESULT.md §5c, §6, §8]`

**What is genuinely BLOCKED on the runtime (do NOT commission yet):** bash, coreutils, the git
*shell wrapper* layer, and any MSYS2-hosted helper that needs fork()/signals — i.e. the
`aarch64-pc-msys` application binaries. These wait on `msys-2.0.dll`.

---

## 3. WHAT ALREADY EXISTS THAT WE ARE NOT USING

- **A complete, published, native ARM64 MINGW toolchain + package repo.** `[M]`
  `https://windows-on-arm-experiments.github.io/msys2-woarm64-build/aarch64/woarm64-native.db`
  returns HTTP 200. 35 native-ARM64 packages incl. gcc-15.0.1, binutils-2.45, crt-git,
  winpthreads, zlib, zstd, bzip2, libiconv, gettext, ncurses, gmp, mpfr, mpc, isl, ninja, pkgconf,
  autotools. **DLLs verified machine=0xAA64 by reading PE headers myself** (libgcc_s_seh,
  libstdc++-6, libgomp, libatomic, zlib1). Evidence: `files/evidence/`.
- **A published x86_64-hosted cross toolchain** (`woarm64` repo, HTTP 200) for cross-building the
  above on any x64 machine. `[M]`
- **The WoA porting effort's own roadmap** (README dependency charts) states MINGW cross + native =
  **DONE**; MSYS2 side: `msys2-runtime`=WIP, `cross-gcc`=WIP, `bash`=TODO, `git4win`=TODO. `[M]`
  This is authoritative and matches the runtime-session evidence — we are exactly at their WIP edge.
- **A ready MSYS2 `git` PKGBUILD** in WoA MSYS2-packages@woarm64 (git + 6 msys2 patches). `[M]`
- **CI that already builds+runs ARM64 binaries** on real ARM64 runners (`check-repository.yml`). `[M]`
- **This host is ARM64** — native execution available for validation without a remote runner. `[M]`

**We are NOT using:** the published native repo (nothing local consumes it yet); the ready git
PKGBUILD; and this ARM64 host as a native test bed.

---

## 4. UPSTREAM newlib-cygwin STATUS `[M]`

`cygwin/cygwin` `winsup/cygwin/aarch64/` contains **only** `cygwin.din` and `fastcwd.cc` (confirmed
via API listing). The signal-frame trampolines, autoload thunks, and the sigfe/gendef backend are
**NOT upstream** — the programme's WSL tree is ahead of upstream on exactly the hard runtime parts.
Searched: `repos/cygwin/cygwin/contents/winsup/cygwin/aarch64` (API), and the sealed evidence in
sessions 1e64365a / c63ab774. A non-match here is confirmed by direct directory listing, not
pattern absence.

---

## 5. THE HONEST CRITICAL PATH

**Shortest real route to a Git that runs on ARM64 — two tracks, run in parallel:**

**Track A (MINGW-only Git — fastest demonstrable win, NOT runtime-gated):**
1. Build curl, openssl, expat, pcre2 for `aarch64-w64-mingw32`. (§2.1)
2. Link core `git.exe` + builtins against the MINGW libs only. (§2.2)
3. Run on this ARM64 host.
→ **Demonstrates:** the full ARM64 toolchain compiles and links a real, non-trivial, executable
Git core, natively, end-to-end. `clone`/`commit`/`log` over the object layer work.
→ **Does NOT demonstrate:** the MSYS2 runtime, the bash/sh porcelain, `git rebase -i`, hooks,
credential helpers, or anything needing fork()/signals — those are the runtime layer. It is a
**real Git binary**, not the full Git-for-Windows distribution.

**Track B (the true finish — runtime-gated, already WIP):**
1. Finish the `msys-2.0.dll` link in session c63ab774 (sigfe + autoload now cleared per kickoff;
   remaining: orphan exports, residual undefs). 
2. Build `aarch64-pc-msys` cross-gcc (WoA WIP), then bash/coreutils.
3. Build the MSYS2 `git` package (PKGBUILD ready) on top of runtime + Track A libs.
→ **Demonstrates:** genuine, full Git for Windows on ARM64 — the owner's actual goal.

**Recommendation:** commission Track A immediately (unblocked, high signal, proves the toolchain end
to end while the runtime link finishes), and let Track B's runtime link continue in c63ab774. They
converge: Track A's curl/openssl/expat/pcre2 are exactly the deps Track B's git package also needs.

---

## 6. READY-TO-COMMISSION SESSIONS (from this map)

- **S1 — ARM64 MINGW Git deps:** build curl, openssl, expat, pcre2 `aarch64-w64-mingw32`. Inputs:
  woarm64-native repo + WoA MINGW-packages. Success: 4 `pkg.tar.zst`, DLLs machine=0xAA64.
- **S2 — MINGW-only git.exe:** after S1, link core git against MINGW libs; run on this ARM64 host.
- **S3 — Toolchain proof-on-host:** install woarm64-native repo locally; reproduce hello-world
  build+run natively (converts WoA CI evidence to ours).
- **S4 — Runtime finish (existing c63ab774):** close orphan exports + residual undefs → first
  `msys-2.0.dll`.
- **S5 — Packaging dry-run:** build-extra/MinGit assembly scaffolding for arm64 ahead of binaries.
