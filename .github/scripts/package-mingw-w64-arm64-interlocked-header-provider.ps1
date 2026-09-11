param(
    [Parameter(Mandatory = $true)]
    [string]$Bash,

    [Parameter(Mandatory = $true)]
    [string]$HostUsrBin,

    [Parameter(Mandatory = $true)]
    [string]$TargetBin,

    [Parameter(Mandatory = $true)]
    [string]$NativeFind,

    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,

    [Parameter(Mandatory = $true)]
    [string]$ProviderArchive,

    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'

$sourceCommit = '70d63e7c9a477b8b275a9782b289fbf1614b6e9e'
$providerArchiveSha = '8fd7777c31ded48e217d2b102c5ce21b063c04b4da1df04f51b2f9c3fab00b65'
$patchedHeaderSha = '8e0d3b2f2f94969faf166d8d9a0d4eb5e358a32be6bd7e99fc76e552ebfc909a'
$packageName = 'mingw-w64-aarch64-headers-git'
$packageVersion = '70d63e7c9-2'
$licenseInputs = [ordered]@{
    'COPYING' = '99a69660981156c21336fdb5661f89341b013c94e4bf9e1c7467b4745718397f'
    'DISCLAIMER' = '039ed6b4f31bb7fb97e733170b58cc435335352e4745734fcfd113877fdaf340'
    'COPYING.MinGW-w64\COPYING.MinGW-w64.txt' = 'f38e6194bd3bfa1b654f118e5acefe0aead437bbe669eee43957ccc65a7127f1'
    'COPYING.MinGW-w64-runtime\COPYING.MinGW-w64-runtime.txt' = 'e9b2dc02451ea29092a1f25fa0f3c07207ed421f1807dffb0c4e6dce69dee7bd'
}

$scriptDirectory = Split-Path -Parent $PSCommandPath
$prepareMakepkg = Join-Path $scriptDirectory 'prepare-native-makepkg-library.sh'
$repackage = Join-Path $scriptDirectory 'repackage-native-mingw-with-d70-find.sh'
$codegenTest = Join-Path $scriptDirectory 'test-mingw-w64-arm64-interlocked-exchange-ordering.ps1'
$runtimeTest = Join-Path $scriptDirectory 'test-mingw-w64-arm64-interlocked-exchange-runtime.ps1'
$makepkgLibrary = Join-Path (Split-Path -Parent $HostUsrBin) 'share\makepkg'
$compiler = Join-Path $TargetBin 'aarch64-w64-mingw32-gcc.exe'

function ConvertTo-MsysPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $converted = (& $Bash -c 'cygpath -u "$1"' -- $Path).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($converted)) {
        throw "Could not convert path for MSYS: $Path"
    }
    return $converted
}

function Read-GzipText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $inputStream = [System.IO.File]::OpenRead($Path)
    try {
        $gzipStream = [System.IO.Compression.GZipStream]::new(
            $inputStream,
            [System.IO.Compression.CompressionMode]::Decompress)
        $reader = [System.IO.StreamReader]::new(
            $gzipStream,
            [System.Text.Encoding]::UTF8)
        return $reader.ReadToEnd()
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
        elseif ($null -ne $gzipStream) {
            $gzipStream.Dispose()
        }
        else {
            $inputStream.Dispose()
        }
    }
}

function Write-GzipText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $outputStream = [System.IO.File]::Create($Path)
    try {
        $gzipStream = [System.IO.Compression.GZipStream]::new(
            $outputStream,
            [System.IO.Compression.CompressionLevel]::Optimal)
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)
        $gzipStream.Write($bytes, 0, $bytes.Length)
    }
    finally {
        if ($null -ne $gzipStream) {
            $gzipStream.Dispose()
        }
        else {
            $outputStream.Dispose()
        }
    }
}

if (Test-Path $OutputRoot) {
    throw "Refusing to overwrite output root: $OutputRoot"
}

$actualArchiveSha = (Get-FileHash $ProviderArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualArchiveSha -ne $providerArchiveSha) {
    throw "Unexpected header provider archive identity: $actualArchiveSha"
}

$actualCommit = (& git -C $SourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $sourceCommit) {
    throw "Unexpected MinGW-w64 source commit: $actualCommit"
}

$changedPaths = @(& git -C $SourceRoot diff --name-only)
if ($LASTEXITCODE -ne 0 -or
    $changedPaths.Count -ne 1 -or
    $changedPaths[0] -ne 'mingw-w64-headers/include/psdk_inc/intrin-impl.h') {
    throw "Unexpected MinGW-w64 source delta: $($changedPaths -join ', ')"
}

