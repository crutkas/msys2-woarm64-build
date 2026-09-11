[CmdletBinding()]
param(
    [string]$Manifest = 'C:\Users\crutkasLocal\.copilot\session-state\f6ea7713-2cec-41d5-b3f9-b4373e60fa33\files\posix-cache-combined-02\manifest.json',
    [string]$Stage = 'C:\Users\crutkasLocal\.copilot\session-state\f6ea7713-2cec-41d5-b3f9-b4373e60fa33\files\posix-cache-combined-02\payload',
    [string]$RuntimeExport = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\export.json',
    [string]$RuntimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll',
    [string]$SourceRoot = 'C:\ap11-native-provider-intake\qualified-make-d70-v1\source',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\qualified-make-d70-v1',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$Strings = 'C:\agtc-libs-01\sdk\bin\aarch64-pc-cygwin-strings.exe'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedManifestHash = '819e6781207c7b218e89df02951148f35f65f13dfa51b1044bd7b14a3efb8c56'
$expectedPreparedSourceHash = '58cde81aa3e12332dd37f805f73a45914badaf9c876d45813b283c996a07cf62'
$builtRuntimeHash = 'a9275cd90461727aadde9d582cfb373c96078cb715f3755288ecc3f1f4deffe3'
$currentRuntimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$expectedRuntimeExportHash = '7913b174303df04d4840516e3d1181e3ab7c67efb1b9e151cac09c8c456f0418'
$recipeCommit = '21bfc351a0c20d4f7dd2c564456d99ed69395a18'

$sourceEvidence = [ordered]@{
    archive = [ordered]@{
        path = (Join-Path $SourceRoot 'make-4.4.1.tar.gz')
        sha256 = 'dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3'
    }
    signature = [ordered]@{
        path = (Join-Path $SourceRoot 'make-4.4.1.tar.gz.sig')
        sha256 = 'b0085e6c3f9a7461e739786a8d28dec9aeb090335bb8818e42b497fdeb73b929'
    }
    recipe = [ordered]@{
        path = (Join-Path $SourceRoot 'PKGBUILD')
        sha256 = '6a0faf368959fbf25a881b96881b1387e5c931862d3a6f5f54e739091ba15b79'
        commit = $recipeCommit
    }
    patch = [ordered]@{
        path = (Join-Path $SourceRoot '0001-fixes-building-with-gcc-15.patch')
        sha256 = '3bedb8aeef4316f4b909e42a3255fd2da4207a1594cc546538d83761efe59ffe'
    }
    verification_log = (Join-Path $SourceRoot 'signature-verification.log')
}

$payload = [ordered]@{
    'usr/bin/make.exe' = '6d740dcb18b4795e3d2326fcf390127b21c08993c1a15db49deac9b6440ac96d'
    'usr/include/gnumake.h' = '3e38df96688ba32938ece2070219684616bd157750c8ba5042ccb790a49dcacc'
    'usr/share/info/make.info' = 'f1c94cd2eaeacdd0825396e4f336701434380da93f8402b2eb64bd5249035a48'
    'usr/share/info/make.info-1' = '50b1810947f3053d81dc1b5349369c31cc30c90d1bd8886f62ca9b360bbced55'
    'usr/share/info/make.info-2' = '388254c7ed632acd86c4b6b65dd6eef4fb6cf62f982e526e78367d5236632399'
    'usr/share/info/make.info-3' = 'a80fbec33f1a6964cec008024032eafea729723a68485425b52b78e9cafaa714'
    'usr/share/licenses/make/COPYING' = 'e79e9c8a0c85d735ff98185918ec94ed7d175efc377012787aebcf3b80f0d90b'
    'usr/share/man/man1/make.1' = '6cfb2259badbd3c770e1943e9a9950742fd6e9405596d69aadee325faf83726d'
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
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
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

Assert-FileHash -Path $Manifest -Expected $expectedManifestHash
Assert-FileHash -Path $RuntimeExport -Expected $expectedRuntimeExportHash
Assert-FileHash -Path $RuntimeDll -Expected $currentRuntimeHash
foreach ($item in $sourceEvidence.Values) {
    if ($item -is [System.Collections.IDictionary] -and $item.Contains('sha256')) {
        Assert-FileHash -Path $item.path -Expected $item.sha256
    }
}
$verificationText = Get-Content -Raw -LiteralPath $sourceEvidence.verification_log
if ($verificationText -notmatch 'VALIDSIG B2508A90102F8AE3B12A0090DEACCAAEDB78137A .+ 6D4EEB02AD834703510B117680CB727A20C79BB2') {
    throw 'GNU make source signature verification does not bind the expected signing key'
}

$manifestData = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
$makeInput = @($manifestData.inputs | Where-Object { $_.input.package -eq 'make' })
if ($makeInput.Count -ne 1) {
    throw "Expected one make input in preserved manifest, found $($makeInput.Count)"
}
if ($makeInput[0].input.status -ne 'built-not-run' -or
    $makeInput[0].input.prepared_source.manifest_sha256 -ne $expectedPreparedSourceHash -or
    $makeInput[0].input.files.'usr/bin/msys-2.0.dll'.sha256 -ne $builtRuntimeHash) {
    throw 'Preserved make build identity does not match the expected old-runtime cohort'
}

$packageRoot = Join-Path $OutputDirectory 'package'
if (Test-Path -LiteralPath $packageRoot) {
    throw "Package output already exists: $packageRoot"
}
$payloadRoot = Join-Path $packageRoot 'payload'
New-Item -ItemType Directory -Path $payloadRoot | Out-Null
foreach ($entry in $payload.GetEnumerator()) {
    $manifestEntry = $manifestData.files.PSObject.Properties[$entry.Key]
    if ($null -eq $manifestEntry -or $manifestEntry.Value.sha256 -ne $entry.Value) {
        throw "Preserved manifest does not bind $($entry.Key)"
    }
    $source = Join-Path $Stage ($entry.Key -replace '/', '\')
    Assert-FileHash -Path $source -Expected $entry.Value
    $destination = Join-Path $payloadRoot ($entry.Key -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$template = Get-Content -Raw -LiteralPath (
    Join-Path $repoRoot 'arm64-git-recovery\native-packaging\qualified-utility\PKGBUILD.in'
)
$pkgbuild = $template.
    Replace('@@PACKAGE_NAME@@', 'make').
    Replace('@@PACKAGE_VERSION@@', '4.4.1').
    Replace('@@PACKAGE_RELEASE@@', '3').
    Replace('@@PACKAGE_EPOCH@@', '').
    Replace('@@PACKAGE_DESCRIPTION@@', 'GNU make utility to maintain groups of programs').
    Replace('@@PACKAGE_URL@@', 'https://www.gnu.org/software/make').
    Replace('@@PACKAGE_LICENSE@@', 'GPL-3.0-or-later').
    Replace('@@PACKAGE_DEPENDS@@', "'libintl' 'sh'").
    Replace('@@PACKAGE_PROVIDES@@', '').
    Replace('@@PAYLOAD_ROOT@@', (Convert-ToMsysPath -Path $payloadRoot)).
    Replace("options=('!strip' '!debug' 'staticlibs')", "options=('!debug' 'staticlibs')").
    Replace("`r`n", "`n")
Set-Content -LiteralPath (Join-Path $packageRoot 'PKGBUILD') -Value $pkgbuild -Encoding utf8NoBOM

$packageOutput = Join-Path $packageRoot 'packages'
$makepkgBuild = Join-Path $packageRoot 'makepkg-build'
New-Item -ItemType Directory -Path $packageOutput, $makepkgBuild | Out-Null
$msysPackageRoot = Convert-ToMsysPath -Path $packageRoot
$msysPackageOutput = Convert-ToMsysPath -Path $packageOutput
$msysMakepkgBuild = Convert-ToMsysPath -Path $makepkgBuild
$msysMakepkgConfig = Convert-ToMsysPath -Path $MakepkgConfig
$oldPath = $env:PATH
try {
    $env:PATH = Split-Path -Parent $Bash
    $command = @"
export PKGDEST='$msysPackageOutput'
export BUILDDIR='$msysMakepkgBuild'
cd '$msysPackageRoot'
/usr/bin/makepkg --config '$msysMakepkgConfig' --force --cleanbuild --noconfirm
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
if ($archives.Count -ne 1) {
    throw "Expected one make archive, found $($archives.Count)"
}
$archive = $archives[0]

$readbackRoot = Join-Path $OutputDirectory 'package-readback'
New-Item -ItemType Directory -Path $readbackRoot | Out-Null
& tar -xf $archive.FullName -C $readbackRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract packaged make archive'
}
$packagedMake = Join-Path $readbackRoot 'usr\bin\make.exe'
$packagedMakeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packagedMake).Hash.ToLowerInvariant()
if ($packagedMakeHash -eq $payload['usr/bin/make.exe']) {
    throw 'Standard makepkg stripping did not remove the producer debug information'
}
if (-not (Test-Path -LiteralPath $Strings -PathType Leaf)) {
    throw "Required strings tool is missing: $Strings"
}
$privateStrings = @(
    & $Strings -a $packagedMake |
        Select-String -Pattern '[A-Za-z]:[/\\].*(?:msys64[/\\]usr|mingwarm64|stage[/\\]usr)[/\\]'
)
if ($privateStrings.Count -ne 0) {
    throw "Packaged make still contains a private operational path: $($privateStrings[0].Line)"
}
Copy-Item -LiteralPath $RuntimeDll -Destination (Join-Path $readbackRoot 'usr\bin\msys-2.0.dll')

$work = Join-Path $readbackRoot 'work'
New-Item -ItemType Directory -Path $work | Out-Null
$makefile = ".PHONY: all`n`nall:`n`t`$(file >result.txt,native-make-d70-package-ok)`n"
[IO.File]::WriteAllText((Join-Path $work 'Makefile'), $makefile, [Text.UTF8Encoding]::new($false))
$oldPath = $env:PATH
try {
    $env:PATH = "$(Join-Path $readbackRoot 'usr\bin');C:\Windows\System32"
    $versionOutput = @(& $packagedMake --version 2>&1)
    if ($LASTEXITCODE -ne 0 -or $versionOutput[0] -ne 'GNU Make 4.4.1') {
        throw "Packaged make version readback failed: $($versionOutput -join "`n")"
    }
    Push-Location $work
    try {
        $runOutput = @(& $packagedMake --no-print-directory -f Makefile all 2>&1)
        $runExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($runExit -ne 0) {
        throw "Packaged make functional readback failed: $($runOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
}
$result = (Get-Content -Raw -LiteralPath (Join-Path $work 'result.txt')).Trim()
if ($result -ne 'native-make-d70-package-ok') {
    throw "Packaged make produced an unexpected result: $result"
}

$pkginfo = (& tar -xOf $archive.FullName '.PKGINFO') -join "`n"
foreach ($expectedLine in @(
    'pkgname = make',
    'pkgver = 4.4.1-3',
    'depend = libintl',
    'depend = sh'
)) {
    if ($pkginfo -notmatch [regex]::Escape($expectedLine)) {
        throw "Packaged make .PKGINFO is missing: $expectedLine"
    }
}

$manifestRows = @(
    Get-ChildItem -LiteralPath $payloadRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($payloadRoot.Length + 1).Replace('\', '/')
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
            bytes = $_.Length
        }
    }
)
$payloadManifestPath = Join-Path $OutputDirectory 'payload-manifest.json'
[ordered]@{
    schema = 1
    package = 'make'
    version = '4.4.1-3'
    files = $manifestRows
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $payloadManifestPath -Encoding utf8NoBOM

$exportPath = Join-Path $OutputDirectory 'export.json'
[ordered]@{
    schema = 1
    status = 'qualified-existing-native-make-exported-for-current-d70-runtime'
    provider = 'native-msys-qualified-make'
    version = 'v1'
    runtime_cohort = [ordered]@{
        built_against_sha256 = $builtRuntimeHash
        compatibility_readback_sha256 = $currentRuntimeHash
        rebuilt_for_current_runtime = $false
    }
    packages = @(
        [ordered]@{
            name = 'make'
            path = $archive.FullName
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive.FullName).Hash.ToLowerInvariant()
        }
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $exportPath -Encoding utf8NoBOM

$handoffPath = Join-Path $OutputDirectory 'handoff.json'
[ordered]@{
    schema = 1
    status = 'qualified-existing-native-make-packaged-for-current-d70-runtime'
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exportPath).Hash.ToLowerInvariant()
    }
    original_build = [ordered]@{
        manifest = [ordered]@{
            path = $Manifest
            sha256 = $expectedManifestHash
        }
        prepared_source_manifest_sha256 = $expectedPreparedSourceHash
        runtime_sha256 = $builtRuntimeHash
        binary_rebuilt = $false
        nls = 'disabled-by-original-qualified-build'
    }
    source_and_recipe = [ordered]@{
        upstream_archive = $sourceEvidence.archive
        detached_signature = $sourceEvidence.signature
        valid_signature = [ordered]@{
            signing_subkey = 'B2508A90102F8AE3B12A0090DEACCAAEDB78137A'
            primary_fingerprint = '6D4EEB02AD834703510B117680CB727A20C79BB2'
            verification_log = [ordered]@{
                path = $sourceEvidence.verification_log
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceEvidence.verification_log).Hash.ToLowerInvariant()
            }
        }
        msys2_recipe = $sourceEvidence.recipe
        gcc_15_patch = $sourceEvidence.patch
    }
    package_payload = [ordered]@{
        manifest = [ordered]@{
            path = $payloadManifestPath
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $payloadManifestPath).Hash.ToLowerInvariant()
        }
        original_binary_sha256 = $payload['usr/bin/make.exe']
        packaged_binary_sha256 = $packagedMakeHash
        packaging_transform = 'standard-makepkg-debug-symbol-stripping'
    }
    current_runtime_readback = [ordered]@{
        runtime_sha256 = $currentRuntimeHash
        native_process = $true
        host_architecture = 'arm64'
        target = 'aarch64-pc-cygwin'
        version = $versionOutput[0]
        result = $result
        exit_code = 0
    }
    controls = [ordered]@{
        producer_stage_modified = $false
        shared_prefixes_modified = $false
        old_runtime_compatibility_not_inferred = $true
        current_runtime_compatibility_executed = $true
        source_binary_reused_without_rebuild = $true
        debug_symbols_stripped_by_standard_packaging = $true
        private_operational_paths_absent_after_packaging = $true
        nls_disabled_disclosed = $true
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $archive.FullName, $exportPath, $handoffPath |
    Select-Object FullName, Length
