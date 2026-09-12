# Local ARM64 runtime toolchain bootstrap

This recipe recovers **Linux-hosted** `aarch64-pc-cygwin` binutils and GCC,
then bootstraps the distinct `aarch64-w64-mingw32` UCRT toolchain. A
Linux-hosted cross compiler is not a native Windows-hosted compiler.

Run `bootstrap-cygwin.sh` with Bash inside an ARM64 Linux/WSL guest. Keep the
recipe in this repository but place dependency sources and objects on the
Linux filesystem. The default dedicated build root is
`/root/arm64-vnext-20260905/toolchain`; override with `TOOLCHAIN_ROOT`.
`JOBS` defaults to 14 and must respect the shared machine's compile budget.

```bash
bash bootstrap-cygwin.sh sources
bash bootstrap-cygwin.sh binutils
bash bootstrap-cygwin.sh gcc
bash bootstrap-cygwin.sh w32api
bash bootstrap-cygwin.sh cxx-headers
# Runtime lane publishes genuine target newlib/Cygwin headers here.
bash bootstrap-cygwin.sh libgcc
bash bootstrap-cygwin.sh w32api-libs
bash bootstrap-cygwin.sh probe
```

Each stage fails on errors and retains timestamped logs under `logs/`.
Source identities and actual source-blob IDs are recorded under `identities/`.
Each invocation snapshots the complete recipe into `recipes/` before running,
so editing the worktree cannot change an in-flight build's commands or inputs.
Configuration arguments are retained beside each build. Repeat a stage to
resume incrementally; the recipe does not delete trees or reset source changes.
No host packages are installed automatically. If configure/build reports
missing prerequisites, review and install only the required packages, record
the package versions, then repeat that stage.

`source-lock.json` is the portable source contract: exact Git URLs/revisions,
source blobs, ordered GCC/binutils patches with SHA256, the separate w32api
overlay, and native math archive SHA512 identities. Bootstrap queries this
lock rather than maintaining a second patch order, validates patch bytes
before every stage, and rejects any disagreement with its explicit source
guards. `python3 source-lock.py verify --gcc-source <pinned-GCC-directory>`
also checks the math identities against GCC's own prerequisite manifest.
`python3 -B test-source-lock.py` checks lock behavior without rebuilding tools.

Consumers of the accepted Windows cache epoch can read
`share\toolchain-epochs\windows-cache\manifest.json` inside the frozen prefix.
The effective inventory is `BaselineFiles` with the single `ChangedFile` hash
replaced by `LibrarySHA256`. Verify actual files read-only, then hash sorted
relative paths and their effective hashes for the toolchain cache identity.
Include that identity in the build/ccache namespace along with host, flavor,
and configuration. It covers headers, CRT/import archives, libgcc, compiler
backends, assembler, and linker; hashing only `gcc.exe` or using ccache's
driver-content check does not invalidate cached objects after these repairs.
The source-lock hash describes source inputs, not proof of executable identity.

On the clean Ubuntu 24.04 ARM64 recovery, actual failures required
`build-essential`, `texinfo`, `bison`, `flex`, `libgmp-dev`, `libmpfr-dev`,
and `libmpc-dev`. Runtime/downstream source regeneration separately required
`autoconf`, `autoconf2.69`, `automake`, `autopoint`, `gperf`, and `libtool`.
The latter two were installed only after libiconv/gettext preparation actually
failed to find `gperf`/`libtoolize`; recommended development packages were not
installed with them. The source packages'
version checks must not be bypassed. Package identities and install logs are
retained in the build root, not inferred from this list. Installing generators
after the first binutils configure can invalidate cached `YACC` values:
preserve and move aside only the reported `build/binutils/{gas,ld,binutils}/config.cache`
files, then repeat the stage. Do not run `distclean` or delete the build root.

Installed tools are under `prefix/bin/`; the target sysroot is
`prefix/aarch64-pc-cygwin/`. The runtime lane owns the recovered runtime and
newlib source/build. Headers, startup objects and runtime libraries require a
coordinated bootstrap cycle before ordinary C/C++ programs can link.
`gcc --version` is not an end-to-end toolchain verification.

The raw Cygwin compiler intentionally retains its Cygwin defaults. After the
runtime publishes `crt0.o` and `libmsys-2.0.a`, run the `msys-specs` stage to
install explicit `prefix/bin/msys2-gcc` and `msys2-g++` application drivers.
They define `__MSYS__`, select `-lmsys-2.0`, and use `_msys_dll_entry` for
application DLLs. The runtime DLL's own special `dll_entry` is distinct.
No misleading `libcygwin.a` alias is installed.

