param(
    [Parameter(Mandatory = $true)]
    [string] $Path
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
$stream = [IO.File]::OpenRead($resolved)
$reader = [IO.BinaryReader]::new($stream)
try {
    if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) {
        throw "Not a PE executable: $resolved"
    }
    $stream.Position = 0x3C
    $offset = $reader.ReadUInt32()
    if ($offset -lt 64 -or $offset -gt ($stream.Length - 24)) {
        throw "Invalid PE header offset: $resolved"
    }
    $stream.Position = $offset
    if ($reader.ReadUInt32() -ne 0x00004550) {
        throw "Missing PE signature: $resolved"
    }
    $machine = $reader.ReadUInt16()
    if ($machine -ne 0xAA64) {
        throw ('Expected ARM64 PE machine 0xAA64, found 0x{0:X4}: {1}' -f $machine, $resolved)
    }
    # Hash the same open image; Get-FileHash is not available in every PS 5.1 host.
    $stream.Position = 0
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
} finally {
    $reader.Dispose()
}

[ordered]@{
    path = $resolved
    machine = '0xAA64'
    sha256 = $digest
    evidence = 'Static PE machine only; not a runtime or dependency-closure assertion'
} | ConvertTo-Json -Compress
