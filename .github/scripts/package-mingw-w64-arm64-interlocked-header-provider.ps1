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
    [string]$BaselineIncludeRoot,

    [Parameter(Mandatory = $true)]
    [string]$OwnershipRoot,

    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'

$sourceCommit = '70d63e7c9a477b8b275a9782b289fbf1614b6e9e'
$providerArchiveSha = 'dd606c0d006e064adc84cf6b1baee3bf6074eb77e8f190663780e3839c0aee32'
$patchedHeaderSha = '8e0d3b2f2f94969faf166d8d9a0d4eb5e358a32be6bd7e99fc76e552ebfc909a'
$patchedFastfailSourceSha = '73f341f1783674ce3cd7c58a4e4aa545ece9f8e16e81474b0b0ac4f3fbd3f633'
$installedFastfailHeaderSha = 'dc7a4b6814d2529862e4e254935adddf1c6ffddb0cd5069d8146513c5f81efb9'
$expectedHeaderCount = 1685
$expectedHeaderPathSetSha = 'c780e3df61a8154bf783634b355d9906658ad46536d5da0bb28cc3b857742681'
$expectedBaselineHeaderCount = 2528
$expectedBaselineHeaderPathSetSha = 'a441d95442647b3e5e11976509d32cea46a625c07bdc986e75ba689945da4321'
$expectedBaselineOnlyCount = 843
$expectedBaselineOnlyPathSetSha = '8bf8d4141d58ed4cfd9f08f61eceb750d25195b15f15d04ae288a80435ccf080'
$packageName = 'mingw-w64-aarch64-headers-git'
$packageVersion = '70d63e7c9-3'
$monolithicGccPackage = 'mingw-w64-aarch64-gcc'
$licenseInputs = @(
    [ordered]@{
        source_path = 'COPYING'
        package_name = 'COPYING'
        sha256 = '99a69660981156c21336fdb5661f89341b013c94e4bf9e1c7467b4745718397f'
    },
    [ordered]@{
        source_path = 'DISCLAIMER'
        package_name = 'DISCLAIMER'
        sha256 = '039ed6b4f31bb7fb97e733170b58cc435335352e4745734fcfd113877fdaf340'
    },
    [ordered]@{
        source_path = 'COPYING.MinGW-w64\COPYING.MinGW-w64.txt'
        package_name = 'COPYING.MinGW-w64.txt'
        sha256 = 'f38e6194bd3bfa1b654f118e5acefe0aead437bbe669eee43957ccc65a7127f1'
    },
    [ordered]@{
        source_path = 'COPYING.MinGW-w64-runtime\COPYING.MinGW-w64-runtime.txt'
        package_name = 'COPYING.MinGW-w64-runtime.txt'
        sha256 = 'e9b2dc02451ea29092a1f25fa0f3c07207ed421f1807dffb0c4e6dce69dee7bd'
    },
    [ordered]@{
        source_path = 'mingw-w64-libraries\winpthreads\COPYING'
        package_name = 'COPYING.winpthreads'
        sha256 = '63263614cdd29f2f93cba85e992f041b31f9fc7b4033692f31269489a8a1b177'
    }
)

$scriptDirectory = Split-Path -Parent $PSCommandPath
$prepareMakepkg = Join-Path $scriptDirectory 'prepare-native-makepkg-library.sh'
$repackage = Join-Path $scriptDirectory 'repackage-native-mingw-with-d70-find.sh'
$codegenTest = Join-Path $scriptDirectory 'test-mingw-w64-arm64-interlocked-exchange-ordering.ps1'
$runtimeTest = Join-Path $scriptDirectory 'test-mingw-w64-arm64-interlocked-exchange-runtime.ps1'
$c89Test = Join-Path $scriptDirectory 'test-mingw-w64-arm64-fastfail-c89.ps1'
$makepkgLibrary = Join-Path (Split-Path -Parent $HostUsrBin) 'share\makepkg'
$compiler = Join-Path $TargetBin 'aarch64-w64-mingw32-gcc.exe'

