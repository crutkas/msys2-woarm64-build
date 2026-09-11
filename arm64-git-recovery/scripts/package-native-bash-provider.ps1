[CmdletBinding()]
param(
    [string]$ProducerHandoff = 'C:\ag-bash-e138-01\bash-provider-handoff-02\handoff.json',
    [string]$Stage = 'C:\ag-bash-e138-01\bash-full-immutable-18\stage',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\bash-qualified-d70-v1',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$CompressionPolicyHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json',
    [string]$CompressionPolicyRoot = '',
    [string]$Strings = 'C:\agtc-libs-01\sdk\bin\aarch64-pc-cygwin-strings.exe',
    [string]$ReadbackSdk = 'C:\ag-bash-e138-01\bash-sdk-relocatable-02\stage'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedHandoffHash = 'f1aaeac6acb81efe8163cad3ea08a8f6432f7a77a9b1e2d0dae48b10efd8d58f'
$expectedInventoryHash = '570915d5b63441d70ad6fc65acd186cace5c19b8ad428a07ed650968916c92f1'
$expectedTargetedHash = '0835ca6e0568da28c80c8cf1e95c581bcce27a58c99d0905bd8c5d0eda955e42'
$expectedFullSuiteHash = '53c3267c22d75aa228b71b4b499960340f88af198af9ee0811a87365e636c268'
$expectedGettextResultHash = '7b50e53e8f389201c22d36420f381e0e82fc99ad1923eb78e274ca97b44fb32e'
$expectedBashHash = '39ef42f62906be249b650dd9e0760109161c40c5b4e047093ef7e16b138c5d6a'
$expectedRecipeHash = 'b2aeaff6799073b992b716efd1da2753198ca099dee9de05315ceca431f7ad50'
$expectedRuntimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'

if (-not $CompressionPolicyRoot) {
    $CompressionPolicyRoot = Join-Path (
        Split-Path -Parent $PSScriptRoot
    ) 'native-packaging\compression-policy'
}

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

function Assert-Reference {
    param([Parameter(Mandatory)][object]$Reference)

    Assert-FileHash -Path ([string]$Reference.path) -Expected ([string]$Reference.sha256)
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

function Assert-GzipPayloadHash {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required compressed file is missing: $Path"
    }
    $stream = [IO.File]::OpenRead($Path)
    try {
        $gzip = [IO.Compression.GZipStream]::new(
            $stream,
            [IO.Compression.CompressionMode]::Decompress
        )
        try {
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $actual = [Convert]::ToHexString(
                    $hash.ComputeHash($gzip)
                ).ToLowerInvariant()
            }
            finally {
                $hash.Dispose()
            }
        }
        finally {
            $gzip.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
    if ($actual -ne $Expected) {
        throw "Decompressed hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

function Get-PackagedPath {
    param([Parameter(Mandatory)][string]$Path)

    if (($Path.StartsWith('usr/share/info/') -or
         $Path.StartsWith('usr/share/man/')) -and
        -not $Path.EndsWith('.gz')) {
        return "$Path.gz"
    }
    return $Path
}

Assert-FileHash -Path $ProducerHandoff -Expected $expectedHandoffHash
Assert-FileHash -Path $CompressionPolicyHandoff -Expected (
    '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
)
$compressionPolicyFiles = [ordered]@{
    'makepkg-compression-policy.sh' = 'a2e161767e4d9dea88768eac448170ec53981acb05efe06ad7064e2ddafc62d1'
    'makepkg-compression.sh' = '41bc1d98d912ddbca60f1a6369be0ee9f97959787dcf499eaee814a5f01406d6'
    'with-makepkg-compression.sh' = 'b3324cc71bb44ad74ed00064e420db90158fb9aa2da022667a7fe6eaa3e8571c'
}
foreach ($entry in $compressionPolicyFiles.GetEnumerator()) {
    Assert-FileHash -Path (Join-Path $CompressionPolicyRoot $entry.Key) -Expected $entry.Value
}

$handoff = Get-Content -Raw -LiteralPath $ProducerHandoff | ConvertFrom-Json
if ($handoff.schema -ne 1 -or
    $handoff.status -ne 'qualified-relocatable-native-arm64-bash-provider-input' -or
    $handoff.admission_request -notmatch 'Package this wholly new stage' -or
    $handoff.supersedes.provider_rejection_sha256 -ne
        '11bf138053d4fc0aca50c4de72332d987fe9cb683b9a9fb6e03aae9861e25dd0') {
    throw 'Bash producer handoff identity is invalid'
}
$inventoryPath = Join-Path $handoff.build.root 'stage.inventory.json'
$targetedPath = Join-Path $handoff.targeted.root 'qualification.json'
$fullSuitePath = Join-Path $handoff.full_suite.root 'qualification.json'
$gettextResultPath = Join-Path $handoff.gettext_runtime.root 'result.json'
Assert-FileHash -Path $inventoryPath -Expected $expectedInventoryHash
Assert-FileHash -Path $targetedPath -Expected $expectedTargetedHash
Assert-FileHash -Path $fullSuitePath -Expected $expectedFullSuiteHash
Assert-FileHash -Path $gettextResultPath -Expected $expectedGettextResultHash

$inventory = Get-Content -Raw -LiteralPath $inventoryPath | ConvertFrom-Json
$targeted = Get-Content -Raw -LiteralPath $targetedPath | ConvertFrom-Json
$fullSuite = Get-Content -Raw -LiteralPath $fullSuitePath | ConvertFrom-Json
$gettextResult = Get-Content -Raw -LiteralPath $gettextResultPath | ConvertFrom-Json
$inventoryEntries = @(
    $inventory.files.PSObject.Properties | Sort-Object Name | ForEach-Object {
        $machineProperty = $_.Value.PSObject.Properties['machine']
        [ordered]@{
            path = $_.Name
            sha256 = $_.Value.sha256
            size = $_.Value.size
            machine = if ($null -ne $machineProperty) {
                $machineProperty.Value
            }
            else {
                $null
            }
        }
    }
)
if ($inventory.status -ne 'sealed-relocatable-native-arm64-bash-stage' -or
    $handoff.build.root -ne (Split-Path -Parent $Stage) -or
    $handoff.build.file_count -ne 283 -or
    $handoff.build.arm64_pe_count -ne 42 -or
    $handoff.payload.bash.sha256 -ne $expectedBashHash -or
    $handoff.payload.sh.sha256 -ne $expectedBashHash -or
    $handoff.payload.fltexpr.sha256 -ne
        '9493348dc9527579985934cecb6b9c835043b78fe4c38a39ceca1508a21b8979' -or
    $handoff.relocation.canonical -ne '/usr/share/locale' -or
    $handoff.relocation.host_bootstrap_prefix_absent -ne $true -or
    $handoff.relocation.sdk_private_prefix_absent -ne $true -or
    $targeted.status -ne 'qualified' -or
    $targeted.case_count -ne 3 -or
    $targeted.observer.parent_raw_exit -ne 0 -or
    $targeted.observer.created -ne $targeted.observer.observed -or
    $targeted.observer.unresolved -ne 0 -or
    $fullSuite.status -ne 'qualified' -or
    $fullSuite.case_count -ne 86 -or
    $fullSuite.observer.parent_raw_exit -ne 0 -or
    $fullSuite.observer.created -ne $fullSuite.observer.observed -or
    $fullSuite.observer.unresolved -ne 0 -or
    $gettextResult.status -ne 'qualified-relocatable-gettext-runtime' -or
    $gettextResult.intl_dll_sha256 -ne
        '44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c' -or
    $inventory.file_count -ne 283 -or
    $inventoryEntries.Count -ne 283) {
    throw 'Bash build, qualification, or stage inventory is invalid'
}
Assert-FileHash -Path $inventory.recipe.path -Expected $inventory.recipe.sha256
Assert-FileHash -Path 'C:\ag-bash-e138-01\sources\bash\PKGBUILD' -Expected $expectedRecipeHash
Assert-FileHash -Path (Join-Path $Stage 'usr\bin\bash.exe') -Expected $expectedBashHash
Assert-FileHash -Path (Join-Path $Stage 'usr\bin\sh.exe') -Expected $expectedBashHash

foreach ($entry in $inventoryEntries) {
    $path = Join-Path $Stage ([string]$entry.path -replace '/', '\')
    Assert-FileHash -Path $path -Expected ([string]$entry.sha256)
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Versioned output directory already exists: $OutputDirectory"
}
$runtimePayload = Join-Path $OutputDirectory 'payload\bash'
$develPayload = Join-Path $OutputDirectory 'payload\bash-devel'
$packageRoot = Join-Path $OutputDirectory 'package'
$packageOutput = Join-Path $packageRoot 'packages'
$makepkgBuild = Join-Path $packageRoot 'makepkg-build'
$readbackRoot = Join-Path $OutputDirectory 'readback'
$dependencyRoot = Join-Path $OutputDirectory 'readback-runtime'
$dependencyBin = Join-Path $dependencyRoot 'usr\bin'
New-Item -ItemType Directory -Path $runtimePayload, $develPayload, $packageRoot,
    $packageOutput, $makepkgBuild, $readbackRoot, $dependencyBin | Out-Null

$runtimeEntries = @()
$develEntries = @()
foreach ($entry in $inventoryEntries) {
    $isDevel = (
        $entry.path.StartsWith('usr/include/bash/') -or
        $entry.path -eq 'usr/lib/libbash.dll.a'
    )
    $destinationRoot = if ($isDevel) { $develPayload } else { $runtimePayload }
    $destination = Join-Path $destinationRoot ([string]$entry.path -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) |
        Out-Null
    Copy-Item -LiteralPath (
        Join-Path $Stage ([string]$entry.path -replace '/', '\')
    ) -Destination $destination
    if ($isDevel) {
        $develEntries += $entry
    }
    else {
        $runtimeEntries += $entry
    }
}
if ($runtimeEntries.Count -ne 170 -or $develEntries.Count -ne 113) {
    throw "Unexpected Bash package split: runtime=$($runtimeEntries.Count), devel=$($develEntries.Count)"
}

$makefilePath = Join-Path $runtimePayload 'usr\lib\bash\Makefile.inc'
Assert-FileHash -Path $makefilePath -Expected (
    '9c328267b219dcf0b51bf82b5e931fe559f1074370197cc8fe7d68879bf0ff14'
)
$makefile = Get-Content -Raw -LiteralPath $makefilePath
$makefileReplacements = [ordered]@{
    'BUILD_DIR = /c/ag-bash-e138-01/bash-full-immutable-18/source' = 'BUILD_DIR = /usr/src/bash'
    'CPPFLAGS = -DWORDEXP_OPTION -DLIBINTL_STATIC -DLIBICONV_STATIC -DNCURSES_STATIC -IC:/ag-bash-e138-01/bash-sdk-relocatable-02/stage/usr/include -IC:/ag-bash-e138-01/bash-sdk-relocatable-02/stage/usr/include/ncursesw -I/c/ag-bash-e138-01/bash-sdk-relocatable-02/stage/usr/include' = 'CPPFLAGS = -DWORDEXP_OPTION -DLIBINTL_STATIC -DLIBICONV_STATIC -DNCURSES_STATIC -I/usr/include -I/usr/include/ncursesw'
    'SHOBJ_LDFLAGS = -shared -Wl,--enable-auto-import -Wl,--enable-auto-image-base -Wl,--export-all -Wl,--out-implib,$@.a -Wl,--no-insert-timestamp -LC:/ag-bash-e138-01/bash-sdk-relocatable-02/stage/usr/lib -static' = 'SHOBJ_LDFLAGS = -shared -Wl,--enable-auto-import -Wl,--enable-auto-image-base -Wl,--export-all -Wl,--out-implib,$@.a -Wl,--no-insert-timestamp -L/usr/lib -static'
    'SHOBJ_LIBS = /c/ag-bash-e138-01/bash-full-immutable-18/source/libbash.dll.a -lintl -liconv' = 'SHOBJ_LIBS = /usr/lib/libbash.dll.a -lintl -liconv'
}
foreach ($replacement in $makefileReplacements.GetEnumerator()) {
    if (-not $makefile.Contains($replacement.Key)) {
        throw "Bash Makefile relocation source text is missing: $($replacement.Key)"
    }
    $makefile = $makefile.Replace($replacement.Key, $replacement.Value)
}
[IO.File]::WriteAllText($makefilePath, $makefile, [Text.UTF8Encoding]::new($false))
$relocatedMakefileHash = Get-Hash $makefilePath

$msysRuntimePayload = Convert-ToMsysPath -Path $runtimePayload
$msysDevelPayload = Convert-ToMsysPath -Path $develPayload
$pkgbuild = @"
pkgbase=bash
pkgname=('bash' 'bash-devel')
pkgver=5.3.015
pkgrel=2
pkgdesc='The GNU Bourne Again shell'
arch=('aarch64')
url='https://www.gnu.org/software/bash/bash.html'
license=('spdx:GPL-3.0-or-later')
options=('!strip' '!debug' 'staticlibs')
source=()

package_bash() {
  depends=('libiconv' 'libintl')
  provides=('sh')
  cp -a '$msysRuntimePayload/.' "`${pkgdir}/"
}

package_bash-devel() {
  pkgdesc='Bash headers and libraries'
  groups=('development')
  depends=('bash=5.3.015-2')
  cp -a '$msysDevelPayload/.' "`${pkgdir}/"
}
"@.Replace("`r`n", "`n")
Set-Content -LiteralPath (Join-Path $packageRoot 'PKGBUILD') -Value $pkgbuild -Encoding utf8NoBOM

$msysPackageRoot = Convert-ToMsysPath -Path $packageRoot
$msysPackageOutput = Convert-ToMsysPath -Path $packageOutput
$msysMakepkgBuild = Convert-ToMsysPath -Path $makepkgBuild
$msysMakepkgConfig = Convert-ToMsysPath -Path $MakepkgConfig
$msysCompressionWrapper = Convert-ToMsysPath -Path (
    Join-Path $CompressionPolicyRoot 'with-makepkg-compression.sh'
)
$oldPath = $env:PATH
try {
    $env:PATH = Split-Path -Parent $Bash
    $command = @"
export PKGDEST='$msysPackageOutput'
export BUILDDIR='$msysMakepkgBuild'
export WOARM64_JOBS=1
cd '$msysPackageRoot'
/usr/bin/bash '$msysCompressionWrapper' /usr/bin/makepkg --config '$msysMakepkgConfig' --force --cleanbuild --noconfirm
"@
    & $Bash --noprofile --norc -c ($command.Replace("`r`n", "`n")) | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "makepkg failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PATH = $oldPath
}

$archives = @(Get-ChildItem -LiteralPath $packageOutput -File -Filter '*.pkg.tar.zst')
if ($archives.Count -ne 2) {
    throw "Expected two Bash split archives, found $($archives.Count)"
}
$archiveByName = @{}
foreach ($archive in $archives) {
    $extract = Join-Path $readbackRoot $archive.BaseName
    New-Item -ItemType Directory -Path $extract | Out-Null
    & tar -xf $archive.FullName -C $extract
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract Bash package: $($archive.FullName)"
    }
    $pkginfo = (& tar -xOf $archive.FullName '.PKGINFO') -join "`n"
    $nameLine = @($pkginfo -split "`n" | Where-Object { $_ -like 'pkgname = *' })
    if ($nameLine.Count -ne 1) {
        throw "Bash package has no unique pkgname: $($archive.FullName)"
    }
    $name = $nameLine[0].Substring('pkgname = '.Length)
    $archiveByName[$name] = [ordered]@{
        file = $archive
        root = $extract
        pkginfo = $pkginfo
    }
}
foreach ($name in 'bash', 'bash-devel') {
    if (-not $archiveByName.ContainsKey($name)) {
        throw "Missing Bash split archive: $name"
    }
}

foreach ($line in @(
    'pkgname = bash',
    'pkgver = 5.3.015-2',
    'depend = libiconv',
    'depend = libintl',
    'provides = sh'
)) {
    if ($archiveByName['bash'].pkginfo -notmatch [regex]::Escape($line)) {
        throw "Bash .PKGINFO is missing: $line"
    }
}
foreach ($line in @(
    'pkgname = bash-devel',
    'pkgver = 5.3.015-2',
    'depend = bash=5.3.015-2'
)) {
    if ($archiveByName['bash-devel'].pkginfo -notmatch [regex]::Escape($line)) {
        throw "bash-devel .PKGINFO is missing: $line"
    }
}

foreach ($entry in $runtimeEntries) {
    if ($entry.path -eq 'usr/share/info/dir') {
        continue
    }
    $packagedPath = Get-PackagedPath -Path ([string]$entry.path)
    $path = Join-Path $archiveByName['bash'].root ($packagedPath -replace '/', '\')
    if ($entry.path -eq 'usr/lib/bash/Makefile.inc') {
        Assert-FileHash -Path $path -Expected $relocatedMakefileHash
    }
    elseif ($packagedPath -ne $entry.path) {
        Assert-GzipPayloadHash -Path $path -Expected ([string]$entry.sha256)
    }
    else {
        Assert-FileHash -Path $path -Expected ([string]$entry.sha256)
    }
}
foreach ($entry in $develEntries) {
    Assert-FileHash -Path (
        Join-Path $archiveByName['bash-devel'].root ([string]$entry.path -replace '/', '\')
    ) -Expected ([string]$entry.sha256)
}

$runtimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll'
$iconvDll = Join-Path $ReadbackSdk 'usr\bin\msys-iconv-2.dll'
$intlDll = Join-Path $ReadbackSdk 'usr\bin\msys-intl-8.dll'
Assert-FileHash -Path $runtimeDll -Expected $expectedRuntimeHash
Assert-FileHash -Path $iconvDll -Expected '86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215'
Assert-FileHash -Path $intlDll -Expected '44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c'
Copy-Item -LiteralPath $runtimeDll, $iconvDll, $intlDll -Destination $dependencyBin

$bashExe = Join-Path $archiveByName['bash'].root 'usr\bin\bash.exe'
$shExe = Join-Path $archiveByName['bash'].root 'usr\bin\sh.exe'
$readbackTemp = Join-Path $dependencyRoot 'tmp'
New-Item -ItemType Directory -Path $readbackTemp | Out-Null
$oldPath = $env:PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpdir = $env:TMPDIR
try {
    $env:PATH = "$(Split-Path -Parent $bashExe);$dependencyBin;C:\Windows\System32"
    $env:TEMP = $readbackTemp
    $env:TMP = $readbackTemp
    $env:TMPDIR = $readbackTemp
    $bashOutput = @(& $bashExe --noprofile --norc -c 'printf "bash:%s:%s\n" "$BASH_VERSION" "$((6*7))"' 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($bashOutput -join "`n") -notmatch '^bash:5\.3\.15\(2\)-release:42$') {
        throw "Packaged Bash readback failed: $($bashOutput -join "`n")"
    }
    $shOutput = @(& $shExe -c 'printf "sh:%s\n" "$((7*6))"' 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($shOutput -join "`n").Trim() -ne 'sh:42') {
        throw "Packaged sh readback failed: $($shOutput -join "`n")"
    }
    $loadable = Join-Path $archiveByName['bash'].root 'usr\lib\bash\printenv.exe'
    $msysLoadable = Convert-ToCygdrivePath -Path $loadable
    $loadableOutput = @(
        & $bashExe --noprofile --norc -c (
            "enable -f '$msysLoadable' printenv && WOARM64_BASH_LOADABLE=ok printenv WOARM64_BASH_LOADABLE"
        ) 2>&1
    )
    if ($LASTEXITCODE -ne 0 -or ($loadableOutput -join "`n").Trim() -ne 'ok') {
        throw "Packaged Bash loadable readback failed: $($loadableOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpdir
}

$operationalPattern = '/msys64/usr/|/mingwarm64/bin|/mingwarm64/etc|/mingwarm64/share|/mingwarm64/lib/tcl'
$privateRuntimePaths = @()
foreach ($file in Get-ChildItem -LiteralPath $archiveByName['bash'].root -Recurse -File -Filter '*.exe') {
    $matches = @(
        & $Strings -a $file.FullName |
            Select-String -Pattern $operationalPattern |
            ForEach-Object { $_.Line } |
            Sort-Object -Unique
    )
    if ($matches.Count) {
        $privateRuntimePaths += [ordered]@{
            path = $file.FullName.Substring($archiveByName['bash'].root.Length + 1).Replace('\', '/')
            sha256 = Get-Hash $file.FullName
            matches = $matches
        }
    }
}
if ($privateRuntimePaths.Count -ne 0) {
    throw "Bash package still contains private operational paths: $($privateRuntimePaths | ConvertTo-Json -Compress)"
}
$canonicalLocaleEvidence = @()
foreach ($relativePath in 'usr/bin/bash.exe', 'usr/bin/sh.exe', 'usr/lib/bash/fltexpr.exe') {
    $path = Join-Path $archiveByName['bash'].root ($relativePath -replace '/', '\')
    $matches = @(
        & $Strings -a $path |
            Select-String -SimpleMatch '/usr/share/locale' |
            ForEach-Object { $_.Line } |
            Sort-Object -Unique
    )
    if ($matches -notcontains '/usr/share/locale') {
        throw "Canonical locale path is missing from packaged $relativePath"
    }
    $canonicalLocaleEvidence += [ordered]@{
        path = $relativePath
        sha256 = Get-Hash $path
        locale = '/usr/share/locale'
    }
}

$packages = @(
    foreach ($name in 'bash', 'bash-devel') {
        [ordered]@{
            name = $name
            path = $archiveByName[$name].file.FullName
            sha256 = Get-Hash $archiveByName[$name].file.FullName
        }
    }
)
$export = Join-Path $OutputDirectory 'export.json'
[ordered]@{
    schema = 1
    status = 'admitted-qualified-current-d70-native-bash-exported'
    provider = 'native-msys-bash'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $expectedRuntimeHash
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = $packages
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $export -Encoding utf8NoBOM

$supersession = Join-Path $OutputDirectory 'rejection-superseding-disposition.json'
[ordered]@{
    schema = 1
    status = 'frozen-bash-v5-rejection-superseded-by-relocatable-provider'
    supersedes = [ordered]@{
        producer_handoff = [ordered]@{
            path = $handoff.supersedes.producer_handoff
        }
        provider_rejection = [ordered]@{
            path = $handoff.supersedes.provider_rejection
            sha256 = $handoff.supersedes.provider_rejection_sha256
        }
    }
    provider_export = [ordered]@{
        path = $export
        sha256 = Get-Hash $export
    }
    producer_handoff = [ordered]@{
        path = $ProducerHandoff
        sha256 = Get-Hash $ProducerHandoff
    }
    packages = $packages
    exact_stage_ownership = [ordered]@{
        bash_files = $runtimeEntries.Count
        bash_packaged_files = $runtimeEntries.Count - 1
        bash_devel_files = $develEntries.Count
        total_files = $inventory.file_count
        bash_provides = @('sh')
        bash_dependencies = @('libiconv', 'libintl')
        bash_devel_dependencies = @('bash=5.3.015-2')
        normal_makepkg_exclusions = @('usr/share/info/dir')
    }
    package_time_text_relocation = [ordered]@{
        path = 'usr/lib/bash/Makefile.inc'
        source_sha256 = '9c328267b219dcf0b51bf82b5e931fe559f1074370197cc8fe7d68879bf0ff14'
        package_sha256 = $relocatedMakefileHash
        replacements = $makefileReplacements
    }
    unchanged_binaries = [ordered]@{
        bash = [ordered]@{
            path = 'usr/bin/bash.exe'
            sha256 = $expectedBashHash
        }
        sh = [ordered]@{
            path = 'usr/bin/sh.exe'
            sha256 = $expectedBashHash
        }
        loadable_count = 40
    }
    readback = [ordered]@{
        bash = $bashOutput
        sh = $shOutput
        loadable = $loadableOutput
        dependencies = @(
            [ordered]@{ name = 'msys-2.0.dll'; sha256 = Get-Hash $runtimeDll },
            [ordered]@{ name = 'msys-iconv-2.dll'; sha256 = Get-Hash $iconvDll },
            [ordered]@{ name = 'msys-intl-8.dll'; sha256 = Get-Hash $intlDll }
        )
        dependency_bytes_admitted_as_packages = $false
    }
    canonical_locale_evidence = $canonicalLocaleEvidence
    blocking_operational_paths = @()
    controls = [ordered]@{
        source_rebuilt_by_intake = $false
        producer_stage_modified = $false
        executable_bytes_modified = $false
        loadable_bytes_modified = $false
        frozen_v5_bytes_reused = $false
        frozen_v5_rejection_modified = $false
        release_eligible = $true
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $supersession -Encoding utf8NoBOM

$handoffPath = Join-Path $OutputDirectory 'handoff.json'
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-bash-packaged-and-read-back'
    provider_export = [ordered]@{
        path = $export
        sha256 = Get-Hash $export
    }
    rejection_supersession = [ordered]@{
        path = $supersession
        sha256 = Get-Hash $supersession
    }
    packages = $packages
    release_eligible = $true
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath @(
    $packages.path
    $export
    $supersession
    $handoffPath
) | Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
