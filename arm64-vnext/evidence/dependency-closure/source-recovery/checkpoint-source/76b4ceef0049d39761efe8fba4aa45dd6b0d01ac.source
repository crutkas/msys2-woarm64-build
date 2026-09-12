#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PreparedPackage,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Input control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$prepared = Get-Content -Raw -LiteralPath "$PreparedPackage\preparation.json" | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath $prepared.Pins[3].Path | ConvertFrom-Json
$arguments = @{
    Prefix=$manifest.Prefix;Manifest=$prepared.Pins[3].Path;Payload=$prepared.SourcePayload
    BuildReceipt=$prepared.Pins[0].Path;ConsumerReceipt=$prepared.Pins[1].Path
    SourceManifest=$prepared.Pins[2].Path;ConsumerExecutable="$PreparedPackage\control\native-crypt-consumer.exe"
    OutputDirectory="$OutputDirectory\unused"
}
$script = "$PSScriptRoot\..\..\.github\scripts\msys\prepare-libxcrypt-package.ps1"
foreach ($case in 'existing-output','wrong-build-receipt','wrong-consumer') {
    $input = $arguments.Clone()
    switch ($case) {
        'existing-output' { $input.OutputDirectory = $PreparedPackage; $message='Libxcrypt package preparation must use a new output.' }
        'wrong-build-receipt' { $input.BuildReceipt=$input.ConsumerReceipt; $message="Published libxcrypt input changed: $($input.BuildReceipt)" }
        'wrong-consumer' { $input.ConsumerExecutable="$PreparedPackage\control\msys-2.0.dll"; $message='Native libxcrypt source-build/runtime-consumer qualification is incomplete or unpaired.' }
    }
    $rejected = $false
    try { & $script @input } catch {
        if ($_.Exception.Message -cne $message) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Accepted $case" }
    "PASS: rejected $case"
}
if (Test-Path -LiteralPath "$OutputDirectory\unused") { throw 'Rejected inputs created package output.' }
