param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRepository,

    [Parameter(Mandatory = $true)]
    [string]$Bash,

    [Parameter(Mandatory = $true)]
    [string]$Compiler,

    [Parameter(Mandatory = $true)]
    [string]$BaselineIncludeRoot,

    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'

$sourceCommit = '70d63e7c9a477b8b275a9782b289fbf1614b6e9e'
$originalHeaderSha = 'b4b1ac36669b315ebdcee4d4e01731419e714a9663174467fe4adb1da1ca2a29'
$patchedHeaderSha = '8e0d3b2f2f94969faf166d8d9a0d4eb5e358a32be6bd7e99fc76e552ebfc909a'
$originalFastfailSourceSha = 'eeef89bcc19b9449fb67aa54ef0d5048dedd70464ad231281e250cd5699285e6'
$patchedFastfailSourceSha = '73f341f1783674ce3cd7c58a4e4aa545ece9f8e16e81474b0b0ac4f3fbd3f633'
$installedFastfailHeaderSha = 'dc7a4b6814d2529862e4e254935adddf1c6ffddb0cd5069d8146513c5f81efb9'
$fastfailPatchSha = '5c89fe22fe5b9a63b43ca4e82b6c1f9fee802cd259a75cf238a821d44529ebd6'
$expectedHeaderCount = 1685
$expectedHeaderPathSetSha = 'c780e3df61a8154bf783634b355d9906658ad46536d5da0bb28cc3b857742681'
$expectedBaselineHeaderCount = 2528
$expectedBaselineHeaderPathSetSha = 'a441d95442647b3e5e11976509d32cea46a625c07bdc986e75ba689945da4321'
$expectedBaselineOnlyCount = 843
$expectedBaselineOnlyPathSetSha = '8bf8d4141d58ed4cfd9f08f61eceb750d25195b15f15d04ae288a80435ccf080'
$target = 'aarch64-w64-mingw32'
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$applier = Join-Path $PSScriptRoot 'apply-mingw-w64-arm64-interlocked-exchange-ordering.sh'
$fastfailApplier = Join-Path $PSScriptRoot 'apply-mingw-w64-arm64-fastfail-c89-inline.sh'
$codegenTest = Join-Path $PSScriptRoot 'test-mingw-w64-arm64-interlocked-exchange-ordering.ps1'
$runtimeTest = Join-Path $PSScriptRoot 'test-mingw-w64-arm64-interlocked-exchange-runtime.ps1'
$c89Test = Join-Path $PSScriptRoot 'test-mingw-w64-arm64-fastfail-c89.ps1'

function Get-LfNormalizedSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $text = [System.IO.File]::ReadAllText($Path)
    $normalized = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($normalized)
    $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [System.Convert]::ToHexString($hash).ToLowerInvariant()
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

if (Test-Path $OutputRoot) {
    throw "Refusing to overwrite output root: $OutputRoot"
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$sourceRoot = Join-Path $OutputRoot 'source'
$buildRoot = Join-Path $OutputRoot 'build'
$stageRoot = Join-Path $OutputRoot 'stage'
$controlsRoot = Join-Path $OutputRoot 'controls'
New-Item -ItemType Directory -Path $buildRoot, $stageRoot, $controlsRoot | Out-Null

& git -c core.autocrlf=false clone --quiet --no-hardlinks $SourceRepository $sourceRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& git -C $sourceRoot config core.autocrlf false

$actualCommit = (& git -C $sourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $sourceCommit) {
    throw "Unexpected MinGW-w64 source commit: $actualCommit"
}

$sourceHeader = Join-Path $sourceRoot 'mingw-w64-headers\include\psdk_inc\intrin-impl.h'
$fastfailSourceHeader = Join-Path $sourceRoot 'mingw-w64-headers\crt\_mingw.h.in'
$actualOriginalSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualOriginalSha -ne $originalHeaderSha) {
    throw "Unexpected original intrinsic header identity: $actualOriginalSha"
}
$actualOriginalFastfailSha = (Get-FileHash $fastfailSourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualOriginalFastfailSha -ne $originalFastfailSourceSha) {
    throw "Unexpected original fastfail header identity: $actualOriginalFastfailSha"
}
$fastfailPatch = Join-Path $PSScriptRoot 'mingw-w64-arm64-fastfail-c89-inline.patch'
$actualFastfailPatchSha = Get-LfNormalizedSha256 $fastfailPatch
if ($actualFastfailPatchSha -ne $fastfailPatchSha) {
    throw "Unexpected LF-normalized fastfail patch identity: $actualFastfailPatchSha"
}

