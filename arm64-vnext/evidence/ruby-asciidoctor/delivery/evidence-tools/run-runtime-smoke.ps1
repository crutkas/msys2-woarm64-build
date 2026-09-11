param([Parameter(Mandatory)][string] $Engine)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\Invoke-LeafProcess.ps1"
$root = 'C:\ar07-9047'
$output = "$root\evidence\runtime-smoke"
if (Test-Path -LiteralPath $output) { throw 'Runtime evidence directory must be new' }
New-Item -ItemType Directory -Path "$output\native-exits" -Force | Out-Null
$ruby = "$root\b\clangarm64\bin\ruby.exe"
$environment = @{
    PATH = "$root\b\clangarm64\bin;$env:SystemRoot\System32;$env:SystemRoot"
    WOARM64_NATIVE_PYTHON_SHA256 = '7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29'
    WOARM64_NATIVE_TEST_ROOT = "$root\b\clangarm64"
    WOARM64_NATIVE_EXIT_DIR = "$output\native-exits"
}
$start = New-LeafStartInfo -Executable 'C:\Program Files\Python314-arm64\python.exe' `
    -Arguments @('-I', "$Engine\native-target-exec.py", $ruby, "$PSScriptRoot\ruby-runtime-smoke.rb",
                 "$output\ready.json", "$output\release") -Environment $environment
$process = [Diagnostics.Process]::Start($start)
Write-Host "START native relay pid=$($process.Id) log=$output"
$stdout = [IO.File]::Create("$output\stdout.log")
$stderr = [IO.File]::Create("$output\stderr.log")
try {
    $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
    $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath "$output\ready.json")) {
        if ($process.HasExited) { throw 'Ruby exited before the native runtime handshake' }
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Ruby runtime handshake timed out' }
        Start-Sleep -Milliseconds 50
    }
    $ready = Get-Content -Raw "$output\ready.json" | ConvertFrom-Json
    $child = [Diagnostics.Process]::GetProcessById($ready.pid)
    try {
        if ($child.MainModule.FileName -ine $ruby) { throw 'Native handshake process identity mismatch' }
        $created = $child.StartTime.ToFileTimeUtc()
        $modules = @($child.Modules | ForEach-Object {
            $path = $_.FileName
            if ($path.StartsWith("$root\b\clangarm64\", [StringComparison]::OrdinalIgnoreCase)) {
                $identity = & "$Engine\assert-arm64-pe.ps1" -Path $path | ConvertFrom-Json
                [pscustomobject]@{Path=$path; Origin='signed-ruby-bootstrap'; Machine=$identity.machine; SHA256=$identity.sha256}
            } elseif ($path.StartsWith("$env:SystemRoot\", [StringComparison]::OrdinalIgnoreCase)) {
                [pscustomobject]@{Path=$path; Origin='Windows'; SHA256=(Get-FileHash $path).Hash.ToLowerInvariant()}
            } else {
                throw "Ruby loaded a module outside its private bootstrap and Windows: $path"
            }
        })
        if ($modules.Count -lt 2) { throw 'Incomplete live module observation' }
    } finally {
        $child.Dispose()
    }
    New-Item -ItemType File -Path "$output\release" | Out-Null
    if (-not $process.WaitForExit(30000)) { throw 'Native relay did not finish after release' }
    $null = $copyOut.GetAwaiter().GetResult()
    $null = $copyErr.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw "Native runtime relay failed: $($process.ExitCode)" }
    $records = @(Get-ChildItem "$output\native-exits" -File)
    if ($records.Count -ne 1) { throw 'Expected one native runtime exit receipt' }
    $exit = Get-Content -Raw $records[0].FullName | ConvertFrom-Json
    if ($exit.child_pid -ne $ready.pid -or $exit.child_created -ne $created -or $exit.raw_exit -ne 0) {
        throw 'Native exit receipt does not match the observed Ruby process generation'
    }
    $result = [ordered]@{
        Status='native-ruby-runtime-and-live-module-closure-passed'
        Runtime=$ready; NativeExit=$exit; Modules=$modules
        Observer='System.Diagnostics.Process.Modules, while native Ruby waits for an explicit release'
        ClearedEnvironment=$true; ModuleGenerationBound=$true
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content "$output\result.json" -Encoding utf8
    "PASS Ruby PID $($ready.pid), $($modules.Count) observed modules, raw exit 0"
} finally {
    if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
    $null = $copyOut.GetAwaiter().GetResult()
    $null = $copyErr.GetAwaiter().GetResult()
    $stdout.Dispose()
    $stderr.Dispose()
    $process.Dispose()
}
