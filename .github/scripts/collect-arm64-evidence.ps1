[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'github-rest.ps1')

function Assert-Arm64ApiObject {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string[]]$RequiredProperties,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -isnot [pscustomobject]) {
        throw "$Context must be a JSON object."
    }
    $names = @($Value.PSObject.Properties.Name)
    foreach ($name in $RequiredProperties) {
        if ($names -cnotcontains $name -or $null -eq $Value.$name) {
            throw "$Context is missing exact required property '$name'."
        }
    }
}

function Assert-Arm64ApiArray {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object]$Value,
        [Parameter(Mandatory)][string]$Context,
        [int]$MaximumRecords = 1000
    )

    if ($Value -isnot [Array]) {
        throw "$Context must be a JSON array."
    }
    if ($Value.Count -gt $MaximumRecords) {
        throw "$Context exceeds the $MaximumRecords-record fail-closed limit."
    }
}

function Assert-Arm64NonnegativeInteger {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -is [bool] -or "$Value" -cnotmatch '^(0|[1-9][0-9]*)$') {
        throw "$Context must be a nonnegative integer."
    }
    $parsed = 0L
    if (-not [long]::TryParse(
            "$Value",
            [Globalization.NumberStyles]::None,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$parsed
        )) {
        throw "$Context exceeds the supported integer range."
    }
    return $parsed
}

function Assert-Arm64Boolean {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -isnot [bool]) {
        throw "$Context must be a JSON boolean."
    }
    return [bool]$Value
}

function Assert-Arm64CanonicalTimestamp {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Context
    )

    $parsed = [DateTimeOffset]::MinValue
    if ($Value -isnot [string] -or
        $Value -cnotmatch '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' -or
        -not [DateTimeOffset]::TryParseExact(
            $Value,
            "yyyy-MM-dd'T'HH:mm:ss'Z'",
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal,
            [ref]$parsed
        )) {
        throw "$Context must be a canonical UTC timestamp."
    }
    return $parsed.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
}

function Assert-Arm64Sha256 {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -isnot [string] -or
        $Value -cnotmatch '^[0-9a-f]{64}$' -or $Value -ceq ('0' * 64)) {
        throw "$Context must be an exact lowercase nonzero SHA-256."
    }
    return $Value
}

function Assert-Arm64Digest {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Context
    )

    if ($Value -isnot [string] -or
        $Value -cnotmatch '^sha256:[0-9a-f]{64}$' -or $Value -ceq "sha256:$('0' * 64)") {
        throw "$Context must be an exact lowercase nonzero sha256 digest."
    }
    return $Value
}

function Invoke-Arm64GitHubApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Endpoint,
        [object]$ReleaseId,
        [object]$RunId,
        [object]$Attempt,
        [string]$ObjectId,
        [string]$BaseObjectId,
        [string]$HeadObjectId,
        [string]$TagName,
        [string]$Path,
        [string]$RefObjectId,
        [object]$Page,
        [object]$PerPage,
        [long]$MaxResponseBytes = 2MB
    )

    if (-not (Get-Variable -Name Arm64GitHubToken -Scope Script -ErrorAction SilentlyContinue)) {
        throw 'The authoritative GitHub token has not been initialized.'
    }
    $arguments = @{}
    foreach ($argument in $PSBoundParameters.GetEnumerator()) {
        if ($argument.Key -cne 'MaxResponseBytes') {
            $arguments[$argument.Key] = $argument.Value
        }
    }
    $request = New-GitHubRestRequest @arguments -MaxResponseBytes $MaxResponseBytes
    return Invoke-GitHubRestGet -Request $request -Token $script:Arm64GitHubToken
}

