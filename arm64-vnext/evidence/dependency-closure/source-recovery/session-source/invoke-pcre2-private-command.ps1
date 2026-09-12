function Invoke-Pcre2PrivateCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Executable,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = 'C:\ap07-pcre2-accd01',
        [hashtable]$Environment = @{},
        [int]$ExpectedExitCode = 0,
        [int]$TimeoutSeconds = 600
    )
    $ErrorActionPreference = 'Stop'
    $root = 'C:\ap07-pcre2-accd01'
    $receipt = "$root\evidence\$Name.json"
    if (Test-Path -LiteralPath $receipt) { throw "Command evidence already exists: $receipt" }
    if (-not [IO.Path]::IsPathRooted($Executable)) { throw 'An absolute executable path is required.' }
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.WorkingDirectory = $WorkingDirectory
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment.Clear()
    $environmentValues = @{
        SystemRoot = $env:SystemRoot
        WINDIR = $env:SystemRoot
        SystemDrive = [IO.Path]::GetPathRoot($env:SystemRoot).TrimEnd('\')
        ComSpec = "$env:SystemRoot\System32\cmd.exe"
        PATH = "$root\b\mingwarm64\bin;$root\b\usr\bin;$env:SystemRoot\System32;$env:SystemRoot;$PSHOME"
        PATHEXT = '.COM;.EXE;.BAT;.CMD'
        HOME = "$root\home"
        USERPROFILE = "$root\home"
        APPDATA = "$root\home\AppData\Roaming"
        LOCALAPPDATA = "$root\home\AppData\Local"
        TEMP = "$root\tmp"
        TMP = "$root\tmp"
        GNUPGHOME = '/c/ap07-pcre2-accd01/gnupg'
        GIT_CONFIG_NOSYSTEM = '1'
        GIT_CONFIG_GLOBAL = 'NUL'
        GIT_TERMINAL_PROMPT = '0'
        MAKEFLAGS = '-j2'
        CMAKE_BUILD_PARALLEL_LEVEL = '2'
        CTEST_PARALLEL_LEVEL = '2'
        OMP_NUM_THREADS = '2'
    }
    foreach ($item in $Environment.GetEnumerator()) { $environmentValues[$item.Key] = $item.Value }
    foreach ($item in $environmentValues.GetEnumerator()) { $start.Environment[$item.Key] = $item.Value }
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $record = [ordered]@{
        Name = $Name
        Executable = $Executable
        ExecutableSHA256 = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash.ToLowerInvariant()
        Arguments = $Arguments
        WorkingDirectory = $WorkingDirectory
        Environment = $environmentValues
        StartedAt = [DateTime]::UtcNow.ToString('o')
        Status = 'failed'
        ExpectedExitCode = $ExpectedExitCode
        RawExitCode = $null
        PID = $null
        Stdout = "$root\evidence\$Name.stdout.log"
        Stderr = "$root\evidence\$Name.stderr.log"
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw "Process failed to start: $Name" }
        $record.PID = $process.Id
        $stdout = [IO.File]::Create($record.Stdout)
        $stderr = [IO.File]::Create($record.Stderr)
        try {
            $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
            $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
            $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receipt
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                $process.Kill($true)
                $process.WaitForExit()
                throw "Private command timed out: $Name"
            }
            $null = $copyOut.GetAwaiter().GetResult()
            $null = $copyErr.GetAwaiter().GetResult()
            $record.RawExitCode = $process.ExitCode
        } finally {
            $stdout.Dispose()
            $stderr.Dispose()
        }
        if ($record.RawExitCode -ne $ExpectedExitCode) {
            throw "Private command $Name returned raw exit $($record.RawExitCode), expected $ExpectedExitCode; see $receipt"
        }
        $record.Status = if ($record.RawExitCode -eq 0) { 'completed-zero' } else { 'observed-expected-nonzero' }
    } finally {
        $record.CompletedAt = [DateTime]::UtcNow.ToString('o')
        $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receipt
        $process.Dispose()
    }
    [pscustomobject]$record
}
