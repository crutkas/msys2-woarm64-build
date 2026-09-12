#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\manifest-contract.ps1"
$root = (Resolve-Path -LiteralPath $Prefix).ProviderPath.TrimEnd('\')
$manifestPath = (Resolve-Path -LiteralPath $Manifest).ProviderPath
$data = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json -AsHashtable
Assert-NativeMsysDeclaration $data
if ([IO.Path]::GetFullPath($data.Prefix).TrimEnd('\') -ine $root) {
    Stop-MsysContract 'supplied prefix differs from qualified manifest'
}

function Get-MsysDigest([string] $Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Resolve-MsysMember([string] $Relative) {
    Assert-MsysRelativePath $Relative 'member path'
    $current = $root
    foreach ($segment in $Relative.Split('\')) {
        $current = Join-Path $current $segment
        $item = Get-Item -LiteralPath $current -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Stop-MsysContract "reparse point is not an immutable prefix member: $Relative"
        }
    }
    if (-not (Test-Path -LiteralPath $current -PathType Leaf)) {
        Stop-MsysContract "missing file: $Relative"
    }
    $current
}

function Assert-MsysFileHash([string] $Path, [string] $Expected) {
    if ((Get-MsysDigest $Path) -cne $Expected) { Stop-MsysContract "file hash mismatch: $Path" }
}

$inventory = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $data.Files) {
    $path = Resolve-MsysMember $entry.Path
    Assert-MsysFileHash $path $entry.SHA256
    $inventory.Add($path, $entry.SHA256)
}
foreach ($entry in Get-ChildItem -LiteralPath $root -Recurse -Force) {
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Stop-MsysContract "unqualified reparse point: $($entry.FullName)"
    }
    if (-not $entry.PSIsContainer -and -not $inventory.ContainsKey($entry.FullName)) {
        Stop-MsysContract "extra file outside qualified inventory: $($entry.FullName)"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $root $data.Sysroot) -PathType Container)) {
    Stop-MsysContract 'declared sysroot does not exist'
}

$components = @{}
foreach ($role in $data.Components.Keys) {
    $components[$role] = [pscustomobject]@{
        Path = Join-Path $root $data.Components[$role].Path
        SHA256 = $data.Components[$role].SHA256
    }
}
$profile = & "$PSScriptRoot\test-msys-profile.ps1" -Prefix $root -ProfileManifest (Join-Path $root $data.ProfileManifest.Path)
if ($profile.Compiler.Path -ine $components.GCC.Path -or $profile.Specs.Path -ine $components.Specs.Path) {
    Stop-MsysContract 'default profile does not bind the selected GCC and specs components'
}

function Read-MsysChecksumManifest([string] $Path) {
    $checksums = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -cnotmatch '^([0-9a-f]{64}) [ *](.+)$' -or $checksums.ContainsKey($Matches[2])) {
            Stop-MsysContract "invalid or duplicate retained checksum entry: $Path"
        }
        $checksums.Add($Matches[2], $Matches[1])
    }
    if ($checksums.Count -eq 0) { Stop-MsysContract "empty retained checksum manifest: $Path" }
    # Do not let PowerShell enumerate a dictionary into a success-shaped array.
    return ,$checksums
}
$sourceInputs = Read-MsysChecksumManifest (Join-Path $root $data.RuntimePairing.SysrootManifest.Path)
foreach ($pair in @(
    @{ Name = 'lib/crt0.o'; Role = 'CRT0' },
    @{ Name = 'lib/libmsys-2.0.a'; Role = 'MsysImport' }
)) {
    if (-not $sourceInputs.ContainsKey($pair.Name) -or $sourceInputs[$pair.Name] -cne $components[$pair.Role].SHA256) {
        Stop-MsysContract "runtime source sysroot does not pair with installed $($pair.Role)"
    }
}
$sourceDll = Read-MsysChecksumManifest (Join-Path $root $data.RuntimePairing.DllManifest.Path)
if ($sourceDll.Count -ne 1 -or -not $sourceDll.ContainsKey($data.RuntimePairing.SourceDll) -or
    $sourceDll[$data.RuntimePairing.SourceDll] -cne $components.RuntimeDll.SHA256) {
    Stop-MsysContract 'runtime DLL is not paired with its retained source-input identity'
}

