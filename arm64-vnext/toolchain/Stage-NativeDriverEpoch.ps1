[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Baseline,
    [Parameter(Mandatory)][string] $Drivers,
    [Parameter(Mandatory)][string] $Prefix,
    [string] $Windres
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$baselineRoot = [IO.Path]::GetFullPath($Baseline).TrimEnd('\') + '\'
$prefixRoot = [IO.Path]::GetFullPath($Prefix).TrimEnd('\') + '\'
if (Test-Path -LiteralPath $Prefix) { throw 'Use a new candidate prefix.' }
if ($prefixRoot.StartsWith($baselineRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The candidate must be outside its baseline.'
}
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() }
$replacements = @{}
foreach ($pair in @(@('gcc.exe','xgcc.exe'), @('g++.exe','xg++.exe'), @('cpp.exe','cpp.exe'))) {
    $replacement = Join-Path $Drivers $pair[1]
    $newHash = Hash $replacement
    $replacements[(Hash (Join-Path $Baseline "bin\$($pair[0])"))] = @{
        Path = $replacement; SHA256 = $newHash
    }
}
if ($Windres) {
    $replacements[(Hash (Join-Path $Baseline 'bin\windres.exe'))] = @{
        Path = $Windres; SHA256 = Hash $Windres
    }
}
$before = @(Get-ChildItem -LiteralPath $Baseline -Recurse -File | ForEach-Object {
    [pscustomobject]@{
        Path = [IO.Path]::GetRelativePath($Baseline, $_.FullName)
        SHA256 = Hash $_.FullName
    }
})
Copy-Item -LiteralPath $Baseline -Destination $Prefix -Recurse
$changes = [Collections.Generic.List[object]]::new()
foreach ($file in $before) {
    if ($replacements.ContainsKey($file.SHA256)) {
        $replacement = $replacements[$file.SHA256]
        Copy-Item -LiteralPath $replacement.Path -Destination (Join-Path $Prefix $file.Path)
        $changes.Add([pscustomobject]@{ Path = $file.Path; Before = $file.SHA256; After = $replacement.SHA256 })
    }
}
foreach ($file in $before) {
    $expected = if ($replacements.ContainsKey($file.SHA256)) {
        $replacements[$file.SHA256].SHA256
    } else { $file.SHA256 }
    if ((Hash (Join-Path $Baseline $file.Path)) -cne $file.SHA256 -or
        (Hash (Join-Path $Prefix $file.Path)) -cne $expected) {
        throw "Unexpected source or candidate change: $($file.Path)"
    }
}
$sourceLock = Join-Path ([IO.Directory]::GetParent([IO.Path]::GetFullPath($Drivers)).FullName) 'source-lock.json'
$metadata = [IO.Directory]::CreateDirectory((Join-Path $Prefix 'share\toolchain-epochs\native-drivers')).FullName
Copy-Item -LiteralPath $sourceLock -Destination $metadata
if (Test-Path -LiteralPath (Join-Path $Prefix 'share\toolchain\msys-profile.json')) {
    Copy-Item -LiteralPath $sourceLock -Destination (Join-Path $Prefix 'share\toolchain\source-lock.json')
    $version = (& "$Prefix\bin\gcc.exe" -dumpversion | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve native MSYS compiler version.' }
    python "$PSScriptRoot\generate-msys-specs.py" --compiler "$Prefix\bin\gcc.exe" `
        --output "$Prefix\lib\gcc\aarch64-pc-cygwin\$version\specs" `
        --manifest "$Prefix\share\toolchain\msys-profile.json" --profile-mode default | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bind default MSYS profile to updated driver.' }
}
[pscustomobject]@{
    Status = 'candidate-not-qualified'
    Baseline = $baselineRoot; Prefix = $prefixRoot; DriverSource = $Drivers
    WindresSource = $Windres; BaselineFiles = $before; ChangedExecutables = $changes.ToArray()
    SourceLockSHA256 = Hash $sourceLock
    Note = 'MSYS profile metadata, when present, is regenerated; legacy qualification files are not rebound to this candidate.'
}
