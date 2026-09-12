function Get-ToolchainPeIdentity {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path)

    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    try {
        $hash = (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash.ToLowerInvariant()
        $stream.Position = 0
        $reader = [IO.BinaryReader]::new($stream)
        $bytes = $reader.ReadBytes([int]$stream.Length)
    }
    finally { $stream.Dispose() }
    if ($bytes.Length -lt 64 -or [BitConverter]::ToUInt16($bytes, 0) -ne 0x5a4d) {
        throw "Missing DOS header: $Path"
    }
    $pe = [long][BitConverter]::ToUInt32($bytes, 0x3c)
    if ($pe -lt 64 -or $pe + 144 -gt $bytes.Length -or
        [BitConverter]::ToUInt32($bytes, $pe) -ne 0x4550 -or
        [BitConverter]::ToUInt16($bytes, $pe + 24) -ne 0x020b) {
        throw "Not a complete PE32+ image: $Path"
    }
    $machine = [BitConverter]::ToUInt16($bytes, $pe + 4)
    $dllCharacteristics = [BitConverter]::ToUInt16($bytes, $pe + 24 + 70)
    $sectionCount = [BitConverter]::ToUInt16($bytes, $pe + 6)
    $optionalSize = [BitConverter]::ToUInt16($bytes, $pe + 20)
    $sectionTable = $pe + 24 + $optionalSize
    if ($sectionCount -lt 1 -or $sectionCount -gt 96 -or $optionalSize -lt 128 -or
        $sectionTable + 40 * $sectionCount -gt $bytes.Length) {
        throw "Invalid PE section table: $Path"
    }
    $sections = for ($i = 0; $i -lt $sectionCount; $i++) {
        $offset = $sectionTable + 40 * $i
        [pscustomobject]@{
            Address = [long][BitConverter]::ToUInt32($bytes, $offset + 12)
            Size = [long][BitConverter]::ToUInt32($bytes, $offset + 16)
            Offset = [long][BitConverter]::ToUInt32($bytes, $offset + 20)
        }
    }
    function Resolve-Rva([long] $Rva, [int] $Length) {
        foreach ($section in $sections) {
            $delta = $Rva - $section.Address
            if ($delta -ge 0 -and $delta + $Length -le $section.Size -and
                $section.Offset + $delta + $Length -le $bytes.Length) {
                return [int]($section.Offset + $delta)
            }
        }
        throw "RVA $Rva is outside raw image data: $Path"
    }
    function Read-ImportName([long] $Rva) {
        $chars = [Collections.Generic.List[byte]]::new()
        for ($i = 0; $i -lt 4096; $i++) {
            $character = $bytes[(Resolve-Rva ($Rva + $i) 1)]
            if ($character -eq 0) {
                if ($chars.Count -eq 0) { throw "Empty import name: $Path" }
                return [Text.Encoding]::ASCII.GetString($chars.ToArray())
            }
            $chars.Add($character)
        }
        throw "Unterminated import name: $Path"
    }
    $imports = [Collections.Generic.List[object]]::new()
    $importRva = [long][BitConverter]::ToUInt32($bytes, $pe + 144)
    $importSize = [long][BitConverter]::ToUInt32($bytes, $pe + 148)
    if ($importRva -ne 0) {
        $terminated = $false
        for ($i = 0; $i + 20 -le $importSize; $i += 20) {
            $descriptor = Resolve-Rva ($importRva + $i) 20
            $lookup = [BitConverter]::ToUInt32($bytes, $descriptor)
            $name = [BitConverter]::ToUInt32($bytes, $descriptor + 12)
            $thunk = [BitConverter]::ToUInt32($bytes, $descriptor + 16)
            if ($lookup -eq 0 -and $name -eq 0 -and $thunk -eq 0) {
                $terminated = $true
                break
            }
            if ($lookup -eq 0) { $lookup = $thunk }
            $symbols = [Collections.Generic.List[string]]::new()
            $thunkTerminated = $false
            for ($j = 0; $j -lt 65536; $j++) {
                $entry = [BitConverter]::ToUInt64($bytes, (Resolve-Rva ($lookup + 8L * $j) 8))
                if ($entry -eq 0) { $thunkTerminated = $true; break }
                if ($entry -band [UInt64]::Parse('9223372036854775808')) {
                    $symbols.Add("ordinal:$($entry -band 65535)")
                }
                else {
                    if ($entry -gt [UInt32]::MaxValue) { throw "Invalid import thunk: $Path" }
                    $symbols.Add((Read-ImportName ([long]$entry + 2)))
                }
            }
            if (-not $thunkTerminated) { throw "Unterminated import thunk table: $Path" }
            $imports.Add([pscustomobject]@{
                Dll = Read-ImportName $name
                Symbols = $symbols.ToArray()
            })
        }
        if (-not $terminated) { throw "Unterminated import descriptor table: $Path" }
    }
    [pscustomobject]@{
        Path = [IO.Path]::GetFullPath($Path)
        Length = $bytes.Length
        SHA256 = $hash
        Machine = ('0x{0:X4}' -f $machine)
        NativeArm64 = $machine -eq 0xaa64
        DllCharacteristics = ('0x{0:X4}' -f $dllCharacteristics)
        DynamicBase = ($dllCharacteristics -band 0x40) -ne 0
        Imports = $imports.ToArray()
    }
}
