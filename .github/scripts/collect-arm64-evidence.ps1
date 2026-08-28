[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
$admissionPath = Join-Path $PSScriptRoot 'arm64-admission.ps1'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
. $admissionPath

function Invoke-Arm64GitHubApi {
    param([Parameter(Mandatory)][string]$Path)

    if ($Path -notmatch '^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/') {
        throw "Refusing non-repository API path: $Path"
    }
    return Invoke-RestMethod `
        -Method Get `
        -Uri "$($policy.trusted_collector.api_url)$Path" `
        -Headers $headers
}

function Get-Arm64ReleaseEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][long]$ReleaseId
    )

    $release = Invoke-Arm64GitHubApi "/repos/$Repository/releases/$ReleaseId"
    return [pscustomobject][ordered]@{
        id          = [long]$release.id
        immutable   = [bool]$release.immutable
        draft       = [bool]$release.draft
        prerelease  = [bool]$release.prerelease
        tag_name    = [string]$release.tag_name
        published_at = ([DateTimeOffset]$release.published_at).ToUniversalTime().ToString(
            "yyyy-MM-dd'T'HH:mm:ss'Z'"
        )
    }
}

function Get-Arm64ReleaseAssets {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][long]$ReleaseId
    )

    $assets = [Collections.Generic.List[object]]::new()
    for ($page = 1; $page -le 100; $page++) {
        $pageItems = @(
            Invoke-Arm64GitHubApi `
                "/repos/$Repository/releases/$ReleaseId/assets?per_page=100&page=$page"
        )
        foreach ($item in $pageItems) {
            [void]$assets.Add($item)
        }
        if ($pageItems.Count -lt 100) {
            return @($assets)
        }
    }
    throw "Release asset pagination exceeded the fail-closed limit: $Repository/$ReleaseId"
}

function Get-Arm64CanonicalAssetManifest {
    param([Parameter(Mandatory)][object[]]$Assets)

    $manifest = @($Assets | Sort-Object id | ForEach-Object {
            [pscustomobject][ordered]@{
                id     = [long]$_.id
                name   = [string]$_.name
                size   = [long]$_.size
                digest = [string]$_.digest
                state  = [string]$_.state
            }
        })
    $json = $manifest | ConvertTo-Json -Compress -Depth 8
    $hash = [Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::UTF8.GetBytes($json)
    )
    return [pscustomobject]@{
        Items  = $manifest
        Sha256 = -join ($hash | ForEach-Object { $_.ToString('x2') })
    }
}

function Get-Arm64AnnotatedTagEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$TagName
    )

    $encodedTag = [Uri]::EscapeDataString($TagName)
    $tagRef = Invoke-Arm64GitHubApi "/repos/$Repository/git/ref/tags/$encodedTag"
    if ($tagRef.object.type -cne 'tag' -or $tagRef.object.sha -notmatch '^[0-9a-f]{40}$') {
        throw "Release tag is not an annotated object: $Repository/$TagName"
    }
    $tagObject = Invoke-Arm64GitHubApi "/repos/$Repository/git/tags/$($tagRef.object.sha)"
    if ($tagObject.object.type -cne 'commit' -or
        $tagObject.object.sha -notmatch '^[0-9a-f]{40}$') {
        throw "Annotated tag does not peel to one commit: $Repository/$TagName"
    }
    return [pscustomobject][ordered]@{
        object_sha    = [string]$tagRef.object.sha
        peeled_commit = [string]$tagObject.object.sha
    }
}

function Get-Arm64ReleaseBundle {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][long]$ReleaseId
    )

    $release = Get-Arm64ReleaseEvidence -Repository $Repository -ReleaseId $ReleaseId
    $assets = Get-Arm64ReleaseAssets -Repository $Repository -ReleaseId $ReleaseId
    $manifest = Get-Arm64CanonicalAssetManifest -Assets $assets
    return [pscustomobject][ordered]@{
        id             = [long]$release.id
        immutable      = [bool]$release.immutable
        draft          = [bool]$release.draft
        prerelease     = [bool]$release.prerelease
        tag_name       = [string]$release.tag_name
        published_at   = [string]$release.published_at
        annotated_tag  = Get-Arm64AnnotatedTagEvidence `
            -Repository $Repository `
            -TagName $release.tag_name
        asset_manifest = [pscustomobject][ordered]@{
            canonicalization = 'id-ascending-compact-json-v1'
            fields           = @('id', 'name', 'size', 'digest', 'state')
            count            = [long]$manifest.Items.Count
            sha256           = [string]$manifest.Sha256
        }
        assets          = @($manifest.Items)
    }
}

