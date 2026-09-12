param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$ArtifactGate,
    [Parameter(Mandatory)][string]$ProcessGate
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Output = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $Output) { throw 'Use a new evidence directory.' }
[void][IO.Directory]::CreateDirectory($Output)
$candidates = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
    $stream = [IO.File]::OpenRead($_.FullName)
    try { $stream.ReadByte() -eq 77 -and $stream.ReadByte() -eq 90 } finally { $stream.Dispose() }
} | ForEach-Object { $_.FullName })
& $ArtifactGate -Path $candidates -ReportPath "$Output\artifacts.json"
$artifact = Get-Content -LiteralPath "$Output\artifacts.json" -Raw | ConvertFrom-Json
if ($artifact.Passed -ne $true -or $artifact.CandidateCount -ne $candidates.Count -or
    $artifact.ParsedCount -ne $candidates.Count -or $candidates.Count -eq 0) {
    throw 'Native PE gate failed, including extensionless modules.'
}
$start = [Diagnostics.ProcessStartInfo]::new("$Root\usr\bin\bash.exe")
$start.UseShellExecute = $false
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.WorkingDirectory = $Output
$start.Environment['PATH'] = "$Root\usr\bin;$env:SystemRoot\System32"
foreach ($argument in @('--noprofile', '--norc', '-c',
    'set -e; enable -f /usr/lib/bash/print print; enable -f /usr/lib/bash/mkdir mkdir; print -r native-loadable-module-ok; mkdir module-created; [[ -d module-created ]]; printf "loadables-ready\n"; IFS= read -r unused || :')) {
    $start.ArgumentList.Add($argument)
}
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
[void]$process.Start()
$errorTask = $process.StandardError.ReadToEndAsync()
$lines = [Collections.Generic.List[string]]::new()
$result = [ordered]@{Passed=$false; ProcessId=$process.Id}
try {
    foreach ($expected in @('native-loadable-module-ok', 'loadables-ready')) {
        $lineTask = $process.StandardOutput.ReadLineAsync()
        if (-not $lineTask.Wait(10000)) { throw 'Module callback did not produce the expected completion marker.' }
        $line = $lineTask.GetAwaiter().GetResult()
        $lines.Add($line)
        if ($line -cne $expected) { throw "Incorrect native module output: $line" }
    }
    & ((Get-Process -Id $PID).Path) -NoProfile -File $ProcessGate -ProcessId $process.Id -ReportPath "$Output\process.json"
    if ($LASTEXITCODE -ne 0) { throw 'Native process identity failed.' }
    $modules = @((Get-Process -Id $process.Id).Modules | ForEach-Object {
        [ordered]@{Path=$_.FileName; SHA256=(Get-FileHash -LiteralPath $_.FileName).Hash.ToLowerInvariant()}
    })
    foreach ($name in @('print', 'mkdir')) {
        $expected = "$Root\usr\lib\bash\$name"
        $found = @($modules | Where-Object { $_.Path.TrimStart('\','?') -ieq $expected })
        if ($found.Count -ne 1 -or $found[0].SHA256 -ne (Get-FileHash -LiteralPath $expected).Hash.ToLowerInvariant()) {
            throw "Exact tested loadable module is not mapped: $name"
        }
    }
    $modules | ConvertTo-Json -Depth 5 | Set-Content "$Output\modules.json"
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(10000)) { throw 'Test shell did not exit after EOF.' }
    $remaining = $process.StandardOutput.ReadToEnd()
    $errors = $errorTask.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0 -or $remaining -ne '' -or $errors -ne '') {
        throw 'Module fixture exited unsuccessfully or emitted unexpected output.'
    }
    $result.Passed = $true
}
finally {
    if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
    $result.ExitCode = $process.ExitCode
    $result.Lines = $lines.ToArray()
    $result.Stderr = $errorTask.GetAwaiter().GetResult()
    $result.DirectoryCreated = Test-Path -LiteralPath "$Output\module-created" -PathType Container
    $result.Scope = 'Two real native Bash loadable callbacks and exact mapped module bytes; all module PE headers gated'
    $result | ConvertTo-Json -Depth 5 | Set-Content "$Output\result.json"
    $process.Dispose()
}
