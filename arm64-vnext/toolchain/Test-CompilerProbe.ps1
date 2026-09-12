[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ProbeDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'Arm64') {
    throw 'These probes require native ARM64 Windows.'
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Choose a new output directory; existing evidence is preserved: $OutputDirectory"
}
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$results = foreach ($case in @(
    @{ Name = 'compiler-probe.exe'; ExpectedExit = 73 },
    @{ Name = 'compiler-negative.exe'; ExpectedExit = 91 }
)) {
    $source = Join-Path $ProbeDirectory $case.Name
    $copy = Join-Path $OutputDirectory $case.Name
    Copy-Item -LiteralPath $source -Destination $copy
    $hash = (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $hash) {
        throw "Source changed during copy: $source"
    }
    $identity = Get-ToolchainPeIdentity $copy
    if (-not $identity.NativeArm64 -or -not $identity.DynamicBase) {
        throw "Not an ARM64 PE32+ image: $copy"
    }
    $process = Start-Process -FilePath $copy -PassThru -NoNewWindow
    try {
        if (-not $process.WaitForExit(30000)) {
            Stop-Process -Id $process.Id -ErrorAction Stop
            throw "Probe timed out: $copy"
        }
        $exitCode = $process.ExitCode
    }
    finally {
        $process.Dispose()
    }
    if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $hash) {
        throw "Probe changed during execution: $copy"
    }
    [pscustomobject]@{
        File = $copy
        SHA256 = $hash.ToLowerInvariant()
        Machine = '0xAA64'
        Imports = $identity.Imports
        ExitCode = $exitCode
        ExpectedExitCode = $case.ExpectedExit
        Passed = $exitCode -eq $case.ExpectedExit
    }
}
$report = [ordered]@{
    RecordedUtc = [DateTime]::UtcNow.ToString('o')
    Scope = 'Linux-hosted C/C++ compiler, assembler and PE linker; no CRT. Positive executable requires ProcessMachineTypeInfo=ARM64. Not an MSYS runtime or native Windows compiler test.'
    Passed = @($results | Where-Object { -not $_.Passed }).Count -eq 0
    Results = @($results)
}
$report | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $OutputDirectory 'result.json') -Encoding utf8
$results | Format-Table -AutoSize
if (-not $report.Passed) { throw 'Compiler execution probe failed.' }
