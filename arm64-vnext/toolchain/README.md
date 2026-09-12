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
source blobs, ordered GCC/binutils/MinGW CRT patches with SHA256, the separate w32api
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

Later libxcrypt preparation failed on the actual missing
`LT_SYS_SYMBOL_USCORE` macro. Installing `libltdl-dev` and its required
`libltdl7` dependency supplied the genuine `/usr/share/aclocal/ltdl.m4`
definition; a no-op macro or `m4_pattern_allow` is not a replacement.

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
upstream ARM64 flags, then builds import libraries for the thirteen named
runtime dependencies. These are not fabricated export definitions, but they
are also not the entire Windows SDK import-library set.
`userenv` is included for the maintained `winsup/utils/cygpath` target, which
links `netapi32`, `userenv`, and `ntdll` and calls `GetProfilesDirectoryW`.
It uses the pinned official `mingw-w64-crt/lib-common/userenv.def`; no host
package or MinGW CRT substitution is needed. Existing frozen SDKs are not
updated by this recipe change. A consumer using a previously built ARM64
Userenv import archive must bind that individual archive and verify its actual
link/import/native execution in a new private cohort.

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

### MinGW CRT complex exponential

`mingw-woarm64-crt-cexp-no-builtin-sincos.patch` repairs the CRT source behind
a real native Tk/wish stack overflow. GCC lowered the `sincos` calls inside
the CRT's own `cexp` implementation back into `cexp`, producing branch
relocations to the function itself. This is distinct from the ARM64 SEH/FP
unwind defects. The exact pinned MinGW CRT source is
`70d63e7c9a477b8b275a9782b289fbf1614b6e9e`; the fix is not a w32api change.

The `cexp.def.h` template now calls the appropriate `sincos` family member
through a volatile function pointer, preserving `-O2` and the existing
numeric branches for `cexp`, `cexpf`, and `cexpl`. No application compiler flags,
renamed binaries, or Tcl/Tk source changes are required. Recovery retained the
old self-relocations, the isolated builtin-lowering discriminator, and new
objects with real `sincos`/`sincosf`/`sincosl` references and native finite-value
family probes. The resulting archive is a separate binary successor; these
producer probes do not by themselves claim full Tk/GitGUI acceptance.

The exact patch SHA256 is
`ee31170ddd4e34c4f84e7d34822ea253e07715101be95eb16a54446d19d0ad28`.
That integration's canonical source lock was
`2709918ed8692e8e379d0dbf72dbbf997e72b47681abd608d8fbd470f9c82f9f`
(19 GCC, 9 binutils, 1 MinGW CRT, and 1 w32api patches). Both the lock query
and the actual bootstrap `check_source` now support `mingw-woarm64`, so the
existing `mingw-crt` stage applies the locked patch before configuring/building
instead of merely listing it as provenance.

`test-crt-source-guard.py --source <pinned-mingw-woarm64-checkout> --output
<new-evidence-directory>` runs under Linux/WSL with the existing Python/Git/Bash
tools. It exercises the real bootstrap guard in a private checkout: pristine
application, accepted resume, tracked-drift rejection, and untracked-drift
rejection, preserving unexpected changes and the real Git index. It never
builds the CRT or modifies the original dependency. Existing installed
`libmingwex.a` archives and applications that linked the old members remain
unchanged; rebuild the affected CRT members/archive and relink consumers into
a new cohort before claiming the repair.

### MinGW fast-fail header in strict C89

The same pinned MinGW source defines ARM64 `__MINGW_FASTFAIL_INLINE` as
`static inline` in `mingw-w64-headers/crt/_mingw.h.in`. Consequently, even
`#include <stdio.h>` fails under `-std=c89 -Werror`, while the unchanged source
passes under C99. This blocked GNU libtool's native test 90; it is not a reason
to change that consumer's language flags.

`mingw-woarm64-fastfail-c89-inline.patch` changes only the keyword spelling to
`static __inline__`, matching the header's other GCC inline definitions.
Static linkage, the noreturn declaration, w0 argument and `brk #0xf003` are
unchanged. The patch follows the CRT repair in the MinGW source series; both
`mingw-headers` and `mingw-crt` invoke the same source guard. The new canonical
source lock is
`08f351813a24a85bb239ab159fc04e943f14ee985fe8b96b0869575213652303`
(19 GCC, 9 binutils, 2 MinGW, and 1 w32api patches).

`Stage-MinGWHeaderDelta.ps1` verifies a complete native MinGW baseline inventory,
the exact pinned template and patch before making a separate header-only
candidate. It never updates the old prefix. `test-mingw-fastfail-header.py`
repeats the unchanged failing C89/C99 input, checks ten C/C++ modes, links
multiple translation units, compares C99 fast-fail assembly at O0/O2 with only
the relocated header-path annotation normalized, and runs native ARM64 C89
and C++98 executables. `test-crt-source-guard.py` also checks that the actual
bootstrap applies this header patch and rejects later header drift.

The header delta retains its baseline compiler/CRT/assembler/library history.
It does not apply newer CRT or FP fixes to those binaries and does not inherit
full new compiler qualification or admit the libtool package. Consumers need
a fresh build against the successor; independent native-ar long-path failures
remain a separate boundary.

### MinGW InterlockedExchange ordering

The pinned native MinGW headers used `__sync_lock_test_and_set` in the
32-bit, 64-bit and pointer exchange fallbacks. On this ARM64 GCC/libgcc pair,
the resulting `_sync` swap helpers are acquire-only. The corrected
`__atomic_exchange_n(..., __ATOMIC_SEQ_CST)` emits `_acq_rel` helpers; the
spelling `_sync` must not be mistaken for a full ordering guarantee.

