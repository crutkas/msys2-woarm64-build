[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $PortableRoot,
    [Parameter(Mandatory = $true)][string] $ValidationEvidencePath,
    [Parameter(Mandatory = $true)][string] $OutputArchive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Preview.Common.psm1') -Force

foreach ($path in @($PortableRoot, $ValidationEvidencePath, $OutputArchive)) {
    Assert-PrivatePath -Path $path
}
if (Test-Path -LiteralPath $OutputArchive) {
    throw "Diagnostics archive already exists: $OutputArchive"
}
$validationRun = Split-Path -Parent ([IO.Path]::GetFullPath($ValidationEvidencePath))
$outputFull = [IO.Path]::GetFullPath($OutputArchive)
if ($outputFull.StartsWith($validationRun.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputArchive must be outside the validation evidence directory"
}
$evidence = Get-Content -LiteralPath $ValidationEvidencePath -Raw -Encoding utf8 | ConvertFrom-Json
Assert-EvidenceComplete -Evidence $evidence
$schemaPath = Join-Path $PortableRoot 'preview-evidence\tools\assembler\schemas\arm64-validation-evidence.schema.json'
if (-not (Test-Path -LiteralPath $schemaPath -PathType Leaf)) {
    throw "Validation evidence schema is absent from the preview"
}
$evidenceJson = Get-Content -LiteralPath $ValidationEvidencePath -Raw -Encoding utf8
if (-not ($evidenceJson | Test-Json -SchemaFile $schemaPath)) {
    throw "Validation evidence does not conform to its versioned schema"
}
$runtimeEvidencePath = Join-Path $validationRun 'runtime-evidence.v1.json'
$runtimeReportPath = Join-Path $validationRun 'authoritative-runtime-report.v1.json'
$failureDiagnostics = "$runtimeEvidencePath.diagnostics"
$collectorLogPath = Join-Path $validationRun 'runtime-collector.log'
$runtimeValidatorLogPath = Join-Path $validationRun 'authoritative-runtime-validator.log'
$hasRuntimeEvidence = Test-Path -LiteralPath $runtimeEvidencePath -PathType Leaf
$hasRuntimeReport = Test-Path -LiteralPath $runtimeReportPath -PathType Leaf
$runtimeArtifacts = @()
$runtimeStatus = $null
if ($hasRuntimeEvidence -and $hasRuntimeReport) {
    $runtimeReport = Get-Content -LiteralPath $runtimeReportPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($null -eq $runtimeReport.PSObject.Properties['result'] -or
        $runtimeReport.result -notin @('pass', 'fail')) {
        throw "Authoritative Runtime report has an open or invalid result"
    }
    $runtimeStatus = [string]$runtimeReport.result
    $runtimeArtifacts = @(
        [ordered]@{ kind = 'runtime-evidence'; path = $runtimeEvidencePath },
        [ordered]@{ kind = 'runtime-report'; path = $runtimeReportPath }
    )
} elseif (-not $hasRuntimeEvidence -and -not $hasRuntimeReport -and
    ((Test-Path -LiteralPath $failureDiagnostics -PathType Container) -or
    (Test-Path -LiteralPath $collectorLogPath -PathType Leaf))) {
    $runtimeStatus = 'collector-failed'
} elseif ($hasRuntimeEvidence -and -not $hasRuntimeReport -and
    (Test-Path -LiteralPath $runtimeValidatorLogPath -PathType Leaf)) {
    $runtimeStatus = 'validator-failed'
} else {
    throw "Authoritative Runtime outputs are incomplete and have no preserved collector failure diagnostics"
}
foreach ($runtimeArtifact in $runtimeArtifacts) {
    $runtimeArtifact.bytes = (Get-Item -LiteralPath $runtimeArtifact.path).Length
    $runtimeArtifact.sha256 = Get-Sha256 -Path $runtimeArtifact.path
}
foreach ($artifact in $evidence.artifacts) {
    $artifactPath = Join-Path $PortableRoot ([string]$artifact.path).Replace('/', '\')
    if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
        throw "Evidence-bound artifact is absent: $($artifact.path)"
    }
    if ((Get-Item -LiteralPath $artifactPath).Length -ne [Int64]$artifact.bytes -or
        (Get-Sha256 -Path $artifactPath) -ne [string]$artifact.sha256) {
        throw "Evidence-bound artifact changed after validation: $($artifact.path)"
    }
}
$staging = Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputArchive))) `
    ".preview-diagnostics-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $staging | Out-Null
try {
    Copy-Item -LiteralPath $ValidationEvidencePath -Destination (Join-Path $staging 'arm64-validation-evidence.v1.json')
    Copy-Item -LiteralPath $validationRun -Destination (Join-Path $staging 'arm64-validation-run') -Recurse
    $previewEvidence = Join-Path $PortableRoot 'preview-evidence'
    if (Test-Path -LiteralPath $previewEvidence -PathType Container) {
        $diagnosticEvidence = Join-Path $staging 'preview-evidence'
        New-Item -ItemType Directory -Path $diagnosticEvidence | Out-Null
        foreach ($item in Get-ChildItem -LiteralPath $previewEvidence -Force |
            Where-Object Name -ine 'tools') {
            Copy-Item -LiteralPath $item.FullName -Destination $diagnosticEvidence -Recurse
        }
    }
    [ordered]@{
        schemaVersion = 1
        collectedAtUtc = [DateTime]::UtcNow.ToString('o')
        runtimeStatus = $runtimeStatus
        machine = [ordered]@{
            computerInfo = Get-ComputerInfo |
                Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture, CsManufacturer, CsModel
            runtime = [ordered]@{
                osArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
                processArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
                powershell = $PSVersionTable.PSVersion.ToString()
            }
        }
        environment = [ordered]@{
            portableRootLeaf = Split-Path -Leaf $PortableRoot
            mutationPolicy = 'Collector requests no PATH, registry, or production Git mutation.'
        }
        runtimeArtifacts = @($runtimeArtifacts | ForEach-Object {
            [ordered]@{
                kind = $_.kind
                bytes = $_.bytes
                sha256 = $_.sha256
            }
        })
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $staging 'diagnostics.json') -Encoding utf8
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $OutputArchive -CompressionLevel Optimal
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Force -Recurse
    }
}
[ordered]@{
    archive = [IO.Path]::GetFullPath($OutputArchive)
    bytes = (Get-Item -LiteralPath $OutputArchive).Length
    sha256 = Get-Sha256 -Path $OutputArchive
} | ConvertTo-Json