function Get-PeMachine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $reader = [System.IO.BinaryReader]::new($stream)
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Not a PE image: $Path"
        }
        return $reader.ReadUInt16()
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
        else {
            $stream.Dispose()
        }
    }
}

function Write-PathSet {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Paths,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $sortedPaths = @($Paths | Sort-Object)
    $text = ($sortedPaths -join "`n") + "`n"
    [System.IO.File]::WriteAllText(
        $OutputPath,
        $text,
        [System.Text.UTF8Encoding]::new($false))
    return $sortedPaths
}

function Write-RelativePathSet {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo[]]$Files,

        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $paths = @($Files | ForEach-Object {
            $_.FullName.Substring($Root.Length + 1).Replace('\', '/')
        })
    return @(Write-PathSet -Paths $paths -OutputPath $OutputPath)
}

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
    $changedPaths.Count -ne 2 -or
    $changedPaths[0] -ne 'mingw-w64-headers/crt/_mingw.h.in' -or
    $changedPaths[1] -ne 'mingw-w64-headers/include/psdk_inc/intrin-impl.h') {
    throw "Unexpected MinGW-w64 source delta: $($changedPaths -join ', ')"
}

$sourceHeader = Join-Path $SourceRoot 'mingw-w64-headers\include\psdk_inc\intrin-impl.h'
$actualHeaderSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHeaderSha -ne $patchedHeaderSha) {
    throw "Unexpected patched header identity: $actualHeaderSha"
}
$fastfailSourceHeader = Join-Path $SourceRoot 'mingw-w64-headers\crt\_mingw.h.in'
$actualFastfailSourceSha = (Get-FileHash $fastfailSourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualFastfailSourceSha -ne $patchedFastfailSourceSha) {
    throw "Unexpected patched fastfail source identity: $actualFastfailSourceSha"
}

foreach ($entry in $licenseInputs) {
    $path = Join-Path $SourceRoot $entry.source_path
    $actual = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.sha256) {
        throw "Unexpected license identity for $($entry.source_path): $actual"
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
foreach ($entry in $licenseInputs) {
    Copy-Item (Join-Path $SourceRoot $entry.source_path) `
        (Join-Path $sourceDirectory $entry.package_name)
}

$pkgbuild = @'
pkgbase=mingw-w64-headers-git
pkgname="${MINGW_PACKAGE_PREFIX}-headers-git"
pkgver=70d63e7c9
pkgrel=3
pkgdesc="MinGW-w64 headers for Windows ARM64 with sequentially consistent interlocked exchange"
arch=('any')
url="https://www.mingw-w64.org/"
license=('custom')
provides=("${MINGW_PACKAGE_PREFIX}-headers")
conflicts=("${MINGW_PACKAGE_PREFIX}-gcc")
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
        "${srcdir}/COPYING.winpthreads" \
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

$expectedTopLevelMembers = @('.BUILDINFO', '.MTREE', '.PKGINFO', 'mingwarm64')
$actualTopLevelMembers = @(Get-ChildItem $normalizationRoot -Force |
    Sort-Object Name | Select-Object -ExpandProperty Name)
if ((Compare-Object ($expectedTopLevelMembers | Sort-Object) $actualTopLevelMembers).Count -ne 0) {
    throw "Unexpected raw package top-level members: $($actualTopLevelMembers -join ', ')"
}

$buildinfoPath = Join-Path $normalizationRoot '.BUILDINFO'
$buildinfo = Get-Content $buildinfoPath -Raw
$builddirMatches = [regex]::Matches($buildinfo, '(?m)^builddir = .*$')
$startdirMatches = [regex]::Matches($buildinfo, '(?m)^startdir = .*$')
if ($builddirMatches.Count -ne 1 -or $startdirMatches.Count -ne 1) {
    throw "Expected exactly one builddir and startdir entry in .BUILDINFO."
}
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
$mtreeBuildinfoMatches = [regex]::Matches($mtreeText, '(?m)^\./\.BUILDINFO .*$')
if ($mtreeBuildinfoMatches.Count -ne 1) {
    throw "Expected exactly one .BUILDINFO entry in .MTREE."
}
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

$listArchiveCommand = @'
set -euo pipefail
archive=$(cygpath -u "$1")
bsdtar -tf "$archive"
'@
$archiveMembers = @(& $Bash -c $listArchiveCommand -- $package.FullName)
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$archiveTopLevelMembers = @($archiveMembers | ForEach-Object {
        ($_ -replace '^\./', '').Split('/')[0]
    } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Sort-Object -Unique)
if ((Compare-Object ($expectedTopLevelMembers | Sort-Object) $archiveTopLevelMembers).Count -ne 0) {
    throw "Unexpected normalized archive top-level members: $($archiveTopLevelMembers -join ', ')"
}

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
        'provides = mingw-w64-aarch64-headers',
        'conflict = mingw-w64-aarch64-gcc')) {
    if ($pkginfo -notmatch "(?m)^$([regex]::Escape($line))`$") {
        throw "Missing package metadata: $line"
    }
}

