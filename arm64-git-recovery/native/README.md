# Native ARM64 Git recovery and assembly

This is the maintained recovery entry point. The adjacent historical `scripts/`
and `evidence/` directories remain unchanged. In particular, do **not** run the
old `assemble-mingit.sh` as a full-distribution builder: it uses deleted-machine
paths, dependency stubs, global pacman changes and a BusyBox shell.

**No full native distribution has been built by this recovery.** The tools here
recover real sources, prepare downstream patches, reject incomplete package
sets, assemble an explicitly unverified candidate, and exercise functionality.
They do not create a release ZIP or declare source/build/native compatibility
from a package name, compiler banner, PE header or assembly success.

## Post-restart integration

**MSYS consumer builds require the coherent jump-buffer SDK.** The
libxcrypt bad-argument case exposed a 176-byte public `jmp_buf` where the
runtime's signal-jump ABI reserves 256 bytes. The runtime owner reproduced
the clobber and closed the unchanged upstream case with corrected headers
and a rebuilt private runtime. Old MSYS executables must be recompiled:
swapping the new DLL under them does not fix baked-in offsets. The old
assembly roots remain preserved intermediate evidence, not newly qualified
consumers. MinGW Git/Tcl binaries are a distinct ABI and are not rebuilt
merely because the MSYS header changed.

The recovery lane subsequently built the pinned Git and preserved its `gd04`
assembly with scoped Git HTTPS, local push, PCRE2 and subtree evidence.
Those compiler, runtime and assembly roots are frozen inputs, not rebuild
targets. New work in this lane uses separate private copies and keeps compiler,
runtime and package ownership distinct.

The runtime owner's real `uname` repair has been consumed into a new coherent
copy. The consolidated `gd06` root places native Git, POSIX tools and their
actual dependency DLLs together; a cross-root or installed-Git PATH is not a
substitute. Local commits, both hook outcomes and recursive submodule clone
work in this root. Native Git fixtures use a real empty private config file,
not `NUL`. Loadable gates inspect the produced report and inventory counts
rather than a stale PowerShell exit-code variable.

Native ncurses 6.6 now builds its full C++ binding with the completed
MSYS-target hosted SDK. A native PTY consumer exercises the real C++ window
constructor/destructor, dimensions, variadic formatting, readback and input,
with exact mapped runtime/library identities. An earlier C-only bootstrap
remains separate. Host-generated terminfo is converted to the target's
`--disable-mixed-case` hexadecimal directory layout without changing terminal
bytes; only byte-identical case aliases are coalesced. The host database is
preserved outside the shipping stage. The colliding `WINDOW` manual alias
retains its complete content in `curses_variables.3ncurses`.

Source-built nano 9.2 has edited and saved exact Unicode file content through
native MSYS `openpty`/`fork`/`exec`, with live native-process/DLL checks and
bounded cleanup. This editor is still an explicitly NLS/libmagic-disabled
bootstrap, not full package admission. Its real `rnano.exe` alias preserves
restricted-mode invocation. The separate ConPTY fixture is not qualified:
its native Win32 control also inherited non-console standard handles.

Tcl/Tk 8.6.18 now runs a real native window, PNG/font operations and a Unicode
keyboard-to-save callback. Tk's original failure was recursive `cexp` in the
producer CRT; `relink-tk-crt.py` uses the repaired CRT with unchanged Tk objects
and optimization flags, preserving the failed build. `stage-tcltk.py` adds the
real interpreter, DLLs, libraries and development headers at `/usr/bin/wish`
in a new root. The `gd10` successor also restores required empty `/tmp` and
`/var/tmp` directories; stage merges now preserve empty directories rather
than silently dropping them from file-only inventories. Gitk displays actual local commits and a Unicode diff
with the upstream-supported repository-local `gui.encoding=utf-8` setting.
This does not change Windows' default codepage. GitGUI currently exits because
native `cygpath` is absent; runtime-owned utility recovery is separate.

The distinct MSYS LP64 OpenSSL target builds with native Windows-hosted GCC,
using upstream `shared_argfileflag` response files rather than a compiler
proxy. Its private runtime copy passes real loopback TLS and rejects both an
unrelated CA and a wrong hostname. The initial six-recipe upstream replay
failed RSA legacy-provider conversion: a dynamic provider's RNDR feature probe
exits on an illegal instruction. The maintained CPU-platform patch selects
OpenSSL's existing Windows feature-query path for Cygwin/MSYS, without defining
`_WIN32` globally or disabling legacy algorithms. The rebuilt consumer loads
the active legacy provider without exceptions, passes the original six
recipes including RSA conversion, and retains the TLS/negative-certificate
behavior. Full upstream coverage remains separate. The initial binaries and
failed replay remain preserved; this CPU-policy change does not repair the
runtime's independently investigated exception coverage in dynamically loaded
DLL constructors or its outstanding whole-cohort FP metadata boundary.
The full old-cohort OpenSSL replay was deliberately interrupted once the
header mismatch was confirmed; its partial log is not full-suite success.

MSYS gettext 0.22.5 source preparation now retains all 3,758 entries of its
nested autopoint archive. Only four outdated `build-to-host.m4` patch contexts
are adapted; missing contexts, added/dropped files and changed archive member
sets fail closed. This is source preparation, not a built gettext package.
Shared MSYS dependencies now require the coherent, signature-bound MSYS
libtool 2.6.2 generator inputs. They use the actual `aarch64-pc-cygwin`
compiler triple: the patched Cygwin rules provide `msys-` DLL names, whereas
the incorrect `aarch64-pc-msys` alias in the library driver silently disabled shared libraries.
Post-configure checks reject static-only fallback. Compile-only jump-buffer
guards also reject old headers before producing or executing target code;
those guards do not replace the producer's coherent headers/CRT/DLL receipt.

Fresh libxcrypt now produces the real shared MSYS DLL with corrected headers.
Its uninstalled tests need an explicit DLL search directory: native libtool
wrappers generated by the bootstrap embed `/c` paths, while the native runtime
imports drive paths under `/cygdrive`. An unchanged-wrapper control fails
without that directory and succeeds with it. The symbol test separately
recognizes only COFF `.refptr._crypt_` records as references to already-private
symbols; public and unexpected symbols remain checked. A fresh replay keeps
all 234 compiled inputs unchanged and reaches 52 passed, one upstream skip
and one remaining `explicit-bzero` coroutine failure. That standalone
`getcontext`/`makecontext`/`swapcontext` consumer fails fast in the runtime
path; it is not evidence of a hashing or zeroization algorithm defect.
The runtime owner has since corrected the ARM64 context layout and switch
path and sealed a successor SDK that runs the original consumer successfully.
The subsequent normal full-library rebuild completes all 54 upstream cases:
53 pass, one upstream getrandom-fallback case skips, and none fail. Both
formerly failing cases pass. A separately compiled consumer of the installed
import library exercises a bcrypt known answer, mismatch rejection, invalid
settings, salt generation and hash roundtrip while a held native process
confirms the exact relocated crypt/runtime DLLs. These are synthetic library
operations, not OS credential operations. The pipeline lane has also admitted
separate `libxcrypt` and `libxcrypt-devel` pacman archives from the exact
payload, with an extracted native consumer. Only the development package
provides `libcrypt-devel`; no legacy runtime provider is invented. Earlier
failures are preserved, not relabeled.