function Get-Arm64ReleaseEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][object]$ReleaseId
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    $id = Assert-GitHubPositiveId $ReleaseId 'release ID'
    $release = Invoke-Arm64GitHubApi `
        -Repository $repositoryValue `
        -Endpoint Release `
        -ReleaseId $id
    Assert-Arm64ApiObject $release @(
        'id', 'url', 'immutable', 'draft', 'prerelease', 'tag_name',
        'published_at', 'target_commitish'
    ) "release $repositoryValue/$id"
    $returnedId = Assert-GitHubPositiveId $release.id 'returned release ID'
    $expectedUrl = "https://api.github.com/repos/$repositoryValue/releases/$id"
    if ($returnedId -ne $id -or $release.url -cne $expectedUrl) {
        throw "Release identity moved or belongs to another repository: $repositoryValue/$id"
    }
    [void](ConvertTo-GitHubEncodedRef ([string]$release.tag_name) 'release tag name')
    [void](ConvertTo-GitHubEncodedRef ([string]$release.target_commitish) 'release target_commitish')

    return [pscustomobject][ordered]@{
        repository       = $repositoryValue
        id               = $returnedId
        immutable        = Assert-Arm64Boolean $release.immutable 'release immutable'
        draft            = Assert-Arm64Boolean $release.draft 'release draft'
        prerelease       = Assert-Arm64Boolean $release.prerelease 'release prerelease'
        tag_name         = [string]$release.tag_name
        published_at     = Assert-Arm64CanonicalTimestamp $release.published_at 'release published_at'
        target_commitish = [string]$release.target_commitish
    }
}

function Get-Arm64ReleaseAssets {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][object]$ReleaseId
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    $id = Assert-GitHubPositiveId $ReleaseId 'release ID'
    $assets = [Collections.Generic.List[object]]::new()
    for ($page = 1; $page -le 20; $page++) {
        $pageResponse = @(
            Invoke-Arm64GitHubApi `
                -Repository $repositoryValue `
                -Endpoint ReleaseAssets `
                -ReleaseId $id `
                -Page $page `
                -PerPage 100 `
                -MaxResponseBytes 8MB
        )
        if ($null -eq $pageResponse) {
            throw "Release asset page is null: $repositoryValue/$id page $page"
        }
        Assert-Arm64ApiArray $pageResponse "release assets $repositoryValue/$id page $page" 100
        $pageItems = @($pageResponse)
        foreach ($item in $pageItems) {
            Assert-Arm64ApiObject $item @('id', 'url', 'name', 'size', 'digest', 'state') `
                "release asset $repositoryValue/$id"
            $assetId = Assert-GitHubPositiveId $item.id 'release asset ID'
            if ($item.url -cne "https://api.github.com/repos/$repositoryValue/releases/assets/$assetId") {
                throw "Release asset identity moved or belongs to another repository: $assetId"
            }
            if ([string]::IsNullOrWhiteSpace([string]$item.name) -or
                ([string]$item.name).IndexOfAny([char[]]"`r`n") -ge 0) {
                throw "Release asset $assetId has an invalid name."
            }
            [void](Assert-Arm64NonnegativeInteger $item.size "release asset $assetId size")
            [void](Assert-Arm64Digest $item.digest "release asset $assetId digest")
            if ($item.state -cnotin @('uploaded', 'open')) {
                throw "Release asset $assetId has an invalid state."
            }
            [void]$assets.Add($item)
            if ($assets.Count -gt 1000) {
                throw "Release asset records exceeded the fail-closed limit: $repositoryValue/$id"
            }
        }
        if ($pageItems.Count -lt 100) {
            return @($assets)
        }
    }
    throw "Release asset pagination exceeded the fail-closed limit: $repositoryValue/$id"
}

function Get-Arm64CanonicalAssetManifest {
    param([Parameter(Mandatory)][object[]]$Assets)

    Assert-Arm64ApiArray $Assets 'canonical asset manifest'
    $seenIds = [Collections.Generic.HashSet[long]]::new()
    $manifest = @($Assets | ForEach-Object {
            Assert-Arm64ApiObject $_ @('id', 'name', 'size', 'digest', 'state') 'asset manifest entry'
            $id = Assert-GitHubPositiveId $_.id 'asset manifest ID'
            if (-not $seenIds.Add($id)) {
                throw "Asset manifest contains duplicate ID $id."
            }
            [pscustomobject][ordered]@{
                id     = $id
                name   = [string]$_.name
                size   = Assert-Arm64NonnegativeInteger $_.size "asset $id size"
                digest = Assert-Arm64Digest $_.digest "asset $id digest"
                state  = [string]$_.state
            }
        } | Sort-Object id)
    $json = $manifest | ConvertTo-Json -Compress -Depth 8
    $hash = [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))
    return [pscustomobject]@{
        Items  = $manifest
        Sha256 = -join ($hash | ForEach-Object { $_.ToString('x2') })
    }
}

function Get-Arm64TagRefEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$TagName
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    [void](ConvertTo-GitHubEncodedRef $TagName 'tag name')
    $tagRef = Invoke-Arm64GitHubApi `
        -Repository $repositoryValue `
        -Endpoint TagRef `
        -TagName $TagName
    Assert-Arm64ApiObject $tagRef @('ref', 'url', 'object') "tag ref $repositoryValue/$TagName"
    Assert-Arm64ApiObject $tagRef.object @('type', 'sha', 'url') "tag ref object $repositoryValue/$TagName"
    $sha = Assert-GitHubObjectId $tagRef.object.sha 'tag ref object ID'
    if ($tagRef.ref -cne "refs/tags/$TagName" -or
        $tagRef.object.type -cnotin @('commit', 'tag') -or
        $tagRef.url -cnotmatch "^https://api\.github\.com/repos/$([regex]::Escape($repositoryValue))/git/refs/tags/" -or
        $tagRef.object.url -cnotmatch "^https://api\.github\.com/repos/$([regex]::Escape($repositoryValue))/git/(commits|tags)/$sha$") {
        throw "Tag ref moved or belongs to another repository: $repositoryValue/$TagName"
    }
    return [pscustomobject][ordered]@{
        type = [string]$tagRef.object.type
        sha  = $sha
    }
}

function Get-Arm64AnnotatedTagEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$TagName,
        [object]$ExpectedObjectSha
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    $tagRef = Get-Arm64TagRefEvidence -Repository $repositoryValue -TagName $TagName
    if ($tagRef.type -cne 'tag') {
        throw "Release tag is not an annotated object: $repositoryValue/$TagName"
    }
    if ($PSBoundParameters.ContainsKey('ExpectedObjectSha') -and
        $tagRef.sha -cne (Assert-GitHubObjectId $ExpectedObjectSha 'expected annotated tag object ID')) {
        throw "Annotated tag object moved: $repositoryValue/$TagName"
    }
    $tagObject = Invoke-Arm64GitHubApi `
        -Repository $repositoryValue `
        -Endpoint TagObject `
        -ObjectId $tagRef.sha
    Assert-Arm64ApiObject $tagObject @('sha', 'url', 'object') `
        "annotated tag $repositoryValue/$TagName"
    Assert-Arm64ApiObject $tagObject.object @('type', 'sha', 'url') `
        "annotated tag target $repositoryValue/$TagName"
    $returnedTagSha = Assert-GitHubObjectId $tagObject.sha 'returned annotated tag object ID'
    $peeledCommit = Assert-GitHubObjectId $tagObject.object.sha 'peeled tag commit ID'
    if ($returnedTagSha -cne $tagRef.sha -or
        $tagObject.url -cne "https://api.github.com/repos/$repositoryValue/git/tags/$($tagRef.sha)" -or
        $tagObject.object.type -cne 'commit' -or
        $tagObject.object.url -cne "https://api.github.com/repos/$repositoryValue/git/commits/$peeledCommit") {
        throw "Annotated tag does not peel to one exact commit: $repositoryValue/$TagName"
    }
    return [pscustomobject][ordered]@{
        object_sha    = $tagRef.sha
        peeled_commit = $peeledCommit
    }
}

