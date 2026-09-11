# Native Berkeley DB

The maintained DB profile preserves Berkeley DB 6.2.32's pinned MSYS recipe:
C++, compatibility 1.85, DBM, shared and static libraries, all 15 utilities,
and documentation. Java, Tcl and test instrumentation remain disabled in the
package profile because they are disabled in that recipe.

`build-msys-library.py --package db-msys` performs a fresh serial native build.
Its two source patches recognize GCC's `__aarch64__` mutex backend and preserve
native Windows GCC library-search paths in libtool. Neither forces a configure
result, removes stack protection, nor bypasses dependency checks.

## Combined-runtime package qualification

`db_combined_release.py` reuses the already-built, hash-bound stage:

1. `prepare --output ROOT --db-handoff FILE --runtime-handoff FILE --shell-root ROOT`
   verifies and copies the sealed inputs. The combined runtime's complete public
   headers and runtime link libraries replace only the private compiler copy.
   The target execution root gets the exact new runtime DLL; source roots remain
   read-only. No DB or runtime rebuild is performed.
2. `validate --output ROOT` builds independent protected C/C++/1.85/process
   consumers with that private compiler, runs them natively, checks ordinary
   cross-DLL C++ exception handling and live module identities, runs all utility
   version paths, and performs a load/verify/dump/reload round trip. Native child
   exit status and process-generation evidence are retained.
3. `package --output ROOT` emits unsigned, genuine pacman-format
   `db`, `libdb`, `libdb-devel`, and `db-docs` `.pkg.tar.zst` archives with
   `.PKGINFO`, `.BUILDINFO`, and compressed `.MTREE`. Every archive member is
   read back and checked against its source size/hash. Every PE is parsed as
   ordinary ARM64 (`0xAA64`), including its import table.

`runtime-only` contains only the two DB DLLs and the original license, for the
Git/SSH runtime artifact. The complete 5,605-file `stage` remains separate for
SDK/Perl consumers. Compiler, proof fixtures, shell-driver files, and MSYS
runtime DLLs are not smuggled into DB packages.

## Qualification boundaries

- Original source identity is a pinned Oracle release archive, not an invented
  upstream Git commit. The receipt binds its archive hash, original/prepared
  source inventories, pinned MSYS recipe commit, and maintained patch hashes.
- The upstream C++ suite passed eight cases. The channel test's master-transition
  synchronization patch passed deterministic controls and three ordinary runs.
- **The full-load MutexAlignment run timed out after 900 seconds during
  configuration 9 of 24.** Its 83-created/76-recorded exit accounting is partial;
  this original receipt is not a pass and remains preserved. The subsequent
  unchanged full matrix on the same D70 cohort completed all 24 configurations
  in approximately 3,734 seconds, with raw exit 0 and 314/314 exit coverage.
  Independent wait measurements explain why the original budget was too short;
  see [the timing investigation](DB-MUTEX-TIMING.md). No worker counts, load or
  cases were reduced. This does not imply a combined907 full-matrix or complete
  upstream-suite pass.
- Optional native Tcl coverage remains separate. A debugger-only exception
  limitation does not supersede the ordinary held-process C++ proof.
- Package creation and archive readback are not signature, repository/provider,
  whole-SDK, Perl, OpenSSH, or Git-distribution admission.

Run the targeted controls using the existing runner:

```powershell
python -B -m unittest -q test_db_package test_msys_library test_native_job_runner
```