The ordering patch follows the CRT and C89 header patches in the
`mingw-woarm64` source series at `70d63e7c9a477b8b275a9782b289fbf1614b6e9e`.
It does not belong to the separate v12 Cygwin w32api overlay. The source
lock binds the producer's exact CRLF patch (`6468dc12...`), its LF-only
portable form, and the intrinsic header's before/after SHA-256 identities.
`mingw-stages.sh` checks the patched source identity before any header/CRT
stage. The actual bootstrap source guard accepts a pristine or known-prefix
patch series, resumes idempotently, and rejects unknown source drift.

`stage-mingw-interlocked-headers.py` exports the pinned sources and applies
the complete ordered series without a build. It copies an explicitly
inventoried native MinGW include directory into a new private cohort, changing
only `psdk_inc/intrin-impl.h`. Run it with the source-owning Git (WSL Git for
the ext4 dependency); no global trust-setting change is needed.
`test-mingw-interlocked-applier.py` exercises the frozen producer applier on
private copies. `test-mingw-interlocked-cohort.py` runs the producer's
baseline-negative/patched-positive codegen control and native 32-bit,
64-bit and pointer exchange return/store checks, with one compiler at a time.

Consumers must explicitly select the new include root and rebuild into a new
package identity. The header-only receipt does not replace a qualified
compiler prefix or relabel earlier binaries as rebuilt. In particular,
OpenSSL's previously qualified local `MemoryBarrier` remains untouched.

### Separate v12 Cygwin w32api ordering

The Cygwin/MSYS public `InterlockedExchange`, `InterlockedExchange64`, and
`InterlockedExchangePointer` macros also reached acquire-only fallbacks in
v12 `819a6ec2ea87c19814b287e21d65e0dc7f05abba`. This is a distinct header from
the native MinGW `70d63` tree. `w32api-arm64-interlocked-exchange-ordering.patch`
is derived against the exact v12 blob and follows the existing
`w32api-arm64-cygwin.patch` in `overlay_patches`. It changes only the ARM64
branches; the x64 branch retains its original implementation.

`prepare-w32api-overlay.py` exports the pinned source, applies the ordered
overlay, and records every resulting file. Its identity names the new
bootstrap overlay directory. Repeated preparation accepts only matching
receipts and bytes; partial exports, tracked drift, and extra files fail
without overwriting anything. The actual `w32api` bootstrap stage uses this
helper rather than the old single-patch marker.

`stage-cygwin-interlocked-headers.py` binds the active SDK's full inventory,
matches the old intrinsic to the pristine v12 blob, and matches `_cygwin.h`
and `basetsd.h` to the existing ABI overlay. It creates a new flat w32api
header cohort with exactly one changed file, never modifying the active SDK.
`test-cygwin-interlocked-cohort.py` uses the parent's unmodified ordinary
`windows.h` source, rejects baseline `_sync` helpers, requires all three public
APIs to select `_acq_rel`, and runs native LP64 return/store probes. A
preprocessing-only x64 branch control requires identical tokens; it is not
advertised as native x64 code-generation or execution evidence.

For the measured root06 driver, select this temporary header-only cohort
with `-isysroot COHORT` (where `COHORT/include` contains the copied w32api
headers). The driver's existing Cygwin/newlib C headers remain before it,
and its old `-idirafter` w32api comes after it. A bare `-I COHORT/include`
instead shadows Cygwin headers with MinGW CRT headers and is not the
qualified command. Future complete SDK exports install the patched w32api
in their normal target include location. Both paths require new explicit
consumer/package identities; no old root06, `907afa` runtime, Perl, or sealed
native-MinGW package is retrospectively relabeled.

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

### Shared MSYS GCC runtime provider

The original SDK contains static target archives, not a `gcc-libs` package.
The genuine MSYS2 `gcc/PKGBUILD` at
`dbd17835da05daa9e70a0e16d01e97892928a157` defines the package ownership rules;
its GCC 15.3.0 version does not change this project's pinned GCC 15.0.1 source.
A provider built from this pin must use a truthful `15.0.1` package version.

`prepare-msys-shared-runtime-sources.py` exports the pinned GCC object and
applies the maintained patch series in a new source tree. It applies the
upstream MSYS DLL-prefix policy to target-library configure scripts and
libgcc's link rule, recording all before/after source hashes. In particular,
the SEH runtime is named `msys-gcc_s-seh-1.dll` at link time; renaming a DLL
after linking would leave incorrect import descriptors.

`prepare-msys-shared-runtime-inputs.py` verifies a full native compiler-copy
inventory and native build-bootstrap inventory, clones them privately, and
binds the complete qualified d70 runtime/import/CRT trio from the execvp
handoff. A copied DLL alone is not a coherent SDK change. The source export
is prepared on WSL ext4; native compilation uses a short Windows build root
because the current UCRT-hosted compiler opens Windows files directly.
Relative `--srcdir` paths keep generated C includes usable by that compiler.
No existing source checkout, compiler prefix or consumer tree is changed.

The standalone libstdc++ stage uses `CXX="g++.exe -nostdinc++"`, matching the
top-level GCC raw-target-compiler boundary. Otherwise an installed SDK's
`math.h`/`complex.h` C++ compatibility wrappers can shadow the actual C headers
and produce false negative configure results (`modf(0, 0)` overload ambiguity
and missing C complex declarations). Its separate `libstdc++-v3-raw-cxx` build
and `dev-raw-cxx` install preserve the earlier configuration evidence. Activate
the resulting configured C++ headers together with its DLL/import archive.

