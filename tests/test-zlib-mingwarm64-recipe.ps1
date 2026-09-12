#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$result = & "$PSScriptRoot\..\.github\scripts\prepare-zlib-mingwarm64-recipe.ps1" @PSBoundParameters -BootstrapAutotools -BootstrapMsysGenerators
$before = [IO.File]::ReadAllText("$SourceDirectory\PKGBUILD").Replace("`r`n","`n")
$after = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  "${srcdir}/${_realname}-${pkgver}/contrib/minizip/configure" \
'@
$dependencyFlags = $dependencyFlags.Replace("`r`n","`n")
$direct = "'autoconf' 'automake' 'make' 'libtool' " + '"${MINGW_PACKAGE_PREFIX}-pkgconf"'
$reversed = $after.Replace("'1165.patch'",'https://patch-diff.githubusercontent.com/raw/madler/zlib/pull/1165.patch').
    Replace('build-${MSYSTEM}/contrib/minizip','build-mz-${MSYSTEM}').
    Replace($dependencyFlags,'  ../${_realname}-${pkgver}/contrib/minizip/configure \').
    Replace($direct,'"${MINGW_PACKAGE_PREFIX}-autotools"').Replace(" 'mingwarm64')",")")
if ($reversed -cne $before -or $result.BootstrapMsysGenerators -ne $true) {
    throw 'Zlib source/features/checks/install changed outside the declared source/layout/generator repair.'
}
if ((Get-FileHash -LiteralPath "$OutputDirectory\1165.patch").Hash.ToLowerInvariant() -cne
    '0774e1368851504115f732f66230ca4a8a9cd60d4ba014502f65cc19b0b4d8bc') {
    throw 'Zlib patch identity changed.'
}
'PASS: exact original zlib patch bytes and all split/features/checks preserved'
