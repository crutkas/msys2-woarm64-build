[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $BaselineManifest,
    [Parameter(Mandatory)][string] $Assembler,
    [Parameter(Mandatory)][string] $AssemblerEpoch,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $StageReceipt
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() }
$manifest = Get-Content -Raw -LiteralPath $BaselineManifest | ConvertFrom-Json
if ($manifest.SchemaVersion -ne 1 -or $manifest.Status -cne 'qualified' -or
    $manifest.Target.Triple -cne 'aarch64-pc-cygwin' -or $manifest.Target.Profile -cne 'MSYS') {
    throw 'An already qualified MSYS SDK baseline is required.'
}
$baseline = [IO.Path]::GetFullPath($manifest.Prefix)
$destination = [IO.Path]::GetFullPath($Prefix)
if ((Test-Path -LiteralPath $Prefix) -or (Test-Path -LiteralPath $StageReceipt) -or
    $destination.StartsWith($baseline.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose new SDK and receipt paths outside the frozen baseline.'
}
$asIdentity = Get-ToolchainPeIdentity $Assembler
if (-not $asIdentity.NativeArm64 -or -not $asIdentity.DynamicBase) {
    throw 'Replacement assembler is not a native ARM64 Windows image.'
}
$version = (& $Assembler --version | Out-String)
if ($LASTEXITCODE -or $version -notmatch 'target of .*aarch64-pc-cygwin') {
    throw 'Replacement assembler was not built for the actual Cygwin/MSYS target.'
}
$inventory = @{}
foreach ($file in $manifest.Files) {
    $full = [IO.Path]::GetFullPath((Join-Path $baseline $file.Path))
    if (-not $full.StartsWith($baseline.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $inventory.ContainsKey($file.Path)) {
        throw "Invalid or duplicate baseline inventory path: $($file.Path)"
    }
    if ((Hash $full) -cne $file.SHA256) {
        throw "Frozen baseline differs: $($file.Path)"
    }
    $inventory[$file.Path] = $file.SHA256
}
$actualFiles = @(Get-ChildItem -LiteralPath $baseline -Recurse -File)
if ($actualFiles.Count -ne $inventory.Count) { throw 'Baseline file set differs from its qualified inventory.' }
foreach ($file in $actualFiles) {
    if (-not $inventory.ContainsKey([IO.Path]::GetRelativePath($baseline, $file.FullName))) {
        throw "Unqualified baseline file: $($file.FullName)"
    }
}
$paths = @('bin\as.exe','bin\aarch64-pc-cygwin-as.exe','aarch64-pc-cygwin\bin\as.exe')
foreach ($relative in $paths) {
    if (-not $inventory.ContainsKey($relative) -or
        $inventory[$relative] -cne $manifest.Components.Assembler.SHA256) {
        throw "Unexpected assembler alias identity: $relative"
    }
}
Copy-Item -LiteralPath $baseline -Destination $Prefix -Recurse
foreach ($relative in $paths) {
    Copy-Item -LiteralPath $Assembler -Destination (Join-Path $Prefix $relative)
}
$metadata = [IO.Directory]::CreateDirectory((Join-Path $Prefix 'share\toolchain\assembler-fp')).FullName
foreach ($name in @('source-lock.json','source.sha256','binutils-revision.txt','binutils-patches.sha256',
                    'native-bootstrap-compiler.txt')) {
    Copy-Item -LiteralPath (Join-Path $AssemblerEpoch "identities\$name") -Destination $metadata
}
Copy-Item -LiteralPath "$PSScriptRoot\binutils-arm64-fp-unwind-enum-order.patch" -Destination $metadata
$gccVersion = (& "$Prefix\bin\gcc.exe" -dumpversion | Out-String).Trim()
if ($LASTEXITCODE) { throw 'Cannot query unchanged compiler version.' }
python "$PSScriptRoot\generate-msys-specs.py" --compiler "$Prefix\bin\gcc.exe" `
    --output "$Prefix\lib\gcc\aarch64-pc-cygwin\$gccVersion\specs" `
    --manifest "$Prefix\share\toolchain\msys-profile.json" --profile-mode default | Out-Host
if ($LASTEXITCODE) { throw 'Cannot relocate MSYS profile metadata.' }
foreach ($file in $manifest.Files) {
    $expected = if ($file.Path -in $paths) { $asIdentity.SHA256 } else { $file.SHA256 }
    if ((Hash (Join-Path $baseline $file.Path)) -cne $file.SHA256) {
        throw "Baseline changed while staging: $($file.Path)"
    }
    if ($file.Path -ne 'share\toolchain\msys-profile.json' -and
        (Hash (Join-Path $Prefix $file.Path)) -cne $expected) {
        throw "Unexpected staged change: $($file.Path)"
    }
}
[ordered]@{
    SchemaVersion = 1; Status = 'msys-assembler-delta-awaiting-qualification'
    BaselineManifest = $BaselineManifest; BaselineManifestSHA256 = Hash $BaselineManifest
    Prefix = $destination; Assembler = $asIdentity; ChangedAliases = $paths
    AssemblerEpoch = $AssemblerEpoch
    Unchanged = 'Compiler frontends, libgcc/libstdc++, all existing target libraries and runtime DLL'
    Limitation = 'Existing objects/libraries retain their earlier unwind metadata; this delta fixes newly assembled objects.'
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StageReceipt -Encoding utf8
Write-Output "Native MSYS assembler delta staged, not yet qualified: $Prefix"
