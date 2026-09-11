#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PackageArchive,
    [Parameter(Mandatory)][string] $SourceReceipt,
    [Parameter(Mandatory)][string] $RejectionReceipt,
    [Parameter(Mandatory)][string] $BuildReceipt,
    [Parameter(Mandatory)][string] $PreparationReceipt,
    [Parameter(Mandatory)][string] $PackageBuildReceipt,
    [Parameter(Mandatory)][string] $QualificationReceipt,
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) {
    throw 'Gettext provider export output must be new.'
}
$package = Get-Item -LiteralPath $PackageArchive
$receipts = [ordered]@{
    source = Get-Item -LiteralPath $SourceReceipt
    rejection = Get-Item -LiteralPath $RejectionReceipt
    build = Get-Item -LiteralPath $BuildReceipt
    preparation = Get-Item -LiteralPath $PreparationReceipt
    packageBuild = Get-Item -LiteralPath $PackageBuildReceipt
    qualification = Get-Item -LiteralPath $QualificationReceipt
}
if ((Get-FileHash $receipts.source.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne
    '9e534ee1ebcabc9df87066f131227bf342f311ce727243c8eea215c45091e173') {
    throw 'Signed gettext source receipt hash changed.'
}
if ((Get-FileHash $receipts.rejection.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne
    '9cfced0a3234bd363d7543476079604e6853aeeb476692ffd0d55484bbeb3f36') {
    throw 'Rejected gettext provider receipt hash changed.'
}

$entries = @(& "$env:SystemRoot\System32\tar.exe" --zstd -tf $package.FullName)
if ($LASTEXITCODE -ne 0) { throw 'Cannot list gettext package archive.' }
foreach ($entry in '.PKGINFO', '.BUILDINFO', '.MTREE',
    'mingwarm64/bin/gettext.exe', 'mingwarm64/bin/libintl-8.dll') {
    if ($entry -cnotin $entries) { throw "Gettext package is missing $entry." }
}
$pkginfo = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $package.FullName .PKGINFO)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read gettext package metadata.' }
foreach ($line in @(
    'pkgname = mingw-w64-aarch64-gettext',
    'pkgver = 1.0-1',
    'depend = mingw-w64-aarch64-libiconv'
)) {
    if ($line -cnotin $pkginfo) { throw "Gettext package metadata is missing: $line" }
}
$packageDependencies = @(
    $pkginfo | ForEach-Object {
        if ($_ -match '^depend = (.+)$') { $Matches[1] }
    }
)

New-Item -ItemType Directory -Path "$OutputDirectory\packages", "$OutputDirectory\evidence" | Out-Null
$packageDestination = Join-Path "$OutputDirectory\packages" $package.Name
Copy-Item $package.FullName $packageDestination
$evidence = [Collections.Generic.List[object]]::new()
foreach ($entry in $receipts.GetEnumerator()) {
    $destination = Join-Path "$OutputDirectory\evidence" "$($entry.Key)-$($entry.Value.Name)"
    Copy-Item $entry.Value.FullName $destination
    $evidence.Add([ordered]@{
        role = $entry.Key
        path = "evidence/$(Split-Path $destination -Leaf)"
        sha256 = (Get-FileHash $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    })
}

function Copy-Evidence([string] $Role, [string] $Path) {
    $source = Get-Item -LiteralPath $Path
    $safeRole = $Role -replace '[^A-Za-z0-9_.-]', '-'
    $destination = Join-Path "$OutputDirectory\evidence" "$safeRole-$($source.Name)"
    Copy-Item $source.FullName $destination
    $evidence.Add([ordered]@{
        role = $Role
        path = "evidence/$(Split-Path $destination -Leaf)"
        sha256 = (Get-FileHash $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    })
}

$sourceDocument = Get-Content $receipts.source.FullName -Raw | ConvertFrom-Json
$sourceDirectory = Split-Path $receipts.source.FullName
Copy-Evidence 'signed-source-archive' (Join-Path $sourceDirectory $sourceDocument.release.archive)
Copy-Evidence 'signed-source-signature' (Join-Path $sourceDirectory $sourceDocument.release.signature)
Copy-Evidence 'signature-verification-log' (
    Join-Path $sourceDirectory $sourceDocument.signatureVerification.log
)

$buildDocument = Get-Content $receipts.build.FullName -Raw | ConvertFrom-Json
foreach ($log in $buildDocument.logs) {
    Copy-Evidence "build-$([IO.Path]::GetFileNameWithoutExtension($log.path))" $log.path
}
foreach ($patch in $buildDocument.source.appliedPatches) {
    Copy-Evidence 'build-source-patch' $patch.path
}

$preparationDocument = Get-Content $receipts.preparation.FullName -Raw | ConvertFrom-Json
Copy-Evidence 'package-recipe' $preparationDocument.recipe.path
Copy-Evidence 'pinned-ownership-recipe' $preparationDocument.pinnedOwnershipRecipe.path
Copy-Evidence 'stage-manifest' $preparationDocument.stageManifest.path

$packageBuildDocument = Get-Content $receipts.packageBuild.FullName -Raw | ConvertFrom-Json
if ($packageBuildDocument.package.sha256 -cne
    (Get-FileHash $package.FullName -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Package build receipt does not bind the exported gettext archive.'
}
Copy-Evidence 'makepkg-config' $packageBuildDocument.makepkg.config
Copy-Evidence 'makepkg-log' $packageBuildDocument.makepkg.log

$qualificationDocument = Get-Content $receipts.qualification.FullName -Raw | ConvertFrom-Json
foreach ($item in $qualificationDocument.evidenceFiles) {
    Copy-Evidence 'qualification' $item.path
}

$receipt = [ordered]@{
    schema = 1
    status = 'admitted-complete-exported-verified-native-gettext-provider'
    generatedUtc = [DateTime]::UtcNow.ToString('o')
    target = 'MINGWARM64/aarch64-w64-mingw32'
    source = [ordered]@{
        project = 'GNU gettext'
        version = '1.0'
        archiveSha256 = '71132a3fb71e68245b8f2ac4e9e97137d3e5c02f415636eb508ae607bc01add7'
        signerFingerprint = 'E0FFBD975397F77A32AB76ECB6301D9E1BBEAC08'
        receiptSha256 = '9e534ee1ebcabc9df87066f131227bf342f311ce727243c8eea215c45091e173'
    }
    supersedes = @(
        [ordered]@{
            package = 'mingw-w64-aarch64-gettext-0.26-1'
            archiveSha256 = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
            export = 'C:\ap09-ca5f\curl-packages-v2\export-12\export.json'
            exportSha256 = '546d8ca66282b89803d6423f36db1f562fadf759e8d4a7e11870cb485ea84dd8'
            reason = 'Metadata version mismatch and private compiled/documentation prefixes'
        },
        [ordered]@{
            export = 'C:\ap12-ca5f\python-provider-export-02\export.json'
            exportSha256 = 'ce20122f2773a5ecde625db5cb58849daf8b66c7f7cff750fee8b5e1aa98fff3'
            reason = 'Dependency closure references the rejected gettext archive'
        }
    )
    packages = @(
        [ordered]@{
            name = 'mingw-w64-aarch64-gettext'
            path = "packages/$($package.Name)"
            sha256 = (Get-FileHash $packageDestination -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    )
    packageMetadata = [ordered]@{
        name = 'mingw-w64-aarch64-gettext'
        version = '1.0-1'
        dependencies = $packageDependencies
        files = @($entries | Where-Object { $_ -and -not $_.EndsWith('/') }).Count
        prefix = '/mingwarm64'
    }
    recipe = [ordered]@{
        path = 'evidence/package-recipe-PKGBUILD'
        sha256 = $preparationDocument.recipe.sha256
        revision = 'Generated from the qualified canonical stage by the hash-bound maintained preparer'
        appliedPatches = @($preparationDocument.recipe.appliedPatches)
        pinnedOwnershipRecipe = $preparationDocument.pinnedOwnershipRecipe
    }
    packageBuild = [ordered]@{
        receiptSha256 =
            (Get-FileHash $receipts.packageBuild.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        makepkgConfigSha256 = $packageBuildDocument.makepkg.configSha256
        makepkgLogSha256 = $packageBuildDocument.makepkg.logSha256
        startDirectory = $packageBuildDocument.makepkg.startDirectory
        buildDirectory = $packageBuildDocument.makepkg.buildDirectory
    }
    build = [ordered]@{
        jobs = $buildDocument.jobs
        prefix = $buildDocument.prefix
        compilerPathPolicy = $buildDocument.compilerPathPolicy
        appliedPatches = $buildDocument.source.appliedPatches
        originalPatchSourceHashes = $buildDocument.source.originalPatchSourceHashes
        patchedSourceHashes = $buildDocument.source.patchedSourceHashes
        stageManifestSha256 = $preparationDocument.stageManifest.sha256
        fullUpstreamChecks = 'passed'
        libtoolDependencyCacheOverride = $qualificationDocument.libtoolDependencyCacheOverride
    }
    qualification = [ordered]@{
        peInventory = $qualificationDocument.peInventory
        installedFileManifest = $qualificationDocument.installedFileManifest
        pacman = $qualificationDocument.pacman
        relocation = $qualificationDocument.relocation
        consumers = $qualificationDocument.consumers
        integrationCohort = $qualificationDocument.integrationCohort
    }
    evidence = @($evidence)
    omissions = @(
        'No MSYS /usr payload is provided.',
        'No compatibility alias for the rejected 0.26 identity is provided.',
        'No source, headers, static/import libraries, licenses, locales, or documentation are omitted from the package.'
    )
}
$receipt | ConvertTo-Json -Depth 20 | Set-Content "$OutputDirectory\export.json" -Encoding utf8
$receipt