$sourceHeader = Join-Path $SourceRoot 'mingw-w64-headers\include\psdk_inc\intrin-impl.h'
$actualHeaderSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHeaderSha -ne $patchedHeaderSha) {
    throw "Unexpected patched header identity: $actualHeaderSha"
}

foreach ($entry in $licenseInputs.GetEnumerator()) {
    $path = Join-Path $SourceRoot $entry.Key
    $actual = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw "Unexpected license identity for $($entry.Key): $actual"
    }
}

$recipeRoot = Join-Path $OutputRoot 'recipe'
$sourceDirectory = Join-Path $recipeRoot 'src'
$packageDirectory = Join-Path $recipeRoot "pkg\$packageName"
$packageDestination = Join-Path $OutputRoot 'packages'
$readbackRoot = Join-Path $OutputRoot 'readback'
$controlsRoot = Join-Path $OutputRoot 'controls'
$privateMakepkgLibrary = Join-Path $OutputRoot 'makepkg-library'
$normalizationRoot = Join-Path $OutputRoot 'normalized-package'
New-Item -ItemType Directory -Path $sourceDirectory, $packageDirectory,
    $packageDestination, $readbackRoot, $controlsRoot, $normalizationRoot | Out-Null

Copy-Item $ProviderArchive (Join-Path $sourceDirectory 'provider.tar.zst')
foreach ($entry in $licenseInputs.GetEnumerator()) {
    Copy-Item (Join-Path $SourceRoot $entry.Key) `
        (Join-Path $sourceDirectory ([System.IO.Path]::GetFileName($entry.Key)))
}

$pkgbuild = @'
pkgbase=mingw-w64-headers-git
pkgname="${MINGW_PACKAGE_PREFIX}-headers-git"
pkgver=70d63e7c9
pkgrel=2
pkgdesc="MinGW-w64 headers for Windows ARM64 with sequentially consistent interlocked exchange"
arch=('any')
url="https://www.mingw-w64.org/"
license=('custom')
provides=("${MINGW_PACKAGE_PREFIX}-headers")
options=('!strip' '!debug' 'staticlibs')

package() {
    bsdtar -xf "${srcdir}/provider.tar.zst" -C "${pkgdir}"
    local license_dir="${pkgdir}/mingwarm64/share/licenses/${pkgname}"
    install -d "${license_dir}"
    install -m644 \
        "${srcdir}/COPYING" \
        "${srcdir}/DISCLAIMER" \
        "${srcdir}/COPYING.MinGW-w64.txt" \
        "${srcdir}/COPYING.MinGW-w64-runtime.txt" \
        "${license_dir}/"
}
'@
$pkgbuildPath = Join-Path $recipeRoot 'PKGBUILD'
[System.IO.File]::WriteAllText(
    $pkgbuildPath,
    ($pkgbuild -replace "`r`n", "`n"),
    [System.Text.UTF8Encoding]::new($false))

& $Bash (ConvertTo-MsysPath $prepareMakepkg) `
    (ConvertTo-MsysPath $makepkgLibrary) `
    (ConvertTo-MsysPath $privateMakepkgLibrary)
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$sourceDateEpoch = (& git -C $SourceRoot show -s --format=%ct $sourceCommit).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceDateEpoch -notmatch '^\d+$') {
    throw "Invalid source commit timestamp: $sourceDateEpoch"
}

$previousSourceDateEpoch = $env:SOURCE_DATE_EPOCH
$env:SOURCE_DATE_EPOCH = $sourceDateEpoch
try {
    & $Bash (ConvertTo-MsysPath $repackage) `
        (ConvertTo-MsysPath $privateMakepkgLibrary) `
        (ConvertTo-MsysPath $NativeFind) `
        (ConvertTo-MsysPath $recipeRoot) `
        (ConvertTo-MsysPath $packageDestination) `
        (ConvertTo-MsysPath $TargetBin) `
        (ConvertTo-MsysPath $HostUsrBin) `
        'mingwarm64'
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    $env:SOURCE_DATE_EPOCH = $previousSourceDateEpoch
}

$packages = @(Get-ChildItem $packageDestination -Filter "$packageName-*.pkg.tar.zst" -File)
if ($packages.Count -ne 1) {
    throw "Expected one package, found $($packages.Count)."
}
$package = $packages[0]
if ($package.Name -ne "$packageName-$packageVersion-any.pkg.tar.zst") {
    throw "Unexpected package name: $($package.Name)"
}

$extractCommand = @'
set -euo pipefail
archive=$(cygpath -u "$1")
destination=$(cygpath -u "$2")
bsdtar -xf "$archive" -C "$destination"
'@
$rawPackage = Join-Path $controlsRoot "raw-makepkg-$($package.Name)"
Move-Item $package.FullName $rawPackage
& $Bash -c $extractCommand -- $rawPackage $normalizationRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$buildinfoPath = Join-Path $normalizationRoot '.BUILDINFO'
$buildinfo = Get-Content $buildinfoPath -Raw
$buildinfo = [regex]::Replace(
    $buildinfo,
    '(?m)^builddir = .*$',
    'builddir = /build/mingw-w64-aarch64-headers-git')
$buildinfo = [regex]::Replace(
    $buildinfo,
    '(?m)^startdir = .*$',
    'startdir = /build/mingw-w64-aarch64-headers-git')
[System.IO.File]::WriteAllText(
    $buildinfoPath,
    ($buildinfo -replace "`r`n", "`n"),
    [System.Text.UTF8Encoding]::new($false))

