[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Baseline,
    [Parameter(Mandatory)][string] $CacheEpoch,
    [Parameter(Mandatory)][string] $Prefix
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$baselineRoot = [IO.Path]::GetFullPath($Baseline).TrimEnd('\') + '\'
$prefixRoot = [IO.Path]::GetFullPath($Prefix).TrimEnd('\') + '\'
if (Test-Path -LiteralPath $Prefix) { throw 'The output prefix must not already exist.' }
if ($prefixRoot.StartsWith($baselineRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Do not create an epoch inside its baseline.'
}
$archive = Join-Path $CacheEpoch 'aarch64-w64-mingw32\libgcc.a'
$newHash = (Get-FileHash -LiteralPath $archive).Hash.ToLowerInvariant()
$cc = Join-Path $Baseline 'bin\gcc.exe'
$selected = (& $cc '-print-libgcc-file-name' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the baseline libgcc archive.' }
$selected = [IO.Path]::GetFullPath($selected)
if (-not $selected.StartsWith($baselineRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Baseline compiler selected a library outside its prefix.'
}
$relativeLibrary = [IO.Path]::GetRelativePath($Baseline, $selected)
$files = @(Get-ChildItem -LiteralPath $Baseline -Recurse -File | ForEach-Object {
    [pscustomobject]@{
        Path = [IO.Path]::GetRelativePath($Baseline, $_.FullName)
        SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
})
if (@($files | Where-Object { [IO.Path]::GetFileName($_.Path) -eq 'libgcc.a' }).Count -ne 1) {
    throw 'Unexpected multiple libgcc archives; inspect the prefix rather than mixing epochs.'
}
if ((Get-FileHash -LiteralPath $selected).Hash.ToLowerInvariant() -eq $newHash) {
    throw 'The candidate archive is identical to the baseline.'
}
Copy-Item -LiteralPath $Baseline -Destination $Prefix -Recurse
Copy-Item -LiteralPath $archive -Destination (Join-Path $Prefix $relativeLibrary)
foreach ($file in $files) {
    $before = (Get-FileHash -LiteralPath (Join-Path $Baseline $file.Path)).Hash.ToLowerInvariant()
    $after = (Get-FileHash -LiteralPath (Join-Path $Prefix $file.Path)).Hash.ToLowerInvariant()
    $expected = if ($file.Path -eq $relativeLibrary) { $newHash } else { $file.SHA256 }
    if ($before -ne $file.SHA256 -or $after -ne $expected) {
        throw "Unexpected epoch or baseline change: $($file.Path)"
    }
}
$metadata = [IO.Directory]::CreateDirectory((Join-Path $Prefix 'share\toolchain-epochs\windows-cache')).FullName
foreach ($name in @('gcc-source.patch', 'gcc-patch.sha256', 'cache-source.sha256',
                    'build-log.txt', 'recipe.txt')) {
    Copy-Item -LiteralPath (Join-Path $CacheEpoch $name) -Destination $metadata
}
$manifest = [ordered]@{
    Baseline = $baselineRoot; Prefix = $prefixRoot; CacheEpoch = $CacheEpoch
    GCC = '5688a17320e775944bbe795010ebe7e89fc7a628'
    ChangedFile = $relativeLibrary; LibrarySHA256 = $newHash; BaselineFiles = $files
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content "$metadata\manifest.json" -Encoding utf8
Write-Output "Created $Prefix; only $relativeLibrary differs from the baseline, plus epoch metadata."
