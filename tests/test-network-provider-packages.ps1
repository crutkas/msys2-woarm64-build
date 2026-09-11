#requires -Version 7.3
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\.github\scripts\export-network-provider-packages.ps1"

$definitions = @(Get-NetworkPackageDefinitions)
$names = @($definitions.Name)
foreach ($required in @(
    'mingw-w64-aarch64-curl',
    'mingw-w64-aarch64-curl-gnutls',
    'mingw-w64-aarch64-curl-winssl',
    'mingw-w64-aarch64-libssh2',
    'mingw-w64-aarch64-libssh2-wincng',
    'mingw-w64-aarch64-pcre2'
)) {
    if ($required -cnotin $names) { throw "Missing package definition: $required" }
}
if ($names.Count -ne ($names | Sort-Object -Unique).Count) { throw 'Package names must be unique.' }
$gettext = $definitions | Where-Object Name -CEQ 'mingw-w64-aarch64-gettext'
if ('^include/(autosprintf|libintl)\.h$' -cnotin $gettext.Match) {
    throw 'Gettext package must own the public libintl header needed by consumers.'
}
$default = $definitions | Where-Object Name -CEQ 'mingw-w64-aarch64-curl'
$gnutls = $definitions | Where-Object Name -CEQ 'mingw-w64-aarch64-curl-gnutls'
$winssl = $definitions | Where-Object Name -CEQ 'mingw-w64-aarch64-curl-winssl'
if ($default.Provides.Count) { throw 'The canonical curl package must not provide itself.' }
if ('mingw-w64-aarch64-curl=8.22.0' -cnotin $gnutls.Provides -or
    'mingw-w64-aarch64-curl=8.22.0' -cnotin $winssl.Provides) {
    throw 'Alternate TLS packages must implement the pinned recipe provider relationship.'
}
foreach ($variant in $default, $gnutls, $winssl) {
    $otherNames = @($default.Name, $gnutls.Name, $winssl.Name | Where-Object { $_ -cne $variant.Name })
    foreach ($other in $otherNames) {
        if ($other -cne $variant.Name -and $other -cnotin $variant.Conflicts) {
            throw "$($variant.Name) does not conflict with $other"
        }
    }
}

$root = Join-Path $env:TEMP "network-relocation-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path "$root\lib\pkgconfig", "$root\lib\cmake\CURL", "$root\bin" | Out-Null
try {
    @'
prefix=C:/ap08-d207/curl-chain-01/prefix/mingwarm64
libdir=${prefix}/lib
Libs.private: -LC:/ap08-d207/curl-chain-01/prefix/mingwarm64/lib
'@ | Set-Content "$root\lib\pkgconfig\probe.pc" -NoNewline
    @'
set(PACKAGE_PREFIX_DIR unused)
set(PROBE "C:/ap08-d207/curl-chain-01/prefix/mingwarm64/lib/probe.a")
'@ | Set-Content "$root\lib\cmake\CURL\Probe.cmake" -NoNewline
    @'
#!/bin/sh
prefix='C:/ap08-d207/curl-chain-01/variants/openssl/prefix/mingwarm64'
'@ | Set-Content "$root\bin\probe-config" -NoNewline
    Set-RelocatableMetadata $root
    $pc = [IO.File]::ReadAllText("$root\lib\pkgconfig\probe.pc")
    $cmake = [IO.File]::ReadAllText("$root\lib\cmake\CURL\Probe.cmake")
    $config = [IO.File]::ReadAllText("$root\bin\probe-config")
    if ($pc -notmatch [regex]::Escape('prefix=${pcfiledir}/../..') -or
        $pc -notmatch [regex]::Escape('-L${libdir}')) {
        throw 'pkg-config relocation failed.'
    }
    if ($cmake -notmatch [regex]::Escape('${PACKAGE_PREFIX_DIR}/lib/probe.a')) {
        throw 'CMake relocation failed.'
    }
    if ($config -notmatch 'pwd -W' -or $config -match 'ap08-d207') {
        throw 'config script relocation failed.'
    }
} finally {
    Remove-Item -LiteralPath $root -Recurse
}

'PASS: network package definitions preserve exclusive TLS providers and relocate metadata'