$baselineCodegenIncludeRoot = Join-Path $controlsRoot 'baseline-include'
$baselineHeaderDirectory = Join-Path $baselineCodegenIncludeRoot 'psdk_inc'
New-Item -ItemType Directory -Path $baselineHeaderDirectory | Out-Null
Copy-Item $sourceHeader (Join-Path $baselineHeaderDirectory 'intrin-impl.h')

& $Bash $fastfailApplier $sourceRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $Bash $applier $sourceRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$actualPatchedSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualPatchedSha -ne $patchedHeaderSha) {
    throw "Unexpected patched intrinsic header identity: $actualPatchedSha"
}
$actualPatchedFastfailSha = (Get-FileHash $fastfailSourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualPatchedFastfailSha -ne $patchedFastfailSourceSha) {
    throw "Unexpected patched fastfail header identity: $actualPatchedFastfailSha"
}

$changedPaths = @(& git -C $sourceRoot diff --name-only)
if ($LASTEXITCODE -ne 0 -or
    $changedPaths.Count -ne 2 -or
    $changedPaths[0] -ne 'mingw-w64-headers/crt/_mingw.h.in' -or
    $changedPaths[1] -ne 'mingw-w64-headers/include/psdk_inc/intrin-impl.h') {
    throw "Unexpected source changes: $($changedPaths -join ', ')"
}
& git -C $sourceRoot diff --check
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$buildCommand = @'
set -euo pipefail
root=$(cygpath -u "$1")
cd "$root/build"
"$root/source/mingw-w64-headers/configure" \
    --host=aarch64-w64-mingw32 \
    --prefix=/mingwarm64/aarch64-w64-mingw32 \
    --enable-sdk=all \
    --with-default-msvcrt=ucrt \
    >"$root/controls/configure.log" 2>&1
make >"$root/controls/make.log" 2>&1
make DESTDIR="$root/stage" install >"$root/controls/install.log" 2>&1
install -m 644 "$root/source/mingw-w64-libraries/winpthreads/include/"*.h \
    "$root/stage/mingwarm64/aarch64-w64-mingw32/include/"
'@
& $Bash -c $buildCommand -- $OutputRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$includeRoot = Join-Path $stageRoot 'mingwarm64\aarch64-w64-mingw32\include'
$stageHeader = Join-Path $includeRoot 'psdk_inc\intrin-impl.h'
$actualStageSha = (Get-FileHash $stageHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualStageSha -ne $patchedHeaderSha) {
    throw "Unexpected installed intrinsic header identity: $actualStageSha"
}
$stageFastfailHeader = Join-Path $includeRoot '_mingw.h'
$actualStageFastfailSha = (Get-FileHash $stageFastfailHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualStageFastfailSha -ne $installedFastfailHeaderSha) {
    throw "Unexpected installed fastfail header identity: $actualStageFastfailSha"
}

