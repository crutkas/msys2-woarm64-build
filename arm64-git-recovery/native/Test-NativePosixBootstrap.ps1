[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Root,
    [Parameter(Mandatory)][string] $EvidenceRoot,
    [Parameter(Mandatory)][string] $ProcessGate,
    [Parameter(Mandatory)][string] $ArtifactGate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'Arm64') {
    throw 'Native POSIX bootstrap tests require Windows ARM64.'
}
$Root = (Resolve-Path -LiteralPath $Root).Path
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'EvidenceRoot must not exist.' }
$relativeEvidence = [IO.Path]::GetRelativePath($Root, $EvidenceRoot)
if (-not [IO.Path]::IsPathRooted($relativeEvidence) -and $relativeEvidence -notmatch '^\.\.([\\/]|$)') {
    throw 'EvidenceRoot must be outside the tested payload.'
}
[void][IO.Directory]::CreateDirectory($EvidenceRoot)
[void][IO.Directory]::CreateDirectory("$EvidenceRoot\home")
[void][IO.Directory]::CreateDirectory("$EvidenceRoot\space dir")
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$pwsh = (Get-Process -Id $PID).Path
$results = [Collections.Generic.List[object]]::new()
$casesPassed = $false

function Write-Json([string] $Path, $Value) {
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 10), $utf8)
}

function Invoke-Gate([string] $Script, [string[]] $Arguments, [string] $ReportPath) {
    & $pwsh -NoProfile -File $Script @Arguments -ReportPath $ReportPath | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Native gate failed: $ReportPath" }
    $report = Get-Content -Raw -LiteralPath $ReportPath | ConvertFrom-Json
    if (-not $report.Passed) { throw "Native gate did not report success: $ReportPath" }
    return $report
}

function Start-Candidate([string] $File, [string[]] $Arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new((Join-Path "$Root\usr\bin" $File))
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $EvidenceRoot
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(GIT_|MSYS|MINGW|MAKE|SHELL$|BASH|ENV$|CDPATH$|PERL)') {
            [void]$start.Environment.Remove($key)
        }
    }
    $start.Environment['PATH'] = "$Root\usr\bin;$env:SystemRoot\System32"
    $start.Environment['HOME'] = "$EvidenceRoot\home"
    $start.Environment['MSYSTEM'] = 'MSYS'
    $start.Environment['MSYS2_PATH_TYPE'] = 'minimal'
    $start.Environment['LC_ALL'] = 'C'
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    [void]$process.Start()
    return $process
}

function Observe-Native([Diagnostics.Process] $Process, [string] $Name) {
    $identity = Invoke-Gate $ProcessGate @('-ProcessId', "$($Process.Id)") "$EvidenceRoot\$Name-process.json"
    if ($identity.MeasuredCount -ne 1 -or $identity.Processes[0].ProcessId -ne $Process.Id -or
        $identity.Processes[0].ImagePath -ine $Process.StartInfo.FileName) { throw 'Live process identity mismatch.' }
    $runtimePath = Join-Path "$Root\usr\bin" 'msys-2.0.dll'
    $runtimeHash = (Get-FileHash -LiteralPath $runtimePath).Hash
    $modules = @((Get-Process -Id $Process.Id).Modules | ForEach-Object {
        $path = $_.FileName
        $relative = [IO.Path]::GetRelativePath($Root, $path)
        $inRoot = -not [IO.Path]::IsPathRooted($relative) -and $relative -notmatch '^\.\.([\\/]|$)'
        $relative = [IO.Path]::GetRelativePath($env:SystemRoot, $path)
        $inWindows = -not [IO.Path]::IsPathRooted($relative) -and $relative -notmatch '^\.\.([\\/]|$)'
        if (-not $inRoot -and -not $inWindows) { throw "Unexpected loaded module: $path" }
        [ordered]@{ Path = $path; SHA256 = (Get-FileHash -LiteralPath $path).Hash; Artifact = $inRoot }
    })
    $runtime = @($modules | Where-Object { $_.Path -ieq $runtimePath -and $_.SHA256 -eq $runtimeHash })
    if ($runtime.Count -ne 1) { throw 'The process did not load the exact staged MSYS runtime.' }
    Write-Json "$EvidenceRoot\$Name-modules.json" $modules
}

