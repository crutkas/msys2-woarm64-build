# Native ARM64 network provider handoff

## Deliverable

The installable package repository is:

`C:\ap09-ca5f\curl-packages-v2\export-12\packages`

Its receipt is `C:\ap09-ca5f\curl-packages-v2\export-12\export.json` with SHA-256
`546d8ca66282b89803d6423f36db1f562fadf759e8d4a7e11870cb485ea84dd8`.
The export contains 34 real pacman packages. Every package has `.PKGINFO`,
`.BUILDINFO`, and `.MTREE`; the original admitted payload archives are unchanged.

This export is not a current combined-admission input. Its
`mingw-w64-aarch64-gettext-0.26-1` archive was revoked because the payload is
actually GNU gettext 1.0 and contains private producer paths. The revocation is
`C:\ap11-native-provider-intake\current-admission-revocation-v1.json`, SHA-256
`206cffaff0a16fc2b0453d74c923b7830fa62c0d7715327cb5a61d8e35421894`.
Use the revoked-free selective closure as the base for the truthful replacement.
The first signed-source corrective attempt failed before checks/install with an
ARM64 SEH frame error and remains rejected. The current revoked-free intake
baseline is
`C:\ap11-native-provider-intake\audit-v17-revoked-free.json`, SHA-256
`d71f2c02617dbc24e338065f5d5ef5e44f08669240fc40b21a9ad82a8823fc47`.
It admits native MSYS Bash, libintl, libasprintf, and libiconv packages, but
those packages do not provide the `mingw-w64-aarch64-gettext` identity or
resolve the 21 MinGW `libintl-8.dll` import blockers. Enforcement receipt
`C:\ap11-native-provider-intake\provider-rejection-enforcement-v12.json`,
SHA-256
`69818c620590f23bd38ba7921c515cdf6629d7d20a55c15fbe8427bf6f2779be`,
requires frame-pointer retention, source/build prefix maps, and the complete
original qualification scope. GCC 15 also requires the target-specific
`-mno-omit-leaf-frame-pointer` switch: generic
`-fno-omit-frame-pointer` alone still reproduces the ARM64 SEH assembler
failure in `gettext-tools/gnulib-lib/libxml/xpath.c`.
After that compile correction, the full build reached `make check` and exposed
an independent bundled-libtool typo: the MSYS `cygpath` helper writes its
result to a different variable than its callers read. The hash-bound patch is
`patches/runtime-providers/gettext-1.0-libtool-msys-cygpath-result.patch`,
SHA-256
`5a52e4ef64b1db22b7aa36b736407601577ff338ebb3289f1e06ff47326dff15`.
It is applied only to a private source copy; the signed official extraction is
never modified.
The full suite then reached 626 passes and exposed native Windows Python CRLF
output in `lang-python-1` and `lang-python-2`. Both tests pass with
trailing-CR normalization. The maintained narrow test patch is
`patches/runtime-providers/gettext-1.0-python-test-crlf.patch`, SHA-256
`b2696cc54b2cd26dc6d50885e3256ec13add9617823bd5c782c3625763b4d0b0`;
it applies the same `tr -d '\r'` normalization already used by other upstream
gettext tests and does not weaken `diff` globally.
Those two upstream test scripts contain ISO-8859-1 fixtures, so the maintained
applicator performs a byte-preserving Latin-1 round trip; decoding and rewriting
them as UTF-8 would corrupt the fixture bytes and is rejected by qualification.
The build also excludes only gettext's installation-directory `-D` arguments
from MSYS path conversion (`LOCALEDIR`, `INSTALLDIR`, `BINDIR`, `LIBDIR`,
`LIBEXECDIR`, `GETTEXTDATADIR`, `PROJECTSDIR`, and `GETTEXTJAR`). This keeps
their compiled values at `/mingwarm64` while retaining normal conversion for
real source, include, and library filesystem arguments. A blanket
`MSYS2_ARG_CONV_EXCL=*` is not used.

The truthful replacement is now complete:

- Package:
  `C:\ap12-ca5f\gettext-package-build-02\mingw-w64-aarch64-gettext-1.0-1-any.pkg.tar.zst`,
  SHA-256
  `37baf6126525e243d314c47fd4f1ba6a3ee5eb0abcadac935864a45086c6b6e8`.
- Standalone provider export:
  `C:\ap12-ca5f\gettext-provider-export-01\export.json`, SHA-256
  `32d4d0b14a96f24175070919e349e950fbaaec28e32ba81da673390970735889`.
