#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PinnedSourceRoot,
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
$prepare = Join-Path $PSScriptRoot '..\.github\scripts\prepare-python-mingwarm64-stack.ps1'
$commit = 'f34f6df66a0a06157dd1b09dd1d1e026ce7c903c'
$result = & $prepare -SourceRoot $PinnedSourceRoot -OutputRoot $OutputDirectory -PinnedCommit $commit

if ($result.Status -cne 'python-stack-namespace-prepared-not-package-admitted' -or
    $result.PinnedCommit -cne $commit -or
    @($result.Recipes).Count -ne 8) {
    throw 'Python provider stack preparation result is incomplete.'
}

$python = [IO.File]::ReadAllText((Join-Path $OutputDirectory 'mingw-w64-python\PKGBUILD'))
if (-not $python.Contains("'mingwarm64'") -or
    -not $python.Contains('"${MINGW_PACKAGE_PREFIX}-gcc"') -or
    $python.Contains('"${MINGW_PACKAGE_PREFIX}-gcc-libs"') -or
    -not $python.Contains('"mingw-w64-x86_64-autotools"') -or
    -not $python.Contains('PATH="/mingw64/bin:$PATH" autoreconf -vfi') -or
    -not $python.Contains("'6c52a31db51c8dc8146dd365629906ce5915db649aef3f98f89886fc15af9497'")) {
    throw 'Python namespace or dependency mapping is incorrect.'
}
$pythonPgoPatch = Join-Path $OutputDirectory 'mingw-w64-python\0123-mingw-pgo-link.patch'
if (-not (Test-Path -LiteralPath $pythonPgoPatch) -or
    (Get-FileHash -LiteralPath $pythonPgoPatch).Hash.ToLowerInvariant() -cne
        '3d0c3282865dba72cd1dc83276cc09e909524949101f9af41efdc723d52eb3fd' -or
    -not $python.Contains('0123-mingw-pgo-link.patch')) {
    throw 'Python does not carry the hash-bound MinGW PGO link fix.'
}
$pythonPgoPatchText = [IO.File]::ReadAllText($pythonPgoPatch)
if (-not $pythonPgoPatchText.Contains('BLDSHARED=') -or
    -not $pythonPgoPatchText.Contains('@BLDSHARED@ $(PY_LDFLAGS)') -or
    @([regex]::Matches($pythonPgoPatchText, '\$\(LINKCC\) \$\(PY_LDFLAGS\)')).Count -ne 3) {
    throw 'Python PGO fix does not isolate profile-runtime linking to libpython.'
}
if (-not $python.Contains('local _check_library_path="$PWD${LIBRARY_PATH:+:$LIBRARY_PATH}"') -or
    @([regex]::Matches($python, 'LIBRARY_PATH="\$\{_check_library_path\}"')).Count -ne 2) {
    throw 'Python in-tree extension smoke tests cannot locate the freshly built import library.'
}
if (-not $python.Contains('_build_prefix_native="$(cygpath -am "${MINGW_PREFIX}")"') -or
    -not $python.Contains("prependdir='`${MINGW_PREFIX}/lib/python`${_pybasever}'") -or
    -not $python.Contains('strip --strip-debug "${pkgdir}${_installed_config}/python.o"') -or
    -not $python.Contains("MSYS2_ARG_CONV_EXCL='-DPYTHONPATH=;-DPREFIX=;-DEXEC_PREFIX=;-DVPATH=' make Modules/getpath.o") -or
    -not $python.Contains("os.add_dll_directory(r'`${_dependency_bin}')") -or
    @([regex]::Matches($python, '"\$\{_staged_python\}" -I -c "\$\{_staged_check\}"')).Count -ne 2) {
    throw 'Python package metadata is not scrubbed and recompiled for relocation.'
}