function Invoke-Candidate([string] $Name, [string] $File, [string[]] $Arguments,
                         [int] $ExpectedExit = 0, [string] $InputText = '') {
    $process = Start-Candidate $File $Arguments
    $stdout = [IO.MemoryStream]::new()
    $stderr = [IO.MemoryStream]::new()
    try {
        $outTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $errTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.StandardInput.Write($InputText)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) { throw "Timed out: $Name" }
        [void]$outTask.GetAwaiter().GetResult()
        [void]$errTask.GetAwaiter().GetResult()
        [IO.File]::WriteAllBytes("$EvidenceRoot\$Name.stdout.bin", $stdout.ToArray())
        [IO.File]::WriteAllBytes("$EvidenceRoot\$Name.stderr.bin", $stderr.ToArray())
        $record = [ordered]@{
            Name = $Name; Executable = $process.StartInfo.FileName; Arguments = $Arguments
            ExitCode = $process.ExitCode; ExpectedExitCode = $ExpectedExit
            StdoutSHA256 = (Get-FileHash "$EvidenceRoot\$Name.stdout.bin").Hash
            StderrSHA256 = (Get-FileHash "$EvidenceRoot\$Name.stderr.bin").Hash
        }
        $results.Add($record)
        Write-Json "$EvidenceRoot\$Name.json" $record
        if ($process.ExitCode -ne $ExpectedExit) { throw "Unexpected exit for ${Name}: $($process.ExitCode)" }
        return $utf8.GetString($stdout.ToArray())
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        [void]$outTask.GetAwaiter().GetResult()
        [void]$errTask.GetAwaiter().GetResult()
        if (-not (Test-Path -LiteralPath "$EvidenceRoot\$Name.stdout.bin")) {
            [IO.File]::WriteAllBytes("$EvidenceRoot\$Name.stdout.bin", $stdout.ToArray())
            [IO.File]::WriteAllBytes("$EvidenceRoot\$Name.stderr.bin", $stderr.ToArray())
        }
        $process.Dispose()
        $stdout.Dispose()
        $stderr.Dispose()
    }
}

function Test-HeldCandidate([string] $Name, [string] $File, [string[]] $Arguments, [string] $InputText = '') {
    $process = Start-Candidate $File $Arguments
    $identityPassed = $false
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        Observe-Native $process $Name
        $identityPassed = $true
        $process.StandardInput.Write($InputText)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000)) { throw "Held $Name did not exit after input closed." }
        if ($process.ExitCode -ne 0) { throw "Held $Name exited $($process.ExitCode)" }
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        [IO.File]::WriteAllText("$EvidenceRoot\$Name.stdout.txt", $stdout.GetAwaiter().GetResult(), $utf8)
        [IO.File]::WriteAllText("$EvidenceRoot\$Name.stderr.txt", $stderr.GetAwaiter().GetResult(), $utf8)
        Write-Json "$EvidenceRoot\$Name-startup.json" ([ordered]@{
            ProcessId = $process.Id; Executable = $process.StartInfo.FileName
            ExitCode = $process.ExitCode; ExitHex = ('0x{0:X8}' -f ($process.ExitCode -band 0xffffffffL))
            NativeIdentityPassed = $identityPassed
        })
        $process.Dispose()
    }
}