- Network closure:
  `C:\ap12-ca5f\gettext-closure-supersession-01\network\export.json`,
  SHA-256
  `1175b640b3d94e78ea146661aff1311eaf196c72715c1ab2eef4793c804fc929`.
- Python closure:
  `C:\ap12-ca5f\gettext-closure-supersession-01\python\export.json`,
  SHA-256
  `0d9dd965a74d6bfc910a64fccb7b5a1ce751976b2eb5c6b3f739ae2fd069fac7`.
- Combined handoff:
  `C:\ap12-ca5f\gettext-closure-supersession-01\handoff.json`, SHA-256
  `8a5d8f064ecf1e4b80918c1af9b59b15465742da0dcf279bcb052e97993171aa`.

The package has genuine makepkg `.PKGINFO`, `.BUILDINFO`, and `.MTREE`,
declares only `mingw-w64-aarch64-libiconv`, and reports 2,849 files with zero
alterations under package-specific `pacman -Qkk`. The inherited libiconv
archive has 18 permission/timestamp MTREE mismatches in every retained export;
qualification records that limitation without waiving it and independently
proves every installed libiconv file byte-identical to its bound archive.
All 28 gettext PE files are ARM64 and have resolved imports. Installed shared
and static libintl consumers run, copied `git.exe` from the exact 15-split
2.55.0.windows.5 cohort runs against the replacement `libintl-8.dll`, and a
second moved root reports its new locale directory, loads the shipped French
catalog, preserves missing-domain identity, and reads the catalog with moved
`msgunfmt`. Neither closure contains the revoked archive bytes; every other
package archive is unchanged.

The canonical Git provider is `mingw-w64-aarch64-curl` 8.22.0-1 using OpenSSL.
`mingw-w64-aarch64-curl-gnutls` and `mingw-w64-aarch64-curl-winssl` provide the
same package identity but conflict with it and with each other. Install only one
curl TLS provider in a prefix.

## Immutable source locks

| Input | Identity |
|---|---|
| Curl admission | `C:\ap08-d207\curl-chain-01\admission-01\admission.json`, SHA-256 `64e5be9d2a93c3055ce3a00ae19fe05ea2547da243d982da56fb2f8eda726677` |
| Pinned curl recipe | `git-for-windows/MINGW-packages@d65b87de173ac2209a63cef8c4528669b5571fd3`, PKGBUILD SHA-256 `1af43e24c3e375b084c2149f986b5e53e9f7c3bc5bf80ed8c40054f253b07ff3` |
| OpenSSL package | `mingw-w64-aarch64-openssl-3.6.4-1-any.pkg.tar.zst`, SHA-256 `256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3` |
| c-ares package | `mingw-w64-aarch64-c-ares-1.34.8-1-any.pkg.tar.zst`, SHA-256 `71ffa79442d0acc49028409b21f922a9c5503dd0ceecabe8fb87fa280e4dfc8d` |
| Git recipe | Git `2.55.0.windows.5`, PKGBUILD SHA-256 `e072d843e42e9b8401bd7b3767f3920572b70415104bd42f7180372df9344e2a` |

## Proven installation

The canonical clean pacman root is:

`C:\ap09-ca5f\curl-packages-v2\integration\openssl-root-05`

Evidence in that directory covers:

| Check | Evidence |
|---|---|
| Pacman install and dependency resolution | `pacman-install.log`, `pacman-dependency.log` |
| Pacman file ownership | `pacman-ownership.log` |
| Native curl feature identity | `curl-version.log` |
| Recursive DLL closure | `import-closure.log` (`missing-non-system=0`) |
| Shared consumer | `shared.exe`, `shared-run.log` |
| Fully static consumer | `static.exe`, `static-run.log`; its import table does not contain `libcurl-4.dll` |
| Relocated CMake config consumer | `cmake-consumer\build\relocated-curl.exe`, `cmake-configure.log`, `cmake-build.log`, `cmake-run.log` |

The alternate provider roots are:

- GnuTLS: `C:\ap09-ca5f\curl-packages-v2\integration\gnutls-root-03`
- Schannel: `C:\ap09-ca5f\curl-packages-v2\integration\winssl-root-01`

