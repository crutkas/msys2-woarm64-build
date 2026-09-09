#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $Stage = 'C:\ag-bash-e138-01\gettext-runtime-01\stage',
    [string] $Inventory = 'C:\ag-bash-e138-01\gettext-runtime-01\stage.inventory.json',
    [string] $ProducerResult = 'C:\ag-bash-e138-01\gettext-runtime-01\result.json',
    [string] $BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string] $MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$inventoryPin = '675e3b358606700dea6d3627b1677dfc7d8f5c95a3163101fe240b4c1c6124ca'
$producerPin = '3fd5d56dc2b9fa06ef936864eabc983c72bef45d9025f37fa13385da94514303'

function Get-Sha256([string] $Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Pin([string] $Path, [string] $Expected, [string] $Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
        throw "$Label changed: expected $Expected, got $actual"
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
Assert-Pin $Inventory $inventoryPin 'Qualified gettext runtime inventory'
Assert-Pin $ProducerResult $producerPin 'Qualified gettext runtime producer result'
if (-not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\bash.exe" -PathType Leaf) -or
    -not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\makepkg" -PathType Leaf)) {
    throw "Packaging bootstrap is incomplete: $BootstrapRoot"
}
if (-not (Test-Path -LiteralPath $MakepkgConfig -PathType Leaf)) {
    throw "ARM64 makepkg configuration is missing: $MakepkgConfig"
}

$inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json -AsHashtable
$producer = Get-Content -Raw -LiteralPath $ProducerResult | ConvertFrom-Json -AsHashtable
if ($producer.get_Item('status') -cne 'native-NLS-component-built-upstream-checked-consumer-proof-pending' -or
    $producer.get_Item('profile') -cne 'gettext-runtime' -or
    $producer.get_Item('nls_enabled') -ne $true -or
    $inventoryData.get_Item('profile') -cne 'gettext-runtime' -or
    $inventoryData.get_Item('nls_enabled') -ne $true) {
    throw 'The supplied stage is not the pinned gettext runtime result.'
}

$sourceFiles = @($inventoryData.get_Item('files').GetEnumerator() | Sort-Object Key)
if ($sourceFiles.Count -ne 101) {
    throw "Qualified gettext runtime inventory changed file count: $($sourceFiles.Count)"
}
foreach ($entry in $sourceFiles) {
    $path = Join-Path $Stage $entry.Key.Replace('/', '\')
    Assert-Pin $path $entry.Value.get_Item('sha256') "Qualified gettext payload $($entry.Key)"
}

New-Item -ItemType Directory -Path $output, "$output\recipe", "$output\packages" | Out-Null
Copy-Item -LiteralPath $Stage -Destination "$output\recipe\payload" -Recurse
foreach ($entry in $sourceFiles) {
    $path = Join-Path "$output\recipe\payload" $entry.Key.Replace('/', '\')
    Assert-Pin $path $entry.Value.get_Item('sha256') "Copied gettext payload $($entry.Key)"
}

$hashLines = $sourceFiles | ForEach-Object {
    "$($_.Value.get_Item('sha256'))  payload/$($_.Key)"
}
[IO.File]::WriteAllText(
    "$output\recipe\payload-files.sha256",
    ($hashLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\payload.tar" -C "$output\recipe" payload
if ($LASTEXITCODE) {
    throw 'Could not archive the qualified gettext runtime payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\gettext-runtime\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Sha256 "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Sha256 "$output\recipe\payload-files.sha256"))
if ($recipe.Contains('@')) {
    throw 'Unresolved gettext package recipe token.'
}
[IO.File]::WriteAllText("$output\recipe\PKGBUILD", $recipe, [Text.UTF8Encoding]::new($false))

$start = [Diagnostics.ProcessStartInfo]::new("$BootstrapRoot\usr\bin\bash.exe")
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.WorkingDirectory = "$output\recipe"
$start.Environment['INTAKE_ROOT'] = $output
$start.Environment['INTAKE_CONFIG'] = [IO.Path]::GetFullPath($MakepkgConfig)
$start.ArgumentList.Add('--noprofile')
$start.ArgumentList.Add('--norc')
$start.ArgumentList.Add('-lc')
$start.ArgumentList.Add(@'
set -euo pipefail
export PATH=/usr/bin
root=$(cygpath -u "$INTAKE_ROOT")
config=$(cygpath -u "$INTAKE_CONFIG")
cd "$root/recipe"
export PKGDEST="$root/packages"
export SRCDEST="$root/sources"
export SRCPKGDEST="$root/source-packages"
export LOGDEST="$root/logs"
export BUILDDIR="$root/build"
export CCACHE_DIR="$root/ccache"
makepkg --config "$config" --check --cleanbuild --log --force --noconfirm
'@)
$stdout = [IO.File]::Create("$output\makepkg.stdout.log")
$stderr = [IO.File]::Create("$output\makepkg.stderr.log")
try {
    $process = [Diagnostics.Process]::Start($start)
    try {
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        $null = $copyOut.GetAwaiter().GetResult()
        $null = $copyErr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "makepkg failed with exit code $($process.ExitCode)"
        }
    } finally {
        $process.Dispose()
    }
} finally {
    $stdout.Dispose()
    $stderr.Dispose()
}

$packages = @(Get-ChildItem -LiteralPath "$output\packages" -File -Filter '*.pkg.tar.zst' | Sort-Object Name)
$expectedNames = @('libasprintf', 'libintl')
if ($packages.Count -ne $expectedNames.Count) {
    throw "Expected two gettext runtime package archives, found $($packages.Count)."
}
$exports = foreach ($package in $packages) {
    $name = ($package.Name -replace '-0\.22\.5-1-aarch64\.pkg\.tar\.zst$', '')
    if ($name -cnotin $expectedNames) {
        throw "Unexpected gettext runtime package archive: $($package.Name)"
    }
    [ordered]@{
        name = $name
        path = "packages/$($package.Name)"
        sha256 = Get-Sha256 $package.FullName
    }
}

[ordered]@{
    schema = 1
    status = 'admitted-qualified-native-msys-gettext-runtime-exported'
    packages = @($exports)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\export.json" -Encoding utf8

[ordered]@{
    schema = 1
    status = 'qualified-native-msys-gettext-runtime-packaged'
    source = [ordered]@{
        stage = [IO.Path]::GetFullPath($Stage)
        inventory = [ordered]@{ path = [IO.Path]::GetFullPath($Inventory); sha256 = $inventoryPin }
        producer_result = [ordered]@{ path = [IO.Path]::GetFullPath($ProducerResult); sha256 = $producerPin }
        recipe_commit = '24db315ff3601c2b69f3e348a48a3eff2e7380c3'
        version = '0.22.5-1'
    }
    payload = [ordered]@{
        source_stage_files = $sourceFiles.Count
        packaged_files = 2
        binary_hashes_unchanged = $true
        package_ownership = [ordered]@{
            libintl = 'usr/bin/msys-intl-8.dll'
            libasprintf = 'usr/bin/msys-asprintf-0.dll'
        }
    }
    packages = @($exports)
    limitations = @(
        'Only the independently owned runtime library splits are packaged; gettext tools are not admitted.',
        'Producer status retains consumer-proof-pending wording.',
        'Stage was qualified against runtime 1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16, not d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d.'
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\handoff.json" -Encoding utf8

[pscustomobject]@{
    Export = "$output\export.json"
    ExportSHA256 = Get-Sha256 "$output\export.json"
    Handoff = "$output\handoff.json"
    HandoffSHA256 = Get-Sha256 "$output\handoff.json"
    Packages = $packages.Count
}