The remaining SSH/editor source graph has also been recovered and prepared:
Heimdal 7.8.0, Berkeley DB 6.2.32, MSYS SQLite 3.53.4, libcbor 0.14.0,
libfido2 1.17.0, file 5.48, Readline 8.3.003, MSYS zlib 1.3.2, bzip2
1.0.8, XZ 5.8.3 and Zstd 1.5.7. CMocka 1.1.8 is a source-only test
dependency; its MinGW recipe supplied an official archive pin, not target
binaries or a substitute ABI. Real Linux JSON and po4a prerequisites were
restored by the toolchain owner after measured failures. XZ translated
manual generation was not disabled.

`sources.py` supports checksum-bound tar, ZIP and individual GNU patch
inputs. ZIP extraction rejects traversal, duplicate/case-alias entries,
links and special file types while retaining executable modes. Readline's
three official patches precede its complete MSYS patch stack; only exact
current contexts are adapted. SQLite's license and extension build inputs
and Readline's `inputrc` remain part of prepared source inventories.
FIDO2's Windows Hello requirement remains enabled, but source preparation
does not authorize credential/device operations. None of these prepared
sources is a built or admitted native package.

`build-msys-cmake.py` provides the subsequent CMocka/CBOR/Zstd build path.
It selects CMake's existing `MSYS` platform and the real Cygwin-target GCC,
keeps required features and upstream cases enabled, and rejects incomplete
dependencies or unreviewed skips. A real no-language CMake control confirms
`msys-` DLL naming and private `CMAKE_STAGING_PREFIX` installation while the
logical package prefix remains `/usr`; it does not install into global `/usr`.
The first real CMocka compile exposed producer SEH/`returns_twice` failures.
Its exact preprocessed reproducer preserves upstream optimization, warning
and stack-protection flags; compiler recovery owns that repair. The optional
source-tree compilation-database symlink is separately disabled without
removing the real build-directory database.
The qualified C-compiler successor now compiles the complete fresh CMocka
source tree with those flags. `--build-only` stops before CTest or installation,
records `native-msys-cmake-built-not-tested`, and does not consume an observer.
This is not package admission. Its retained C++ compiler/runtime/libraries and
producer source lock remain separate from the later canonical recipe merge.
Single-config CMocka test metadata also needs its DLL path corrected from
`build/src/Release` to `build/src`. The maintained source patch leaves emulator
and multi-config handling unchanged. `cmake_test_replay.py` prepares a separate
CTest tree for already-compiled inputs, preserving every original command,
working directory and expected-failure property. Native CTest discovery must
roundtrip those semantics exactly; preparing that metadata executes no tests.
`finish-msys-cmake.py` consumes that exact replay, the original source/compiler
receipts, and a current qualified observer. It requires every original test
exactly once before installing through native CMake into a new private stage.
It never recompiles the existing objects, never installs after a failed or
incompletely observed suite, and still leaves installed API/package admission
as explicit follow-up gates.
Libcbor may use `--cmocka-build-result`, `--cmocka-source-manifest` and
`--cmocka-build-sha256` only together with `--build-only`. This binds the
existing CMocka header/import/DLL paths and complete source/build inventories
to the same compiler receipt, disables unrelated pkg-config discovery, and
copies or installs nothing into CMocka. The dependency's built-not-tested
status flows into the new receipt; this mode cannot run or qualify tests.
The fresh native MSYS libcbor 0.14.0 build now completes with its upstream
C23 selection, custom allocation support and all 28 registered CTest targets
retained. It remains built-not-tested; CMocka's execution qualification is
still required before its downstream test results could be admitted.
In 0.14, allocator replacement is unconditional: the old `CBOR_CUSTOM_ALLOC`
CMake variable is unused. The maintained recipe checks the actual
`cbor_set_allocs` export instead of treating that stale flag as feature proof.
The original build receipt remains unchanged, including its unused-variable
warning; export presence is not a runtime allocator test.

`fido_build_inputs.py` creates metadata-only pkgconf views of the real CBOR,
libcrypto and zlib headers/imports/DLLs. It preserves each dependency's actual
qualification status and binds the older crypto/zlib inputs through the exact
retained MSYS ABI payload of the C-compiler delta. Genuine native pkgconf must
resolve their original versions and explicit paths without installed-package
fallback or prefix relocation. No dependency payload is copied or installed.
The FIDO2 CMake profile retains Windows Hello, both libraries, tools, examples,
manuals and test targets, but currently permits **build-only** operation:
device/authentication operations and test/install/admission are not authorized.
CTest execution now requires the qualified native job observer as well as its
normal result checks. Upstream expected-failure properties remain unchanged;
missing child observations and unrelayed high native statuses reject the run
even when CTest itself returns zero. The native CMake/Ninja drivers are not
wrapped as target tests.
The Zstd profile additionally requires `--bootstrap` and
`--bootstrap-manifest` for a verified private copy of its shell-test drivers.
Its programs and upstream CLI tests stay enabled; missing `sh`/`uname` cannot
silently remove that coverage. This emulated test-driver scope is recorded
separately from native CMake/Ninja/GCC provenance.
For native Windows source readback, preparation accepts the Zstd-only
`--windows-launcher-aliases` option. Its two internal `unzstd`/`zstdcat`
launcher links become byte-identical executable copies of the actual `zstd`
script, which still dispatches by invocation basename. The original link
targets and transformation hashes are recorded. This does not omit files,
create stubs, change runtime symlink tests, or relax Perl's strict prerequisite.
The native-host CMake recipe also creates real hardlinked `zstdcat.exe`,
`unzstd.exe` and `zstdmt.exe` aliases plus the two manpage aliases, retaining
upstream basename dispatch and refreshing links after a rebuild. Other hosts
keep symbolic links. The complete fresh native MSYS Zstd compilation now
finishes with shared/static libraries and all upstream CMake targets, but is
sealed as built-not-tested until observed execution and installation finish.

The GNU MSYS driver also has an `xz-msys` profile for the pinned XZ 5.8.3
recipe. It requires native iconv/gettext development payloads, shared and
static liblzma, the CLI programs, POSIX threads, NLS and Doxygen API output.
Missing gettext, Doxygen, or a configured feature fails rather than selecting
a reduced bootstrap profile. All upstream XZ license texts are retained.
This source-only recipe still requires an allocated build and native admission.
Its missing documentation prerequisite is now recoverable with
`recover-documentation-driver.py`: the official, checksum-pinned Doxygen
1.18.0 ZIP and paired source license stay in a standalone **x64 emulated**
bootstrap directory, never in the native payload or shared MSYS installation.
The native-ARM64 gate must explicitly reject its five parsed x64 PE files.
Actual API-document generation, not just a version banner, qualifies this
limited bootstrap role.

XZ's prepared documentation helper has an explicit Windows-path mode with a
single documentation-parser thread. `generate-xz-api-docs.py` exercises the
real source helper; its fixed Doxygen relay preserves raw Windows exits across
the foreign shell. `build-msys-library.py --package xz-msys` requires the
qualified `--documentation-driver` and `--documentation-manifest` pair.
This is not a replacement for the still-required native test-tree observer.

