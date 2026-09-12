# Native MSYS ARM64 SQLite 3.53.4

This is an executable, bounded implementation of the pinned MSYS recipe, not
package admission or a full SDK/Git qualification. The native Windows-hosted
compiler targets **aarch64-pc-cygwin, MSYS LP64**. The separately authorized h1
MinGW compiler builds a Windows-host **configure interpreter only**; it does
not build SQLite libraries, delivered lemon, Tcl, or other target payloads.

## Preserved recipe

`sqlite_build_inputs.py` consumes the exact configure options and all 20
preprocessor definitions from `ssh-recipes.json`. The seven independent stages
are `sqlite`, `libsqlite`, `libsqlite-devel`, `sqlite-doc`, `tcl-sqlite`,
`sqlite-extensions`, and `lemon`. The CLI package includes `sqlite3`,
`sqlite3_analyzer`, `sqldiff`, `dbhash`, and `rbu`. All 56 recipe-selected
extension DLLs and the complete 1,027-file documentation input are retained.

`sqlite-inputs.json` binds the prepared source/docs/three already-applied
patches, compiler, bootstrap, Tcl, readline, ncurses, zlib, observer and Python.
Adoption verifies complete input/copy/input inventory equality. Original
inputs are never modified. Recipe assets are retained as exact inputs; their
unbounded `make -j` and masked `quicktest || true` are **not executed**.

## Execution

All commands use the native Python interpreter named in the input lock. Every
output directory must be fresh, below `C:\ag-sqlite-e138-01`. Do not rerun
adoption over an existing area.

1. `adopt-msys-sqlite.py` adopts the original inputs.
2. `adopt-sqlite-host-compiler.py` and `prove-sqlite-host-jim.py` adopt the
   separately authorized h1 compiler and prove the host Jim's ARM64 PE,
   zero/nonzero raw exits and argument fidelity.
3. `prepare-sqlite-host-source.py` creates the current explicit private
   host-source view. Its inventory records every changed file and the patch.
4. `configure-sqlite-host-jim.py --source SOURCE --build BUILD --output OUTPUT`
   performs the full target configuration with the Windows-host interpreter.
5. `build-msys-sqlite.py --phase PHASE --build BUILD --output OUTPUT --jobs N`
   runs `build`, `extensions`, or `install`, in that order. `N` is 1 or 2.
   Installation produces `BUILD\splits\PACKAGE`; it does not install globally.
6. `test-native-msys-sqlite.py --build BUILD --output OUTPUT` runs the native
   staged unit proofs, serially, in a fresh composite runtime.

The legacy `configure` phase retains the direct native-MSYS interpreter route
for investigation. It must not be treated as accepted configuration when the
observer reports high-exit fork/overlay events. The Windows-host configure
route avoids that particular observer ambiguity. Host Jim's configure
qualification does not qualify it for every code-generation operation; actual
SQLite generation uses the native MSYS Tcl interpreter.

## Path and process boundaries

Compiler include/library/temp paths are Windows `C:/...` paths. Tcl script and
source-directory arguments use the actual private MSYS `/c/...` mount view.
The argument adapter converts only declared script/source-file positions, not
SQL or arbitrary application arguments.

Native Tcl and its MSYS children must load the **same canonical**
`tcl\usr\bin\msys-2.0.dll`, not another byte-identical copy from a different
runtime root. The qualified `etc\fstab` is copied only into private runtimes.
Tcl compiler/config views retain 8.6.12, all feature flags, real headers,
import libraries and stubs; only input paths change.

`sqlite_tcl_relay.py` executes the unchanged, verified native target relay. It
removes the foreign shell's argument-conversion switch only after native
Python has received the literal argv, so it cannot leak into Tcl's later host
tool invocations. The observer/relay never decode, forge or promote raw exits.
`capture-native-exception.py` adds standard `--` child-argument separation to
the imported capture tool; its original positional invocation remains valid.

## Proof and upstream gates

The 66-step staged unit proof includes shared/static C API sessions and
changesets, WAL, math, JSON, FTS5, RTree, DBSTAT/DBPAGE, STAT4, update/delete
limits, metadata, CLI compile options, readline DLL closure, Tcl Unicode
binding, analyzer page accounting, diff/hash/RBU, packaged lemon, 50 isolated
canonical extension initializers, five direct helper APIs, and the original
Win32-only stdio helper's no-op MSYS DLL. Extensions are loaded with `.load`,
outside an active SQL VM; combined `basexx` uses its actual public initializer,
not the separately exported internal helpers. All payload PEs must be ordinary
ARM64 PE32+ and loaded non-system DLLs must match the private inventory.

Upstream results are separate from unit results:

- `build-msys-sqlite.py --phase quicktest ...` runs the actual unmasked target.
- `--phase tcltest` runs the original `veryquick.test` with its standard output
  options. A file-level abort remains a failure, not a completed suite.
- `replay-sqlite-quicktest.py --build BUILD --output OUTPUT` preserves all
  All-O0/All-Debug/fuzz/sanitizer jobs using the pinned private driver fixes.
- `run-sqlite-per-file-tests.py --output OUTPUT --jobs N` uses the upstream
  runner to execute all veryquick files independently. This is **not** a
  substitute claim for quicktest's separate configurations.

The opt-in source patch fixes shell-text transport, explicit private Tcl and
build-triplet discovery, actual `.exe` program target names, and per-job shell
environment initialization. It removes no tests, assertions, features, or
instrumentation. Permission, symlink, sanitizer, fork and native-exit failures
remain visible in logs and result JSON. Windows Developer Mode, ACL policy,
global mounts and shared installations are never changed.