$buildinfoFile = Get-Item $buildinfoPath
$buildinfoSha = (Get-FileHash $buildinfoPath -Algorithm SHA256).Hash.ToLowerInvariant()
$mtreePath = Join-Path $normalizationRoot '.MTREE'
$mtreeText = Read-GzipText $mtreePath
$normalizedBuildinfoEntry = "./.BUILDINFO time=$sourceDateEpoch.0 size=$($buildinfoFile.Length) sha256digest=$buildinfoSha"
$mtreeText = [regex]::Replace(
    $mtreeText,
    '(?m)^\./\.BUILDINFO .*$',
    $normalizedBuildinfoEntry)
Write-GzipText $mtreePath ($mtreeText -replace "`r`n", "`n")

$sourceDate = [System.DateTimeOffset]::FromUnixTimeSeconds([long]$sourceDateEpoch).UtcDateTime
Get-ChildItem $normalizationRoot -Recurse -Force | ForEach-Object {
    $_.LastWriteTimeUtc = $sourceDate
}
(Get-Item $normalizationRoot).LastWriteTimeUtc = $sourceDate

$normalizeCommand = @'
set -euo pipefail
root=$(cygpath -u "$1")
output=$(cygpath -u "$2")
epoch=$3
tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
    --format=posix --pax-option=delete=atime,delete=ctime \
    -I "zstd -19 -T0" -cf "$output" \
    -C "$root" .BUILDINFO .MTREE .PKGINFO mingwarm64
'@
& $Bash -c $normalizeCommand -- $normalizationRoot $package.FullName $sourceDateEpoch
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$package = Get-Item $package.FullName

& $Bash -c $extractCommand -- $package.FullName $readbackRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$expectedFiles = @(Get-ChildItem (Join-Path $packageDirectory 'mingwarm64') `
    -Recurse -File | Sort-Object FullName)
$actualFiles = @(Get-ChildItem (Join-Path $readbackRoot 'mingwarm64') -Recurse -File |
    Sort-Object FullName)
if ($expectedFiles.Count -ne $actualFiles.Count) {
    throw "Readback file-count mismatch: expected $($expectedFiles.Count), actual $($actualFiles.Count)"
}

$manifest = foreach ($file in $expectedFiles) {
    $relativePath = $file.FullName.Substring($packageDirectory.Length + 1).Replace('\', '/')
    $readbackPath = Join-Path $readbackRoot $relativePath
    if (-not (Test-Path $readbackPath -PathType Leaf)) {
        throw "Missing readback path: $relativePath"
    }
    $expectedSha = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualSha = (Get-FileHash $readbackPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) {
        throw "Readback hash mismatch: $relativePath"
    }
    [ordered]@{
        path = $relativePath
        bytes = $file.Length
        sha256 = $expectedSha
    }
}
$manifestPath = Join-Path $controlsRoot 'payload-manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content $manifestPath -Encoding utf8NoBOM

$pkginfoPath = Join-Path $readbackRoot '.PKGINFO'
$pkginfo = Get-Content $pkginfoPath -Raw
foreach ($line in @(
        "pkgname = $packageName",
        "pkgver = $packageVersion",
        'license = custom',
        'provides = mingw-w64-aarch64-headers')) {
    if ($pkginfo -notmatch [regex]::Escape($line)) {
        throw "Missing package metadata: $line"
    }
}

$readbackIncludeRoot = Join-Path $readbackRoot 'mingwarm64\aarch64-w64-mingw32\include'
& $codegenTest -Compiler $compiler -IncludeRoot $readbackIncludeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'readback-codegen')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $runtimeTest -Compiler $compiler -IncludeRoot $readbackIncludeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'readback-runtime')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$pacmanRoot = Join-Path $controlsRoot 'pacman-root'
$pacmanDatabase = Join-Path $pacmanRoot 'var\lib\pacman'
New-Item -ItemType Directory -Path $pacmanDatabase | Out-Null
$pacmanConfig = Join-Path $controlsRoot 'pacman.conf'
$pacmanConfigText = @'
[options]
Architecture = auto
SigLevel = Never
LocalFileSigLevel = Never
'@
[System.IO.File]::WriteAllText(
    $pacmanConfig,
    ($pacmanConfigText -replace "`r`n", "`n"),
    [System.Text.UTF8Encoding]::new($false))
