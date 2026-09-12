#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PinnedRecipe,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = Join-Path $PSScriptRoot '..\.github\scripts\prepare-expat-mingwarm64-recipe.ps1'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$result = & $prepare -SourceDirectory $PinnedRecipe -OutputDirectory "$OutputDirectory\mapped"
$before = [IO.File]::ReadAllText((Join-Path $PinnedRecipe 'PKGBUILD'))
$after = [IO.File]::ReadAllText("$OutputDirectory\mapped\PKGBUILD")
$restored = $after.Replace("'clangarm64' 'mingwarm64'", "'clangarm64'").Replace(
    'ctest --test-dir build-${MSYSTEM} --output-on-failure',
    'ctest --test-dir build-${MSYSTEM} --output-on-failure || true')
if ($before.Replace("`r`n", "`n") -cne $restored) { throw 'Unexpected recipe changes.' }
'PASS: namespace and strict check only; signatures, dependencies, shared/static features preserved'
foreach ($case in 'modified-input', 'existing-output') {
    $arguments = if ($case -eq 'modified-input') {
        @{SourceDirectory="$OutputDirectory\mapped";OutputDirectory="$OutputDirectory\rejected"}
    } else {
        @{SourceDirectory=$PinnedRecipe;OutputDirectory="$OutputDirectory\mapped"}
    }
    $message = if ($case -eq 'modified-input') {
        'Only the pinned Expat 2.8.4-2 recipe is supported by this mapping.'
    } else { 'Prepared Expat recipe output must be new.' }
    $rejected = $false
    try { $null = & $prepare @arguments } catch {
        if ($_.Exception.Message -cne $message) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Accepted $case" }
    "PASS: rejected $case"
}
$result | ConvertTo-Json | Set-Content -LiteralPath "$OutputDirectory\result.json" -Encoding utf8
