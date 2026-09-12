#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PreparedPackage,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Library input-control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$prepared = Get-Content -Raw -LiteralPath "$PreparedPackage\preparation.json" | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath $prepared.Pins[3].Path | ConvertFrom-Json
$arguments = @{
    Package=$prepared.Package;Prefix=$manifest.Prefix;Manifest=$prepared.Pins[3].Path
    Payload=$prepared.SourcePayload;BuildReceipt=$prepared.Pins[0].Path
    ConsumerReceipt=$prepared.Pins[1].Path;SourceManifest=$prepared.Pins[2].Path
    ConsumerExecutable=(Join-Path "$PreparedPackage\control" $prepared.ConsumerName)
    OutputDirectory="$OutputDirectory\unused"
}
$script = "$PSScriptRoot\..\..\.github\scripts\msys\prepare-library-package.ps1"
foreach ($case in 'existing-output','wrong-producer') {
    $parameters = $arguments.Clone()
    if ($case -eq 'existing-output') {
        $parameters.OutputDirectory = $PreparedPackage
        $expected = 'MSYS library package output must be new.'
    } else {
        $parameters.BuildReceipt = $parameters.ConsumerReceipt
        $expected = "Published MSYS library input changed: $($parameters.BuildReceipt)"
    }
    $rejected = $false
    try { & $script @parameters } catch {
        if ($_.Exception.Message -cne $expected) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Accepted $case" }
    "PASS: rejected $($prepared.Package) $case"
}
if (Test-Path -LiteralPath "$OutputDirectory\unused") { throw 'Rejected library inputs created output.' }
