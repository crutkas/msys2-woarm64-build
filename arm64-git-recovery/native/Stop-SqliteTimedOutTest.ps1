param(
    [Parameter(Mandatory)][int]$TargetPid,
    [Parameter(Mandatory)][long]$ExpectedCreationFileTime,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$TestName,
    [Nullable[int]]$PriorDurationMs
)
$ErrorActionPreference = 'Stop'
$root = 'C:\ag-sqlite-e138-01'
$destination = [IO.Path]::GetFullPath($Output)
if (!$destination.StartsWith($root + '\') -or (Test-Path $destination)) {
    throw 'Fresh private timeout evidence path required'
}
$process = Get-Process -Id $TargetPid
$null = $process.Handle
if ($process.StartTime.ToFileTimeUtc() -ne $ExpectedCreationFileTime -or
    !$process.Path.StartsWith($root + '\') -or $process.ProcessName -ne 'testfixture') {
    throw 'Exact owned test generation does not match'
}
$elapsed = ((Get-Date) - $process.StartTime).TotalSeconds
if ($elapsed -lt 1200 -or $process.HasExited) {
    throw 'This action requires an observed running test exceeding twenty minutes'
}
$record = [ordered]@{
    scope = 'Explicit timeout failure, not a natural or successful test exit'
    pid = $TargetPid
    creation_filetime = $ExpectedCreationFileTime
    executable = $process.Path
    elapsed_seconds = $elapsed
    cpu_seconds = $process.CPU
    test = $TestName
    prior_measured_duration_ms = $PriorDurationMs
    action = 'Stop-Process -Id on the exact owned leaf; upstream runner records failure and continues'
}
Stop-Process -Id $TargetPid
if (!$process.WaitForExit(10000)) { throw 'Timed-out test did not exit' }
$record['observed_exit'] = $true
$record['exit_code'] = $process.ExitCode
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $destination -Encoding utf8
$record | ConvertTo-Json -Depth 6
