#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $StagedPrefix,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $RuntimeDependencyBin,
    [Parameter(Mandatory)][string] $BuildReceipt,
    [Parameter(Mandatory)][string] $ConfigureLog,
    [Parameter(Mandatory)][string] $BuildLog,
    [Parameter(Mandatory)][string] $CheckLog,
    [Parameter(Mandatory)][string] $InstallLog
)

$ErrorActionPreference = 'Stop'
$stage = Get-Item -LiteralPath $StagedPrefix
if ($stage.Name -cne 'mingwarm64' -or -not (Test-Path "$($stage.FullName)\bin\gettext.exe")) {
    throw 'StagedPrefix must be a complete canonical mingwarm64 gettext installation.'
}
foreach ($log in $ConfigureLog, $BuildLog, $CheckLog, $InstallLog) {
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
        throw "Required gettext evidence is missing: $log"
    }
}
$dependencyBin = Get-Item -LiteralPath $RuntimeDependencyBin
$buildReceiptFile = Get-Item -LiteralPath $BuildReceipt
$pinnedOwnershipRecipe = Get-Item -LiteralPath (
    'C:\ap09-ca5f\curl-packages-v2\source\' +
    'MINGW-packages-d65b87de173ac2209a63cef8c4528669b5571fd3\mingw-w64-gettext\PKGBUILD'
)
if ((Get-FileHash $pinnedOwnershipRecipe.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne
    '2753811ebaef825701261cead50289472134122fd2b0fb87dc3599cf2a53c37a') {
    throw 'Pinned Git-for-Windows gettext ownership recipe hash changed.'
}
$integrationRoot = $dependencyBin.Parent.Parent
$objdump = "$($dependencyBin.FullName)\objdump.exe"
$pacman = "$($integrationRoot.FullName)\usr\bin\pacman.exe"
$pacmanConfig = "$($integrationRoot.FullName)\etc\pacman.conf"
foreach ($required in "$($dependencyBin.FullName)\libiconv-2.dll", $objdump, $pacman, $pacmanConfig) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "RuntimeDependencyBin is missing a qualification prerequisite: $required"
    }
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw 'Gettext package preparation output must be new.'
}

$savedPath = $env:PATH
$env:PATH = "$($stage.FullName)\bin;$($dependencyBin.FullName);$savedPath"
try {
    $version = & "$($stage.FullName)\bin\gettext.exe" --version
} finally {
    $env:PATH = $savedPath
}
if ($LASTEXITCODE -ne 0 -or $version[0] -cne 'gettext.exe (GNU gettext-runtime) 1.0') {
    throw 'Staged gettext runtime does not report the retained source version 1.0.'
}

function Get-PeImports([string] $Path) {
    $output = @(& $objdump -p $Path 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect staged PE imports: $Path" }
    @(
        $output |
            ForEach-Object {
                if ($_ -match '^\s*DLL Name:\s*(\S+)\s*$') { $Matches[1] }
            } |
            Where-Object { $_ } |
            Sort-Object -Unique
    )
}

$stageBinNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
Get-ChildItem "$($stage.FullName)\bin" -File | ForEach-Object {
    [void]$stageBinNames.Add($_.Name)
}
$systemDllNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
Get-ChildItem "$env:SystemRoot\System32" -Filter '*.dll' -File | ForEach-Object {
    [void]$systemDllNames.Add($_.Name)
}
$dependencyPackages = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)
$importOwners = [Collections.Generic.List[object]]::new()
foreach ($binary in Get-ChildItem "$($stage.FullName)\bin" -File |
    Where-Object { $_.Extension -in '.exe', '.dll' }) {
    foreach ($import in Get-PeImports $binary.FullName) {
        if ($stageBinNames.Contains($import)) { continue }
        $dependencyPath = Join-Path $dependencyBin.FullName $import
        if (Test-Path -LiteralPath $dependencyPath -PathType Leaf) {
            $ownerQueryPath = "/mingwarm64/bin/$import"
            $ownerOutput = @(
                & $pacman --root $integrationRoot.FullName --config $pacmanConfig `
                    -Qo $ownerQueryPath 2>&1
            )
            if ($LASTEXITCODE -ne 0 -or
                ($ownerOutput -join "`n") -notmatch '\sis owned by\s+(\S+)\s+(\S+)') {
                throw "Cannot identify the package owner for staged import '$import'."
            }
            $owner = $Matches[1]
            [void]$dependencyPackages.Add($owner)
            $importOwners.Add([ordered]@{
                binary = $binary.Name
                import = $import
                package = $owner
                version = $Matches[2]
            })
        } elseif ($systemDllNames.Contains($import) -or
            $import.StartsWith('api-ms-win-', [StringComparison]::OrdinalIgnoreCase) -or
            $import.StartsWith('ext-ms-', [StringComparison]::OrdinalIgnoreCase)) {
            continue
        } else {
            throw "Staged gettext binary has unresolved external import '$import': $($binary.FullName)"
        }
    }
}
$dependencies = @($dependencyPackages | Sort-Object)
if ('mingw-w64-aarch64-libiconv' -cnotin $dependencies) {
    throw 'Staged gettext payload does not resolve its required libiconv dependency.'
}