$stageIncludeFiles = @(Get-ChildItem $includeRoot -Recurse -File | Sort-Object FullName)
$headerPathsPath = Join-Path $controlsRoot 'header-paths.txt'
$stageHeaderPaths = @(Write-RelativePathSet -Files $stageIncludeFiles -Root $includeRoot `
    -OutputPath $headerPathsPath)
$actualHeaderPathSetSha = (Get-FileHash $headerPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($stageHeaderPaths.Count -ne $expectedHeaderCount -or
    $actualHeaderPathSetSha -ne $expectedHeaderPathSetSha) {
    throw "Unexpected installed header path set: count=$($stageHeaderPaths.Count), sha256=$actualHeaderPathSetSha"
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

$pathDelta = @(Compare-Object $baselineHeaderPaths $stageHeaderPaths)
$stageOnlyPaths = @($pathDelta | Where-Object SideIndicator -eq '=>' |
    Select-Object -ExpandProperty InputObject | Sort-Object)
$baselineOnlyPaths = @($pathDelta | Where-Object SideIndicator -eq '<=' |
    Select-Object -ExpandProperty InputObject | Sort-Object)
$stageOnlyPathsPath = Join-Path $controlsRoot 'stage-only-header-paths.txt'
$baselineOnlyPathsPath = Join-Path $controlsRoot 'baseline-only-header-paths.txt'
$null = Write-PathSet -Paths $stageOnlyPaths -OutputPath $stageOnlyPathsPath
$null = Write-PathSet -Paths $baselineOnlyPaths -OutputPath $baselineOnlyPathsPath
$stageOnlyPathSetSha = (Get-FileHash $stageOnlyPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
$baselineOnlyPathSetSha = (Get-FileHash $baselineOnlyPathsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($stageOnlyPaths.Count -ne 0) {
    throw "Provider contains paths absent from the deployed toolchain: $($stageOnlyPaths -join ', ')"
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

$stagedDifferences = @()
foreach ($file in $stageIncludeFiles) {
    $relativePath = $file.FullName.Substring($includeRoot.Length + 1)
    $baselinePath = Join-Path $BaselineIncludeRoot $relativePath
    if (-not (Test-Path $baselinePath -PathType Leaf)) {
        throw "Staged header is absent from baseline toolchain: $relativePath"
    }
    $stageSha = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $baselineSha = (Get-FileHash $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($stageSha -ne $baselineSha) {
        $stagedDifferences += $relativePath.Replace('\', '/')
    }
}
if ($stagedDifferences.Count -ne 1 -or
    $stagedDifferences[0] -ne 'psdk_inc/intrin-impl.h') {
    throw "Unexpected staged differences from deployed toolchain: $($stagedDifferences -join ', ')"
}

$compilerTarget = (& $Compiler -dumpmachine).Trim()
if ($LASTEXITCODE -ne 0 -or $compilerTarget -ne $target) {
    throw "Unexpected compiler target: $compilerTarget"
}

$baselineAssembly = Join-Path $controlsRoot 'baseline-interlocked-exchange.s'
$codegenFixture = Join-Path $repositoryRoot 'tests\arm64-interlocked-exchange-ordering.c'
& $Compiler -O2 -S -I $baselineCodegenIncludeRoot $codegenFixture -o $baselineAssembly
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$baselineAssemblyText = Get-Content $baselineAssembly -Raw
foreach ($helper in '__aarch64_swp4_sync', '__aarch64_swp8_sync') {
    if ($baselineAssemblyText -notmatch [regex]::Escape($helper)) {
        throw "Baseline did not reproduce acquire-only helper: $helper"
    }
}
if ($baselineAssemblyText -match '__aarch64_swp[48]_acq_rel') {
    throw 'Baseline unexpectedly emitted an acquire-release swap helper.'
}

& $codegenTest -Compiler $Compiler -IncludeRoot $includeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'codegen')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $runtimeTest -Compiler $Compiler -IncludeRoot $includeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'runtime')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $c89Test -Compiler $Compiler -IncludeRoot $includeRoot `
    -OutputDirectory (Join-Path $controlsRoot 'c89')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$runtimeExecutable = Join-Path $controlsRoot 'runtime\interlocked-exchange-runtime.exe'
$runtimeMachine = Get-PeMachine $runtimeExecutable
if ($runtimeMachine -ne 0xaa64) {
    throw ('Runtime control has unexpected PE machine 0x{0:x4}.' -f $runtimeMachine)
}
$compilerMachine = Get-PeMachine $Compiler
if ($compilerMachine -ne 0xaa64) {
    throw ('Compiler has unexpected PE machine 0x{0:x4}.' -f $compilerMachine)
}
$bashMachine = Get-PeMachine $Bash
$archivePath = Join-Path $OutputRoot 'provider.tar.zst'
$archiveCommand = @'
set -euo pipefail
root=$(cygpath -u "$1")
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    --format=posix --pax-option=delete=atime,delete=ctime \
    -I "zstd -19 -T0" -cf "$root/provider.tar.zst" \
    -C "$root/stage" mingwarm64
'@
& $Bash -c $archiveCommand -- $OutputRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$stageFiles = @(Get-ChildItem $stageRoot -Recurse -File | Sort-Object FullName)
$manifest = foreach ($file in $stageFiles) {
    [ordered]@{
        path = $file.FullName.Substring($stageRoot.Length + 1).Replace('\', '/')
        bytes = $file.Length
        sha256 = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifestPath = Join-Path $controlsRoot 'stage-manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content $manifestPath -Encoding utf8NoBOM

$handoff = [ordered]@{
    schema = 'mingw-w64-arm64-interlocked-header-provider-v3'
    source = [ordered]@{
        commit = $actualCommit
        original_header_sha256 = $actualOriginalSha
        patched_header_sha256 = $actualPatchedSha
        original_fastfail_header_sha256 = $actualOriginalFastfailSha
        patched_fastfail_header_sha256 = $actualPatchedFastfailSha
        changed_paths = $changedPaths
    }
    recipe = [ordered]@{
        patch_sha256 = (Get-FileHash (Join-Path $PSScriptRoot 'mingw-w64-arm64-interlocked-exchange-ordering.patch') -Algorithm SHA256).Hash.ToLowerInvariant()
        applier_sha256 = (Get-FileHash $applier -Algorithm SHA256).Hash.ToLowerInvariant()
        fastfail_patch_sha256 = $actualFastfailPatchSha
        fastfail_patch_hash_normalization = 'UTF-8 text with CRLF and lone CR normalized to LF'
        fastfail_patch_worktree_sha256 = (Get-FileHash $fastfailPatch -Algorithm SHA256).Hash.ToLowerInvariant()
        fastfail_applier_sha256 = (Get-FileHash $fastfailApplier -Algorithm SHA256).Hash.ToLowerInvariant()
        preparation_script_sha256 = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        codegen_test_sha256 = (Get-FileHash $codegenTest -Algorithm SHA256).Hash.ToLowerInvariant()
        runtime_test_sha256 = (Get-FileHash $runtimeTest -Algorithm SHA256).Hash.ToLowerInvariant()
        c89_test_sha256 = (Get-FileHash $c89Test -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    provider = [ordered]@{
        root = $stageRoot
        include_root = $includeRoot
        file_count = $stageFiles.Count
        bytes = ($stageFiles | Measure-Object Length -Sum).Sum
        manifest = $manifestPath
        manifest_sha256 = (Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        installed_header_sha256 = $actualStageSha
        installed_fastfail_header_sha256 = $actualStageFastfailSha
        header_count = $stageHeaderPaths.Count
        header_paths = $headerPathsPath
        header_paths_sha256 = $actualHeaderPathSetSha
        baseline_include_root = (Resolve-Path $BaselineIncludeRoot).Path
        baseline_header_count = $baselineHeaderPaths.Count
        baseline_header_paths = $baselineHeaderPathsPath
        baseline_header_paths_sha256 = $actualBaselineHeaderPathSetSha
        stage_only_header_count = $stageOnlyPaths.Count
        stage_only_header_paths = $stageOnlyPathsPath
        stage_only_header_paths_sha256 = $stageOnlyPathSetSha
        baseline_only_header_count = $baselineOnlyPaths.Count
        baseline_only_header_paths = $baselineOnlyPathsPath
        baseline_only_header_paths_sha256 = $baselineOnlyPathSetSha
        baseline_only_classification = [ordered]@{
            cxx_headers = $baselineOnlyCxxCount
            generated_c_sources = $baselineOnlyCSourceCount
            other = $baselineOnlyOtherPaths.Count
        }
        staged_differences_from_baseline = $stagedDifferences
        archive = $archivePath
        archive_sha256 = (Get-FileHash $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        archive_bytes = (Get-Item $archivePath).Length
    }
    compiler = [ordered]@{
        path = (Resolve-Path $Compiler).Path
        sha256 = (Get-FileHash $Compiler -Algorithm SHA256).Hash.ToLowerInvariant()
        target = $compilerTarget
        pe_machine = ('0x{0:x4}' -f $compilerMachine)
    }
    build_host = [ordered]@{
        bash = (Resolve-Path $Bash).Path
        bash_sha256 = (Get-FileHash $Bash -Algorithm SHA256).Hash.ToLowerInvariant()
        bash_pe_machine = ('0x{0:x4}' -f $bashMachine)
    }
    controls = [ordered]@{
        baseline_codegen = 'reproduced acquire-only __aarch64_swp4_sync and __aarch64_swp8_sync'
        codegen = 'passed'
        runtime = 'passed'
        c89 = 'passed'
        runtime_executable_sha256 = (Get-FileHash $runtimeExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
        runtime_pe_machine = ('0x{0:x4}' -f $runtimeMachine)
        expected_helpers = @('__aarch64_swp4_acq_rel', '__aarch64_swp8_acq_rel')
        forbidden_helpers = @('__aarch64_swp4_sync', '__aarch64_swp8_sync')
    }
    limitation = 'This replaces the pinned MinGW-w64 C target headers and winpthreads compatibility headers. Header configure/install used the recorded build-host Bash; code generation and runtime controls used the recorded native ARM64 compiler. It does not rebuild GCC, CRT libraries, C++ headers, or the already-qualified OpenSSL package.'
}
$handoffPath = Join-Path $OutputRoot 'handoff.json'
$handoff | ConvertTo-Json -Depth 6 | Set-Content $handoffPath -Encoding utf8NoBOM

[ordered]@{
    handoff = $handoffPath
    handoff_sha256 = (Get-FileHash $handoffPath -Algorithm SHA256).Hash.ToLowerInvariant()
    provider_manifest_sha256 = $handoff.provider.manifest_sha256
} | ConvertTo-Json
