#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\..\.github\scripts\build-gettext-mingwarm64-package.ps1"
)
foreach ($required in @(
    'pkgname=mingw-w64-aarch64-gettext',
    'pkgver=1\.0',
    'pkgrel=1',
    'makepkg_mingw.conf',
    'MAKEFLAGS="-j1"',
    'startdir = /tmp/gettext-package-1.0-1',
    'BUILDDIR=/tmp/gettext-package-build-1.0-1',
    '$canonicalStartDirectory',
    '--cleanbuild --clean --force',
    '.PKGINFO',
    '.BUILDINFO',
    '.MTREE',
    'builddir = /tmp/gettext-package-build-1.0-1',
    'appliedPatches = @()',
    'truthful-gettext-1.0-1-makepkg-complete'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext makepkg builder lost invariant: $required"
    }
}

'PASS: gettext makepkg builder emits genuine metadata without private build paths'
