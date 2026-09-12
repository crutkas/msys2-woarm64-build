#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $PackageDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][ValidateRange(1, 16)][int] $Jobs,
    [string] $NativePython,
    [ValidateRange(1, 86400)][int] $NativeTimeoutSeconds = 86400
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\..\package-runtime.ps1"
$nativeDriver = if ($NativePython) { & "$PSScriptRoot\..\get-native-target-driver.ps1" -Python $NativePython } else { $null }
$source = (Resolve-Path -LiteralPath $PackageDirectory).ProviderPath.TrimEnd('\')
if (-not (Test-Path -LiteralPath "$source\PKGBUILD" -PathType Leaf)) { throw 'An MSYS package recipe must contain PKGBUILD.' }
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if ($output -ieq $source -or $output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'MSYS package output must be separate from its source recipe.'
}
$contextArgs = @{ Prefix = $Prefix; Manifest = $Manifest; MsysRoot = $MsysRoot; OutputDirectory = $output; Jobs = $Jobs }
$context = & "$PSScriptRoot\new-package-context.ps1" @contextArgs
$report = [ordered]@{
    Kind = 'msys-package-build'
    State = 'failed'
    CheckRequested = $true
    Jobs = $Jobs
    Context = "$output\context.json"
    Before = $context.Qualification
    DriverScope = 'MSYS2 bootstrap may be x64 emulated; qualified compiler host and MSYS target remain distinct'
    NativeTargetDriver = $nativeDriver
    NativeTargetArgumentConversion = 'none'
    NativeExitScope = 'With NativePython: scoped job records native target exits and rejects unrelayed high exits or missing process observations; no compiler proxy'
}
try {
    $runtime = New-PackageRuntimeSnapshot ([IO.Path]::GetFullPath("$PSScriptRoot\..\..\..")) "$output\pipeline"
    $report.PipelineRuntime = $runtime.Root
    $report.PipelineRevision = $runtime.Revision
    $report.PipelineSources = $runtime.Files
    $report.RecipeInputs = @(Get-ChildItem -LiteralPath $source -Recurse -File | ForEach-Object {
        @{ Path = $_.FullName.Substring($source.Length + 1); SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    })
    Copy-Item -LiteralPath $source -Destination "$output\recipe" -Recurse
    foreach ($entry in $report.RecipeInputs) {
        if ((Get-FileHash -LiteralPath (Join-Path "$output\recipe" $entry.Path)).Hash.ToLowerInvariant() -cne $entry.SHA256) {
            throw "MSYS recipe changed during copy: $($entry.Path)"
        }
    }
    $start = [Diagnostics.ProcessStartInfo]::new("$($context.BootstrapRoot)\usr\bin\bash.exe")
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = "$output\recipe"
    foreach ($name in @($start.Environment.Keys)) {
        if ($name -match '^(CCACHE_|WOARM64_|GCC_|MSYS|MINGW|BASH_FUNC_)' -or $name -in @(
            'CC', 'CXX', 'AR', 'AS', 'LD', 'RANLIB', 'RC', 'WINDRES', 'STRIP', 'OBJCOPY', 'OBJDUMP',
            'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH',
            'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'MAKEPKG_LIBRARY', 'MAKEPKG_CONF',
            'BUILDDIR', 'SRCDEST', 'SRCPKGDEST', 'LOGDEST', 'PKGDEST', 'CARCH',
            'BASH_ENV', 'ENV', 'RUN_CHECK', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR', 'PKG_CONFIG_SYSROOT_DIR',
            'CMAKE_BUILD_PARALLEL_LEVEL', 'CTEST_PARALLEL_LEVEL'
        )) { $null = $start.Environment.Remove($name) }
    }
    foreach ($entry in $context.Environment.GetEnumerator()) { $start.Environment[$entry.Key] = $entry.Value }
    $start.Environment['WOARM64_MSYS_CONFIG'] = $context.Config.Path
    $start.Environment['WOARM64_OUTPUT_ROOT'] = $output
    $start.Environment['WOARM64_JOBS'] = "$Jobs"
    $start.Environment['WOARM64_ENTRY'] = "$($runtime.Root)\.github\scripts\msys\run-package.sh"
    $start.Environment['CCACHE_DIR'] = "$output\ccache"
    $start.Environment['CCACHE_MAXSIZE'] = '512M'
    if ($nativeDriver) {
        New-Item -ItemType Directory -Path "$output\native-exits" | Out-Null
        $start.Environment['WOARM64_NATIVE_PYTHON'] = $nativeDriver.Path
        $start.Environment['WOARM64_NATIVE_PYTHON_SHA256'] = $nativeDriver.SHA256
        $start.Environment['WOARM64_NATIVE_TEST_ROOT'] = "$output\build"
        $start.Environment['WOARM64_NATIVE_EXIT_DIR'] = "$output\native-exits"
        $start.Environment['WOARM64_NATIVE_EXEC'] = "$($runtime.Root)\.github\scripts\native-target-exec.sh"
        $start.Environment['WOARM64_NATIVE_ARG_CONVERSION'] = 'none'
    }
    $start.ArgumentList.Add('-lc')
    $start.ArgumentList.Add('exec bash "$(cygpath -u "$WOARM64_ENTRY")"')
    if ($nativeDriver) { Set-NativePackageJob $start $nativeDriver $runtime.Root $output $NativeTimeoutSeconds }
    $stdout = [IO.File]::Create("$output\launcher.stdout.log")
    $stderr = [IO.File]::Create("$output\launcher.stderr.log")
    try {
        $process = [Diagnostics.Process]::Start($start)
        try {
            $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
            $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
            $process.WaitForExit()
            $null = $copyOut.GetAwaiter().GetResult()
            $null = $copyErr.GetAwaiter().GetResult()
            $report.ExitCode = $process.ExitCode
        } finally {
            $process.Dispose()
        }
        if ($nativeDriver) {
            $job = Read-NativePackageJob $output
            $report.NativeJob = $job
            $report.MakepkgRawExitCode = $job.parent_raw_exit
            if ($job.passed -ne $true) { $report.ExitCode = 255 }
        }
    } finally {
        $stdout.Dispose()
        $stderr.Dispose()
    }
    $after = & "$($runtime.Root)\.github\scripts\msys\read-qualified-toolchain.ps1" -Prefix $Prefix -Manifest $Manifest
    Assert-PackageRuntimeSnapshot $runtime
    $report.After = $after
    if ($nativeDriver -and (Get-FileHash -LiteralPath $nativeDriver.Path).Hash.ToLowerInvariant() -cne $nativeDriver.SHA256) {
        throw 'Native target interpreter changed during package execution.'
    }
    if ($context.Qualification.EpochSHA256 -cne $after.EpochSHA256 -or
        $context.Qualification.Manifest.SHA256 -cne $after.Manifest.SHA256) {
        throw 'MSYS qualification changed during package execution.'
    }
    if ($report.ExitCode -ne 0) { throw "MSYS package failed ($($report.ExitCode)); see $output\build.log" }
    $packages = @(Get-ChildItem -LiteralPath "$output\packages" -File -Filter '*.pkg.tar.*')
    if ($packages.Count -eq 0) { throw 'MSYS package returned success without an archive.' }
    $report.Packages = @($packages | ForEach-Object {
        @{ Path = $_.FullName; SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    })
    $report.State = 'built'
} finally {
    $report | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath "$output\result.json" -Encoding utf8
}
[pscustomobject]$report
