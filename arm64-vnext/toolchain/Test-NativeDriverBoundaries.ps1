[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [switch] $ExpectLegacyFailures
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new evidence directory.' }
$out = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
[void][IO.Directory]::CreateDirectory("$out\.libs")
$bin = Join-Path $Prefix 'bin'
$runs = [Collections.Generic.List[object]]::new()
$report = [ordered]@{
    Passed = $false; Prefix = $Prefix; Legacy = [bool]$ExpectLegacyFailures
    Scope = 'Native C/C++ driver output naming, C pthread/TLS, and quoted resource preprocessing; not full hosted C++ qualification'
    Runs = $runs
}
function Run([string]$Name, [string]$Executable, [string[]]$Arguments, [switch]$AllowFailure) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WorkingDirectory = $out
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
        if (-not $process.WaitForExit(60000)) {
            Stop-Process -Id $process.Id
            throw "$Name timed out"
        }
        [void]$copyOut.GetAwaiter().GetResult()
        [void]$copyErr.GetAwaiter().GetResult()
        $runs.Add([pscustomobject]@{
            Name = $Name; Executable = $Executable; Arguments = $Arguments; ExitCode = $process.ExitCode
        })
        if ($process.ExitCode -ne 0 -and -not $AllowFailure) {
            throw "$Name failed: $($process.ExitCode); see retained stderr"
        }
        return $process.ExitCode
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
    $env:PATH = "$bin;$oldPath"
    foreach ($name in @('gcc','g++','windres')) {
        $report[$name] = Get-ToolchainPeIdentity "$bin\$name.exe"
        if (-not $report[$name].NativeArm64 -or -not $report[$name].DynamicBase) {
            throw "Non-native or invalid tool: $name"
        }
    }
    foreach ($source in @('native-executable.c', 'quoted-version.c', 'quoted-version.rc')) {
        Copy-Item -LiteralPath "$PSScriptRoot\probes\$source" -Destination $out
    }
    if (Test-Path -LiteralPath "$bin\msys-2.0.dll") {
        Copy-Item -LiteralPath "$bin\msys-2.0.dll" -Destination $out
        Copy-Item -LiteralPath "$bin\msys-2.0.dll" -Destination "$out\.libs"
        $report.RuntimeDll = Get-ToolchainPeIdentity "$bin\msys-2.0.dll"
    }
    $null = Run 'c-suffix' "$bin\gcc.exe" @('-O2','-pthread',"$out\native-executable.c",'-o',"$out\conftest")
    if ($ExpectLegacyFailures) {
        if (-not (Test-Path "$out\conftest") -or (Test-Path "$out\conftest.exe")) {
            throw 'The legacy missing-suffix failure was not reproduced.'
        }
    } else {
        if (-not (Test-Path "$out\conftest.exe") -or (Test-Path "$out\conftest")) {
            throw 'Bare executable output did not receive exactly one .exe suffix.'
        }
        $null = Run 'c-native-run' "$out\conftest.exe" @()
        $null = Run 'cxx-suffix' "$bin\g++.exe" @('-O2','-pthread','-x','c++',
            "$out\native-executable.c",'-o',"$out\.libs\table-from")
        if (-not (Test-Path "$out\.libs\table-from.exe") -or (Test-Path "$out\.libs\table-from")) {
            throw 'C++ output inside .libs has the wrong suffix.'
        }
        $null = Run 'cxx-native-run' "$out\.libs\table-from.exe" @()
        $null = Run 'object-name' "$bin\gcc.exe" @('-c',"$out\native-executable.c",'-o',"$out\plain-object")
        if (-not (Test-Path "$out\plain-object") -or (Test-Path "$out\plain-object.exe")) {
            throw 'Compile-only output was incorrectly renamed.'
        }
        $null = Run 'explicit-name' "$bin\gcc.exe" @('-pthread',"$out\native-executable.c",'-o',"$out\kept.bin")
        if (-not (Test-Path "$out\kept.bin") -or (Test-Path "$out\kept.bin.exe")) {
            throw 'An explicitly suffixed output was incorrectly renamed.'
        }
    }
    # Preserve the literal quote escapes supplied by GNU libtool's RC command.
    $rcArgs = @('-DPACKAGE_VERSION_STRING=\"1.19\"', '-DPACKAGE_VERSION_MAJOR=1',
        '-DPACKAGE_VERSION_MINOR=19', '-DPACKAGE_VERSION_SUBMINOR=0',
        '-i', "$out\quoted-version.rc", '--output-format=coff', '-o', "$out\quoted-version.o")
    $rcExit = Run 'resource-quoted' "$bin\windres.exe" $rcArgs -AllowFailure
    if ($ExpectLegacyFailures) {
        if ($rcExit -eq 0 -or
            (Get-Content -Raw "$out\resource-quoted.stderr.bin") -notmatch 'not recognized') {
            throw 'The legacy cmd.exe quoting failure was not reproduced.'
        }
    } else {
        if ($rcExit -ne 0) { throw 'Default quoted resource preprocessing failed.' }
        $null = Run 'resource-link' "$bin\gcc.exe" @("$out\quoted-version.c",
            "$out\quoted-version.o",'-o',"$out\quoted-version.exe")
        $null = Run 'resource-native-run' "$out\quoted-version.exe" @()
        if ((Get-Content -Raw "$out\resource-native-run.stdout.bin").Trim() -ne 'native-windres-quoted-ok') {
            throw 'Resource string/integer values were not preserved.'
        }
        $report.Outputs = @("$out\conftest.exe", "$out\.libs\table-from.exe", "$out\quoted-version.exe" |
            ForEach-Object { Get-ToolchainPeIdentity $_ })
    }
    $report.Passed = $true
} finally {
    $env:PATH = $oldPath
    $report | ConvertTo-Json -Depth 10 | Set-Content "$out\result.json" -Encoding utf8
}
Write-Output "Driver boundary proof passed (legacy=$ExpectLegacyFailures): $out\result.json"
