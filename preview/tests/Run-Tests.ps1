[CmdletBinding()]
param(
    [string] $ResultsDirectory
)

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

if (-not [string]::IsNullOrWhiteSpace($ResultsDirectory)) {
    $ResultsDirectory = [IO.Path]::GetFullPath($ResultsDirectory)
    if (-not (Test-Path -LiteralPath $ResultsDirectory -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $ResultsDirectory
    }
}

function Invoke-TargetedSuite {
    param(
        [Parameter(Mandatory = $true)][string] $Script,
        [Parameter(Mandatory = $true)][string] $LogName
    )

    $output = @(& pwsh -NoLogo -NoProfile -File $Script 2>&1)
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) {
        Write-Host ([string]$line)
    }
    if (-not [string]::IsNullOrWhiteSpace($ResultsDirectory)) {
        $logPath = Join-Path $ResultsDirectory $LogName
        if (Test-Path -LiteralPath $logPath) {
            throw "Targeted test log already exists: $logPath"
        }
        [IO.File]::WriteAllText(
            $logPath,
            (@($output | ForEach-Object { [string]$_ }) -join "`n") + "`n",
            [Text.UTF8Encoding]::new($false)
        )
    }
    if ($exitCode -ne 0) {
        exit $exitCode
    }
}

Invoke-TargetedSuite -Script (Join-Path $PSScriptRoot 'Preview.Tests.ps1') `
    -LogName 'assembler-tests.log'
Invoke-TargetedSuite -Script (Join-Path $PSScriptRoot 'EtwCollector.Tests.ps1') `
    -LogName 'etw-tests.log'