function Get-Arm64ReleaseBundle {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][object]$ReleaseId
    )

    $release = Get-Arm64ReleaseEvidence -Repository $Repository -ReleaseId $ReleaseId
    $assets = Get-Arm64ReleaseAssets -Repository $Repository -ReleaseId $ReleaseId
    $manifest = Get-Arm64CanonicalAssetManifest -Assets $assets
    $tagRef = Get-Arm64TagRefEvidence -Repository $Repository -TagName $release.tag_name
    $annotatedTag = $null
    if ($tagRef.type -ceq 'tag') {
        $annotatedTag = Get-Arm64AnnotatedTagEvidence `
            -Repository $Repository `
            -TagName $release.tag_name `
            -ExpectedObjectSha $tagRef.sha
    }
    return [pscustomobject][ordered]@{
        repository       = $release.repository
        id               = $release.id
        immutable        = $release.immutable
        draft            = $release.draft
        prerelease       = $release.prerelease
        tag_name         = $release.tag_name
        published_at     = $release.published_at
        target_commitish = $release.target_commitish
        tag_ref          = $tagRef
        annotated_tag    = $annotatedTag
        asset_manifest   = [pscustomobject][ordered]@{
            canonicalization = 'id-ascending-compact-json-v1'
            fields           = @('id', 'name', 'size', 'digest', 'state')
            count            = [long]$manifest.Items.Count
            sha256           = [string]$manifest.Sha256
        }
        assets           = @($manifest.Items)
    }
}

function Assert-Arm64ReleaseAnchor {
    param(
        [Parameter(Mandatory)][object]$Anchor,
        [Parameter(Mandatory)][object]$Bundle,
        [Parameter(Mandatory)][string]$Context
    )

    Assert-Arm64ApiObject $Anchor @(
        'repository', 'id', 'tag_name', 'immutable', 'draft', 'prerelease',
        'published_at', 'target_commitish', 'tag_ref', 'asset_manifest'
    ) $Context
    Assert-Arm64ApiObject $Anchor.tag_ref @('type', 'sha') "$Context tag_ref"
    Assert-Arm64ApiObject $Anchor.asset_manifest @('count', 'sha256') "$Context asset_manifest"
    $repository = Assert-GitHubRepository $Anchor.repository
    $id = Assert-GitHubPositiveId $Anchor.id "$Context release ID"
    $tagSha = Assert-GitHubObjectId $Anchor.tag_ref.sha "$Context tag ref SHA"
    [void](Assert-Arm64Sha256 $Anchor.asset_manifest.sha256 "$Context manifest hash")
    [void](Assert-GitHubPositiveId $Anchor.asset_manifest.count "$Context manifest count")
    if ($Bundle.repository -cne $repository -or $Bundle.id -ne $id -or
        $Bundle.tag_name -cne $Anchor.tag_name -or
        $Bundle.immutable -ne (Assert-Arm64Boolean $Anchor.immutable "$Context immutable") -or
        $Bundle.draft -ne (Assert-Arm64Boolean $Anchor.draft "$Context draft") -or
        $Bundle.prerelease -ne (Assert-Arm64Boolean $Anchor.prerelease "$Context prerelease") -or
        $Bundle.published_at -cne (Assert-Arm64CanonicalTimestamp $Anchor.published_at "$Context published_at") -or
        $Bundle.target_commitish -cne $Anchor.target_commitish -or
        $Bundle.tag_ref.type -cne $Anchor.tag_ref.type -or
        $Bundle.tag_ref.sha -cne $tagSha -or
        $Bundle.asset_manifest.count -ne [long]$Anchor.asset_manifest.count -or
        $Bundle.asset_manifest.sha256 -cne $Anchor.asset_manifest.sha256) {
        throw "$Context does not match its exact authoritative release state."
    }

    $hasAnnotated = @($Anchor.PSObject.Properties.Name) -ccontains 'annotated_tag'
    if ($hasAnnotated) {
        Assert-Arm64ApiObject $Anchor.annotated_tag @('object_sha', 'peeled_commit') "$Context annotated_tag"
        $objectSha = Assert-GitHubObjectId $Anchor.annotated_tag.object_sha "$Context annotated tag object"
        $peeled = Assert-GitHubObjectId $Anchor.annotated_tag.peeled_commit "$Context peeled commit"
        if ($null -eq $Bundle.annotated_tag -or
            $Bundle.annotated_tag.object_sha -cne $objectSha -or
            $Bundle.annotated_tag.peeled_commit -cne $peeled) {
            throw "$Context annotated tag identity moved."
        }
    }
    elseif ($null -ne $Bundle.annotated_tag) {
        throw "$Context unexpectedly resolves through an annotated tag."
    }
}

function Confirm-Arm64RevokedReleases {
    param(
        [AllowEmptyCollection()][object[]]$Anchors,
        [Parameter(Mandatory)][string]$Context
    )

    Assert-Arm64ApiArray $Anchors "$Context release anchors" 100
    if ($Anchors.Count -eq 0) {
        throw "$Context anchors cannot be empty."
    }
    $confirmed = [Collections.Generic.List[object]]::new()
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($anchor in $Anchors) {
        Assert-Arm64ApiObject $anchor @('repository', 'id') "$Context release anchor"
        $anchorKey = "$($anchor.repository)/$($anchor.id)"
        if (-not $seen.Add($anchorKey)) {
            throw "$Context contains duplicate release identity $anchorKey."
        }
        $bundle = Get-Arm64ReleaseBundle `
            -Repository $anchor.repository `
            -ReleaseId $anchor.id
        Assert-Arm64ReleaseAnchor -Anchor $anchor -Bundle $bundle -Context $Context
        [void]$confirmed.Add([pscustomobject]@{ Anchor = $anchor; Bundle = $bundle })
    }
    return @($confirmed)
}

function Get-Arm64CommitEvidence {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Commit
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    $commitValue = Assert-GitHubObjectId $Commit 'requested commit ID'
    $response = Invoke-Arm64GitHubApi `
        -Repository $repositoryValue `
        -Endpoint Commit `
        -ObjectId $commitValue
    Assert-Arm64ApiObject $response @('sha', 'url', 'tree', 'parents', 'message') `
        "commit $repositoryValue/$commitValue"
    Assert-Arm64ApiObject $response.tree @('sha', 'url') "commit tree $repositoryValue/$commitValue"
    $returnedSha = Assert-GitHubObjectId $response.sha 'returned commit ID'
    $treeSha = Assert-GitHubObjectId $response.tree.sha 'returned commit tree ID'
    if ($returnedSha -cne $commitValue -or
        $response.url -cne "https://api.github.com/repos/$repositoryValue/git/commits/$commitValue" -or
        $response.tree.url -cne "https://api.github.com/repos/$repositoryValue/git/trees/$treeSha") {
        throw "Commit identity moved or belongs to another repository: $repositoryValue/$commitValue"
    }
    Assert-Arm64ApiArray $response.parents "commit parents $repositoryValue/$commitValue" 100
    $parents = @($response.parents)
    foreach ($entry in $parents) {
        Assert-Arm64ApiObject $entry @('sha', 'url') "commit parent $repositoryValue/$commitValue"
        $parentSha = Assert-GitHubObjectId $entry.sha 'commit parent ID'
        if ($entry.url -cne "https://api.github.com/repos/$repositoryValue/git/commits/$parentSha") {
            throw "Commit parent belongs to another repository: $parentSha"
        }
    }
    return $response
}

function Get-Arm64AncestryCheck {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$RevokedCommit,
        [Parameter(Mandatory)][string]$RevokedTree,
        [Parameter(Mandatory)][string]$CandidateCommit
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    if ($repositoryValue -cne 'crutkas/msys2-runtime') {
        throw 'Runtime revocation comparisons are restricted to crutkas/msys2-runtime.'
    }
    $base = Assert-GitHubObjectId $RevokedCommit 'revoked comparison root'
    $baseTree = Assert-GitHubObjectId $RevokedTree 'revoked comparison root tree'
    $head = Assert-GitHubObjectId $CandidateCommit 'candidate comparison commit'
    $compare = Invoke-Arm64GitHubApi `
        -Repository $repositoryValue `
        -Endpoint Compare `
        -BaseObjectId $base `
        -HeadObjectId $head `
        -MaxResponseBytes 8MB
    Assert-Arm64ApiObject $compare @(
        'status', 'ahead_by', 'behind_by', 'total_commits',
        'base_commit', 'merge_base_commit', 'commits'
    ) "compare $base...$head"
    Assert-Arm64ApiObject $compare.base_commit @('sha') 'compare base_commit'
    Assert-Arm64ApiObject $compare.merge_base_commit @('sha') 'compare merge_base_commit'
    $baseReturned = Assert-GitHubObjectId $compare.base_commit.sha 'compare returned base'
    $mergeBase = Assert-GitHubObjectId $compare.merge_base_commit.sha 'compare merge base'
    $aheadBy = Assert-Arm64NonnegativeInteger $compare.ahead_by 'compare ahead_by'
    $behindBy = Assert-Arm64NonnegativeInteger $compare.behind_by 'compare behind_by'
    $totalCommits = Assert-Arm64NonnegativeInteger $compare.total_commits 'compare total_commits'
    Assert-Arm64ApiArray $compare.commits 'compare commits' 1000
    $commits = @($compare.commits)
    if ($baseReturned -cne $base -or $totalCommits -ne $commits.Count -or
        $compare.status -cnotin @('ahead', 'behind', 'diverged', 'identical')) {
        throw "Compare response is incomplete or does not match $base...$head."
    }
    foreach ($entry in $commits) {
        Assert-Arm64ApiObject $entry @('sha') 'compare commit'
        [void](Assert-GitHubObjectId $entry.sha 'compare commit ID')
    }
    switch ($compare.status) {
        'identical' {
            if ($base -cne $head -or $aheadBy -ne 0 -or $behindBy -ne 0 -or $commits.Count -ne 0) {
                throw 'Identical compare response is internally inconsistent.'
            }
        }
        'ahead' {
            if ($aheadBy -le 0 -or $behindBy -ne 0 -or $commits.Count -eq 0 -or
                $commits[-1].sha -cne $head) {
                throw 'Ahead compare response is incomplete or does not terminate at the candidate.'
            }
        }
        'behind' {
            if ($aheadBy -ne 0 -or $behindBy -le 0 -or $mergeBase -cne $head) {
                throw 'Behind compare response does not bind the candidate identity.'
            }
        }
        'diverged' {
            if ($aheadBy -le 0 -or $behindBy -le 0 -or $commits.Count -eq 0 -or
                $commits[-1].sha -cne $head) {
                throw 'Diverged compare response is incomplete or does not terminate at the candidate.'
            }
        }
    }
    return [pscustomobject][ordered]@{
        repository       = $repositoryValue
        revoked_commit   = $base
        revoked_tree     = $baseTree
        candidate_commit = $head
        query_complete   = $true
        is_descendant    = $compare.status -cin @('ahead', 'identical')
    }
}

