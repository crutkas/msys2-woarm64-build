param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Output = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $Output) { throw 'Use a new private prerequisite fixture.' }
[void][IO.Directory]::CreateDirectory("$Output\home")
[IO.File]::WriteAllText("$Output\target", "native link prerequisite`n", [Text.UTF8Encoding]::new($false))
$cases = @()
function Invoke-Prerequisite([string]$Name, [string]$Exe, [string[]]$Arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new($Exe)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $Output
    $start.Environment.Clear()
    $start.Environment['SystemRoot'] = $env:SystemRoot
    $start.Environment['PATH'] = "$Root\usr\bin;$env:SystemRoot\System32"
    $start.Environment['HOME'] = "$Output\home"
    $start.Environment['MSYS'] = 'winsymlinks:nativestrict'
    $start.Environment['LC_ALL'] = 'C'
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    $process = [Diagnostics.Process]::Start($start)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) { throw "Native prerequisite timed out: $Name" }
        return [ordered]@{Name=$Name; Executable=$Exe; Arguments=$Arguments; ExitCode=$process.ExitCode;
            Stdout=$stdout.GetAwaiter().GetResult(); Stderr=$stderr.GetAwaiter().GetResult()}
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}
$guard = Join-Path $PSScriptRoot 'perl-native-arch-guard.sh'
$architecture = Invoke-Prerequisite 'shared-architecture-guard' "$Root\usr\bin\bash.exe" @('--noprofile','--norc',$guard,$Root)
$cases += $architecture
$link = Invoke-Prerequisite 'strict-native-symlink' "$Root\usr\bin\ln.exe" @('-s','target','link')
$cases += $link
$linkTest = Invoke-Prerequisite 'native-link-predicate' "$Root\usr\bin\bash.exe" @('--noprofile','--norc','-c','test -L link')
$cases += $linkTest
$passed = $architecture.ExitCode -eq 0 -and $architecture.Stdout.Trim() -in @('aarch64','arm64') -and
    $link.ExitCode -eq 0 -and $linkTest.ExitCode -eq 0
[ordered]@{Passed=$passed; Cases=$cases; ArchitectureGuardSHA256=(Get-FileHash -LiteralPath $guard).Hash;
    RuntimeSHA256=(Get-FileHash -LiteralPath "$Root\usr\bin\msys-2.0.dll").Hash;
    Scope='Actual shared architecture guard and strict native symlink prerequisites only; no Configure/build, settings, or shared-root writes'} |
    ConvertTo-Json -Depth 7 | Set-Content -LiteralPath "$Output\result.json"
if (-not $passed) { throw 'Native Perl prerequisites failed; no Configure or build launched.' }