Native test status also needs an explicit cross-runtime boundary. An actual
MSYS `abort` returned raw Windows status 1536 while an emulated MSYS Perl
parent observed success. The native process relay preserves 0..255, maps
other nonzero statuses to nonzero 255, and records the exact raw value.
It never manufactures a POSIX signal or substitutes for a compiler.
OpenSSL's MSYS replay additionally uses native drive URIs, byte-preserving
Perl I/O, actual PE export tables and a private CA configuration. All 355
recipes/4,535 assertions subsequently pass, but full admission still requires
complete native child-exit observation and bounded cleanup. Its CMP fixture
now stops the process handle it owns rather than signaling a PID printed
from a different MSYS namespace. Earlier failures and narrower receipts
remain preserved rather than retroactively promoted.
The GNU MSYS library driver now also requires an explicit qualified native
job-observer copy. Native Automake executables use the real process relay;
foreign scripts remain normal, while the outer observer covers nested target
processes. A successful foreign parent cannot override missing observations
or an unprotected high native exit. This is test-driver protection, not a
compiler wrapper or a claim that historical suite logs had that protection.
The initial observer's exact published hash is rejected at copy and execution
boundaries: its PID-reuse classification could mistake a later foreign process
for an earlier native target. Retained reports from that observer remain failed
evidence; a versioned, newly qualified producer handoff is required.

Perl's shared architecture guard now succeeds with the repaired runtime, but
strict native symlink creation still lacks privilege. Neither the guard nor
`nativestrict` is bypassed. The pinned Perl cross-build documentation requires
an actual supported target transport or valid pre-generated target
configuration; it supplies no WSL-local runner. Neither missing input is
invented. GCM's neutral IL classification, native SSH, full OpenSSL suite and
full package/admission gaps remain separate completion items.

## Pinned inputs, not a latest-release claim

`sources.lock.json` records official URLs, exact commits/versions and SHA-256.
Hashes for repository archives were measured from official downloads; hashes
for GNU make, Bash, coreutils and Perl also match their pinned package recipes.
The recovery tool never evaluates a `PKGBUILD` or installs a package.

| Source | Pin / purpose |
| --- | --- |
| Git for Windows | `2.55.0.windows.5`, commit `32c4f7689275d233577576630e1ac5b7eb354eb0`, as selected by the recovered recipe |
| Git for Windows MINGW-packages | `d65b87de173ac2209a63cef8c4528669b5571fd3` |
| Git for Windows MSYS2-packages | `d6337d462fc6c0ed909358e7173e7a266d7aacbd` |
| MSYS2 upstream package recipes | `9154e8a73cf7813e3e4b87df14e6aea5776dc571` |
| Git for Windows build-extra | `21d6ed86c38d28e89c950c9e1e349b6edefd1afb` |
| Historical upstream recovery baseline | Git 2.47.1, zlib 1.3.1, OpenSSL 3.4.1, expat 2.6.4, PCRE2 10.44, curl 8.11.1 |
| Prepared POSIX sources | Bash 5.3 + 15 release patches; make 4.4.1; coreutils 8.32; Git for Windows Perl 5.38.2 |
| Additional POSIX build utilities | sed 4.9, gawk 5.4.1, grep 3.0, findutils 4.11.0 from the pinned MSYS2 recipe snapshot |

The historical upstream Git tarball does not recover the two locally modified
Makefile cleanup recipes mentioned in B13. It is **not** an exact identification
of all lost source bytes, and rebuilding it is not expected to reproduce the
historical binary hash. Repository archive hashes are also not substitutes for
makepkg's differently generated VCS-source checksums.

The recipe repositories are not interchangeable. At these pins, Git for Windows
has coreutils 8.26, make 4.2.1 and Perl 5.38.2; MSYS2 upstream has coreutils 8.32,
make 4.4.1 and Perl 5.42.3. This recovery deliberately uses the newer MSYS2
coreutils/make stacks for downstream bring-up, while retaining Git for Windows
Bash/Perl patches. Neither choice is yet a native compatibility result.

`prepare-posix-tools.py` preserves the selected utility recipe steps, including
sed's patch/autoreconf/patch ordering and strip levels. The older grep pin is
intentional: the MSYS recipe documents Windows line-ending behavior needed by
configure scripts. Its obsolete permission-test substitution does not match
the pinned source, so preparation records that no-op and retains the strict
check instead of introducing a new relaxation. These packages require
MSYS-target dependencies (including PCRE1 for grep and MPFR/readline for gawk);
the recovered MinGW/UCRT libraries are not ABI substitutes.

The bootstrap builder now also produces real sed, grep, gawk and findutils
executables against the coherent MSYS runtime receipt. Native scenarios cover
CRLF/text/binary/error behavior, awk arithmetic/arrays and its `readfile`
loadable, Unicode/space-containing file names, and find/xargs invoking an
ordinary native Windows program with quoted, empty and Unicode arguments.
These are explicitly limited bootstrap packages: NLS is disabled, grep omits
PCRE1, and gawk omits MPFR/GMP/readline. Their Linux cross-build provenance is
retained. No locate database or global filesystem scan is part of the fixtures.

The MINGW recipe tree also contains different-era slots: curl 8.22.0,
OpenSSL 3.5.7 and PCRE2 10.47, but zlib 1.2.11 and expat 2.2.5. Those are
**recipe declarations**, not a measured installed package closure, nor an
instruction to downgrade libraries. Resolve the concrete package/provider set
before a full build; do not silently substitute the historical static closure.

### Actual native-Windows static library baseline

`build-native-zlib.py` builds the recovered zlib 1.3.1 static library using the
frozen native Windows ARM64 GCC, assembler, linker and archiver supplied by the
toolchain lane. It derives the source-object list and checks flags against the
official `win32/Makefile.gcc`; a native Python driver runs those compile/archive
commands sequentially, without an emulated make or shell. The upstream headers,
sources and example programs remain unmodified.

An explicit one-job allocation is required. The recipe verifies the complete
source manifest, the supplied native-tool identity snapshot, GCC-resolved
support programs, and CRT/import libraries. It holds Python/GCC/minigzip
processes for the controlled live native gate, checks the test executables with
the raw PE gate, and checks all 15 static archive members as ARM64 COFF with
bytes identical to the compiled objects. Source/tool/library identities are
checked again before the stage is accepted.

The `native-zlib-windows-01` run passed zlib's upstream example through its
final dictionary test and independent compression/decompression against
Python's gzip implementation for a 176,128-byte fixture. The stage contains
`lib/libz.a`, `include/zlib.h`, `include/zconf.h` and the actual zlib license.
Its static archive is 118,204 bytes, SHA-256
`bacccbafa4ea68b18c05f35518e599bfbd298cf50bd63ef11403b0644a95cefd`.

This is **native Windows-hosted build and execution proof for that historical
static library**, distinct from the earlier Linux cross builds. It is not
final Git/toolchain admission: the toolchain lane's external-data ADRP/refptr
issue was still open, and final-distribution artifacts must be rebuilt and
requalified after that repair. No Clang, source address workaround, replacement
stdio implementation or false latest-release claim is involved.

