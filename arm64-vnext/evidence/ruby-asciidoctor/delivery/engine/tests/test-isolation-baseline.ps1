#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $BaselineSource,
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Identities,
    [Parameter(Mandatory)][string] $Proof,
    [Parameter(Mandatory)][string] $CacheHandoff,
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'The destructive-behavior control requires a fresh, dedicated output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$outside = Join-Path $output 'controlled-shared-tree'
$sentinel = "$outside\build\woarm64-adapter-control\src\sentinel"
New-Item -ItemType Directory -Path (Split-Path $sentinel) -Force | Out-Null
[IO.File]::WriteAllText($sentinel, 'Only this test-owned sentinel is expected to be deleted by version 1.')
$values = @{
    BUILDDIR = "$outside\build"; SRCDEST = "$outside\sources"; SRCPKGDEST = "$outside\source-packages"
    LOGDEST = "$outside\logs"; PKGDEST = "$outside\packages"
}
foreach ($path in $values.Values) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
$values.CONTROL_OUTPUT = (& "$MsysRoot\usr\bin\cygpath.exe" -u "$output\invocation").Trim()
$values.GIT_DIR = (& git -C "$PSScriptRoot\.." rev-parse --absolute-git-dir).Trim()
$values.GIT_WORK_TREE = $BaselineSource
$saved = @{}
foreach ($name in $values.Keys) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$arguments = @{
    MsysRoot = $MsysRoot; Prefix = $Prefix; Identities = $Identities; Proof = $Proof; CacheHandoff = $CacheHandoff
    PackageDirectory = Join-Path $PSScriptRoot 'package-controls'
    OutputDirectory = "$output\invocation"; CacheDirectory = "$output\ccache"; Jobs = 1
}
try {
    foreach ($name in $values.Keys) { [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process') }
    $failedAsExpected = $false
    try {
        $null = & "$BaselineSource\.github\scripts\invoke-native-package.ps1" @arguments
    } catch {
        if ($_.Exception.Message -notlike 'Package build failed*') { throw }
        $failedAsExpected = $true
    }
    if (-not $failedAsExpected -or (Test-Path -LiteralPath $sentinel)) {
        throw 'The preserved version-1 destination defect was not reproduced.'
    }
    [ordered]@{
        Kind = 'version-1-isolation-negative-control'
        Reproduced = $true
        CompilationPerformed = $false
        DeletedTestOwnedSentinel = $sentinel
        BaselineSource = $BaselineSource
        Scope = 'Original adapter removed a test-owned shared src tree outside its fresh invocation; no user data was targeted'
    } | ConvertTo-Json | Set-Content -LiteralPath "$output\control-result.json" -Encoding utf8
    'REPRODUCED: original v1 adapter cleaned the test-owned outside src sentinel before build(); no compilation'
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
