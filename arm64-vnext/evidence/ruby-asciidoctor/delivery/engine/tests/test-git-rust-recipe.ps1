#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PinnedRecipe,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$result = & "$PSScriptRoot\..\.github\scripts\prepare-git-rust-recipe.ps1" -SourceDirectory $PinnedRecipe -OutputDirectory $OutputDirectory
$original = [IO.File]::ReadAllText((Join-Path $PinnedRecipe 'PKGBUILD')).Replace("`r`n","`n")
$prepared = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$restored = $prepared.Replace("'clangarm64' 'mingwarm64'","'clangarm64'").Replace(
    '  source "${startdir}/native-rust-environment.sh" || return 1'+"`n",'').Replace(
    'LDFLAGS = $LDFLAGS $WOARM64_RUST_LDFLAGS'+"`n`t"+'EXTLIBS += $WOARM64_RUST_EXTLIBS','LDFLAGS = $LDFLAGS')
if ($restored -cne $original -or $prepared.Contains("`r")) { throw 'Git preparation changed unrelated recipe behavior.' }
if (([regex]::Matches($prepared,'(?m)^package_git[^ ]* \(\)')).Count -ne 16 -or
    -not $prepared.Contains('"${MINGW_PACKAGE_PREFIX}-rust"') -or
    -not $prepared.Contains('6925371671a574826d17cfb9a085b2cb7a4b7b099341498624c710edee1193f9')) {
    throw 'Pinned Git splits, Rust requirement or original VCS archive checksum changed.'
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$OutputDirectory\preparation-result.json" -Encoding utf8
'PASS: explicit Rust bridge only; all pinned Git splits/features/dependencies/source checks retained'
