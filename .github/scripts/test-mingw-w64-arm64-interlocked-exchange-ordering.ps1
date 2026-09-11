param(
    [Parameter(Mandatory = $true)]
    [string]$Compiler,

    [Parameter(Mandatory = $true)]
    [string]$IncludeRoot,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$fixture = Join-Path $repositoryRoot 'tests\arm64-interlocked-exchange-ordering.c'
$assembly = Join-Path $OutputDirectory 'interlocked-exchange.s'

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
& $Compiler -O2 -S -I $IncludeRoot $fixture -o $assembly
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$text = Get-Content $assembly -Raw
foreach ($helper in '__aarch64_swp4_acq_rel', '__aarch64_swp8_acq_rel') {
    if ($text -notmatch [regex]::Escape($helper)) {
        throw "Missing release-capable helper: $helper"
    }
}

if ($text -match '__aarch64_swp[48]_sync') {
    throw 'Acquire-only swap helper remains in generated assembly.'
}
