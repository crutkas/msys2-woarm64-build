# Native ARM64 network provider handoff

## Deliverable

The installable package repository is:

`C:\ap09-ca5f\curl-packages-v2\export-11\packages`

Its receipt is `C:\ap09-ca5f\curl-packages-v2\export-11\export.json` with SHA-256
`96769baea2ea7dfa7ce32f915314c3057ca2b949c30389b51ce82ea57226e8d0`.
The export contains 34 real pacman packages. Every package has `.PKGINFO`,
`.BUILDINFO`, and `.MTREE`; the original admitted payload archives are unchanged.

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

## Git recipe integration

Prepare the pinned 15-split recipe without altering its source:

```powershell
.\.github\scripts\prepare-git-mingwarm64-recipe.ps1 `
  -SourceDirectory C:\ap06-2160\gitpkg01\recipe\mingw-w64-git `
  -OutputDirectory C:\private-new-root\mingw-w64-git
```

The maintained patch adds only `mingwarm64` to `mingw_arch`. It preserves the
tag, source checksums, all package functions, Rust use, documentation targets,
and PDB behavior. The mapped environment is:

| Variable | Value |
|---|---|
| `MSYSTEM` | `MINGWARM64` |
| `MINGW_PREFIX` | `/mingwarm64` |
| `MINGW_PACKAGE_PREFIX` | `mingw-w64-aarch64` |
| `CC` | `gcc` |
| target | `aarch64-w64-mingw32` |

The tested prepared recipe is
`C:\ap09-ca5f\curl-packages-v2\git-recipe-test-01\mapped\PKGBUILD`, SHA-256
`a4cf673b18cd0ee367a14b08e549c0f921f661642b80d1ca597bea9ebb41c733`.

## Git prerequisites closed

The private canonical pacman root resolves these exact Git recipe dependencies:

- `mingw-w64-aarch64-curl`
- `mingw-w64-aarch64-openssl`
- `mingw-w64-aarch64-c-ares`
- `mingw-w64-aarch64-expat`
- `mingw-w64-aarch64-pcre2`
- `mingw-w64-aarch64-cc`
- `mingw-w64-aarch64-rust`
- `mingw-w64-aarch64-ca-certificates`

`cc` is satisfied by the qualified native GCC package, which intentionally
provides `mingw-w64-aarch64-cc`; it is not disguised as a fabricated `gcc-libs`
split. `rust` is satisfied by the qualified bootstrap package's real provider.

## Remaining full-build blockers

The networking lane does not claim the complete Git build is ready. The pinned
recipe still needs:

- a genuine `mingw-w64-aarch64-asciidoctor` package;
- MSYS-side `git`, `openssh`, `ca-certificates`, `xmlto`, `docbook-xsl`, and
  `docbook-xsl-ns`, plus the ordinary makepkg/base-devel host tools;
- the separately owned native Coreutils/Bash build-workflow lane;
- the separately owned native `msys2-runtime` `/dev/urandom` lane.

Do not rename a host MSYS package into the MINGW namespace and do not treat raw
payload files as installed dependencies. The full 15-split Git build should be
launched only after those remaining package identities and runtime facilities
are present in a fresh owned integration root.

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
