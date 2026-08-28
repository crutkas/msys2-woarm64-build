[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $PSScriptRoot 'git-object-integrity.ps1')

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
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

if ($env:GITHUB_EVENT_NAME -cne 'pull_request_target' -or
    $env:GITHUB_REPOSITORY -cne 'crutkas/msys2-woarm64-build' -or
    $env:GITHUB_REF -cne 'refs/heads/main' -or
    $env:GITHUB_WORKFLOW_REF -cne
        'crutkas/msys2-woarm64-build/.github/workflows/arm64-quarantine-policy.yml@refs/heads/main') {
    throw 'Verifier is not executing from the protected main workflow context.'
}

$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
if ($event.pull_request.base.repo.full_name -cne 'crutkas/msys2-woarm64-build' -or
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

$trustedBindings = @(Get-Arm64ProtectedGitSourceBindings `
        -RepositoryRoot $repositoryRoot `
        -Revision $checkedOutHead)
$policyBinding = @($trustedBindings | Where-Object {
        $_.path -ceq '.github/policies/arm64-quarantine-policy.json'
    })
if ($policyBinding.Count -ne 1) {
    throw 'Protected policy Git object is absent or ambiguous.'
}
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
if ($env:GITHUB_EVENT_NAME -cne $policy.protected_verifier.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.protected_verifier.workflow_ref) {
    throw 'Protected policy context does not match the validated event identity.'
}

$requiredSources = @(
    '.github/workflows/arm64-quarantine-policy.yml',
    '.github/scripts/arm64-admission.ps1',
    '.github/scripts/audit-arm64-workflows.ps1',
    '.github/scripts/collect-arm64-evidence.ps1',
    '.github/scripts/collect-pr-workflow-data.ps1',
    '.github/scripts/git-object-integrity.ps1',
    '.github/scripts/github-rest.ps1',
    '.github/scripts/parse-yaml.rb',
    '.github/scripts/verify-protected-context.ps1'
) | Sort-Object
$declaredSources = @($policy.protected_verifier.sources.PSObject.Properties.Name | Sort-Object)
if (($requiredSources -join "`0") -cne ($declaredSources -join "`0")) {
    throw 'Protected verifier source set is missing, extra, or renamed.'
}
foreach ($protectedPath in $requiredSources) {
    $expected = $policy.protected_verifier.sources.PSObject.Properties[$protectedPath].Value
    Assert-Arm64SourceBinding -Binding $expected -Label $protectedPath
    $actual = @($trustedBindings | Where-Object { $_.path -ceq $protectedPath })
    if ($actual.Count -ne 1 -or
        -not (Test-Arm64SourceBindingEqual -Expected $expected -Actual $actual[0])) {
        throw "Protected verifier source binding mismatch: $protectedPath"
    }
}

Write-Output 'Protected-base verifier context and raw Git source bindings are exact.'
