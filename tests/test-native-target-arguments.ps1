#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $NativePython,
    [Parameter(Mandatory)][string] $Compiler,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Argument control root must be new.' }
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path "$output\records" | Out-Null
$executable = "$output\arguments.exe"
& $Compiler "$PSScriptRoot\native-target-arguments.c" -o $executable
if ($LASTEXITCODE) { throw 'Native argument fixture compilation failed.' }
[IO.File]::WriteAllText("$output\input with space.txt", 'R')
$relay = [IO.Path]::GetFullPath("$PSScriptRoot\..\.github\scripts\native-target-exec.sh")
$runs = @()
foreach ($mode in @('mingw', 'none')) {
    $start = [Diagnostics.ProcessStartInfo]::new("$MsysRoot\usr\bin\bash.exe")
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $output
    $start.Environment.Clear()
    foreach ($pair in @{
        SystemRoot=$env:SystemRoot;WINDIR=$env:SystemRoot
        PATH="$MsysRoot\usr\bin;$env:SystemRoot\System32"
        TEMP=$output;TMP=$output;MSYSTEM='MSYS';MSYS2_ARG_CONV_EXCL='*'
        WOARM64_NATIVE_PYTHON=$NativePython
        WOARM64_NATIVE_PYTHON_SHA256=(Get-FileHash -LiteralPath $NativePython).Hash.ToLowerInvariant()
        WOARM64_NATIVE_TEST_ROOT=$output;WOARM64_NATIVE_EXIT_DIR="$output\records"
        WOARM64_NATIVE_ARG_CONVERSION=$mode
    }.GetEnumerator()) { $start.Environment[$pair.Key]=$pair.Value }
    foreach ($arg in @('--noprofile','--norc','-c',
        'exec bash "$(cygpath -u "$1")" "$(cygpath -u "$2")" "$(cygpath -u "$3")"',
        'argument-control',$relay,$executable,"$output\input with space.txt")) {
        $start.ArgumentList.Add($arg)
    }
    $process = [Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit(30000)) { throw "Native argument control timed out: $mode" }
        $code = $process.ExitCode
        $out = $stdout.GetAwaiter().GetResult()
        $err = $stderr.GetAwaiter().GetResult()
        [IO.File]::WriteAllText("$output\$mode.stdout.log",$out)
        [IO.File]::WriteAllText("$output\$mode.stderr.log",$err)
    } finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
    $runs += @{Mode=$mode;Exit=$code;Stdout=$out;Stderr=$err}
}
$runs | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$output\runs.json" -Encoding utf8
if ($runs[0].Exit -ne 0 -or $runs[0].Stdout.Trim() -cne 'argument-file-ok' -or $runs[1].Exit -ne 1) {
    throw 'The relay did not distinguish MinGW path conversion from preserved POSIX arguments.'
}
$records = @(Get-ChildItem -LiteralPath "$output\records" -File -Filter '*.json' |
    ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json })
if ($records.Count -ne 2 -or @($records | Where-Object raw_exit -EQ 0).Count -ne 1 -or
    @($records | Where-Object raw_exit -EQ 1).Count -ne 1) { throw 'Argument controls lost raw exit evidence.' }
'PASS: MinGW file arguments are converted; explicit no-conversion preserves POSIX arguments'
