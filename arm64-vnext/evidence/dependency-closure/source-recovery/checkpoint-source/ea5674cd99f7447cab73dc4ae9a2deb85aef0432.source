#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PinnedRecipe,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = "$PSScriptRoot\..\.github\scripts\prepare-xmlto-msys-recipe.ps1"
$result = & $prepare -SourceDirectory $PinnedRecipe -OutputDirectory $OutputDirectory
$text = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$before = [IO.File]::ReadAllText((Join-Path $PinnedRecipe 'PKGBUILD')).Replace("`r`n", "`n")
$insertion = $text.Substring($text.IndexOf("source+=('0001-explicit-int.patch')"))
$insertion = $insertion.Substring(0, $insertion.IndexOf('build() {'))
if ($text.Replace($insertion, '').Replace('pkgrel=3', 'pkgrel=2') -cne $before -or
    $text.Contains("`r") -or $text.Contains('-Wno-') -or $text.Contains('-std=')) {
    throw 'Unexpected source, feature, compiler-default or line-ending change.'
}
if ((Get-FileHash -LiteralPath "$OutputDirectory\0001-explicit-int.patch").Hash.ToLowerInvariant() -cne $result.Patch.SHA256) {
    throw 'Prepared source patch changed.'
}
'PASS: only versioned explicit-int preparation added; archive/dependencies/defaults preserved'
foreach ($case in 'modified-input', 'existing-output') {
    $arguments = if ($case -eq 'modified-input') {
        @{SourceDirectory=$OutputDirectory;OutputDirectory="$OutputDirectory-rejected"}
    } else { @{SourceDirectory=$PinnedRecipe;OutputDirectory=$OutputDirectory} }
    $expected = if ($case -eq 'modified-input') {
        'Only the pinned xmlto 0.0.28-2 recipe is supported.'
    } else { 'Prepared xmlto recipe output must be new.' }
    $rejected = $false
    try { $null = & $prepare @arguments } catch {
        if ($_.Exception.Message -cne $expected) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Accepted $case" }
    "PASS: rejected $case"
}