try {
    foreach ($name in @('bash.exe', 'sh.exe', 'make.exe', 'msys-2.0.dll')) {
        if (-not (Test-Path -LiteralPath "$Root\usr\bin\$name" -PathType Leaf)) { throw "Missing native input: $name" }
    }
    $before = Invoke-Gate $ArtifactGate @('-Root', $Root) "$EvidenceRoot\artifact-before.json"
    Test-HeldCandidate 'bash' 'bash.exe' @('--noprofile', '--norc', '-c', 'IFS= read -r value || :')
    Test-HeldCandidate 'make' 'make.exe' @('-f', '-', 'all') ".PHONY: all`nall:`n"
    $script = @'
set -euo pipefail
[[ ${BASH_VERSINFO[0]} == 5 ]]
[[ $(printf '%s\n' alpha beta | while IFS= read -r value; do printf '<%s>' "$value"; done) == '<alpha><beta>' ]]
[[ $(( (7 * 9) - 5 )) == 58 ]]
trap 'observed=yes' USR1
observed=no
kill -USR1 "$$"
[[ $observed == yes ]]
(exit 37) &
child=$!
if wait "$child"; then exit 21; else [[ $? == 37 ]]; fi
if "$BASH" --noprofile --norc -c 'exit 37'; then exit 22; else [[ $? == 37 ]]; fi
cd "space dir"
windows_path=$(builtin pwd -W)
[[ $windows_path == [a-zA-Z]:/*/"space dir" ]]
printf '%s\n' "$windows_path" > ../pwd-w.txt
printf 'native-bash-behavior-ok\n' > ../bash-result.txt
'@
    $scriptPath = "$EvidenceRoot\bash-fixture.sh"
    [IO.File]::WriteAllText($scriptPath, $script.Replace("`r`n", "`n") + "`n", $utf8)
    Invoke-Candidate 'bash-behavior' 'bash.exe' @('--noprofile', '--norc', $scriptPath.Replace('\', '/')) | Out-Null
    if ([IO.File]::ReadAllText("$EvidenceRoot\bash-result.txt") -cne "native-bash-behavior-ok`n") {
        throw 'Bash behavior marker missing or changed.'
    }
    $expectedPwd = (Join-Path $EvidenceRoot 'space dir').Replace('\', '/')
    if ([IO.File]::ReadAllText("$EvidenceRoot\pwd-w.txt").TrimEnd("`n") -cne $expectedPwd) {
        throw 'MSYS Bash pwd -W did not name the actual working directory.'
    }
    $makefile = @'
SHELL := /usr/bin/bash
.SHELLFLAGS := --noprofile --norc -ec
.PHONY: all always failure
all: output.txt
output.txt: input.txt
	IFS= read -r value < input.txt; printf 'built:%s\n' "$$value" > output.txt
always:
	printf 'shell-dispatched\n' > make-shell.txt
failure:
	exit 37
'@
    [IO.File]::WriteAllText("$EvidenceRoot\Makefile", $makefile.Replace("`r`n", "`n") + "`n", $utf8)
    [IO.File]::WriteAllText("$EvidenceRoot\input.txt", "first`n", $utf8)
    Invoke-Candidate 'make-initial' 'make.exe' @('-f', 'Makefile', 'all', 'always') | Out-Null
    if ([IO.File]::ReadAllText("$EvidenceRoot\output.txt") -cne "built:first`n" -or
        [IO.File]::ReadAllText("$EvidenceRoot\make-shell.txt") -cne "shell-dispatched`n") {
        throw 'Make did not dispatch a real Bash recipe.'
    }
    $firstWrite = [IO.File]::GetLastWriteTimeUtc("$EvidenceRoot\output.txt")
    Invoke-Candidate 'make-noop' 'make.exe' @('-f', 'Makefile', 'all') | Out-Null
    if ([IO.File]::GetLastWriteTimeUtc("$EvidenceRoot\output.txt") -ne $firstWrite) { throw 'Make unnecessarily rebuilt an up-to-date target.' }
    [IO.File]::WriteAllText("$EvidenceRoot\input.txt", "second`n", $utf8)
    [IO.File]::SetLastWriteTimeUtc("$EvidenceRoot\input.txt", $firstWrite.AddSeconds(2))
    Invoke-Candidate 'make-rebuild' 'make.exe' @('-f', 'Makefile', 'all') | Out-Null
    if ([IO.File]::ReadAllText("$EvidenceRoot\output.txt") -cne "built:second`n") { throw 'Make failed to rebuild a changed prerequisite.' }
    Invoke-Candidate 'make-failure' 'make.exe' @('-f', 'Makefile', 'failure') 2 | Out-Null
    $after = Invoke-Gate $ArtifactGate @('-Root', $Root) "$EvidenceRoot\artifact-after.json"
    $old = @($before.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
    $new = @($after.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
    if (@(Compare-Object $old $new).Count) { throw 'Candidate binaries changed during native scenarios.' }
    $casesPassed = $true
}
finally {
    Write-Json "$EvidenceRoot\summary.json" ([ordered]@{
        Passed = $casesPassed; Classification = 'bootstrap-not-full-distribution'
        Scope = 'Native Bash pipelines/substitution/arithmetic/signal/background-wait/child-exec/pwd-W and make recipe/noop/rebuild/failure behavior; exact staged runtime observed in held Bash and make.'
        Cases = $results.ToArray()
        ArtifactGateSHA256 = (Get-FileHash -LiteralPath $ArtifactGate).Hash
        ProcessGateSHA256 = (Get-FileHash -LiteralPath $ProcessGate).Hash
    })
}
