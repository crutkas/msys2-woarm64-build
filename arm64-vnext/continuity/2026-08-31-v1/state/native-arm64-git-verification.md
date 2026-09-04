# Verification: native ARM64 `git.exe` (single-toolchain WoA GCC build)

Status: **MEASURED**. Originated in **this verifier thread**. Read-only on the
producing session's tree — all work done on an isolated copy.

Artefact: `2918d1f1…/files/gcc-native/git-2.47.1/git.exe`
sha256 `1ec7f3b2782619bd46883113e29c2c0d9229156400170334427fecfbda7a6397`, 4,723,261 B.

## Five-point protocol

| # | Check | Result |
|---|---|---|
| 1 | **Raw COFF** | `Machine=0xaa64` (ARM64), `Magic=0x020b` (PE32+), Subsystem 3 (console), `DllCharacteristics=0x0160` |
| 2 | **Live process** `IsWow64Process2` | `ProcessMachine=0x0000`, `NativeMachine=0xaa64` → **not WOW64, running natively** |
| 3 | **Bound-module sweep** | 36 modules across `git` + `git-remote-https`; **no `schannel.dll`, no `ncrypt.dll`** (control below) |
| 4 | **Controlled `PATH`** | restricted to staged dir + `System32`; `sh.exe` confirmed **ABSENT** |
| 5 | **Negative control** | `git submodule status` → **exit 128**, "not able to execute it" — the shell-dependent porcelain fails as it must |

`git --version` → `git version 2.47.1`.

## Per-component toolchain attribution

No embedded `GCC:`/`clang version` strings (stripped), so attribution is by
structural tells, with the **retired clang build as a differential control**:

| Binary | LinkerVersion | `.buildid` | `clang` strings | Verdict |
|---|---|---|---|---|
| `git.exe` | **2.44** | no | **0** | GNU ld / binutils 2.44 |
| `git-remote-http.exe` | **2.44** | no | **0** | GNU |
| `git-remote-https.exe`, `git-receive-pack`, `git-upload-pack`, `git-upload-archive` | **2.44** | no | **0** | GNU |
| `git-clang-arm64/git.exe` *(retired pass)* | **14.0** | **yes** | **42** | clang / LLD |

The GNU binaries also carry `.edata` and `.idata` sections absent from the LLD
output — a second, independent discriminator. **The differential is clean: the
produced git binaries are single-toolchain GNU, and the clang pass is genuinely
distinct and retired.**

### One exception, stated precisely

`gcc-native/driver-bin/mingw32-make.exe` reports **LinkerVersion 14.0** and carries
`.buildid` — it is **LLD-linked**, byte-identical in size to
`make-pkg/clangarm64/bin/mingw32-make.exe`. It is the **clangarm64 package make**,
not a product of the WoA GCC chain.

So "the entire chain is single-toolchain WoA GCC" holds for **everything the build
produces**, but the **build driver** is a clang/LLD-built package binary. Whether a
driver counts as part of "the chain" is a definition the programme should settle
rather than leave implicit — the *artefacts* are unambiguously GNU.

## TLS: Windows demonstrably did not participate

The requirement is evidence of what *happened*, not what was *configured*.

**Positive control — the detector must be shown to fire.** Windows' own
`System32\curl.exe` over the same HTTPS URL, swept with the identical harness:

```
schannel.DLL      PRESENT
ncrypt.dll        PRESENT
ncryptsslp.dll    PRESENT
```

**Test — our ARM64 git**, `git ls-remote https://github.com/git/git`, sweeping
process names `git`, `git-remote-https`, `git-remote-http`:

- processes actually observed: **`git`, `git-remote-https`** — the child that does
  the TLS *was* swept
- **36** modules observed
- crypto-relevant modules present: `bcrypt.dll`, `bcryptPrimitives.dll`,
  `CRYPT32.dll`, `CRYPTBASE.DLL`, `CRYPTSP.dll` — primitives and certificate store
- **`schannel.dll`: absent. `ncrypt.dll`: absent.**

Static import tables agree: `git.exe` imports **no** crypto DLL at all;
`git-remote-https.exe` imports `CRYPT32` and `bcrypt` only.

### Why the module check mattered — a strings audit would have been WRONG

`git-remote-http.exe` contains **351 `ncrypt` strings and 5 `schannel` strings**.
A strings-based audit would have reported Windows TLS involvement. **Neither DLL
ever loads.** String presence is not linkage; linkage is not loading. This is the
same class as every other error catalogued: an artefact that *mentions* a thing
being mistaken for evidence that the thing is *in play*.

## Known-SHA clone

