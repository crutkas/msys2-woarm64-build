#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $NativePython,
    [Parameter(Mandatory)][string] $FixtureExecutable,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [switch] $MsysTarget
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Package exit-control output must be new.' }
New-Item -ItemType Directory -Path "$OutputDirectory\recipe" | Out-Null
Copy-Item -LiteralPath $FixtureExecutable -Destination "$OutputDirectory\recipe\exit-status.exe"
$template = [IO.File]::ReadAllText("$PSScriptRoot\native-exit-package\PKGBUILD.in").Replace("`r`n","`n")
$template = $template.Replace('@EXE_SHA256@',(Get-FileHash -LiteralPath $FixtureExecutable).Hash.ToLowerInvariant())
[IO.File]::WriteAllText("$OutputDirectory\recipe\PKGBUILD",$template,[Text.UTF8Encoding]::new($false))
$saved = $env:CONTROL_NATIVE_EXIT
$savedUnrelayed = $env:CONTROL_UNRELAYED
$runs = @()
try {
    foreach ($case in @(@{Name='exit-0';Code=0;Unrelayed=$false},@{Name='exit-1536';Code=1536;Unrelayed=$false},
        @{Name='unrelayed-1536';Code=1536;Unrelayed=$true})) {
        $code = $case.Code
        $env:CONTROL_NATIVE_EXIT = "$code"
        $env:CONTROL_UNRELAYED = if ($case.Unrelayed) { '1' } else { '0' }
        $destination = "$OutputDirectory\$($case.Name)"
        $arguments = @{
            MsysRoot=$MsysRoot;Prefix=$Prefix;NativePython=$NativePython
            PackageDirectory="$OutputDirectory\recipe";OutputDirectory=$destination;Jobs=1
        }
        if ($MsysTarget) {
            $script = "$PSScriptRoot\..\.github\scripts\msys\invoke-package.ps1"
            $arguments.Manifest = $Manifest
        } else {
            $script = "$PSScriptRoot\..\.github\scripts\invoke-native-package.ps1"
            $arguments.CohortManifest = $Manifest
            $arguments.CacheDirectory = "$OutputDirectory\cache"
        }
        $rejected = $false
        try { $null = & $script @arguments } catch {
            if ($code -eq 0 -or $_.Exception.Message -notmatch '^(MSYS package|Package build) failed \(') { throw }
            $rejected = $true
        }
        if (($code -ne 0) -ne $rejected) { throw 'Package source did not preserve success/failure.' }
        $records = @(Get-ChildItem -LiteralPath "$destination\native-exits" -File -Filter '*.json' | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json })
        if ($case.Unrelayed) {
            $job = Get-Content -Raw -LiteralPath "$destination\native-job.json" | ConvertFrom-Json
            if ($records.Count -ne 0 -or $job.passed -ne $false -or $job.parent_raw_exit -ne 0 -or
                $job.unrelayed_high_exits.Count -ne 1 -or $job.unrelayed_high_exits[0].raw_exit -ne 1536) {
                throw 'Job monitor did not reject foreign-parent success after an unrelayed native failure.'
            }
            if (@(Get-ChildItem -LiteralPath "$destination\rejected-packages" -File -Filter '*.pkg.tar.*').Count -ne 1) {
                throw 'Unadmitted archive was not retained in quarantine.'
            }
        } elseif ($records.Count -ne 1 -or $records[0].raw_exit -ne $code -or
            $records[0].portable_exit -ne $(if ($code) { 255 } else { 0 })) {
            throw 'Package did not retain the exact raw native exit.'
        }
        $packages = @(Get-ChildItem -LiteralPath "$destination\packages" -File -Filter '*.pkg.tar.*')
        if (($code -eq 0 -and $packages.Count -ne 1) -or ($code -ne 0 -and $packages.Count)) {
            throw 'Package publication did not respect native target failure.'
        }
        $runs += @{RawExit=$code;Unrelayed=$case.Unrelayed;Rejected=$rejected;Records=$records;Packages=$packages.Count}
        "PASS: actual package raw native exit=$code; unrelayed=$($case.Unrelayed); rejected=$rejected"
    }
} finally { $env:CONTROL_NATIVE_EXIT = $saved; $env:CONTROL_UNRELAYED = $savedUnrelayed }
[ordered]@{Status='passed';MsysTarget=[bool]$MsysTarget;Runs=$runs;CompilationPerformed=$false} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$OutputDirectory\result.json" -Encoding utf8
