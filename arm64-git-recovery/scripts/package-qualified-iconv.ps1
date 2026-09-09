#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $Stage = 'C:\ag-bash-e138-01\iconv-full-recovery-02\stage',
    [string] $Inventory = 'C:\ag-bash-e138-01\iconv-full-recovery-02\stage.inventory.json',
    [string] $ProducerResult = 'C:\ag-bash-e138-01\iconv-full-recovery-02\result.json',
    [string] $BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string] $MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$pins = [ordered]@{
    inventory = 'ade429de6ca8ea1c6da0e9937ba4d52be1dc1b2250a04ed0901659b4c72635ca'
    producer_result = '44839c2e10f7a4efe9e0e5824588c807378f84368c684c4631acc459353d2b16'
}

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
Assert-Pin $Inventory $pins.inventory 'Qualified iconv inventory'
Assert-Pin $ProducerResult $pins.producer_result 'Qualified iconv producer result'
if (-not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\bash.exe" -PathType Leaf) -or
    -not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\makepkg" -PathType Leaf)) {
    throw "Packaging bootstrap is incomplete: $BootstrapRoot"
}
if (-not (Test-Path -LiteralPath $MakepkgConfig -PathType Leaf)) {
    throw "ARM64 makepkg configuration is missing: $MakepkgConfig"
}

$inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json -AsHashtable
$producer = Get-Content -Raw -LiteralPath $ProducerResult | ConvertFrom-Json -AsHashtable
$producerStatus = $producer.get_Item('status')
$producerProfile = $producer.get_Item('profile')
$producerNls = $producer.get_Item('nls_enabled')
$inventoryProfile = $inventoryData.get_Item('profile')
$inventoryNls = $inventoryData.get_Item('nls_enabled')
if ($producerStatus -cne 'native-NLS-component-built-upstream-checked-consumer-proof-pending' -or
    $producerProfile -cne 'iconv-full' -or
    $producerNls -ne $true -or
    $inventoryProfile -cne 'iconv-full' -or
    $inventoryNls -ne $true) {
    throw 'The supplied stage is not the pinned full-NLS iconv result.'
}

$sourceFiles = @($inventoryData.get_Item('files').GetEnumerator() | Sort-Object Key)
if ($sourceFiles.Count -ne 65) {
    throw "Qualified iconv inventory changed file count: $($sourceFiles.Count)"
}
foreach ($entry in $sourceFiles) {
    $path = Join-Path $Stage $entry.Key.Replace('/', '\')
    Assert-Pin $path $entry.Value.get_Item('sha256') "Qualified iconv payload $($entry.Key)"
}

New-Item -ItemType Directory -Path $output, "$output\recipe", "$output\packages" | Out-Null
Copy-Item -LiteralPath $Stage -Destination "$output\recipe\payload" -Recurse
foreach ($entry in $sourceFiles) {
    $path = Join-Path "$output\recipe\payload" $entry.Key.Replace('/', '\')
    Assert-Pin $path $entry.Value.get_Item('sha256') "Copied iconv payload $($entry.Key)"
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
    throw 'Could not archive the qualified iconv payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\iconv-full\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Sha256 "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Sha256 "$output\recipe\payload-files.sha256"))
if ($recipe.Contains('@')) {
    throw 'Unresolved iconv package recipe token.'
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
$expectedNames = @('iconv', 'libiconv', 'libiconv-devel')
if ($packages.Count -ne $expectedNames.Count) {
    throw "Expected three iconv package archives, found $($packages.Count)."
}
$exports = foreach ($package in $packages) {
    $name = ($package.Name -replace '-1\.19-1-aarch64\.pkg\.tar\.zst$', '')
    if ($name -cnotin $expectedNames) {
        throw "Unexpected iconv package archive: $($package.Name)"
    }
    [ordered]@{
        name = $name
        path = "packages/$($package.Name)"
        sha256 = Get-Sha256 $package.FullName
    }
}

$export = [ordered]@{
    schema = 1
    status = 'admitted-qualified-native-msys-iconv-full-exported'
    packages = @($exports)
}
$export | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\export.json" -Encoding utf8

$handoff = [ordered]@{
    schema = 1
    status = 'qualified-native-msys-iconv-full-packaged'
    source = [ordered]@{
        stage = [IO.Path]::GetFullPath($Stage)
        inventory = [ordered]@{ path = [IO.Path]::GetFullPath($Inventory); sha256 = $pins.inventory }
        producer_result = [ordered]@{ path = [IO.Path]::GetFullPath($ProducerResult); sha256 = $pins.producer_result }
        recipe_commit = '21bfc351a0c20d4f7dd2c564456d99ed69395a18'
        version = '1.19-1'
    }
    payload = [ordered]@{
        files = $sourceFiles.Count
        nls_enabled = $true
        binary_hashes_unchanged = $true
        package_ownership = [ordered]@{
            libiconv = 'usr/bin/*.dll and usr/share/**'
            iconv = 'usr/bin/iconv.exe'
            'libiconv-devel' = 'usr/include/** and usr/lib/** except usr/lib/charset.alias'
        }
    }
    packages = @($exports)
    limitations = @(
        'Producer status retains consumer-proof-pending wording.',
        'Stage was qualified against runtime 1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16, not d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d.',
        'No full gettext-tools or distribution admission is claimed.'
    )
}
$handoff | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\handoff.json" -Encoding utf8

[pscustomobject]@{
    Export = "$output\export.json"
    ExportSHA256 = Get-Sha256 "$output\export.json"
    Handoff = "$output\handoff.json"
    HandoffSHA256 = Get-Sha256 "$output\handoff.json"
    Packages = $packages.Count
}
