#requires -Version 7.3
[CmdletBinding(DefaultParameterSetName = 'CacheEpoch')]
param(
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory, ParameterSetName = 'CacheEpoch')][string] $Identities,
    [Parameter(Mandatory, ParameterSetName = 'CacheEpoch')][string] $Proof,
    [Parameter(Mandatory, ParameterSetName = 'CacheEpoch')][string] $CacheHandoff,
    [Parameter(Mandatory, ParameterSetName = 'NativeCohort')][string] $CohortManifest,
    [Parameter(Mandatory, ParameterSetName = 'HeaderDelta')][string] $HeaderDeltaManifest,
    [Parameter(Mandatory)][string] $PackageDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $CacheDirectory,
    [string] $RustPrefix,
    [string] $RustQualification,
    [string] $NativePython,
    [ValidateRange(1, 86400)][int] $NativeTimeoutSeconds = 86400,
    [ValidateRange(1, 16)][int] $Jobs = 2
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\package-runtime.ps1"
if ($PSCmdlet.ParameterSetName -eq 'HeaderDelta') {
    $qualifiedArgs = @{Prefix=$Prefix;Manifest=$HeaderDeltaManifest}
    $qualifier = "$PSScriptRoot\test-qualified-header-delta.ps1"
} elseif ($PSCmdlet.ParameterSetName -eq 'NativeCohort') {
    $qualifiedArgs = @{ Prefix = $Prefix; Manifest = $CohortManifest }
    $qualifier = "$PSScriptRoot\test-qualified-native-cohort.ps1"
} else {
    $qualifiedArgs = @{ Prefix = $Prefix; Identities = $Identities; Proof = $Proof; CacheHandoff = $CacheHandoff }
    $qualifier = "$PSScriptRoot\test-qualified-toolchain.ps1"
}
$before = & $qualifier @qualifiedArgs
$nativeDriver = if ($NativePython) { & "$PSScriptRoot\get-native-target-driver.ps1" -Python $NativePython } else { $null }
$rustBefore = $null
if ([bool]$RustPrefix -ne [bool]$RustQualification) { throw 'RustPrefix and RustQualification must be supplied together.' }
if ($RustPrefix) {
    $rustBefore = & "$PSScriptRoot\test-qualified-rust-bootstrap.ps1" -Prefix $RustPrefix -Qualification $RustQualification -GccEpoch $before.Epoch
}
$source = (Resolve-Path -LiteralPath $PackageDirectory).ProviderPath.TrimEnd('\')
$msys = (Resolve-Path -LiteralPath $MsysRoot).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
$cache = [IO.Path]::GetFullPath($CacheDirectory).TrimEnd('\')
foreach ($destination in $output, $cache) {
    foreach ($protected in $source, $msys, $before.Prefix) {
        if ($destination -ieq $protected -or $destination.StartsWith("$protected\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "Output/cache must be separate from recipe, MSYS and toolchain inputs: $destination"
        }
        if ($rustBefore -and ($destination -ieq $rustBefore.Prefix -or $destination.StartsWith("$($rustBefore.Prefix)\",[StringComparison]::OrdinalIgnoreCase))) {
            throw 'Output/cache must not write inside Rust runtime inputs.'
        }
    }
}
if (Test-Path -LiteralPath $output) { throw "Output directory must be new: $output" }
if (-not (Test-Path -LiteralPath "$source\PKGBUILD" -PathType Leaf)) { throw 'PackageDirectory must contain a PKGBUILD.' }
foreach ($required in 'usr\bin\bash.exe', 'usr\bin\makepkg', 'usr\bin\ccache.exe', 'etc\makepkg_mingw.d\mingwarm64.conf') {
    if (-not (Test-Path -LiteralPath (Join-Path $msys $required) -PathType Leaf)) {
        throw "Missing dedicated MSYS2 prerequisite: $required"
    }
}
New-Item -ItemType Directory -Path $output | Out-Null
$report = [ordered]@{
    Status = 'failed'
    BuildDriver = 'MSYS2 bootstrap (may be emulated x64); compiler inputs qualified Windows ARM64'
    Target = $before.Target
    Jobs = $Jobs
    VerifySourceSignatures = $true
    Before = $before
    RustBefore = $rustBefore
    NativeTargetDriver = $nativeDriver
    NativeTargetArgumentConversion = 'mingw'
    NativeExitScope = 'With NativePython: scoped job records native target exits and rejects unrelayed high exits or missing process observations; no compiler proxy'
    Source = $source
    RecipeSHA256 = (Get-FileHash -LiteralPath "$source\PKGBUILD" -Algorithm SHA256).Hash.ToLowerInvariant()
    CacheDirectory = Join-Path $cache $before.Epoch
}
try {
    $pipelineRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    $runtime = New-PackageRuntimeSnapshot $pipelineRoot (Join-Path $output 'pipeline')
    $runtimeRoot = $runtime.Root
    $revision = $runtime.Revision
    $report.PipelineSources = $runtime.Files
    $report.PipelineRevision = $revision
    $report.PipelineRuntime = $runtimeRoot
    $report.SourceInputs = @(Get-ChildItem -LiteralPath $source -Recurse -File | ForEach-Object {
        @{ Path = $_.FullName.Substring($source.Length + 1); SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    Copy-Item -LiteralPath $source -Destination "$output\recipe" -Recurse
    foreach ($inputFile in $report.SourceInputs) {
        if ((Get-FileHash -LiteralPath (Join-Path "$output\recipe" $inputFile.Path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputFile.SHA256) {
            throw "Recipe changed while being copied: $($inputFile.Path)"
        }
    }
    New-Item -ItemType Directory -Path "$output\packages", $report.CacheDirectory -Force | Out-Null
    $start = [Diagnostics.ProcessStartInfo]::new("$msys\usr\bin\bash.exe")
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = "$output\recipe"
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(CCACHE_|WOARM64_|GCC_|MSYS|MINGW)' -or $key -in @(
            'CC', 'CXX', 'AR', 'AS', 'LD', 'RANLIB', 'RC', 'WINDRES', 'STRIP', 'OBJCOPY', 'OBJDUMP',
            'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH',
            'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'MAKEPKG_LIBRARY', 'MAKEPKG_CONF',
            'BUILDDIR', 'SRCDEST', 'SRCPKGDEST', 'LOGDEST', 'PKGDEST',
            'NO_EXTRACT', 'INSTALL_PACKAGE', 'CLEAN_BUILD', 'RESOLVE_DEPENDENCIES', 'RUN_CHECKS',
            'VERIFY_SOURCE_SIGNATURES', 'CMAKE_BUILD_PARALLEL_LEVEL', 'CTEST_PARALLEL_LEVEL',
            'CARGO_TARGET_AARCH64_PC_WINDOWS_GNULLVM_LINKER', 'CARGO_ENCODED_RUSTFLAGS',
            'RUSTC', 'RUSTDOC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER'
        )) { $null = $start.Environment.Remove($key) }
    }
    $environment = @{
        MSYSTEM = 'MINGWARM64'; MSYS2_PATH_TYPE = 'minimal'; CHERE_INVOKING = '1'
        FLAVOR = 'NATIVE_WITH_NATIVE'; CLEAN_BUILD = '1'; RUN_CHECKS = '1'; RESOLVE_DEPENDENCIES = '0'
        VERIFY_SOURCE_SIGNATURES = '1'
        WOARM64_NATIVE_PREFIX = $before.Prefix; WOARM64_TOOLCHAIN_EPOCH = $before.Epoch
        WOARM64_JOBS = "$Jobs"; WOARM64_ENTRY = "$runtimeRoot\.github\scripts\run-native-package.sh"
        WOARM64_PIPELINE_REVISION = $revision
        WOARM64_OUTPUT_ROOT = $output; WOARM64_BUILD_LOG = "$output\build.log"
        BUILDDIR = "$output\build"; SRCDEST = "$output\sources"; SRCPKGDEST = "$output\source-packages"
        LOGDEST = "$output\logs"; PKGDEST = "$output\packages"
        CCACHE_DIR = $report.CacheDirectory
        CCACHE_MAXSIZE = '512M'
    }
    foreach ($entry in $environment.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
    if ($nativeDriver) {
        New-Item -ItemType Directory -Path "$output\native-exits" | Out-Null
        $start.Environment['WOARM64_NATIVE_PYTHON'] = $nativeDriver.Path
        $start.Environment['WOARM64_NATIVE_PYTHON_SHA256'] = $nativeDriver.SHA256
        $start.Environment['WOARM64_NATIVE_TEST_ROOT'] = "$output\build"
        $start.Environment['WOARM64_NATIVE_EXIT_DIR'] = "$output\native-exits"
        $start.Environment['WOARM64_NATIVE_EXEC'] = "$runtimeRoot\.github\scripts\native-target-exec.sh"
        $start.Environment['WOARM64_NATIVE_ARG_CONVERSION'] = 'mingw'
    }
    if ($rustBefore) {
        $start.Environment['WOARM64_RUST_PREFIX'] = $rustBefore.Prefix
        $start.Environment['WOARM64_RUST_EPOCH'] = $rustBefore.Epoch
        $start.Environment['CARGO_HOME'] = "$output\cargo-home"
    }
    $start.ArgumentList.Add('-lc')
    $start.ArgumentList.Add('exec bash "$(cygpath -u "$WOARM64_ENTRY")"')
    if ($nativeDriver) { Set-NativePackageJob $start $nativeDriver $runtimeRoot $output $NativeTimeoutSeconds }
    $process = [Diagnostics.Process]::Start($start)
    $stdout = [IO.File]::Create("$output\launcher.stdout.log")
    $stderr = [IO.File]::Create("$output\launcher.stderr.log")
    try {
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        $null = $copyOut.GetAwaiter().GetResult()
        $null = $copyErr.GetAwaiter().GetResult()
        $report.ExitCode = $process.ExitCode
    } finally {
        $stdout.Dispose()
        $stderr.Dispose()
        $process.Dispose()
    }
    if ($nativeDriver) {
        $job = Read-NativePackageJob $output
        $report.NativeJob = $job
        $report.MakepkgRawExitCode = $job.parent_raw_exit
        if ($job.passed -ne $true) { $report.ExitCode = 255 }
    }
    $after = & (Join-Path "$runtimeRoot\.github\scripts" (Split-Path -Leaf $qualifier)) @qualifiedArgs
    $report.After = $after
    if ($nativeDriver -and (Get-FileHash -LiteralPath $nativeDriver.Path).Hash.ToLowerInvariant() -cne $nativeDriver.SHA256) {
        throw 'Native target interpreter changed during package execution.'
    }
    if ($rustBefore) {
        $rustAfter = & "$runtimeRoot\.github\scripts\test-qualified-rust-bootstrap.ps1" -Prefix $RustPrefix -Qualification $RustQualification -GccEpoch $after.Epoch
        $report.RustAfter = $rustAfter
        if ($rustBefore.Epoch -cne $rustAfter.Epoch) { throw 'Qualified Rust inputs changed during package execution.' }
    }
    Assert-PackageRuntimeSnapshot $runtime
    if ($before.Epoch -ne $after.Epoch -or
        ($before.Descriptors | ConvertTo-Json -Compress) -cne ($after.Descriptors | ConvertTo-Json -Compress)) {
        throw 'Qualified toolchain or qualification descriptors changed during package build.'
    }
    if ($report.ExitCode -ne 0) { throw "Package build failed ($($report.ExitCode)); see $output\build.log" }
    $packages = @(Get-ChildItem -LiteralPath "$output\packages" -File -Filter '*.pkg.tar.*')
    if ($packages.Count -eq 0) { throw 'Build returned success without any package archives.' }
    $report.Packages = @($packages | ForEach-Object {
        @{ Path = $_.FullName; SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $report.Status = 'passed'
} finally {
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\result.json" -Encoding utf8
}
[pscustomobject]$report
