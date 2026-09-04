# clangarm64 native userland — availability verification

Status: **MEASURED**. Independent verification of `ea1641ea`'s negative claim.
Originated in **this verifier thread** (not the heartbeat context).

## Claim under test

> `awk`, `m4`, `bison`, `automake`, `autoconf` and `sh` are "genuinely absent"
> from the native ARM64 (`clangarm64`) userland.

The programme strategy rests on this: it is why `sh` is called the last gate and
why busybox was commissioned. Negative package claims had already been wrong
twice, so the claim was re-derived from source rather than accepted.

## Corpus and exact queries

| Item | Value |
|---|---|
| Database (metadata) | `https://mirror.msys2.org/mingw/clangarm64/clangarm64.db` |
| sha256 | `30ae099492ab642a6fe880f2999a71d79658867100671c2dd9a6a9dce60ed517` (570,808 B) |
| Database (file lists) | `https://mirror.msys2.org/mingw/clangarm64/clangarm64.files` |
| sha256 | `7734e9f76c8807a105541340026e2e6b9d449fa2f14e4f4bc99465462def338a` (6,222,600 B) |
| Packages indexed | **3,806** (matches `ea1641ea`'s figure — same corpus) |
| File entries indexed | **1,435,885** across 3,801 packages carrying file lists |
| Distinct `clangarm64/bin/*.exe` | **5,051** |

Four independent axes were searched, not just package name:
1. **exact binary name** — `clangarm64/bin/<tok>` and `<tok>.exe`
2. **substring over all 5,051 shipped executables** — catches `gawk.exe`, `mingw32-make.exe`
3. **`%PROVIDES%`** — 251 packages, 1,132 entries
4. **`%DESC%` free text** — catches a tool packaged under an unrelated name

## Detector controls (established before any result was counted)

Per the sensitivity/specificity standard now in force.

- **Sensitivity** — `sed`→`bin/sed.exe`, `grep`→`bin/grep.exe`, `perl`→`bin/perl.exe`,
  `pkgconf`→`bin/pkgconf.exe`, `diff`→`bin/diff.exe`. Axis fires on known positives.
- **Specificity** — `zzznotarealbinary`, `qqxxzz-nonexistent`,
  `definitely_not_a_tool_42` → **0 hits each**.
- **`%PROVIDES%` axis proven live** before trusting its zero: 1,132 entries parsed,
  positive control (`openssl`/`python`) returns 19 hits.

## Result — the five build tools: claim CONFIRMED

| Tool | exact exe | substring | pkg name | provides | desc | verdict |
|---|---|---|---|---|---|---|
| `awk` | — | only `czkawka_*` | — | — | — | **ABSENT** |
| `m4` | — | none | — | — | — | **ABSENT** |
| `bison` | — | only `btyacc.exe` | — | — | — | **ABSENT** |
| `automake` | — | none | — | — | — | **ABSENT** |
| `autoconf` | — | none | `perl-config-autoconf` only | — | — | **ABSENT** |

No `busybox`, `mawk`, `gawk`, `original-awk`, `goawk`, `nawk`, `toybox`, `dash`,
`bash`, `byacc`, `flex`, or versioned `autoconf*`/`automake*` package exists.

## Result — `sh`: claim FALSE AS STATED, CORRECT IN CONSEQUENCE

A native ARM64 shell **does** exist and was missed:

**`mingw-w64-clang-aarch64-brush` 0.4.0-2 — "Bash-compatible shell" — ships `clangarm64/bin/brush.exe`.**

Verified by measurement, not by database inference:

- package sha256 `f4ae5b9c1bc7c70cb160253800a68048876affb25ef65e01b2afbff8f15f4f39`
- `brush.exe` sha256 `1a9112d27f0de6128e7c570ff43c5744ef3b738d9b5917bce72fd723f5731f51`, 5,608,448 B
- **raw COFF read**: `Machine=0xaa64` (`IMAGE_FILE_MACHINE_ARM64`), `OptMagic=0x020b` (PE32+)
- **executed on this host**: `brush 0.4.0 (cargo:0.4.0)`, exit 0
- **live-process check**: `IsWow64Process2` → `ProcessMachine=0x0000`, `NativeMachine=0xaa64`
  ⇒ **not** WOW64, genuinely native; 22 modules loaded

### Capability: 24 of 25 core POSIX constructs pass

Parameter expansion (`${v%x}`, `${v#x}`, `${v-d}`, `${v:-d}`, `${#v}`), both command
substitution forms, pipelines, **heredocs (quoted and unquoted)**, `eval`, subshell
isolation, `if`/`else`, `&&`/`||` lists, `while`, `$((arith))`, `trap`, `test`
operators including the `x$v` idiom, and `${1+"$@"}` — all pass.

One genuine deviation: with `IFS=:`, `set -- a:b:c` yields `$1=a`; brush applies
field splitting to a **literal**, where POSIX applies it only to expansions.

### But it cannot run `configure`, and the cause is exactly one builtin

Run against a real **GNU Autoconf 2.71** `configure` (c-ares 1.34.5, 838,932 B),
the script **self-diagnoses brush as inadequate**:

```
error: command not found: exec
configure: This script requires a shell more modern than all
configure: the shells that I found on your system.
```

Builtin probe — 12 of 13 autoconf-critical builtins present:

| present | `trap` `unset` `shift` `return` `local` `export` `read` `printf` `LINENO` `${1+"$@"}` subshell-`set +e` |
|---|---|
| **MISSING** | **`exec`** — both the redirect form (`exec 6>&1`) and the replace form |

`exec` is precisely what autoconf's preamble needs (`exec 7<&0 </dev/null 6>&1`
and the `exec "$CONFIG_SHELL"` re-exec path). **The gap is one builtin.**