$markers = @('C:\ap', 'C:/ap', '/c/ap', '.copilot', 'session-state')
function Test-ByteSequence([byte[]] $Haystack, [byte[]] $Needle) {
    if ($Needle.Length -eq 0 -or $Needle.Length -gt $Haystack.Length) { return $false }
    for ($i = 0; $i -le $Haystack.Length - $Needle.Length; $i++) {
        if ($Haystack[$i] -ne $Needle[0]) { continue }
        $match = $true
        for ($j = 1; $j -lt $Needle.Length; $j++) {
            if ($Haystack[$i + $j] -ne $Needle[$j]) {
                $match = $false
                break
            }
        }
        if ($match) { return $true }
    }
    $false
}
foreach ($marker in $markers) {
    $needle = [Text.Encoding]::ASCII.GetBytes($marker)
    $matches = @(Get-ChildItem $stage.FullName -Recurse -File | Where-Object {
        Test-ByteSequence ([IO.File]::ReadAllBytes($_.FullName)) $needle
    })
    if ($matches.Count) {
        throw "Staged gettext payload contains forbidden marker '$marker': $($matches.FullName -join ', ')"
    }
}

New-Item -ItemType Directory -Path "$OutputDirectory\payload", "$OutputDirectory\evidence" | Out-Null
$payloadPrefix = "$OutputDirectory\payload\mingwarm64"
Copy-Item -LiteralPath $stage.FullName -Destination $payloadPrefix -Recurse
foreach ($log in $ConfigureLog, $BuildLog, $CheckLog, $InstallLog) {
    Copy-Item -LiteralPath $log -Destination "$OutputDirectory\evidence\$(Split-Path $log -Leaf)"
}

$buildDocument = Get-Content $buildReceiptFile.FullName -Raw | ConvertFrom-Json
$sourceRoot = Get-Item -LiteralPath $buildDocument.source.path
$licenseFiles = @(
    'COPYING',
    'gettext-runtime\COPYING',
    'gettext-runtime\intl\COPYING.LIB',
    'gettext-runtime\libasprintf\COPYING',
    'gettext-runtime\libasprintf\COPYING.LIB',
    'gettext-tools\COPYING',
    'gettext-tools\gnulib-lib\libxml\COPYING',
    'gnulib-local\lib\libxml\COPYING',
    'gettext-tools\tree-sitter-0.23.2\LICENSE',
    'gettext-tools\tree-sitter-0.23.2\lib\src\unicode\LICENSE',
    'gettext-tools\tree-sitter-d-0.8.2\LICENSE',
    'gettext-tools\tree-sitter-go-0.23.4\LICENSE',
    'gettext-tools\tree-sitter-ocaml-0.23.2\LICENSE',
    'gettext-tools\tree-sitter-rust-0.23.2\LICENSE',
    'gettext-tools\tree-sitter-typescript-0.23.2\LICENSE'
)
foreach ($relative in $licenseFiles) {
    $sourceLicense = Join-Path $sourceRoot.FullName $relative
    if (-not (Test-Path -LiteralPath $sourceLicense -PathType Leaf)) {
        throw "Signed gettext source is missing required license evidence: $relative"
    }
    $destinationLicense = Join-Path "$payloadPrefix\share\licenses\gettext" $relative
    New-Item -ItemType Directory -Path (Split-Path $destinationLicense) -Force | Out-Null
    Copy-Item $sourceLicense $destinationLicense
}