Assert-MsysFileHash $data.Acceptance.Path $data.Acceptance.SHA256
Assert-MsysFileHash $data.Acceptance.ToolIdentitiesPath $data.Acceptance.ToolIdentitiesSHA256
$proof = Get-Content -Raw -LiteralPath $data.Acceptance.Path | ConvertFrom-Json -AsHashtable
$images = @(Get-Content -Raw -LiteralPath $data.Acceptance.ToolIdentitiesPath | ConvertFrom-Json -AsHashtable)
Assert-MsysFields $proof @('Passed', 'Host', 'Target', 'Profile', 'CompilerProcess', 'RuntimeInputs', 'RuntimeDll', 'Runs', 'Outputs') 'Acceptance result'
if ($proof.Passed -isnot [bool] -or $proof.Passed -ne $true -or
    $proof.Host -cne 'Windows ARM64 UCRT' -or $proof.Target -cne 'aarch64-pc-cygwin' -or $proof.Profile -cne 'MSYS') {
    Stop-MsysContract 'acceptance is not a passing native MSYS C/C++ result'
}
Assert-MsysFields $proof.CompilerProcess @('Image', 'Machine', 'ProcessId') 'CompilerProcess'
if ($proof.CompilerProcess.Machine -cne '0xAA64' -or
    $proof.CompilerProcess.ProcessId -isnot [long] -or $proof.CompilerProcess.ProcessId -le 0 -or
    [IO.Path]::GetFullPath($proof.CompilerProcess.Image) -ine $components.GCC.Path) {
    Stop-MsysContract 'compiler process evidence does not identify the selected native GCC'
}