The pinned `src/os_setup.h` deliberately selects SQLite's Win32 VFS for
`__CYGWIN__`; this is still the MSYS LP64 package, not a MinGW library.
Upstream All-O0/All-Debug presets separately request the Unix VFS. Do not
change either configuration to conceal the corresponding platform failures.
The optional per-file verbose output uses SQLite's existing
`--verbose=file --output=...` interface and retains all assertion diagnostics
in unique persistent files; it does not qualify cross-runtime pipe behavior.

`qualify-sqlite-environment.py --output OUTPUT` is a separate runtime
qualification diagnostic. It compares inherited and Tcl/C-mutated synthetic
variables across same-runtime MSYS, x64 MSYS and native Windows children.
Cross-architecture child-info/environment loss is not waived merely because
the private test-driver initialization makes a particular test runnable.

Keep aggregate build/test concurrency at two or fewer, including nested
invocations, and free RAM above 8 GiB. Retain every failed attempt and wait for
the observer's job drain before returning the allocation. Full upstream
success, package/provider admission and `full_cpp_qualified` must never be
inferred from the staged unit proof.

## Targeted continuation: native shell and TDBC

The continuation uses fresh `C:\ag-sqlite-resume-01` outputs, leaving the seven
original split stages and their handoff unchanged. This MSYS LP64 SQLite 3.53.4
consumer is distinct from the MinGW/UCRT SQLite used by the Python provider.

`resume-native-sqlite.py --output OUTPUT` reproduces the old shell import
failure and exercises the installed TDBC SQLite module with bound Unicode
parameters, commit/rollback, metadata and independent Windows database
readback. The native C control identifies `popen()` failing with `ENOENT`
because the original private runtime has no `/bin/sh`.

`sqlite-shell-candidate.json` binds the separate native utilities, stable
candidate Bash/sh, and qualified d70 runtime receipts. The files-only
`prepare-sqlite-shell-consumer.py --output OUTPUT` builds a new composition.
It preserves original SQLite/Tcl/zlib payloads and `etc/fstab`, provides the
real native shell and utilities, and creates a real private `/tmp` directory.
It retains the original generated Info index instead of silently overwriting
it with the utilities index; this is runtime composition, not installation.

`run-sqlite-shell-consumer.py --prepared OUTPUT --sha256 PREPARATION_SHA`
performs ordinary and independently captured native-parent pipeline controls.
It checks actual native child executable coverage, raw exits, DLL identity,
all five imported rows, and TDBC transaction results. Bash remains a
candidate input: successful SQLite consumer controls do not admit Bash or
requalify the whole SQLite package under a different runtime.

`run-sqlite-upstream-shell5.py --output OUTPUT --consumer COMPOSITION
--consumer-sha256 RESULT_SHA` runs all 53 original `shell5.test` assertions.
Both the assertion summary and native observer must pass for an overall
pass. In particular, a zero-error test summary does not override unresolved
raw-256 negative-CLI child exits. The earlier missing-`/tmp` stderr failure is
also retained; the fix creates the required directory, not a warning filter.

## Combined-runtime MVP package

The next qualification uses `C:\ag-sqlite-combined-01` and the sealed combined
runtime receipt `f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b`.
The runtime DLL is
`907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`.
The associated import library and CRT are retained as provenance inputs, not
bundled into the SQLite runtime package. Neither SQLite nor the runtime is
rebuilt for this compatibility qualification.

1. `prepare-sqlite-combined.py --output INPUTS` privately copies the runtime
   view, checks the complete old SQLite inventories, parses the real headers
   and import tables of every PE, and copies three already-qualified native
   API fixtures. Original sources, packages and runtime prefixes stay read-only.
2. `test-native-msys-sqlite.py --root C:\ag-sqlite-e138-01 --build
   C:\ag-sqlite-e138-01\build-06 --output PROOF --prepared INPUTS
   --prepared-sha256 SHA` executes the 63 positive consumer cases, reusing
   rather than rebuilding the three API programs. Each captured process must
   load the exact new runtime from the private path. No compiler or x64
   bootstrap directory is on the target execution path.
3. `run-sqlite-combined-ordinary.py --prepared INPUTS --sha256 SHA --output
   ORDINARY` independently executes shared/static C APIs and direct extension
   helper APIs without a debugger.
4. `package-sqlite-runtime.py --prepared INPUTS --prepared-sha256 SHA --proof
   PROOF --proof-sha256 SHA --ordinary ORDINARY --ordinary-sha256 SHA --output
   PACKAGE` creates `libsqlite-3.53.4-1-aarch64.pkg.tar.zst` and `receipt.json`.
   It verifies the decompressed member contents against the exact input
   inventory, not just the compressed archive's hash.

The MVP artifact contains only `usr/bin/msys-sqlite3-0.dll`, its license, and
standard `.PKGINFO`; the assembly owns the runtime dependency. The original
DLL bytes, including their embedded build debug sections, are unchanged.
No separate symbols, development artifacts, unrelated CLI, documentation or
extension binaries are included. All seven original split inventories and PE
identities remain traceable in the receipt.

The receipt records the upstream Fossil commit, patched prepared-tree hash,
source archive and recipe hashes, original build, actual per-file PE machine
and imports, archive path/size/SHA-256, combined-runtime source commit and exact
DLL/import/CRT identities, ordinary and captured proof receipts, and process
drain. This is a new compatibility proof, not a claim that the old SQLite
binary was relinked with the new CRT. Broader upstream failures and exit-domain
limitations are not waived, and final provider admission belongs to assembly.
