param([Parameter(Mandatory)][object[]] $Inputs)

$ErrorActionPreference = 'Stop'
if ($Inputs.Count -eq 0) { throw 'Cannot derive a cache epoch from an empty inventory.' }
$seen = @{}
$lines = [string[]]@($Inputs | ForEach-Object {
    if ([IO.Path]::IsPathRooted($_.Path) -or $_.Path -match '[\t\r\n]' -or
        $_.SHA256 -notmatch '^[0-9a-fA-F]{64}$' -or $seen.ContainsKey($_.Path)) {
        throw "Invalid or duplicate cache input: $($_.Path)"
    }
    $seen[$_.Path] = $true
    "$($_.Path)`t$($_.SHA256.ToLowerInvariant())"
})
[Array]::Sort($lines, [StringComparer]::Ordinal)
$text = ($lines -join "`n") + "`n"
$sha = [Security.Cryptography.SHA256]::Create()
try {
    [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))).Replace('-', '').ToLowerInvariant()
} finally {
    $sha.Dispose()
}
