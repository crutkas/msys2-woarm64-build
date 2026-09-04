# MinGit-arm64 (Windows on Arm) — Release Notes

**Artefact:** `MinGit-2.47.1-arm64.zip`
**Size:** 26,622,481 bytes (~26.6 MB)
**SHA-256:** `7d2c2ebf8bf236c736fa73f38447a8b52530b326704f90d0d07716d9f8b1a88e`

## The claim

**Every *functional* Git binary and library in this artefact was built with our
Windows-on-Arm GCC toolchain** — Git itself, its libraries, and the BusyBox
shell. Two credential-helper slots are **non-functional ARM64 stubs**, disclosed
in full below; they were not built as working programs and nothing in this
artefact manages credentials.

This is a statement about the **toolchain**. It is *not* a claim that we wrote
BusyBox, and it is *not* "the first native ARM64 Git" — MSYS2 already ships one
(`clangarm64` 2.55.0.5). The value here is that a native on-host Windows-on-Arm
GCC 15.0.1 toolchain produced every executable byte of a genuinely native ARM64
Git and its shell, assembled into a correctly-sized, runtime-free MinGit.

## Non-functional stubs (disclosed)

Two of the sixteen `bin/*.exe` are **non-functional placeholder stubs**, both
exactly 153,353 bytes, shipped only so the MinGit packaging tooling has a valid
ARM64 PE to place in the credential-manager slot:

- `git-credential-manager.exe` — Git Credential Manager is a .NET/Avalonia
  application, out of scope for a C-toolchain demonstration. This stub **manages
  no credentials.** (`doc/git-credential-manager/STUB-PLACEHOLDER.txt` says so
  in-package.)
- `git-credential-helper-selector.exe` — the same stub bytes in the selector
  slot.

**Do not treat these as working credential storage.** Every *other* binary in
the artefact — Git, the network helpers, and the BusyBox shell — is a real,
functional program built by our toolchain. HTTPS clone (proven below) needs no
credential helper for public repositories.

## What it contains

- **git.exe 2.47.1**, native ARM64 (PE `0xAA64`), SHA-256 `69b1e704…`.
  Fully static: binds only UCRT + core Win32 (ADVAPI32/KERNEL32/USER32/WS2_32/
  ntdll; the HTTPS remote helper adds only CRYPT32 + bcrypt). No `msys-2.0.dll`,
  no MinGW runtime.
- **BusyBox shell**, native ARM64 (PE `0xAA64`), SHA-256 `67665b44…`, built from
  `busybox-w32` `d8d8bb397` **unmodified**. Ships as both `busybox.exe` and
  `ash.exe`. **179 applets** (`ash sh sed awk grep sort cut tar gzip wget diff
  patch find xargs less stty cygpath …`) — a complete shell layer, not a
  bootstrap subset (the earlier stand-in carried only 39).
- 16 `bin/*.exe` (11 distinct binaries), all `0xAA64`; runtime-free (UCRT-only
  plus core Win32 across the set).

## Verified behaviour (decisive A/B)

Same native ARM64 `git.exe`, same source repo, single variable = our BusyBox on
PATH as the shell:

- **Without a shell:** `git clone` crashes with `0xC0000005` (access violation),
  leaving a partial `.git` and no checkout.
- **With our BusyBox as `sh.exe`:** `done.`, exit 0. `README.md` present (21 B),
  clone HEAD `574d742f…` equal to source HEAD, `git status` clean.
- **Negative control (run first):** PATH cut to `system32;Windows;Wbem`,
  `GIT_EXEC_PATH`/`GIT_CONFIG_*` cleared, `sh.exe`/`bash.exe` not found →
  `git submodule status` exit 128.

**Our toolchain's Git, cured by our toolchain's shell.**

Additionally, git.exe was run on-host and cloned `octocat/Hello-World` over
HTTPS (our static OpenSSL + the cert bundle) to the known HEAD
`7fd1a60b…`, `fsck` exit 0.

## Known limitation (shared with upstream, stated up front)

**`git submodule` does not work with BusyBox as the shell.** This is **inherent
to BusyBox `ash`, not specific to our build.** `git-sh-setup` matches
`*MINGW*` against `uname -s`; BusyBox reports `MINGW(BusyBox/Win32)`, so the
script takes the MSYS2-bash branch and calls `builtin pwd -W`, which BusyBox
`ash` does not implement (`builtin: not found` → "Unable to determine absolute
path of git directory", exit 1).

Tested against **upstream's own ARM64 BusyBox** (`aabca41f`, SHA-256
`4E510E35…`): identical failure. This is the same family as
`git-for-windows/git#5184` and `#6107`. **Our artefact inherits exactly the same
limitation as upstream's MinGit-BusyBox — no better, no worse.** It does **not**
affect `git clone`, which needs only that `sh` exist.

## Provenance (honest)

- **git.exe / libraries:** compiled by our native ARM64 GCC toolchain; the build
  *driver* (`make`/`sh`) contributed no code to the output.
- **BusyBox:** compiler = our native ARM64 GCC 15.0.1 (`aarch64-w64-mingw32`,
  posix threads, `armv8-a`); source `busybox-w32 d8d8bb397`, unmodified. Build
  *driver* was emulated x86-64 MSYS2 `make` + Git-for-Windows `usr/bin`; the
  driver's architecture has no bearing on the output's, proven from the COFF
  header and `IsWow64Process2` on the running process.

Unlike `make`/`sh`, which only drove the build, the BusyBox shell **ships inside
the artefact** — hence it is named in the claim above.