`build-msys-shared-runtimes.sh` exposes focused configure/build/install stages
for libgcc, libstdc++, libgomp, libatomic and target-applicable libquadmath.
`run-msys-library-stage.py` executes one stage with the private native MSYS
shell, explicit one/two-job limit, bounded kill-on-close process tree, raw
logs, and process-local noninteractive error policy. The shell's own runtime
directory precedes the compiler directory on its private PATH: identical
MSYS DLL bytes loaded from different roots are not interchangeable parent/
child private-protocol identities.

The driver initially has a static-only `*libgcc` spec. After real shared
libgcc builds, `activate-msys-shared-libgcc.py` installs its actual import
library and static companions only into the owned build SDK, then enables
normal shared selection while preserving explicit `-static`/`-static-libgcc`.
`activate-msys-runtime-library.py` adds other actually installed DLL/import
libraries. These development artifacts are distinct from the `gcc-libs`
runtime payload; they are not application aliases or empty providers.
Explicit libstdc++ successor activation retains predecessor bytes and receipts;
it never rewrites a frozen input SDK.

`test-shared-msys-runtimes.py` uses normal native links and checks raw AA64
PE/imports, shared C++ exceptions across a DLL boundary, threads/TLS,
filesystem I/O, C/C++ locale behavior, 128-bit arithmetic/atomics and OpenMP.
It observes actual loaded DLL paths/hashes without a debugger. The pinned
generic libstdc++ locale backend supports the C locale; named non-C C++ facets
remain unsupported, even though the MSYS C runtime supports `C.UTF-8`.
These ordinary tests do not establish debugger C++ exception parity.

`libgcc-arm64-unwind-context.patch` fixes the separately reproduced ARM64 SEH
dispatcher-context alias: `RtlUnwindEx` writes its context argument, which can
be the saved dispatcher frame still needed by phase two. The handler makes a
private `CONTEXT` copy on ARM64 before either existing unwind call; x64 code is
unchanged. The patch is locked by SHA256 and does not change compiler frontends,
runtime headers or the MSYS DLL. A private source-object experiment is not
qualification of a newly produced static archive/shared DLL: preserve the
predecessor, rebuild the affected members and link outputs in a new epoch,
then requalify ordinary/debugger behavior against those actual outputs.

`build-msys-runtime-docs.sh` can generate the upstream info manuals and genuine
German/French libstdc++ catalogs using existing ARM64 Linux host tools when the
native bootstrap lacks makeinfo/msgfmt. Record that host-only documentation
step separately. Catalog presence does not enable NLS or named locale facets
in a libstdc++ configured without those features.

`stage-msys-gcc-libs.py` splits installed runtime DLLs, available locale/info
files, and licenses into a new immutable stage for the provider packager.
The source's `libvtv/configure.tgt` does not support ARM64 Cygwin; never invent
its payload. Any other unsupported component needs source/configure evidence.
The runtime stage is not admitted until native shared-runtime qualification
and the packaging owner's archive/readback gates are both complete.

### Runtime signal generation and fault recovery

`generate-runtime-signals.py` runs `gendef` in a new directory, preserves an
explicit hash-bound TLS-offset file, and rejects empty assembly or missing
export trampolines even when Perl returned zero. The pre-port x86-only
generator exhibits exactly that silent ARM64 failure. Reuse the complete
recovered ARM64 port, including its signal-frame restore helper and matching
TLS/jump-buffer headers; do not substitute a generator alone into an unrelated
runtime snapshot. `assemble-runtime-signals.py` checks the resulting object
with the native ARM64 assembler and requires the actual exported providers.
Neither recipe invokes `make` in a preserved runtime tree.

`runtime-arm64-myfault-context.patch` handles two ARM64 SEH requirements in
`exception::myfault`: unwind-phase callbacks must continue the unwind rather
than start another one, and `RtlUnwindEx` needs a private `CONTEXT` instead of
overwriting the saved dispatcher context. The x64 handler remains unchanged.
`replay-runtime-myfault.py` copies the recorded source/build/toolchain inputs,
rebases the exact compile and link commands, and rebuilds only `exceptions.o`.
It checks that every other runtime archive member and the TLS offsets remain
unchanged. `--control` reproduces the unmodified DLL without applying the fix.

`test-runtime-signals.py` checks 16 asynchronous deliveries across integer,
vector and floating-point control state, eight protected-page-to-`EFAULT`
recoveries, and explicitly selected existing jump/signal regressions.
`capture-runtime-myfault.py` uses the preserved zero-write debugger and native
job observer for matched ordinary/debug/no-context captures; a successful
collector launch alone does not qualify the target. These are scoped runtime
proofs, not full-distribution admission.

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

**Runtime pairing:** the historical ARM64 runtime suppressed the public
`_ctype_` DATA export although its headers and the GCC newlib ctype backend
require it. Its newlib alias code also selected the x86-32 spelling for
non-x86_64 targets. The runtime owner's `ctype-20260907` cohort restores the
real `_ctype_b + 127` alias and DATA import and retains the ARM64 uname fix.
`__ctype_ptr__` is not an equivalent classic-table substitute: the runtime
changes it when the locale changes. The newly paired SDK has passed the full
native C/C++/DLL/thread/TLS/exception/filesystem gate and the strict downstream
SDK reader without relaxing either gate.
Keep independently produced consumer reports alongside the aggregate SDK
handoff, with their own hashes and stated scope; PE/process reports alone do
not replace the functional result. Add a versioned supplemental handoff rather
than rewriting the published SDK inventory or prior receipts. Later MinGW/Tcl
producer repairs remain separate cohorts and do not reopen this restored
MSYS C++ runtime ABI.

