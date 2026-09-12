[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $CrossProbeDirectory,
    [switch] $ExpectLegacyFault
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new evidence directory.' }
$out = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$cc = Join-Path $Prefix 'bin\gcc.exe'
$objdump = Join-Path $Prefix 'bin\objdump.exe'
$runs = [Collections.Generic.List[object]]::new()
$result = [ordered]@{ Prefix = $Prefix; Legacy = [bool]$ExpectLegacyFault; Passed = $false; Runs = $runs }
function Run([string]$Name, [string]$Executable, [string[]]$Arguments, [int]$ExpectedExit = 0) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $stdout = [IO.File]::Create("$out\$Name.stdout.bin")
    $stderr = [IO.File]::Create("$out\$Name.stderr.bin")
    $process = $null
    try {
        $process = [Diagnostics.Process]::Start($info)
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
        if (-not $process.WaitForExit(120000)) {
            Stop-Process -Id $process.Id
            throw "$Name timed out."
        }
        [void]$copyOut.GetAwaiter().GetResult()
        [void]$copyErr.GetAwaiter().GetResult()
        $runs.Add([pscustomobject]@{
            Name = $Name; Executable = $Executable; Arguments = $Arguments
            ExitCode = $process.ExitCode; ExpectedExit = $ExpectedExit
        })
        if ($process.ExitCode -ne $ExpectedExit) {
            throw "$Name exit $($process.ExitCode), expected $ExpectedExit. See retained raw streams."
        }
    } finally {
        if ($process) {
            if (-not $process.HasExited) { Stop-Process -Id $process.Id }
            $process.Dispose()
        }
        $stdout.Dispose()
        $stderr.Dispose()
    }
}
$oldPath = $env:PATH
try {
    $env:PATH = "$(Join-Path $Prefix 'bin');$oldPath"
    if ($CrossProbeDirectory) {
        if ($ExpectLegacyFault) { throw 'The cross-probe stage is for the fixed archive.' }
        $selected = Join-Path $CrossProbeDirectory 'libgcc.a'
        $result.Compiler = Get-Content -Raw (Join-Path $CrossProbeDirectory 'compiler-identity.txt')
        foreach ($name in @('windows-clear-cache.exe', 'windows-cache-contract.exe', 'msys-2.0.dll')) {
            Copy-Item -LiteralPath (Join-Path $CrossProbeDirectory $name) -Destination $out
        }
        $result.Runtime = Get-ToolchainPeIdentity "$out\msys-2.0.dll"
    } else {
        $selected = (& $cc '-print-libgcc-file-name' | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $selected -PathType Leaf)) {
            throw 'Compiler did not resolve libgcc.'
        }
        $result.Compiler = Get-ToolchainPeIdentity $cc
        foreach ($name in @('windows-clear-cache', 'windows-cache-contract')) {
            Copy-Item -LiteralPath "$PSScriptRoot\probes\$name.c" -Destination $out
            Run "$name-build" $cc @('-O2', '-Wall', '-Wextra', "$out\$name.c", '-o', "$out\$name.exe")
        }
    }
    $result.Library = [ordered]@{
        Path = [IO.Path]::GetFullPath($selected)
        SHA256 = (Get-FileHash -LiteralPath $selected).Hash.ToLowerInvariant()
    }
    $identity = Get-ToolchainPeIdentity "$out\windows-clear-cache.exe"
    if (-not $identity.NativeArm64 -or -not $identity.DynamicBase) { throw 'Invalid probe PE identity.' }
    $result.Probe = $identity
    Run 'cache-disassembly' $objdump @('-d', '--disassemble=__aarch64_sync_cache_range',
                                      "$out\windows-clear-cache.exe")
    $disassembly = Get-Content -Raw "$out\cache-disassembly.stdout.bin"
    Run 'cache-archive-relocations' $objdump @('-dr', '--disassemble=__aarch64_sync_cache_range', $selected)
    $relocations = Get-Content -Raw "$out\cache-archive-relocations.stdout.bin"
    if ($ExpectLegacyFault) {
        if ($disassembly -notmatch 'mrs\s+.*ctr_el0') { throw 'Negative control has no legacy cache instruction.' }
        Run 'native-execute' "$out\windows-clear-cache.exe" @() -1073741795
    } else {
        if ('FlushInstructionCache' -notin @($identity.Imports |
            Where-Object { $_.Dll -ieq 'KERNEL32.dll' } | ForEach-Object { $_.Symbols })) {
            throw 'The real probe does not import the Windows cache API.'
        }
        if ($disassembly -match '\bctr_el0\b|\bdc\s+cvau\b|\bic\s+ivau\b' -or
            $relocations -notmatch 'IMAGE_REL_ARM64_PAGEBASE_REL21\s+__imp_FlushInstructionCache') {
            throw 'Cache helper does not exclusively use the Windows API.'
        }
        Run 'native-execute' "$out\windows-clear-cache.exe" @()
        $text = Get-Content -Raw "$out\native-execute.stdout.bin"
        if ($text -notmatch 'clear-cache-native-ok iterations=512 cross-page=1') { throw 'Missing execution proof.' }
        Run 'contract-success' "$out\windows-cache-contract.exe" @()
        Run 'contract-failure' "$out\windows-cache-contract.exe" @('failure') 71
        Run 'contract-reversed' "$out\windows-cache-contract.exe" @('reversed') 72
    }
    if ((Get-FileHash -LiteralPath $selected).Hash.ToLowerInvariant() -ne $result.Library.SHA256) {
        throw 'Runtime library changed during the proof.'
    }
    $result.Passed = $true
} finally {
    $env:PATH = $oldPath
    $result | ConvertTo-Json -Depth 12 | Set-Content "$out\result.json" -Encoding utf8
}
Write-Output "Cache proof passed (legacy=$ExpectLegacyFault); result: $out\result.json"