### Updated native library candidates

The later recipe snapshot `msys2/MINGW-packages` at
`fbb9173f78adaea078046ea53e35cee47e7a5527` supplies source hashes for
zlib 1.3.2, Expat 2.8.4, PCRE2 10.48, OpenSSL 3.6.4 and curl 8.22.0.
Their official release archives are locked separately from historical inputs.
This records the selected recipes, not a latest-release assertion. The
OpenSSL has now been compiled and installed as a dependent-build candidate;
curl still requires the remaining dependency closure. Neither is a full
distribution acceptance result.

### Current downstream integration boundaries

The export-filter-fixed Bash and make builds pass their native primary
scenarios. Bash's real `print` and `mkdir` loadable callbacks now work, with
exact mapped-module identities and all 44 PEs (including extensionless modules)
checked. The combined Bash/make/coreutils bootstrap root remains limited:
NLS/readline/GMP omissions and Linux-hosted compiler provenance are not erased
by native execution. Its runtime currently reports `uname -m` as `unknown`;
that must be repaired by the runtime owner rather than relabeled by a recipe.

Native libiconv 1.19 static and shared builds have completed upstream checks
and installation. Shared libtool wrappers require the repaired GCC executable
suffix. Gettext 1.0 needs the adapted libasprintf include-order patch, which
preserves both private and backward-compatible public symbols; an older
recipe patch redefined the private symbols twice. A space-free, byte-identical
compiler input avoids libtool's broken C++ predependency parsing. A later
output audit also caught libtool silently producing static libintl after its
legacy file-magic test rejected a real ARM64 `advapi32` import archive. The
driver now applies the pinned Windows dependency-check policy only after
independent archive inspection and requires the requested DLL/import/static
outputs. The earlier static-only libintl result is not shared-package success.
Libssh2 1.11.1 builds with OpenSSL and zlib and passes
its available offline test; actual SSH/SFTP service fixtures remain required.

OpenSSL's shared test transport canonicalizes local drive paths, file lists,
file URIs and password-file arguments while preserving distinguished names
and HTTP paths. It uses a separate test-driver hook, **not** `EXE_SHELL`, which
would suppress native server coverage. Store, key-conversion and CMP semantic
checks have passed; server lifecycle and complete-suite closure remain open.
The installed native CLI also exchanged an exact TLS payload with an
independent loopback peer and rejected an unrelated CA and a wrong hostname.
Its live ARM64 process and exact loaded OpenSSL DLLs were observed separately.
`bounded_process.py` contains the entire fixture tree in a kill-on-close
Windows job and rejects timeouts or orphaned children as ordinary success.
The existing candidate uses OpenSSL's `lib-arm64` default; future clean builds
explicitly configure the distribution's `lib` layout. Installation alone does
not promote either candidate.

### Perl bootstrap safety boundary

A failed Perl symlink-creation probe left `issymlink` empty. Two upstream
shell expansions could then execute a pathname as a command. During bring-up,
this caused C files to be interpreted as shell input and invoked the isolated
bootstrap's `autorebase.bat`. The pipeline owner preserved the resulting DLL
and rebase-database evidence. This is not a successful Perl build.

Prepared Perl sources now require fail-closed guards at **both** expansions.
The native driver also requires a private bootstrap copy, a minimal
credential-free child environment, a real ARM64 `uname` result, and successful
strict symlink creation before configuring. No false predicate or architecture
label substitutes for a missing prerequisite. Windows link-fixture evidence
currently reports error 1314 (privilege not held); no system setting was
changed. The portable `/proc/cygdrive` namespace avoids mixing the bootstrap's
`/c` paths with the native runtime's `/cygdrive/c` paths.

The explicit alternative
`build-native-perl.py --profile msys-system-symlink-bootstrap` retains the
preserved **5.38.2** source/recipe pins and accepts the current protected native
C/C++ compiler receipt with the complete paired runtime DLL/import/CRT overlay.
The original `nativestrict` profile remains the default and its blocked
qualification is unchanged. No privilege or system setting is changed.

This alternative first checks real MSYS POSIX system-file symlinks: `-L`,
`readlink`, target mutation, regular-copy rejection, dangling links, directory
links, physical `pwd`, and nonempty Perl-style/external predicates. This is
the documented `winsymlinks:sys` mode, not a plain-copy substitute. Its receipt
always records `NativeWindowsSymlinkQualification=false`.

Current evidence exposes a **separate compiler host-file-access blocker**.
Those POSIX checks pass with runtime `d70cfb46...`, but the current UCRT-hosted
GCC reads both source and header system-file links as `!<symlink>` cookie bytes.
An ordinary source with the same flags compiles successfully. The bounded
`probe-perl-upstream-symlinks.py` replay of unchanged Configure and Makefile.SH
fragments confirms `issymlink='test -h'`, `LNS='.../ln -s'`, and symbolic-link
recipes for `opmini.c`, `perlmini.c` and `universalmini.c`; invoking GCC through
the native MSYS parent on that mini-source still fails. The upstream regular
source branch does not resolve these links before compilation.

The alternative therefore stops at this failed compatibility preflight. No
full Configure/miniperl/Perl/XS/test-harness/install success is inferred, no
link is flattened to hide the failure, and no missing gdbm/DB/crypt dependency
is silently omitted. This result does **not** mean MSYS system-file symlinks
are invalid POSIX symlinks or that every possible Perl bootstrap requires
Windows-native symlink privilege.

Failed Perl logs include an inherited environment dump and are **private
diagnostic artifacts**: never publish, upload, commit or package those raw
logs. Use only the separately filtered incident receipts. Bootstrap recovery
belongs to its owner and must be coordinated after all consumers have drained.

### Native Windows helper build-tool replay

`export-helper-sources.py` verifies the full Linux source snapshots, then exports
only the complete helper subtrees and licenses with an explicit scope manifest.
This avoids pretending that Windows can traverse the full source tree's WSL
`RelNotes` symlink. The export is not a replacement full Git checkout.

`build-winapi-helpers.py --native-root ... --pwsh ... --artifact-gate ...`
uses native Windows GCC, make, Bash and coreutils, with mandatory native PE
input gates and source/tool/archive fingerprints. It has built all four real
helpers without putting an emulated bootstrap on PATH. The newly built askpass
and askyesno dialogs passed synthetic value/cancel/Yes/No interaction and visual
checks; current-binary wincred storage and selector-with-Git qualification
remain separate pending work.

`copy-toolchain-input.py` produces a hash-identical, space-free compiler input
for libtool's verbose C++ link parser. It preserves the published prefix and
explicitly does not turn a scoped toolchain receipt into a new full C++
qualification. Consumers must still build and exercise their actual outputs.

After the missing Meson module was observed, the official Meson 1.12.0 source
runtime was restored privately on native Python. `build-native-pkgconf.py` uses
native Python/Meson/Ninja/GCC with bounded build parallelism, runs all 29
registered upstream tests, and exercises `.pc` version, transitive dependency,
variable and rejection controls. The resulting pkgconf 3.0.5 and aliases are
native ARM64. This is a portable upstream Meson runtime, not a claim that the
MSYS2-specific Meson packaging patches were applied.

