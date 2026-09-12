#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Qualification,
    [Parameter(Mandatory)][string] $GccEpoch
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path -LiteralPath $Prefix).ProviderPath.TrimEnd('\')
if ((Get-FileHash -LiteralPath $Qualification).Hash.ToLowerInvariant() -cne
    '12ffeaf77233e962326014e62648f8b3c3220e37fe7aa54cf8e053e88c0cba5b') {
    throw 'Rust bootstrap qualification differs from the accepted pin.'
}
$data = Get-Content -Raw -LiteralPath $Qualification | ConvertFrom-Json
foreach ($binding in $data.Inventory, $data.Interop) {
    if ((Get-FileHash -LiteralPath $binding.Path).Hash.ToLowerInvariant() -cne $binding.SHA256) {
        throw 'Rust bootstrap qualification evidence changed.'
    }
}
$interop = Get-Content -Raw -LiteralPath $data.Interop.Path | ConvertFrom-Json
if ($data.Status -cne 'official-native-rust-gnu-bootstrap-gcc-bidirectional-interop-qualified' -or
    $interop.Status -cne 'native-rust-gcc-explicit-llvm-linker-interop-passed' -or
    $interop.GccEpoch -cne $GccEpoch -or $interop.GccRun.ExitCode -ne 0 -or $interop.RustRun.ExitCode -ne 0) {
    throw 'Rust bootstrap is not qualified against this exact GCC cohort.'
}
$excluded = @('components','install.log','rust-installer-version','uninstall.sh','manifest-cargo','manifest-rustc',
    'manifest-rust-mingw','manifest-rust-std-aarch64-pc-windows-gnullvm') | ForEach-Object { "lib\rustlib\$_" }
$files = @(Get-Content -Raw -LiteralPath $data.Inventory.Path | ConvertFrom-Json | Where-Object { $_.Path -cnotin $excluded })
$members = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($file in $files) {
    if ([IO.Path]::IsPathRooted($file.Path) -or $file.Path -match '(^|\\)\.\.?($|\\)|[/:\x00-\x1f]' -or
        -not $members.Add($file.Path)) { throw 'Invalid Rust package inventory member.' }
    $path = Join-Path $root $file.Path
    $current = $root
    foreach ($segment in $file.Path.Split('\')) {
        $current = Join-Path $current $segment
        if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Rust runtime members must not be reparse points.'
        }
    }
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -cne $file.SHA256) {
        throw "Rust runtime member changed: $($file.Path)"
    }
}
foreach ($file in Get-ChildItem -LiteralPath "$root\lib\rustlib" -Recurse -File -Force) {
    $relative = $file.FullName.Substring($root.Length+1)
    if ($relative -cnotin $excluded -and -not $members.Contains($relative)) { throw "Unqualified Rust sysroot member: $relative" }
}
$epoch = & "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs $files
[pscustomobject]@{
    Kind='qualified-native-rust-bridge';Prefix=$root;Epoch=$epoch;GccEpoch=$GccEpoch
    Qualification=@{Path=(Resolve-Path -LiteralPath $Qualification).ProviderPath;SHA256=(Get-FileHash -LiteralPath $Qualification).Hash.ToLowerInvariant()}
    Inventory=$data.Inventory;Interop=$data.Interop;Files=$files
    Target='aarch64-pc-windows-gnullvm';Version='1.98.1'
    Scope='Explicit native LLVM ARM64PE/dynamic-unwind bridge; does not replace or qualify default GNU BFD'
}
