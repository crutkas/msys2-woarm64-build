[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ProbeDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [ValidateSet('all', 'gcc-self', 'stdio', 'cross-compiler', 'clang-reference')]
    [string[]] $IncludeGroup = @('all'),
    [ValidateRange(1, 300)][int] $TimeoutSeconds = 15
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'Arm64') {
    throw 'These probes require native ARM64 Windows.'
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Existing evidence is preserved; choose a new output directory: $OutputDirectory"
}
$manifest = Get-Content -Raw -LiteralPath (Join-Path $ProbeDirectory 'build.json') | ConvertFrom-Json
if ($manifest.version -ne 1) { throw 'Unsupported varargs manifest version.' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
Copy-Item -LiteralPath (Join-Path $ProbeDirectory 'build.json') `
    -Destination (Join-Path $OutputDirectory 'build.json')
$results = [Collections.Generic.List[object]]::new()
$programs = @($manifest.programs | Where-Object {
    $IncludeGroup -contains 'all' -or $IncludeGroup -contains $_.group
})
if ($programs.Count -eq 0) { throw 'No programs match the explicitly selected groups.' }
foreach ($program in $programs) {
    if ([IO.Path]::GetFileName($program.file) -cne $program.file) {
        throw "Executable name must not contain a directory: $($program.file)"
    }
    $source = Join-Path $ProbeDirectory $program.file
    $executable = Join-Path $OutputDirectory $program.file
    Copy-Item -LiteralPath $source -Destination $executable
    $hash = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne $program.sha256 -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash) {
        throw "Build executable changed during copy: $source"
    }
    $identity = Get-ToolchainPeIdentity $executable
    if (-not $identity.NativeArm64 -or -not $identity.DynamicBase) {
        throw "Executable must be AA64 PE32+ with DYNAMIC_BASE: $executable"
    }
    foreach ($case in $program.cases) {
        $stem = '{0}-{1:D2}-{2}' -f $program.name, [int]$case.id, $case.name
        $outPath = Join-Path $OutputDirectory "$stem.stdout.bin"
        $errPath = Join-Path $OutputDirectory "$stem.stderr.bin"
        $stdout = [IO.File]::Create($outPath)
        $stderr = [IO.File]::Create($errPath)
        $process = $null
        $errorText = $null
        $exitCode = $null
        $timedOut = $false
        try {
            $start = [Diagnostics.ProcessStartInfo]::new($executable)
            $start.UseShellExecute = $false
            $start.RedirectStandardOutput = $true
            $start.RedirectStandardError = $true
            $start.RedirectStandardInput = $true
            $start.Arguments = [string]$case.id
            $start.WorkingDirectory = $OutputDirectory
            $process = [Diagnostics.Process]::Start($start)
            $process.StandardInput.Close()
            $outTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
            $errTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                $timedOut = $true
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit()
            }
            [void]$outTask.GetAwaiter().GetResult()
            [void]$errTask.GetAwaiter().GetResult()
            $exitCode = $process.ExitCode
        }
        catch {
            $errorText = $_.Exception.Message
            if ($null -ne $process -and -not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit()
            }
        }
        finally {
            $stdout.Dispose()
            $stderr.Dispose()
            if ($null -ne $process) { $process.Dispose() }
        }
        $outBytes = [IO.File]::ReadAllBytes($outPath)
        $errBytes = [IO.File]::ReadAllBytes($errPath)
        $passed = $false
        $detail = [ordered]@{}
        if ($program.kind -eq 'abi' -and $outBytes.Length -eq 64) {
            $words = @(for ($i = 0; $i -lt 8; ++$i) {
                [BitConverter]::ToUInt32($outBytes, 4 * $i)
            })
            $detail.ProducerVaListSize = $words[4]
            $detail.ConsumerVaListSize = $words[5]
            $detail.MachineQuerySucceeded = $words[6]
            $detail.RunningMachine = '0x{0:X4}' -f $words[7]
            $detail.CaseResult = $words[3]
            $detail.ObservedWords = @(for ($i = 0; $i -lt 4; ++$i) {
                '0x{0:X16}' -f [BitConverter]::ToUInt64($outBytes, 32 + 8 * $i)
            })
            $passed = $words[0] -eq 0x4D535641 -and $words[1] -eq 1 -and
                $words[2] -eq $case.id -and $words[3] -eq 0 -and
                $words[4] -eq 8 -and $words[5] -eq 8 -and
                $words[6] -eq 1 -and $words[7] -eq 0xAA64 -and
                $errBytes.Length -eq 0
        }
        elseif ($program.kind -eq 'stdio' -and $errBytes.Length -eq 48) {
            $words = @(for ($i = 0; $i -lt 12; ++$i) {
                [BitConverter]::ToUInt32($errBytes, 4 * $i)
            })
            $detail.VaListSize = $words[3]
            $detail.AnsiStdioAtInclude = $words[4]
            $detail.MachineQuerySucceeded = $words[5]
            $detail.RunningMachine = '0x{0:X4}' -f $words[6]
            $detail.FirstReturnBits = $words[7]
            $detail.SecondReturnBits = $words[8]
            $detail.FirstErrno = $words[9]
            $detail.LastErrno = $words[10]
            $detail.FlushReturnBits = $words[11]
            $detail.ExpectedHex = $case.expectedHex
            $detail.ExactBytes = [Convert]::ToHexString($outBytes).ToLowerInvariant() -ceq $case.expectedHex
            $detail.ValidUtf8 = $true
            try { [void][Text.UTF8Encoding]::new($false, $true).GetString($outBytes) }
            catch [Text.DecoderFallbackException] { $detail.ValidUtf8 = $false }
            $returns = if ($case.id -lt 10) {
                $words[7] -eq 9 -and $words[8] -eq 9
            } elseif ($case.id -lt 14) {
                $words[7] -eq 25
            } else { $true }
            $passed = $detail.ExactBytes -and $returns -and
                $words[0] -eq 0x4D535354 -and $words[1] -eq 1 -and
                $words[2] -eq $case.id -and $words[3] -eq 8 -and
                $words[4] -eq 0 -and $words[5] -eq 1 -and
                $words[6] -eq 0xAA64 -and $words[11] -eq 0
        }
        $passed = $passed -and $exitCode -eq 0 -and -not $timedOut -and $null -eq $errorText
        $result = [pscustomobject][ordered]@{
            Program = $program.name
            ExecutableSHA256 = $hash
            Kind = $program.kind
            Group = $program.group
            Case = $case.name
            CaseId = $case.id
            Category = $case.category
            Passed = $passed
            ExitCode = $exitCode
            TimedOut = $timedOut
            Error = $errorText
            StdoutLength = $outBytes.Length
            StdoutHex = [Convert]::ToHexString($outBytes).ToLowerInvariant()
            StdoutSHA256 = (Get-FileHash -LiteralPath $outPath -Algorithm SHA256).Hash.ToLowerInvariant()
            StderrLength = $errBytes.Length
            StderrHex = [Convert]::ToHexString($errBytes).ToLowerInvariant()
            StderrSHA256 = (Get-FileHash -LiteralPath $errPath -Algorithm SHA256).Hash.ToLowerInvariant()
            Detail = $detail
        }
        $result | ConvertTo-Json -Depth 7 |
            Set-Content -LiteralPath (Join-Path $OutputDirectory "$stem.json") -Encoding utf8
        $results.Add($result)
    }
    if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash) {
        throw "Executable changed during execution: $executable"
    }
}
$failures = @($results | Where-Object { -not $_.Passed })
$controlFailures = @($failures | Where-Object { $_.Category -ne 'alignment-reference' })
$alignmentFailures = @($failures | Where-Object { $_.Category -eq 'alignment-reference' })
$groups = @(foreach ($group in ($results | Group-Object Group)) {
    [pscustomobject]@{
        Group = $group.Name
        Cases = $group.Count
        Failures = @($group.Group | Where-Object { -not $_.Passed }).Count
        Passed = @($group.Group | Where-Object { -not $_.Passed }).Count -eq 0
    }
})
$report = [ordered]@{
    RecordedUtc = [DateTime]::UtcNow.ToString('o')
    Mode = $manifest.mode
    SelectedGroups = @($IncludeGroup)
    Suite = if ($manifest.PSObject.Properties['suite']) { $manifest.suite } else { 'all' }
    BuildPassed = $manifest.buildPassed
    Passed = $manifest.buildPassed -and $results.Count -gt 0 -and $failures.Count -eq 0
    ControlsPassed = $manifest.buildPassed -and $controlFailures.Count -eq 0
    AlignmentReferencePassed = $manifest.buildPassed -and $alignmentFailures.Count -eq 0
    CaseCount = $results.Count
    FailureCount = $failures.Count
    Groups = $groups
    Results = $results.ToArray()
    Scope = 'Native AA64 GetProcessInformation plus raw per-case streams. Cross-compiler ABI cases use SDK-free real target objects and Kernel32; stdio cases use normal GCC/UCRT wrappers. Alignment discrepancies are failures, not suppressed.'
}
$report | ConvertTo-Json -Depth 9 |
    Set-Content -LiteralPath (Join-Path $OutputDirectory 'result.json') -Encoding utf8
$failures | Select-Object Program, Case, ExitCode, TimedOut | Format-Table -AutoSize
Write-Output "$($results.Count) cases; $($failures.Count) failures; controls passed=$($report.ControlsPassed)"
if (-not $report.Passed) { throw "Varargs acceptance failed; raw evidence: $OutputDirectory" }
