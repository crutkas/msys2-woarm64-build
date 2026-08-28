[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
$requiredEnvironment = @(
    'GITHUB_EVENT_NAME',
    'GITHUB_EVENT_PATH',
    'GITHUB_REPOSITORY',
    'GITHUB_REF',
    'GITHUB_SHA',
    'GITHUB_WORKFLOW_REF'
)
foreach ($name in $requiredEnvironment) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Protected verifier context is missing $name."
    }
}

if ($env:GITHUB_EVENT_NAME -cne $policy.protected_verifier.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.protected_verifier.workflow_ref) {
    throw 'Verifier is not executing from the protected main workflow context.'
}

$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
if ($event.pull_request.base.repo.full_name -cne $policy.producer_repository -or
    $event.pull_request.base.ref -cne 'main' -or
    $event.pull_request.base.sha -cne $env:GITHUB_SHA -or
    $event.pull_request.head.sha -notmatch '^[0-9a-f]{40}$' -or
    $event.pull_request.base.sha -notmatch '^[0-9a-f]{40}$') {
    throw 'Pull request base/head identity is incomplete or not bound to protected main.'
}
if ($event.pull_request.head.sha -ceq $event.pull_request.merge_commit_sha) {
    throw 'Synthetic pull request merge commits are not admissible verifier inputs.'
}

$checkedOutHead = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $checkedOutHead -cne $event.pull_request.base.sha) {
    throw 'Verifier checkout is not the exact pull request base SHA.'
}

$protectedPaths = [ordered]@{
    $policy.protected_verifier.workflow_path = $policy.protected_verifier.workflow_blob
}
foreach ($script in $policy.protected_verifier.scripts.PSObject.Properties) {
    $protectedPaths[$script.Name] = $script.Value
}
foreach ($entry in $protectedPaths.GetEnumerator()) {
    $blob = (& git rev-parse "HEAD:$($entry.Key)").Trim()
    if ($LASTEXITCODE -ne 0 -or $blob -cne $entry.Value) {
        throw "Protected verifier blob mismatch: $($entry.Key)"
    }
}

Write-Output 'Protected-base verifier context and source blobs are exact.'
