function Invoke-LessPrivateCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Executable,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory)][string]$Root,
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{},
        [int]$ExpectedExit = 0,
        [ValidateRange(1, 86400)][int]$TimeoutSeconds = 600
    )
    $ErrorActionPreference = 'Stop'
    if (-not $WorkingDirectory) { $WorkingDirectory = $Root }
    $recordPath = Join-Path "$Root\evidence" "$Name.json"
    if (Test-Path -LiteralPath $recordPath) { throw "Command record already exists: $recordPath" }
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.WorkingDirectory = $WorkingDirectory
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment.Clear()
    $values = @{
        SystemRoot = $env:SystemRoot; WINDIR = $env:SystemRoot
        ComSpec = "$env:SystemRoot\System32\cmd.exe"
        PATH = "$env:SystemRoot\System32"; PATHEXT = '.COM;.EXE;.BAT;.CMD'
        HOME = "$Root\home"; USERPROFILE = "$Root\home"
        TEMP = "$Root\temp"; TMP = "$Root\temp"
        GIT_CONFIG_NOSYSTEM = '1'; GIT_CONFIG_GLOBAL = "$Root\home\empty.gitconfig"
        GIT_TERMINAL_PROMPT = '0'; MAKEFLAGS = '-j1'
        CMAKE_BUILD_PARALLEL_LEVEL = '1'; CTEST_PARALLEL_LEVEL = '1'; OMP_NUM_THREADS = '1'
    }
    foreach ($entry in $Environment.GetEnumerator()) { $values[$entry.Key] = $entry.Value }
    foreach ($entry in $values.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $record = [ordered]@{
        Name = $Name; Status = 'failed'; Executable = $Executable
        ExecutableSHA256 = (Get-FileHash -LiteralPath $Executable).Hash.ToLowerInvariant()
        Arguments = $Arguments; Environment = $values; WorkingDirectory = $WorkingDirectory
        PID = $null; StartedAt = [DateTime]::UtcNow.ToString('o'); RawExit = $null
        ExpectedExit = $ExpectedExit
        Stdout = "$Root\evidence\$Name.stdout.log"; Stderr = "$Root\evidence\$Name.stderr.log"
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $started = $false
    try {
        $started = $process.Start()
        if (-not $started) { throw "Could not start $Name" }
        $record.PID = $process.Id
        $stdout = [IO.File]::Create($record.Stdout)
        $stderr = [IO.File]::Create($record.Stderr)
        try {
            $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
            $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
            $record | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $recordPath
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                $process.Kill($true)
                $process.WaitForExit()
                throw "Command timed out: $Name"
            }
            $record.RawExit = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$process.ExitCode), 0)
            $null = $copyOut.GetAwaiter().GetResult()
            $null = $copyErr.GetAwaiter().GetResult()
        } finally {
            $stdout.Dispose()
            $stderr.Dispose()
        }
        if ($record.RawExit -ne $ExpectedExit) {
            throw "$Name returned raw $($record.RawExit), expected $ExpectedExit; see $recordPath"
        }
        $record.Status = 'expected-raw-exit'
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
        $record.CompletedAt = [DateTime]::UtcNow.ToString('o')
        $record | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $recordPath
    }
    [pscustomobject]$record
}
