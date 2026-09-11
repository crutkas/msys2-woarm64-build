#requires -Version 7.3
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\iconv-current-d70-v2',
    [string]$ProducerHandoff = 'C:\ag-bash-e138-01\iconv-provider-handoff-01\handoff.json',
    [string]$PinnedRecipe = 'C:\ag-bash-e138-01\sources\libiconv\PKGBUILD',
    [string]$BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string]$RuntimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll',
    [string]$LibiconvRoot = 'C:\ap11-native-provider-intake\libiconv-current-d70-v1',
    [string]$GettextRoot = 'C:\ap11-native-provider-intake\gettext-runtime-relocatable-v2',
    [string]$ToolchainBin = 'C:\agtc-libs-01\sdk\bin',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$CompressionPolicyHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json',
    [string]$CompressionPolicyRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$handoffPin = '5bb7d82ef4778c56ad4e8319bbd325a8246a26536c16b40c4f8e81cfa9be7602'
$inventoryPin = '4521085ee06d413021c444924fb21b280e031f574c3ce35ac584de519c1b6b7a'
$resultPin = '41a7d7394e489ef14dfc0702185e00a038b0c7e63e8865cd57dff2af8348b7d8'
$recipePin = '72144bedfb5efa0b492c27cde22918e14c0745896e624ab063c735e2bb516c7c'
$runtimePin = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$iconvExePin = '5fc974e03a6c2a4bd25850e23876ee3503565bb77c72118fe7dde0f8f10fbca5'
$supersededIconvPin = '1354cb317c75b52db5f2e0d808d6612a561f93cbbafe0e2900d090e061acc8fc'
$admittedIconvDllPin = '86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215'
$admittedCharsetDllPin = '0d6c999892ae10d3e173792596ef4653514777eebddb75015868a9056e6f7d73'
$intlDllPin = '44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c'

if (-not $CompressionPolicyRoot) {
    $CompressionPolicyRoot = Join-Path (
        Split-Path -Parent $PSScriptRoot
    ) 'native-packaging\compression-policy'
}

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Hash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "$Label changed: expected $Expected, got $actual"
    }
}

function Convert-ToMsysPath {
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to MSYS form: $resolved"
    }
    return "/$($Matches[1].ToLowerInvariant())/$($Matches[2] -replace '\\', '/')"
}

function Convert-ToCygdrivePath {
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to cygdrive form: $resolved"
    }
    return "/cygdrive/$($Matches[1].ToLowerInvariant())/$($Matches[2] -replace '\\', '/')"
}

