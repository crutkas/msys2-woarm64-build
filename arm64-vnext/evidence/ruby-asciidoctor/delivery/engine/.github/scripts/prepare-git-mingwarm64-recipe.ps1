#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\cohort-inventory.ps1"
$source = (Resolve-Path -LiteralPath $SourceDirectory).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) { throw 'Prepared Git recipe output must be new.' }
if ($output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Prepared recipe must be outside its immutable source.'
}
$pkgbuild = Join-Path $source 'PKGBUILD'
$expected = 'e072d843e42e9b8401bd7b3767f3920572b70415104bd42f7180372df9344e2a'
if ((Get-FileHash -LiteralPath $pkgbuild).Hash.ToLowerInvariant() -cne $expected) {
    throw 'Only the pinned Git 2.55.0.windows.5 recipe is supported by this mapping.'
}
$files = @(Get-CohortInventory $source)
$patch = Join-Path $PSScriptRoot '..\..\patches\git\0001-declare-mingwarm64.patch'
Copy-Item -LiteralPath $source -Destination $output -Recurse
& git -C $output apply --check $patch
if ($LASTEXITCODE -ne 0) { throw 'Pinned Git namespace patch check failed.' }
& git -C $output apply $patch
if ($LASTEXITCODE -ne 0) { throw 'Pinned Git namespace patch application failed.' }
Assert-CohortInventory $source $files
$before = [IO.File]::ReadAllText($pkgbuild).Replace("`r`n", "`n")
$after = [IO.File]::ReadAllText((Join-Path $output 'PKGBUILD')).Replace("`r`n", "`n")
$original = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
$mapped = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
if ($before.Replace($original, $mapped) -cne $after) {
    throw 'Recipe preparation changed more than the declared MINGWARM64 environment.'
}
foreach ($entry in $files | Where-Object Path -CNE 'PKGBUILD') {
    if ((Get-FileHash -LiteralPath (Join-Path $output $entry.Path)).Hash.ToLowerInvariant() -cne $entry.SHA256) {
        throw "Recipe companion changed: $($entry.Path)"
    }
}
[ordered]@{
    Status = 'namespace-prepared-not-package-admitted'
    Source = $source
    Output = $output
    BeforeSHA256 = $expected
    AfterSHA256 = (Get-FileHash -LiteralPath (Join-Path $output 'PKGBUILD')).Hash.ToLowerInvariant()
    Patch = @{ Path = [IO.Path]::GetFullPath($patch); SHA256 = (Get-FileHash -LiteralPath $patch).Hash.ToLowerInvariant() }
    Namespace = @{ MSYSTEM = 'MINGWARM64'; MINGW_PREFIX = '/mingwarm64'; MINGW_PACKAGE_PREFIX = 'mingw-w64-aarch64'; CC = 'gcc'; Target = 'aarch64-w64-mingw32' }
    Preserved = 'All original package splits, dependencies, Rust/docs/PDB defaults, source/tag/checksums and function bodies'
    Scope = 'Additional project-native GCC environment only; no clang package rename, fake provider or installed dependency'
}