`build-native-cmake.py` uses explicit native Windows ARM64 GCC, CMake and Ninja
paths and a fresh directory per attempt. The portable driver pins are CMake
4.4.3 ARM64 ZIP SHA-256
`7b410ddd00e24c7250eec7452da2348a4a70437aa87e9cda0a20d6a85662fcff`
and Ninja 1.13.2 ARM64 ZIP SHA-256
`e52f0bdef9dfb1003229dbd6508a508c4073fd017247002adc66e5e806cb0391`.
Both downloads match official release digests and their PE inventories are
ARM64. No global installation, PATH change, emulated shell or compiler
substitution is required.

The recipe builds static and shared libraries with source/tool/support/CRT
identity records, runs nonempty upstream tests without ignored failures, then
installs into separate candidate stages. It is not a replacement for full
distribution dependency resolution. In particular PCRE2's CLI compression and
editline integrations, zlib's separately packaged minizip, and Expat man-page
generation are explicitly outside these library candidates.

Actual results using the later refptr-corrected native compiler:

| Candidate | Result |
| --- | --- |
| Historical zlib 1.3.1 | Fresh static build and gzip round trips passed; archive SHA-256 `c13de79004617fa3080618bde78437a5e486cb17bd7baf34a4dacc87775b91d8` |
| zlib 1.3.2 | Static/shared build and all 18 CTest cases passed |
| Expat 2.8.4 | Static/shared builds; 4,884 upstream checks passed for each; installed XML parsers accepted valid XML and rejected mismatched tags, with native identity and exact shared DLL path observed |
| PCRE2 10.48 | Initial cache epoch failed; the later cache-fix epoch passes the configured native interpreter/JIT suites as described below |

The zlib test driver explicitly runs the missing `asx_config` fixture before
the entire suite because the pinned upstream CMake graph incorrectly depends
on `as_config`. No test is omitted. Expat's upstream `run.sh` only selects
direct execution versus Wine; the native Windows driver runs the exact
`runtests.exe` directly instead of requiring Bash solely for that dispatcher.
Both initial dispatcher/fixture failures remain separate failed evidence.

PCRE2's bounded discriminator (`test-pcre2-runtime.py`) runs a literal pattern
through 8/16/32-bit interpreters and JIT. All interpreters pass; all JIT cases
exit `0xC000001D`. The diagnostic fixture
`fixtures/pcre2-jit-probe.c` located the fault **during JIT compilation**, before
generated-code execution, in the linked libgcc
`__aarch64_sync_cache_range+0x0c`: opcode `0xd53b0023`,
`mrs x3, ctr_el0`. SLJIT selects GCC's advertised `__builtin___clear_cache`
before its Windows API fallback. The toolchain owner owns repair of that
Windows compiler-runtime boundary. JIT is not disabled, no application
cache-flush override is added, and earlier native compiler round trips do not
qualify this newly exercised operation.

**Cache-fix follow-up:** a distinct immutable native toolchain prefix supplied
libgcc SHA-256
`ee091009c9893c049fc2f13a24f3ce3d70d3a5431ca92254d786d89a07f60adc`,
implementing the Windows cache synchronization API. A clean PCRE2 build,
without a SLJIT override or JIT-disabled configuration, now passes:

- Exact complete output for the six 8/16/32-bit interpreter/JIT literal cases.
- All four configured upstream suites: `pcre2_test_bat`,
  `pcre2_grep_test_bat`, `pcre2_jit_test` and `pcre2posix_test`.
- The installed programs' six live native process gates and raw ARM64 inventory.
- Eighteen public API match/no-match/span checks through the exact installed
  8/16/32-bit DLL paths, including Unicode/UCP and direct JIT calls.

The candidate contains 241 files. The 8-bit DLL is SHA-256
`631cd65ed9d1a33938e6cdb63dd3c2e866d1d9b2dc81c4cdfd813ccbf50c1bff`;
installed `pcre2test.exe` is
`52fa4b6ff79bdd527b0905d94aa3189ed81d48e75354cd36d0ae5390e50c58ec`.
The unchanged earlier exception probe also succeeds against the new DLL,
reaching both JIT compilation and matching. The original failed binaries,
illegal-instruction output and disassembly remain separate negative evidence.

The combined upstream build statically links its test/grep executables even
while producing shared libraries. Therefore executable tests alone do not
prove those DLLs were loaded. `test-pcre2-shared.py` explicitly loads each
installed library, compares the actual module path, and exercises its public
APIs. `test-pcre2-runtime.py` additionally supports the controlled native
artifact/process gates for installed executable testing. The build driver
requires its bounded exact-output comparison before attempting the larger
upstream suites. CLI compression/editline integrations remain outside this
library candidate; this is not full Git distribution acceptance.

## Recovery and preparation

Use Python 3.12 or newer. No third-party Python dependencies are needed.
On Windows, use explicit paths; on WSL, run the same project scripts through
their mounted path, keeping outputs on the owned ext4 build volume.

```powershell
python -B .\arm64-git-recovery\native\sources.py `
  --cache C:\build\git\downloads --output C:\build\git\sources
```

An existing download must match its lock hash. Extraction refuses traversal,
duplicate members, external links and unexpected prefixes. Each source has an
adjacent complete path/hash inventory. Reuse compares the **entire file set**,
including unlisted extra files, not just hashes of previously listed files.
Interrupted/failed extraction is retained and requires a new output directory.
For source trees containing symlinks, WSL is the supported extraction host.

With `patch` available on the host:

```powershell
python -B .\arm64-git-recovery\native\prepare-posix.py `
  --package bash --sources C:\build\git\sources `
  --cache C:\build\git\downloads --output C:\build\git\prepared\bash-01 `
  --regenerate
```

Use `make`, `coreutils`, or `perl` for the other patch stacks. `--regenerate`
runs actual `autoconf` for Bash or `autoreconf -fi` for coreutils. It does not
compile. Without it, the report explicitly leaves regeneration/recipe tail
work pending. Perl's full recipe additionally supplies `Policy.sh`, configure
layout and test settings; the preparation tool does not pretend those native
build steps ran.

All local patches must match checksums in the locked recipe. The fifteen GNU
Bash patches are downloaded and checked against that same recipe. Three named
older upstream patches retain their reviewed GNU patch default maximum fuzz 2;
all others use zero fuzz. Reports retain exact patch output, including offsets
and fuzz. Two uniformly CRLF Perl release files are normalized explicitly for
WSL patch, with before/after hashes. No reject is ignored.

Two additional maintained Bash recipe patches are recorded separately with
their own hashes. `bash-completion-requires-readline.patch` gates the MSYS
readline-only `completion_strip_exe` option when readline is disabled; it
preserves the enabled-readline behavior. `bash-install-fail-closed.patch`
propagates recursive installation failures that upstream make otherwise
ignores. They are downstream adaptations, not falsely attributed to the pinned
upstream source archive.

## Build ownership and first real POSIX applications

