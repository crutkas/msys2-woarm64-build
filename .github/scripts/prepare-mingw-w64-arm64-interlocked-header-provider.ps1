param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRepository,

    [Parameter(Mandatory = $true)]
    [string]$Bash,

    [Parameter(Mandatory = $true)]
    [string]$Compiler,

    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'

$sourceCommit = '70d63e7c9a477b8b275a9782b289fbf1614b6e9e'
$originalHeaderSha = 'b4b1ac36669b315ebdcee4d4e01731419e714a9663174467fe4adb1da1ca2a29'
$patchedHeaderSha = '8e0d3b2f2f94969faf166d8d9a0d4eb5e358a32be6bd7e99fc76e552ebfc909a'
$target = 'aarch64-w64-mingw32'
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$applier = Join-Path $PSScriptRoot 'apply-mingw-w64-arm64-interlocked-exchange-ordering.sh'
$codegenTest = Join-Path $PSScriptRoot 'test-mingw-w64-arm64-interlocked-exchange-ordering.ps1'
$runtimeTest = Join-Path $PSScriptRoot 'test-mingw-w64-arm64-interlocked-exchange-runtime.ps1'

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
$actualOriginalSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualOriginalSha -ne $originalHeaderSha) {
    throw "Unexpected original intrinsic header identity: $actualOriginalSha"
}

$baselineIncludeRoot = Join-Path $controlsRoot 'baseline-include'
$baselineHeaderDirectory = Join-Path $baselineIncludeRoot 'psdk_inc'
New-Item -ItemType Directory -Path $baselineHeaderDirectory | Out-Null
Copy-Item $sourceHeader (Join-Path $baselineHeaderDirectory 'intrin-impl.h')

& $Bash $applier $sourceRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$actualPatchedSha = (Get-FileHash $sourceHeader -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualPatchedSha -ne $patchedHeaderSha) {
    throw "Unexpected patched intrinsic header identity: $actualPatchedSha"
}

$changedPaths = @(& git -C $sourceRoot diff --name-only)
if ($LASTEXITCODE -ne 0 -or
    $changedPaths.Count -ne 1 -or
    $changedPaths[0] -ne 'mingw-w64-headers/include/psdk_inc/intrin-impl.h') {
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
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    --format=posix --pax-option=delete=atime,delete=ctime \
    -I "zstd -19 -T0" -cf "$root/provider.tar.zst" \
    -C "$root/stage" mingwarm64
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

$compilerTarget = (& $Compiler -dumpmachine).Trim()
if ($LASTEXITCODE -ne 0 -or $compilerTarget -ne $target) {
    throw "Unexpected compiler target: $compilerTarget"
}

$baselineAssembly = Join-Path $controlsRoot 'baseline-interlocked-exchange.s'
$codegenFixture = Join-Path $repositoryRoot 'tests\arm64-interlocked-exchange-ordering.c'
& $Compiler -O2 -S -I $baselineIncludeRoot $codegenFixture -o $baselineAssembly
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
    schema = 'mingw-w64-arm64-interlocked-header-provider-v2'
    source = [ordered]@{
        commit = $actualCommit
        original_header_sha256 = $actualOriginalSha
        patched_header_sha256 = $actualPatchedSha
        changed_paths = $changedPaths
    }
    recipe = [ordered]@{
        patch_sha256 = (Get-FileHash (Join-Path $PSScriptRoot 'mingw-w64-arm64-interlocked-exchange-ordering.patch') -Algorithm SHA256).Hash.ToLowerInvariant()
        applier_sha256 = (Get-FileHash $applier -Algorithm SHA256).Hash.ToLowerInvariant()
        preparation_script_sha256 = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        codegen_test_sha256 = (Get-FileHash $codegenTest -Algorithm SHA256).Hash.ToLowerInvariant()
        runtime_test_sha256 = (Get-FileHash $runtimeTest -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    provider = [ordered]@{
        root = $stageRoot
        include_root = $includeRoot
        file_count = $stageFiles.Count
        bytes = ($stageFiles | Measure-Object Length -Sum).Sum
        manifest = $manifestPath
        manifest_sha256 = (Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        installed_header_sha256 = $actualStageSha
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
