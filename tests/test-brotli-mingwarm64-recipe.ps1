#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$null = & "$PSScriptRoot\..\.github\scripts\prepare-brotli-mingwarm64-recipe.ps1" @PSBoundParameters
$before = [IO.File]::ReadAllText("$SourceDirectory\PKGBUILD").Replace("`r`n","`n")
$after = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$old = '${MINGW_PREFIX}/bin/ctest . || warning "Tests failed"'
$new = '${MINGW_PREFIX}/bin/ctest --output-on-failure --no-tests=error --parallel "${WOARM64_JOBS:?}"'
if ([regex]::Matches($after,[regex]::Escape($new)).Count -ne 2 -or
    $after.Replace($new,$old).Replace(" 'mingwarm64')",")") -cne $before) {
    throw 'Brotli source/features/splits changed outside strict test/environment mapping.'
}
'PASS: both Brotli profiles require successful nonempty checks; original source/features/splits preserved'
