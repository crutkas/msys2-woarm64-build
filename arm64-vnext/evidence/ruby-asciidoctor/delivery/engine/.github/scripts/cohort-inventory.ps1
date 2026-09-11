#requires -Version 7.3
Set-StrictMode -Version Latest

function Get-CohortInventory([string] $Root) {
    $resolved = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd('\')
    $items = @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
    if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'A qualified cohort must contain files, not reparse points.'
    }
    $files = @($items | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
        [pscustomobject]@{
            Path = $_.FullName.Substring($resolved.Length + 1)
            SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    if ($files.Count -eq 0) { throw 'Cannot qualify an empty cohort.' }
    $files
}

function Assert-CohortInventory([string] $Root, [object[]] $Expected) {
    if ($Expected.Count -eq 0) { throw 'Expected cohort inventory cannot be empty.' }
    $map = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $Expected) {
        if ([IO.Path]::IsPathRooted($entry.Path) -or $entry.Path -match '(^|\\)\.\.?($|\\)|[/:\x00-\x1f]' -or
            $entry.SHA256 -cnotmatch '^[0-9a-f]{64}$' -or $map.ContainsKey($entry.Path)) {
            throw "Invalid cohort inventory entry: $($entry.Path)"
        }
        $map.Add($entry.Path, $entry.SHA256)
    }
    $current = @(Get-CohortInventory $Root)
    if ($current.Count -ne $map.Count) { throw "Cohort file set changed: $Root" }
    foreach ($entry in $current) {
        if (-not $map.ContainsKey($entry.Path) -or $entry.SHA256 -cne $map[$entry.Path]) {
            throw "Cohort input changed: $($entry.Path)"
        }
    }
}
