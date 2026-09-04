
# Verification: the INSTALLED tree (`git-install/`) — the tree that becomes the package

Status: **MEASURED, ALL PASS**. Originated in **this verifier thread**. Read-only.

## The hash this verification covers

```
bin/git.exe   sha256 = 69b1e704729cf69f0a0c029aa189eb9d38f74fc16ef37823048cb6a98b1523d1
              size   = 4,723,261 B      mtime = 2026-09-03 10:02:49
```

Re-read at **report time (10:13:13)** per the standing rule — **unchanged**.

## Freeze state: NOT FROZEN

The tree was reported as having been asked to freeze. **It has not been.**

| Check | Result |
|---|---|
| read-only files | **0** |
| writable files | **220** |
| `SHA256SUMS` manifest inside the tree | **absent** |

I therefore anchored to **my own snapshot** taken at audit time and re-verified every
binary at report time: **158 files checked, 158 unchanged, 0 changed** across the
verification window (10:10 → 10:13). The verification is self-anchored, but the tree
remains mutable and could move after this report.

## Structure and the hardlink question

| Measurement | Value |
|---|---|
| `bin/*.exe` | 6 |
| `libexec/git-core` files | 173 (152 `.exe` + 21 non-exe) |
| **total `.exe` audited** | **158** |
| **reparse points (symlinks)** | **0** |
| **files with `NumberOfLinks` > 1** | **0** — histogram `1 -> 158` |
| **distinct NTFS file indexes** | **158**, none shared |
| **PE machine** | **`0xaa64` × 158**, zero exceptions |
| distinct binary contents | **11** across 158 files |
| logical `.exe` bytes | **761,270,357** |
| `dir` on `libexec/git-core` | 173 files, **736,311,314 bytes** |

**`NO_INSTALL_HARDLINKS=1` worked.** Three independent signals agree: link count 1,
158 distinct file indexes, and on-disk consumption matching the full logical sum. Had
these been hardlinks to the 11 distinct contents, consumption would be a small
fraction. `pacman -Ql` will enumerate all 158.

### The four network helpers

| Helper | sha256 |
|---|---|
| `git-remote-https.exe` | `4290174bed6056fde895aaebdc13f04eab148f80d50548cd09d774542d0f2a41` |
| `git-remote-http.exe` | `4290174bed6056fde895aaebdc13f04eab148f80d50548cd09d774542d0f2a41` (identical content) |
| `git-http-fetch.exe` | `3f570a00a6d6ab7baac1f4008a74abc4eeb49e2b4e4152d036f33baaaba8fe80` |
| `git-http-push.exe` | `4e0a87cf3e05bd79ebae4d9962f9e8e9c5c8dc5a65f23e29ade0899b5d0543c0` |

All four present, all `0xaa64`.

## Five-point protocol + additions — from the installed tree

| Check | Result |
|---|---|
| 1 Raw COFF | `Machine=0xaa64`, `Magic=0x020b`, Subsystem 3, `ImageBase=0x140000000` |
| 2 Live `IsWow64Process2` | `git` **and** `git-remote-https` both `ProcessMachine=0x0000` → **native** |
| 3 Bound modules | 36; **`schannel` absent, `ncrypt` absent** |
| 4 Controlled `PATH` | `bin` + `System32`; `sh.exe` **ABSENT** — control valid |
| 5 Negative control | `git-submodule` script **present** in exec path, no `sh` → **exit 128**, correct fatal |
| Toolchain | **LinkerVersion 2.44**, **0 clang strings**, **no `.buildid`** |
| TLS positive control | Windows `curl.exe`: `schannel.DLL`, `ncrypt.dll`, `ncryptsslp.dll` **PRESENT** — detector fires |
| SHA-1 known-answer | empty → `e69de29b…`, `hello\n` → `ce013625…`, `test content\n` → `d670460b…` — **3/3 match** |
| Known-SHA clone | exit 0; `rev-parse HEAD` = **`7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`**; `fsck` exit 0 |

`GIT_EXEC_PATH` resolved **inside** the installed tree, so the helpers were exercised
from where they will ship. The negative control is now the strong form — the script
is present and still cannot run, isolating the missing shell as the cause.

## A bug in my own harness that would have blocked the release

My first audit reported **`files with NumberOfLinks > 1: 158 — HARDLINKS PRESENT`**.

That is a release-blocking claim: it says `NO_INSTALL_HARDLINKS=1` failed and the
package would ship a fraction of its files.

**It was wrong, and it was mine.** `BY_HANDLE_FILE_INFORMATION` packs `FILETIME` on
4-byte alignment; C#'s default `LayoutKind.Sequential` padded my `long` fields to
8 bytes, so every field after `dwFileAttributes` was read at the wrong offset.

Two things exposed it before it left this thread:

1. **The values were impossible** — link counts of 131072, 196608, 262144, 327680,
   786432. Link counts are small integers.
2. **Two fields from the same struct contradicted each other** — "158 files with
   multiple links" alongside "158 distinct file indexes, 0 shared". A struct that
   disagrees with itself is misaligned, not reporting a finding.

Corrected with `Pack = 4`: `NumberOfLinks` histogram `1 -> 158`. Confirmed by an
independent test that touches none of that code — on-disk consumption matches the
full logical sum.

**Fourth harness self-catch of the day.** The pattern is now consistent: my errors
are in the *instrument*, not the *reading*, and each was caught by an internal
inconsistency rather than by care.

## Labelling

- **Measured**: every hash, count, link count, file index, PE machine, module list,
  exit code, and the report-time re-read.
- **Derived**: that 11 distinct contents across 158 files is the expected shape of
  copied builtins.
- **Not established**: that the tree will still match after this report — **it is not
  frozen**. Any consumer must pin `69b1e704…` and re-check, which is exactly what
  `wrap-git-package.sh`'s exit-4 refusal does.
