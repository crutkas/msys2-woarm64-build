#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Identities,
    [Parameter(Mandatory)][string] $Proof,
    [Parameter(Mandatory)][string] $CacheHandoff,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $CacheDirectory,
    [string] $NativePython,
    [switch] $NoCompile
)

$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new native-control output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$outside = Join-Path $output 'hostile-destinations'
$destinations = @{
    BUILDDIR = "$outside\build"; SRCDEST = "$outside\sources"; SRCPKGDEST = "$outside\source-packages"
    LOGDEST = "$outside\logs"; PKGDEST = "$outside\packages"
}
foreach ($path in $destinations.Values) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    [IO.File]::WriteAllText("$path\sentinel", 'outside fresh invocation; must not change')
}
$packageName = if ($NoCompile) { 'woarm64-adapter-control' } else { 'woarm64-native-pipeline-probe' }
$cleanTarget = "$outside\build\$packageName\src"
New-Item -ItemType Directory -Path $cleanTarget -Force | Out-Null
[IO.File]::WriteAllText("$cleanTarget\sentinel", 'must survive cleanbuild')

function Get-Sentinels {
    @(Get-ChildItem -LiteralPath $outside -File -Recurse | Sort-Object FullName | ForEach-Object {
        @{ Path = $_.FullName; SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    }) | ConvertTo-Json -Compress
}
$before = Get-Sentinels
$saved = @{}
foreach ($name in @($destinations.Keys) + 'RUN_CHECK') {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$arguments = @{
    MsysRoot = $MsysRoot; Prefix = $Prefix; Identities = $Identities; Proof = $Proof; CacheHandoff = $CacheHandoff
    PackageDirectory = Join-Path $PSScriptRoot $(if ($NoCompile) { 'package-controls' } else { 'native-package' })
    OutputDirectory = Join-Path $output 'invocation'
    CacheDirectory = $CacheDirectory
    Jobs = 1
}
if ($NativePython) { $arguments.NativePython = $NativePython }
try {
    foreach ($name in $destinations.Keys) { [Environment]::SetEnvironmentVariable($name, $destinations[$name], 'Process') }
    $env:RUN_CHECK = 'n'
    $results = @(& "$PSScriptRoot\..\.github\scripts\invoke-native-package.ps1" @arguments)
    if ($results.Count -ne 1 -or $results[0].Status -ne 'passed') { throw 'Native adapter did not return one passing result.' }
    $log = [IO.File]::ReadAllText("$output\invocation\build.log")
    if ($log -notmatch '==> Starting check\(\)' -or
        (-not $NoCompile -and $log -notmatch 'PASS: native ARM64 C/C\+\+ package executable reached main') -or
        ($NoCompile -and -not (Test-Path -LiteralPath "$output\invocation\check-reached"))) {
        throw 'Requested native recipe check was not executed.'
    }
    $after = Get-Sentinels
    if ($before -cne $after) { throw 'Native adapter changed files outside its fresh invocation.' }
    foreach ($directory in 'build', 'sources', 'source-packages', 'logs', 'packages') {
        if (-not (Test-Path -LiteralPath "$output\invocation\$directory" -PathType Container)) {
            throw "Invocation destination missing: $directory"
        }
    }
    [ordered]@{
        Status = 'passed'
        Jobs = 1
        CompilationPerformed = -not $NoCompile
        CheckRequested = $true
        HostileRunCheck = 'n'
        SentinelsBefore = $before | ConvertFrom-Json
        SentinelsAfter = $after | ConvertFrom-Json
        PackageResult = "$output\invocation\result.json"
        PackageResultSHA256 = (Get-FileHash -LiteralPath "$output\invocation\result.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\control-result.json" -Encoding utf8
    "PASS: top-level adapter check executed despite RUN_CHECK=n; outside sentinels unchanged; compilation=$(-not $NoCompile)"
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
