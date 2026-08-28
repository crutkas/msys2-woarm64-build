[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$parseFailures = [Collections.Generic.List[string]]::new()
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..') -Filter '*.ps1' -File -Recurse) {
    $tokens = $null
    $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile(
        $file.FullName,
        [ref]$tokens,
        [ref]$errors
    )
    foreach ($error in $errors) {
        $parseFailures.Add("$($file.FullName):$($error.Extent.StartLineNumber): $($error.Message)")
    }
}
if ($parseFailures.Count -gt 0) {
    throw "PowerShell parse failures:`n$($parseFailures -join [Environment]::NewLine)"
}

& pwsh -NoLogo -NoProfile -File (Join-Path $PSScriptRoot 'Preview.Tests.ps1')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& pwsh -NoLogo -NoProfile -File (Join-Path $PSScriptRoot 'EtwCollector.Tests.ps1')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
