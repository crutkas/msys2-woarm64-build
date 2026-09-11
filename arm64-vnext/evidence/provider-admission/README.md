# Provider admission evidence

This directory preserves the admission authority previously stored under
`C:\ap11-native-provider-intake` before that volatile machine path is removed.
The repository is `crutkas/msys2-woarm64-build`, the preservation branch is
`crutkas-native-provider-intake`, and the pre-preservation repository commit is
`d3285432b03cc0398f3212c51b40237c701f719f`.

The copied authority files are byte-for-byte records. `manifest.json` maps every
repository path to its original absolute path, byte size, and full SHA-256.
`.gitattributes` disables text conversion for the preserved record types. No
package archive, source archive, DLL, executable, static library, signature, or
other payload binary is included.

## Rehydration authority

`acceptance-criteria.json` preserves the seven grouped acceptance gates measured
by the maintained contract and assembler documentation. The detailed executable
authority remains:

- `arm64-git-recovery/contracts/full-release-v1.json`
- `arm64-git-recovery/scripts/assemble-full-release.py`
- `arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md`

Do not relax or reinterpret those sources from a limited provider projection.
Rehydrate a provider by resolving its original package/source bytes separately,
verifying every referenced full SHA-256, and feeding only its exact qualified
export to the unchanged assembler. The preserved JSON records are evidence and
metadata, not replacement package payloads.

## Strict 81-blocker authority

`audit/audit-v18-qualified-openssl.json` is the authoritative OpenSSL-era strict
audit: 64 selected packages, 16,633 payload files, 267 native ARM64 PE files,
81 blockers, `release_complete=false`, and no release archive. Its SHA-256 is
`72dde6b8014c8ff0b6d96cea1ccc3d7ccfd35c241333cf9773b6191251a990cb`.

`audit/audit-v18-static-closure-supplement-v1.json` preserves the non-admission
decomposition of those same 81 rows into 22 gettext-related and 59 other rows.
It does not clear a blocker or replace the strict audit. The input and rejection
authority are preserved beside the report. Later ledger records may document
additional valid admissions without retroactively changing this sealed audit.

## Scope boundaries

### Limited libintl

`limited-libintl/export.json` authorizes only unchanged `libintl-8.dll`,
`libiconv-2.dll`, and six package-owned license files for the limited first Git
artifact. It is not a `mingw-w64-aarch64-gettext` provider, cannot use an alias
or fake `provides`, and does not satisfy the strict GNU gettext gate. The
compiled default `/clangarm64/share/locale` means unbound/default-domain
localization is not admitted. Revoked gettext archive `7abded5b...` remains
revoked.

### Limited PCRE2

`limited-pcre2/export.json` authorizes only unchanged `libpcre2-8.dll` and its
license from selected package `mingw-w64-aarch64-pcre2 10.48-1`. It creates no
new package and claims no fresh or reproducible PCRE2 build. The `10.48-3`
candidate exporting `libpcre2-8-0.dll` is not borrowable for current Git, and no
renamed DLL alias is permitted.

`native-msys-pcre2/` is a different runtime-907 MSYS package admission. It must
not be conflated with the MinGW/UCRT limited projection or inferred across
runtime cohorts.

### OpenSSL supersession

`openssl/handoff.json` is the current closure authority. Old package SHA-256
`256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3`
is superseded and unadmitted. Current package SHA-256
`02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab`
is selected in both preserved revoked-free network and Python closures, with
zero old rows remaining. Historical artifact generations may still physically
contain the old bytes; they are not current closure authority.

### Header overlay

`header-overlay/export.json` admits the Cygwin/MSYS ARM64 w32api v12 Interlocked
successor only as an SDK/header input for fresh private consumers targeting
`aarch64-pc-cygwin`. It is not MinGW, GCC, CRT, runtime, package, Perl, OpenSSL,
or full-release admission. It must not mutate a shared prefix or be treated as
evidence for unchanged existing binaries.

### Provider ledger

`ledger/` preserves the hash-linked v20 through v42 provider ledger chain. The
v42 tip SHA-256 is
`c198b4018ea31c97c1e3b96249b41029754cf4a315c1bc0ebd266ad0e01ef3d4`.
Each version remains immutable historical authority; later versions supersede
current-state selection but do not erase earlier rejection, conflict, or scope
decisions.

## Standing runtime rule

Every artifact qualifies against its own runtime contract. MinGW/UCRT libraries
must not be forced to import `msys-2.0.dll`. Genuine MSYS providers and
consumers must prove their exact MSYS runtime cohort. Import shape alone does
not authorize cross-runtime substitution. In particular, runtime-907
admissions do not imply d70 compatibility, and d70 packages cannot be relabeled
for runtime-907.

## Integrity procedure

1. Check out the preservation commit without line-ending conversion.
2. Hash every copied authority file and compare it with `manifest.json`.
3. Resolve any omitted payload from its original immutable source using the
   full hashes embedded in the preserved records.
4. Recreate fresh private roots; never restore evidence by writing into a
   shared package prefix.
5. Preserve rejection, revocation, runtime-cohort, and supersession boundaries.
6. Run the maintained assembler against explicit qualified exports.
7. Treat exit code 2 as an incomplete audit and any hard conflict as a failed
   input; never publish an apparently complete archive while blockers remain.
