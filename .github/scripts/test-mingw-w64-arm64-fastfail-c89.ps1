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
$fixture = Join-Path $repositoryRoot 'tests\arm64-mingw-fastfail-c89.c'
$object = Join-Path $OutputDirectory 'arm64-mingw-fastfail-c89.o'

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
& $Compiler -std=c89 -c -I $IncludeRoot $fixture -o $object
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
