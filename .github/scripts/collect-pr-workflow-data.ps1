[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
foreach ($name in @(
        'GITHUB_API_URL',
        'GITHUB_EVENT_NAME',
        'GITHUB_EVENT_PATH',
        'GITHUB_REPOSITORY',
        'GITHUB_REF',
        'GITHUB_WORKFLOW_REF',
        'GITHUB_TOKEN',
        'RUNNER_TEMP',
        'GITHUB_ENV')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Candidate data collector context is missing $name."
    }
}
if ($env:GITHUB_API_URL -cne $policy.trusted_collector.api_url -or
    $env:GITHUB_EVENT_NAME -cne $policy.protected_verifier.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.protected_verifier.workflow_ref) {
    throw 'Candidate data collector is not executing from protected main.'
}

$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
$headRepository = [string]$event.pull_request.head.repo.full_name
$headSha = [string]$event.pull_request.head.sha
if ($headRepository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or
    $headSha -notmatch '^[0-9a-f]{40}$') {
    throw 'Candidate repository or commit identity is invalid.'
}

$headers = @{
    Accept                 = 'application/vnd.github+json'
    Authorization          = "Bearer $env:GITHUB_TOKEN"
    'X-GitHub-Api-Version' = '2022-11-28'
}
function Invoke-CandidateApi {
    param([Parameter(Mandatory)][string]$Path)

    if ($Path -notmatch '^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/') {
        throw "Refusing non-repository API path: $Path"
    }
    return Invoke-RestMethod `
        -Method Get `
        -Uri "$($policy.trusted_collector.api_url)$Path" `
        -Headers $headers
}

function Get-GitBlobHash {
    param([Parameter(Mandatory)][byte[]]$Content)

    $prefix = [Text.Encoding]::UTF8.GetBytes("blob $($Content.Length)`0")
    $payload = [byte[]]::new($prefix.Length + $Content.Length)
    [Array]::Copy($prefix, 0, $payload, 0, $prefix.Length)
    [Array]::Copy($Content, 0, $payload, $prefix.Length, $Content.Length)
    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        return -join ($sha1.ComputeHash($payload) | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha1.Dispose()
    }
}

$commit = Invoke-CandidateApi "/repos/$headRepository/git/commits/$headSha"
if ($commit.sha -cne $headSha -or $commit.tree.sha -notmatch '^[0-9a-f]{40}$') {
    throw 'Candidate commit/tree binding failed.'
}
$tree = Invoke-CandidateApi "/repos/$headRepository/git/trees/$($commit.tree.sha)?recursive=1"
if ($tree.sha -cne $commit.tree.sha -or $tree.truncated) {
    throw 'Candidate tree response is incomplete.'
}

$outputRoot = Join-Path $env:RUNNER_TEMP 'arm64-candidate-data'
if (Test-Path -LiteralPath $outputRoot) {
    Remove-Item -LiteralPath $outputRoot -Recurse -Force
}
[void](New-Item -ItemType Directory -Path $outputRoot)

$selectedEntries = @($tree.tree | Where-Object {
        if ($_.type -ne 'blob') {
            return $false
        }
        $path = [string]$_.path
        return $path -match '^(?:\.github/(?:workflows|actions|scripts|policies)/|tests/arm64-admission/)' -or
            $path -match '(?i)(?:^|/)(?:action|Dockerfile)\.ya?ml$' -or
            $path -match '(?i)\.(?:ps1|psm1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb)$'
    })

$snapshotEntries = [Collections.Generic.List[object]]::new()
foreach ($entry in $selectedEntries) {
    if ($entry.mode -eq '120000') {
        throw "Candidate policy data contains a symlink: $($entry.path)"
    }
    if ($entry.size -gt 1048576) {
        throw "Candidate policy data file is too large: $($entry.path)"
    }

    $blob = Invoke-CandidateApi "/repos/$headRepository/git/blobs/$($entry.sha)"
    if ($blob.encoding -cne 'base64') {
        throw "Candidate blob encoding is unsupported: $($entry.path)"
    }
    $content = [Convert]::FromBase64String(($blob.content -replace '\s', ''))
    if ($content.Length -ne [long]$entry.size -or
        (Get-GitBlobHash -Content $content) -cne $entry.sha) {
        throw "Candidate blob integrity mismatch: $($entry.path)"
    }

    $relativePath = ([string]$entry.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
    $destination = [IO.Path]::GetFullPath((Join-Path $outputRoot $relativePath))
    if (-not $destination.StartsWith(
            "$([IO.Path]::GetFullPath($outputRoot))$([IO.Path]::DirectorySeparatorChar)",
            [StringComparison]::Ordinal)) {
        throw "Candidate path escapes the data directory: $($entry.path)"
    }
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) {
        [void](New-Item -ItemType Directory -Path $parent -Force)
    }
    [IO.File]::WriteAllBytes($destination, $content)
    [void]$snapshotEntries.Add([pscustomobject][ordered]@{
            path = [string]$entry.path
            mode = [string]$entry.mode
            blob = [string]$entry.sha
            size = [long]$entry.size
        })
}

$snapshot = [pscustomobject][ordered]@{
    authority = 'github-rest-api'
    repository = $headRepository
    commit = $headSha
    tree = [string]$commit.tree.sha
    complete = $true
    files = @($snapshotEntries)
}
$snapshot | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath (Join-Path $outputRoot 'authoritative-snapshot.json') -Encoding utf8NoBOM
Add-Content -LiteralPath $env:GITHUB_ENV -Value "ARM64_CANDIDATE_ROOT=$outputRoot"

Write-Output "Collected $($snapshotEntries.Count) candidate files as non-executable API data."