| Boundary | Owner / required outputs |
| --- | --- |
| Toolchain | Linux ARM64 host cross tools initially; later native Windows ARM64 host tools. Do not confuse these proofs. |
| Runtime | `aarch64-pc-cygwin/include/sys/cygwin.h`, `aarch64-pc-cygwin/lib/libmsys-2.0.a`, `bin/msys-2.0.dll` under the agreed toolchain prefix |
| This lane | Bash/coreutils/make/Perl recipes and Git distribution/package contracts |
| Pipeline | MSYS2 bootstrap, makepkg/ccache configuration, workflows and package-manager operations |

`build-posix-bootstrap.sh` builds first-stage make, Bash or coreutils against that
runtime boundary. Its fifth argument must be an explicitly allocated job count,
or `check` for a non-compiling preflight. Its sixth argument is a mandatory
normal-link/native-run readiness receipt, described below. It never installs into the toolchain
or a global MSYS2 root, removes no old build tree, and records compiler/runtime
hashes and a complete output inventory. A missing boundary aborts before build.
The driver invokes the source's known `config.guess` through its declared host
shell, including Bash's non-executable copy. Bash uses the recovered recipe's
in-source build layout rather than assuming its documentation rules support
out-of-tree builds. The driver attempts the full staged installation including
dynamic loadable examples: the executable exports the upstream MSYS-style
`libbash.dll.a`, and loadable modules link that actual import library. Host generator link flags
remain separate from those Windows target flags. An ignored loadable install
failure cannot result in a successful maintained build.

`build-native-posix.py` provides the separate native Windows-hosted GCC path
for these same three bootstrap profiles. It requires the coherent jump-buffer
and ucontext SDK, an explicitly qualified native job observer, a fresh output
root and an approved job count. Prepared source and recipe origin inventories
must match both the preparation receipt and `sources.lock.json`; Bash/coreutils
must already have their actual generator steps recorded. The private x64
bootstrap shell/make orchestration remains explicitly labeled. Input manifests,
source, SDK and bootstrap bytes are checked again even after a failed build,
and old result paths cannot be overwritten. Native behavior, loadable modules,
full-feature rebuilds and package admission remain separate gates. This recipe
does not authorize using the observer version with the known PID-reuse defect.

For a coherent MSYS dependency prefix, `merge-library-stages.py` accepts one
`--manifest` per `--stage` plus `--compiler-receipt`. It rejects failed build
receipts, byte drift and mixed compiler/runtime cohorts before copying.
The new manifest retains each input's limitations and pending qualification;
merging does not upgrade historical execution evidence or admit packages.

Completed builds produce `build-inputs.json` and a full stage
`build-evidence.json`; the latter is emitted only after checking the current
runtime receipt, compiler/archive tools and prepared source against the inputs.
`Test-NativePosixBootstrap.ps1` exercises native Bash and make from an isolated
combined bootstrap root, checks the exact loaded runtime in held processes,
and tests shell pipelines/signals/child status/path conversion and make
recipe/no-op/rebuild/failure behavior. It never labels those NLS/readline-disabled
bootstrap components as the complete distribution.
`package_posix.py` installs actual COPYING files and reproduces the coreutils
package tail (`libstdbuf.so.exe` to `libstdbuf.dll`, plus `etc/DIR_COLORS`).

If a full Bash installation is blocked after the core executable links,
`stage-posix-core.py --acknowledge-core-only` can explicitly select only
Bash/sh/make/the matching runtime and licenses into a fresh diagnostic root.
It revalidates both builds' source/tool/runtime inputs and records whether
full-install reports exist. It never runs automatically after a failed build,
never rewrites that failure, and never emits a full-package manifest.

The first coherent-runtime application run exposed additional real gaps:
both Bash and make exited **before main**, with status `0xE0000269` and
`Unknown pseudo relocation bit size 21` from the runtime. Bash loadable
examples separately failed to link because the generated auto-import object
could not resolve `_pei386_runtime_relocator`. These are held as runtime/linker
integration blockers, not bypassed with application relocation flags.

Coreutils 8.32 did build and stage successfully in that same epoch, with NLS
and GMP explicitly disabled. All 109 PE candidates in its 219-file stage
passed the raw ARM64 gate. `test-coreutils.py` then passed nine native scenarios:
printf, cat, sort, uniq, cp, mkdir, stat, sha256sum and rm, with exact outputs
and file-state assertions; held cat also passed native process identity.
This is measured coverage of those scenarios, **not all coreutils behavior**.
The harness uses a printf `\n` escape rather than an unquoted literal newline
in the Windows command line, and explicitly selects SHA-256 binary mode and
its `*` marker. Neither convention changes the target executable.

### Normal compiler-link prerequisite

File presence is insufficient. The raw `aarch64-pc-cygwin-gcc` driver was
measured requesting `-lcygwin`, not the MSYS runtime, and does not define
`__MSYS__`. Downstream builds therefore use the toolchain lane's maintained
`prefix/bin/msys2-gcc` driver and its explicit MSYS specs overlay. The raw
driver remains unchanged for the runtime build. This lane adds no `libcygwin`
alias, application-supplied runtime library flag or replacement startup object.

`runtime_readiness.py` requires a schema-1 JSON receipt from the runtime lane's
actual normal-link/native-run hello. Every file record is
`{"path":"<accessible absolute path>","sha256":"<lowercase SHA-256>"}`.
The required fields are:

| Field | Requirement |
| --- | --- |
| `schema`, `target` | `1`, `aarch64-pc-cygwin` |
| `compiler` | Current prefix `bin/msys2-gcc` file record |
| `base_compiler` | Current prefix `bin/aarch64-pc-cygwin-gcc` file record |
| `support_tools` | Complete `cc1`, `collect2`, `as`, `ld` file records, resolved using this driver |
| `runtime_link_inputs` | Records for `crt0.o`, `libgcc.a`, `libgcc_eh.a`, `libgcc_s.dll.a` as described below |
| `specs` | Actual MSYS overlay file record, inside this prefix |
| `installed_runtime_dll`, `import_library` | Current canonical runtime files from the boundary table |
| `runtime_dll` | Actual staged/tested DLL file record; its hash must equal `installed_runtime_dll` |
| `source`, `executable` | Hello source and linked executable file records |
| `default_specs_sha256` | SHA-256 of the MSYS driver's current raw `-dumpspecs` stdout |
| `link` | `argv`, integer `exit_code: 0`, `default_runtime_link: true` |
| `run` | Integer `exit_code: 0`, `process_id`, `created_utc`, `windows_image_path`, `windows_runtime_dll_path`, and file records `native_process_report` / `artifact_report` |

The normal application command is `msys2-gcc SOURCE -o EXECUTABLE`, with only
optional `-D__MSYS__`, `-g` or ordinary `-O` flags. No application `-l`, `-L`,
`-specs`, `-nostdlib`, startup object or arbitrary linker overrides are accepted.
The installed wrapper's internal maintained overlay is part of the toolchain,
not an application workaround. Hashing the overlay separately is mandatory:
`-dumpspecs` by itself need not expose every external overlay change.
Support program paths come from `gcc -print-prog-name=NAME`; bare names are
resolved against the same process PATH. Resolved files must be inside the
current prefix. `compiler_tools.py` checks both paths and hashes again, so an
assembler replacement or changed PATH resolution invalidates the receipt even
when wrapper, base compiler and specs are unchanged. This also applies to
future WinAPI helper build evidence, which checks support identities before
and after compilation. Earlier receipts without these records are insufficient;
do not retroactively add new support hashes to an old execution claim.