$sqlite = [IO.File]::ReadAllText((Join-Path $OutputDirectory 'mingw-w64-sqlite3\PKGBUILD'))
if (-not $sqlite.Contains('"${MINGW_PACKAGE_PREFIX}-wineditline"') -or
    -not $sqlite.Contains('_extra_config+=("--enable-editline" "--disable-readline" "--enable-tcl")') -or
    $sqlite.Contains('--with-readline-') -or
    -not $sqlite.Contains('CPPFLAGS="-I../.. -I../../../sqlite-src-${_amalgamationver}/src -I${MINGW_PREFIX}/include"') -or
    $sqlite.Contains('make quicktest ||')) {
    throw 'SQLite did not retain readline support through the genuine wineditline package.'
}
$sqlitePatch = Join-Path $OutputDirectory 'mingw-w64-sqlite3\0004-wineditline-history-limit.patch'
if (-not (Test-Path -LiteralPath $sqlitePatch) -or
    (Get-FileHash -LiteralPath $sqlitePatch).Hash.ToLowerInvariant() -cne
        '0bb0b1baa910ca500782122c5c594a72d749e4a551a0d2026d95507449163c23' -or
    -not $sqlite.Contains('patch -p1 -i "${srcdir}/0004-wineditline-history-limit.patch"')) {
    throw 'SQLite does not carry the hash-bound wineditline history compatibility fix.'
}

$mpdecimal = [IO.File]::ReadAllText((Join-Path $OutputDirectory 'mingw-w64-mpdecimal\PKGBUILD'))
if (-not $mpdecimal.Contains('checkdepends=("wget" "unzip")')) {
    throw 'mpdecimal is missing the unzip tool required by its upstream check target.'
}
if (-not $mpdecimal.Contains('CXXFLAGS="${CXXFLAGS//-static-libstdc++/}"')) {
    throw 'mpdecimal still duplicates the C++ runtime across its shared-library boundary.'
}
$mpdecimalPatch = Join-Path $OutputDirectory 'mingw-w64-mpdecimal\0001-mingw-dll-thread-context.patch'
if (-not (Test-Path -LiteralPath $mpdecimalPatch) -or
    (Get-FileHash -LiteralPath $mpdecimalPatch).Hash.ToLowerInvariant() -cne
        'd8782982c077ff0d425a83a2e486af3f2f16be4ec8d50ddbdb363b9ba5e4a86e' -or
    -not $mpdecimal.Contains('patch -Np1 -i "${srcdir}/0001-mingw-dll-thread-context.patch"') -or
    -not $mpdecimal.Contains("'d8782982c077ff0d425a83a2e486af3f2f16be4ec8d50ddbdb363b9ba5e4a86e'")) {
    throw 'mpdecimal does not carry the hash-bound MinGW DLL thread-context fix.'
}
$mpdecimalPatchText = [IO.File]::ReadAllText($mpdecimalPatch)
if (-not $mpdecimalPatchText.Contains('defined(__MINGW32__)')) {
    throw 'mpdecimal MinGW DLL thread-context patch is incomplete.'
}

$ncurses = [IO.File]::ReadAllText((Join-Path $OutputDirectory 'mingw-w64-ncurses\PKGBUILD'))
if (-not $ncurses.Contains('https://ftp.gnu.org/gnu/ncurses/${_realname}-${_base_ver}.tar.gz') -or
    -not $ncurses.Contains("'20241228:a48046bc81d926383acd6da582091dbbadf67e71b048de1f0660227c00e95030'") -or
    -not $ncurses.Contains('gzip -cd "${srcdir}/${_realname}-${_base_ver}-${_patch_date}.patch.gz" | patch --binary -p1')) {
    throw 'ncurses does not reconstruct the retained signed 6.5-20241228 source state.'
}

$xz = [IO.File]::ReadAllText((Join-Path $OutputDirectory 'mingw-w64-xz\PKGBUILD'))
if (-not $xz.Contains('"mingw-w64-x86_64-doxygen"') -or
    @([regex]::Matches($xz, 'PATH="/mingw64/bin:\$PATH"')).Count -lt 3) {
    throw 'XZ documentation generation is not isolated to the build-only x64 prefix.'
}

'PASS: pinned Python provider stack maps to truthful MINGWARM64 package identities'
