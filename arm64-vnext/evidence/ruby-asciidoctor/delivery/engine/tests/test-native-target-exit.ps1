#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $NativePython,
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Compiler,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Raw-exit control root must be new.' }
New-Item -ItemType Directory -Path "$output\records" | Out-Null
$source = Join-Path $PSScriptRoot 'native-exit-status.c'
$target = "$output\exit-status.exe"
& $Compiler $source -o $target
if ($LASTEXITCODE) { throw 'Native exit-status fixture compilation failed.' }
$relay = [IO.Path]::GetFullPath("$PSScriptRoot\..\.github\scripts\native-target-exec.py")
$pythonHash = (Get-FileHash -LiteralPath $NativePython).Hash.ToLowerInvariant()
function Run-Control([string] $Name, [string] $Executable, [string[]] $Arguments, [int] $Expected) {
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $output
    $start.Environment.Clear()
    foreach ($pair in @{
        SystemRoot=$env:SystemRoot;WINDIR=$env:SystemRoot;PATH="$MsysRoot\usr\bin;$env:SystemRoot\System32"
        HOME=$output;TEMP=$output;TMP=$output;MSYSTEM='MSYS';MSYS2_ARG_CONV_EXCL='*'
        WOARM64_NATIVE_PYTHON_SHA256=$pythonHash;WOARM64_NATIVE_TEST_ROOT=$output
        WOARM64_NATIVE_EXIT_DIR="$output\records"
    }.GetEnumerator()) { $start.Environment[$pair.Key] = $pair.Value }
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    $process = [Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit(30000)) { throw "Exit control timed out: $Name" }
        $code = $process.ExitCode
        [IO.File]::WriteAllText("$output\$Name.stdout.log",$stdout.GetAwaiter().GetResult())
        [IO.File]::WriteAllText("$output\$Name.stderr.log",$stderr.GetAwaiter().GetResult())
        if ($code -ne $Expected) { throw "Unexpected $Name exit $code, expected $Expected" }
    } finally {
        if (-not $process.HasExited) { $process.Kill($true);$process.WaitForExit() }
        $process.Dispose()
    }
    [pscustomobject]@{Name=$Name;ExitCode=$code;Expected=$Expected}
}
$results = @()
$results += Run-Control 'raw-1536' $target @('1536') 1536
foreach ($code in @(0,1,77,255,256,1536,-1)) {
    $expected = if ($code -ge 0 -and $code -le 255) { $code } else { 255 }
    $results += Run-Control "relay-$code" $NativePython @('-I',$relay,$target,"$code") $expected
    $bash = 'exec "$1" -I "$2" "$3" "$4"'
    $results += Run-Control "foreign-parent-$code" "$MsysRoot\usr\bin\bash.exe" @('--noprofile','--norc','-c',$bash,'relay-control',$NativePython,$relay,$target,"$code") $expected
}
$outside = [IO.Path]::GetFullPath($Compiler)
$results += Run-Control 'outside-root-rejected' $NativePython @('-I',$relay,$outside) 1
$records = @(Get-ChildItem -LiteralPath "$output\records" -File -Filter '*.json' | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json })
if ($records.Count -ne 14 -or @($records | Where-Object { $_.raw_exit -eq 1536 -and $_.portable_exit -eq 255 }).Count -ne 2 -or
    @($records | Where-Object { $_.raw_exit -ne 0 -and $_.portable_exit -eq 0 }).Count) {
    throw 'Raw native exit records were lost or a failure became success.'
}
[ordered]@{Status='passed';Results=$results;Records=$records;Fixture=$target;PythonSHA256=$pythonHash
    Scope='Synthetic native Windows return values preserve failure through foreign Bash; not a claim of a naturally occurring MinGW application failure'
} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath "$output\result.json" -Encoding utf8
'PASS: raw native nonzero exits remain nonzero through direct and foreign-parent relay paths'
