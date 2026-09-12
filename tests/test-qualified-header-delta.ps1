#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Header-delta control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$reader = "$PSScriptRoot\..\.github\scripts\test-qualified-header-delta.ps1"
$qualified = & $reader -Prefix $Prefix -Manifest $Manifest
if ($qualified.Epoch -cne '5382e3f64bfd1314f168e2df67ce1abd79f3574acf32538708e7a2c8432fb3b7' -or $qualified.Files.Count -ne 4030) {
    throw 'Wrong qualified header delta.'
}
'PASS: exact source/native delta and complete owned inventory accepted'
$copy = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json -AsHashtable
$copy.Status = 'qualified'
$copy | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath "$OutputDirectory\wrong-status.json" -Encoding utf8
$rejected = $false
try { $null = & $reader -Prefix $Prefix -Manifest "$OutputDirectory\wrong-status.json" } catch {
    if ($_.Exception.Message -cne 'Header-delta manifest differs from the accepted source-owner pin.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Header-only receipt was promoted to another status.' }
'PASS: a changed/promoted header receipt is rejected'
$rejected = $false
try {
    $null = & "$PSScriptRoot\..\.github\scripts\test-qualified-native-cohort.ps1" -Prefix $Prefix -Manifest $Manifest
} catch {
    if ($_.Exception.Message -cne 'Unqualified native MinGW cohort: missing Evidence') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Header delta was accepted as a freshly qualified full cohort.' }
'PASS: old full-cohort route does not reinterpret the header-delta contract'