- CA bundle: `ca-bundle.crt`, sha256 `d2eb6ed690d732c10f151e6a657a5012363fe30b6301741b7cedefbd1685b170`, **exactly 172 certificates**, supplied via `GIT_SSL_CAINFO`
- `git clone https://github.com/octocat/Hello-World` → **exit 0**, 13 objects received
- `git rev-parse HEAD` → **`7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`** — **exact match** to the expected public SHA
- `git fsck` → **exit 0**, no corruption
- full history reachable: `7fd1a60` ← `7629413` ← `553c207`
- `git cat-file -t 7fd1a60b…` → `commit`

## A failure in my own harness, recorded

My **first** sweep reported `schannel: NO` after taking **one** sample and observing
**zero** processes — the tiny clone finished before the loop could see the child.
That is a detector returning zero **without ever having been shown to return
non-zero**: an *absent* result, not a negative one, and precisely the failure mode
this programme adopted a rule against. I discarded it and rebuilt the harness with
a positive control and a longer-lived operation. **The rule caught its author.**

I also initially staged the artefact by copying `git-2.47.1/*`, which is the full
source tree, not a binary directory — corrected before use.

## Labelling

- **Measured**: every hash, COFF field, linker version, section list, string count,
  module list, process list, exit code, and the SHA/fsck results.
- **Derived**: that LinkerVersion 2.44 + absent `.buildid` + zero clang strings
  implies GNU ld — supported by the clean differential against the clang build, but
  it is an inference from structure, not a compiler banner.
- **Not established**: whether the `mingw32-make.exe` provenance matters to the
  programme's definition of "chain"; behaviour against hosts requiring TLS features
  beyond this one handshake.


---

## RE-VERIFICATION: the artefact moved underneath the first report

**The binary was rebuilt at 09:51:20 on 2026-09-03 — six minutes after I completed the first verification and six minutes before the coordinator asked for it.** The first report therefore described a **superseded** artefact, and the coordinator's acceptance was granted against it. Recorded prominently because this is the moving-target trap the programme has already been bitten by.

| | first report | claimed / current |
|---|---|---|
| `git.exe` | `1ec7f3b2782619bd...` 4,723,261 B | **`fb8ecae91dc8fce9d8eb41020cd22d080efccbdc113b5001fc18f14a14d9c971`** 4,723,261 B |
| `git-remote-http.exe` | `ae480324d44aa8bb...` 9,077,899 B | **`e4d66ba49bb3d0f00b4d22a04e3e1137beab3e96584f7c9fe0866e4b9fee2047`** 9,075,851 B |

Note `git.exe` is **the same size with a different hash** - the case where a size check alone would have concluded 'unchanged'. `git-remote-http.exe` differs by exactly 2,048 bytes.

### Full protocol re-run against `fb8ecae9...` - ALL PASS

| Check | Result |
|---|---|
| Raw COFF | `Machine=0xaa64`, PE32+, Subsystem 3, `DllChar=0x0160`, `ImageBase=0x140000000` |
| sha256 vs claim | **exact match** |
| Toolchain | **LinkerVersion 2.44**, no `.buildid`, **0 clang strings**, `.edata`/`.idata` present |
| Components | `OpenSSL 3.4.1`, `libcurl/8.11.1` embedded - matches the claim |
| Live `IsWow64Process2` | `git` **and** `git-remote-https` both `ProcessMachine=0x0000` -> **native** |
| Bound modules | 37 across both processes; **schannel absent, ncrypt absent** |
| TLS positive control | Windows `curl.exe`: `schannel.DLL`, `ncrypt.dll`, `ncryptsslp.dll` **PRESENT** - detector fires |
| Known-SHA clone | exit 0; `rev-parse HEAD` = `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d` **exact**; `fsck` exit 0 |
| Negative control | with full exec path (`git-submodule` script present, no `sh`): *fatal: 'submodule' appears to be a git command, but we were not able to execute it* |

### Known-answer test of the SHA-1 object machinery (new)

| Input (exact bytes) | Result |
|---|---|
| empty | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` **match** |
| `hello\\n` | `ce013625030ba8dba906f756967f9e9ca394464a` **match** |
| `test content\\n` | `d670460b4b4aece5915caf5c68d12f560a9fe3e4` **match** |

**A second harness failure of my own, and this time I proved it rather than asserting it.** My first attempt piped strings from PowerShell and got `d3f5a12faa99758192ecc4ed3fc22c9249232e86` for 'empty'. Rather than report a mismatch, I hashed a file containing **literal CRLF bytes** and got **the identical value** - so PowerShell had injected `\\r\\n`. Proven, not assumed. Same class as the earlier CRLF torture-test artefact.

**Not reproducible by design**: the claimed root commit `f540649c006e88f64ff2d5d69df45a42ffa12fc8` cannot be re-derived without the exact author/committer identity and timestamps. With a fixed identity and date I obtained a deterministic root commit and a clean `fsck`, which tests the same machinery without depending on their environment.

**Settled by the coordinator**: the claim is that **every byte of every produced artefact came from our GCC and our assembler running natively on ARM64; the `make` and shell that drove them were obtained prebuilt and contributed no code.** My measurement supports exactly that.
