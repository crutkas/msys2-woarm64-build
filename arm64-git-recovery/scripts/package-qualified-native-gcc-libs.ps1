[CmdletBinding()]
param(
    [string]$ProducerHandoff = 'C:\agtc-package-01\export\handoff.json',
    [string]$StageManifest = 'C:\agtc-package-01\stage.manifest.json',
    [string]$Stage = 'C:\agtc-package-01\stage',
    [string]$RuntimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\gcc-libs-v1',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$Strings = 'C:\agtc-libs-01\sdk\bin\aarch64-pc-cygwin-strings.exe'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedHandoffHash = 'c403bee2810970a13f9f058e5cd60f5b86db14593be726d9c755b16d1ea6d48b'
$expectedManifestHash = '8bbb56dea2b09c7de844bf1f6d6a7b69f314dece7f7eb0bd897451aa3addcf68'
$expectedRuntimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$expectedImportHash = 'fac7ee56bb99f1c8aa06fd04c164f3b95e71a2fe3168e0b55db5fa02275bf32c'
$expectedCrtHash = '3f1d5aed644750ca496008c6c2bc5206da144da3e633065e0a41d0ef07dfeb0e'
$recipeSnapshot = 'C:\agtc-package-01\export\source\upstream-PKGBUILD'

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

function Assert-Reference {
    param(
        [Parameter(Mandatory)]
        [object]$Reference
    )

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

function Get-PackagedRelativePath {
    param([Parameter(Mandatory)][string]$SourceRelativePath)

    if ($SourceRelativePath.StartsWith('usr/share/info/', [StringComparison]::Ordinal)) {
        return "$SourceRelativePath.gz"
    }
    return $SourceRelativePath
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

function Get-PeIdentity {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        try {
            $stream.Position = 0x3c
            $peOffset = $reader.ReadUInt32()
            $stream.Position = $peOffset
            if ($reader.ReadUInt32() -ne 0x00004550) {
                throw "Invalid PE signature: $Path"
            }
            $machine = $reader.ReadUInt16()
            $stream.Position = $peOffset + 4 + 20
            $optionalMagic = $reader.ReadUInt16()
            if ($optionalMagic -ne 0x20b) {
                throw "Expected a PE32+ image: $Path"
            }
            $stream.Position = $peOffset + 4 + 20 + 0x46
            $dllCharacteristics = $reader.ReadUInt16()
            return [ordered]@{
                machine = ('0x{0:X4}' -f $machine)
                native_arm64 = ($machine -eq 0xaa64)
                pe32_plus = $true
                dll_characteristics = ('0x{0:X4}' -f $dllCharacteristics)
                dynamic_base = (($dllCharacteristics -band 0x0040) -ne 0)
            }
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

Assert-FileHash -Path $ProducerHandoff -Expected $expectedHandoffHash
Assert-FileHash -Path $StageManifest -Expected $expectedManifestHash
Assert-FileHash -Path $RuntimeDll -Expected $expectedRuntimeHash
if (-not (Test-Path -LiteralPath $Strings -PathType Leaf)) {
    throw "Required strings tool is missing: $Strings"
}

$handoff = Get-Content -Raw -LiteralPath $ProducerHandoff | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath $StageManifest | ConvertFrom-Json
if ($handoff.schema -ne 1 -or
    $handoff.status -ne 'native-msys-gcc-libs-producer-export-qualified' -or
    $handoff.packageCandidate.name -ne 'gcc-libs' -or
    $handoff.packageCandidate.version -ne '15.0.1-1' -or
    $handoff.packageCandidate.target -ne 'aarch64-pc-cygwin') {
    throw 'Producer handoff package identity is invalid'
}
if ($handoff.runtimeCohort.runtimeSha256 -ne $expectedRuntimeHash -or
    $handoff.runtimeCohort.importLibrarySha256 -ne $expectedImportHash -or
    $handoff.runtimeCohort.crt0Sha256 -ne $expectedCrtHash) {
    throw 'Producer handoff runtime cohort is invalid'
}
if ($handoff.stage.manifest.sha256 -ne $expectedManifestHash -or
    [int]$handoff.stage.files -ne 12 -or
    @($manifest.files.PSObject.Properties).Count -ne 12) {
    throw 'Producer stage manifest identity or file count is invalid'
}

Assert-FileHash -Path $recipeSnapshot -Expected $handoff.source.pinnedRecipe.sha256
Assert-Reference -Reference $handoff.source.sourceInventory
Assert-Reference -Reference $handoff.source.unwindSuccessor
Assert-Reference -Reference $handoff.source.effectiveSourceOverride
foreach ($reference in $handoff.source.patches) {
    Assert-Reference -Reference $reference
}
Assert-Reference -Reference $handoff.development.manifest
Assert-Reference -Reference $handoff.validation.normalLinkProof
Assert-Reference -Reference $handoff.validation.dynamicLoadProof
Assert-Reference -Reference $handoff.validation.sharedDebuggerParityProof
Assert-Reference -Reference $handoff.validation.libgccExportABI
foreach ($reference in $handoff.validation.commandsResults) {
    Assert-Reference -Reference $reference
}
Assert-Reference -Reference $handoff.documentation.files
foreach ($unsupported in $handoff.unsupported) {
    Assert-Reference -Reference $unsupported.sourceEvidence
    $configureEvidence = $unsupported.PSObject.Properties['configureEvidence']
    if ($null -ne $configureEvidence) {
        Assert-Reference -Reference $configureEvidence.Value
    }
}

$payloadRoot = Join-Path $OutputDirectory 'payload'
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory"
}
New-Item -ItemType Directory -Path $payloadRoot | Out-Null

foreach ($entry in $manifest.files.PSObject.Properties) {
    $source = Join-Path $Stage ($entry.Name -replace '/', '\')
    Assert-FileHash -Path $source -Expected $entry.Value.sha256
    $destination = Join-Path $payloadRoot ($entry.Name -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

$dllEntries = @($handoff.outputs | Where-Object { $_.kind -eq 'runtime-dll' })
if ($dllEntries.Count -ne 4) {
    throw "Expected four runtime DLLs, found $($dllEntries.Count)"
}
foreach ($entry in $dllEntries) {
    Assert-FileHash -Path $entry.path -Expected $entry.sha256
    $privateOperationalPaths = @(
        & $Strings -a $entry.path |
            Select-String -Pattern '[A-Za-z]:[/\\].*(?:msys64[/\\]usr|mingwarm64|stage[/\\]usr)[/\\]'
    )
    if ($privateOperationalPaths.Count -ne 0) {
        throw "Producer DLL contains a private operational path: $($entry.path)"
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$template = Get-Content -Raw -LiteralPath (
    Join-Path $repoRoot 'arm64-git-recovery\native-packaging\qualified-utility\PKGBUILD.in'
)
$pkgbuild = $template.
    Replace('@@PACKAGE_NAME@@', 'gcc-libs').
    Replace('@@PACKAGE_VERSION@@', '15.0.1').
    Replace('@@PACKAGE_RELEASE@@', '1').
    Replace('@@PACKAGE_EPOCH@@', '').
    Replace('@@PACKAGE_DESCRIPTION@@', 'Runtime libraries shipped by GCC').
    Replace('@@PACKAGE_URL@@', 'https://gcc.gnu.org/').
    Replace(
        '@@PACKAGE_LICENSE@@',
        'LGPL-3.0-or-later AND GPL-3.0-or-later WITH GCC-exception-3.1'
    ).
    Replace('@@PACKAGE_DEPENDS@@', '').
    Replace('@@PACKAGE_PROVIDES@@', '').
    Replace('@@PAYLOAD_ROOT@@', (Convert-ToMsysPath -Path $payloadRoot)).
    Replace("`r`n", "`n")
$packageRoot = Join-Path $OutputDirectory 'package'
New-Item -ItemType Directory -Path $packageRoot | Out-Null
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
    throw "Expected one gcc-libs archive, found $($archives.Count)"
}
$archive = $archives[0]
$readbackRoot = Join-Path $OutputDirectory 'readback'
New-Item -ItemType Directory -Path $readbackRoot | Out-Null
& tar -xf $archive.FullName -C $readbackRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract packaged gcc-libs archive'
}

foreach ($entry in $manifest.files.PSObject.Properties) {
    $packagedRelativePath = Get-PackagedRelativePath -SourceRelativePath $entry.Name
    $extracted = Join-Path $readbackRoot ($packagedRelativePath -replace '/', '\')
    if ($packagedRelativePath.EndsWith('.gz', [StringComparison]::Ordinal)) {
        Assert-GzipPayloadHash -Path $extracted -Expected $entry.Value.sha256
    }
    else {
        Assert-FileHash -Path $extracted -Expected $entry.Value.sha256
    }
}
$normalLinkProof = Get-Content -Raw -LiteralPath $handoff.validation.normalLinkProof.path |
    ConvertFrom-Json
$packagedPeReadback = @(
    $dllEntries | ForEach-Object {
        $packagedDll = Join-Path $readbackRoot (
            $_.path.Substring($Stage.Length + 1)
        )
        $pe = Get-PeIdentity -Path $packagedDll
        if (-not $pe.native_arm64 -or -not $pe.dynamic_base) {
            throw "Packaged DLL is not ARM64/ASLR: $packagedDll"
        }
        $proofProperty = $normalLinkProof.pe.PSObject.Properties[$_.soname]
        if ($null -eq $proofProperty) {
            throw "Producer proof is missing PE evidence for $($_.soname)"
        }
        $producerPe = $proofProperty.Value
        if ($producerPe.SHA256 -ne $_.sha256 -or
            -not $producerPe.NativeArm64 -or
            -not $producerPe.DynamicBase) {
            throw "Producer PE evidence does not match $($_.soname)"
        }
        [ordered]@{
            soname = $_.soname
            sha256 = $_.sha256
            machine = $pe.machine
            pe32_plus = $pe.pe32_plus
            dll_characteristics = $pe.dll_characteristics
            dynamic_base = $pe.dynamic_base
            producer_import_dlls = @($producerPe.Imports | ForEach-Object { $_.Dll })
        }
    }
)
$pkginfo = (& tar -xOf $archive.FullName '.PKGINFO') -join "`n"
foreach ($expectedLine in @(
    'pkgname = gcc-libs',
    'pkgver = 15.0.1-1'
)) {
    if ($pkginfo -notmatch [regex]::Escape($expectedLine)) {
        throw "Packaged gcc-libs .PKGINFO is missing: $expectedLine"
    }
}
if ($pkginfo -match '(?m)^depend = ') {
    throw 'Packaged gcc-libs unexpectedly declares a package dependency'
}

$probeRoot = Join-Path $readbackRoot 'probe'
New-Item -ItemType Directory -Path $probeRoot | Out-Null
Copy-Item -LiteralPath $RuntimeDll -Destination (Join-Path $probeRoot 'msys-2.0.dll')
foreach ($dll in $dllEntries) {
    Copy-Item -LiteralPath (
        Join-Path $readbackRoot ($dll.path.Substring($Stage.Length + 1))
    ) -Destination $probeRoot
}
$probeFiles = @(
    [ordered]@{
        name = 'consumer.exe'
        sha256 = 'eee9fa7439c0c99d618ddddf914562c9007acb98b4da906d79d9eb197d2c754c'
        expected = 'native-msys-shared-gcc-cpp-ok'
    },
    [ordered]@{
        name = 'consumer-c.exe'
        sha256 = '2d4d0738706f91933096552369b5db1f04a8920443ea608b2da7ebe88e2b2992'
        expected = 'native-msys-shared-gcc-c-ok'
    },
    [ordered]@{
        name = 'provider.dll'
        sha256 = '69c93ed3e0a74eafa92fbb0ac0e08aa37f5bec3091f2d3807dea9e097eee48b6'
        expected = $null
    }
)
foreach ($probe in $probeFiles) {
    $source = Join-Path (Split-Path -Parent $handoff.validation.normalLinkProof.path) $probe.name
    Assert-FileHash -Path $source -Expected $probe.sha256
    Copy-Item -LiteralPath $source -Destination $probeRoot
}

$readbacks = @()
$oldPath = $env:PATH
try {
    $env:PATH = "$probeRoot;C:\Windows\System32"
    foreach ($probe in @($probeFiles | Where-Object { $null -ne $_.expected })) {
        $output = @(& (Join-Path $probeRoot $probe.name) 2>&1)
        $exit = $LASTEXITCODE
        if ($exit -ne 0 -or ($output -join "`n").Trim() -ne $probe.expected) {
            throw "$($probe.name) packaged runtime readback failed: $($output -join "`n")"
        }
        $readbacks += [ordered]@{
            executable = $probe.name
            executable_sha256 = $probe.sha256
            native_process = $true
            host_architecture = 'arm64'
            target = 'aarch64-pc-cygwin'
            exit_code = 0
            output = $output
        }
    }
}
finally {
    $env:PATH = $oldPath
}

$payloadManifestPath = Join-Path $OutputDirectory 'payload-manifest.json'
[ordered]@{
    schema = 1
    package = 'gcc-libs'
    version = '15.0.1-1'
    runtime_sha256 = $expectedRuntimeHash
    files = @(
        $manifest.files.PSObject.Properties | Sort-Object Name | ForEach-Object {
            $packagedRelativePath = Get-PackagedRelativePath -SourceRelativePath $_.Name
            $packagedPath = Join-Path $readbackRoot ($packagedRelativePath -replace '/', '\')
            [ordered]@{
                source_path = $_.Name
                source_sha256 = $_.Value.sha256
                package_path = $packagedRelativePath
                package_sha256 = (
                    Get-FileHash -Algorithm SHA256 -LiteralPath $packagedPath
                ).Hash.ToLowerInvariant()
                package_bytes = (Get-Item -LiteralPath $packagedPath).Length
                package_transform = if ($packagedRelativePath.EndsWith(
                    '.gz',
                    [StringComparison]::Ordinal
                )) {
                    'makepkg-info-gzip'
                }
                else {
                    'none'
                }
            }
        }
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $payloadManifestPath -Encoding utf8NoBOM

$exportPath = Join-Path $OutputDirectory 'export.json'
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-gcc-libs-exported'
    provider = 'native-msys-gcc-libs'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $expectedRuntimeHash
        import_library_sha256 = $expectedImportHash
        crt0_sha256 = $expectedCrtHash
    }
    packages = @(
        [ordered]@{
            name = 'gcc-libs'
            path = $archive.FullName
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive.FullName).Hash.ToLowerInvariant()
        }
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $exportPath -Encoding utf8NoBOM

$handoffPath = Join-Path $OutputDirectory 'handoff.json'
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-gcc-libs-packaged'
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exportPath).Hash.ToLowerInvariant()
    }
    producer = [ordered]@{
        handoff = [ordered]@{
            path = $ProducerHandoff
            sha256 = $expectedHandoffHash
        }
        stage_manifest = [ordered]@{
            path = $StageManifest
            sha256 = $expectedManifestHash
            original_status = $manifest.status
            qualification_superseded_by_final_handoff = $true
        }
        source_commit = $handoff.source.commit
        recipe_commit = $handoff.source.pinnedRecipe.commit
        recipe_sha256 = $handoff.source.pinnedRecipe.sha256
    }
    package_payload = [ordered]@{
        manifest = [ordered]@{
            path = $payloadManifestPath
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $payloadManifestPath).Hash.ToLowerInvariant()
        }
        runtime_dlls = @(
            $dllEntries | ForEach-Object {
                [ordered]@{
                    soname = $_.soname
                    sha256 = $_.sha256
                }
            }
        )
        pe_readback = $packagedPeReadback
        packaged_dll_bytes_unchanged = $true
        development_files_excluded = $true
        unsupported_components_not_provided = @('libquadmath', 'libvtv')
    }
    current_runtime_readbacks = $readbacks
    controls = [ordered]@{
        native_arm64 = $true
        producer_stage_hashes_verified = $true
        producer_stage_modified = $false
        shared_prefixes_modified = $false
        private_operational_paths_absent = $true
        strip_disabled_to_preserve_proof_qualified_dll_hashes = $true
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $archive.FullName, $exportPath, $handoffPath |
    Select-Object FullName, Length