$pacmanCommand = @'
set -euo pipefail
host_usr_bin=$(cygpath -u "$1")
config=$(cygpath -u "$2")
root=$(cygpath -u "$3")
database=$(cygpath -u "$4")
package=$(cygpath -u "$5")
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -U --noconfirm "$package"
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -Q mingw-w64-aarch64-headers-git
'@
& $Bash -c $pacmanCommand -- $HostUsrBin $pacmanConfig $pacmanRoot `
    $pacmanDatabase $package.FullName
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$installedPayloadRoot = Join-Path $pacmanRoot 'mingwarm64'
$installedFiles = @(Get-ChildItem $installedPayloadRoot -Recurse -File | Sort-Object FullName)
if ($installedFiles.Count -ne $expectedFiles.Count) {
    throw "Pacman file-count mismatch: expected $($expectedFiles.Count), installed $($installedFiles.Count)"
}
foreach ($file in $expectedFiles) {
    $relativePath = $file.FullName.Substring($packageDirectory.Length + 1)
    $installedPath = Join-Path $pacmanRoot $relativePath
    $expectedSha = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $installedSha = (Get-FileHash $installedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($installedSha -ne $expectedSha) {
        throw "Pacman payload hash mismatch: $relativePath"
    }
}

$licenseManifest = foreach ($entry in $licenseInputs.GetEnumerator()) {
    [ordered]@{
        source_path = $entry.Key.Replace('\', '/')
        sha256 = $entry.Value
        package_path = "mingwarm64/share/licenses/$packageName/$([System.IO.Path]::GetFileName($entry.Key))"
    }
}
$handoff = [ordered]@{
    schema = 'mingw-w64-arm64-interlocked-header-package-v1'
    package = [ordered]@{
        name = $packageName
        version = $packageVersion
        path = $package.FullName
        sha256 = (Get-FileHash $package.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $package.Length
        raw_makepkg_sha256 = (Get-FileHash $rawPackage -Algorithm SHA256).Hash.ToLowerInvariant()
        canonical_build_path = '/build/mingw-w64-aarch64-headers-git'
        metadata_normalized = $true
    }
    provider = [ordered]@{
        archive = (Resolve-Path $ProviderArchive).Path
        archive_sha256 = $actualArchiveSha
        source_commit = $actualCommit
        patched_header_sha256 = $actualHeaderSha
    }
    payload = [ordered]@{
        files = $expectedFiles.Count
        bytes = ($expectedFiles | Measure-Object Length -Sum).Sum
        manifest = $manifestPath
        manifest_sha256 = (Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        readback_identical = $true
        package_readback_codegen = 'passed'
        package_readback_runtime = 'passed'
        pacman_transaction = 'passed'
        pacman_installed_identical = $true
    }
    licenses = $licenseManifest
    recipe = [ordered]@{
        pkgbuild_sha256 = (Get-FileHash $pkgbuildPath -Algorithm SHA256).Hash.ToLowerInvariant()
        packaging_script_sha256 = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        makepkg_library_patch_sha256 = (Get-FileHash (Join-Path $scriptDirectory 'makepkg-6.1-gnu-find-metadata.patch') -Algorithm SHA256).Hash.ToLowerInvariant()
        source_date_epoch = [long]$sourceDateEpoch
    }
    scope = 'Distributable MinGW-w64 Windows ARM64 C headers and winpthreads compatibility headers only; no GCC, CRT library, C++ header, OpenSSL, or full toolchain rebuild claim.'
}
$handoffPath = Join-Path $OutputRoot 'handoff.json'
$handoff | ConvertTo-Json -Depth 6 | Set-Content $handoffPath -Encoding utf8NoBOM

[ordered]@{
    handoff = $handoffPath
    handoff_sha256 = (Get-FileHash $handoffPath -Algorithm SHA256).Hash.ToLowerInvariant()
    package = $package.FullName
    package_sha256 = $handoff.package.sha256
    payload_manifest_sha256 = $handoff.payload.manifest_sha256
} | ConvertTo-Json
