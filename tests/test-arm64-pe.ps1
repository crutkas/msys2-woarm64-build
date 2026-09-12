$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\.github\scripts\assert-arm64-pe.ps1'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    foreach ($case in @(
        @{ Name = 'arm64'; Machine = 0xAA64; Pass = $true },
        @{ Name = 'x64'; Machine = 0x8664; Pass = $false },
        @{ Name = 'x86'; Machine = 0x014C; Pass = $false },
        @{ Name = 'arm64ec'; Machine = 0xA641; Pass = $false }
    )) {
        # Parser controls only: these minimal headers are deliberately not runnable.
        $path = Join-Path $temporary ($case.Name + '.exe')
        $bytes = [byte[]]::new(128)
        $bytes[0] = 0x4D
        $bytes[1] = 0x5A
        $bytes[0x3C] = 0x40
        $bytes[0x40] = 0x50
        $bytes[0x41] = 0x45
        [BitConverter]::GetBytes([UInt16]$case.Machine).CopyTo($bytes, 0x44)
        [IO.File]::WriteAllBytes($path, $bytes)
        $passed = $false
        try {
            $null = & $script -Path $path
            $passed = $true
        } catch {
            if ($case.Pass) { throw }
            if ($_.Exception.Message -notlike 'Expected ARM64 PE machine*') { throw }
        }
        if ($passed -ne $case.Pass) { throw "Unexpected result: $($case.Name)" }
        Write-Output "PASS: $($case.Name)"
    }
    $path = Join-Path $temporary 'truncated.exe'
    [IO.File]::WriteAllBytes($path, [byte[]](0x4D, 0x5A))
    $rejected = $false
    try {
        $null = & $script -Path $path
    } catch {
        if ($_.Exception.Message -notlike 'Not a PE executable*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Truncated PE accepted' }
    Write-Output 'PASS: truncated PE'
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
