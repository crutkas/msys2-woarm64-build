[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'git-object-integrity.ps1')
. (Join-Path $PSScriptRoot 'github-rest.ps1')

function Assert-CandidateApiObject {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string[]]$RequiredProperties,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -isnot [pscustomobject]) {
        throw "$Context must be a JSON object."
    }
    foreach ($property in $RequiredProperties) {
        if ($null -eq $Value.PSObject.Properties[$property] -or
            $null -eq $Value.$property) {
            throw "$Context is missing required property '$property'."
        }
    }
}

function Invoke-CandidateApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)]
        [ValidateSet('Commit', 'Tree', 'Blob')]
        [string]$Endpoint,
        [Parameter(Mandatory)][string]$ObjectId,
        [long]$MaxResponseBytes = 2MB
    )

    if (-not (Get-Variable -Name CandidateGitHubToken -Scope Script -ErrorAction SilentlyContinue)) {
        throw 'The candidate GitHub token has not been initialized.'
    }
    $request = New-GitHubRestRequest `
        -Repository $Repository `
        -Endpoint $Endpoint `
        -ObjectId $ObjectId `
        -MaxResponseBytes $MaxResponseBytes
    return Invoke-GitHubRestGet -Request $request -Token $script:CandidateGitHubToken
}

function Test-CandidateSelectedPath {
    param([Parameter(Mandatory)][string]$Path)

    return $Path -match '^(?:\.github/(?:workflows|actions|scripts|policies)/|tests/arm64-admission/)' -or
        $Path -match '(?i)(?:^|/)(?:action|Dockerfile)\.ya?ml$' -or
        $Path -match '(?i)\.(?:ps1|psm1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb)$'
}

if ($MyInvocation.InvocationName -eq '.') {
    return
}

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
$requiredEnvironment = @(
    'GITHUB_API_URL',
    'GITHUB_EVENT_NAME',
    'GITHUB_EVENT_PATH',
    'GITHUB_REPOSITORY',
    'GITHUB_REF',
    'GITHUB_WORKFLOW_REF',
    'GITHUB_TOKEN',
    'RUNNER_TEMP',
    'GITHUB_ENV'
)
foreach ($name in $requiredEnvironment) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Candidate data collector context is missing $name."
    }
}
if ($env:GITHUB_API_URL -cne 'https://api.github.com' -or
    $policy.trusted_collector.api_url -cne 'https://api.github.com' -or
    $env:GITHUB_EVENT_NAME -cne $policy.protected_verifier.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.protected_verifier.workflow_ref) {
    throw 'Candidate data collector is not executing from protected main.'
}

$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
Assert-CandidateApiObject $event @('pull_request') 'pull request event'
Assert-CandidateApiObject $event.pull_request @('base', 'head') 'pull request identity'
Assert-CandidateApiObject $event.pull_request.base @('sha', 'repo') 'pull request base'
Assert-CandidateApiObject $event.pull_request.base.repo @('full_name') 'pull request base repository'
Assert-CandidateApiObject $event.pull_request.head @('sha', 'repo') 'pull request head'
Assert-CandidateApiObject $event.pull_request.head.repo @('full_name') 'pull request head repository'
$baseSha = Assert-GitHubObjectId $event.pull_request.base.sha 'pull request base SHA'
$headSha = Assert-GitHubObjectId $event.pull_request.head.sha 'pull request head SHA'
$headRepository = Assert-GitHubRepository $event.pull_request.head.repo.full_name
if ($event.pull_request.base.repo.full_name -cne $policy.producer_repository -or
    $baseSha -cne $env:GITHUB_SHA -or $headSha -ceq $baseSha) {
    throw 'Candidate pull request identity is moved, synthetic, or not bound to protected main.'
}

$script:CandidateGitHubToken = $env:GITHUB_TOKEN
$commit = Invoke-CandidateApi `
    -Repository $headRepository `
    -Endpoint Commit `
    -ObjectId $headSha
Assert-CandidateApiObject $commit @('sha', 'url', 'tree') 'candidate commit'
Assert-CandidateApiObject $commit.tree @('sha', 'url') 'candidate commit tree'
$returnedCommit = Assert-GitHubObjectId $commit.sha 'returned candidate commit SHA'
$treeSha = Assert-GitHubObjectId $commit.tree.sha 'candidate tree SHA'
if ($returnedCommit -cne $headSha -or
    $commit.url -cne "https://api.github.com/repos/$headRepository/git/commits/$headSha" -or
    $commit.tree.url -cne "https://api.github.com/repos/$headRepository/git/trees/$treeSha") {
    throw 'Candidate commit/tree binding failed or moved repositories.'
}

$tree = Invoke-CandidateApi `
    -Repository $headRepository `
    -Endpoint Tree `
    -ObjectId $treeSha `
    -MaxResponseBytes 8MB
Assert-CandidateApiObject $tree @('sha', 'url', 'tree', 'truncated') 'candidate tree'
if ($tree.url -cne "https://api.github.com/repos/$headRepository/git/trees/$treeSha") {
    throw 'Candidate tree response moved repositories.'
}
$treeEntries = @(Get-Arm64ValidatedRestTreeEntries `
        -TreeResponse $tree `
        -ExpectedTree $treeSha `
        -MaximumRecords 10000)
