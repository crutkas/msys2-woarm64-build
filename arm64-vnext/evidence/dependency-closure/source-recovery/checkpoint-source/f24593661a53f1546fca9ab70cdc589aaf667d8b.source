param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$reader = Join-Path $PSScriptRoot '..\.github\scripts\test-qualified-native-cohort.ps1'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$json = [IO.File]::ReadAllText($Manifest)
$positive = & $reader -Prefix $Prefix -Manifest $Manifest
if ($positive.Inputs.Count -eq 0) { throw 'Positive control did not bind real inputs.' }
'PASS: actual new cohort proof and full inventory bound'
foreach ($case in @(
    @{ Name = 'unqualified-status'; Field = 'Status'; Value = 'staged' },
    @{ Name = 'wrong-target'; Field = 'Target'; Value = 'aarch64-pc-cygwin' },
    @{ Name = 'wrong-epoch'; Field = 'Epoch'; Value = '0' * 64 }
)) {
    $invalid = $json | ConvertFrom-Json -AsHashtable
    $invalid[$case.Field] = $case.Value
    $path = Join-Path $OutputDirectory "$($case.Name).json"
    $invalid | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $path -Encoding utf8
    $rejected = $false
    try { $null = & $reader -Prefix $Prefix -Manifest $path } catch {
        if ($_.Exception.Message -notlike 'Unqualified native MinGW cohort:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Invalid contract accepted: $($case.Name)" }
    "PASS: $($case.Name) rejected"
}
foreach ($case in @(
    @{ Name = 'failed-cache-proof'; Proof = 'Cache'; Mutate = { param($p) $p.Passed = $false } },
    @{ Name = 'missing-cxx-run'; Proof = 'Native'; Mutate = { param($p) $p.Runs = @($p.Runs | Where-Object { $_.Name -ne 'cxx-execute' }) } },
    @{ Name = 'wrong-selected-libgcc'; Proof = 'Cache'; Mutate = { param($p) $p.Library.SHA256 = '0' * 64 } },
    @{ Name = 'weakened-seh-flags'; Proof = 'Seh'; Mutate = { param($p) $p.Options = @($p.Options | Where-Object { $_ -ne '-fstack-protector-strong' }) } }
)) {
    $invalid = $json | ConvertFrom-Json -AsHashtable
    $proof = Get-Content -Raw -LiteralPath $invalid.Evidence[$case.Proof].Path | ConvertFrom-Json -AsHashtable
    $null = & $case.Mutate $proof
    $proofPath = Join-Path $OutputDirectory "$($case.Name)-proof.json"
    $proof | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $proofPath -Encoding utf8
    $invalid.Evidence[$case.Proof] = @{ Path = $proofPath; SHA256 = (Get-FileHash -LiteralPath $proofPath).Hash.ToLowerInvariant() }
    $path = Join-Path $OutputDirectory "$($case.Name).json"
    $invalid | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $path -Encoding utf8
    $rejected = $false
    try { $null = & $reader -Prefix $Prefix -Manifest $path } catch {
        if ($_.Exception.Message -notlike 'Unqualified native MinGW cohort:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Invalid proof accepted: $($case.Name)" }
    "PASS: $($case.Name) rejected"
}