## Consequences

1. **The claim's operational conclusion survives**: no shell in `clangarm64` can
   run autoconf `configure`. Busybox remains justified — busybox `ash` implements
   `exec`.
2. **The claim's factual form does not survive**: it is not true that nothing
   native exists. A native ARM64 POSIX shell exists, runs, and is 24/25 correct.
   Any plan written on "there is no native shell at all" is built on a false premise.
3. **`awk`/`m4`/`bison`/`autoconf`/`automake` remain hard gates** — confirmed on
   four axes with controls. Busybox does **not** supply `m4`, `bison`, `autoconf`
   or `automake`; it supplies `awk` and `sh` only.

## Incidental corrections found while running the controls

- **`make` ships as `mingw32-make.exe`, NOT `make.exe`.** `make.exe` does not exist
  anywhere in the 5,051 executables. `mingw-w64-clang-aarch64-make` 4.4.1-5 is real
  and native, but **any script invoking `make` fails unless aliased**. My own
  exact-name sensitivity control initially "failed" on `make` for this reason —
  the shared-prefix/naming error family, caught mechanically rather than by care.
- **`libtool` 2.6.2-1 ships zero executables** — only the shell scripts `libtool`,
  `libtoolize`, `libtool-next-version`. Listing it as "present native tooling" is
  misleading: it is unusable without a working shell.
- **`texinfo` 7.3-2**: `info.exe`/`install-info.exe` are native, but `makeinfo`,
  `texi2any`, `texindex` are scripts (with `.bat` wrappers).
- A CRLF artifact in my own first torture-test file produced
  `syntax error at end of input`. Reporting that as a brush limitation would have
  been a false negative — the mirror image of the false positive caught in the
  encoding scan. **Test-harness line endings must be LF before any shell verdict.**

## Perl module probe (for `2918d1f1`'s native-vs-cross decision)

`mingw-w64-clang-aarch64-perl` **5.44.0-3**; 164 perl-related packages.

| Module | Status | Path |
|---|---|---|
| `Locale::Maketext::Simple` | **PRESENT** | `clangarm64/lib/perl5/core_perl/Locale/Maketext/Simple.pm` |
| `Params::Check` | **PRESENT** | `clangarm64/lib/perl5/core_perl/Params/Check.pm` |
| `Locale::Maketext` | PRESENT | core_perl |
| `Module::Load`, `Module::Load::Conditional` | PRESENT | core_perl |
| `IPC::Cmd`, `ExtUtils::MakeMaker`, `Text::ParseWords` | PRESENT | core_perl |
| `Locale::Maketext::Lexicon` | absent | (not required by the decision) |

**Both modules `2918d1f1`'s decision hinges on are present in core perl.** That
decision is not blocked by module availability.

## Labelling

- **Measured**: every hash, count, COFF field, `IsWow64Process2` result, construct
  pass/fail, builtin present/absent, and the autoconf rejection.
- **Derived**: that `exec` alone is what makes autoconf reject brush (the error is
  adjacent and consistent, but no patched brush was built to prove it).
- **Presumed**: nothing.

## Unverified / not attempted

- Whether adding `exec` to brush would make configure succeed (would require
  building brush; not attempted).
- Whether brush handles configure at full scale beyond the preamble.
- Other MSYS2 repos were **not** searched — `clangarm64` is the only ARM64 repo
  on the mirror; that itself was not independently confirmed here.
