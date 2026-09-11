#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $RecipeDirectory,
    [Parameter(Mandatory)][string] $IntegrationRoot,
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'

function Convert-ToMsysPath([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Only absolute drive paths are supported: $Path"
    }
    "/$($Matches[1].ToLowerInvariant())/$($Matches[2].Replace('\', '/'))"
}

$recipe = Get-Item -LiteralPath $RecipeDirectory
$integration = Get-Item -LiteralPath $IntegrationRoot
$pkgbuild = "$($recipe.FullName)\PKGBUILD"
$preparation = "$($recipe.FullName)\preparation.json"
$baseConfig = "$($integration.FullName)\etc\makepkg_mingw.conf"
$bash = "$($integration.FullName)\usr\bin\bash.exe"
$makepkg = "$($integration.FullName)\usr\bin\makepkg"
foreach ($required in $pkgbuild, $preparation, $baseConfig, $bash, $makepkg) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Gettext makepkg prerequisite is missing: $required"
    }
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw 'Gettext package build output must be new.'
}
if ((Get-Content $pkgbuild -Raw) -notmatch '(?m)^pkgname=mingw-w64-aarch64-gettext$' -or
    (Get-Content $pkgbuild -Raw) -notmatch '(?m)^pkgver=1\.0$' -or
    (Get-Content $pkgbuild -Raw) -notmatch '(?m)^pkgrel=1$') {
    throw 'Prepared gettext recipe does not declare the truthful 1.0-1 identity.'
}

New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$config = "$OutputDirectory\makepkg-gettext.conf"
Copy-Item $baseConfig $config
$outputMsys = Convert-ToMsysPath $OutputDirectory
$canonicalStartDirectory = "$($integration.FullName)\tmp\gettext-package-1.0-1"
if (Test-Path -LiteralPath $canonicalStartDirectory) {
    throw 'Canonical gettext makepkg start directory must be new.'
}
Copy-Item -LiteralPath $recipe.FullName -Destination $canonicalStartDirectory -Recurse
Add-Content $config @"

# Canonical package-build paths for relocatable metadata.
MAKEFLAGS="-j1"
BUILDDIR=/tmp/gettext-package-build-1.0-1
PKGDEST=$outputMsys
"@

$recipeMsys = '/tmp/gettext-package-1.0-1'
$configMsys = Convert-ToMsysPath $config
$command = @"
set -euo pipefail
export MSYSTEM=MINGWARM64 CHERE_INVOKING=1
cd '$recipeMsys'
makepkg --config '$configMsys' --noconfirm --cleanbuild --clean --force
"@
try {
    $output = @(& $bash -lc $command 2>&1)
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $canonicalStartDirectory -Recurse -Force
}
$output | Set-Content "$OutputDirectory\makepkg.log" -Encoding utf8
if ($exitCode -ne 0) {
    throw "Gettext makepkg failed with exit code $exitCode."
}

$archives = @(Get-ChildItem $OutputDirectory -Filter 'mingw-w64-aarch64-gettext-1.0-1-*.pkg.tar.zst')
if ($archives.Count -ne 1) {
    throw 'Gettext makepkg did not produce exactly one truthful package archive.'
}
$archive = $archives[0]
$entries = @(& "$env:SystemRoot\System32\tar.exe" --zstd -tf $archive.FullName)
if ($LASTEXITCODE -ne 0) { throw 'Cannot list the gettext package archive.' }
foreach ($entry in '.PKGINFO', '.BUILDINFO', '.MTREE') {
    if ($entry -cnotin $entries) { throw "Gettext package is missing $entry." }
}
$buildInfo = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $archive.FullName .BUILDINFO)
if ($LASTEXITCODE -ne 0 -or
    'builddir = /tmp/gettext-package-build-1.0-1' -cnotin $buildInfo -or
    'startdir = /tmp/gettext-package-1.0-1' -cnotin $buildInfo) {
    throw 'Gettext package does not contain the canonical makepkg build directory.'
}
if ($buildInfo -match 'C:\\ap|C:/ap|/c/ap|\.copilot|session-state') {
    throw 'Gettext package build metadata contains a private producer path.'
}

$receipt = [ordered]@{
    schema = 1
    status = 'truthful-gettext-1.0-1-makepkg-complete'
    package = [ordered]@{
        path = $archive.FullName
        sha256 = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    recipe = [ordered]@{
        path = $pkgbuild
        sha256 = (Get-FileHash $pkgbuild -Algorithm SHA256).Hash.ToLowerInvariant()
        preparationReceipt = $preparation
        preparationReceiptSha256 =
            (Get-FileHash $preparation -Algorithm SHA256).Hash.ToLowerInvariant()
        appliedPatches = @()
    }
    makepkg = [ordered]@{
        config = $config
        configSha256 = (Get-FileHash $config -Algorithm SHA256).Hash.ToLowerInvariant()
        log = "$OutputDirectory\makepkg.log"
        logSha256 =
            (Get-FileHash "$OutputDirectory\makepkg.log" -Algorithm SHA256).Hash.ToLowerInvariant()
        startDirectory = '/tmp/gettext-package-1.0-1'
        buildDirectory = '/tmp/gettext-package-build-1.0-1'
        jobs = 1
    }
}
$receipt | ConvertTo-Json -Depth 7 |
    Set-Content "$OutputDirectory\package-build.json" -Encoding utf8
$receipt
