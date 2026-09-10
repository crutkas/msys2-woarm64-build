#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $BuildRoot = '\\wsl.localhost\Ubuntu\root\ap11-native-runtime-package-01',
    [string] $RuntimeHandoff = 'C:\Users\crutkasLocal\.copilot\session-state\0af73d1b-9b87-4723-8e25-1e32f44a090c\files\execvp-runtime-01\runtime-execvp-handoff.json',
    [string] $UtilityAdmission = 'C:\ag-utils-e138-01\native-utilities-06\admission.json',
    [string] $UtilityManifest = 'C:\ag-utils-e138-01\native-utilities-06\native-bash-test-utilities.manifest.json',
    [string] $UtilityStage = 'C:\ag-utils-e138-01\native-utilities-06\stage',
    [string] $BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string] $MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$handoffPin = 'f32ef8e115a78a24c8eec432fe2843df8e7896a9c5e5ebf8bd4bf411e7d29a98'
$runtimePin = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$importPin = 'fac7ee56bb99f1c8aa06fd04c164f3b95e71a2fe3168e0b55db5fa02275bf32c'
$crtPin = '3f1d5aed644750ca496008c6c2bc5206da144da3e633065e0a41d0ef07dfeb0e'
$utilityAdmissionPin = 'bbc0046280991ae12f14298c8886faf78706e97be3aaf98e4369702912c47445'
$utilityManifestPin = '300bda77f05606c6f49390297695d0507d769b2dc527843c746b0f6e1b72c9aa'
$localePin = '27a57074b3286bb0b16e5447750ac3263329cf4b4209402ff460ac8bf987bfca'
$expectedUnsupported = @('profiler.exe', 'ssp.exe')

function Get-Sha256([string] $Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Pin([string] $Path, [string] $Expected, [string] $Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
        throw "$Label changed: expected $Expected, got $actual"
    }
}

