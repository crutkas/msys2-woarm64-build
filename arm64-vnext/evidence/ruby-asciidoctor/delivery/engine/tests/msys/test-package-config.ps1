param([string] $MsysRoot)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\.github\scripts\msys\package-config.ps1"
$text = New-MsysPackageConfigText -NativeBin "/c/native path/it's/bin" -Sysroot '/c/native path/aarch64-pc-cygwin' `
    -OutputRoot '/c/fresh invocation' -Jobs 1
foreach ($line in @('export MSYSTEM=MSYS', 'CARCH=aarch64', 'CHOST=aarch64-pc-cygwin',
    'CC=gcc', 'CXX=g++', 'MAKEFLAGS=-j1', "CFLAGS='-O2 -pipe'",
    'export CMAKE_BUILD_PARALLEL_LEVEL=1', 'export CTEST_PARALLEL_LEVEL=1')) {
    if (-not $text.Contains("$line`n")) { throw "Missing explicit MSYS package setting: $line" }
}
foreach ($pair in @(
    @('BUILDDIR', 'build'), @('SRCDEST', 'sources'), @('SRCPKGDEST', 'source-packages'),
    @('LOGDEST', 'logs'), @('PKGDEST', 'packages')
)) {
    if (-not $text.Contains("export $($pair[0])='/c/fresh invocation/$($pair[1])'")) { throw 'Unconfined destination in config.' }
}
if ($text.Contains('clang') -or $text.Contains('-mms-bitfields') -or $text.Contains('-lcygwin')) {
    throw 'MSYS context must not silently substitute Clang, LLP64 or Cygwin application options.'
}
if (-not $text.Contains("'/c/native path/it'\''s/bin'")) { throw 'Apostrophe in native prefix was not shell-escaped.' }
'PASS: separate MSYS config preserves target, all destinations and quoted prefix'
if ($MsysRoot) {
    $temporary = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($temporary, $text, [Text.UTF8Encoding]::new($false))
        $script = @'
set -eo pipefail
source "$(cygpath -u "$1")"
[[ $CARCH == aarch64 && $CHOST == aarch64-pc-cygwin && $CC == gcc && $CXX == g++ ]]
[[ $MAKEFLAGS == -j1 && $CFLAGS == '-O2 -pipe' ]]
[[ $CMAKE_BUILD_PARALLEL_LEVEL == 1 && $CTEST_PARALLEL_LEVEL == 1 ]]
[[ ${PATH%%:*} == "/c/native path/it's/bin" ]]
[[ $BUILDDIR == '/c/fresh invocation/build' && $SRCDEST == '/c/fresh invocation/sources' ]]
[[ $SRCPKGDEST == '/c/fresh invocation/source-packages' && $LOGDEST == '/c/fresh invocation/logs' ]]
[[ $PKGDEST == '/c/fresh invocation/packages' ]]
[[ $PKG_CONFIG_LIBDIR == '/c/native path/aarch64-pc-cygwin/lib/pkgconfig:/c/native path/aarch64-pc-cygwin/share/pkgconfig' ]]
printf 'PASS: generated config sourced by actual MSYS Bash; no compiler or makepkg executed\n'
'@
        & "$MsysRoot\usr\bin\bash.exe" -lc $script bash $temporary
        if ($LASTEXITCODE -ne 0) { throw 'Generated MSYS config failed in Bash.' }
    } finally {
        Remove-Item -LiteralPath $temporary -Force
    }
}
foreach ($case in @(
    @{ NativeBin = 'relative'; Sysroot = '/sysroot'; OutputRoot = '/output'; Jobs = 1 },
    @{ NativeBin = '/bin'; Sysroot = '/sysroot/../other'; OutputRoot = '/output'; Jobs = 1 },
    @{ NativeBin = "/bin`ncommand"; Sysroot = '/sysroot'; OutputRoot = '/output'; Jobs = 1 },
    @{ NativeBin = '/bin'; Sysroot = '/sysroot'; OutputRoot = '/output'; Jobs = 0 }
)) {
    $rejected = $false
    try { $null = New-MsysPackageConfigText @case } catch {
        if ($_.Exception.Message -notlike 'MSYS package config *') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Invalid config input accepted.' }
    'PASS: invalid MSYS package config rejected'
}