`generate-msys-specs.py` checks the real driver's target and expected spec
tokens before producing the overlay and identity record. Bind the wrapper,
underlying compiler, overlay file, and `-dumpspecs` output separately:
GCC's `-dumpspecs` prints built-in specs even with an external overlay.
A macro compile and `-###` linker trace do not prove runtime readiness;
an ordinary wrapper-linked application must execute successfully against
the matching DLL before downstream application builds consume the prefix.
The `__MSYS__` definition belongs in the driver `*self_spec`, not only
`*cpp`: a real native C++ compile demonstrated that the latter did not pass
the definition to `cc1plus`. `--profile-mode default` writes the automatically
loaded `specs` file and records that scope separately from an explicit overlay.
Both C and C++ must receive the definition without caller `-D` workarounds.

`cxx-headers` uses upstream libstdc++ configure in freestanding target-library
mode and installs both the `include` and `libsupc++` headers. It compiles
`<new>`, `<type_traits>`, placement new and LP64/long-double assertions. It
does not manufacture `c++config.h`, build a hosted libstdc++, or provide
thread/exception runtime verification.

`w32api-libs` preprocesses the pinned v12 official definitions using the
upstream ARM64 flags, then builds import libraries for the twelve named
runtime dependencies. These are not fabricated export definitions, but they
are also not the entire Windows SDK import-library set.

`probe` retains a timestamped directory with generated assembly, objects,
PE executables and hashes. Run `Test-CompilerProbe.ps1` in ARM64 Windows
against that directory, with a new evidence output directory. The positive
case must exit 73 and the deliberately incorrect arithmetic control must
exit 91. It exercises C/C++, explicit assembly, PE linking, a forced
128-bit division from libgcc, and the Windows loader without an MSYS CRT.
The positive case requires `GetProcessInformation(ProcessMachineTypeInfo)`
to report ARM64. `IsWow64Process2` alone did not distinguish native and
emulated processes on the recovery machine.

**Decoder limitation:** the pinned custom `objdump -p` was observed to
truncate PE32+ import symbols and interpret ARM64 `.pdata` with the wrong
entry size. Its output is retained diagnostically, not accepted as complete
import/unwind evidence. Independently parse the raw PE headers/imports.

The MinGW cross bootstrap uses separate build directories and installs to
`mingw-cross/`, leaving the Cygwin prefix unchanged:

```bash
bash bootstrap-cygwin.sh mingw-binutils
bash bootstrap-cygwin.sh mingw-headers
bash bootstrap-cygwin.sh mingw-gcc
bash bootstrap-cygwin.sh mingw-crt
bash bootstrap-cygwin.sh mingw-libraries
```

These stages still produce Linux compiler executables, with Windows-targeted
libraries. The header stage publishes compatibility headers from the same
pinned winpthreads source, not from an unrelated x64 installation.
The compiler uses `/include` as its sysroot header directory. The hosted
C++ library's configure must see the generated target `gthr-default.h`;
failure to detect threads is fatal, not silently accepted. If repairing a
previous misconfiguration, rebuild the affected libstdc++ objects: its
disabled dependency tracking can otherwise retain a single-threaded
`thread.o` alongside newly enabled thread headers.

ABI-sensitive target libraries use fresh build directories after a compiler
calling-convention or unwind change. Do not turn an old partial build into
success merely by relinking its stale objects. The source checks accept only
an exact prefix of the maintained patch series, then apply the remaining
patches; unexpected local modifications are preserved and rejected.

Windows-hosted GCC and binutils:

```bash
# This configure establishes any genuinely missing native dependencies.
bash bootstrap-cygwin.sh native-configure
# If native GMP/MPFR/MPC are missing, build the checksum-pinned inputs:
bash bootstrap-cygwin.sh native-deps
bash bootstrap-cygwin.sh native-binutils
bash bootstrap-cygwin.sh native-gcc
```

The native prefix is `native/`. Static GMP 6.2.1, MPFR 4.1.0, and MPC 1.2.1
come from the pinned GCC source's `contrib/prerequisites.sha512`, with actual
archive checks before extraction. GMP uses portable C rather than
ELF-specific assembly. Explicit GNU C17 avoids GCC 15's changed C23
empty-parameter-list semantics in old configure probes. `CC_FOR_BUILD`
remains the Linux compiler, while `CC`/`CXX` produce Windows code.