foreach ($entry in $treeEntries) {
    $expectedUrl = switch ($entry.object_type) {
        'blob' { "https://api.github.com/repos/$headRepository/git/blobs/$($entry.oid)" }
        'tree' { "https://api.github.com/repos/$headRepository/git/trees/$($entry.oid)" }
        default { throw "Candidate tree contains an unsupported object type: $($entry.path)" }
    }
    if ($entry.api_url -cne $expectedUrl) {
        throw "Candidate tree entry URL moved repositories: $($entry.path)"
    }
}

$selectedEntries = @($treeEntries | Where-Object {
        $_.object_type -ceq 'blob' -and (Test-CandidateSelectedPath -Path $_.path)
    } | Sort-Object path)
if ($selectedEntries.Count -gt 2000) {
    throw 'Candidate policy data exceeds the selected-file limit.'
}

$outputRoot = Join-Path $env:RUNNER_TEMP 'arm64-candidate-data'
if (Test-Path -LiteralPath $outputRoot) {
    Remove-Item -LiteralPath $outputRoot -Recurse -Force
}
[void](New-Item -ItemType Directory -Path $outputRoot)

$totalBytes = 0L
$snapshotEntries = [Collections.Generic.List[object]]::new()
foreach ($entry in $selectedEntries) {
    if ($entry.byte_length -gt 1048576) {
        throw "Candidate policy data file is too large: $($entry.path)"
    }
    $totalBytes += $entry.byte_length
    if ($totalBytes -gt 64MB) {
        throw 'Candidate policy data exceeds the aggregate byte limit.'
    }

    $blob = Invoke-CandidateApi `
        -Repository $headRepository `
        -Endpoint Blob `
        -ObjectId $entry.oid `
        -MaxResponseBytes 2MB
    Assert-CandidateApiObject $blob @('sha', 'url', 'encoding', 'size', 'content') `
        "candidate blob $($entry.path)"
    $blobSha = Assert-GitHubObjectId $blob.sha "candidate blob SHA $($entry.path)"
    if ($blobSha -cne $entry.oid -or
        $blob.url -cne "https://api.github.com/repos/$headRepository/git/blobs/$blobSha" -or
        $blob.encoding -cne 'base64' -or
        ($blob.size -isnot [int] -and $blob.size -isnot [long]) -or
        [long]$blob.size -ne $entry.byte_length -or
        $blob.content -isnot [string]) {
        throw "Candidate blob schema or identity moved: $($entry.path)"
    }
    try {
        $content = [Convert]::FromBase64String(($blob.content -replace '\s', ''))
    }
    catch {
        throw "Candidate blob content is not canonical base64: $($entry.path)"
    }
    if ($content.LongLength -ne $entry.byte_length -or
        (Get-Arm64GitBlobOid -Bytes $content) -cne $entry.oid) {
        throw "Candidate blob raw-byte integrity mismatch: $($entry.path)"
    }

    $relativePath = $entry.path.Replace('/', [IO.Path]::DirectorySeparatorChar)
    $destination = [IO.Path]::GetFullPath((Join-Path $outputRoot $relativePath))
    $outputPrefix = "$([IO.Path]::GetFullPath($outputRoot).TrimEnd(
            [IO.Path]::DirectorySeparatorChar
        ))$([IO.Path]::DirectorySeparatorChar)"
    if (-not $destination.StartsWith($outputPrefix, [StringComparison]::Ordinal)) {
        throw "Candidate path escapes the data directory: $($entry.path)"
    }
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) {
        [void](New-Item -ItemType Directory -Path $parent -Force)
    }
    [IO.File]::WriteAllBytes($destination, $content)
    [void]$snapshotEntries.Add((New-Arm64SourceBinding `
                -Path $entry.path `
                -Mode $entry.mode `
                -ObjectType $entry.object_type `
                -ByteLength $entry.byte_length `
                -Oid $entry.oid))
}

$snapshot = [pscustomobject][ordered]@{
    authority  = 'github-rest-api'
    repository = $headRepository
    commit     = $headSha
    tree       = $treeSha
    complete   = $true
    files      = @($snapshotEntries)
}
$snapshot | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath (Join-Path $outputRoot 'authoritative-snapshot.json') -Encoding utf8NoBOM
Add-Content -LiteralPath $env:GITHUB_ENV -Value "ARM64_CANDIDATE_ROOT=$outputRoot"

Write-Output "Collected $($snapshotEntries.Count) candidate files as bounded non-executable API data."