Runtime link inputs are resolved with this driver's `-print-file-name=NAME`.
`crt0.o` and `libgcc.a` must exist inside the prefix and use
`{"present":true,"path":"...","sha256":"..."}`. For `libgcc_eh.a` and
`libgcc_s.dll.a`, record either the same present-file shape or
`{"present":false}` when GCC returns the unchanged unresolved filename.
Optional absence is explicit, not proof of a missing required library being
acceptable. Installing an optional archive later also invalidates the receipt.
The helper `compiler_tools.runtime_link_identities()` produces this structure.
This prevents a compiler-runtime ABI rebuild from inheriting old hello proof
solely because the driver and specs did not change.

The native-process report must come from the controlled process gate, match
that run's PID/creation time/image, and contain `ProcessMachineTypeInfo` ARM64
identity. The controlled artifact report must pass and bind the Windows image
to the linked executable hash and the exact staged Windows DLL path/hash.
Receipt file paths may use `/mnt/c/...` for Windows-staged files while the
separate `run.windows_*` fields match the native reports' Windows paths.
The installed and staged DLL records are both checked, so staging different
bytes or updating the installed DLL invalidates an old receipt. Missing proof,
failed links/runs, changed compiler/specs/runtime bytes, or a mismatched live
image all block bootstrap. This receipt proves only the prerequisite hello,
not downstream package compatibility or complete loaded-module closure.

The bootstrap disables NLS, Bash additionally disables readline, and coreutils
disables GMP. These
outputs are deliberately **bootstrap**, not full-distribution packages.
`packages.py` rejects bootstrap metadata. Full Bash needs the maintained
readline/ncurses/gettext configuration; coreutils needs gmp/iconv/gettext;
make needs libintl and a real shell; Perl needs its runtime and libxcrypt
plus the Git Perl modules. Their dependency recipes are in the recovered
snapshots. Existing MSYS recipe architecture allowlists still omit ARM64;
changing an allowlist is not evidence that the target works.

For native Windows binaries, the separate toolchain target is
`aarch64-w64-mingw32`. The resolved historical CRT source is
`Windows-on-ARM-Experiments/mingw-woarm64` at
`70d63e7c9a477b8b275a9782b289fbf1614b6e9e`; toolchain recovery is owned by the
toolchain lane, not duplicated here.

## Full Git package boundary

`mingw-recipes/mingw-w64-git/PKGBUILD` and `mingw-w64-git.mak` contain the actual
full Git build, wrapper builds and builtin generation. The base package removes
send-email, Perl modules, GUI and askpass scripts. Include the split packages;
the base Git package is not the product.

`distribution.json` uses logical package IDs (for example `git-gui`, rather
than a hard-coded pacman architecture prefix). Its roots cover the full
`build-extra/make-file-list.sh` default package selection, the split Git
features, and native make/Perl. Transitive dependencies and their **exact**
versions come from each concrete package manifest. Library providers must be
resolved to those IDs before assembly; there is no fake `provides` package,
dependency bypass or automatic pacman invocation.

Keep the real curl variants and their dependency closure. The recovered full
curl recipe enables shared libraries, SSPI/LDAP, compression and libssh2, with
OpenSSL, Schannel and GnuTLS variants. The historical statically linked,
OpenSSL-only `--without-*` build does not establish those features.
CA data and TLS backend selection must match the binaries and configuration.
Do not turn off TLS verification to make a clone pass.

Real native credential helper sources are at:

```text
build-extra/git-extra/git-askpass.c
build-extra/git-extra/git-askyesno.c
build-extra/git-extra/git-credential-helper-selector.c
git-full/contrib/credential/wincred/
```

Their existing Makefiles include resources and Windows libraries; do not
replace these targets with placeholders. Preserve SSH/key/agent tools, shell
and Perl scripts, templates, Tcl/Tk, gitk/git-gui, terminal/editor behavior,
Git LFS and system configuration.

### Runtime-independent native helper stage

`build-winapi-helpers.py` reuses the upstream Makefiles to build askpass,
askyesno, credential-helper-selector and wincred. This is a separate
`aarch64-w64-mingw32` C-only stage and does not need the MSYS DLL. It requires
the toolchain owner's stable MinGW CRT/import-library boundary and an explicitly
approved `--jobs` allocation. `--check` performs only prerequisite queries.
It uses a new output directory, scopes PATH to the subprocess, hashes the
compiler/resource tool/link inputs, rejects input churn, and stages actual
licenses with the four real executables.

The output is labeled `built-not-run`, `linux-aarch64-cross`, and explicitly
not a full git-extra package. It cannot stand in for the remaining Git extras
or a native-Windows-hosted compiler.
The default is `--component all`; explicit `wincred` and `prompts` components
support independent bring-up without turning a failed all-helper build into
success.

`test-wincred.py` consumes the controlled PE and process gates and exercises
real Windows Credential Manager store/get/erase using a fresh UUID-based
`.invalid` host and clearly synthetic password. It first asserts that the
fixture does not exist, then always attempts cleanup after a store attempt.
It does not alter Git configuration or intentionally read unrelated
credentials. A failed cleanup remains a failure, never a passing helper
result. Direct `CredReadW` must return `ERROR_NOT_FOUND` for the exact fixture
key after teardown; an empty helper response alone is insufficient. If helper
erase fails, the harness removes only its own initially absent UUID key through
the Windows API and still fails the test.
The harness captures raw stdout/stderr before strict UTF-8 decoding, so invalid
helper output cannot disappear inside a Python reader-thread exception.

Initial execution against the recovered cross toolchain exposed two real
integration gaps: the prompt helpers' upstream `-municode` link was rejected,
and wincred built as native ARM64 but emitted corrupted protocol labels from
its C `printf("%s=", what)` path. Its stored synthetic username/password bytes
were correct; its `username=` / `password=` labels were not. Cleanup completed.
That initial wincred hash,
`8507e0f5f9bd8ef4c6e10a0787c0b4dd73d6cc41bf55236fa18ec030201e47a0`,
is a **failed functional artifact**, despite passing raw/native-process gates.
The toolchain lane owns repair; do not replace output labels, strip `-municode`,
or insert application CRT workarounds to make the component appear functional.

After the toolchain owner fixed and exercised normal `-municode` support,
all three prompt helpers built unmodified. `Test-NativePrompts.ps1` uses
the installed `winapp ui` accessibility harness and the controlled native gates
to exercise askyesno Yes/No and askpass Cancel/value, capturing raw output and
screenshots without screen-wide input. Actual askyesno Yes/No returned 0/1;
askpass cancellation returned 1. The accepted-value path still exposed corrupt
C/UCRT wide-printf output, so the overall GUI behavior report correctly failed.
Selector behavior remains pending a real native Git configuration dependency;
there is no replacement fake Git executable to make it appear operational.