function Get-PeMachine([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        try {
            if ($reader.ReadUInt16() -ne 0x5a4d) {
                throw "Not a PE image: $Path"
            }
            $stream.Position = 0x3c
            $peOffset = $reader.ReadUInt32()
            $stream.Position = $peOffset
            if ($reader.ReadUInt32() -ne 0x00004550) {
                throw "Invalid PE signature: $Path"
            }
            $reader.ReadUInt16()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Invoke-Readback([string] $Executable, [string[]] $Arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment['PATH'] = [IO.Path]::GetDirectoryName($Executable)
    $start.Environment['MSYSTEM'] = 'MSYS'
    foreach ($argument in $Arguments) {
        $start.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::Start($start)
    try {
        if (-not $process.WaitForExit(30000)) {
            $process.Kill($true)
            throw "Runtime readback timed out: $([IO.Path]::GetFileName($Executable))"
        }
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        if ($process.ExitCode -ne 0) {
            throw "Runtime readback failed ($($process.ExitCode)): $Executable $stderr"
        }
        [ordered]@{
            executable = [IO.Path]::GetFileName($Executable)
            arguments = $Arguments
            exit = $process.ExitCode
            stdout_sha256 = [Convert]::ToHexString(
                [Security.Cryptography.SHA256]::HashData(
                    [Text.Encoding]::UTF8.GetBytes($stdout)
                )
            ).ToLowerInvariant()
            stderr = $stderr
        }
    } finally {
        $process.Dispose()
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
Assert-Pin $RuntimeHandoff $handoffPin 'Qualified runtime handoff'
Assert-Pin $UtilityAdmission $utilityAdmissionPin 'Qualified utility admission'
Assert-Pin $UtilityManifest $utilityManifestPin 'Qualified utility manifest'
$handoff = Get-Content -Raw -LiteralPath $RuntimeHandoff | ConvertFrom-Json -AsHashtable
$runtimeSource = $handoff.get_Item('binaries').get_Item('runtime').get_Item('path')
$importSource = $handoff.get_Item('binaries').get_Item('import_library').get_Item('path')
$crtSource = $handoff.get_Item('binaries').get_Item('crt0').get_Item('path')
Assert-Pin $runtimeSource $runtimePin 'Qualified runtime DLL'
Assert-Pin $importSource $importPin 'Qualified runtime import library'
Assert-Pin $crtSource $crtPin 'Qualified runtime CRT'
$utilityAdmissionData = Get-Content -Raw -LiteralPath $UtilityAdmission |
    ConvertFrom-Json -AsHashtable
if ($utilityAdmissionData.get_Item('runtime_sha256') -cne $runtimePin -or
    $utilityAdmissionData.get_Item('manifest_sha256') -cne $utilityManifestPin) {
    throw 'The qualified utility admission is not bound to the d70 runtime and manifest.'
}
$utilityManifestData = Get-Content -Raw -LiteralPath $UtilityManifest |
    ConvertFrom-Json -AsHashtable
$localeSource = Join-Path $UtilityStage 'usr\bin\locale.exe'
if ($utilityManifestData.get_Item('files').get_Item('usr/bin/locale.exe').get_Item('sha256') -cne $localePin) {
    throw 'The qualified locale manifest identity changed.'
}
Assert-Pin $localeSource $localePin 'Qualified current runtime locale utility'
if (-not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\bash.exe" -PathType Leaf) -or
    -not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\makepkg" -PathType Leaf)) {
    throw "Packaging bootstrap is incomplete: $BootstrapRoot"
}

$buildUtilities = Join-Path $BuildRoot 'winsup\utils'
$builtNames = @(
    Get-ChildItem -LiteralPath $buildUtilities -File -Filter '*.exe' |
        ForEach-Object Name | Sort-Object
)
if ($builtNames.Count -lt 20) {
    throw "The private runtime build produced only $($builtNames.Count) utilities."
}
foreach ($unsupported in $expectedUnsupported) {
    if ($builtNames -ccontains $unsupported) {
        throw "Unexpectedly built unsupported ARM64 utility: $unsupported"
    }
}

New-Item -ItemType Directory -Path $output, "$output\recipe", "$output\recipe\payload", `
    "$output\recipe\payload\runtime\usr\bin", "$output\recipe\payload\runtime\usr\libexec", `
    "$output\recipe\payload\runtime\usr\share", "$output\recipe\payload\devel\usr\include", `
    "$output\recipe\payload\devel\usr\lib", "$output\packages", "$output\receipts" | Out-Null

Copy-Item -LiteralPath $runtimeSource -Destination "$output\recipe\payload\runtime\usr\bin\msys-2.0.dll"
foreach ($name in $builtNames) {
    Copy-Item -LiteralPath (Join-Path $buildUtilities $name) `
        -Destination "$output\recipe\payload\runtime\usr\bin\$name"
    if ((Get-PeMachine "$output\recipe\payload\runtime\usr\bin\$name") -ne 0xaa64) {
        throw "Runtime utility is not ARM64: $name"
    }
}
Copy-Item -LiteralPath $localeSource -Destination "$output\recipe\payload\runtime\usr\bin\locale.exe" -Force
$cygserver = Join-Path $BuildRoot 'winsup\cygserver\cygserver.exe'
if (Test-Path -LiteralPath $cygserver -PathType Leaf) {
    Copy-Item -LiteralPath $cygserver -Destination "$output\recipe\payload\runtime\usr\bin\cygserver.exe"
}

$sdkRoot = Join-Path $BuildRoot 'sdk\aarch64-pc-cygwin'
$installedTarget = Join-Path $BuildRoot 'dest\usr\aarch64-pc-cygwin'
$installedHeaders = @(
    Get-ChildItem -LiteralPath "$installedTarget\include" -File -Recurse |
        Sort-Object FullName
)
foreach ($installedHeader in $installedHeaders) {
    $relative = [IO.Path]::GetRelativePath("$installedTarget\include", $installedHeader.FullName)
    $qualifiedHeader = Join-Path "$sdkRoot\include" $relative
    if (-not (Test-Path -LiteralPath $qualifiedHeader -PathType Leaf)) {
        throw "The qualified SDK is missing an installed runtime header: $relative"
    }
    $destination = Join-Path "$output\recipe\payload\devel\usr\include" $relative
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
    Copy-Item -LiteralPath $qualifiedHeader -Destination $destination
}
Remove-Item -LiteralPath "$output\recipe\payload\devel\usr\include\iconv.h", `
    "$output\recipe\payload\devel\usr\include\unctrl.h" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$output\recipe\payload\devel\usr\include\rpc" -Recurse -Force -ErrorAction SilentlyContinue
$installedLibraries = @(
    Get-ChildItem -LiteralPath "$installedTarget\lib" -File |
        Sort-Object Name
)
foreach ($installedLibrary in $installedLibraries) {
    if ($installedLibrary.Name -ceq 'libg.a') {
        Copy-Item -LiteralPath $importSource `
            -Destination "$output\recipe\payload\devel\usr\lib\libg.a"
        continue
    }
    $qualifiedLibrary = Join-Path "$sdkRoot\lib" $installedLibrary.Name
    $source = if (Test-Path -LiteralPath $qualifiedLibrary -PathType Leaf) {
        $qualifiedLibrary
    } else {
        $installedLibrary.FullName
    }
    Copy-Item -LiteralPath $source -Destination "$output\recipe\payload\devel\usr\lib\$($installedLibrary.Name)"
}
Copy-Item -LiteralPath $importSource -Destination "$output\recipe\payload\devel\usr\lib\libmsys-2.0.a"
Copy-Item -LiteralPath $importSource -Destination "$output\recipe\payload\devel\usr\lib\libcygwin.a"
Copy-Item -LiteralPath $crtSource -Destination "$output\recipe\payload\devel\usr\lib\crt0.o"

$installedShare = Join-Path $BuildRoot 'dest\usr\share'
if (Test-Path -LiteralPath $installedShare -PathType Container) {
    Copy-Item -Path "$installedShare\*" -Destination "$output\recipe\payload\runtime\usr\share" -Recurse
}

$runtimeBin = "$output\recipe\payload\runtime\usr\bin"
$readbacks = @(
    Invoke-Readback "$runtimeBin\cygpath.exe" @('-w', '/usr/bin')
    Invoke-Readback "$runtimeBin\kill.exe" @('-l')
    Invoke-Readback "$runtimeBin\mount.exe" @('-m')
)
$readbacks | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath "$output\receipts\runtime-readback.json" -Encoding utf8

$payloadFiles = @(
    Get-ChildItem -LiteralPath "$output\recipe\payload" -File -Recurse |
        Sort-Object FullName
)
$hashLines = foreach ($file in $payloadFiles) {
    $relative = [IO.Path]::GetRelativePath("$output\recipe", $file.FullName).Replace('\', '/')
    "$(Get-Sha256 $file.FullName)  $relative"
}
[IO.File]::WriteAllText(
    "$output\recipe\runtime-files.sha256",
    ($hashLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\runtime-payload.tar" `
    -C "$output\recipe" payload
if ($LASTEXITCODE) {
    throw 'Could not archive the qualified runtime payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\msys2-runtime\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Sha256 "$output\recipe\runtime-payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Sha256 "$output\recipe\runtime-files.sha256"))
[IO.File]::WriteAllText("$output\recipe\PKGBUILD", $recipe, [Text.UTF8Encoding]::new($false))

$start = [Diagnostics.ProcessStartInfo]::new("$BootstrapRoot\usr\bin\bash.exe")
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.WorkingDirectory = "$output\recipe"
$start.Environment['INTAKE_ROOT'] = $output
$start.Environment['INTAKE_CONFIG'] = [IO.Path]::GetFullPath($MakepkgConfig)
$start.ArgumentList.Add('--noprofile')
$start.ArgumentList.Add('--norc')
$start.ArgumentList.Add('-lc')
$start.ArgumentList.Add(@'
set -euo pipefail
export PATH=/usr/bin
root=$(cygpath -u "$INTAKE_ROOT")
config=$(cygpath -u "$INTAKE_CONFIG")
cd "$root/recipe"
export PKGDEST="$root/packages"
export SRCDEST="$root/sources"
export SRCPKGDEST="$root/source-packages"
export LOGDEST="$root/logs"
export BUILDDIR="$root/build"
makepkg --config "$config" --check --cleanbuild --log --force --noconfirm
'@)
$stdout = [IO.File]::Create("$output\makepkg.stdout.log")
$stderr = [IO.File]::Create("$output\makepkg.stderr.log")
try {
    $process = [Diagnostics.Process]::Start($start)
    try {
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        $null = $copyOut.GetAwaiter().GetResult()
        $null = $copyErr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "makepkg failed with exit code $($process.ExitCode)"
        }
    } finally {
        $process.Dispose()
    }
} finally {
    $stdout.Dispose()
    $stderr.Dispose()
}

$packages = @(Get-ChildItem -LiteralPath "$output\packages" -File -Filter '*.pkg.tar.zst' | Sort-Object Name)
if ($packages.Count -ne 2) {
    throw "Expected two runtime package archives, found $($packages.Count)."
}
$exports = foreach ($package in $packages) {
    $name = $package.Name -replace '-3\.6\.10-4\.1-aarch64\.pkg\.tar\.zst$', ''
    if ($name -cnotin @('msys2-runtime', 'msys2-runtime-devel')) {
        throw "Unexpected runtime package archive: $($package.Name)"
    }
    [ordered]@{
        name = $name
        path = "packages/$($package.Name)"
        sha256 = Get-Sha256 $package.FullName
    }
}

Copy-Item -Path "$BuildRoot\logs\*" -Destination "$output\receipts" -ErrorAction SilentlyContinue
[ordered]@{
    schema = 1
    status = 'admitted-current-d70-native-msys2-runtime-exported'
    packages = @($exports)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\export.json" -Encoding utf8

[ordered]@{
    schema = 1
    status = 'current-d70-native-msys2-runtime-packaged'
    source = [ordered]@{
        handoff = [ordered]@{ path = [IO.Path]::GetFullPath($RuntimeHandoff); sha256 = $handoffPin }
        repository = 'crutkas/msys2-runtime'
        commit = 'd890a845e992638a6f09560efacc26d15b3ffe6a'
        source_patch_sha256 = 'ce17ade7aab3040eee927355a0d40431431856c330ce0cd3708b8cea8ec499b3'
        upstream_recipe = 'msys2/MSYS2-packages msys2-runtime 3.6.10-4'
    }
    preserved = [ordered]@{
        runtime_sha256 = $runtimePin
        import_library_sha256 = $importPin
        crt0_sha256 = $crtPin
    }
    private_build = [ordered]@{
        target = 'aarch64-pc-cygwin'
        compiler_host = 'linux'
        jobs = 2
        supported_utilities = $builtNames
        qualified_utility_overrides = [ordered]@{
            'locale.exe' = $localePin
        }
        qualified_utility_smoke = [ordered]@{
            path = $utilityAdmissionData.get_Item('smoke_result')
            sha256 = $utilityAdmissionData.get_Item('smoke_result_sha256')
            processes = $utilityAdmissionData.get_Item('smoke_processes')
        }
        unsupported_source_utilities = $expectedUnsupported
        supplemented_system_import_libraries = [ordered]@{
            'libuserenv.a' = 'a22750ffb8a9fe9a3d71eb18bb9fc27b6fd2cd7456de2e557cc9dfc0bcc5fdce'
            'libpsapi.a' = 'd9d8d8127942e8d2f1fece44359df2235b2cdec88cb0fb7e663897ab23793677'
            'libdbghelp.a' = '9a86867fa90d80fca7a3cba303721d2ef31afe1b14f205cad0cf7897c7f77e54'
        }
        readback = $readbacks
    }
    packages = @($exports)
    limitations = @(
        'The package retains the exact sealed d70 runtime DLL and paired import library/CRT.',
        'profiler.exe and ssp.exe are omitted because their upstream sources explicitly reject ARM64.',
        'The Linux-hosted SDK is a build input only and is not shipped as a native Windows compiler.',
        'No native self-hosting, managed GCM, Bash/Coreutils, or gcc-libs admission is claimed.'
    )
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$output\handoff.json" -Encoding utf8

[pscustomobject]@{
    Export = "$output\export.json"
    ExportSHA256 = Get-Sha256 "$output\export.json"
    Handoff = "$output\handoff.json"
    HandoffSHA256 = Get-Sha256 "$output\handoff.json"
    Packages = $packages.Count
    Utilities = $builtNames.Count
}