$readbackIncludeRoot = Join-Path $readbackRoot 'mingwarm64\aarch64-w64-mingw32\include'
$readbackFastfailHeader = Join-Path $readbackIncludeRoot '_mingw.h'
$actualReadbackFastfailSha = (Get-FileHash $readbackFastfailHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualReadbackFastfailSha -ne $installedFastfailHeaderSha) {
    throw "Unexpected package-readback fastfail header identity: $actualReadbackFastfailSha"
}

$readbackIncludeFiles = @(Get-ChildItem $readbackIncludeRoot -Recurse -File | Sort-Object FullName)
$readbackHeaderPathsPath = Join-Path $controlsRoot 'readback-header-paths.txt'
$readbackHeaderPaths = @(Write-RelativePathSet -Files $readbackIncludeFiles `
    -Root $readbackIncludeRoot -OutputPath $readbackHeaderPathsPath)
$actualReadbackHeaderPathSetSha = (Get-FileHash $readbackHeaderPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($readbackHeaderPaths.Count -ne $expectedHeaderCount -or
    $actualReadbackHeaderPathSetSha -ne $expectedHeaderPathSetSha) {
    throw "Unexpected package-readback header path set: count=$($readbackHeaderPaths.Count), sha256=$actualReadbackHeaderPathSetSha"
}

$baselineIncludeFiles = @(Get-ChildItem $BaselineIncludeRoot -Recurse -File | Sort-Object FullName)
$baselineHeaderPathsPath = Join-Path $controlsRoot 'baseline-header-paths.txt'
$baselineHeaderPaths = @(Write-RelativePathSet -Files $baselineIncludeFiles `
    -Root $BaselineIncludeRoot -OutputPath $baselineHeaderPathsPath)