Keep GCC's default native C++ include layout (`native/include/c++/15.0.1`).
An explicit absolute `--with-gxx-include-dir` can be relocated after the C
header paths, breaking `<cstdlib>`'s `#include_next <stdlib.h>`. The native
recipe does not pass that override. If diagnosing an earlier misconfigured
build, inspect the strings in `cppdefault.o`: reconfiguring alone did not
rebuild that object. Preserve the stale object before rebuilding; do not add
application include-path overrides.

**ARM64 loader requirement:** native GCC must use `--enable-host-pie`.
GCC otherwise adds `-no-pie`, clearing `DYNAMIC_BASE`; Windows rejected the
resulting raw-ARM64 compiler with error 193. A one-bit diagnostic copy
isolated the cause, but that modified binary is not a deliverable. The
maintained build enables ASLR through configure. Microsoft documents that
[ASLR cannot be disabled on ARM64](https://learn.microsoft.com/en-us/cpp/build/reference/dynamicbase-use-address-space-layout-randomization).

Copy the completed native prefix into a new isolated Windows directory,
dereferencing its Unix symlinks (for example, `tar --dereference
--hard-dereference` in WSL followed by Windows `tar.exe` extraction).
Run `Test-NativeToolchain.ps1 -Prefix <Windows-directory> -OutputDirectory
<new-evidence-directory>`. It checks raw PE architecture/ASLR/imports, the
live compiler's `ProcessMachineTypeInfo`, C compile/assemble/resource/link/run,
Unicode `wmain` startup, and C++ varargs/thread/exception/filesystem behavior.
It also builds an ordinary C provider DLL and plain-extern consumer, requiring
read/write/address equality across a measured greater-than-4GB image/data gap.
Compiler-selected CRT and runtime archives are hashed before and after the
test, in addition to the executable tools.
The test changes PATH only in its own process and restores it afterward.
Built binaries or `--version` alone do not satisfy this gate.

## Windows instruction-cache runtime

`gcc-arm64-windows-cache.patch` fixes the libgcc implementation behind
`__builtin___clear_cache` for both `_WIN32` and `__CYGWIN__`. The recovered
implementation read `CTR_EL0` and issued `DC CVAU` / `IC IVAU` directly.
On this Windows machine, PCRE2 10.48 faulted with `0xC000001D` at
`__aarch64_sync_cache_range + 0x0c` (`d53b0023`, `mrs x3, ctr_el0`) inside
JIT compilation, before executing generated code.

The Windows branch uses `FlushInstructionCache(GetCurrentProcess(), ...)`.
The end address is exclusive, with a full pointer-width byte count. Empty
ranges are no-ops. Reversed ranges and API failure abort rather than returning
success from an operation whose builtin interface cannot report an error.
Non-Windows AArch64 retains its original implementation.

For an existing completed bootstrap, preserve the old installed prefixes:

```bash
JOBS=4 bash bootstrap-cygwin.sh cache-runtime
# Use the exact CACHE_EPOCH_READY directory printed by that invocation.
export CACHE_EPOCH='/root/arm64-vnext-20260905/toolchain/epochs/cache-<timestamp>-<pid>'
JOBS=1 bash bootstrap-cygwin.sh cache-cross-prefixes
JOBS=1 bash bootstrap-cygwin.sh cache-cross-probe
```

`cache-runtime` applies the checked patch series and incrementally rebuilds
both target libgcc archives. It preserves the old objects/archive,
configuration, build-compiler hashes, source delta, and patch identities in
the epoch. It does **not** install into either existing prefix.
`cache-cross-prefixes` creates complete, separate `cygwin-cross/` and
`mingw-cross/` prefixes under that epoch. It compares their contents with
the baselines and requires libgcc to be the sole differing file, then checks
the relocated compiler's default library, sysroot, and support-tool selection.
Existing output prefixes are never overwritten.

Use `cygwin-cross/bin/msys2-gcc` or `msys2-g++` from the new epoch for MSYS
applications, and `mingw-cross/bin/aarch64-w64-mingw32-gcc` for the Linux-hosted
Windows cross compiler. `cache-cross-probe` compiles against the new MSYS
prefix without a library override and retains linker maps, source files,
the full runtime DLL, and identities. It also requires the Linux cache
implementation to preprocess identically to the pinned original.

Create a new **Windows-hosted** epoch from the previously accepted native
prefix, not by copying Linux compiler executables:

```powershell
.\New-CacheToolchainEpoch.ps1 -Baseline 'C:\tools\native-baseline' `
    -CacheEpoch '\\wsl.localhost\Ubuntu\root\arm64-vnext-20260905\toolchain\epochs\cache-<timestamp>-<pid>' `
    -Prefix 'C:\tools\native-cache-fixed'
.\Test-WindowsClearCache.ps1 -Prefix 'C:\tools\native-baseline' `
    -OutputDirectory 'C:\evidence\cache-old' -ExpectLegacyFault
.\Test-WindowsClearCache.ps1 -Prefix 'C:\tools\native-cache-fixed' `
    -OutputDirectory 'C:\evidence\cache-fixed'
.\Test-NativeToolchain.ps1 -Prefix 'C:\tools\native-cache-fixed' `
    -OutputDirectory 'C:\evidence\native-cache-acceptance'
# Use the exact CACHE_CROSS_PROBE directory printed by the WSL stage.
.\Test-WindowsClearCache.ps1 -Prefix 'C:\tools\native-cache-fixed' `
    -CrossProbeDirectory '\\wsl.localhost\Ubuntu\root\arm64-vnext-20260905\toolchain\probes\cache-cross-<timestamp>-<pid>' `
    -OutputDirectory 'C:\evidence\msys-cache-fixed'
```

The Windows staging script hashes every baseline file before/after copying,
changes only the compiler-selected libgcc archive, and adds source/epoch
metadata under `share\toolchain-epochs\windows-cache`. The cache regression
checks raw ARM64 PE/ASLR/imports and actual native process architecture.
It repeatedly rewrites and executes a tiny ARM64 function straddling a page
boundary, using one RWX allocation and no intervening `VirtualProtect` that
could mask a missing cache flush. A separate test-only import-cell fixture
checks empty ranges, a 4,294,967,301-byte range, API failure, and reversed
ranges; those fake imports are not present in the real execution probe.
Archive relocations bind the helper to the Windows API, since linked ADRP
disassembly can label an entire IAT page rather than the particular import.

The first fixed epoch passed all 512 rewrite/execute iterations and error
controls for MinGW and MSYS, plus the full native compiler acceptance.
All 55 native host executables had symbols and contained neither cache
helper, so replacing the target archive did not leave a stale helper embedded
in those tools. The dependency lane's clean PCRE2 rebuild subsequently
passed literal interpreter/JIT comparisons for 8/16/32-bit widths and all
four upstream CTest entries, including its JIT suite. Old failed PCRE2 DLLs
remain negative evidence. Because those upstream CLI tools statically link
PCRE2, shared-library acceptance separately exercised 18 public-API cases
against the exact installed 8/16/32-bit DLL paths in a native ARM64 process.
**Existing applications/DLLs that statically
linked the old helper must be rebuilt/relinked**; replacing libgcc on disk
does not fix their embedded code. Do not disable JIT, override SLJIT's
builtin selection, or rebind old application evidence to the new archive.

## Native MSYS-target compiler and consumer boundaries

The Windows-hosted **MinGW/UCRT-target** compiler above cannot build native
MSYS Perl/XS as if it targeted the POSIX runtime. `native-msys-stages.sh`
implements a separate Canadian build: Linux ARM64 build host, Windows ARM64
UCRT compiler executables, and `aarch64-pc-cygwin` with an MSYS application
profile as the output target. Its target data model is LP64, not MinGW LLP64.

```bash
export ACCEPTED_CACHE_EPOCH='/root/arm64-vnext-20260905/toolchain/epochs/cache-<timestamp>-<pid>'
export NATIVE_MSYS_EPOCH='/root/arm64-vnext-20260905/toolchain/epochs/native-msys-<identity>'
JOBS=3 bash bootstrap-cygwin.sh native-msys-configure
JOBS=3 bash bootstrap-cygwin.sh native-msys-gcc
JOBS=3 bash bootstrap-cygwin.sh native-msys-posix-cross
JOBS=3 bash bootstrap-cygwin.sh native-msys-runtime
JOBS=3 bash bootstrap-cygwin.sh native-msys-libstdcxx
JOBS=3 bash bootstrap-cygwin.sh native-msys-binutils
JOBS=3 bash bootstrap-cygwin.sh native-msys-finalize
```

Coordinate `JOBS` before running these commands. The old Cygwin bootstrap
reported `Thread model: single`. Both libgcc and libstdc++ actually query that
compiler metadata; passing `--enable-threads` to libstdc++ did not change it.
The separate `native-msys-posix-cross` helper is genuinely configured for POSIX
threads. Its target libgcc must select `gthr-posix.h`, and hosted libstdc++
must detect `_GLIBCXX_HAS_GTHREADS`; failed single-thread attempts are retained.
The target libraries use the native compiler's default C++ include layout.

`RUNTIME_SYSROOT` and `RUNTIME_DLL` can select an explicitly accepted runtime
pair. Defaults use the frozen cache epoch. Preparation records all input
headers/libraries and the DLL hash, rejects a changed receipt on resumption,
and copies only target `include`/`lib`, never the cross sysroot's Linux `bin`.
Native aliases and licenses are staged without modifying older prefixes.
After copying this tree to Windows with links dereferenced, derive default
specs from that actual Windows `gcc.exe`, then run:

```powershell
python .\generate-msys-specs.py --compiler "$prefix\bin\gcc.exe" `
    --output "$prefix\lib\gcc\aarch64-pc-cygwin\15.0.1\specs" `
    --manifest "$prefix\share\toolchain\msys-profile.json" --profile-mode default
.\Test-NativeToolchain.ps1 -Profile MSYS -Prefix $prefix -OutputDirectory $proof
.\Publish-NativeMsysToolchain.ps1 -Prefix $prefix -AcceptanceDirectory $proof `
    -OutputFile $manifest
```

This MSYS gate is independent of MinGW qualification. It requires actual
native C/assembly/link, `dlopen` of a C++ module with constructors, and hosted
C++ thread/TLS/exception/filesystem behavior. Compiler images must be ARM64
UCRT-hosted; resulting applications must import MSYS, not UCRT/Cygwin1.
The publisher writes `Status: qualified` only after this proof and publishes
a full relative file inventory, component identities, default-specs binding,
and runtime source pairing. A C-only bootstrap receipt is explicitly
`c-qualified`, not interchangeable with that full contract.

**Current runtime prerequisite:** the accepted ARM64 runtime suppresses the
public `_ctype_` DATA export although its headers and the GCC newlib ctype
backend require it. Its newlib alias code also selects the x86-32 spelling
for non-x86_64 targets. This is a runtime-owned ABI restoration, not permission
to edit another lane's source. It blocks full hosted C++ publication.
`__ctype_ptr__` is not an equivalent classic-table substitute: the runtime
changes it when the locale changes. Native C/pthread/TLS and simple C++ module
constructors have passed against the unchanged accepted runtime.

Additional consumer-driven repairs are maintained independently:

* `gcc-cygming-crt-host-types.patch` follows existing `crtstuff.c` practice:
  preserve tool-feature defines from `auto-host.h`, but undefine host typedef
  fallbacks before including target headers. A MinGW-host/Cygwin-target build
  otherwise replaced the target `caddr_t` typedef with `char *`.
* `binutils-arm64-runtime-exports.patch` applies Cygming startup/global
  auto-export exclusions to both ARM64 COFF formats and excludes the MSYS
  runtime archive. Bash previously re-exported `_msys_dll_entry`, so loadables
  imported Bash's startup instead of their own and never applied their own
  data pseudo-relocations. Live reference cells and the same print/mkdir
  callbacks established the failure and correction. Re-link Bash **and its
  import library**, then modules; filtering only module exports is not a fix.
  `test-runtime-exports.py` reads raw PE exports, retains a leaking baseline,
  and checks that explicit exports still work.
* `gcc-arm64-executable-suffix.patch` restores the standard Cygming
  `TARGET_EXECUTABLE_SUFFIX`. Without it, `-o conftest` created a bare PE while
  native GNU libtool expected `conftest.exe`. `binutils-windres-windows-quotes.patch`
  protects a quoted preprocessor path from `cmd.exe /c` outer-quote removal
  when GNU libtool also supplies escaped quotes in resource definitions.

For existing native builds, `native-drivers` builds only the affected driver
targets through the top-level Canadian environment, and `native-windres`
builds an uninstalled resource-compiler candidate. `Stage-NativeDriverEpoch.ps1`
copies a baseline to a new prefix, updates every matching driver alias, and
retains the baseline inventory rather than rebinding its old qualification.
`Test-NativeDriverBoundaries.ps1` exercises suffixless outputs including
`.libs/table-from`, explicit/compile-only filename preservation, actual native
C pthread/TLS behavior through both drivers, and default quoted resource
preprocessing with a native executable checking the string/integer payload.
`-ExpectLegacyFailures` proves the original naming and quoting defects.

## Provenance

The historical recipe was read from runtime preservation commit
`05a8c9c500cb0979b5826f112810fd28021b8841`, at
`arm64-vnext/c63ab774-session/evidence/toolchain-recipe/PROVENANCE.md`.
The relevant original steps are `from-fca94a35/binutils.sh`,
`from-1e64365a/gcc-cxx.sh`, and `from-1e64365a/s14-w32api-v12.sh`.
Historical destructive cleanups and machine-local `file://` clone URLs are
not replayed. Dependencies are fetched and checked out by complete commit ID,
not a moving branch or tag.

| Source | Exact recovery commit | Evidence |
|---|---|---|
| crutkas/gcc-woarm64 | `5688a17320e775944bbe795010ebe7e89fc7a628` | Preserved verified source identity |
| crutkas/binutils-woarm64 | `44335833f8f734f978211b082b15aed14efcf958` | Corroborated candidate, **not proof of the lost binary's exact source** |
| mingw-w64/mingw-w64 | `819a6ec2ea87c19814b287e21d65e0dc7f05abba` | Preserved v12.0.0 commit |
| Windows-on-ARM-Experiments/mingw-woarm64 | `70d63e7c9a477b8b275a9782b289fbf1614b6e9e` | Recovered native CRT source identity; separate from v12 w32api |

`w32api-arm64-cygwin.patch` enables the ARM64 `_WIN64` and pointer-width
header branches. Note that `basetsd.h` is in `mingw-w64-headers/include/`,
not the nonexistent `crt/` location used by one historical script.

`gcc-cygwin-crtbegin.patch` fixes an actual GCC 15 bootstrap error: the
Cygwin startup object called undeclared `__cxa_atexit` with a callback of
the wrong function type. The patch declares the ABI and adapts the
argument-taking destructor callback without suppressing compiler diagnostics.
An alternate Git index verifies the dependency checkout matches exactly the
pinned source plus the recorded patches, preserving unexpected changes on failure.

`gcc-mingw-driver.patch` repairs actual downstream failures rather than
rewriting applications: the ARM64 target includes the existing
architecture-independent `-municode` option, defines `UNICODE`, selects
`crt2u.o`, and enables the existing POSIX-thread default spec when configured
for POSIX threads. The native Unicode probe checks actual `wmain` arguments.

`gcc-native-includes.patch` retains the explicitly configured ARM64 system
header directory instead of silently replacing it with `/mingw/include`.

`gcc-ms-varargs.patch` supplies the actual Microsoft ARM64 pointer `va_list`,
GP-register argument convention (including named floating-point arguments),
large aggregate indirection, and register/stack splits. The historical
32-byte AAPCS64 list was self-consistent within GCC but incompatible with
UCRT. `gcc-ms-varargs-named-pair.patch` additionally accounts for the generic
pretend-argument area when a named aggregate straddles x7 and the stack.
Rebuild the CRT, libgcc, libstdc++, native compiler dependencies, and applications:
the old `printf` objects themselves contained the wrong ABI.

The maintained `test-ms-varargs.py` / `.ps1` harness checks actual C/C++
producer/consumer boundaries and raw UCRT output. The corrected GCC self
matrix passed 72/72 cases, and narrow/wide UCRT formatting passed 32/32.
Clang 18 reference cases remain separately classified: its own producer and
consumer disagree for natural 16-byte alignment and some split aggregates.
Those real failures are retained, not used to force GCC to reproduce one
inconsistent side. `-IncludeGroup gcc-self` or `stdio` explicitly selects a
targeted group; it is not a claim that omitted cross-compiler groups passed.
See `test-ms-varargs.txt` for the full interoperability limitations.

The GCC ARM64 SEH patches are maintained separately from argument ABI:

| Patch | Measured defect addressed |
|---|---|
| `gcc-arm64-seh-prologue.patch` | Missing instruction-count NOP records for stack probes and volatile homing |
| `gcc-arm64-seh-contiguous.patch` | Shrink-wrapped saves spread across basic blocks without representable region metadata |
| `gcc-arm64-seh-add-fp.patch` | Missing frame-pointer offset operation for `FP = SP + constant` |
| `gcc-arm64-seh-frames.patch` | Dynamic-SP recovery ordering and absent ordinary epilogue scopes |
| `gcc-arm64-seh-order-offsets.patch` | Scheduler movement of FP setup and missing paired-load offsets inside UNSPEC |
| `gcc-arm64-seh-frameless.patch` | Redundant unwind scopes for hundreds of frameless switch returns |

Unknown frame effects fail compilation instead of being silently encoded as
NOPs. `test-compiler-prologue.py` checks real instruction coverage and
FP-after-saves ordering in ordinary, variadic, conditional, and large dynamic
frames. Separate native runtime fixtures verify `RtlVirtualUnwind` at actual
instruction boundaries, including a changed dynamic SP and the final return.

`binutils-arm64-epilogue.patch` fixes ARM64 unwind serialization: compact
E=1 headers need an epilogue byte index, not a count; larger indices and
nonterminal epilogues retain explicit scopes; scope instruction offsets must
be divided by four exactly once. `test-gas-unwind.py` checks four raw-COFF
cases independently of the faulty objdump decoder. The original assembler
fails all four; corrected Linux and Windows assemblers produce identical
passing objects. A separate frozen runtime probe passed 31 actual native
`RtlVirtualUnwind` cases, including both original x19 epilogue failures.

`binutils-arm64-add-fp.patch` encodes the directive's byte offset in units of
eight and rejects misaligned/out-of-range inputs. The unwind-storage and
unwind-sharing patches replace a corrupting fixed 32-scope array with checked
storage and share identical/suffix epilogue sequences in the Windows format.
Without sharing, real functions in the native binutils build exceeded the
1020-byte encoded unwind limit. The capacity regression covers 600 shared
epilogues plus oversized, unmatched, and nested failures; an assembler crash
does not count as a valid rejection. Raw encoding tests also run using the
actual Windows-native assembler.

`binutils-pe-runtime-reference.patch` queues the existing pseudo-relocation
compatibility symbol before archive scanning. Creating that reference only
after auto-import processing was too late to extract the existing runtime
archive member, breaking ordinary Bash loadable-module links. The fix adds
no runtime stub and does not require an application `-u` workaround. `ld`
builds a non-installed candidate; `ld-install` updates both compiler-visible
linker paths only after coordinated acceptance.

`binutils-arm64-weak-relocs.patch` treats auto-import's `defweak` symbols as
defined when applying ARM64 instruction relocations. The previous generic
fallback produced incorrect ADRP/low12 immediates. Correcting those immediates
alone cannot make a remote DLL address fit ADRP's signed page-relative range.

`gcc-arm64-pe-extern-data.patch` addresses that architectural limit using
the existing PE `.refptr` machinery for ordinary non-TLS extern data, not
just weak symbols. It normalizes symbol-plus-offset policy checks and aligns
full-width reference cells to eight bytes. Text addresses a local cell;
the cell can carry a 64-bit imported address regardless of the DLL's distance.
Application declarations, ASLR, and image bases are unchanged. Recompile
affected objects: relinking old direct-ADRP code does not change its reach.
`test-pe-extern-data.py` checks actual COFF cells for read/write/address/array
offset paths and preserves function/local-data controls. Native far-ASLR
read/write/address-identity tests are a separate acceptance requirement.

`gcc-arm64-pe-reload.patch` makes that existing PE expansion safe during
register reload. A real libstdc++ `cow-fs_path` compilation exposed a new
`force_reg` pseudo created while LRA was assigning registers. Loading the
reference cell into the destination and applying the constant offset afterward
preserves the same pointer-cell ABI without that hidden temporary. The exact
saved preprocessed translation unit and the full clean target library build
must both compile; disabling compiler checking or reducing optimization is
not an acceptable substitute.

For an existing build, `gas` builds/tests an isolated Cygwin assembler
candidate. After native acceptance, `gas-install` updates and compares both
compiler-visible assembler paths. `mingw-gas` and `native-gas` propagate the
same fix. Reassemble affected runtime objects; relinking old objects retains
their old unwind metadata.

The GCC configuration intentionally builds drivers/cc1/cc1plus without libc.
The runtime build needs C++, even before libstdc++ is available. The later
`libgcc` stage is explicit and must not be mistaken for a complete C++ runtime.
Fresh runtime binaries will include recovered signal fixes and therefore are
not expected to match old DLL hashes.
