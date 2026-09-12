[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $BinDirectory,
    [Parameter(Mandatory)][string] $EvidenceRoot,
    [Parameter(Mandatory)][string] $ProcessGate,
    [Parameter(Mandatory)][string] $ArtifactGate,
    [string] $Winapp = 'winapp'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:WINAPP_CLI_TELEMETRY_OPTOUT = '1'
$BinDirectory = (Resolve-Path -LiteralPath $BinDirectory).Path
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'EvidenceRoot must not exist.' }
[void][IO.Directory]::CreateDirectory($EvidenceRoot)
$pwsh = (Get-Process -Id $PID).Path
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$results = [Collections.Generic.List[object]]::new()

function Invoke-Ui([string[]] $Arguments) {
    $text = & $Winapp ui @Arguments --json
    if ($LASTEXITCODE -ne 0) { throw "UI command failed: $($Arguments -join ' ')" }
    return ($text -join "`n") | ConvertFrom-Json
}

function Write-Json([string] $Path, $Value) {
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 12), $utf8)
}

& $pwsh -NoProfile -File $ArtifactGate -Root $BinDirectory -ReportPath "$EvidenceRoot\artifact-before.json"
if ($LASTEXITCODE -ne 0) { throw 'Native artifact gate failed.' }
$before = Get-Content -LiteralPath "$EvidenceRoot\artifact-before.json" -Raw | ConvertFrom-Json
if (-not $before.Passed -or $before.ParsedCount -lt 2) { throw 'Incomplete artifact proof.' }
$secret = 'synthetic-arm64-fixture-not-a-secret'
$cases = @(
    @{ Name = 'askyesno-yes'; Exe = 'git-askyesno.exe'; Args = @('--title', 'ARM64 helper fixture', 'Synthetic fixture: choose Yes.'); Button = '6'; Exit = 0; Stdout = ''; Value = $null },
    @{ Name = 'askyesno-no'; Exe = 'git-askyesno.exe'; Args = @('--title', 'ARM64 helper fixture', 'Synthetic fixture: choose No.'); Button = '7'; Exit = 1; Stdout = ''; Value = $null },
    @{ Name = 'askpass-cancel'; Exe = 'git-askpass.exe'; Args = @('Synthetic fixture: cancel this prompt.'); Button = '2'; Exit = 1; Stdout = ''; Value = $null },
    @{ Name = 'askpass-value'; Exe = 'git-askpass.exe'; Args = @('Synthetic fixture: enter the non-secret test value.'); Button = '1'; Exit = 0; Stdout = $secret; Value = $secret }
)
foreach ($case in $cases) {
    $out = Join-Path $EvidenceRoot $case.Name
    [void][IO.Directory]::CreateDirectory($out)
    $exe = Join-Path $BinDirectory $case.Exe
    $start = [Diagnostics.ProcessStartInfo]::new($exe)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $out
    $start.Environment['PATH'] = "$BinDirectory;$env:SystemRoot\System32"
    foreach ($arg in $case.Args) { $start.ArgumentList.Add($arg) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $stdoutBuffer = [IO.MemoryStream]::new()
    $stderrBuffer = [IO.MemoryStream]::new()
    $started = $false
    $record = [ordered]@{ Name = $case.Name; Status = 'failed'; ExpectedExit = $case.Exit }
    try {
        [void]$process.Start()
        $started = $true
        $record.ProcessId = $process.Id
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutBuffer)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrBuffer)
        Invoke-Ui @('wait-for', $case.Button, '-a', "$($process.Id)", '-t', '5000') | Out-Null
        $tree = Invoke-Ui @('inspect', '-a', "$($process.Id)", '--interactive')
        Write-Json "$out\ui.json" $tree
        $elements = @($tree.windows | ForEach-Object { $_.elements })
        $button = @($elements | Where-Object { $_.automationId -eq $case.Button })
        if ($button.Count -ne 1 -or -not $button[0].isEnabled) { throw 'Expected dialog action not available.' }
        & $pwsh -NoProfile -File $ProcessGate -ProcessId $process.Id -ReportPath "$out\native-process.json"
        if ($LASTEXITCODE -ne 0) { throw 'Native process gate failed.' }
        $identity = Get-Content -Raw -LiteralPath "$out\native-process.json" | ConvertFrom-Json
        if (-not $identity.Passed -or $identity.MeasuredCount -ne 1 -or
            $identity.Processes[0].ImagePath -ine $exe) { throw 'Live image mismatch.' }
        if ($null -ne $case.Value) {
            $edit = @($elements | Where-Object { $_.automationId -eq '1000' })
            if ($edit.Count -ne 1) { throw 'Expected Win32 password edit not available.' }
            Invoke-Ui @('set-value', $edit[0].selector, $case.Value, '-a', "$($process.Id)") | Out-Null
        }
        Invoke-Ui @('screenshot', '-a', "$($process.Id)", '-o', "$out\dialog.png") | Out-Null
        Invoke-Ui @('invoke', $button[0].selector, '-a', "$($process.Id)") | Out-Null
        if (-not $process.WaitForExit(10000)) { throw 'Helper did not exit after dialog action.' }
        [void]$stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        $stdout = $stdoutBuffer.ToArray()
        $stderr = $stderrBuffer.ToArray()
        [IO.File]::WriteAllBytes("$out\stdout.bin", $stdout)
        [IO.File]::WriteAllBytes("$out\stderr.bin", $stderr)
        $record.ExitCode = $process.ExitCode
        $record.StdoutSHA256 = (Get-FileHash "$out\stdout.bin").Hash
        $record.StderrSHA256 = (Get-FileHash "$out\stderr.bin").Hash
        if ($process.ExitCode -ne $case.Exit) { throw 'Helper exit code differs from the chosen action.' }
        $text = $utf8.GetString($stdout)
        $expectedText = if ($null -ne $case.Value) { "$($case.Stdout)`r`n" } else { $case.Stdout }
        if ($text -cne $expectedText -or $stderr.Length -ne 0) {
            throw 'Helper output differs from the fixture value; raw bytes preserved.'
        }
        $record.Status = 'behavior-passed'
    }
    catch {
        $record.Error = $_.Exception.Message
    }
    finally {
        if ($started) {
            if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
            [void]$stdoutTask.GetAwaiter().GetResult()
            [void]$stderrTask.GetAwaiter().GetResult()
            if (-not (Test-Path -LiteralPath "$out\stdout.bin")) {
                [IO.File]::WriteAllBytes("$out\stdout.bin", $stdoutBuffer.ToArray())
                [IO.File]::WriteAllBytes("$out\stderr.bin", $stderrBuffer.ToArray())
            }
        }
        $process.Dispose()
        $stdoutBuffer.Dispose()
        $stderrBuffer.Dispose()
        Write-Json "$out\result.json" $record
        $results.Add($record)
    }
}
& $pwsh -NoProfile -File $ArtifactGate -Root $BinDirectory -ReportPath "$EvidenceRoot\artifact-after.json"
if ($LASTEXITCODE -ne 0) { throw 'Post-test native artifact gate failed.' }
$after = Get-Content -Raw -LiteralPath "$EvidenceRoot\artifact-after.json" | ConvertFrom-Json
$old = @($before.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
$new = @($after.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
if (-not $after.Passed -or @(Compare-Object $old $new).Count) { throw 'Prompt binaries changed during testing.' }
$failed = @($results | Where-Object { $_.Status -ne 'behavior-passed' })
Write-Json "$EvidenceRoot\summary.json" ([ordered]@{
    Scope = 'Native askyesno yes/no and askpass cancel/value only. Selector awaits real native Git configuration.'
    Passed = $failed.Count -eq 0
    VisualReviewPending = $true
    Cases = $results.ToArray()
})
if ($failed.Count) { throw "$($failed.Count) prompt behavior case(s) failed." }