function Assert-MsysPeRecord($Record, [string] $Label) {
    Assert-MsysFields $Record @('Path', 'SHA256', 'Machine', 'NativeArm64', 'DynamicBase', 'Imports') $Label
    Assert-MsysBinding $Record $Label -Absolute
    if ($Record.Machine -cne '0xAA64' -or $Record.NativeArm64 -isnot [bool] -or -not $Record.NativeArm64 -or
        $Record.DynamicBase -isnot [bool] -or -not $Record.DynamicBase -or $Record.Imports -isnot [array]) {
        Stop-MsysContract "$Label lacks ARM64 PE/ASLR/import evidence"
    }
    Assert-MsysFileHash $Record.Path $Record.SHA256
    $actual = & "$PSScriptRoot\..\assert-arm64-pe.ps1" -Path $Record.Path | ConvertFrom-Json
    if ($actual.sha256 -cne $Record.SHA256) { Stop-MsysContract "$Label changed during PE inspection" }
}
$imageMap = [Collections.Generic.Dictionary[string, object]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($image in $images) {
    Assert-MsysPeRecord $image 'tool identity'
    $path = [IO.Path]::GetFullPath($image.Path)
    if (-not $inventory.ContainsKey($path) -or $inventory[$path] -cne $image.SHA256 -or $imageMap.ContainsKey($path)) {
        Stop-MsysContract "tool identity is duplicate or outside the full inventory: $path"
    }
    $imageMap.Add($path, $image)
}
foreach ($path in $inventory.Keys) {
    if ([IO.Path]::GetExtension($path).ToLowerInvariant() -in @('.exe', '.dll') -and -not $imageMap.ContainsKey($path)) {
        Stop-MsysContract "tool identities omit a prefix PE image: $path"
    }
}
foreach ($role in 'GCC', 'GXX', 'CC1', 'CC1Plus', 'Assembler', 'Linker', 'Ar', 'Ranlib', 'Windres', 'RuntimeDll') {
    if (-not $imageMap.ContainsKey($components[$role].Path)) { Stop-MsysContract "tool identities omit $role" }
}
foreach ($role in 'GCC', 'GXX') {
    $dlls = @($imageMap[$components[$role].Path].Imports | ForEach-Object { $_.Dll })
    if (-not ($dlls -match '^api-ms-win-crt-') -or 'msys-2.0.dll' -in $dlls -or 'cygwin1.dll' -in $dlls) {
        Stop-MsysContract "$role must be UCRT-hosted, independently of its MSYS target"
    }
}
$runtimeRoles = @{
    'crt0.o' = 'CRT0'; 'crtbegin.o' = 'CRTBegin'; 'crtend.o' = 'CRTEnd'; 'libgcc.a' = 'Libgcc'
    'libstdc++.a' = 'Libstdcxx'; 'libmsys-2.0.a' = 'MsysImport'; 'specs' = 'Specs'
}
if ($proof.RuntimeInputs -isnot [array]) { Stop-MsysContract 'RuntimeInputs must be an array' }
foreach ($name in $runtimeRoles.Keys) {
    $entries = @($proof.RuntimeInputs | Where-Object { $_.Name -ceq $name })
    if ($entries.Count -ne 1) { Stop-MsysContract "acceptance must resolve exactly one $name" }
    $entry = $entries[0]
    if ([IO.Path]::GetFullPath($entry.Path) -ine $components[$runtimeRoles[$name]].Path -or
        $entry.SHA256 -cne $components[$runtimeRoles[$name]].SHA256) {
        Stop-MsysContract "acceptance used a different $name"
    }
}
Assert-MsysPeRecord $proof.RuntimeDll 'acceptance runtime DLL'
if ($proof.RuntimeDll.SHA256 -cne $components.RuntimeDll.SHA256) {
    Stop-MsysContract 'acceptance executed a different runtime DLL'
}
$expectedOutputs = @('msys-native.exe', 'msys-runtime.exe', 'module.dll')
if ($proof.Outputs -isnot [array] -or $proof.Outputs.Count -ne $expectedOutputs.Count) {
    Stop-MsysContract 'acceptance must contain all native C, C++ and DLL outputs'
}
$outputMap = @{}
foreach ($output in $proof.Outputs) {
    Assert-MsysPeRecord $output 'acceptance output'
    $name = [IO.Path]::GetFileName($output.Path)
    $dlls = @($output.Imports | ForEach-Object { $_.Dll })
    if ($name -cnotin $expectedOutputs -or $outputMap.ContainsKey($name) -or 'msys-2.0.dll' -notin $dlls -or
        'cygwin1.dll' -in $dlls -or 'ucrtbase.dll' -in $dlls -or 'msvcrt.dll' -in $dlls -or $dlls -match '^api-ms-win-crt-') {
        Stop-MsysContract 'acceptance output is not unique native MSYS-only target code'
    }
    $outputMap[$name] = $output.Path
}
$expectedRuns = @{
    'msys-c-compile' = $components.GCC.Path; 'msys-c-assemble' = $components.Assembler.Path
    'msys-module' = $components.GXX.Path; 'msys-c-link' = $components.GCC.Path
    'msys-c-execute' = $outputMap['msys-native.exe']; 'msys-cxx-build' = $components.GXX.Path
    'msys-cxx-execute' = $outputMap['msys-runtime.exe']
}
if ($proof.Runs -isnot [array] -or $proof.Runs.Count -eq 0) { Stop-MsysContract 'acceptance runs cannot be empty' }
foreach ($run in $proof.Runs) {
    Assert-MsysFields $run @('Name', 'Executable', 'ExitCode') 'acceptance run'
    if ($run.ExitCode -isnot [long] -or $run.ExitCode -ne 0) { Stop-MsysContract 'acceptance has a failed/invalid run' }
}
foreach ($name in $expectedRuns.Keys) {
    $runs = @($proof.Runs | Where-Object { $_.Name -ceq $name })
    if ($runs.Count -ne 1 -or [IO.Path]::GetFullPath($runs[0].Executable) -ine $expectedRuns[$name]) {
        Stop-MsysContract "acceptance does not bind the actual $name command"
    }
}

[pscustomobject]@{
    Kind = 'qualified-msys-input-binding'
    Prefix = $root
    Target = $data.Target
    Host = $data.Host
    EpochSHA256 = $data.EpochSHA256
    Sysroot = Join-Path $root $data.Sysroot
    Components = $components
    Files = $data.Files
    Manifest = [pscustomobject]@{ Path = $manifestPath; SHA256 = Get-MsysDigest $manifestPath }
    Acceptance = $data.Acceptance
    Scope = 'Read-only binding to published native MSYS qualification; no package execution performed'
}