$actualBaselineHeaderPathSetSha = (Get-FileHash $baselineHeaderPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($baselineHeaderPaths.Count -ne $expectedBaselineHeaderCount -or
    $actualBaselineHeaderPathSetSha -ne $expectedBaselineHeaderPathSetSha) {
    throw "Unexpected deployed baseline header path set: count=$($baselineHeaderPaths.Count), sha256=$actualBaselineHeaderPathSetSha"
}

$pathDelta = @(Compare-Object $baselineHeaderPaths $readbackHeaderPaths)
$readbackOnlyPaths = @($pathDelta | Where-Object SideIndicator -eq '=>' |
    Select-Object -ExpandProperty InputObject | Sort-Object)
$baselineOnlyPaths = @($pathDelta | Where-Object SideIndicator -eq '<=' |
    Select-Object -ExpandProperty InputObject | Sort-Object)
$readbackOnlyPathsPath = Join-Path $controlsRoot 'readback-only-header-paths.txt'
$baselineOnlyPathsPath = Join-Path $controlsRoot 'baseline-only-header-paths.txt'
$null = Write-PathSet -Paths $readbackOnlyPaths -OutputPath $readbackOnlyPathsPath
$null = Write-PathSet -Paths $baselineOnlyPaths -OutputPath $baselineOnlyPathsPath
$readbackOnlyPathSetSha = (Get-FileHash $readbackOnlyPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
$baselineOnlyPathSetSha = (Get-FileHash $baselineOnlyPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($readbackOnlyPaths.Count -ne 0) {
    throw "Package contains header paths absent from the deployed toolchain: $($readbackOnlyPaths -join ', ')"
}
if ($baselineOnlyPaths.Count -ne $expectedBaselineOnlyCount -or
    $baselineOnlyPathSetSha -ne $expectedBaselineOnlyPathSetSha) {
    throw "Unexpected deployed-only header path set: count=$($baselineOnlyPaths.Count), sha256=$baselineOnlyPathSetSha"
}
$baselineOnlyCxxCount = @($baselineOnlyPaths | Where-Object { $_ -like 'c++/*' }).Count
$baselineOnlyCSourceCount = @($baselineOnlyPaths | Where-Object { $_ -like '*.c' }).Count
$baselineOnlyOtherPaths = @($baselineOnlyPaths |
    Where-Object { $_ -notlike 'c++/*' -and $_ -notlike '*.c' })
if ($baselineOnlyCxxCount -ne 831 -or
    $baselineOnlyCSourceCount -ne 12 -or
    $baselineOnlyOtherPaths.Count -ne 0) {
    throw "Unexpected deployed-only classification: cxx=$baselineOnlyCxxCount, c=$baselineOnlyCSourceCount, other=$($baselineOnlyOtherPaths.Count)"
}

$readbackDifferences = @()
foreach ($file in $readbackIncludeFiles) {
    $relativePath = $file.FullName.Substring($readbackIncludeRoot.Length + 1)
    $baselinePath = Join-Path $BaselineIncludeRoot $relativePath
    if (-not (Test-Path $baselinePath -PathType Leaf)) {
        throw "Package header is absent from baseline toolchain: $relativePath"
    }
    $readbackSha = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $baselineSha = (Get-FileHash $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($readbackSha -ne $baselineSha) {
        $readbackDifferences += $relativePath.Replace('\', '/')
    }
}
if ($readbackDifferences.Count -ne 1 -or
    $readbackDifferences[0] -ne 'psdk_inc/intrin-impl.h') {
    throw "Unexpected package-readback differences from deployed toolchain: $($readbackDifferences -join ', ')"
}

$compilerTarget = (& $compiler -dumpmachine).Trim()
if ($LASTEXITCODE -ne 0 -or $compilerTarget -ne 'aarch64-w64-mingw32') {
    throw "Unexpected package-readback compiler target: $compilerTarget"
}
$compilerMachine = Get-PeMachine $compiler
if ($compilerMachine -ne 0xaa64) {
    throw ('Package-readback compiler has unexpected PE machine 0x{0:x4}.' -f $compilerMachine)
}

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
& $c89Test -Compiler $compiler -IncludeRoot $readbackIncludeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'readback-c89')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$readbackRuntimeExecutable = Join-Path $controlsRoot 'readback-runtime\interlocked-exchange-runtime.exe'
$readbackRuntimeMachine = Get-PeMachine $readbackRuntimeExecutable
if ($readbackRuntimeMachine -ne 0xaa64) {
    throw ('Package-readback runtime has unexpected PE machine 0x{0:x4}.' -f $readbackRuntimeMachine)
}

$ownershipDatabaseRoot = Join-Path $OwnershipRoot 'var\lib\pacman\local'
$ownershipBash = Join-Path $OwnershipRoot 'usr\bin\bash.exe'
if ((Resolve-Path $Bash).Path -ne (Resolve-Path $ownershipBash).Path) {
    throw "OwnershipRoot must be the filesystem root mounted by the selected Bash."
}
$ownershipUsrBin = Join-Path $OwnershipRoot 'usr\bin'
if ((Resolve-Path $HostUsrBin).Path -ne (Resolve-Path $ownershipUsrBin).Path) {
    throw "HostUsrBin must belong to OwnershipRoot."
}
$gccPackageDirectories = @(Get-ChildItem $ownershipDatabaseRoot -Directory |
    Where-Object Name -Like "$monolithicGccPackage-*")
if ($gccPackageDirectories.Count -ne 1) {
    throw "Expected one installed $monolithicGccPackage database entry, found $($gccPackageDirectories.Count)."
}
$gccPackageDirectory = $gccPackageDirectories[0]
$gccFilesDatabase = Join-Path $gccPackageDirectory.FullName 'files'
$gccOwnedPaths = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::Ordinal)
foreach ($line in Get-Content $gccFilesDatabase) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line -eq '%FILES%' -or $line.EndsWith('/')) {
        continue
    }
    $null = $gccOwnedPaths.Add($line)
}

$overlappingFiles = @()
$nonOverlappingFiles = @()
foreach ($file in $expectedFiles) {
    $relativePath = $file.FullName.Substring($packageDirectory.Length + 1).Replace('\', '/')
    if ($gccOwnedPaths.Contains($relativePath)) {
        $overlappingFiles += $relativePath
    }
    else {
        $nonOverlappingFiles += $relativePath
    }
}
$providerHeaderCount = $readbackIncludeFiles.Count
if ($overlappingFiles.Count -ne $providerHeaderCount) {
    throw "Unexpected GCC ownership overlap: expected $providerHeaderCount, actual $($overlappingFiles.Count)."
}
$expectedNonOverlappingFiles = @($licenseInputs | ForEach-Object {
        "mingwarm64/share/licenses/$packageName/$($_.package_name)"
    } | Sort-Object)
if ((Compare-Object $expectedNonOverlappingFiles ($nonOverlappingFiles | Sort-Object)).Count -ne 0) {
    throw "Unexpected files outside the monolithic GCC ownership overlap: $($nonOverlappingFiles -join ', ')"
}

$ownershipQueryCommand = @'
set -euo pipefail
export LC_ALL=C LANG=C
host_usr_bin=$(cygpath -u "$1")
[[ $(cygpath -u "$2") == / ]]
"$host_usr_bin/pacman.exe" -Qo \
    /mingwarm64/aarch64-w64-mingw32/include/psdk_inc/intrin-impl.h
'@
$ownershipQuery = @(& $Bash -c $ownershipQueryCommand -- $HostUsrBin $OwnershipRoot)
if ($LASTEXITCODE -ne 0 -or
    ($ownershipQuery -join "`n") -notmatch [regex]::Escape("is owned by $monolithicGccPackage ")) {
    throw "Representative deployed-header ownership query failed: $($ownershipQuery -join ' ')"
}
$ownershipQueryPath = Join-Path $controlsRoot 'representative-ownership-query.txt'
$ownershipQuery | Set-Content $ownershipQueryPath -Encoding utf8NoBOM

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
export LC_ALL=C LANG=C
host_usr_bin=$(cygpath -u "$1")
config=$(cygpath -u "$2")
root=$(cygpath -u "$3")
database=$(cygpath -u "$4")
package=$(cygpath -u "$5")
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -U --noconfirm "$package"
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -Q mingw-w64-aarch64-headers-git
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -Qkk mingw-w64-aarch64-headers-git
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

$conflictRoot = Join-Path $controlsRoot 'ownership-conflict-root'
$conflictDatabase = Join-Path $conflictRoot 'var\lib\pacman'
$conflictLocalDatabase = Join-Path $conflictDatabase 'local'
New-Item -ItemType Directory -Path $conflictLocalDatabase | Out-Null
Copy-Item $gccPackageDirectory.FullName $conflictLocalDatabase -Recurse
$alpmVersion = Join-Path $ownershipDatabaseRoot 'ALPM_DB_VERSION'
if (Test-Path $alpmVersion -PathType Leaf) {
    Copy-Item $alpmVersion $conflictLocalDatabase
}
$conflictLog = Join-Path $controlsRoot 'ownership-conflict-transaction.log'
$conflictCommand = @'
set -euo pipefail
export LC_ALL=C LANG=C
host_usr_bin=$(cygpath -u "$1")
config=$(cygpath -u "$2")
root=$(cygpath -u "$3")
database=$(cygpath -u "$4")
package=$(cygpath -u "$5")
log=$(cygpath -u "$6")
set +e
printf 'n\n' | "$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -U "$package" >"$log" 2>&1
status=$?
set -e
[[ $status -ne 0 ]]
"$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -Q mingw-w64-aarch64-gcc
if "$host_usr_bin/pacman.exe" --config "$config" --root "$root" \
    --dbpath "$database" -Q mingw-w64-aarch64-headers-git >/dev/null 2>&1; then
    exit 41
fi
printf '%s\n' "$status"
'@
$conflictStatus = @(& $Bash -c $conflictCommand -- $HostUsrBin $pacmanConfig `
    $conflictRoot $conflictDatabase $package.FullName $conflictLog)
$conflictExit = $conflictStatus | Select-Object -Last 1
if ($LASTEXITCODE -ne 0 -or $conflictExit -ne '1') {
    throw "Representative ownership-conflict transaction control failed."
}
$conflictLogText = Get-Content $conflictLog -Raw
foreach ($expectedConflictLine in @(
        "$packageName-$packageVersion and $($gccPackageDirectory.Name) are in conflict. Remove $monolithicGccPackage?",
        'error: unresolvable package conflicts detected',
        'error: failed to prepare transaction (conflicting dependencies)')) {
    if ($conflictLogText -notmatch [regex]::Escape($expectedConflictLine)) {
        throw "Conflict log did not contain the expected diagnostic: $expectedConflictLine"
    }
}
foreach ($forbiddenConflictDiagnostic in @(
        'failed to initialize alpm library',
        'unable to lock database',
        'invalid or corrupted package')) {
    if ($conflictLogText -match [regex]::Escape($forbiddenConflictDiagnostic)) {
        throw "Conflict transaction failed for an unrelated reason: $forbiddenConflictDiagnostic"
    }
}

$licenseManifest = foreach ($entry in $licenseInputs) {
    [ordered]@{
        source_path = $entry.source_path.Replace('\', '/')
        sha256 = $entry.sha256
        package_path = "mingwarm64/share/licenses/$packageName/$($entry.package_name)"
    }
}
$handoff = [ordered]@{
    schema = 'mingw-w64-arm64-interlocked-header-package-v2'
    package = [ordered]@{
        name = $packageName
        version = $packageVersion
        path = $package.FullName
        sha256 = (Get-FileHash $package.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $package.Length
        raw_makepkg_sha256 = (Get-FileHash $rawPackage -Algorithm SHA256).Hash.ToLowerInvariant()
        canonical_build_path = '/build/mingw-w64-aarch64-headers-git'
        metadata_normalized = $true
        top_level_members = $expectedTopLevelMembers
        conflicts = @($monolithicGccPackage)
        transaction_scope = 'fresh-root bootstrap only; the package intentionally conflicts with the monolithic GCC package that owns the same headers'
    }
    provider = [ordered]@{
        archive = (Resolve-Path $ProviderArchive).Path
        archive_sha256 = $actualArchiveSha
        source_commit = $actualCommit
        patched_header_sha256 = $actualHeaderSha
        patched_fastfail_source_sha256 = $actualFastfailSourceSha
        installed_fastfail_header_sha256 = $actualReadbackFastfailSha
        header_count = $readbackHeaderPaths.Count
        header_paths = $readbackHeaderPathsPath
        header_paths_sha256 = $actualReadbackHeaderPathSetSha
        baseline_include_root = (Resolve-Path $BaselineIncludeRoot).Path
        baseline_header_count = $baselineHeaderPaths.Count
        baseline_header_paths = $baselineHeaderPathsPath
        baseline_header_paths_sha256 = $actualBaselineHeaderPathSetSha
        readback_only_header_count = $readbackOnlyPaths.Count
        readback_only_header_paths = $readbackOnlyPathsPath
        readback_only_header_paths_sha256 = $readbackOnlyPathSetSha
        baseline_only_header_count = $baselineOnlyPaths.Count
        baseline_only_header_paths = $baselineOnlyPathsPath
        baseline_only_header_paths_sha256 = $baselineOnlyPathSetSha
        baseline_only_classification = [ordered]@{
            cxx_headers = $baselineOnlyCxxCount
            generated_c_sources = $baselineOnlyCSourceCount
            other = $baselineOnlyOtherPaths.Count
        }
        readback_differences_from_baseline = $readbackDifferences
    }
    payload = [ordered]@{
        files = $expectedFiles.Count
        bytes = ($expectedFiles | Measure-Object Length -Sum).Sum
        manifest = $manifestPath
        manifest_sha256 = (Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        readback_identical = $true
        package_readback_codegen = 'passed'
        package_readback_runtime = 'passed'
        package_readback_c89 = 'passed'
        package_readback_runtime_pe_machine = ('0x{0:x4}' -f $readbackRuntimeMachine)
        bootstrap_pacman_transaction = 'passed'
        pacman_qkk = 'passed'
        pacman_installed_identical = $true
    }
    ownership = [ordered]@{
        root = (Resolve-Path $OwnershipRoot).Path
        installed_package_database = $gccPackageDirectory.Name
        overlap_files = $overlappingFiles.Count
        expected_overlap_files = $providerHeaderCount
        non_overlapping_files = $nonOverlappingFiles
        representative_query = $ownershipQueryPath
        representative_query_sha256 = (Get-FileHash $ownershipQueryPath -Algorithm SHA256).Hash.ToLowerInvariant()
        conflict_transaction = 'rejected without removing the installed monolithic GCC package'
        conflict_transaction_exit = [int]$conflictExit
        conflict_log = $conflictLog
        conflict_log_sha256 = (Get-FileHash $conflictLog -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    licenses = $licenseManifest
    compiler = [ordered]@{
        path = (Resolve-Path $compiler).Path
        sha256 = (Get-FileHash $compiler -Algorithm SHA256).Hash.ToLowerInvariant()
        target = $compilerTarget
        pe_machine = ('0x{0:x4}' -f $compilerMachine)
    }
    recipe = [ordered]@{
        pkgbuild_sha256 = (Get-FileHash $pkgbuildPath -Algorithm SHA256).Hash.ToLowerInvariant()
        packaging_script_sha256 = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        makepkg_library_patch_sha256 = (Get-FileHash (Join-Path $scriptDirectory 'makepkg-6.1-gnu-find-metadata.patch') -Algorithm SHA256).Hash.ToLowerInvariant()
        source_date_epoch = [long]$sourceDateEpoch
    }
    scope = 'Distributable bootstrap-only MinGW-w64 Windows ARM64 C headers and winpthreads compatibility headers. It intentionally conflicts with the monolithic GCC package that currently owns the same header paths; it is not an in-place upgrade, ownership migration, GCC/CRT library/C++ header rebuild, OpenSSL rebuild, or full toolchain claim.'
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