if ($MyInvocation.InvocationName -eq '.') {
    return
}

# Fail before token use or API access until an exact candidate is approved on protected main.
if ($policy.live_admission_enabled -isnot [bool] -or -not $policy.live_admission_enabled) {
    throw 'Live ARM64 admission is bootstrap-disabled.'
}
if (@($policy.explicit_admissions).Count -eq 0) {
    throw 'No exact ARM64 candidate identity is allowlisted.'
}

$requiredEnvironment = @(
    'GITHUB_API_URL',
    'GITHUB_EVENT_NAME',
    'GITHUB_EVENT_PATH',
    'GITHUB_REPOSITORY',
    'GITHUB_REF',
    'GITHUB_WORKFLOW_REF',
    'GITHUB_WORKSPACE',
    'GITHUB_TOKEN'
)
foreach ($name in $requiredEnvironment) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Trusted collector context is missing $name."
    }
}
if ($env:GITHUB_API_URL -cne $policy.trusted_collector.api_url -or
    $env:GITHUB_EVENT_NAME -cne $policy.trusted_collector.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.trusted_collector.workflow_ref) {
    throw 'Trusted collector is not running from the protected main workflow context.'
}

$workspace = Get-Arm64CanonicalWorkspaceEvidence -Path $env:GITHUB_WORKSPACE -Policy $policy
$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
if ($null -eq $event.workflow_run -or
    -not (Test-Arm64PositiveInteger $event.workflow_run.id) -or
    $event.workflow_run.head_repository.full_name -cne $policy.producer_repository) {
    throw 'workflow_run event identity is incomplete or belongs to another repository.'
}

$admissions = @($policy.explicit_admissions | Where-Object {
        $_.identity.run.id -eq [long]$event.workflow_run.id -and
        $_.identity.run.attempt -eq [long]$event.workflow_run.run_attempt -and
        $_.identity.run.head_sha -ceq $event.workflow_run.head_sha
    })
if ($admissions.Count -ne 1) {
    throw 'The workflow_run event does not identify exactly one allowlisted candidate.'
}
$expected = $admissions[0]

$headers = @{
    Accept                 = 'application/vnd.github+json'
    Authorization          = "Bearer $env:GITHUB_TOKEN"
    'X-GitHub-Api-Version' = '2022-11-28'
}

$runId = [long]$event.workflow_run.id
$run = Invoke-Arm64GitHubApi "/repos/$($policy.producer_repository)/actions/runs/$runId"
if ($run.id -ne $expected.identity.run.id -or
    $run.run_attempt -ne $expected.identity.run.attempt -or
    $run.head_sha -cne $expected.identity.run.head_sha -or
    $run.head_branch -cne 'main' -or
    $run.path -cne $expected.identity.workflow.path -or
    $run.event -cne $expected.identity.run.event_name -or
    $run.conclusion -cne 'success') {
    throw 'Authoritative run metadata does not match the allowlisted identity.'
}

$jobsResponse = Invoke-Arm64GitHubApi `
    "/repos/$($policy.producer_repository)/actions/runs/$runId/attempts/$($expected.identity.run.attempt)/jobs?per_page=100"
if ($jobsResponse.total_count -ne 1) {
    throw 'The producer run attempt must contain exactly one job.'
}
$jobs = @($jobsResponse.jobs | Where-Object {
        $_.name -ceq $expected.identity.run.job -and $_.conclusion -ceq 'success'
    })
if ($jobs.Count -ne 1) {
    throw 'The exact successful producer job is absent or ambiguous.'
}

$artifactsResponse = Invoke-Arm64GitHubApi `
    "/repos/$($policy.producer_repository)/actions/runs/$runId/artifacts?per_page=100"
