#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PreparedPackage,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Cygpath input-control root must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$prepared = Get-Content -Raw -LiteralPath "$PreparedPackage\preparation.json" | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath "$PreparedPackage\provenance\sdk-manifest.json" | ConvertFrom-Json
$arguments = @{
    Prefix=$manifest.Prefix;Manifest="$PreparedPackage\provenance\sdk-manifest.json"
    UtilityReceipt=$prepared.Input;OutputDirectory="$OutputDirectory\unused"
}
$prepare = "$PSScriptRoot\..\..\.github\scripts\msys\prepare-cygpath-package.ps1"
foreach ($case in 'existing-output','wrong-receipt') {
    $parameters = $arguments.Clone()
    if ($case -eq 'existing-output') {
        $parameters.OutputDirectory = $PreparedPackage
        $expected = 'Cygpath package preparation must use a new output.'
    } else {
        $parameters.UtilityReceipt = $parameters.Manifest
        $expected = 'Native cygpath receipt differs from the accepted pin.'
    }
    $rejected = $false
    try { & $prepare @parameters } catch {
        if ($_.Exception.Message -cne $expected) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Accepted $case" }
    "PASS: rejected $case"
}
if (Test-Path -LiteralPath "$OutputDirectory\unused") { throw 'Rejected inputs created a package output.' }