if ($MyInvocation.InvocationName -eq '.') {
    return
}

$policyPath = Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'
$admissionPath = Join-Path $PSScriptRoot 'arm64-admission.ps1'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 64
. $admissionPath

# This denial remains before token use or any API access.
if ($policy.live_admission_enabled -isnot [bool] -or -not $policy.live_admission_enabled) {
    throw 'Live ARM64 admission is bootstrap-disabled.'
}
if (@($policy.explicit_admissions).Count -eq 0) {
    throw 'No exact ARM64 candidate identity is allowlisted.'
}
if ($policy.trusted_collector.api_url -cne 'https://api.github.com') {
    throw 'Trusted collector API origin is not the hard-pinned GitHub origin.'
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
if ($env:GITHUB_API_URL -cne 'https://api.github.com' -or
    $env:GITHUB_EVENT_NAME -cne $policy.trusted_collector.event -or
    $env:GITHUB_REPOSITORY -cne $policy.producer_repository -or
    $env:GITHUB_REF -cne $policy.protected_ref -or
    $env:GITHUB_WORKFLOW_REF -cne $policy.trusted_collector.workflow_ref) {
    throw 'Trusted collector is not running from the protected main workflow context.'
}

$workspace = Get-Arm64CanonicalWorkspaceEvidence -Path $env:GITHUB_WORKSPACE -Policy $policy
$event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw | ConvertFrom-Json -Depth 64
Assert-Arm64ApiObject $event @('workflow_run') 'workflow_run event'
Assert-Arm64ApiObject $event.workflow_run @(
    'id', 'run_attempt', 'head_sha', 'head_repository'
) 'workflow_run event identity'
Assert-Arm64ApiObject $event.workflow_run.head_repository @('full_name') `
    'workflow_run head repository'
$eventRunId = Assert-GitHubPositiveId $event.workflow_run.id 'event workflow run ID'
$eventAttempt = Assert-GitHubPositiveId $event.workflow_run.run_attempt 'event workflow run attempt'
$eventHeadSha = Assert-GitHubObjectId $event.workflow_run.head_sha 'event workflow run head SHA'
if ($event.workflow_run.head_repository.full_name -cne $policy.producer_repository) {
    throw 'workflow_run event identity belongs to another repository.'
}

$admissions = @($policy.explicit_admissions | Where-Object {
        $_.identity.run.id -eq $eventRunId -and
        $_.identity.run.attempt -eq $eventAttempt -and
        $_.identity.run.head_sha -ceq $eventHeadSha
    })
if ($admissions.Count -ne 1) {
    throw 'The workflow_run event does not identify exactly one allowlisted candidate.'
}
$expected = $admissions[0]
$script:Arm64GitHubToken = $env:GITHUB_TOKEN

$producerRepository = Assert-GitHubRepository $policy.producer_repository
$run = Invoke-Arm64GitHubApi `
    -Repository $producerRepository `
    -Endpoint WorkflowRun `
    -RunId $eventRunId
Assert-Arm64ApiObject $run @(
    'id', 'url', 'run_attempt', 'head_sha', 'head_branch', 'path',
    'event', 'conclusion', 'repository'
) 'authoritative workflow run'
Assert-Arm64ApiObject $run.repository @('full_name') 'workflow run repository'
if ((Assert-GitHubPositiveId $run.id 'returned workflow run ID') -ne $expected.identity.run.id -or
    (Assert-GitHubPositiveId $run.run_attempt 'returned workflow run attempt') -ne $expected.identity.run.attempt -or
    (Assert-GitHubObjectId $run.head_sha 'returned workflow run head SHA') -cne $expected.identity.run.head_sha -or
    $run.url -cne "https://api.github.com/repos/$producerRepository/actions/runs/$eventRunId" -or
    $run.repository.full_name -cne $producerRepository -or
    $run.head_branch -cne 'main' -or
    $run.path -cne $expected.identity.workflow.path -or
    $run.event -cne $expected.identity.run.event_name -or
    $run.conclusion -cne 'success') {
    throw 'Authoritative run metadata does not match the allowlisted identity.'
}

$jobsResponse = Invoke-Arm64GitHubApi `
    -Repository $producerRepository `
    -Endpoint AttemptJobs `
    -RunId $eventRunId `
    -Attempt $expected.identity.run.attempt
Assert-Arm64ApiObject $jobsResponse @('total_count', 'jobs') 'workflow jobs response'
$jobs = @($jobsResponse.jobs)
Assert-Arm64ApiArray $jobsResponse.jobs 'workflow jobs' 100
if ((Assert-Arm64NonnegativeInteger $jobsResponse.total_count 'jobs total_count') -ne $jobs.Count -or
    $jobs.Count -ne 1) {
    throw 'The producer run attempt must contain exactly one complete job record.'
}
foreach ($jobEntry in $jobs) {
    Assert-Arm64ApiObject $jobEntry @('id', 'run_id', 'head_sha', 'name', 'conclusion', 'url') `
        'workflow job'
    [void](Assert-GitHubPositiveId $jobEntry.id 'workflow job ID')
    if ((Assert-GitHubPositiveId $jobEntry.run_id 'workflow job run ID') -ne $eventRunId -or
        (Assert-GitHubObjectId $jobEntry.head_sha 'workflow job head SHA') -cne $run.head_sha -or
        $jobEntry.url -cnotmatch "^https://api\.github\.com/repos/$([regex]::Escape($producerRepository))/actions/jobs/[1-9][0-9]*$") {
        throw 'Workflow job identity moved or is incomplete.'
    }
}
if ($jobs[0].name -cne $expected.identity.run.job -or $jobs[0].conclusion -cne 'success') {
    throw 'The exact successful producer job is absent.'
}

$artifactsResponse = Invoke-Arm64GitHubApi `
    -Repository $producerRepository `
    -Endpoint RunArtifacts `
    -RunId $eventRunId
Assert-Arm64ApiObject $artifactsResponse @('total_count', 'artifacts') 'workflow artifacts response'
$artifacts = @($artifactsResponse.artifacts)
Assert-Arm64ApiArray $artifactsResponse.artifacts 'workflow artifacts' 100
if ((Assert-Arm64NonnegativeInteger $artifactsResponse.total_count 'artifacts total_count') -ne $artifacts.Count -or
    $artifacts.Count -ne 1) {
    throw 'The producer run must contain exactly one complete artifact record.'
}
$artifact = $artifacts[0]
Assert-Arm64ApiObject $artifact @(
    'id', 'url', 'name', 'size_in_bytes', 'digest', 'expired', 'expires_at', 'workflow_run'
) 'workflow artifact'
Assert-Arm64ApiObject $artifact.workflow_run @('id', 'head_sha') 'artifact workflow_run'
$artifactId = Assert-GitHubPositiveId $artifact.id 'artifact ID'
if ($artifactId -ne $expected.identity.artifact.id -or
    $artifact.url -cne "https://api.github.com/repos/$producerRepository/actions/artifacts/$artifactId" -or
    (Assert-GitHubPositiveId $artifact.workflow_run.id 'artifact workflow run ID') -ne $eventRunId -or
    (Assert-GitHubObjectId $artifact.workflow_run.head_sha 'artifact workflow head SHA') -cne $run.head_sha -or
    $artifact.expired -isnot [bool] -or $artifact.expired) {
    throw 'The exact allowlisted artifact identity is absent, expired, or moved.'
}

$producerCommit = Get-Arm64CommitEvidence `
    -Repository $producerRepository `
    -Commit $run.head_sha
if ($producerCommit.tree.sha -cne $expected.identity.producer.tree) {
    throw 'Producer commit tree does not match the allowlist.'
}

[void](ConvertTo-GitHubEncodedPath $run.path)
$workflowContent = Invoke-Arm64GitHubApi `
    -Repository $producerRepository `
    -Endpoint Contents `
    -Path $run.path `
    -RefObjectId $run.head_sha
Assert-Arm64ApiObject $workflowContent @('type', 'sha', 'path', 'url', 'git_url') `
    'producer workflow content'
$workflowSha = Assert-GitHubObjectId $workflowContent.sha 'workflow blob ID'
if ($workflowContent.type -cne 'file' -or $workflowContent.path -cne $run.path -or
    $workflowSha -cne $expected.identity.workflow.blob -or
    $workflowContent.git_url -cne "https://api.github.com/repos/$producerRepository/git/blobs/$workflowSha" -or
    $workflowContent.url -cnotmatch "^https://api\.github\.com/repos/$([regex]::Escape($producerRepository))/contents/") {
    throw 'Producer workflow blob does not match the exact allowlist identity.'
}

$baselineBundle = Get-Arm64ReleaseBundle `
    -Repository $policy.accepted_baseline.repository `
    -ReleaseId $policy.accepted_baseline.release.id
$baselineAnchor = [pscustomobject][ordered]@{
    repository       = $policy.accepted_baseline.repository
    id               = $policy.accepted_baseline.release.id
    tag_name         = $policy.accepted_baseline.release.tag_name
    immutable        = $policy.accepted_baseline.release.immutable
    draft            = $policy.accepted_baseline.release.draft
    prerelease       = $policy.accepted_baseline.release.prerelease
    published_at     = $policy.accepted_baseline.release.published_at
    target_commitish = $policy.accepted_baseline.release.target_commitish
    tag_ref          = $policy.accepted_baseline.tag_ref
    annotated_tag    = $policy.accepted_baseline.annotated_tag
    asset_manifest   = $policy.accepted_baseline.asset_manifest
}
Assert-Arm64ReleaseAnchor -Anchor $baselineAnchor -Bundle $baselineBundle -Context 'accepted baseline'
if ($baselineBundle.id -ne 368726166 -or $baselineBundle.asset_manifest.count -ne 113) {
    throw 'Accepted baseline release 368726166 or its 113-asset manifest moved.'
}
$baselineAsset = @($baselineBundle.assets | Where-Object {
        $_.id -eq $policy.accepted_baseline.asset_manifest.required_asset.id
    })
if ($baselineAsset.Count -ne 1) {
    throw 'Accepted baseline required asset is absent or ambiguous.'
}
$baseline = [pscustomobject][ordered]@{
    repository    = [string]$policy.accepted_baseline.repository
    release       = [pscustomobject][ordered]@{
        id           = [long]$baselineBundle.id
        immutable    = [bool]$baselineBundle.immutable
        draft        = [bool]$baselineBundle.draft
        prerelease   = [bool]$baselineBundle.prerelease
        tag_name     = [string]$baselineBundle.tag_name
        published_at = [string]$baselineBundle.published_at
        target_commitish = [string]$baselineBundle.target_commitish
    }
    tag_ref       = $baselineBundle.tag_ref
    annotated_tag = $baselineBundle.annotated_tag
    asset_manifest = [pscustomobject][ordered]@{
        canonicalization = 'id-ascending-compact-json-v1'
        fields           = @('id', 'name', 'size', 'digest', 'state')
        count            = [long]$baselineBundle.asset_manifest.count
        sha256           = [string]$baselineBundle.asset_manifest.sha256
        required_asset   = $baselineAsset[0]
    }
}

Assert-Arm64ApiObject $policy.revocations.runtime @(
    'repository', 'commits_and_descendants', 'releases'
) 'runtime revocation policy'
if ($policy.revocations.runtime.repository -cne 'crutkas/msys2-runtime') {
    throw 'Runtime revocation repository must be exactly crutkas/msys2-runtime.'
}
$revokedRoots = @($policy.revocations.runtime.commits_and_descendants)
Assert-Arm64ApiArray $policy.revocations.runtime.commits_and_descendants 'runtime revoked roots' 100
if ($revokedRoots.Count -eq 0) {
    throw 'Runtime revoked roots cannot be empty.'
}
foreach ($root in $revokedRoots) {
    Assert-Arm64ApiObject $root @('commit', 'tree') 'runtime revoked root'
    $rootCommit = Assert-GitHubObjectId $root.commit 'runtime revoked root commit'
    $rootTree = Assert-GitHubObjectId $root.tree 'runtime revoked root tree'
    $confirmedRoot = Get-Arm64CommitEvidence `
        -Repository 'crutkas/msys2-runtime' `
        -Commit $rootCommit
    if ($confirmedRoot.tree.sha -cne $rootTree) {
        throw "Revoked runtime root tree moved: $rootCommit"
    }
}

Assert-Arm64ApiObject $policy.revocations.binutils @('releases', 'package_sha256') `
    'binutils revocation policy'
Assert-Arm64ApiArray $policy.revocations.runtime.releases 'runtime revoked releases' 100
Assert-Arm64ApiArray $policy.revocations.binutils.releases 'binutils revoked releases' 100
$confirmedRuntimeRevocations = Confirm-Arm64RevokedReleases `
    -Anchors @($policy.revocations.runtime.releases) `
    -Context 'revoked runtime release'
$confirmedBinutilsRevocations = Confirm-Arm64RevokedReleases `
    -Anchors @($policy.revocations.binutils.releases) `
    -Context 'revoked binutils release'

$packageRevocations = @($policy.revocations.binutils.package_sha256)
Assert-Arm64ApiArray $policy.revocations.binutils.package_sha256 'revoked binutils packages' 100
if ($packageRevocations.Count -eq 0) {
    throw 'Revoked binutils package anchors cannot be empty.'
}
$seenPackageHashes = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($packageAnchor in $packageRevocations) {
    Assert-Arm64ApiObject $packageAnchor @(
        'sha256', 'repository', 'release_id', 'asset'
    ) 'revoked binutils package'
    Assert-Arm64ApiObject $packageAnchor.asset @('id', 'name', 'size', 'digest', 'state') `
        'revoked binutils package asset'
    $packageHash = Assert-Arm64Sha256 $packageAnchor.sha256 'revoked package SHA-256'
    if (-not $seenPackageHashes.Add($packageHash)) {
        throw "Duplicate revoked package SHA-256: $packageHash"
    }
    $packageRepository = Assert-GitHubRepository $packageAnchor.repository
    $packageReleaseId = Assert-GitHubPositiveId $packageAnchor.release_id 'revoked package release ID'
    $matchingRelease = @($confirmedBinutilsRevocations | Where-Object {
            $_.Bundle.repository -ceq $packageRepository -and
            $_.Bundle.id -eq $packageReleaseId
        })
    if ($matchingRelease.Count -ne 1) {
        throw 'Revoked package does not bind exactly one confirmed binutils release.'
    }
    $assetId = Assert-GitHubPositiveId $packageAnchor.asset.id 'revoked package asset ID'
    $matchingAsset = @($matchingRelease[0].Bundle.assets | Where-Object { $_.id -eq $assetId })
    if ($matchingAsset.Count -ne 1 -or
        $matchingAsset[0].name -cne $packageAnchor.asset.name -or
        $matchingAsset[0].size -ne (Assert-Arm64NonnegativeInteger $packageAnchor.asset.size 'revoked asset size') -or
        $matchingAsset[0].digest -cne (Assert-Arm64Digest $packageAnchor.asset.digest 'revoked asset digest') -or
        $matchingAsset[0].state -cne $packageAnchor.asset.state -or
        $matchingAsset[0].digest -cne "sha256:$packageHash") {
        throw 'Revoked binutils digest is not bound to its exact authoritative release asset.'
    }
}

$runtimeRepository = Assert-GitHubRepository $expected.identity.runtime.repository
if ($runtimeRepository -cne 'crutkas/msys2-runtime') {
    throw 'Candidate runtime repository must be exactly crutkas/msys2-runtime.'
}
$runtimeCommit = Get-Arm64CommitEvidence `
    -Repository $runtimeRepository `
    -Commit $expected.identity.runtime.commit
$ancestryChecks = @($revokedRoots | ForEach-Object {
        Get-Arm64AncestryCheck `
            -Repository 'crutkas/msys2-runtime' `
            -RevokedCommit $_.commit `
            -RevokedTree $_.tree `
            -CandidateCommit $runtimeCommit.sha
    })

$runtimeReleaseBundle = Get-Arm64ReleaseBundle `
    -Repository $expected.identity.runtime.release.repository `
    -ReleaseId $expected.identity.runtime.release.id
$binutilsReleaseBundle = Get-Arm64ReleaseBundle `
    -Repository $expected.identity.binutils.release.repository `
    -ReleaseId $expected.identity.binutils.release.id
if ($null -eq $runtimeReleaseBundle.annotated_tag -or $null -eq $binutilsReleaseBundle.annotated_tag) {
    throw 'Candidate runtime and binutils releases must resolve through exact annotated tags.'
}
$binutilsAssets = @($binutilsReleaseBundle.assets | Where-Object {
        $_.id -eq $expected.identity.binutils.asset.id
    })
if ($binutilsAssets.Count -ne 1) {
    throw 'The exact binutils package asset is absent or ambiguous.'
}
$binutilsAsset = $binutilsAssets[0]

$identity = [pscustomobject][ordered]@{
    producer = [pscustomobject][ordered]@{
        repository     = $producerRepository
        commit         = [string]$producerCommit.sha
        tree           = [string]$producerCommit.tree.sha
        parents        = @($producerCommit.parents | ForEach-Object {
                Assert-GitHubObjectId $_.sha 'producer parent ID'
            })
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
        size       = Assert-Arm64NonnegativeInteger $artifact.size_in_bytes 'artifact size'
        digest     = Assert-Arm64Digest $artifact.digest 'artifact digest'
        expires_at = Assert-Arm64CanonicalTimestamp $artifact.expires_at 'artifact expires_at'
    }
    runtime = [pscustomobject][ordered]@{
        repository = $runtimeRepository
        release    = [pscustomobject][ordered]@{
            repository     = [string]$runtimeReleaseBundle.repository
            id             = [long]$runtimeReleaseBundle.id
            immutable      = [bool]$runtimeReleaseBundle.immutable
            draft          = [bool]$runtimeReleaseBundle.draft
            prerelease     = [bool]$runtimeReleaseBundle.prerelease
            tag_name       = [string]$runtimeReleaseBundle.tag_name
            published_at   = [string]$runtimeReleaseBundle.published_at
            target_commitish = [string]$runtimeReleaseBundle.target_commitish
            tag_ref         = $runtimeReleaseBundle.tag_ref
            annotated_tag  = $runtimeReleaseBundle.annotated_tag
            asset_manifest = $runtimeReleaseBundle.asset_manifest
        }
        commit     = [string]$runtimeCommit.sha
    }
    binutils = [pscustomobject][ordered]@{
        repository     = [string]$expected.identity.binutils.repository
        release        = [pscustomobject][ordered]@{
            repository     = [string]$binutilsReleaseBundle.repository
            id             = [long]$binutilsReleaseBundle.id
            immutable      = [bool]$binutilsReleaseBundle.immutable
            draft          = [bool]$binutilsReleaseBundle.draft
            prerelease     = [bool]$binutilsReleaseBundle.prerelease
            tag_name       = [string]$binutilsReleaseBundle.tag_name
            published_at   = [string]$binutilsReleaseBundle.published_at
            target_commitish = [string]$binutilsReleaseBundle.target_commitish
            tag_ref         = $binutilsReleaseBundle.tag_ref
            annotated_tag  = $binutilsReleaseBundle.annotated_tag
            asset_manifest = $binutilsReleaseBundle.asset_manifest
        }
        source_commit   = [string]$binutilsReleaseBundle.annotated_tag.peeled_commit
        asset          = [pscustomobject][ordered]@{
            id     = [long]$binutilsAsset.id
            name   = [string]$binutilsAsset.name
            size   = [long]$binutilsAsset.size
            digest = [string]$binutilsAsset.digest
            state  = [string]$binutilsAsset.state
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
        admission_id    = [string]$expected.admission_id
        identity        = $identity
        ancestry_checks = $ancestryChecks
        workspace       = $workspace
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
