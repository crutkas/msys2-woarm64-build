#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $CohortManifest,
    [Parameter(Mandatory)][string] $PackageDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $CacheDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Signature control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
Copy-Item -LiteralPath $PackageDirectory -Destination "$OutputDirectory\recipe" -Recurse
$signatures = @(Get-ChildItem -LiteralPath "$OutputDirectory\recipe" -Filter '*.asc' -File)
if ($signatures.Count -ne 1) { throw 'The control requires exactly one declared detached source signature.' }
[IO.File]::WriteAllText($signatures[0].FullName, "Deliberately invalid detached signature.`n")
$arguments = @{
    MsysRoot=$MsysRoot;Prefix=$Prefix;CohortManifest=$CohortManifest
    PackageDirectory="$OutputDirectory\recipe";OutputDirectory="$OutputDirectory\invocation"
    CacheDirectory=$CacheDirectory;Jobs=1
}
$saved = $env:VERIFY_SOURCE_SIGNATURES
try {
    $env:VERIFY_SOURCE_SIGNATURES = '0'
    $rejected = $false
    try { $null = & "$PSScriptRoot\..\.github\scripts\invoke-native-package.ps1" @arguments } catch {
        if ($_.Exception.Message -notlike 'Package build failed (*)*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Invalid source signature was admitted.' }
    $result = Get-Content -Raw -LiteralPath "$OutputDirectory\invocation\result.json" | ConvertFrom-Json
    $log = [IO.File]::ReadAllText("$OutputDirectory\invocation\build.log")
    if ($result.VerifySourceSignatures -ne $true -or $result.Status -cne 'failed' -or $result.ExitCode -eq 0 -or
        $log -notmatch 'Verifying source file signatures' -or $log -notmatch 'PGP signatures could not be verified' -or
        $log -match '==> Starting (prepare|build|check|package)\(\)') {
        throw 'Failure was not a fail-closed pre-build source-signature rejection.'
    }
    if (@(Get-ChildItem -LiteralPath "$OutputDirectory\invocation\packages" -Filter '*.pkg.tar.*' -File).Count) {
        throw 'Rejected signature produced a package.'
    }
    [ordered]@{
        Status='passed';InvalidSignatureRejected=$true;InheritedBypassRejected=$true
        CompilationPerformed=$false;MakepkgExitCode=$result.ExitCode
        Result="$OutputDirectory\invocation\result.json";Log="$OutputDirectory\invocation\build.log"
    } | ConvertTo-Json | Set-Content -LiteralPath "$OutputDirectory\control-result.json" -Encoding utf8
    'PASS: actual makepkg rejects invalid signature before build despite inherited bypass request'
} finally { $env:VERIFY_SOURCE_SIGNATURES = $saved }