function Invoke-IconvTransform {
    param(
        [Parameter(Mandatory)][string]$Iconv,
        [Parameter(Mandatory)][string]$From,
        [Parameter(Mandatory)][string]$To,
        [Parameter(Mandatory)][string]$InputPath,
        [Parameter(Mandatory)][string]$OutputPath,
        [Parameter(Mandatory)][string]$PathEnvironment,
        [Parameter(Mandatory)][string]$TempDirectory
    )

    $start = [Diagnostics.ProcessStartInfo]::new($Iconv)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment['PATH'] = $PathEnvironment
    $start.Environment['TEMP'] = $TempDirectory
    $start.Environment['TMP'] = $TempDirectory
    $start.Environment['TMPDIR'] = $TempDirectory
    foreach ($argument in @(
        '-f', $From, '-t', $To, (Convert-ToCygdrivePath $InputPath)
    )) {
        $start.ArgumentList.Add($argument)
    }
    $output = [IO.File]::Create($OutputPath)
    try {
        $process = [Diagnostics.Process]::Start($start)
        try {
            $copy = $process.StandardOutput.BaseStream.CopyToAsync($output)
            $errorText = $process.StandardError.ReadToEndAsync()
            $process.WaitForExit()
            $null = $copy.GetAwaiter().GetResult()
            $stderr = $errorText.GetAwaiter().GetResult()
            if ($process.ExitCode -ne 0) {
                throw "iconv transform failed with $($process.ExitCode): $stderr"
            }
        }
        finally {
            $process.Dispose()
        }
    }
    finally {
        $output.Dispose()
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
Assert-Hash $ProducerHandoff $handoffPin 'Canonical iconv provider handoff'
Assert-Hash $PinnedRecipe $recipePin 'Pinned MSYS2 libiconv recipe'
Assert-Hash $CompressionPolicyHandoff (
    '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
) 'Compression policy handoff'
foreach ($entry in ([ordered]@{
    'makepkg-compression-policy.sh' = 'a2e161767e4d9dea88768eac448170ec53981acb05efe06ad7064e2ddafc62d1'
    'makepkg-compression.sh' = '41bc1d98d912ddbca60f1a6369be0ee9f97959787dcf499eaee814a5f01406d6'
    'with-makepkg-compression.sh' = 'b3324cc71bb44ad74ed00064e420db90158fb9aa2da022667a7fe6eaa3e8571c'
}).GetEnumerator()) {
    Assert-Hash (
        Join-Path $CompressionPolicyRoot $entry.Key
    ) $entry.Value "Compression policy $($entry.Key)"
}

$handoff = Get-Content -Raw -LiteralPath $ProducerHandoff | ConvertFrom-Json
if ($handoff.schema -ne 1 -or
    $handoff.status -ne 'ready-for-provider-intake' -or
    $handoff.scope -notmatch 'relocatable GNU libiconv 1.19' -or
    $handoff.stage_inventory_sha256 -ne $inventoryPin -or
    $handoff.result_sha256 -ne $resultPin -or
    $handoff.iconv_exe_sha256 -ne $iconvExePin -or
    $handoff.forbidden_locale_prefix_hits -ne 0 -or
    $handoff.canonical_locale_literal -ne '/usr/share/locale' -or
    $handoff.supersedes_excluded_iconv_exe_sha256 -ne $supersededIconvPin) {
    throw 'Canonical iconv provider handoff identity is invalid.'
}
Assert-Hash $handoff.stage_inventory $inventoryPin 'Canonical iconv stage inventory'
Assert-Hash $handoff.result $resultPin 'Canonical iconv producer result'

$inventory = Get-Content -Raw -LiteralPath $handoff.stage_inventory | ConvertFrom-Json
$result = Get-Content -Raw -LiteralPath $handoff.result | ConvertFrom-Json
if ($inventory.schema -ne 1 -or
    $inventory.root -ne $handoff.stage -or
    $inventory.file_count -ne 65 -or
    $inventory.arm64_pe_count -ne 3 -or
    @($inventory.files).Count -ne 65 -or
    $result.status -ne 'qualified-relocatable-native-libiconv' -or
    $result.runtime_sha256 -ne $runtimePin -or
    $result.stage.inventory_sha256 -ne $inventoryPin -or
    $result.stage.file_count -ne 65 -or
    $result.stage.arm64_pe_count -ne 3 -or
    $result.stage.forbidden_locale_prefix_hits -ne 0 -or
    $result.stage.canonical_locale_literal -ne '/usr/share/locale' -or
    $result.stage.iconv_exe_sha256 -ne $iconvExePin -or
    $result.excluded_predecessor_sha256 -ne $supersededIconvPin -or
    $result.build.parent_raw_exit -ne 0 -or
    $result.build.created_processes -ne $result.build.observed_processes -or
    $result.build.unresolved_processes -ne 0 -or
    $result.build.unobserved_processes -ne 0 -or
    $result.build.make_check -ne 'passed' -or
    $result.qualification.parent_raw_exit -ne 0 -or
    $result.qualification.created_processes -ne
        $result.qualification.observed_processes -or
    $result.qualification.all_native_exits_zero -ne $true) {
    throw 'Canonical iconv stage or qualification result is invalid.'
}
foreach ($entry in $inventory.files) {
    Assert-Hash (
        Join-Path $handoff.stage ([string]$entry.path -replace '/', '\')
    ) ([string]$entry.sha256) "Canonical iconv stage payload $($entry.path)"
}

$sourceIconv = Join-Path $handoff.stage 'usr\bin\iconv.exe'
Assert-Hash $sourceIconv $iconvExePin 'Canonical iconv executable'
New-Item -ItemType Directory -Path (
    $output,
    "$output\recipe\payload\usr\bin",
    "$output\packages",
    "$output\readback",
    "$output\readback-runtime\usr\bin",
    "$output\readback-runtime\tmp",
    "$output\qualification"
) | Out-Null
Copy-Item -LiteralPath $sourceIconv -Destination "$output\recipe\payload\usr\bin\iconv.exe"
Assert-Hash "$output\recipe\payload\usr\bin\iconv.exe" $iconvExePin 'Copied iconv executable'
[IO.File]::WriteAllText(
    "$output\recipe\payload-files.sha256",
    "$iconvExePin  payload/usr/bin/iconv.exe`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\payload.tar" `
    -C "$output\recipe" payload
if ($LASTEXITCODE -ne 0) {
    throw 'Could not archive the qualified iconv payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\iconv\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Hash "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Hash "$output\recipe\payload-files.sha256"))
if ($recipe.Contains('@')) {
    throw 'Unresolved iconv package recipe token.'
}
[IO.File]::WriteAllText("$output\recipe\PKGBUILD", $recipe, [Text.UTF8Encoding]::new($false))

$bash = "$BootstrapRoot\usr\bin\bash.exe"
$msysOutput = Convert-ToMsysPath $output
$msysConfig = Convert-ToMsysPath $MakepkgConfig
$msysWrapper = Convert-ToMsysPath (Join-Path $CompressionPolicyRoot 'with-makepkg-compression.sh')
$oldPath = $env:PATH
try {
    $env:PATH = Split-Path -Parent $bash
    $command = @"
set -euo pipefail
export PATH=/usr/bin
export PKGDEST='$msysOutput/packages'
export BUILDDIR='$msysOutput/build'
export LOGDEST='$msysOutput/logs'
export WOARM64_JOBS=1
cd '$msysOutput/recipe'
/usr/bin/bash '$msysWrapper' /usr/bin/makepkg --config '$msysConfig' --check --cleanbuild --log --force --noconfirm
"@
    & $bash --noprofile --norc -c $command | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "makepkg failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PATH = $oldPath
}

$archive = @(Get-ChildItem "$output\packages" -File -Filter '*.pkg.tar.zst')
if ($archive.Count -ne 1) {
    throw "Expected one iconv package archive, found $($archive.Count)"
}
$pkginfo = (& tar -xOf $archive[0].FullName '.PKGINFO') -join "`n"
foreach ($line in @(
    'pkgname = iconv',
    'pkgver = 1.19-1',
    'depend = gcc-libs',
    'depend = libiconv=1.19',
    'depend = libintl',
    'conflict = libiconv<1.18-2',
    'license = spdx:GPL-3.0-only AND LGPL-2.1-only'
)) {
    if ($pkginfo -notmatch [regex]::Escape($line)) {
        throw "iconv .PKGINFO is missing: $line"
    }
}
& tar -xf $archive[0].FullName -C "$output\readback"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract packaged iconv.'
}
$packagedIconv = "$output\readback\usr\bin\iconv.exe"
Assert-Hash $packagedIconv $iconvExePin 'Packaged canonical iconv executable'

$strings = Join-Path $ToolchainBin 'aarch64-pc-cygwin-strings.exe'
$blockedPattern = '/msys64/usr/|/mingwarm64/bin|/mingwarm64/etc|/mingwarm64/share|/mingwarm64/lib/tcl'
$blocked = @(& $strings -a $packagedIconv | Select-String -Pattern $blockedPattern)
if ($blocked.Count -ne 0) {
    throw 'Packaged iconv executable contains a blocked operational path.'
}
$canonical = @(& $strings -a $packagedIconv | Select-String -SimpleMatch '/usr/share/locale')
if ($canonical.Count -eq 0) {
    throw 'Packaged iconv executable does not contain canonical /usr/share/locale.'
}
$machine = @(
    & (Join-Path $ToolchainBin 'aarch64-pc-cygwin-objdump.exe') -f $packagedIconv |
        Select-String 'architecture:'
)
if ($machine -notmatch 'aarch64') {
    throw 'Packaged iconv executable is not ARM64.'
}

$dependencyBin = "$output\readback-runtime\usr\bin"
$admittedIconvDll = Join-Path $LibiconvRoot 'readback\usr\bin\msys-iconv-2.dll'
$admittedCharsetDll = Join-Path $LibiconvRoot 'readback\usr\bin\msys-charset-1.dll'
$intlDll = Join-Path $GettextRoot 'readback\libintl\usr\bin\msys-intl-8.dll'
Assert-Hash $RuntimeDll $runtimePin 'Current d70 runtime'
Assert-Hash $admittedIconvDll $admittedIconvDllPin 'Admitted libiconv DLL'
Assert-Hash $admittedCharsetDll $admittedCharsetDllPin 'Admitted libcharset DLL'
Assert-Hash $intlDll $intlDllPin 'Admitted libintl DLL'
Copy-Item -LiteralPath (
    $RuntimeDll,
    $admittedIconvDll,
    $admittedCharsetDll,
    $intlDll,
    $packagedIconv
) -Destination $dependencyBin

$runtimeIconv = Join-Path $dependencyBin 'iconv.exe'
$runtimePath = "$dependencyBin;C:\Windows\System32"
$oldPath = $env:PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpdir = $env:TMPDIR
try {
    $env:PATH = $runtimePath
    $env:TEMP = "$output\readback-runtime\tmp"
    $env:TMP = $env:TEMP
    $env:TMPDIR = $env:TEMP
    $versionOutput = @(& $runtimeIconv --version 2>&1)
    if ($LASTEXITCODE -ne 0 -or
        ($versionOutput -join "`n") -notmatch 'iconv \(GNU libiconv 1\.19\)') {
        throw "Packaged iconv version readback failed: $($versionOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpdir
}

$inputFile = "$output\qualification\utf8.txt"
$utf16File = "$output\qualification\utf16le.bin"
$roundTripFile = "$output\qualification\roundtrip.txt"
$inputBytes = [Text.UTF8Encoding]::new($false).GetBytes("native iconv: café 日本語`n")
[IO.File]::WriteAllBytes($inputFile, $inputBytes)
Invoke-IconvTransform -Iconv $runtimeIconv -From 'UTF-8' -To 'UTF-16LE' `
    -InputPath $inputFile -OutputPath $utf16File -PathEnvironment $runtimePath `
    -TempDirectory "$output\readback-runtime\tmp"
Invoke-IconvTransform -Iconv $runtimeIconv -From 'UTF-16LE' -To 'UTF-8' `
    -InputPath $utf16File -OutputPath $roundTripFile -PathEnvironment $runtimePath `
    -TempDirectory "$output\readback-runtime\tmp"
$inputHash = Get-Hash $inputFile
$roundTripHash = Get-Hash $roundTripFile
if ($inputHash -ne $roundTripHash) {
    throw 'Packaged iconv UTF-8/UTF-16LE round-trip changed the input bytes.'
}

$package = [ordered]@{
    name = 'iconv'
    path = $archive[0].FullName
    sha256 = Get-Hash $archive[0].FullName
}
$export = "$output\export.json"
[ordered]@{
    schema = 1
    status = 'admitted-qualified-current-d70-native-msys-iconv-exported'
    provider = 'native-msys-iconv'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $runtimePin
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = @($package)
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $export -Encoding utf8NoBOM

$supersession = "$output\excluded-iconv-superseding-disposition.json"
[ordered]@{
    schema = 1
    status = 'excluded-private-prefix-iconv-superseded-by-canonical-provider'
    excluded_predecessor = [ordered]@{
        sha256 = $supersededIconvPin
        reused = $false
        relabeled = $false
    }
    replacement = [ordered]@{
        path = 'usr/bin/iconv.exe'
        sha256 = $iconvExePin
        canonical_locale = '/usr/share/locale'
        blocked_operational_paths = @()
    }
    provider_export = [ordered]@{ path = $export; sha256 = Get-Hash $export }
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $supersession -Encoding utf8NoBOM

$handoffPath = "$output\handoff.json"
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-msys-iconv-packaged'
    provider_export = [ordered]@{ path = $export; sha256 = Get-Hash $export }
    producer_handoff = [ordered]@{
        path = $ProducerHandoff
        sha256 = $handoffPin
    }
    package = $package
    exact_binary = [ordered]@{
        path = 'usr/bin/iconv.exe'
        sha256 = $iconvExePin
        modified_by_intake = $false
    }
    dependency_readback = [ordered]@{
        runtime_sha256 = $runtimePin
        libiconv_sha256 = $admittedIconvDllPin
        libcharset_sha256 = $admittedCharsetDllPin
        libintl_sha256 = $intlDllPin
        existing_admitted_libiconv_superseded = $false
        version = $versionOutput
        utf8_utf16le_roundtrip = 'passed'
        utf8_input_sha256 = $inputHash
        utf8_roundtrip_sha256 = $roundTripHash
    }
    supersession = [ordered]@{
        path = $supersession
        sha256 = Get-Hash $supersession
    }
    controls = [ordered]@{
        source_rebuilt_by_intake = $false
        producer_stage_modified = $false
        iconv_executable_modified = $false
        old_excluded_iconv_reused = $false
        existing_admitted_libiconv_repackaged = $false
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $archive[0].FullName, $export, $supersession, $handoffPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