$stageManifest = @(
    Get-ChildItem $payloadPrefix -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = [IO.Path]::GetRelativePath($payloadPrefix, $_.FullName).Replace('\', '/')
                bytes = $_.Length
                sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
)
$stageManifestPath = "$OutputDirectory\evidence\stage-manifest.json"
$stageManifest | ConvertTo-Json -Depth 4 | Set-Content $stageManifestPath -Encoding utf8
$dependsLiteral = ($dependencies | ForEach-Object { "'$_'" }) -join ' '
$pkgbuild = @'
pkgname=mingw-w64-aarch64-gettext
pkgver=1.0
pkgrel=1
pkgdesc='GNU internationalization runtime libraries and tools (mingw-w64)'
arch=('any')
url='https://www.gnu.org/software/gettext/'
license=('spdx:GPL-3.0-or-later' 'spdx:LGPL-2.1-or-later' 'spdx:MIT' 'LicenseRef-Unicode-3.0')
depends=(@DEPENDS@)
options=('staticlibs' '!strip' '!zipman' '!purge' '!debug')

package() {
  cp -a "$startdir/payload/mingwarm64" "$pkgdir/"
}
'@
$pkgbuild = $pkgbuild.Replace('@DEPENDS@', $dependsLiteral)
[IO.File]::WriteAllText(
    (Join-Path $OutputDirectory 'PKGBUILD'),
    $pkgbuild.Replace("`r`n", "`n"),
    [Text.UTF8Encoding]::new($false)
)
$receipt = [ordered]@{
    schema = 1
    status = 'canonical-prefix-gettext-package-prepared'
    sourceVersion = '1.0'
    priorMislabelledPackage = [ordered]@{
        identity = 'mingw-w64-aarch64-gettext-0.26-1'
        sha256 = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
        issue = 'The retained source and binaries report GNU gettext 1.0, not 0.26, and embed a private staging prefix.'
    }
    packageVersion = '1.0-1'
    pinnedOwnershipRecipe = [ordered]@{
        repository = 'git-for-windows/MINGW-packages'
        commit = 'd65b87de173ac2209a63cef8c4528669b5571fd3'
        path = $pinnedOwnershipRecipe.FullName
        sha256 = '2753811ebaef825701261cead50289472134122fd2b0fb87dc3599cf2a53c37a'
        use = 'File ownership, dependency, and license-install rules; old 0.19.8.1 source identity is not reused'
    }
    dependencies = $dependencies
    dependencyImportOwners = @($importOwners)
    recipe = [ordered]@{
        path = (Join-Path $OutputDirectory 'PKGBUILD')
        sha256 = (Get-FileHash (Join-Path $OutputDirectory 'PKGBUILD') -Algorithm SHA256).Hash.ToLowerInvariant()
        appliedPatches = @()
    }
    buildReceipt = [ordered]@{
        path = $buildReceiptFile.FullName
        sha256 = (Get-FileHash $buildReceiptFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    stagedPrefix = $stage.FullName
    stagedFiles = $stageManifest.Count
    licenseFiles = $licenseFiles
    stageManifest = [ordered]@{
        path = (Get-Item $stageManifestPath).FullName
        sha256 = (Get-FileHash $stageManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        includesEveryFileHash = $true
    }
    evidence = foreach ($log in $ConfigureLog, $BuildLog, $CheckLog, $InstallLog) {
        [ordered]@{
            path = (Get-Item -LiteralPath $log).FullName
            sha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content "$OutputDirectory\preparation.json" -Encoding utf8
$receipt
