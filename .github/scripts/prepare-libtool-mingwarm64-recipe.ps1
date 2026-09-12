#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath (Join-Path $SourceDirectory 'PKGBUILD')).Hash.ToLowerInvariant() -cne
    '72d2d8d5d80a83c71f26a28aa90e3ae8335e4551446674c3725f81c8fbf09a00') {
    throw 'Only the pinned libtool 2.6.2-1 recipe is supported.'
}
$result = & "$PSScriptRoot\prepare-pinned-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path)
$permissive = 'make check -k || warning "Tests failed"'
if ([regex]::Matches($text,[regex]::Escape($permissive)).Count -ne 1) { throw 'Unexpected pinned libtool check structure.' }
$guard = Join-Path $PSScriptRoot 'assert-libtool-path-budget.sh'
$guardHash = (Get-FileHash -LiteralPath $guard).Hash.ToLowerInvariant()
Copy-Item -LiteralPath $guard -Destination (Join-Path $OutputDirectory 'assert-libtool-path-budget.sh')
$relayPatch = Join-Path $PSScriptRoot 'patch-libtool-native-tests.py'
$relayPatchHash = (Get-FileHash -LiteralPath $relayPatch).Hash.ToLowerInvariant()
Copy-Item -LiteralPath $relayPatch -Destination (Join-Path $OutputDirectory 'patch-libtool-native-tests.py')
$prepare = @'
source+=('assert-libtool-path-budget.sh')
sha256sums+=('@GUARD_SHA256@')
source+=('patch-libtool-native-tests.py')
sha256sums+=('@RELAY_PATCH_SHA256@')

prepare() {
  bash "$srcdir/assert-libtool-path-budget.sh" "$srcdir/libtool-${pkgver}"
  MSYS2_ARG_CONV_EXCL='*' "$(cygpath -u "${WOARM64_NATIVE_PYTHON:?}")" -I -B \
    "$(cygpath -am "$srcdir/patch-libtool-native-tests.py")" "$(cygpath -am "$srcdir/libtool-${pkgver}")"
'@
if ([regex]::Matches($text,[regex]::Escape('prepare() {')).Count -ne 1) { throw 'Unexpected pinned libtool preparation structure.' }
$strictCheck = @'
local jobs=${WOARM64_JOBS:-1}
  [[ $jobs =~ ^[1-9][0-9]*$ && $jobs -le 16 ]] || return 1
  export WOARM64_NATIVE_EXEC
  WOARM64_NATIVE_EXEC=$(cygpath -u "${WOARM64_NATIVE_EXEC:?}")
  MAKEFLAGS=-j1 make -j1 check -k TESTSUITEFLAGS="-j$jobs"
'@
$prepare = $prepare.Replace('@GUARD_SHA256@',$guardHash).Replace('@RELAY_PATCH_SHA256@',$relayPatchHash)
$text = $text.Replace($permissive,$strictCheck).Replace('prepare() {',$prepare).Replace("`r`n","`n")
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'namespace-and-strict-check-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.Change = 'Declare MINGWARM64, preserve raw native test exits without changing expected assertions, propagate test failures, bound parallel test groups with serial nested make, and reject unsafe nested DESTDIR lengths'
$result.Preserved = 'Pinned version/source/signatures/patches, native libtool/libltdl splits and build/install features'
$result
