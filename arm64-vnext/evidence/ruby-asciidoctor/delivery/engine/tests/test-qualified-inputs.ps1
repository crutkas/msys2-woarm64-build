param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Identities,
    [Parameter(Mandatory)][string] $Proof,
    [Parameter(Mandatory)][string] $CacheHandoff
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\.github\scripts\test-qualified-toolchain.ps1'
$arguments = @{ Prefix = $Prefix; Identities = $Identities; Proof = $Proof; CacheHandoff = $CacheHandoff }
$positive = & $script @arguments
if ($positive.Inputs.Count -eq 0 -or $positive.Epoch -notmatch '^[0-9a-f]{64}$') {
    throw 'Qualified positive control did not produce a nonempty input inventory.'
}
'PASS: actual qualified prefix accepted'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $images = @(Get-Content -Raw -LiteralPath $Identities | ConvertFrom-Json)
    $images[0].SHA256 = '0' * 64
    $badIdentities = Join-Path $temporary 'bad-identities.json'
    $images | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $badIdentities -Encoding utf8
    $handoff = Get-Content -Raw -LiteralPath $CacheHandoff | ConvertFrom-Json
    $handoff.Archives.MinGW = '0' * 64
    $badHandoff = Join-Path $temporary 'bad-handoff.json'
    $handoff | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $badHandoff -Encoding utf8
    $badProof = Join-Path $temporary 'unbound-proof.json'
    Copy-Item -LiteralPath $Proof -Destination $badProof
    foreach ($case in @(
        @{ Key = 'Identities'; Path = $badIdentities; Error = 'Qualification and full-prefix inventory disagree:*' },
        @{ Key = 'CacheHandoff'; Path = $badHandoff; Error = 'Full-prefix manifest does not match*' },
        @{ Key = 'Proof'; Path = $badProof; Error = 'Native qualification proof is missing*' }
    )) {
        $invalid = $arguments.Clone()
        $invalid[$case.Key] = $case.Path
        $rejected = $false
        try { $null = & $script @invalid } catch {
            if ($_.Exception.Message -notlike $case.Error) { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw "Invalid $($case.Key) accepted." }
        "PASS: invalid $($case.Key) rejected without executing compiler"
    }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
