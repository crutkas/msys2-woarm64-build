param(
    [Parameter(Mandatory)][string]$Prefix,
    [Parameter(Mandatory)][string]$Iconv,
    [Parameter(Mandatory)][string]$Ssh,
    [Parameter(Mandatory)][string]$OpenSsl,
    [Parameter(Mandatory)][string]$Zlib,
    [string]$Gettext,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$ArtifactGate,
    [Parameter(Mandatory)][string]$ProcessGate
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Use new evidence output.' }
[void][IO.Directory]::CreateDirectory($Output)
$identities = @()
$stages = @($Iconv, $Ssh, $OpenSsl, $Zlib)
if ($Gettext) { $stages += $Gettext }
foreach ($stage in $stages) {
    foreach ($dll in Get-ChildItem -LiteralPath "$stage\bin" -Filter '*.dll' -File) {
        $destination = Join-Path $Output $dll.Name
        if (Test-Path -LiteralPath $destination) { throw "Conflicting dependency DLL: $destination" }
        Copy-Item -LiteralPath $dll.FullName -Destination $destination
        $hash = (Get-FileHash -LiteralPath $dll.FullName).Hash
        if ((Get-FileHash -LiteralPath $destination).Hash -ne $hash) { throw 'Copied DLL differs.' }
        $identities += [ordered]@{Source=$dll.FullName; Snapshot=$destination; SHA256=$hash}
    }
}
$source = Join-Path $PSScriptRoot 'fixtures\native-text-ssh-probe.c'
$executable = Join-Path $Output 'native-text-ssh-probe.exe'
$compileArguments = @('-O2', "-I$Iconv\include", "-I$Ssh\include", $source,
                      "$Iconv\lib\libiconv.dll.a", "$Ssh\lib\libssh2.dll.a", '-o', $executable)
if ($Gettext) { $compileArguments += @('-DTEST_LIBINTL', "-I$Gettext\include", "$Gettext\lib\libintl.dll.a") }
& "$Prefix\bin\gcc.exe" @compileArguments *> "$Output\compile.log"
if ($LASTEXITCODE -ne 0) { throw 'Native API probe compilation failed.' }
& $ArtifactGate -Root $Output -ReportPath "$Output\artifacts.json"
$artifact = Get-Content -LiteralPath "$Output\artifacts.json" -Raw | ConvertFrom-Json
if ($artifact.Passed -ne $true -or $artifact.CandidateCount -lt 1 -or
    $artifact.ParsedCount -ne $artifact.CandidateCount) { throw 'Native PE gate failed.' }
$start = [Diagnostics.ProcessStartInfo]::new($executable)
$start.UseShellExecute = $false
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.WorkingDirectory = $Output
$start.Environment.Clear()
$start.Environment['SystemRoot'] = $env:SystemRoot
$start.Environment['PATH'] = "$Output;$env:SystemRoot\System32"
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
[void]$process.Start()
$errors = $process.StandardError.ReadToEndAsync()
$report = [ordered]@{Passed=$false; Dlls=$identities; CompilerSHA256=(Get-FileHash "$Prefix\bin\gcc.exe").Hash}
try {
    $lineTask = $process.StandardOutput.ReadLineAsync()
    if (-not $lineTask.Wait(15000)) { throw 'Native API probe timed out.' }
    $report.Marker = $lineTask.GetAwaiter().GetResult()
    if ($report.Marker -cne 'native-text-ssh-api-ready') { throw 'Native API probe failed before readiness.' }
    & ((Get-Process -Id $PID).Path) -NoProfile -File $ProcessGate -ProcessId $process.Id -ReportPath "$Output\process.json"
    if ($LASTEXITCODE -ne 0) { throw 'Native process gate failed.' }
    $modules = @((Get-Process -Id $process.Id).Modules | ForEach-Object { $_.FileName.TrimStart('\','?') })
    $requiredModules = @('libiconv-2.dll','libssh2.dll','libcrypto-3.dll')
    if ($Gettext) { $requiredModules += 'libintl-8.dll' }
    foreach ($name in $requiredModules) {
        $mapped = @($modules | Where-Object {[IO.Path]::GetFileName($_) -ieq $name})
        if ($mapped.Count -ne 1 -or $mapped[0] -ine (Join-Path $Output $name)) {
            throw "Wrong mapped library: $name"
        }
    }
    $modules | ConvertTo-Json | Set-Content "$Output\modules.json"
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(10000)) { throw 'Native probe did not exit after EOF.' }
    if ($process.ExitCode -ne 0 -or $errors.GetAwaiter().GetResult() -ne '' -or
        $process.StandardOutput.ReadToEnd() -ne '') { throw 'Unexpected native probe result.' }
    foreach ($identity in $identities) {
        if ((Get-FileHash -LiteralPath $identity.Source).Hash -ne $identity.SHA256 -or
            (Get-FileHash -LiteralPath $identity.Snapshot).Hash -ne $identity.SHA256) {
            throw 'Library bytes changed during the native API probe.'
        }
    }
    $report.Passed = $true
}
finally {
    if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
    $report.ExitCode = $process.ExitCode
    $report.Stderr = $errors.GetAwaiter().GetResult()
    $report.Scope = 'Unicode conversion and invalid-input rejection; SSH session lifecycle and crypto/compression algorithm APIs; no SSH connection/authentication claim'
    if ($Gettext) { $report.GettextScope = 'Exact shared libintl Windows %I64u and standard uint64 formatting' }
    $report | ConvertTo-Json -Depth 6 | Set-Content "$Output\result.json"
    $process.Dispose()
}
