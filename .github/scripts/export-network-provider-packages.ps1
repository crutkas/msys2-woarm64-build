#requires -Version 7.3
param(
    [string] $CurlChainRoot,
    [string] $PinnedRecipeRoot,
    [string] $OutputDirectory,
    [string] $CaBundle,
    [string] $OpenSslPackage,
    [string] $CaresPackage,
    [string] $BrotliPackage,
    [string] $ExpatPackage,
    [string] $GccPackage,
    [string] $RustPackage,
    [string] $PkgconfPackage,
    [string] $CmakePackage,
    [switch] $Describe
)

$ErrorActionPreference = 'Stop'

function Get-NetworkPackageDefinitions {
    $prefix = 'mingw-w64-aarch64'
    @(
        [ordered]@{
            Name = "$prefix-libiconv"; Version = '1.18-1'; Source = 'prerequisites'
            Description = 'Character set conversion library (mingw-w64)'
            License = @('spdx:LGPL-2.1-or-later', 'spdx:GPL-3.0-or-later')
            Depends = @()
            Match = @(
                '^bin/(iconv\.exe|libcharset-1\.dll|libiconv-2\.dll)$',
                '^include/(iconv\.h|libcharset\.h|localcharset\.h)$',
                '^lib/(charset\.alias|libcharset\..*|libiconv\..*)$',
                '^share/(doc/libiconv/.*|licenses/libiconv/.*|locale/.*/LC_MESSAGES/libiconv\.mo|man/man1/iconv\.1.*|man/man3/iconv.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-gettext"; Version = '0.26-1'; Source = 'prerequisites'
            Description = 'GNU internationalization runtime libraries and tools (mingw-w64)'
            License = @('spdx:GPL-3.0-or-later', 'spdx:LGPL-2.1-or-later')
            Depends = @("$prefix-libiconv")
            Match = @(
                '^bin/(envsubst|gettext|ngettext|printf_gettext|printf_ngettext)(\.exe|\.sh)?$',
                '^bin/lib(asprintf-0|intl-8)\.dll$',
                '^include/(autosprintf|libintl)\.h$',
                '^lib/lib(asprintf|intl)\..*$',
                '^share/(doc/(gettext|libasprintf)/.*|info/gettext.*|licenses/gettext-runtime/.*|locale/.*/LC_MESSAGES/(gettext-runtime|gettext-tools|libasprintf)\.mo|man/man1/(envsubst|gettext|ngettext)\.1.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libunistring"; Version = '1.4-1'; Source = 'prerequisites'
            Description = 'Library for manipulating Unicode strings (mingw-w64)'
            License = @('spdx:LGPL-3.0-or-later')
            Depends = @("$prefix-libiconv")
            Match = @(
                '^bin/libunistring-5\.dll$',
                '^include/(uniconv\.h|unictype\.h|uninorm\.h|unistdio\.h|unistr\.h|unistring/.*|unitypes\.h|uniwbrk\.h|uniwidth\.h|unilbrk\.h)$',
                '^lib/libunistring\..*$',
                '^share/(doc/libunistring/.*|info/libunistring.*|licenses/libunistring/.*|man/man3/.*unistring.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libidn2"; Version = '2.3.8-1'; Source = 'prerequisites'
            Description = 'Internationalized domain name library (mingw-w64)'
            License = @('spdx:GPL-3.0-or-later', 'spdx:LGPL-3.0-or-later')
            Depends = @("$prefix-gettext", "$prefix-libunistring")
            Match = @(
                '^bin/(idn2\.exe|libidn2-0\.dll)$',
                '^include/idn2\.h$',
                '^lib/libidn2.*$',
                '^lib/pkgconfig/libidn2\.pc$',
                '^share/(info/libidn2.*|licenses/libidn2/.*|locale/.*/LC_MESSAGES/libidn2\.mo|man/man1/idn2\.1.*|man/man3/idn2.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libpsl"; Version = '0.21.5-1'; Source = 'prerequisites'
            Description = 'Public suffix list library (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @("$prefix-libidn2", "$prefix-libunistring")
            Match = @(
                '^bin/(libpsl-5\.dll|psl\.exe|psl-make-dafsa)$',
                '^include/libpsl\.h$',
                '^lib/libpsl.*$',
                '^lib/pkgconfig/libpsl\.pc$',
                '^share/(licenses/libpsl/.*|man/man1/psl\.1.*|man/man3/libpsl.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-winpthreads"; Version = '1.0-1'; Source = 'prerequisites'
            Description = 'POSIX threads compatibility library for MinGW-w64'
            License = @('spdx:MIT')
            Depends = @("$prefix-gcc")
            Match = @(
                '^bin/libwinpthread-1\.dll$',
                '^include/(pthread|sched|semaphore)\.h$',
                '^lib/lib(win)?pthread.*$'
            )
        },
        [ordered]@{
            Name = "$prefix-zlib"; Version = '1.3.2-3'; Source = 'prerequisites'
            Description = 'DEFLATE compression library with the admitted libz.dll ABI (mingw-w64)'
            License = @('spdx:Zlib')
            Depends = @()
            Match = @(
                '^bin/libz\.dll$',
                '^include/(zconf|zlib)\.h$',
                '^lib/(libz(\..*)?|cmake/zlib/.*|pkgconfig/zlib\.pc)$',
                '^share/(doc/zlib/.*|licenses/zlib/.*|man/man3/zlib.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-zstd"; Version = '1.5.7-1'; Source = 'prerequisites'
            Description = 'Zstandard compression library (mingw-w64)'
            License = @('spdx:BSD-3-Clause')
            Depends = @()
            Match = @(
                '^bin/(libzstd\.dll|pzstd\.exe|zstd.*\.exe)$',
                '^include/zstd.*\.h$',
                '^lib/(libzstd.*|cmake/zstd/.*|pkgconfig/libzstd\.pc)$',
                '^share/(doc/zstd/.*|licenses/zstd/.*|man/man1/(pzstd|zstd).*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libssh2"; Version = '1.11.1-1'; Source = 'prerequisites'
            Description = 'SSH2 protocol library using OpenSSL (mingw-w64)'
            License = @('spdx:BSD-3-Clause')
            Depends = @("$prefix-openssl", "$prefix-zlib")
            Match = @(
                '^bin/libssh2\.dll$',
                '^include/libssh2.*\.h$',
                '^lib/(libssh2.*|cmake/libssh2/.*|pkgconfig/libssh2\.pc)$',
                '^share/(doc/libssh2/.*|licenses/libssh2/.*|man/man3/libssh2.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-nghttp2"; Version = '1.70.0-1'; Source = 'prerequisites'
            Description = 'HTTP/2 framing layer library (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @("$prefix-openssl", "$prefix-c-ares")
            Match = @(
                '^bin/libnghttp2-14\.dll$',
                '^include/nghttp2/.*',
                '^lib/(libnghttp2.*|cmake/nghttp2/.*|pkgconfig/libnghttp2\.pc)$',
                '^share/(doc/nghttp2/.*|licenses/nghttp2/.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-nghttp3"; Version = '1.18.0-1'; Source = 'prerequisites'
            Description = 'HTTP/3 protocol library (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @()
            Match = @(
                '^bin/libnghttp3-9\.dll$',
                '^include/nghttp3/.*',
                '^lib/(libnghttp3.*|cmake/nghttp3/.*|pkgconfig/libnghttp3\.pc)$',
                '^share/doc/nghttp3/.*'
            )
        },
        [ordered]@{
            Name = "$prefix-ngtcp2"; Version = '1.25.0-1'; Source = 'prerequisites'
            Description = 'IETF QUIC protocol library (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @()
            Match = @(
                '^bin/libngtcp2(-16)?\.dll$',
                '^include/ngtcp2/(ngtcp2|version)\.h$',
                '^lib/(libngtcp2(\.a|\.dll\.a)|cmake/ngtcp2/.*|pkgconfig/libngtcp2\.pc)$',
                '^share/doc/ngtcp2/.*'
            )
        },
        [ordered]@{
            Name = "$prefix-ngtcp2-crypto-openssl"; Version = '1.25.0-1'; Source = 'prerequisites'
            Description = 'ngtcp2 OpenSSL crypto helper (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @("$prefix-ngtcp2", "$prefix-openssl")
            Match = @(
                '^bin/libngtcp2_crypto_ossl-0\.dll$',
                '^include/ngtcp2/ngtcp2_crypto(_ossl)?\.h$',
                '^lib/libngtcp2_crypto_ossl.*$',
                '^lib/pkgconfig/libngtcp2_crypto_ossl\.pc$'
            )
        },
        [ordered]@{
            Name = "$prefix-ngtcp2-crypto-gnutls"; Version = '1.25.0-1'; Source = 'prerequisites'
            Description = 'ngtcp2 GnuTLS crypto helper (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @("$prefix-ngtcp2", "$prefix-gnutls")
            Match = @(
                '^bin/libngtcp2_crypto_gnutls\.dll$',
                '^include/ngtcp2/ngtcp2_crypto_gnutls\.h$',
                '^lib/libngtcp2_crypto_gnutls.*$',
                '^lib/pkgconfig/libngtcp2_crypto_gnutls\.pc$'
            )
        },
        [ordered]@{
            Name = "$prefix-gmp"; Version = '6.3.0-1'; Source = 'prerequisites'
            Description = 'Arbitrary precision arithmetic library (mingw-w64)'
            License = @('spdx:LGPL-3.0-or-later', 'spdx:GPL-2.0-or-later')
            Depends = @()
            Match = @(
                '^bin/libgmp(xx)?-[0-9]+\.dll$',
                '^include/gmp.*\.h$',
                '^lib/libgmp.*$',
                '^lib/pkgconfig/gmp.*\.pc$',
                '^share/info/gmp.*'
            )
        },
        [ordered]@{
            Name = "$prefix-nettle"; Version = '4.0-1'; Source = 'prerequisites'
            Description = 'Low-level cryptographic library (mingw-w64)'
            License = @('spdx:LGPL-3.0-or-later', 'spdx:GPL-2.0-or-later')
            Depends = @("$prefix-gmp")
            Match = @(
                '^bin/(libhogweed-[0-9]+\.dll|libnettle-[0-9]+\.dll|nettle-.*\.exe|pkcs1-conv\.exe|sexp-conv\.exe)$',
                '^include/nettle/.*',
                '^lib/lib(hogweed|nettle).*$',
                '^lib/pkgconfig/(hogweed|nettle)\.pc$',
                '^share/(info/nettle.*|man/man1/(nettle-hash|nettle-lfib-stream|nettle-pbkdf2|pkcs1-conv|sexp-conv)\.1.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libtasn1"; Version = '4.21.0-1'; Source = 'prerequisites'
            Description = 'ASN.1 and DER library (mingw-w64)'
            License = @('spdx:LGPL-2.1-or-later', 'spdx:GPL-3.0-or-later')
            Depends = @("$prefix-gcc")
            Match = @(
                '^bin/(asn1(Coding|Decoding|Parser)\.exe|libtasn1-[0-9]+\.dll)$',
                '^include/libtasn1\.h$',
                '^lib/libtasn1.*$',
                '^lib/pkgconfig/libtasn1\.pc$',
                '^share/(info/libtasn1.*|man/man1/asn1(Coding|Decoding|Parser)\.1.*|man/man3/libtasn1.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libffi"; Version = '3.8.0-1'; Source = 'prerequisites'
            Description = 'Portable foreign function interface library (mingw-w64)'
            License = @('spdx:MIT')
            Depends = @("$prefix-gcc")
            Match = @(
                '^bin/libffi-[0-9]+\.dll$',
                '^include/(ffi\.h|ffitarget\.h|libffi/.*)$',
                '^lib/libffi.*$',
                '^lib/pkgconfig/libffi\.pc$',
                '^share/info/libffi.*'
            )
        },
        [ordered]@{
            Name = "$prefix-p11-kit"; Version = '0.26.5-1'; Source = 'prerequisites'
            Description = 'PKCS#11 module and trust framework (mingw-w64)'
            License = @('spdx:BSD-3-Clause')
            Depends = @("$prefix-gettext", "$prefix-libffi", "$prefix-libtasn1")
            Match = @(
                '^bin/(libp11-kit-0\.dll|p11-kit\.exe|trust\.exe)$',
                '^include/p11-kit-1/.*',
                '^lib/(libp11-kit.*|p11-kit/.*|pkcs11/.*|pkgconfig/p11-kit-1\.pc)$',
                '^share/(locale/.*/LC_MESSAGES/p11-kit\.mo|man/man1/(p11-kit|trust).*|p11-kit/.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-gnutls"; Version = '3.8.13-1'; Source = 'prerequisites'
            Description = 'TLS protocol library (mingw-w64)'
            License = @('spdx:LGPL-2.1-or-later', 'spdx:GPL-3.0-or-later')
            Depends = @(
                "$prefix-gcc", "$prefix-gettext", "$prefix-libidn2", "$prefix-libunistring",
                "$prefix-libtasn1", "$prefix-nettle", "$prefix-p11-kit", "$prefix-winpthreads",
                "$prefix-zlib"
            )
            Match = @(
                '^bin/(certtool|gnutls-.*|ocsptool|p11tool|psktool)\.exe$',
                '^bin/libgnutls.*\.dll$',
                '^include/gnutls/.*',
                '^lib/libgnutls.*$',
                '^lib/pkgconfig/gnutls\.pc$',
                '^share/(doc/gnutls/.*|info/gnutls.*|locale/.*/LC_MESSAGES/gnutls\.mo|man/man1/(certtool|gnutls|ocsptool|p11tool|psktool).*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-pcre2"; Version = '10.48-1'; Source = 'prerequisites'
            Description = 'Perl-compatible regular expression library (mingw-w64)'
            License = @('spdx:BSD-3-Clause')
            Depends = @("$prefix-gcc")
            Match = @(
                '^bin/(libpcre2.*\.dll|pcre2-config|pcre2grep\.exe|pcre2test\.exe)$',
                '^include/pcre2.*\.h$',
                '^lib/(libpcre2.*|cmake/pcre2/.*|pkgconfig/libpcre2.*\.pc)$',
                '^share/(doc/pcre2/.*|licenses/pcre2/.*|man/man1/pcre2.*|man/man3/pcre2.*)$'
            )
        },
        [ordered]@{
            Name = "$prefix-libssh2-wincng"; Version = '1.11.1-1'; Source = 'libssh2-wincng'
            Description = 'SSH2 protocol library using Windows CNG (mingw-w64)'
            License = @('spdx:BSD-3-Clause')
            Depends = @("$prefix-zlib")
            Provides = @("$prefix-libssh2=1.11.1")
            Conflicts = @("$prefix-libssh2")
            Match = @('.*')
        },
        [ordered]@{
            Name = "$prefix-curl"; Version = '8.22.0-1'; Source = 'curl-openssl'
            Description = 'Command line URL transfer tool and library, OpenSSL default (mingw-w64)'
            License = @('spdx:curl')
            Depends = @(
                "$prefix-gcc", "$prefix-ca-certificates", "$prefix-c-ares", "$prefix-brotli",
                "$prefix-libidn2", "$prefix-libpsl", "$prefix-zlib", "$prefix-zstd",
                "$prefix-libssh2-wincng", "$prefix-openssl", "$prefix-nghttp2", "$prefix-nghttp3",
                "$prefix-ngtcp2", "$prefix-ngtcp2-crypto-openssl"
            )
            Conflicts = @("$prefix-curl-gnutls", "$prefix-curl-winssl")
            Match = @('.*')
        },
        [ordered]@{
            Name = "$prefix-curl-gnutls"; Version = '8.22.0-1'; Source = 'curl-gnutls'
            Description = 'Command line URL transfer tool and library, GnuTLS default (mingw-w64)'
            License = @('spdx:curl')
            Depends = @(
                "$prefix-gcc", "$prefix-ca-certificates", "$prefix-c-ares", "$prefix-brotli",
                "$prefix-libidn2", "$prefix-libpsl", "$prefix-zlib", "$prefix-zstd",
                "$prefix-libssh2-wincng", "$prefix-gnutls", "$prefix-nghttp2", "$prefix-nghttp3",
                "$prefix-ngtcp2", "$prefix-ngtcp2-crypto-gnutls"
            )
            Provides = @("$prefix-curl=8.22.0")
            Conflicts = @("$prefix-curl", "$prefix-curl-winssl")
            Match = @('.*')
        },
        [ordered]@{
            Name = "$prefix-curl-winssl"; Version = '8.22.0-1'; Source = 'curl-winssl'
            Description = 'Command line URL transfer tool and library, Schannel default (mingw-w64)'
            License = @('spdx:curl')
            Depends = @(
                "$prefix-gcc", "$prefix-c-ares", "$prefix-brotli", "$prefix-libidn2",
                "$prefix-libpsl", "$prefix-zlib", "$prefix-zstd", "$prefix-libssh2-wincng"
            )
            Provides = @("$prefix-curl=8.22.0")
            Conflicts = @("$prefix-curl", "$prefix-curl-gnutls")
            Match = @('.*')
        }
    )
}

function ConvertTo-RelativePath([string] $Root, [string] $Path) {
    [IO.Path]::GetRelativePath($Root, $Path).Replace('\', '/')
}

function Test-PackageMatch($Definition, [string] $RelativePath) {
    foreach ($pattern in $Definition.Match) {
        if ($RelativePath -cmatch $pattern) { return $true }
    }
    return $false
}

function Set-RelocatableMetadata([string] $Root) {
    $privatePatterns = @(
        'C:/ap08-d207/curl-chain-01/variants/(openssl|gnutls|winssl)/prefix/mingwarm64',
        'C:/ap08-d207/curl-chain-01/dependencies/libssh2-wincng/mingwarm64',
        'C:/ap08-d207/curl-chain-01/prefix/mingwarm64',
        '/c/ap08-d207/curl-chain-01/variants/(openssl|gnutls|winssl)/prefix/mingwarm64',
        '/c/ap08-d207/curl-chain-01/dependencies/libssh2-wincng/mingwarm64',
        '/c/ap08-d207/curl-chain-01/prefix/mingwarm64',
        'C:/Users/crutkasLocal/\.copilot/session-state/[^/]+/files/[^/]+/stage(?:-combined)?',
        '/c/Users/crutkasLocal/\.copilot/session-state/[^/]+/files/[^/]+/stage(?:-combined)?',
        'C:/Users/crutkasLocal/\.copilot/session-state/[^/]+/files/native-empty-dependencies-[^/]+',
        '/c/Users/crutkasLocal/\.copilot/session-state/[^/]+/files/native-empty-dependencies-[^/]+',
        'C:/ap06-2160/.+?/mingwarm64'
    )
    $metadata = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
        $_.Extension -in '.pc', '.cmake', '.la' -or $_.Name -match 'config$'
    })
    foreach ($file in $metadata) {
        $text = [IO.File]::ReadAllText($file.FullName).Replace("`r`n", "`n")
        if ($file.Extension -eq '.pc') {
            $text = [regex]::Replace($text, '(?m)^prefix=.*$', 'prefix=${pcfiledir}/../..')
            foreach ($pattern in $privatePatterns) {
                $text = [regex]::Replace($text, $pattern, '${prefix}')
            }
            $text = [regex]::Replace(
                $text,
                '(?i)-L(?:[A-Z]:|/c)/Users/crutkasLocal/[^\s,''"]+',
                '-L${libdir}'
            )
            $text = $text.Replace('${prefix}/lib-arm64', '${libdir}')
            $text = $text.Replace('-L${prefix}/lib', '-L${libdir}')
        } elseif ($file.Extension -eq '.cmake') {
            $cmakePrefix = if ($text.Contains('_IMPORT_PREFIX')) { '${_IMPORT_PREFIX}' } else { '${PACKAGE_PREFIX_DIR}' }
            foreach ($pattern in $privatePatterns) {
                $text = [regex]::Replace($text, $pattern, $cmakePrefix)
            }
        } else {
            foreach ($pattern in $privatePatterns) {
                $text = [regex]::Replace($text, $pattern, '/mingwarm64')
            }
            if ($file.Extension -eq '.la') {
                $text = [regex]::Replace(
                    $text,
                    '(?i)-L=?(?:[A-Z]:|/c)/Users/crutkasLocal/[^\s''"]+',
                    '-L/mingwarm64/lib'
                )
                $text = [regex]::Replace($text, "(?m)^libdir=.*$", "libdir='/mingwarm64/lib'")
            }
            $text = [regex]::Replace($text, "(?m)^prefix=(['""]?)[^`r`n]*\1$", 'prefix="$(cd "$(dirname "$$0")/.." && pwd -W)"')
            $text = [regex]::Replace($text, "(?m)^\s*echo ['""]C:/ap06-2160/[^'""]+/gcc\.exe['""]$", "    echo 'cc'")
        }
        [IO.File]::WriteAllText($file.FullName, $text, [Text.UTF8Encoding]::new($false))
    }
    $leaks = @($metadata | Select-String -SimpleMatch 'C:/ap08-d207', '/c/ap08-d207', 'C:/ap06-2160', 'C:/Users/crutkasLocal/.copilot/session-state')
    if ($leaks.Count) {
        throw "Private prefix remains in package metadata: $($leaks[0].Path):$($leaks[0].LineNumber)"
    }
}

function New-Mtree([string] $Stage, [string] $Output) {
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add('#mtree')
    $lines.Add('/set type=file uid=0 gid=0 mode=644')
    $lines.Add('./mingwarm64 type=dir mode=755')
    foreach ($directory in Get-ChildItem -LiteralPath "$Stage\mingwarm64" -Recurse -Directory | Sort-Object FullName) {
        $relative = ConvertTo-RelativePath $Stage $directory.FullName
        $lines.Add("./$relative type=dir mode=755")
    }
    foreach ($file in Get-ChildItem -LiteralPath "$Stage\mingwarm64" -Recurse -File | Sort-Object FullName) {
        $relative = ConvertTo-RelativePath $Stage $file.FullName
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $mode = if ($relative -match '(^|/)(bin|lib/p11-kit)/' -and $file.Extension -notin '.dll', '.a', '.pc', '.cmake') { '755' } else { '644' }
        $lines.Add("./$relative size=$($file.Length) sha256digest=$hash mode=$mode")
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($lines -join "`n") + "`n")
    $stream = [IO.File]::Create($Output)
    try {
        $gzip = [IO.Compression.GZipStream]::new($stream, [IO.Compression.CompressionLevel]::SmallestSize)
        try { $gzip.Write($bytes) } finally { $gzip.Dispose() }
    } finally {
        $stream.Dispose()
    }
}

function New-PacmanPackage($Definition, [string] $SourceRoot, [string] $PackagesDirectory, [hashtable] $Ownership) {
    $stage = Join-Path (Split-Path $PackagesDirectory) "stage-$($Definition.Name)"
    if (Test-Path -LiteralPath $stage) { throw "Package stage already exists: $stage" }
    New-Item -ItemType Directory -Path "$stage\mingwarm64" | Out-Null
    $files = @(Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {
        $relative = ConvertTo-RelativePath $SourceRoot $_.FullName
        Test-PackageMatch $Definition $relative
    })
    if (-not $files.Count) { throw "Package has no payload: $($Definition.Name)" }
    foreach ($file in $files) {
        $relative = ConvertTo-RelativePath $SourceRoot $file.FullName
        $key = "$($Definition.Source):$relative"
        if ($Ownership.ContainsKey($key)) {
            throw "Overlapping ownership: $relative ($($Ownership[$key]), $($Definition.Name))"
        }
        $Ownership[$key] = $Definition.Name
        $destination = Join-Path "$stage\mingwarm64" $relative.Replace('/', '\')
        New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }
    if ($Definition.Name -like 'mingw-w64-aarch64-curl*') {
        $license = "$stage\mingwarm64\share\licenses\curl\LICENSE"
        New-Item -ItemType Directory -Path (Split-Path $license) -Force | Out-Null
        Copy-Item -LiteralPath "$CurlChainRoot\src\curl-8.22.0\COPYING" -Destination $license
    } elseif ($Definition.Name -eq 'mingw-w64-aarch64-libssh2-wincng') {
        $license = "$stage\mingwarm64\share\licenses\libssh2-wincng\COPYING"
        New-Item -ItemType Directory -Path (Split-Path $license) -Force | Out-Null
        Copy-Item -LiteralPath "$CurlChainRoot\src\libssh2-1.11.1\COPYING" -Destination $license
        Copy-Item -LiteralPath "$stage\mingwarm64\bin\libssh2-1.dll" -Destination "$stage\mingwarm64\bin\libssh2.dll"
    }
    Get-ChildItem -LiteralPath $stage -Recurse -File -Filter '*.la' | Remove-Item
    Set-RelocatableMetadata $stage
    $size = (Get-ChildItem "$stage\mingwarm64" -Recurse -File | Measure-Object Length -Sum).Sum
    $buildDate = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $pkginfo = [Collections.Generic.List[string]]::new()
    $pkginfo.Add('# Generated by export-network-provider-packages.ps1')
    $pkginfo.Add("pkgname = $($Definition.Name)")
    $pkginfo.Add('pkgbase = mingw-w64-network-providers')
    $pkginfo.Add('xdata = pkgtype=pkg')
    $pkginfo.Add("pkgver = $($Definition.Version)")
    $pkginfo.Add("pkgdesc = $($Definition.Description)")
    $pkginfo.Add('url = https://curl.se/')
    $pkginfo.Add("builddate = $buildDate")
    $pkginfo.Add('packager = Windows on ARM native packaging export')
    $pkginfo.Add("size = $size")
    $pkginfo.Add('arch = any')
    foreach ($license in $Definition.License) { $pkginfo.Add("license = $license") }
    foreach ($dependency in $Definition.Depends) { $pkginfo.Add("depend = $dependency") }
    foreach ($provider in @($Definition.Provides)) { if ($provider) { $pkginfo.Add("provides = $provider") } }
    foreach ($conflict in @($Definition.Conflicts)) { if ($conflict) { $pkginfo.Add("conflict = $conflict") } }
    [IO.File]::WriteAllText("$stage\.PKGINFO", ($pkginfo -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    $buildInfo = @(
        'format = 2',
        "pkgname = $($Definition.Name)",
        "pkgbase = mingw-w64-network-providers",
        "pkgver = $($Definition.Version)",
        'pkgarch = any',
        "packager = Windows on ARM native packaging export",
        "builddate = $buildDate",
        'builddir = /build/network-provider-export',
        "buildenv = !distcc",
        "buildenv = color",
        "buildenv = !ccache",
        "options = staticlibs"
    )
    [IO.File]::WriteAllText("$stage\.BUILDINFO", ($buildInfo -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    New-Mtree $stage "$stage\.MTREE"
    $archive = Join-Path $PackagesDirectory "$($Definition.Name)-$($Definition.Version)-any.pkg.tar.zst"
    & "$env:SystemRoot\System32\tar.exe" --zstd -cf $archive -C $stage .BUILDINFO .MTREE .PKGINFO mingwarm64
    if ($LASTEXITCODE) { throw "Package archive failed: $($Definition.Name)" }
    Remove-Item -LiteralPath $stage -Recurse
    [ordered]@{
        name = $Definition.Name
        version = $Definition.Version
        path = $archive
        sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        files = $files.Count
        bytes = (Get-Item -LiteralPath $archive).Length
        depends = @($Definition.Depends)
        provides = @($Definition.Provides)
        conflicts = @($Definition.Conflicts)
    }
}

function Assert-Hash([string] $Path, [string] $Expected, [string] $Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing $Label`: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $Expected) { throw "$Label hash mismatch: $actual" }
}

function Invoke-NetworkPackageExport {
    foreach ($value in $CurlChainRoot, $PinnedRecipeRoot, $OutputDirectory, $CaBundle, $OpenSslPackage, $CaresPackage, $BrotliPackage, $ExpatPackage, $GccPackage, $RustPackage, $PkgconfPackage, $CmakePackage) {
        if ([string]::IsNullOrWhiteSpace($value)) { throw 'All export inputs are required.' }
    }
    if (Test-Path -LiteralPath $OutputDirectory) { throw 'Network package export output must be new.' }
    Assert-Hash "$CurlChainRoot\admission-01\admission.json" '64e5be9d2a93c3055ce3a00ae19fe05ea2547da243d982da56fb2f8eda726677' 'curl admission'
    Assert-Hash "$PinnedRecipeRoot\mingw-w64-curl\PKGBUILD" '1af43e24c3e375b084c2149f986b5e53e9f7c3bc5bf80ed8c40054f253b07ff3' 'pinned curl recipe'
    Assert-Hash $CaBundle '8b347435463fdfb8400da4599d2e1af448ae8426ca7546c417aa289cb1c61bfa' 'pinned CA bundle'
    Assert-Hash $OpenSslPackage '256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3' 'OpenSSL package'
    Assert-Hash $CaresPackage '71ffa79442d0acc49028409b21f922a9c5503dd0ceecabe8fb87fa280e4dfc8d' 'c-ares package'
    Assert-Hash $BrotliPackage '68a6ae38da6cc8fd8d39c581c7836eaf33de52244278e79dd6d93135f3b347f5' 'Brotli package'
    Assert-Hash $ExpatPackage 'e75f9453add9836c825a8f4538833e196f4272f52b5f8a89a1ed45fed1c0b6e8' 'Expat package'
    Assert-Hash $GccPackage 'c14621b131cdefe62a8400b61c9267047a021889b78e718df9ff9a5471e59b9b' 'GCC package'
    Assert-Hash $RustPackage 'b5046f576f4410568dfcb97360f2cb10961312cf4aae75b0a275a1182cc667d5' 'Rust package'
    Assert-Hash $PkgconfPackage '53b6168e15af14520cd170a06f301e8a199a6e4e5efa01d4987409b586e928fe' 'pkgconf package'
    Assert-Hash $CmakePackage '0687be90b8bf508e2d8a9df8ae8bc2b63199c6950888a938ed5a2eab5c7606bc' 'CMake package'
    foreach ($binding in @(
        @{ Path = "$CurlChainRoot\packages\curl-8.22.0-openssl-mingwarm64.tar.zst"; Hash = '6a2b925d03521abd149d3552e44eaff3ca001ad4f15c589a9e149be99460b5d9' },
        @{ Path = "$CurlChainRoot\packages\curl-8.22.0-gnutls-mingwarm64.tar.zst"; Hash = '2bc7af46166a454747bd005461c43aa49f299c735664bdd2dd5c15eba9eec419' },
        @{ Path = "$CurlChainRoot\packages\curl-8.22.0-winssl-mingwarm64.tar.zst"; Hash = '678c559ef4fadaa8623808be304833e7c553112d3d81a7ce4e816a8faeb0fa29' },
        @{ Path = "$CurlChainRoot\packages\curl-native-prerequisites-20260908-mingwarm64.tar.zst"; Hash = '91313296f0158e1d5416c85eafe0bfcf66867afac7fea181abb7b63928ad70f0' },
        @{ Path = "$CurlChainRoot\packages\libssh2-1.11.1-wincng-mingwarm64.tar.zst"; Hash = '4bf84ba7ae159596f24d0aa875db6ec55c1671c7e84c4865bb11353d29ace5ff' }
    )) {
        Assert-Hash $binding.Path $binding.Hash 'admitted payload'
    }
    New-Item -ItemType Directory -Path "$OutputDirectory\packages" -Force | Out-Null
    $sources = @{
        prerequisites = "$CurlChainRoot\prefix\mingwarm64"
        'libssh2-wincng' = "$CurlChainRoot\dependencies\libssh2-wincng\mingwarm64"
        'curl-openssl' = "$CurlChainRoot\variants\openssl\prefix\mingwarm64"
        'curl-gnutls' = "$CurlChainRoot\variants\gnutls\prefix\mingwarm64"
        'curl-winssl' = "$CurlChainRoot\variants\winssl\prefix\mingwarm64"
    }
    $ownership = @{}
    $packages = [Collections.Generic.List[object]]::new()
    foreach ($definition in Get-NetworkPackageDefinitions) {
        $packages.Add((New-PacmanPackage $definition $sources[$definition.Source] "$OutputDirectory\packages" $ownership))
    }
    $caDefinition = [ordered]@{
        Name = 'mingw-w64-aarch64-ca-certificates'; Version = '20180409-5'
        Description = 'Common CA certificates for the MINGWARM64 prefix'
        License = @('spdx:MPL-2.0', 'spdx:GPL-2.0-or-later')
        Depends = @()
    }
    $caStage = "$OutputDirectory\ca-stage"
    New-Item -ItemType Directory -Path "$caStage\mingwarm64\etc\ssl\certs", "$caStage\mingwarm64\ssl\certs" | Out-Null
    Copy-Item -LiteralPath $CaBundle -Destination "$caStage\mingwarm64\etc\ssl\certs\ca-bundle.crt"
    Copy-Item -LiteralPath $CaBundle -Destination "$caStage\mingwarm64\ssl\certs\ca-bundle.crt"
    $caSource = "$OutputDirectory\ca-source"
    Move-Item -LiteralPath "$caStage\mingwarm64" -Destination $caSource
    Remove-Item -LiteralPath $caStage
    $caDefinition.Source = 'ca-certificates'
    $caDefinition.Match = @('.*')
    $packages.Add((New-PacmanPackage $caDefinition $caSource "$OutputDirectory\packages" $ownership))
    Remove-Item -LiteralPath $caSource -Recurse
    foreach ($reused in @(
        @{ Name = 'openssl'; Path = $OpenSslPackage },
        @{ Name = 'c-ares'; Path = $CaresPackage },
        @{ Name = 'brotli'; Path = $BrotliPackage },
        @{ Name = 'expat'; Path = $ExpatPackage },
        @{ Name = 'gcc'; Path = $GccPackage },
        @{ Name = 'rust'; Path = $RustPackage },
        @{ Name = 'pkgconf'; Path = $PkgconfPackage },
        @{ Name = 'cmake'; Path = $CmakePackage }
    )) {
        $destination = Join-Path "$OutputDirectory\packages" (Split-Path -Leaf $reused.Path)
        Copy-Item -LiteralPath $reused.Path -Destination $destination
        $packages.Add([ordered]@{
            name = $reused.Name
            path = $destination
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            reused_unchanged = $true
        })
    }
    $receipt = [ordered]@{
        schema = 1
        status = 'relocatable-native-network-packages-exported'
        generated_utc = [DateTime]::UtcNow.ToString('o')
        target = 'MINGWARM64/aarch64-w64-mingw32'
        pinned_recipe = @{
            commit = 'd65b87de173ac2209a63cef8c4528669b5571fd3'
            curl_recipe_sha256 = '1af43e24c3e375b084c2149f986b5e53e9f7c3bc5bf80ed8c40054f253b07ff3'
        }
        immutable_admission = @{
            path = "$CurlChainRoot\admission-01\admission.json"
            sha256 = '64e5be9d2a93c3055ce3a00ae19fe05ea2547da243d982da56fb2f8eda726677'
        }
        packages = $packages
        ownership_entries = $ownership.Count
        variant_policy = 'Mutually exclusive curl/OpenSSL, curl/GnuTLS, and curl/Schannel packages; no overlay layout'
        known_recipe_delta = @(
            'The pinned curl recipe declares HTTP/2 only; admitted OpenSSL and GnuTLS payloads also contain HTTP/3 and therefore carry explicit nghttp3/ngtcp2 dependencies.',
            'The native GCC provider is intentionally depended on directly because the qualified native compiler is not split into a separate gcc-libs package.',
            'The admitted curl binaries import libz.dll, so the export uses the hash-bound admitted zlib payload rather than the incompatible reusable zlib1.dll package.',
            'The admitted OpenSSL libssh2 imports an unavailable libcrypto-3.dll name; curl variants therefore use the admitted WinCNG libssh2 ABI, exported with its native libssh2-1.dll plus a libssh2.dll runtime alias.',
            'CA certificate data is exported as a separate static-bundle provider and is never folded into curl or OpenSSL; update-ca-trust tooling is outside this export.'
        )
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$OutputDirectory\export.json" -Encoding utf8
    $receipt
}

if ($Describe) {
    Get-NetworkPackageDefinitions | ConvertTo-Json -Depth 8
} elseif ($MyInvocation.InvocationName -ne '.') {
    Invoke-NetworkPackageExport
}
