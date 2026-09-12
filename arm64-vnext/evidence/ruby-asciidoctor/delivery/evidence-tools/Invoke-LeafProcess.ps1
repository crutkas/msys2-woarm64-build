function New-LeafStartInfo {
    param([string] $Executable, [string[]] $Arguments, [string] $WorkingDirectory = 'C:\ar07-9047',
          [hashtable] $Environment = @{})
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $WorkingDirectory
    $start.Environment.Clear()
    $values = @{
        SYSTEMROOT = $env:SystemRoot; WINDIR = $env:WINDIR; SystemDrive = $env:SystemDrive
        COMSPEC = $env:COMSPEC; PATHEXT = '.COM;.EXE;.BAT;.CMD'
        PATH = "C:\ar07-9047\b\usr\bin;$env:SystemRoot\System32;$env:SystemRoot"
        HOME = 'C:\ar07-9047\home'; USERPROFILE = 'C:\ar07-9047\home'
        TEMP = 'C:\ar07-9047\tmp'; TMP = 'C:\ar07-9047\tmp'
        GNUPGHOME = 'C:\ar07-9047\b\etc\pacman.d\gnupg'
        GIT_CONFIG_NOSYSTEM = '1'; GIT_CONFIG_GLOBAL = 'C:\ar07-9047\home\no-global-config'
        GIT_TERMINAL_PROMPT = '0'; GCM_INTERACTIVE = 'never'
        MSYSTEM = 'MSYS'; MSYS2_PATH_TYPE = 'minimal'; CHERE_INVOKING = '1'
        LANG = 'C.UTF-8'; MAKEFLAGS = '-j2'; CMAKE_BUILD_PARALLEL_LEVEL = '2'
        CTEST_PARALLEL_LEVEL = '2'; NUMBER_OF_PROCESSORS = '2'; OMP_NUM_THREADS = '1'
    }
    foreach ($entry in $values.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
    foreach ($entry in $Environment.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $start
}

function Invoke-LeafProcess {
    param([string] $Executable, [string[]] $Arguments, [string] $Label,
          [string] $WorkingDirectory = 'C:\ar07-9047', [hashtable] $Environment = @{},
          [int] $ExpectedExit = 0)
    $logRoot = "C:\ar07-9047\evidence\$Label"
    foreach ($extension in 'stdout.log', 'stderr.log', 'json') {
        if (Test-Path -LiteralPath "$logRoot.$extension") { throw "Log already exists: $logRoot.$extension" }
    }
    $start = New-LeafStartInfo -Executable $Executable -Arguments $Arguments `
        -WorkingDirectory $WorkingDirectory -Environment $Environment
    $process = [Diagnostics.Process]::Start($start)
    Write-Host "START pid=$($process.Id) executable=$Executable log=$logRoot"
    $outFile = [IO.File]::Create("$logRoot.stdout.log")
    $errFile = [IO.File]::Create("$logRoot.stderr.log")
    try {
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($outFile)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($errFile)
        $process.WaitForExit()
        $null = $copyOut.GetAwaiter().GetResult()
        $null = $copyErr.GetAwaiter().GetResult()
        $result = [ordered]@{
            Executable = $Executable; Arguments = $Arguments; WorkingDirectory = $WorkingDirectory
            ProcessId = $process.Id; Started = $process.StartTime.ToUniversalTime().ToString('o')
            Completed = $process.ExitTime.ToUniversalTime().ToString('o')
            RawExitCode = $process.ExitCode; ExpectedExitCode = $ExpectedExit
            ClearedEnvironment = $true; Stdout = "$logRoot.stdout.log"; Stderr = "$logRoot.stderr.log"
        }
        $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$logRoot.json" -Encoding utf8
        if ($process.ExitCode -ne $ExpectedExit) { throw "Process failed with raw exit $($process.ExitCode): $logRoot" }
        [pscustomobject]$result
    } finally {
        $outFile.Dispose()
        $errFile.Dispose()
        $process.Dispose()
    }
}