`Stage-NativeMsysRuntime.ps1` copies an existing genuine hosted SDK to a new
prefix and overlays only the qualified runtime's C headers, startup/import
libraries, and DLL. It verifies the runtime owner's receipt hash and exact
paired inputs, keeps the original compiler/libgcc/hosted C++ files unchanged,
and regenerates the relocated profile metadata. First materialize the runtime
inputs with `tar --dereference --hard-dereference`: Windows cannot reliably
follow the Unix `libg.a` symlink through the WSL UNC share. Retain that export
in owned evidence storage; never overwrite the source runtime or prior SDK.
The receipt preserves the original Linux source paths even when copying from
the materialized Windows files. Publish only after a new full native proof:

```powershell
.\Stage-NativeMsysRuntime.ps1 -Baseline $oldHostedSdk `
    -RuntimeSysroot $materializedSysroot -RuntimeDll $materializedDll `
    -RuntimeReceipt $qualifiedRuntimeReceipt -RuntimeReceiptSHA256 $receiptHash `
    -Prefix $newHostedSdk -StageReceipt $newStageReceipt
.\Test-NativeToolchain.ps1 -Profile MSYS -Prefix $newHostedSdk `
    -OutputDirectory $newProof
.\Publish-NativeMsysToolchain.ps1 -Prefix $newHostedSdk `
    -AcceptanceDirectory $newProof -OutputFile $newManifest
```

`test-msys-ctype.py` distinguishes this ABI failure from an incomplete cross
sysroot. It uses the existing native MSYS C++ driver and actual hosted
headers/libstdc++/libsupc++, compiles `probes/msys-ctype.cc` to ARM64 COFF,
then links it without extra library paths or application definitions.
`--expect-missing-import` requires the original missing `_ctype_` DLL export,
missing `__imp__ctype_` import, and corresponding link failure. Without that
option, the same consumer must link and execute natively, match
`classic_table()` to `_ctype_ + 1`, check all 256 character classifications,
and produce the expected iostream output. Input hashes and raw command output
are retained and the input prefix is never modified:

```powershell
python -B .\test-msys-ctype.py --prefix $oldNativeMsysPrefix `
    --output $newNegativeEvidence --expect-missing-import
python -B .\test-msys-ctype.py --prefix $newPairedNativeMsysPrefix `
    --output $newPositiveEvidence
```

The ncurses 6.6 failure using the separate `uname-20260907` Linux cross prefix
instead reported that `<iostream>` itself was absent. Restoring the runtime
DATA export alone does not turn that freestanding sysroot into a hosted SDK.
`stage-hosted-msys-cross.sh` supplies the genuine headers/libstdc++/libsupc++
and POSIX libgcc from a fully qualified native SDK, verifies its full inventory,
and combines them with the existing Linux POSIX compiler helper:

```bash
bash stage-hosted-msys-cross.sh "$runtime_prefix" "$posix_helper" \
  "$windows_sdk_as_wsl_path" "$new_cross_prefix" "$native_manifest_as_wsl_path"