if ($artifactsResponse.total_count -ne 1) {
    throw 'The producer run must contain exactly one artifact.'
}
$artifactMatches = @($artifactsResponse.artifacts | Where-Object {
        $_.id -eq $expected.identity.artifact.id
    })
if ($artifactMatches.Count -ne 1) {
    throw 'The exact allowlisted artifact is absent or ambiguous.'
}
$artifact = $artifactMatches[0]

$producerCommit = Invoke-Arm64GitHubApi `
    "/repos/$($policy.producer_repository)/git/commits/$($run.head_sha)"
if ($producerCommit.sha -cne $run.head_sha -or
    $producerCommit.tree.sha -cne $expected.identity.producer.tree) {
    throw 'Producer commit or tree does not match the allowlist.'
}

$encodedWorkflowPath = [Uri]::EscapeDataString($run.path).Replace('%2F', '/')
$workflowContent = Invoke-Arm64GitHubApi `
    "/repos/$($policy.producer_repository)/contents/$encodedWorkflowPath?ref=$($run.head_sha)"
if ($workflowContent.type -cne 'file' -or
    $workflowContent.sha -cne $expected.identity.workflow.blob) {
    throw 'Producer workflow blob does not match the allowlist.'
}

$baselineRelease = Get-Arm64ReleaseEvidence `
    -Repository $policy.accepted_baseline.repository `
    -ReleaseId $policy.accepted_baseline.release.id
$baselineAssets = Get-Arm64ReleaseAssets `
    -Repository $policy.accepted_baseline.repository `
    -ReleaseId $policy.accepted_baseline.release.id
$baselineManifest = Get-Arm64CanonicalAssetManifest -Assets $baselineAssets
$baselineAsset = @($baselineManifest.Items | Where-Object {
        $_.id -eq $policy.accepted_baseline.asset_manifest.required_asset.id
    })
if ($baselineAsset.Count -ne 1) {
    throw 'Accepted baseline required asset is absent or ambiguous.'
}
$baseline = [pscustomobject][ordered]@{
    repository    = [string]$policy.accepted_baseline.repository
    release       = $baselineRelease
    annotated_tag = Get-Arm64AnnotatedTagEvidence `
        -Repository $policy.accepted_baseline.repository `
        -TagName $baselineRelease.tag_name
    asset_manifest = [pscustomobject][ordered]@{
        canonicalization = 'id-ascending-compact-json-v1'
        fields           = @('id', 'name', 'size', 'digest', 'state')
        count            = [long]$baselineManifest.Items.Count
        sha256           = [string]$baselineManifest.Sha256
        required_asset   = $baselineAsset[0]
    }
}

$runtimeCommit = Invoke-Arm64GitHubApi `
    "/repos/$($expected.identity.runtime.repository)/git/commits/$($expected.identity.runtime.commit)"
if ($runtimeCommit.sha -cne $expected.identity.runtime.commit) {
    throw 'Runtime commit does not exist at the exact allowlisted identity.'
}
$ancestryChecks = @($policy.revocations.runtime.commits_and_descendants | ForEach-Object {
        $revokedCommit = $_
        $compare = Invoke-Arm64GitHubApi `
            "/repos/$($expected.identity.runtime.repository)/compare/$revokedCommit...$($runtimeCommit.sha)"
        [pscustomobject][ordered]@{
            revoked_commit  = [string]$revokedCommit
            candidate_commit = [string]$runtimeCommit.sha
            query_complete   = $true
            is_descendant    = $compare.status -in @('ahead', 'identical')
        }
    })

$runtimeReleaseBundle = Get-Arm64ReleaseBundle `
    -Repository $expected.identity.runtime.repository `
    -ReleaseId $expected.identity.runtime.release.id
$binutilsReleaseBundle = Get-Arm64ReleaseBundle `
    -Repository $expected.identity.binutils.repository `
    -ReleaseId $expected.identity.binutils.release.id
$binutilsAssets = @($binutilsReleaseBundle.assets | Where-Object {
        $_.id -eq $expected.identity.binutils.asset.id
    })