Both contain successful `curl-version.log` evidence. The OpenSSL provider reports
OpenSSL 3.6.4, c-ares 1.34.8, HTTP/2, HTTP/3, nghttp3 1.18.0, and ngtcp2 1.25.0.
All exported pkg-config, CMake, and config-script metadata was audited for the
private `C:\ap08-d207`, `C:\ap06-2160`, and session-state roots with no matches.
That metadata result does not clear the compiled OpenSSL-variant
`libcurl-4.dll`: SHA-256
`d060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669`
contains the producer `CURL_BINDIR`. It is an independent operational-prefix
blocker that requires a pinned-source canonical-prefix curl rebuild; repackaging
cannot remove it. The combined curl/Tcl lineage evidence is
`C:\ap11-native-provider-intake\operational-prefix-lineage-v1.json`, SHA-256
`b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332`.

## Git recipe integration

Prepare the pinned 15-split recipe without altering its source:

```powershell
.\.github\scripts\prepare-git-mingwarm64-recipe.ps1 `
  -SourceDirectory C:\ap06-2160\gitpkg01\recipe\mingw-w64-git `
  -OutputDirectory C:\private-new-root\mingw-w64-git `
  -MakepkgReady
```

The maintained patch adds only `mingwarm64` to `mingw_arch`. It preserves the
tag, source checksums, all package functions, Rust use, documentation targets,
and PDB behavior. `-MakepkgReady` additionally converts the copied PKGBUILD
from CRLF to LF because makepkg refuses to source a CRLF recipe. It also
rewrites only the packaged `git-p4` shebang from `/usr/bin/python` to
`/usr/bin/env python.exe`, so the script uses its declared
`mingw-w64-aarch64-python` dependency instead of an unrelated MSYS
interpreter. The mapped environment is:

| Variable | Value |
|---|---|
| `MSYSTEM` | `MINGWARM64` |
| `MINGW_PREFIX` | `/mingwarm64` |
| `MINGW_PACKAGE_PREFIX` | `mingw-w64-aarch64` |
| `CC` | `gcc` |
| target | `aarch64-w64-mingw32` |

The makepkg-ready recipe used for the full build is
`C:\ap10-ca5f\git-full-01\recipe-build\PKGBUILD`, SHA-256
`289b6cb61dcbc5e8842e8831a2483be21cd6098fe21bf52c30cfea44cf0d3813`.

## Git prerequisites closed

The private canonical pacman root resolves these exact Git recipe dependencies:

- `mingw-w64-aarch64-curl`
- `mingw-w64-aarch64-openssl`
- `mingw-w64-aarch64-c-ares`
- `mingw-w64-aarch64-expat`
- `mingw-w64-aarch64-pcre2`
- `mingw-w64-aarch64-gettext`
- `mingw-w64-aarch64-cc`
- `mingw-w64-aarch64-rust`
- `mingw-w64-aarch64-ca-certificates`

`cc` is satisfied by the qualified native GCC package, which intentionally
provides `mingw-w64-aarch64-cc`; it is not disguised as a fabricated `gcc-libs`
split. `rust` is satisfied by the qualified bootstrap package's real provider.

## Full Git package result

The pinned recipe completed a genuine `makepkg` build in
`C:\ap10-ca5f\git-full-01`. All 15 original split archives are in its
`packages` directory and each contains `.PKGINFO`, `.BUILDINFO`, and `.MTREE`.
The assembled handoff is `C:\ap10-ca5f\git-full-01\delivery`; its
`git-package-handoff.json` receipt has SHA-256
`a95526e1a07749d2c5964b4d62cd2d13845c84eb3847603cd9c04e463aec52c5`.
The build used Git tag `v2.55.0.windows.5`, commit
`32c4f7689275d233577576630e1ac5b7eb354eb0`, archive SHA-256
`6925371671a574826d17cfb9a085b2cb7a4b7b099341498624c710edee1193f9`,
and makepkg configuration SHA-256
`f92977648dc0c991d281f418e2ff2c4371b904d56323448c1c0c04f092af0a80`.

The independent readback root is `C:\ap10-ca5f\git-readback-02`. An explicit
transaction installed exactly the 14 dependency-complete splits with full
dependency checking and no implicit skipped package. `pacman -Qkk` reports zero
altered files for all 14 Git splits and the native Tcl/Tk providers. Native Git
reports `2.55.0.windows.5`, resolves its relocated `libexec/git-core`, creates
and commits a repository, completes a subtree split, and reaches GitHub over
HTTPS when configured with:

```text
http.sslCAInfo=%(prefix)/etc/ssl/certs/ca-bundle.crt
```

The readback evidence is:

- `C:\ap10-ca5f\git-readback-02\install-14.log`
- `C:\ap10-ca5f\git-readback-02\git-native-readback.json`
- `C:\ap10-ca5f\git-readback-02\p4-install-blocker.log`

The curl provider's CA bundle is canonical-prefix based, but its relocation
anchor was compiled from the private producer bindir. Native callers can supply
`GIT_SSL_CAINFO` as a runtime control, but that does not make the current
`libcurl-4.dll` admissibly relocatable.

## Python provider and exact-15 handoff

The genuine Python provider export is
`C:\ap12-ca5f\python-provider-export-02\export.json`, SHA-256
`ce20122f2773a5ecde625db5cb58849daf8b66c7f7cff750fee8b5e1aa98fff3`.
It contains a 19-package dependency closure with relative archive paths and
unchanged package metadata. The native Python 3.12.9-3 archive has SHA-256
`1d10d98cf681ba8fb9d50853b75520b4f525205ba744e851b77933635c95333e`.
The export is currently superseded because its package list still references
the revoked gettext archive.

The superseding exact-15 Git handoff is
`C:\ap12-ca5f\git-python-handoff-02\git-package-handoff.json`, SHA-256
`947cdb44357f6e6639b0ff87c1b4299f53073477ff9cb5ed8e30b276ed54d911`.
It preserves the prior `a95526e1...` handoff and its 14 unaffected Git
archives byte-for-byte. The corrected `git-p4` archive has SHA-256
`e951434eadf733f6a1831fb8bdb9863387ec3807f4adf45c1cee4e0ea6e56e6d`;
its payload file set and documentation are unchanged, and its script differs
only in the interpreter line.

The private readback root is
`C:\ap12-ca5f\git-python-readback-01`. Pacman resolves every declared Python
closure dependency and reports zero altered files for Python and all 15 Git
splits. Native Python imports `_ssl`, `_sqlite3`, `_decimal`, `_ctypes`,
`_bz2`, `_lzma`, `_curses`, and `_tkinter`; `git p4 sync --help` runs locally
through the installed native Python without contacting Perforce.

## Remaining integration boundary

The final all-native MSYS build driver remains owned by the separate
Coreutils/Bash/runtime lane. This Git build used an isolated x64 MSYS bootstrap
only as the build driver; every delivered Git executable, Python executable,
extension module, and library payload is native ARM64.

Native Tcl 8.6.13 and Tk 8.6.13 packages needed by Git GUI/gitk were built from
`Windows-on-ARM-Experiments/MINGW-packages@f34f6df66a0a06157dd1b09dd1d1e026ce7c903c`.
Their package SHA-256 values are
`72aa94a360986451ae10e52b21624ec8247bbf45a6d6711cbd0fbd19fe08d65e`
and
`a319ebfdbc109f2255d2b76b2512a2bf077bc58ccbd039bc1d20238b01215490`,
respectively.
The Tcl package is not yet an admissibly relocatable operational provider:
`tcl86.dll` SHA-256
`28dfc8ae4069a3fbf31bd461aff0d1c01d9701fe219c70de199b0087943e22d9`
contains private compiled bindir, libdir, scriptdir, includedir, and docdir
values. This requires a separate pinned-source canonical-prefix Tcl rebuild.
The maintained integration deltas are in
`patches/runtime-providers/0001-tcl-mingwarm64-integration.patch` and
`patches/runtime-providers/0002-tk-mingwarm64-integration.patch`. They preserve
stack protection while retaining frame pointers to avoid the GCC ARM64 SEH
assembler failure.

## Explicit package deltas

- The admitted curl variants include HTTP/3 although the pinned curl recipe
  declares only HTTP/2 dependencies. The packages therefore declare their real
  nghttp3/ngtcp2 runtime requirements.
- The admitted OpenSSL-flavored libssh2 imports `libcrypto-3.dll`, while the
  admitted OpenSSL package correctly installs `libcrypto-3-arm64.dll`. The
  exported curl providers use the already-built WinCNG libssh2 payload and add
  the `libssh2.dll` ABI alias required by the admitted curl binaries.
- The admitted prerequisite bundle's zlib package naming was incompatible with
  the curl import (`libz.dll` versus `zlib1.dll`). The export packages the
  admitted `libz.dll` cohort with its headers, import/static libraries, and
  relocatable pkg-config/CMake metadata.
- Absolute-path `.la` files were removed. They contained private build roots and
  are not needed by the validated shared, static, pkg-config, or CMake consumers.