export PATH="$new_cross_prefix/bin:$PATH"
export CC="$new_cross_prefix/bin/msys2-gcc"
export CXX="$new_cross_prefix/bin/msys2-g++"
```

The development payload includes GCC's target `gcov.h` and `unwind.h` as well
as the target sysroot and hosted C++ headers. A helper built with `all-gcc`
alone need not already contain those runtime-installed headers. Compare the
complete target-header/library inventory with the qualified native SDK before
sealing the cross sibling, not just the files used by a single application.

The preserved helper's configured absolute assembler/linker paths can bypass
`-B`; the recipe detects this and rebuilds only the Linux driver/collect2
closure in a fresh build directory, not cc1/cc1plus. It verifies the original
source tree against the SDK's exact source lock using a private index, retains
the frontend's configuration origin for GCC's normal include relocation, and
selects the new paired tools/sysroot. There are no application `-I` fixes or
fake headers. Actual library/tool selections and a linked ctype consumer are
retained under `identities/`; execute that consumer with the paired DLL on
Windows before handoff. The completed cross SDK has also produced a native
passing thread/TLS/exception/filesystem consumer.

### CMocka emutls and returns-twice producer repair

An actual native MSYS CMocka 1.1.8 build exposed two compiler boundaries.
Its `vprint_message` stack-clash prologue allocated 4112 bytes through x13;
the old frontend did not contain the already maintained arbitrary-GP
`gcc-arm64-seh-stackalloc-reg.patch`. Separately, `tree-emutls.cc` inserted
TLS address materialization before a returns-twice `setjmp` call in a block
with abnormal predecessors, violating GCC's control-flow invariant.

`gcc-emutls-returns-twice-safe-insert.patch`, SHA256
`2e8af2b425d9716fec157377a0945bed506a98bdd141c78ae704f9741f845c49`,
is appended after the existing GCC series. Following GCC's bitint handling,
it moves the generated statements onto the normal incoming edge, repairs
call-used SSA operands with PHIs and abnormal-edge default definitions, and
refreshes the statement and call-graph edge count. Moving the statements alone
left SSA dominance invalid; omitting the edge-count refresh caused another
verifier failure. Those intermediate producer attempts remain unqualified.

Recovery's private native C frontend compiled and assembled the exact frozen
`cmocka.i` with the original `-O3 -DNDEBUG -std=gnu99 -fno-common
-fstack-protector-strong -fstack-clash-protection` and warning flags. No
CMocka source or optimization workaround is involved. This is a C producer
frontier, not full CMocka execution, C++ frontend, complete SDK or Git admission.
The existing runtime, assembler, target libraries and cc1plus retain their
earlier lineage; adding this source patch does not mutate an installed SDK.

The merged recipe retains the MinGW C89 header repair and switches the direct-SP
patch to the portable artifact described below. Its canonical source lock is
`74373d5062b4108c90a8a47d3a7083430319d84649e4be9fdff28d50a49b5af1`
(20 GCC, 9 binutils, 2 MinGW and 1 w32api patches), distinct from the producer's
`34b0def7a7f74521944a40b152e193f1aa46a4588a5408f21878aab503918225`
lock. Do not relabel the producer's binary receipt with this merged recipe.

`test-gcc-source-guard.py --source <pinned-GCC-checkout> --output
<new-evidence-directory>` exercises the actual bootstrap guard under Linux/WSL
in its own checkout: full pristine application, accepted resume, the exact
19-patch predecessor, and tracked/untracked drift rejection. It also verifies
that the portable direct-SP patch and a separately normalized copy of the
retained legacy artifact produce identical complete GCC trees. The optional
`--producer-direct-sp <frozen-producer-patch>` checks the producer artifact too.
The original dependency and real Git index remain unchanged; this source-only
control does not rebuild or qualify any compiler binary.

### Additive Windows system import archives

The native MSYS FIDO2 link exposed four absent SDK imports: `wsock32`,
`bcrypt`, `setupapi` and `hid`. Its C sources, Windows HID/Hello backends and
resource object compiled normally; `ws2_32` already resolved. The maintained
`w32api-libs` stage now includes these four libraries. This is a Windows API
import dependency, not a reason to substitute MinGW CRT libraries, disable
FIDO features or rebuild the compiler.

For a frozen SDK, use `build-msys-windows-imports.py` to create a separate
import-only overlay. `windows-system-imports.json` binds the four complete
official `lib-common/*.def` blobs at w32api revision
`819a6ec2ea87c19814b287e21d65e0dc7f05abba`; its revision must also match the
source lock. Export those paths and `COPYING` from the pinned Git object,
never from an unverified branch tip. The native SDK's own `dlltool` and
corrected ARM64 assembler generate each archive twice with deterministic
metadata and stable temporary names.

```powershell
python -B .\build-msys-windows-imports.py `
    --compiler-receipt $frozenCompilerCopyReceipt --receipt-sha256 $compilerReceiptSHA `
    --source-root $pinnedDefinitionExport `
    --process-runner $boundedProcessRunner --process-runner-sha256 $runnerSHA `
    --output $newOverlayEvidence
python -B .\test-windows-imports.py --overlay $newOverlayEvidence
```

The output `payload\aarch64-pc-cygwin\lib` contains exactly four `.a` files,
with no compiler, headers, CRT, runtime or target-library replacements.
The receipt checks all baseline SDK files before and after, every ordinary
COFF member's raw AA64 machine and import-only sections, the actual DLL
descriptor, and every `__imp_` symbol from the definitions. A normal LP64
MSYS link forces references to all four libraries and inspects raw PE
imports; neither that executable nor its Windows APIs are invoked.

`test-fido-windows-import-link.py` can replay the preserved FIDO DLL link,
changing only the explicit `-L` overlay and the two output paths. It hashes
the frozen objects, SDK and dependencies before and after and never runs
FIDO or modifies its failed build tree. MSYS FIDO uses `arc4random_buf`, so
its unchanged DLL need not import BCrypt despite the common link list's
`-lbcrypt`; the independent all-four-library probe covers that archive.

Consume the overlay only after hash verification, through an explicit
library search path in a new invocation. Keep the compiler-copy, dependency,
source and overlay receipts distinct. Status
`qualified-msys-windows-import-overlay-link-only` is **not** full SDK, C++,
FIDO execution, device/authentication, installation or package admission.

### Salted stack-protector addresses on ARM64 PE

Native execution exposed a path not covered by ordinary extern-data lowering:
CMocka and FIDO objects had direct `PAGEBASE_REL21`/`PAGEOFFSET_12L` references
to imported `__stack_chk_guard`. Binutils consequently emitted version-2
pseudo-relocations with bit sizes 21 and 12. The sampled libcbor test and DLL
had empty tables; their CMocka dependency contained the failing records.
There is no admitted runtime that makes arbitrary distant DLL data reachable
through a 21-bit page-relative instruction.

`aarch64_stack_protect_canary_mem` wraps the guard address in
`CONST(UNSPEC_SALT_ADDR)`, distinguishing the canary SET and TEST calculations.
The PE import path in `aarch64_expand_mov_immediate` previously removed an
offset but not that wrapper. The import helper rejected it, whereas the later
symbol classifier removed the salt and selected a direct ADRP/low12 sequence.

`gcc-arm64-pe-salted-guard.patch` unwraps the symbol for PE import lookup, then
reapplies the original salt to the image-local import-cell address. The
existing reload-safe destination-register load remains intact. Do not remove
the salt: its SET/TEST separation prevents reusing a spilled SET address as
the address of the expected canary during TEST. The canary load/check patterns,
stack-protector flags, ASLR, target macros and runtime are unchanged.

`bootstrap-msys-guard-cc1.sh NEW_ROOT JOBS` creates a private source/build
epoch, verifies and copies the previous C-frontend build artifacts, preserves
relocated configure caches as evidence, reconfigures, and builds only
`all-gcc TARGET-gcc=cc1.exe`. It does not install any compiler. `JOBS` is bounded
to the explicitly coordinated one or two slots; `--resume` is limited to that
existing private epoch. The seed build and original source remain unchanged.

`test-native-stack-guard.py` stages a new prefix from a hash-bound compiler-copy
receipt and replaces only `cc1.exe`. It repeats the original protected FIDO
and CMocka compile commands, checks raw object reference-cell relocations,
examines the linked pseudo-relocation table and distinct SET/TEST RTL salts,
and exercises an ordinary native MSYS canary across a greater-than-4GB data
gap, including deliberate own-process guard corruption. Its evidence binds
the raw PE/COFF inspector and bounded runner; a source-only or link-only
result must not be mistaken for native execution acceptance.

The new C-only receipt must name its actual immediate base, not an older
ancestor that happens to satisfy a consumer reader. A chain such as
`bd5 -> f54 -> salted-guard C delta` retains the original runtime, C++ frontend,
headers and target libraries and their earlier limitations. All affected
protected objects require recompilation; relinking old ADRP instructions
alone is not the repair. Full CMocka/FIDO suites and package admission remain
separate downstream gates.

An actual follow-up C++ prerequisite used the same protected guard fixture
with `g++ -x c++ -O2 -g -Werror -fstack-protector-strong`. The retained old
`cc1plus` still produced four 21-bit and four 12-bit guard entries alongside
one ordinary 64-bit entry. This is why the C-only successor must not claim
the C++ frontend was repaired.

`bootstrap-msys-guard-cc1.sh NEW_ROOT JOBS --cxx` selects the verified guarded
C producer as its read-only build seed and builds only `cc1plus.exe` in the
new epoch. It applies the same canonical source series; it does not require
another source workaround or rebuilding libstdc++. The companion
`test-native-cpp-guard.py` binds the actual immediate C-cohort copy receipt
and the exact new C++ prerequisite, stages only a `cc1plus` replacement, and
repeats the protected positive and real canary-failure controls.

That C++ gate additionally runs the existing native MSYS C/C++ matrix and
fresh all-protected DLL constructors, threads/TLS, exceptions, filesystem,
and hosted iostream/ctype consumers. It uses the exact private SDK DLL path
for child launches and the hash-bound consumer owner's process-local
`noninteractive_error_mode` context manager. The inherited `0x8003` error
mode prevents modal loader/crash dialogs while retaining real error codes;
restoration and a nonzero inheritance control are required. No system-wide
WER or loader setting is changed. A successful scoped C++ frontend delta
still does not requalify old target-library objects or admit the full SDK
or downstream protected C++ packages.

### Coherent jump-buffer ABI updates

The runtime-owned `sigjmp-20260907` successor corrects the Cygwin ARM64 public
`jmp_buf` allocation from 176 to 256 bytes and `sigjmp_buf` to 272 bytes.
The old header's macro save-mask flag at byte 176 overlapped a register save;
the runtime function ABI uses the flag at byte 256 and signal mask at byte
264. Existing machine code with the old allocation or macro offsets must be
recompiled, not merely relinked or run beside a replacement DLL.

For this cohort, `Stage-NativeMsysRuntime.ps1` also requires
`-RuntimeInputManifest <handoff-inputs\SHA256SUMS>`. It checks the sealed
inventory index, its child manifests, and all 268 C headers plus 19
runtime/CRT/library inputs against the owner's receipt before any SDK copy.
It does not replace genuine hosted C++ headers or pretend that existing
libgcc/libstdc++ archives were rebuilt. Materialize Unix symlinks first, and
use a new prefix with the fixed Cygwin-target assembler.

`test-msys-sigjmp.py` requires an exact hash-bound runtime-owned regression
source and receipt. It compiles fresh buffer-size/offset assertions and the
macro/function protected-fault guard at the original flags, runs each native
consumer within 15 seconds, and can also exercise a newly cross-compiled guard.
Publication of a jump-ABI cohort requires this new consumer result, not an
older SDK success record. Refresh any assembler-boundary evidence that also
binds the runtime DLL before publishing; old embedded evidence remains tied
to its original runtime.
The publisher adds `JumpBufferQualification` with the selected header,
consumer/runtime receipts, exact sizes and offsets, and explicit false flags
for retroactive consumer recompilation or target-library rebuilding. The
full native C/C++/DLL gate and strict downstream reader remain required;
runtime-owned protected-fault success alone is not an SDK acceptance result.
`test-sigjmp-stage-contract.ps1` rejects the old layout, an active runtime
writer, failed signal-mask recovery, or missing complete inventory before any
SDK creation or compiler execution.

The corresponding Linux cross SDK must be assembled from that newly
qualified native development payload and the same runtime pair. Its copied
compiler frontends remain independently identified; if their driver contains
absolute old-prefix tool paths, rebuild only the driver/collect2 relocation
closure as described above. Compile the same hash-bound jump regression again
with this cross driver and execute the resulting ARM64 program with the new
DLL. Never substitute the header under an existing old-object build directory.

### Coherent ucontext successor

The runtime-owned `ucontext-20260907-03` cohort preserves that jump-buffer ABI
and repairs the ARM64 context-entry layout and restoration path. Its sealed
receipt has status `coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified`.
`Stage-NativeMsysRuntime.ps1` accepts this status only with a quiescent writer,
16-byte stack alignment, actual register/stack argument cases, linked/null
returns, 32 coroutine yields, FEnv/signal-mask/TLS/errno preservation, invalid
context error behavior, and the complete paired header/runtime inventory.
No compiler flags or TEB stack-bound changes are part of SDK staging.

`test-msys-ucontext.py` recompiles the runtime owner's exact hash-bound
`ucontext-arm64.c` and invalid-context source with ordinary
`-O2 -g -Wall -Wextra -Werror`. It runs layout and full coroutine modes plus
the `-1/EINVAL` control under 15-second Windows kill-on-close jobs, checks the
actual process machine/image, and rejects an undrained child boundary.
Supply the existing `bounded_process.py` from the Git lane through
`--process-runner` and its exact `--process-runner-sha256`; the harness
snapshots that dependency into its evidence directory. An optional
`--cross-executable` exercises the fresh Linux-cross-produced context consumer.

The publisher requires refreshed `share\toolchain\ucontext\consumer-result.json`,
the jump-buffer result, and the assembler-boundary result, all bound to the
new runtime and the selected SDK components. It records additive
`UcontextQualification`; the ordinary full native C/C++/DLL gate and downstream
SDK reader still apply. These controls are not full libxcrypt shared-package
admission or a claim that every dynamically loaded constructor case is solved.
Copied libgcc/libstdc++ and compiler backends retain their original inventories
and build/FP-metadata scope. Old frozen SDKs and failure cohorts stay untouched.

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
| `gcc-arm64-seh-stackalloc-reg.patch` | Large stack adjustments allocated to GP registers other than x12, and intervening constant loads overwriting single-slot tracking |
| `gcc-arm64-seh-prepost-index-save.patch` | Single callee-save registers stored/restored with pre/post-indexed stack-pointer updates |
| `gcc-arm64-seh-sp-direct-save-portable.patch` | GP callee-save registers stored/restored at direct `[sp]` after a separate stack allocation |
| `gcc-arm64-seh-order-offsets.patch` | Scheduler movement of FP setup and missing paired-load offsets inside UNSPEC |
| `gcc-arm64-seh-frameless.patch` | Redundant unwind scopes for hundreds of frameless switch returns |

Unknown frame effects fail compilation instead of being silently encoded as
NOPs. `test-compiler-prologue.py` checks real instruction coverage and
FP-after-saves ordering in ordinary, variadic, conditional, and large dynamic
frames. Separate native runtime fixtures verify `RtlVirtualUnwind` at actual
instruction boundaries, including a changed dynamic SP and the final return.

The stack-allocation register patch is the exact final compiler-recovery
input, SHA256
`7397e8deacbc7ce0eec353dffd4956ef2b33b1b8f3bc2be975adb5b0c08f0973`.
It must follow `gcc-arm64-seh-frames.patch` and precede
`gcc-arm64-seh-order-offsets.patch`, matching the validated recovery series
(with the subsequent pre/post-index patch between them).
The unchanged real Git `object-file.i` reproducer compiled with
`-g -O2 -Wall -fstack-protector-strong` after the repair. Constants are tracked
per GP register in each frame's SEH state rather than in one static x12 slot.
The canonical source-lock transition is
`dab17118b65f265ca6682e02f7b19d3cd5a59afd99affdf6a8e48ecc92bc537f`
to `9ff7b5f12f7e30e08408bc0cb8661ab8ac70464d9caeab2a02ab7245101c00c6`
(17 GCC, 8 binutils, and 1 w32api patches).
Adopting these source inputs does not update an installed compiler or qualify
an older prefix. Package providers must bind their actual corrected compiler,
frontends, assembler/linker, target headers/libraries, and licenses to the
consumer-qualified inventory; source identity alone is not a binary receipt.
The existing source guard remains fail-closed: a checkout carrying the complete
predecessor series is not necessarily a prefix of this newly ordered series.
Do not replay an old stage, reset that checkout, or bypass its guard. Use a new
dedicated source root for the complete pinned series, or separately reconcile
the exact source delta before an authorized incremental build.

The later Tcl `tclStubLib.i` recovery adds the exact
`gcc-arm64-seh-prepost-index-save.patch`, SHA256
`8caab28001598547efbcf9b81eb2e680d0f6d29174a4fcfaaf86a3ec28d4f252`,
immediately after the stack-allocation register patch. It emits the existing
`.seh_save_reg_x` / `.seh_save_freg_x` operations for single-register indexed
saves/restores without changing the application's optimization, frame-pointer,
debugging, or stack-protection settings. The resulting canonical source lock is
`79a4b877b7c977e8815f3c9b4cdd19503b1c9ba28ef012ebefb9b6841d0db0ad`
(18 GCC, 8 binutils, and 1 w32api patches). Recovery's rebuilt MinGW frontends
are a separate binary cohort, not a retrospective update to any existing MSYS
SDK or the prior cc02 package inventory.

The next TclMain producer repair adds `gcc-arm64-seh-sp-direct-save.patch`,
SHA256 `88fe85505db8a692f21993e80e432d52ac712b75875b698dc6217a69ef9ce6bc`,
after the pre/post-index patch and before the order/offset patch. The canonical
source lock becomes
`c5a968eb881454cfbc02de9a60257573385a44079cd63d459f685b041abdcdae`
(19 GCC, 8 binutils, and 1 w32api patches). That recovery artifact uses CRLF
line endings and remains preserved by a specific `.gitattributes` exception.
The later complete CMocka source-guard replay exposed an ordinary WSL
`git apply --check` failure for this artifact against the fresh ordered series.
The maintained lock now uses the separately named
`gcc-arm64-seh-sp-direct-save-portable.patch`, SHA256
`cfccc4de9849a50b5687b0a50a945abcd34dbf96dfe82d3f8ea4918761f2772c`:
recovery's deliberate LF and hunk-offset refresh, not a weakened apply command.
Its hunk body is identical; the source guard compares the full resulting trees
with a normalized copy of the original patch. The old bytes and failed
application evidence are retained, never silently rebound to the new hash.
The fix is deliberately **GP-register-only**. Recovery's exact TclMain/frontier
and native `RtlVirtualUnwind` partial-boundary evidence covers direct `[sp]`
LR saves/restores. That GP-only patch did not address the separately observed
D8 `.seh_save_freg` mismatch; the GAS repair below resolves its encoding cause.
Neither floating-point unwind qualification nor a full Tcl/Git build is
retrospectively implied for the earlier GP-only cohort.

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

`binutils-arm64-fp-unwind-enum-order.patch` fixes the separate D8/FP unwind
defect in GAS, not in GCC's selected stack offset. The header's enum put
`save_lrpair` after the FP entries, but `unwind_code_pack_infos` expected it
before them. Because the enum selects an encoder-table entry, the mismatch
made `.seh_save_freg v8,8` produce `da00` instead of `dc01`, and
`.seh_save_fregp v8,16` produce `d642` instead of `d802`.
Moving that single enum member restores the documented opcode dispatch for
single, paired, pre/post-indexed FP saves and LR pairs.

The exact recovery patch SHA256 is
`520ea312ae1e5d3764b57ad311dc4417af678192044d70a0d4381690124b7679`;
it follows `binutils-arm64-add-fp.patch` and precedes the storage patch.
The canonical source lock becomes
`03f8478a8cf07efd76bacaa687dc103e76830b0c4eb7de31cb5721b1dc8dab56`
(19 GCC, 9 binutils, and 1 w32api patches). Recovery retained the bad-byte
baseline and validated corrected bytes plus native `RtlVirtualUnwind`
D8/D9 lower-64-bit, SP, LR, and PC behavior at partial boundaries.
The successor assembler is a new binary cohort. Source integration does not
change frozen SDKs, and replacing an assembler does not fix existing object
unwind data: affected objects must be reassembled/rebuilt and relinked before
their outputs can claim this repair.

### MSYS assembler-delta SDKs

The FP enum mismatch affects both MinGW and Cygwin/MSYS ARM64 PE assemblers,
independent of the assembler's host. The frozen native MSYS and Linux Cygwin
assemblers both reproduced the old bad bytes. Do not relabel a fixed
MinGW-target assembler as a Cygwin-target build or mutate an accepted SDK.

`bootstrap-msys-fp-as.sh` exports the exact pinned binutils source into a new
private epoch, applies the locked series, and builds three sequential stages:

```bash
export MSYS_FP_AS_EPOCH='/root/arm64-vnext-20260905/toolchain/epochs/msys-fp-as-<identity>'
JOBS=1 bash bootstrap-msys-fp-as.sh prepare
JOBS=1 bash bootstrap-msys-fp-as.sh host-as
JOBS=1 bash bootstrap-msys-fp-as.sh cross-as
JOBS=1 bash bootstrap-msys-fp-as.sh native-as
```

The Linux MinGW-target `host-as` is a bootstrap prerequisite for building
the Windows-hosted Cygwin-target assembler with corrected FP metadata in its
newly compiled host objects. The Linux Cygwin-target and Windows Cygwin-target
assemblers are distinct builds. Each stage snapshots the recipe and retains
source checksums, configuration, logs, and target identities; no package
manager operation is implicit.

`Stage-MsysAssemblerDelta.ps1` clones a qualified native SDK, checks every
baseline input, replaces all three matching assembler aliases, preserves the
compiler/runtime/static libraries, and records the assembler-specific source
lineage separately. `stage-msys-cross-as-delta.sh` creates the corresponding
Linux SDK and rebases only its driver/collect2 tool paths; the original
frontends and development libraries remain unchanged.

`test-gas-fp-unwind.py` checks seven exact raw `.xdata` encodings, with
`--expect-legacy` preserving the known bad FP bytes and unchanged GP control.
`test-msys-fp-native.py` executes 18 actual Windows `RtlVirtualUnwind`
boundaries for direct, paired, and pre/post-indexed D8/D9 saves, SP/LR/PC
recovery, and a wrong-LR negative. Its optional Linux-assembled object must
have identical `.xdata` and pass the same native harness. The fixtures derive
from the recovery lane's accepted matrix; native process-machine checking is
also required by the maintained harness.

Before publication, place the raw encoding and native boundary results in
the staged SDK's `share\toolchain\assembler-fp\raw-encoding.json` and
`native-boundaries.json`, then run a new full MSYS compiler acceptance.
The publisher requires both host-object executions to match the selected
assembler/runtime and emits an explicit `AssemblerQualification` binding.
The strict downstream SDK reader still applies; no old package-cache key or
inventory is reused.

**This is an assembler-producer delta, not a whole-runtime rebuild.** Newly
assembled crypto or other application objects get corrected FP metadata.
Copied runtime DLLs, libgcc/libstdc++, and earlier packages keep the metadata
from their original objects. Their existing behavioral receipts do not become
FP-unwind qualification, and complete artifact/runtime closure must explicitly
reassemble/rebuild affected objects and bind those new outputs.

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