if ($binutilsAssets.Count -ne 1) {
    throw 'The exact binutils package asset is absent or ambiguous.'
}
$binutilsAsset = $binutilsAssets[0]
$identity = [pscustomobject][ordered]@{
    producer = [pscustomobject][ordered]@{
        repository     = [string]$policy.producer_repository
        commit         = [string]$producerCommit.sha
        tree           = [string]$producerCommit.tree.sha
        parents        = @($producerCommit.parents | ForEach-Object { [string]$_.sha })
        commit_message = [string]$producerCommit.message
    }
    workflow = [pscustomobject][ordered]@{
        path    = [string]$run.path
        blob    = [string]$workflowContent.sha
        actions = $expected.identity.workflow.actions
    }
    run = [pscustomobject][ordered]@{
        id         = [long]$run.id
        attempt    = [long]$run.run_attempt
        job        = [string]$jobs[0].name
        event_name = [string]$run.event
        ref        = "refs/heads/$($run.head_branch)"
        head_sha   = [string]$run.head_sha
    }
    artifact = [pscustomobject][ordered]@{
        id         = [long]$artifact.id
        name       = [string]$artifact.name
        size       = [long]$artifact.size_in_bytes
        digest     = [string]$artifact.digest
        expires_at = ([DateTimeOffset]$artifact.expires_at).ToUniversalTime().ToString(
            "yyyy-MM-dd'T'HH:mm:ss'Z'"
        )
    }
    runtime = [pscustomobject][ordered]@{
        repository = [string]$expected.identity.runtime.repository
        release    = [pscustomobject][ordered]@{
            id             = [long]$runtimeReleaseBundle.id
            immutable      = [bool]$runtimeReleaseBundle.immutable
            draft          = [bool]$runtimeReleaseBundle.draft
            prerelease     = [bool]$runtimeReleaseBundle.prerelease
            tag_name       = [string]$runtimeReleaseBundle.tag_name
            published_at   = [string]$runtimeReleaseBundle.published_at
            annotated_tag  = $runtimeReleaseBundle.annotated_tag
            asset_manifest = $runtimeReleaseBundle.asset_manifest
        }
        commit     = [string]$runtimeCommit.sha
    }
    binutils = [pscustomobject][ordered]@{
        repository     = [string]$expected.identity.binutils.repository
        release        = [pscustomobject][ordered]@{
            id             = [long]$binutilsReleaseBundle.id
            immutable      = [bool]$binutilsReleaseBundle.immutable
            draft          = [bool]$binutilsReleaseBundle.draft
            prerelease     = [bool]$binutilsReleaseBundle.prerelease
            tag_name       = [string]$binutilsReleaseBundle.tag_name
            published_at   = [string]$binutilsReleaseBundle.published_at
            annotated_tag  = $binutilsReleaseBundle.annotated_tag
            asset_manifest = $binutilsReleaseBundle.asset_manifest
        }
        source_commit   = [string]$binutilsReleaseBundle.annotated_tag.peeled_commit
        asset          = [pscustomobject][ordered]@{
            id     = [long]$binutilsAsset.id
            name   = [string]$binutilsAsset.name
            size   = [long]$binutilsAsset.size
            digest = [string]$binutilsAsset.digest
        }
        package_digest = [string]$binutilsAsset.digest
    }
}

$trustedNow = [DateTimeOffset]::UtcNow
$evidence = [pscustomobject][ordered]@{
    schema_version = [long]$policy.schema_version
    authority      = [pscustomobject][ordered]@{
        kind          = [string]$policy.trusted_collector.authority
        repository    = [string]$env:GITHUB_REPOSITORY
        protected_ref = [string]$env:GITHUB_REF
        workflow_ref  = [string]$env:GITHUB_WORKFLOW_REF
        collected_at  = $trustedNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        fixture_only  = $false
    }
    baseline       = $baseline
    candidate      = [pscustomobject][ordered]@{
        admission_id   = [string]$expected.admission_id
        identity       = $identity
        ancestry_checks = $ancestryChecks
        workspace      = $workspace
    }
}

$result = Test-Arm64AdmissionEvidence `
    -Evidence $evidence `
    -Policy $policy `
    -TrustedNow $trustedNow `
    -Mode TrustedCollector
if (-not $result.Allowed) {
    throw "Authoritative ARM64 evidence denied: $($result.Errors -join ', ')"
}

Write-Output 'Authoritative ARM64 candidate metadata admitted.'