**Ordinary helper ABI recovery, 2026-09-05:** after the compiler owner repaired
the Windows `va_list` ABI and rebuilt the CRT, a clean `helpers-abi-01` build
from the same unmodified upstream helper sources passed real wincred
store/get/erase and askpass value/cancel plus askyesno Yes/No. The harnesses
require exact output, including wincred's LF-delimited protocol and askpass's
single CRLF, with empty stderr. Wincred's own erase succeeded; independent
`CredReadW` confirmed absence without API-cleanup fallback. All tested
executables passed raw ARM64 and live `ProcessMachineTypeInfo` gates.

| Helper | Rebuilt SHA-256 | Evidence scope |
| --- | --- | --- |
| wincred | `ab2c063b457a9762d84c4e2fe4cc98a0805cf15404a7f59eb267a4fa7bd24e56` | Native synthetic credential store/get/erase, exact protocol output |
| askpass | `b73d81816480cf5b9dcf1b6a9609853162215e54253c0a32aede7aa44135bc81` | Native dialog cancel/value, exact synthetic value output |
| askyesno | `40487ac716dd38b8123fd37d0f889e056974b1761d4c5e4ed94362b9874c79ce` | Native Yes/No dialog and exit status |
| credential-helper-selector | `44f2b2cb55d3d41a1da0470f1baf5a49c6f7cd5e31b8f73e800238ef36b071a8` | Build and raw ARM64 gate only; native Git configuration dependency remains |

These are **Linux-cross-built helpers running natively on Windows ARM64**,
not a native-Windows-hosted build or complete toolchain qualification.
The compiler owner's separate named 16-byte aggregate argument-split issue
remained open during this narrow helper run. The clean build records current
GCC, resource tool, `cc1`/`collect2`/assembler/linker and CRT/import-library
identities; earlier failed helper hashes and their evidence remain historical
failures. No stdio replacement, application CRT workaround or stub was used.

**GCM blocker:** the pinned build-extra recipe selects GCM 2.9.1 ARM64 ZIP
`1b573743a6162415d8398cbd9e2201aa8c43fd291bf45c242a5a12fa5ded3bd1`.
The actual official download has 50 PE candidates: five parse as native
ARM64 PE32+, while 45 managed PE32 assemblies fail the strict PE32+ gate.
For example `gcmcore.dll` has raw machine `0x014c`, optional magic `0x010b`;
its config targets .NET Framework 4.7.2. That is not proof of x86 emulation,
but it **does fail the current all-delivered-PE-native-ARM64 contract**.
No exception has been added and no functionality claimed from its filename.

## Package snapshot and candidate assembly

Each package payload is already rooted at the final layout (`usr/...`,
`clangarm64/...`, `cmd/...`). Keep metadata and evidence outside it:

```json
{
  "schema": 1,
  "id": "bash",
  "version": "5.3.015-2",
  "target": "aarch64-pc-cygwin",
  "build_host": "linux-aarch64-cross",
  "classification": "functional",
  "source_ids": ["bash", "msys-recipes"],
  "source_lock_sha256": "<SHA-256 of sources.lock.json>",
  "build_evidence_path": "C:\\build\\git\\bash-build-evidence.json",
  "build_evidence_sha256": "<SHA-256 of that actual evidence file>",
  "depends": {"msys2-runtime": "<exact package version>"},
  "required_files": ["usr/bin/bash.exe", "usr/bin/sh.exe"],
  "additional_pe_files": ["usr/lib/bash/print"],
  "license_files": ["usr/share/licenses/bash/COPYING"]
}
```

That abbreviated dependency example must be replaced with the dependencies of
the actual build. Script/data-only packages use target/build host `data`.
List every extensionless or alternate-suffix PE loadable explicitly in
`additional_pe_files`; the single Bash module above is only an example.
Undeclared hidden PE files still fail, and declared files must exist with an
MZ header and remain PE candidates for the later raw-header and behavior gates.
The full contract also requires `cygpath` and preserves empty `tmp`/`var/tmp`
directories rather than losing them in file-only assembly.
All other packages require actual readable build evidence with a matching hash.
`windows-arm64-native`, `linux-aarch64-cross`,
`windows-x64-emulated-driver`, and `official-arm64-prebuilt` remain distinct
provenance categories. Metadata declarations are not execution proof.

```powershell
python -B .\arm64-git-recovery\native\packages.py snapshot `
  --root C:\build\git\packages\bash\payload `
  --metadata C:\build\git\packages\bash\metadata.json `
  --manifest C:\build\git\packages\bash\manifest.json
python -B .\arm64-git-recovery\native\packages.py assemble `
  --plan C:\build\git\plan.json --output C:\build\git\candidate-01
```

The plan is `{"schema":1,"packages":[{"root":"...","manifest":"..."}]}`.
Assembly rejects missing packages, version mismatches, dependency cycles,
changed/extra/missing files, empty required files, absent licenses,
case-insensitive collisions, conflicting file owners, unresolved links, known
stubs and hidden PE payloads. Identical shared files retain both owners.
Every copied byte is checked again.

Builtin dedup uses the new package's own `builtins.txt`, never the old 142-line
list. Only named, byte-identical copies of this `git.exe` may be removed.
Transport helpers and frontend aliases are preserved; already-absent builtins
are recorded separately from removed files. The native harness compares the
packaged builtin list against the exact tested Git.

Output is a directory plus `candidate-01.assembly.json` marked
**`assembled-unverified`**. There is intentionally no release ZIP command.

## Behavior and native identity

`Test-NativeGit.ps1` requires explicit paths to the coordinator's controlled
`Test-NativeArm64Artifact.ps1` and `Test-NativeArm64Process.ps1` helpers. It calls
them in fresh PowerShell processes, records their hashes, and propagates errors.
The process helper must use `ProcessMachineTypeInfo`, not merely the
`IsWow64Process2` tuple: an emulated shell was measured returning `0000/AA64`.

The wrapper restricts child PATH/configuration to the candidate and Windows,
requires full-distribution files, holds Git/Bash/Perl for native identity and
module observations, and runs `git-fixtures.sh` via the candidate's Bash.
Fixtures use only new, explicitly disposable directories; their local Git
commits never touch the project. They cover real init/commit/clone/fsck, positive
and negative hooks, recursive submodules with a spaced path, credential protocol,
local SSH-helper dispatch, Perl fork/wait status, make shell dispatch and
coreutils. SSH keys are generated and round-tripped. Optional HTTPS requires
both a URL and an exact expected commit.

The SSH transport and credential **fixture helpers are test inputs**, never
distribution artifacts or replacements for real helpers. They do not prove
SSH encryption/host keys, GCM, Windows credential storage or UI prompting.
The result remains `tested-subset-not-full-acceptance`: those routes, GUI,
complete loaded-module closure, and a native Windows compiler
compile/assemble/link/run round trip still require real integration evidence.

Lightweight controls use the standard library:

```powershell
python -B -m unittest discover -s .\arm64-git-recovery\native -p "test_*.py"
```

The synthetic MZ files in those tests are not executable images. Separately,
`git-fixtures.sh` supports an explicitly labeled `harness-control` mode so the
fixture itself can run on Linux; that mode is never accepted by the native
wrapper and never supplies target-native evidence.
