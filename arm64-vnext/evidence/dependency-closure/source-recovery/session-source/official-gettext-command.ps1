function Invoke-OfficialGettextCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Executable,
        [string[]]$Arguments = @(),
        [hashtable]$Environment = @{},
        [string]$WorkingDirectory = 'C:\ap11-accd-gettext01',
        [int]$TimeoutSeconds = 120,
        [int]$ExpectedExit = 0
    )
    $ErrorActionPreference = 'Stop'
    $root = 'C:\ap11-accd-gettext01'
    $receipt = "$root\evidence\$Name.json"
    if (Test-Path -LiteralPath $receipt) { throw "Evidence already exists: $receipt" }
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.WorkingDirectory = $WorkingDirectory
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment.Clear()
    $values = @{
        SystemRoot = $env:SystemRoot; WINDIR = $env:SystemRoot
        PATH = "$env:SystemRoot\System32"
        PATHEXT = '.COM;.EXE;.BAT;.CMD'
        HOME = "$root\home"; USERPROFILE = "$root\home"
        TEMP = "$root\tmp"; TMP = "$root\tmp"
        GIT_CONFIG_NOSYSTEM = '1'; GIT_CONFIG_GLOBAL = 'NUL'
        GIT_TERMINAL_PROMPT = '0'
    }
    foreach ($item in $Environment.GetEnumerator()) { $values[$item.Key] = $item.Value }
    foreach ($item in $values.GetEnumerator()) { $start.Environment[$item.Key] = $item.Value }
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $record = [ordered]@{
        Status = 'failed'; Name = $Name; Executable = $Executable
        ExecutableSHA256 = (Get-FileHash -LiteralPath $Executable).Hash.ToLowerInvariant()
        Arguments = $Arguments; Environment = $values; WorkingDirectory = $WorkingDirectory
        PID = $null; RawExit = $null; ExpectedExit = $ExpectedExit
        StartedAt = [DateTime]::UtcNow.ToString('o')
        Stdout = "$root\evidence\$Name.stdout.log"; Stderr = "$root\evidence\$Name.stderr.log"
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
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { throw "Timed out: $Name" }
            $record.RawExit = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$process.ExitCode), 0)
            $null = $copyOut.GetAwaiter().GetResult()
            $null = $copyErr.GetAwaiter().GetResult()
        } finally {
            $stdout.Dispose()
            $stderr.Dispose()
        }
        if ($record.RawExit -ne $ExpectedExit) { throw "$Name raw exit $($record.RawExit), expected $ExpectedExit; see $receipt" }
        $record.Status = 'observed-expected-exit'
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
        $record.CompletedAt = [DateTime]::UtcNow.ToString('o')
        $record | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $receipt
    }
    [pscustomobject]$record
}
