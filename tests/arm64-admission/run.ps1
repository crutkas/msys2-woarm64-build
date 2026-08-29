[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$livePolicyPath = Join-Path $repoRoot '.github\policies\arm64-quarantine-policy.json'
$fixturePolicyPath = Join-Path $PSScriptRoot 'fixtures\fixture-policy.json'
$fixtureEvidencePath = Join-Path $PSScriptRoot 'fixtures\fixture-evidence.json'
$evidenceCasesPath = Join-Path $PSScriptRoot 'fixtures\evidence-cases.json'
$workflowFixtureRoot = Join-Path $PSScriptRoot 'workflow-fixtures'

. ./.github/scripts/arm64-admission.ps1
. ./.github/scripts/audit-arm64-workflows.ps1
. ./.github/scripts/collect-pr-workflow-data.ps1

$script:assertionCount = 0
function Assert-Arm64 {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][string]$Message
    )

    $script:assertionCount++
    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

function Test-Arm64RuntimeFileWriteLocked {
    param([Parameter(Mandatory)][string]$Path)

    $stream = $null
    try {
        $stream = [IO.File]::Open(
            $Path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Write,
            [IO.FileShare]::ReadWrite
        )
        return $false
    }
    catch [IO.IOException] {
        return $true
    }
    catch [UnauthorizedAccessException] {
        return $true
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

function Copy-JsonObject {
    param([Parameter(Mandatory)][object]$InputObject)

    return $InputObject | ConvertTo-Json -Compress -Depth 64 | ConvertFrom-Json -Depth 64
}

function Get-MutationTarget {
    param(
        [Parameter(Mandatory)][object]$Root,
        [Parameter(Mandatory)][string]$Path
    )

    $segments = $Path.Split('.')
    $current = $Root
    for ($index = 0; $index -lt $segments.Length - 1; $index++) {
        $segment = $segments[$index]
        if ($current -is [Collections.IList] -and $segment -match '^[0-9]+$') {
            $current = $current[[int]$segment]
            continue
        }
        $property = $current.PSObject.Properties[$segment]
        if ($null -eq $property) {
            throw "Mutation parent does not exist: $Path"
        }
        $current = $property.Value
    }

    return [pscustomobject]@{
        Parent = $current
        Leaf = $segments[-1]
    }
}

function Set-MutationPath {
    param(
        [Parameter(Mandatory)][object]$Root,
        [Parameter(Mandatory)][string]$Path,
        [AllowNull()][object]$Value
    )

    $target = Get-MutationTarget -Root $Root -Path $Path
    if ($target.Parent -is [Collections.IList] -and $target.Leaf -match '^[0-9]+$') {
        $target.Parent[[int]$target.Leaf] = $Value
        return
    }
    $property = $target.Parent.PSObject.Properties[$target.Leaf]
    if ($null -eq $property) {
        $target.Parent | Add-Member -MemberType NoteProperty -Name $target.Leaf -Value $Value
    }
    else {
        $property.Value = $Value
    }
}

function Remove-MutationPath {
    param(
        [Parameter(Mandatory)][object]$Root,
        [Parameter(Mandatory)][string]$Path
    )

    $target = Get-MutationTarget -Root $Root -Path $Path
    if ($target.Parent -is [Collections.IList]) {
        throw "Array removal is unsupported in deterministic fixtures: $Path"
    }
    $target.Parent.PSObject.Properties.Remove($target.Leaf)
}

function Invoke-EvidenceTest {
    param(
        [Parameter(Mandatory)][object]$Evidence,
        [Parameter(Mandatory)][object]$Policy,
        [ValidateSet('OfflineFixture', 'TrustedCollector')]
        [string]$Mode = 'OfflineFixture'
    )

    try {
        return Test-Arm64AdmissionEvidence `
            -Evidence $Evidence `
            -Policy $Policy `
            -TrustedNow ([DateTimeOffset]'2026-08-27T22:00:00Z') `
            -Mode $Mode
    }
    catch {
        return [pscustomobject]@{
            Allowed = $false
            Errors = @("fail-closed-exception:$($_.Exception.Message)")
        }
    }
}

function New-WorkflowFixturePolicy {
    param(
        [Parameter(Mandatory)][string]$Root,
        [string[]]$Entrypoints = @(),
        [string]$Authority = 'untrusted-diagnostic'
    )

    $policy = Copy-JsonObject $script:livePolicy
    $policy.PSObject.Properties.Remove('protected_verifier')
    $workflowFiles = @(Get-ChildItem (Join-Path $Root '.github\workflows') -File |
            Where-Object { $_.Extension -in @('.yml', '.yaml') } |
            Sort-Object Name)
    $primary = @($workflowFiles | Where-Object { $_.BaseName -ceq 'test' })[0]
    $relativeWorkflow = $primary.FullName.Substring(
        [IO.Path]::GetFullPath($Root).Length + 1
    ).Replace([IO.Path]::DirectorySeparatorChar, '/')
    $sources = [ordered]@{}
    foreach ($entrypoint in $Entrypoints) {
        $entrypointPath = Join-Path $Root (
            $entrypoint.Replace('/', [IO.Path]::DirectorySeparatorChar)
        )
        $identity = Get-Arm64FileBlobIdentity -Path $entrypointPath
        $sources[$entrypoint] = New-Arm64SourceBinding `
            -Path $entrypoint `
            -Mode '100644' `
            -ObjectType 'blob' `
            -ByteLength $identity.byte_length `
            -Oid $identity.oid
    }
    $workflowIdentity = Get-Arm64FileBlobIdentity -Path $primary.FullName
    $rule = [pscustomobject][ordered]@{
        authority = $Authority
        source = New-Arm64SourceBinding `
            -Path $relativeWorkflow `
            -Mode '100644' `
            -ObjectType 'blob' `
            -ByteLength $workflowIdentity.byte_length `
            -Oid $workflowIdentity.oid
        allowed_events = @('pull_request')
        allowed_local_shell_entrypoints = @($Entrypoints)
        allowed_local_shell_sources = [pscustomobject]$sources
        allowed_inline_shell_sha256 = @()
        allowed_shells = @('pwsh')
    }
    $active = [ordered]@{}
    $active[$relativeWorkflow] = $rule
    $policy.active_workflows = [pscustomobject]$active
    return $policy
}

function Find-SemanticUses {
    param([AllowNull()][object]$Node)

    $found = [Collections.Generic.List[string]]::new()
    function Visit {
        param([AllowNull()][object]$Value)

        if ($null -eq $Value -or $Value -is [string]) {
            return
        }
        if ($Value -is [Collections.IDictionary]) {
            foreach ($key in $Value.Keys) {
                if ([string]$key -ceq 'uses') {
                    [void]$found.Add([string]$Value[$key])
                }
                else {
                    Visit $Value[$key]
                }
            }
            return
        }
        if ($Value -is [pscustomobject]) {
            foreach ($property in $Value.PSObject.Properties) {
                if ($property.Name -ceq 'uses') {
                    [void]$found.Add([string]$property.Value)
                }
                else {
                    Visit $property.Value
                }
            }
            return
        }
        if ($Value -is [Collections.IEnumerable]) {
            foreach ($item in $Value) {
                Visit $item
            }
        }
    }

    Visit $Node
    return @($found)
}

$livePolicy = Get-Content -LiteralPath (
    Join-Path $repoRoot '.github\policies\arm64-quarantine-policy.json'
) -Raw | ConvertFrom-Json -Depth 64
$fixturePolicy = Get-Content -LiteralPath (
    Join-Path $PSScriptRoot 'fixtures\fixture-policy.json'
) -Raw | ConvertFrom-Json -Depth 64
$fixtureEvidence = Get-Content -LiteralPath (
    Join-Path $PSScriptRoot 'fixtures\fixture-evidence.json'
) -Raw | ConvertFrom-Json -Depth 64
$evidenceCases = Get-Content -LiteralPath (
    Join-Path $PSScriptRoot 'fixtures\evidence-cases.json'
) -Raw | ConvertFrom-Json -Depth 64

Assert-Arm64 (-not $livePolicy.live_admission_enabled) 'live admission must remain bootstrap-disabled'
Assert-Arm64 (@($livePolicy.explicit_admissions).Count -eq 0) 'live policy must admit no candidate'
Assert-Arm64 (-not $livePolicy.trusted_collector.caller_json_allowed) 'caller JSON must be forbidden'
Assert-Arm64 ($livePolicy.publication.enabled -is [bool] -and
    -not $livePolicy.publication.enabled) 'publication must be disabled'
Assert-Arm64 (-not $livePolicy.publication.protected_environment_confirmed) `
    'unconfigured approval environment must not be claimed protected'
Assert-Arm64 ($livePolicy.publication.mode -ceq 'unconditional-deny') `
    'publication policy is not an unconditional denial'
Assert-Arm64 ($null -eq $livePolicy.publication.PSObject.Properties['required_environment']) `
    'an unverified publication environment remains configured'
Assert-Arm64 (Test-CandidateSelectedPath -Path 'package.json') `
    'the parser package manifest is absent from protected candidate data'
Assert-Arm64 (Test-CandidateSelectedPath -Path 'package-lock.json') `
    'the parser lockfile is absent from protected candidate data'
Assert-Arm64 (Test-CandidateSelectedPath -Path '.gitattributes') `
    'the checkout normalization policy is absent from protected candidate data'
Assert-Arm64 (-not (Test-CandidateSelectedPath -Path 'unrelated.json')) `
    'unrelated root JSON was added to protected candidate data'
$protectedVerifierSource = Get-Content -LiteralPath (
    Join-Path $repoRoot '.github\scripts\verify-protected-context.ps1'
) -Raw
foreach ($requiredParserSource in @(
        '.gitattributes',
        '.github/scripts/parse-yaml.js',
        'package-lock.json',
        'package.json')) {
    Assert-Arm64 ($protectedVerifierSource.Contains(
            "'$requiredParserSource'",
            [StringComparison]::Ordinal
        )) "protected verifier omits $requiredParserSource"
}
foreach ($retiredParserSource in @('parse-yaml.ps1', 'parse-yaml.rb')) {
    Assert-Arm64 (-not $protectedVerifierSource.Contains(
            $retiredParserSource,
            [StringComparison]::Ordinal
        )) "protected verifier still requires $retiredParserSource"
}
foreach ($publicationField in @('enabled', 'protected_environment_confirmed')) {
    $flippedPolicy = Copy-JsonObject $fixturePolicy
    $flippedPolicy.publication.PSObject.Properties[$publicationField].Value = $true
    $flippedResult = Invoke-EvidenceTest `
        -Evidence $fixtureEvidence `
        -Policy $flippedPolicy
    Assert-Arm64 (-not $flippedResult.Allowed -and
        $flippedResult.Errors -ccontains
            'publication-policy-must-remain-unconditionally-disabled') `
        "flipping publication.$publicationField enabled admission"
}

$admissionAst = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repoRoot '.github\scripts\arm64-admission.ps1'),
    [ref]$null,
    [ref]$null
)
$parameterNames = @($admissionAst.ParamBlock.Parameters | ForEach-Object {
        $_.Name.VariablePath.UserPath
    })
Assert-Arm64 ($parameterNames -cnotcontains 'MetadataJson') 'caller JSON parameter still exists'
Assert-Arm64 ($parameterNames -cnotcontains 'MetadataPath') 'caller metadata path still exists'

$validResult = Invoke-EvidenceTest -Evidence $fixtureEvidence -Policy $fixturePolicy
Assert-Arm64 $validResult.Allowed "fixture-only success case failed: $($validResult.Errors -join ', ')"
$collectorTypedEvidence = Copy-JsonObject $fixtureEvidence
$collectorTypedEvidence.baseline.release.published_at = '2026-08-11T17:35:02Z'
$collectorTypedEvidence.candidate.identity.artifact.expires_at = '2026-09-03T00:00:00Z'
$collectorTypedEvidence.candidate.identity.runtime.release.published_at =
    '2026-08-20T00:00:00Z'
$collectorTypedEvidence.candidate.identity.binutils.release.published_at =
    '2026-08-20T00:00:00Z'
$collectorTypedResult = Invoke-EvidenceTest `
    -Evidence $collectorTypedEvidence `
    -Policy $fixturePolicy
Assert-Arm64 $collectorTypedResult.Allowed `
    "collector string timestamps failed exact comparison: $($collectorTypedResult.Errors -join ', ')"

$liveResult = Invoke-EvidenceTest `
    -Evidence $fixtureEvidence `
    -Policy $livePolicy `
    -Mode TrustedCollector
Assert-Arm64 (-not $liveResult.Allowed) 'bootstrap-disabled live policy admitted fixture evidence'
Assert-Arm64 ($liveResult.Errors -ccontains 'live-admission-bootstrap-disabled') `
    'bootstrap-disabled live policy missed its denial code'

$fixtureLiveResult = Invoke-EvidenceTest `
    -Evidence $fixtureEvidence `
    -Policy $fixturePolicy `
    -Mode TrustedCollector
Assert-Arm64 (-not $fixtureLiveResult.Allowed) 'fixture policy was accepted as live authority'
Assert-Arm64 ($fixtureLiveResult.Errors -ccontains 'fixture-policy-never-live') `
    'fixture policy did not report never-live status'

foreach ($case in $evidenceCases) {
    $evidence = Copy-JsonObject $fixtureEvidence
    if ($null -ne $case.PSObject.Properties['remove']) {
        Remove-MutationPath -Root $evidence -Path $case.remove
    }
    else {
        Set-MutationPath -Root $evidence -Path $case.path -Value $case.value
    }
    $result = Invoke-EvidenceTest -Evidence $evidence -Policy $fixturePolicy
    Assert-Arm64 (-not $result.Allowed) "adversarial evidence passed: $($case.name)"
    Assert-Arm64 ($result.Errors -ccontains $case.error) `
        "adversarial evidence '$($case.name)' missed '$($case.error)': $($result.Errors -join ', ')"
}

$revokedAssetEvidence = Copy-JsonObject $fixtureEvidence
$revokedAssetEvidence.candidate.identity.binutils.release.id = 377908415
$revokedAssetEvidence.candidate.identity.binutils.asset = Copy-JsonObject `
    $fixturePolicy.revocations.binutils.package_sha256[0].asset
$revokedAssetEvidence.candidate.identity.binutils.package_digest =
    $fixturePolicy.revocations.binutils.package_sha256[0].asset.digest
$revokedAssetPolicy = Copy-JsonObject $fixturePolicy
$revokedAssetPolicy.explicit_admissions[0].identity = Copy-JsonObject `
    $revokedAssetEvidence.candidate.identity
$revokedAssetResult = Invoke-EvidenceTest `
    -Evidence $revokedAssetEvidence `
    -Policy $revokedAssetPolicy
Assert-Arm64 (-not $revokedAssetResult.Allowed) `
    'exact repository/release/asset-bound revoked package passed'
Assert-Arm64 ($revokedAssetResult.Errors -ccontains 'revoked-binutils-package') `
    'exact revoked package identity missed its denial'

$wrongRuntimeRepository = Copy-JsonObject $fixtureEvidence
$wrongRuntimeRepository.candidate.identity.runtime.repository = 'example/decoy-runtime'
$wrongRuntimePolicy = Copy-JsonObject $fixturePolicy
$wrongRuntimePolicy.explicit_admissions[0].identity = Copy-JsonObject `
    $wrongRuntimeRepository.candidate.identity
$wrongRuntimeResult = Invoke-EvidenceTest `
    -Evidence $wrongRuntimeRepository `
    -Policy $wrongRuntimePolicy
Assert-Arm64 (-not $wrongRuntimeResult.Allowed -and
    $wrongRuntimeResult.Errors -ccontains 'runtime-authoritative-repository-mismatch') `
    'wrong runtime repository passed revocation ancestry binding'

foreach ($ancestryField in @('repository', 'revoked_commit', 'revoked_tree')) {
    $replayedEvidence = Copy-JsonObject $fixtureEvidence
    $replayedEvidence.candidate.ancestry_checks[0].PSObject.Properties[
        $ancestryField
    ].Value = if ($ancestryField -ceq 'repository') {
        'example/decoy-runtime'
    }
    else {
        'ffffffffffffffffffffffffffffffffffffffff'
    }
    $replayedResult = Invoke-EvidenceTest `
        -Evidence $replayedEvidence `
        -Policy $fixturePolicy
    Assert-Arm64 (-not $replayedResult.Allowed -and
        $replayedResult.Errors -ccontains 'runtime-ancestry-incomplete') `
        "replayed ancestry evidence passed: $ancestryField"
}

$workspaceCases = @(
    @{ Name = 'forward-slash forbidden root'; Input = 'C:/msys64'; Canonical = 'C:\msys64'; Error = 'workspace-forbidden-root' },
    @{ Name = 'device namespace'; Input = '\\?\C:\msys64'; Canonical = 'C:\msys64'; Error = 'workspace-device-namespace' },
    @{ Name = 'NT device namespace'; Input = '\??\C:\msys64'; Canonical = 'C:\msys64'; Error = 'workspace-device-namespace' },
    @{ Name = 'relative path'; Input = '..\msys64'; Canonical = 'C:\safe'; Error = 'workspace-relative' },
    @{ Name = 'non-string path'; Input = 42; Canonical = 'C:\safe'; Error = 'workspace-input-not-string' },
    @{ Name = 'short-name alias'; Input = 'C:\MSYS64~1\candidate'; Canonical = 'C:\safe'; Error = 'workspace-short-name' },
    @{ Name = 'UNC alias'; Input = '\\server\share'; Canonical = '\\server\share'; Error = 'workspace-unc' },
    @{ Name = 'canonical alias'; Input = 'C:\safe'; Canonical = 'C:\msys64\candidate'; Error = 'workspace-forbidden-root' },
    @{ Name = 'containment alias'; Input = 'C:\safe\..\msys64\candidate'; Canonical = 'C:\msys64\candidate'; Error = 'workspace-forbidden-root' },
    @{ Name = 'trailing-dot alias'; Input = 'C:\msys64.'; Canonical = 'C:\msys64'; Error = 'workspace-forbidden-root' },
    @{ Name = 'trailing-space alias'; Input = 'C:\msys64 '; Canonical = 'C:\msys64'; Error = 'workspace-forbidden-root' }
)
foreach ($case in $workspaceCases) {
    $workspace = Copy-JsonObject $fixtureEvidence.candidate.workspace
    $workspace.input_path = $case.Input
    $workspace.canonical_path = $case.Canonical
    $errors = Test-Arm64WorkspaceEvidence -Workspace $workspace -Policy $fixturePolicy
    Assert-Arm64 ($errors -ccontains $case.Error) `
        "workspace bypass '$($case.Name)' missed '$($case.Error)': $($errors -join ', ')"
}
foreach ($case in @(
        @{ Property = 'exists'; Value = $false; Error = 'workspace-not-existing' },
        @{ Property = 'absolute'; Value = $false; Error = 'workspace-not-absolute' },
        @{ Property = 'final_path_resolved'; Value = $false; Error = 'workspace-final-path-unresolved' },
        @{ Property = 'reparse_components'; Value = @('D:\junction'); Error = 'workspace-reparse-component' },
        @{ Property = 'reparse_components'; Value = @('D:\symlink'); Error = 'workspace-reparse-component' },
        @{ Property = 'volume_id'; Value = ''; Error = 'workspace-volume-missing' })) {
    $workspace = Copy-JsonObject $fixtureEvidence.candidate.workspace
    $workspace.PSObject.Properties[$case.Property].Value = $case.Value
    $errors = Test-Arm64WorkspaceEvidence -Workspace $workspace -Policy $fixturePolicy
    Assert-Arm64 ($errors -ccontains $case.Error) `
        "workspace evidence bypass missed '$($case.Error)': $($errors -join ', ')"
}

$canonicalWorkspace = Get-Arm64CanonicalWorkspaceEvidence -Path $repoRoot -Policy $livePolicy
Assert-Arm64 $canonicalWorkspace.final_path_resolved 'workspace final path was not resolved'
Assert-Arm64 (@($canonicalWorkspace.reparse_components).Count -eq 0) `
    'workspace unexpectedly contains a reparse component'
$admissionSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\arm64-admission.ps1') `
    -Raw
$resolverStart = $admissionSource.IndexOf(
    'function Get-Arm64CanonicalWorkspaceEvidence',
    [StringComparison]::Ordinal
)
$resolverSource = $admissionSource.Substring($resolverStart)
Assert-Arm64 ($resolverSource.IndexOf(
        'Normalized workspace aliases the forbidden shared root.',
        [StringComparison]::Ordinal
    ) -lt $resolverSource.IndexOf(
        'Get-Item -LiteralPath $current',
        [StringComparison]::Ordinal
    )) 'normalized forbidden aliases are not rejected before filesystem access'

$semanticCases = @(
    @{ Name = 'yaml-inline'; Error = 'workflow-trigger-not-allowlisted:.github/workflows/test.yaml' },
    @{ Name = 'alias'; Error = 'semantic-yaml-anchor-alias-merge-forbidden:.github/workflows/test.yml' },
    @{ Name = 'yaml-merge'; Error = 'semantic-yaml-anchor-alias-merge-forbidden:.github/workflows/test.yml' },
    @{ Name = 'anchor-dot-name'; Error = 'semantic-yaml-anchor-alias-merge-forbidden:.github/workflows/test.yml' },
    @{ Name = 'anchor-punctuation'; Error = 'semantic-yaml-anchor-alias-merge-forbidden:.github/workflows/test.yml' },
    @{ Name = 'document-marker-inline'; Error = 'semantic-yaml-explicit-document-marker-forbidden:.github/workflows/test.yml' },
    @{ Name = 'document-marker-second'; Error = 'semantic-yaml-explicit-document-marker-forbidden:.github/workflows/test.yml' },
    @{ Name = 'quoted-uses'; ErrorLike = 'remote-uses-not-commit-pinned:' },
    @{ Name = 'local-action'; ErrorLike = 'local-action-not-allowlisted:' },
    @{ Name = 'local-reusable'; Error = 'workflow-not-allowlisted:.github/workflows/reusable.yaml' },
    @{ Name = 'remote-reusable'; ErrorLike = 'remote-uses-not-commit-pinned:' },
    @{ Name = 'docker-action'; ErrorLike = 'container-not-digest-pinned:' },
    @{ Name = 'containers'; ErrorLike = 'container-not-digest-pinned:' },
    @{ Name = 'delegated-script'; Entrypoints = @('scripts/build.ps1'); ErrorLike = 'diagnostic-operation-forbidden:' },
    @{ Name = 'delegated-shell'; Entrypoints = @('scripts/build.sh'); ErrorLike = 'delegated-script-parser-unavailable:' },
    @{ Name = 'constructed-url'; Entrypoints = @('scripts/check.ps1'); ErrorLike = 'diagnostic-url-forbidden:' },
    @{ Name = 'git-operation'; Entrypoints = @('scripts/check.ps1'); ErrorLike = 'diagnostic-operation-forbidden:' },
    @{ Name = 'unsupported-msystem'; ErrorLike = 'unsupported-msystem-before-setup:' },
    @{ Name = 'action-case'; ErrorLike = 'remote-uses-not-reviewed:' },
    @{ Name = 'dynamic-uses'; ErrorLike = 'uses-reference-invalid:' },
    @{ Name = 'local-docker'; ErrorLike = 'local-docker-action-forbidden:' },
    @{ Name = 'inline-shell'; ErrorLike = 'inline-shell-not-allowlisted:' },
    @{ Name = 'local-escape'; ErrorLike = 'local-path-invalid:' },
    @{ Name = 'command-chain'; ErrorLike = 'shell-command-chain-forbidden:' },
    @{ Name = 'command-subexpression'; ErrorLike = 'shell-arguments-forbidden:' },
    @{ Name = 'custom-shell'; Entrypoints = @('scripts/check.ps1'); ErrorLike = 'shell-template-not-allowlisted:' }
)

$approvedBackends = @(Get-Arm64ApprovedYamlBackends)
Assert-Arm64 (($approvedBackends -join ',') -ceq 'NodeJsYaml') `
    "the provenance-bound YAML backend is required: $($approvedBackends -join ',')"

$semanticBackend = Resolve-Arm64YamlBackend -Requested Auto
Assert-Arm64 ($semanticBackend -ceq 'NodeJsYaml') `
    "Auto did not select the pinned backend: $semanticBackend"
$nodeJsYamlIdentity = Resolve-Arm64NodeJsYamlIdentity
Assert-Arm64 ($null -ne $nodeJsYamlIdentity.NodePath -and
    (Test-Path -LiteralPath $nodeJsYamlIdentity.NodePath -PathType Leaf)) `
    'the approved Node.js executable is not available'
Assert-Arm64 ($null -ne $nodeJsYamlIdentity.ParserHelperPath -and
    (Test-Path -LiteralPath $nodeJsYamlIdentity.ParserHelperPath -PathType Leaf)) `
    'the approved parse-yaml.js helper is not available'
Assert-Arm64 ($null -ne $nodeJsYamlIdentity.JsYamlRoot -and
    (Test-Path -LiteralPath $nodeJsYamlIdentity.JsYamlRoot -PathType Container)) `
    'the approved js-yaml package root is not available'
$auditSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\audit-arm64-workflows.ps1') `
    -Raw
$validRoot = Join-Path $workflowFixtureRoot 'valid'
$validNodeJsDocument = ConvertFrom-Arm64YamlFile `
    -Path (Join-Path $validRoot '.github\workflows\test.yml') `
    -Backend NodeJsYaml
Assert-Arm64 ((Get-Arm64MapProperty -Map $validNodeJsDocument -Name 'name').Value -ceq
    'Valid diagnostic') 'the NodeJsYaml backend did not parse the valid fixture'
$validWorkflowPolicy = New-WorkflowFixturePolicy `
    -Root $validRoot `
    -Entrypoints @('scripts/check.ps1')
$validWorkflowResult = Test-Arm64WorkflowTree `
    -Root $validRoot `
    -Policy $validWorkflowPolicy `
    -Backend $semanticBackend `
    -SkipAuthoritativeSnapshot
Assert-Arm64 $validWorkflowResult.Allowed `
    "valid semantic workflow fixture failed: $($validWorkflowResult.Errors -join ', ')"
Assert-Arm64 ($validWorkflowResult.Parser -ceq 'NodeJsYaml') `
    'unexpected local semantic parser backend'


foreach ($case in $semanticCases) {
    $root = Join-Path $workflowFixtureRoot $case.Name
    $entrypoints = if (-not $case.ContainsKey('Entrypoints')) {
        @()
    }
    else {
        @($case['Entrypoints'])
    }
    $policy = New-WorkflowFixturePolicy -Root $root -Entrypoints $entrypoints
    $result = Test-Arm64WorkflowTree `
        -Root $root `
        -Policy $policy `
        -Backend $semanticBackend `
        -SkipAuthoritativeSnapshot
    Assert-Arm64 (-not $result.Allowed) "semantic bypass passed: $($case.Name)"
    if ($case.ContainsKey('Error')) {
        Assert-Arm64 ($result.Errors -ccontains $case['Error']) `
            "semantic bypass '$($case.Name)' missed '$($case['Error'])': $($result.Errors -join ', ')"
    }
    else {
        $errorLike = $case['ErrorLike']
        Assert-Arm64 (@($result.Errors | Where-Object {
                    $_.StartsWith($errorLike, [StringComparison]::Ordinal)
                }).Count -gt 0) `
            "semantic bypass '$($case.Name)' missed '$errorLike': $($result.Errors -join ', ')"
    }
}

$nearMissRoot = Join-Path $workflowFixtureRoot 'document-nonmarker'
$nearMissResult = Test-Arm64WorkflowTree `
    -Root $nearMissRoot `
    -Policy (New-WorkflowFixturePolicy -Root $nearMissRoot) `
    -Backend $semanticBackend `
    -SkipAuthoritativeSnapshot
foreach ($nearMissCode in @(
        'semantic-yaml-explicit-document-marker-forbidden:.github/workflows/test.yml',
        'semantic-yaml-anchor-alias-merge-forbidden:.github/workflows/test.yml',
        'semantic-yaml-parse-failed:.github/workflows/test.yml')) {
    Assert-Arm64 ($nearMissResult.Errors -cnotcontains $nearMissCode) `
        "near-miss document/anchor text was rejected as $nearMissCode"
}
Assert-Arm64 (@($nearMissResult.Errors | Where-Object {
            $_.StartsWith('remote-uses-not-commit-pinned:', [StringComparison]::Ordinal)
        }).Count -gt 0) 'near-miss fixture did not reach semantic uses analysis'

$utf8Strict = [Text.UTF8Encoding]::new($false, $true)
$utf8Plain = [Text.UTF8Encoding]::new($false)
$yamlProbeRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'arm64-yaml-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $yamlProbeRoot -Force)
function Get-Arm64YamlRejection {
    param(
        [Parameter(Mandatory)][byte[]]$Bytes,
        [Parameter(Mandatory)][string]$Name
    )

    $probePath = Join-Path $script:yamlProbeRoot $Name
    [IO.File]::WriteAllBytes($probePath, $Bytes)
    try {
        [void](Get-Arm64YamlText -Path $probePath)
        return 'accepted'
    }
    catch {
        return [string]$_.Exception.Message
    }
    finally {
        Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue
    }
}

try {
    $script:yamlProbeRoot = $yamlProbeRoot

    # Each deliberate rejection must surface its own distinct code so that one denial can
    # never stand in for another.
    $yamlCodeCases = @(
        @{ Name = 'byte-limit.yml'
            Bytes = $utf8Plain.GetBytes('a: ' + ('b' * 1048600))
            Code = 'semantic-yaml-byte-limit-exceeded' },
        @{ Name = 'bom-utf8.yml'
            Bytes = [byte[]](@(0xef, 0xbb, 0xbf) + $utf8Plain.GetBytes("a: 1`n"))
            Code = 'semantic-yaml-bom-forbidden' },
        @{ Name = 'bom-utf16le.yml'
            Bytes = [byte[]](@(0xff, 0xfe) + $utf8Plain.GetBytes("a: 1`n"))
            Code = 'semantic-yaml-bom-forbidden' },
        @{ Name = 'bom-utf16be.yml'
            Bytes = [byte[]](@(0xfe, 0xff) + $utf8Plain.GetBytes("a: 1`n"))
            Code = 'semantic-yaml-bom-forbidden' },
        @{ Name = 'utf8-invalid.yml'
            Bytes = [byte[]]@(0x61, 0x3a, 0x20, 0xc3, 0x28, 0x0a)
            Code = 'semantic-yaml-utf8-invalid' },
        @{ Name = 'nul.yml'
            Bytes = [byte[]]@(0x61, 0x3a, 0x20, 0x00, 0x0a)
            Code = 'semantic-yaml-nul-forbidden' },
        @{ Name = 'marker-bare.yml'
            Bytes = $utf8Plain.GetBytes("---`na: 1`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-first-inline.yml'
            Bytes = $utf8Plain.GetBytes("--- {a: 1}`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-second-inline.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n--- {b: 2}`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-second-block.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n--- b: 2`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-end-bare.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n...`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-end-inline.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n... trailing`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },

        @{ Name = 'marker-crlf.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`r`n---`r`nb: 2`r`n")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-lone-cr.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`r---`rb: 2")
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-next-line.yml'
            Bytes = $utf8Plain.GetBytes(
                'a: 1' + [char]0x85 + '---' + [char]0x85 + 'b: 2')
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-line-separator.yml'
            Bytes = $utf8Plain.GetBytes(
                'a: 1' + [char]0x2028 + '---' + [char]0x2028 + 'b: 2')
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'marker-paragraph-separator.yml'
            Bytes = $utf8Plain.GetBytes(
                'a: 1' + [char]0x2029 + '---' + [char]0x2029 + 'b: 2')
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'anchor-line-separator.yml'
            Bytes = $utf8Plain.GetBytes('a: 1' + [char]0x2028 + 'b: &k 1')
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-next-line.yml'
            Bytes = $utf8Plain.GetBytes('a: 1' + [char]0x85 + 'b: &.k 1')
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'alias-paragraph-separator.yml'
            Bytes = $utf8Plain.GetBytes('a: &k 1' + [char]0x2029 + 'b: *k')
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-dot.yml'
            Bytes = $utf8Plain.GetBytes("a: &.base 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'alias-dot.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`nb: *.base`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-ampersand.yml'
            Bytes = $utf8Plain.GetBytes("a: &&x 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'alias-ampersand.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`nb: *&x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-star.yml'
            Bytes = $utf8Plain.GetBytes("a: &*x 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-sequence.yml'
            Bytes = $utf8Plain.GetBytes("a:`n  - &@0/x! 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-flow.yml'
            Bytes = $utf8Plain.GetBytes("a: {b: &%x 1}`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-explicit-key.yml'
            Bytes = $utf8Plain.GetBytes("a:`n  ? &k 1`n  : 2`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'alias-explicit-key.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`nb:`n  ? *k`n  : 2`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-explicit-key-sequence.yml'
            Bytes = $utf8Plain.GetBytes("a:`n  - ? &k 1`n    : 2`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-after-tag.yml'
            Bytes = $utf8Plain.GetBytes("a: !!str &t 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-after-local-tag.yml'
            Bytes = $utf8Plain.GetBytes("a: !foo &t 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-before-tag.yml'
            Bytes = $utf8Plain.GetBytes("a: &t !!str 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-flow-explicit-key.yml'
            Bytes = $utf8Plain.GetBytes("a: {? &k : 1}`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-bare-entry-continuation-quote.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n  - abc`n    `"x`njobs:`n  - a`n  - &p b`n  - *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-bare-entry-continuation-bracket.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n  - abc`n    [x`njobs:`n  - a`n  - &p b`n  - *p`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-bare-entry-zero-indent.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n- abc`n  `"x`njobs:`n- a`n- &p b`n- *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-nested-sequence-continuation.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n  - - abc`n      [x`njobs:`n  - a`n  - &p b`n  - *p`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-explicit-key-continuation.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n  ? abc`n    [x`njobs:`n  - a`n  - &p b`n  - *p`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-paths-entry-continuation-workflow.yml'
            Bytes = $utf8Plain.GetBytes(
                "name: CI`non:`n  push:`n    paths:`n      - src/**`n        `"extra`n" +
                "jobs:`n  build:`n    runs-on: ubuntu-latest`n    steps:`n" +
                "      - uses: actions/checkout@v4`n      - &poison`n        name: setup`n" +
                "        run: echo attacker`n      - *poison`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-blank-line-continuation-quote.yml'
            Bytes = $utf8Plain.GetBytes(
                "name: CI`n`n  `"x`non: push`njobs:`n  build:`n    runs-on: ubuntu-latest`n" +
                "    steps:`n      - uses: actions/checkout@v4`n      - &poison`n" +
                "        run: echo attacker`n      - *poison`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-blank-line-continuation-bracket.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: abc`n`n  [x`njobs:`n- a`n- &p b`n- *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-whitespace-line-continuation.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: abc`n   `n  [x`njobs:`n- a`n- &p b`n- *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-continuation-bracket.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nname: build`n  [x`nlist:`n  - a`n  - &p b`n  - *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-continuation-brace.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nname: build`n  {x`nlist:`n  - a`n  - &p b`n  - *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-continuation-quote.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nname: build`n  `"x`nlist:`n  - a`n  - &p b`n  - *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-continuation-apostrophe.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nname: build`n  'x`nlist:`n  - a`n  - &p b`n  - *p")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-continuation-workflow.yml'
            Bytes = $utf8Plain.GetBytes(
                "name: build`n  [wip`non: push`njobs:`n  build:`n    runs-on: ubuntu-latest`n" +
                "    steps:`n      - uses: actions/checkout@v4`n      - &poison`n" +
                "        name: setup`n        run: echo attacker`n      - *poison`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-sequence-sibling.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nlist:`n  - a`n  - &x b`n  - *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-top-level-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`n&x k: v`njobs:`n  b: c`n  *x : d`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-sequence-flow-sibling.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nlist:`n  - a`n  - [b, &x c]`n  - [d, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-sequence-amplification.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nlist:`n  - seed`n  - &a [1,1,1]`n  - &b [*a,*a,*a]`n" +
                "  - &c [*b,*b,*b]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-mapping-sibling.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nm:`n  a: 1`n  b: &x g`n  c: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-after-block-scalar-sibling.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`na: |`n  body`nlist:`n  - x`n  - &y g`n  - *y`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-comma-quote-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc, `"def: &x g`nhij, `"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-comma-quote-tight.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc,`"def: &x g`nhij,`"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-bracket-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc[ `"def: &x g`nhij[ `"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-brace-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc{ `"def: &x g`nhij{ `"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-comma-quote-sequence.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nsteps:`n  - k, `"v: &x g`n  - k, `"w: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-plain-comma-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nb, `"z: &x {A: 1}`nq, `"z2: {<<: *x}`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-after-block-scalar-exit.yml'
            Bytes = $utf8Plain.GetBytes("on: push`na: |`n  body`nb, `"c: &x g`nd, `"e: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-comma-quote-workflow.yml'
            Bytes = $utf8Plain.GetBytes(
                "name: demo`non: push`njobs:`n  build:`n    runs-on: ubuntu-latest`n" +
                "    steps:`n      - shell, `"a: &poison`n          run: echo x`n" +
                "        name: first`n      - shell, `"b: *poison`n        name: second`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc- `"def: &x g`nhij- `"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-question-quote-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nok? `"y: &x g`nno? `"z: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-apostrophe-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc- 'def: &x g`nhij- 'klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-tab-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nabc-`t`"def: &x g`nhij-`t`"klm: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-sequence.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nsteps:`n  - k- `"v: &x g`n  - k- `"w: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-flow.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: [abc- `"def, &x g]`nj: [hij- `"klm, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-plain-dash-quote-flow.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nk: [abc- `"def, &x {a: 1}]`nj: [hij- `"klm, <<: *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-nested-flow.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: {p: [q- `"r, &x g]}`nj: {p: [s- `"t, *x]}`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-continuation.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nk: [abc-`n  `"def, &x g]`nj: [hij-`n  `"klm, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote-workflow.yml'
            Bytes = $utf8Plain.GetBytes(
                "name: demo`non: push`njobs:`n  build:`n    runs-on: ubuntu-latest`n" +
                "    steps:`n      - shell- `"a: &poison`n          run: echo x`n" +
                "        name: first`n      - shell- `"b: *poison`n        name: second`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-alias-expansion.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nq- `"z: &a [x,x,x]`nr- `"z: &b [*a,*a,*a]`ns- `"z: &c [*b,*b,*b]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },



        @{ Name = 'anchor-flow-continuation-sequence.yml'
            Bytes = $utf8Plain.GetBytes("on: push`na: [`n  1,`n  &x 2`n]`nb: [`n  *x`n]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-fake-header-comma.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`njobs:`n  b:`n    steps:`n      - run: echo hi, |`n" +
                "        env: &x`n          A: 1`n        with:`n          <<: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-fake-header-bracket.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`njobs:`n  b:`n    steps:`n      - run: echo [ |`n" +
                "        env: &x`n          A: 1`n        with: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-fake-header-chomp.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`njobs:`n  b:`n    steps:`n      - run: echo a, |-`n" +
                "        env: &x`n          A: 1`n        with: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-dash-quote.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: pull_request`njobs:`n  build:`n" +
                "    runs-on: [self-`"hosted, &poison ubuntu-latest]`n    steps:`n" +
                "      - uses: [actions-`"checkout, *poison]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-colon-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: [a:`"b, &x g]`nj: [c:`"d, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-continuation-quote.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`nk: [abc`n  `"def, &x g]`nj: [hij`n  `"klm, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-explicit-key-sequence-order.yml'
            Bytes = $utf8Plain.GetBytes("on: push`na:`n  ? - &x v`n  : 1`nb:`n  ? - *x`n  : 2`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },


        @{ Name = 'anchor-fake-folded-header.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`njobs:`n  b:`n    steps:`n      - name: pipe >`n" +
                "        env: &x`n          A: 1`n        with:`n          <<: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-fake-literal-header.yml'
            Bytes = $utf8Plain.GetBytes(
                "on: push`njobs:`n  b:`n    steps:`n      - run: echo a |`n" +
                "        env: &x`n          A: 1`n        with: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-colon-key.yml'
            Bytes = $utf8Plain.GetBytes("on: push`na:b: &x hidden`nc:d: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-apostrophe.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: [don't, &x bar]`nj: [it's, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-plain-double-quote.yml'
            Bytes = $utf8Plain.GetBytes("on: push`nk: [a`"b, &x bar]`nj: [c`"d, *x]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-hash-key.yml'
            Bytes = $utf8Plain.GetBytes("a#b: &x 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'alias-hash-key.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`nc#d: *x`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-comma-key.yml'
            Bytes = $utf8Plain.GetBytes("a,b: &x 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-quoted-colon-key.yml'
            Bytes = $utf8Plain.GetBytes("`"a:b`": &x 1`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'anchor-multiline-flow.yml'
            Bytes = $utf8Plain.GetBytes("a: [`n  &x 1,`n  *x`n]`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-key.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n<<: *base`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-key-plain.yml'
            Bytes = $utf8Plain.GetBytes("a: 1`n<<: b`n")
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' }
    )
    foreach ($yamlCase in $yamlCodeCases) {
        $observed = Get-Arm64YamlRejection -Bytes $yamlCase.Bytes -Name $yamlCase.Name
        Assert-Arm64 ($observed -ceq $yamlCase.Code) `
            "YAML case '$($yamlCase.Name)' produced '$observed' instead of '$($yamlCase.Code)'"
    }

    # Near-miss text must stay admissible so the gate cannot be satisfied by prefix accidents.
    $yamlAcceptCases = @(
        @{ Name = 'nonmarker-prefix.yml'; Text = "---not-a-marker: 1`n" },
        # The pinned backend treats each of these as ordinary scalar content, not as a
        # document marker or a node property, so the gate must admit them too.
        @{ Name = 'indented-dashes.yml'; Text = "a: 1`n  --- b`n" },
        @{ Name = 'flow-plain-colon-key.yml'; Text = "on: push`nk: {a:&x 1}`nj: {b:*x}`n" },
        @{ Name = 'flow-plain-question-key.yml'; Text = "on: push`nk: {?&x : 1}`n" },
        @{ Name = 'flow-continuation-plain-key.yml'
            Text = "on: push`na: {`n  b:&x 1`n}`nc: {`n  d:*x`n}`n" },
        @{ Name = 'flow-continuation-question-key.yml'
            Text = "on: push`na: {`n  ?&x : 1`n}`n" },
        @{ Name = 'flow-nested-plain-key.yml'
            Text = "on: push`na: {b: {`n  c:&x 1`n}}`nd: {e: {`n  f:*x`n}}`n" },
        @{ Name = 'nonmarker-dotted-key.yml'; Text = "...key: 1`n" },
        @{ Name = 'shell-and.yml'; Text = "jobs:`n  run: cmd1 && cmd2`n" },
        @{ Name = 'shell-glob.yml'; Text = "jobs:`n  run: cp *.txt out/`n" },
        @{ Name = 'quoted-glob.yml'; Text = "paths:`n  - `".github/workflows/*.yml`"`n" },
        @{ Name = 'block-scalar-and.yml'; Text = "run: |`n  a && b`n  c *.txt`n" },
        @{ Name = 'folded-scalar-and.yml'; Text = "runs-on: >-`n  x`n    && y`n    || z`n" },
        @{ Name = 'comment-anchor.yml'; Text = "a: 1 # &anchor *alias`n" },
        @{ Name = 'question-in-run.yml'; Text = "jobs:`n  run: is this ok? *.txt`n" },
        @{ Name = 'bang-in-run.yml'; Text = "jobs:`n  run: echo !important *.txt`n" },
        @{ Name = 'dash-in-run.yml'; Text = "jobs:`n  run: cmd --flag && other`n" },
        @{ Name = 'apostrophe-run.yml'; Text = "jobs:`n  run: don't stop && go`n" },
        @{ Name = 'quoted-name.yml'; Text = "name: `"Build the thing`"`n" },
        @{ Name = 'four-dash-key.yml'; Text = "a: 1`n----:`n" },
        @{ Name = 'four-dot-key.yml'; Text = "a: 1`n....:`n" },
        @{ Name = 'quoted-merge-text.yml'; Text = "- run: echo `"a <<: b`"`n" },
        @{ Name = 'real-folded-header.yml'
            Text = "runs-on: >-`n  x`n    && y`n    || z`nsteps: 1`n" },
        @{ Name = 'real-literal-header.yml'
            Text = "jobs:`n  a:`n    run: |`n      echo x && y`n  b: 1`n" },
        @{ Name = 'quoted-key.yml'; Text = "on:`n  `"push`": null`n" },
        @{ Name = 'sequence-quoted.yml'; Text = "steps:`n  - `"a`"`n  - `"b`"`n" },
        @{ Name = 'flow-sequence.yml'; Text = "runs-on: [self-hosted, linux]`n" },
        @{ Name = 'expression-and.yml'
            Text = "env:`n  F: `${{ (a == 'x') && 'y' || 'z' }}`n" },
        @{ Name = 'expression-glob.yml'
            Text = "env:`n  P: `${{ github.workspace }}/x/*.zst`n" },
        @{ Name = 'sequence-quoted-glob.yml'
            Text = "paths:`n  - `"a/**`"`n  - `"b/*.yml`"`n" },
        @{ Name = 'sequence-quoted-comma-glob.yml'; Text = "paths:`n  - `"*.md, *.txt`"`n" },
        @{ Name = 'sequence-quoted-brace-glob.yml'; Text = "paths:`n  - `"{*.md,*.txt}`"`n" },
        @{ Name = 'sequence-quoted-brace-args.yml'
            Text = "args:`n  - `"rm -rf build/{*.o,*.a}`"`n" },
        @{ Name = 'sequence-quoted-comma-args.yml'; Text = "args:`n  - `"cp a.txt,*.md d/`"`n" },
        @{ Name = 'run-comma-quote-and.yml'; Text = "run: echo a, `"b`" && ls`n" },
        @{ Name = 'cron-quoted.yml'
            Text = "on:`n  schedule:`n    - cron: `"30 5,17 * * *`"`n" },
        @{ Name = 'matrix-flow-quoted.yml'; Text = "os: [`"ubuntu-latest`",`"windows-latest`"]`n" },
        @{ Name = 'name-quoted-ampersand.yml'
            Text = "steps:`n  - name: `"Build, test & package`"`n" },
        @{ Name = 'path-quoted-expression.yml'
            Text = "path: `"`${{ github.workspace }}/dist/*.zst`"`n" },
        @{ Name = 'run-git-log-format.yml'
            Text = "run: git log --pretty=format:`"%h, %s`" && echo ok`n" },
        @{ Name = 'run-find-quoted.yml'
            Text = "run: find . -name `"*.log`" -delete && echo done`n" },
        @{ Name = 'run-cp-brace.yml'; Text = "run: cp -r src/{a,b} dist/ && ls dist/*`n" },
        @{ Name = 'run-jq-quoted.yml'; Text = "run: jq -r '.a[0], .b' f.json && echo ok`n" },
        @{ Name = 'sequence-brace-globstar.yml'; Text = "paths:`n  - `"**/{docs,ex}/**`"`n" },
        @{ Name = 'quoted-sequence-nested-glob.yml'
            Text = "on:`n  push:`n    paths:`n      - `"a`"`n      - `"b: *.md`"`n" },
        @{ Name = 'quoted-key-with-ampersand.yml'; Text = "a: 1`n`"b: &c`": 2`n" },

        @{ Name = 'merge-text-in-comment.yml'
            Text = "# note: <<: merge keys are banned`na: 1`n" },
        @{ Name = 'merge-text-in-block-scalar.yml'
            Text = "- run: |`n    echo `"x <<: y`"`n" },
        @{ Name = 'merge-text-as-plain-value.yml'; Text = "d: <<`n" },
        @{ Name = 'tagged-scalar.yml'; Text = "d: !!str value`n" },
        @{ Name = 'plain-continuation-ampersand.yml'; Text = "name: a`n  && b`non: push`n" },
        @{ Name = 'plain-continuation-glob.yml'; Text = "name: a`n  *.txt`non: push`n" },
        @{ Name = 'quoted-scalar-blank-line.yml'; Text = "name: `"a`n`n  b`"`non: push`n" },
        @{ Name = 'step-sibling-after-comment.yml'
            Text = "steps:`n  - name: x   # comment`n    run: y`n" },
        @{ Name = 'nested-job-steps.yml'
            Text = "jobs:`n  build:`n    runs-on: ubuntu-latest`n    steps:`n" +
            "      - uses: a/b@c`n      - run: echo hi`n" },
        @{ Name = 'blank-line-between-steps.yml'
            Text = "steps:`n  - name: A`n    run: x`n`n  - name: B`n    run: z`n" },
        @{ Name = 'sequence-entry-continuation.yml'
            Text = "paths:`n  - src/**`n    more`non: push`n" }
    )
    foreach ($yamlCase in $yamlAcceptCases) {
        $observed = Get-Arm64YamlRejection `
            -Bytes $utf8Plain.GetBytes($yamlCase.Text) `
            -Name $yamlCase.Name
        Assert-Arm64 ($observed -ceq 'accepted') `
            "near-miss YAML '$($yamlCase.Name)' was rejected as '$observed'"
    }

    # A genuinely unexpected backend fault stays generic and never echoes candidate text.
    $backendFailure = 'accepted'
    try {
        [void](Invoke-Arm64YamlBackend -Text "a: [1, 2`n" -Backend $semanticBackend)
    }
    catch {
        $backendFailure = [string]$_.Exception.Message
    }
    Assert-Arm64 ($backendFailure -ceq 'semantic-yaml-backend-parse-failed') `
        "malformed backend input produced '$backendFailure'"

    $syntheticError = [Management.Automation.ErrorRecord]::new(
        [Exception]::new(
            'curl https' + [char]58 + '//example.invalid/payload leaked from the backend'
        ),
        'synthetic',
        [Management.Automation.ErrorCategory]::NotSpecified,
        $null
    )
    $mappedGeneric = Resolve-Arm64YamlErrorCode `
        -ErrorRecord $syntheticError `
        -Relative '.github/workflows/test.yml'
    Assert-Arm64 ($mappedGeneric -ceq 'semantic-yaml-parse-failed:.github/workflows/test.yml') `
        'unexpected backend failures are not reduced to the stable generic code'
    Assert-Arm64 (-not $mappedGeneric.Contains('example.invalid', [StringComparison]::Ordinal)) `
        'unexpected backend failure text leaked into the audit error stream'
    $rawSelectionError = Resolve-Arm64ParserSelectionErrorCode `
        -ErrorRecord ([Management.Automation.ErrorRecord]::new(
            [Exception]::new(
                "The property 'Version' cannot be found on this object. Secret path follows."
            ),
            'synthetic-selection',
            [Management.Automation.ErrorCategory]::NotSpecified,
            $null))
    Assert-Arm64 ($rawSelectionError -ceq 'semantic-parser-unavailable') `
        "raw parser-selection text escaped as '$rawSelectionError'"
    $rawSnapshotError = Resolve-Arm64AuthoritativeSnapshotErrorCode `
        -ErrorRecord ([Management.Automation.ErrorRecord]::new(
            [Exception]::new(
                "The property 'Version' cannot be found. Secret path follows."
            ),
            'synthetic-snapshot',
            [Management.Automation.ErrorCategory]::NotSpecified,
            $null))
    Assert-Arm64 ($rawSnapshotError -ceq 'authoritative-snapshot-invalid') `
        "raw authoritative-snapshot text escaped as '$rawSnapshotError'"
    foreach ($deliberateCode in @(
            'semantic-yaml-bom-forbidden',
            'semantic-yaml-nul-forbidden',
            'semantic-yaml-byte-limit-exceeded',
            'semantic-yaml-utf8-invalid',
            'semantic-yaml-explicit-document-marker-forbidden',
            'semantic-yaml-anchor-alias-merge-forbidden',
            'semantic-yaml-backend-parse-failed',
            'semantic-parser-unavailable',
            'semantic-parser-provenance-unapproved',
            'semantic-parser-containment-unavailable')) {
        $mapped = Resolve-Arm64YamlErrorCode `
            -ErrorRecord ([Management.Automation.ErrorRecord]::new(
                [Exception]::new($deliberateCode),
                'deliberate',
                [Management.Automation.ErrorCategory]::NotSpecified,
                $null)) `
            -Relative '.github/workflows/test.yml'
        Assert-Arm64 ($mapped -ceq "${deliberateCode}:.github/workflows/test.yml") `
            "deliberate code '$deliberateCode' was not propagated structurally"
    }
    $mappedPrefixed = Resolve-Arm64YamlErrorCode `
        -ErrorRecord ([Management.Automation.ErrorRecord]::new(
            [Exception]::new('semantic-parser-differential:C:\candidate\test.yml'),
            'deliberate',
            [Management.Automation.ErrorCategory]::NotSpecified,
            $null)) `
        -Relative '.github/workflows/test.yml'
    Assert-Arm64 ($mappedPrefixed -ceq
        'semantic-parser-differential:.github/workflows/test.yml') `
        'differential rejection did not keep its structural code and relative path'

    # The backend parses the exact validated bytes, so mutating or re-reading the source
    # path after validation cannot change what the parser sees.
    $pwshPath = (Get-Process -Id $PID).Path
    $mutationPath = Join-Path $yamlProbeRoot 'mutation.yml'
    [IO.File]::WriteAllBytes($mutationPath, $utf8Plain.GetBytes("name: original`n"))
    $validatedText = Get-Arm64YamlText -Path $mutationPath
    [IO.File]::WriteAllBytes($mutationPath, $utf8Plain.GetBytes("name: mutated-after-validation`n"))
    $echoResult = Invoke-Arm64BoundedProcess `
        -FilePath $pwshPath `
        -ArgumentList @(
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            '$i=[Console]::OpenStandardInput();$o=[Console]::OpenStandardOutput();' +
            '$i.CopyTo($o);$o.Flush()'
        ) `
        -InputBytes $utf8Strict.GetBytes($validatedText)
    Assert-Arm64 ($echoResult.ExitCode -eq 0) 'bounded parser transport did not exit cleanly'
    Assert-Arm64 ($echoResult.Containment -ceq 'WindowsJob') `
        'bounded parser transport is not assigned to a Windows Job Object'
    Assert-Arm64 ($echoResult.ProcessMemoryLimitBytes -eq 268435456 -and
        $echoResult.JobMemoryLimitBytes -eq 402653184) `
        'bounded parser transport does not expose the enforced memory caps'
    $echoedText = $utf8Strict.GetString($echoResult.OutputBytes)
    Assert-Arm64 ($echoedText -ceq "name: original`n") `
        'bounded parser input was re-read from the mutated path instead of validated bytes'
    Assert-Arm64 ((Get-Content -LiteralPath $mutationPath -Raw) -cnotmatch 'original') `
        'path mutation probe did not actually change the file on disk'
    Remove-Item -LiteralPath $mutationPath -Force -ErrorAction SilentlyContinue

    $boundedCases = @(
        @{ Name = 'input-cap'
            Arguments = @('-NoProfile', '-NonInteractive', '-Command', 'exit 0')
            Bytes = [byte[]]::new(4096)
            Limits = @{ MaximumInputBytes = 1024 }
            Code = 'semantic-parser-input-limit-exceeded' },
        @{ Name = 'output-cap'
            Arguments = @('-NoProfile', '-NonInteractive', '-Command',
                '$o=[Console]::OpenStandardOutput();$b=[byte[]]::new(262144);' +
                '$o.Write($b,0,$b.Length);$o.Flush()')
            Bytes = [byte[]]::new(0)
            Limits = @{ MaximumOutputBytes = 1024 }
            Code = 'semantic-parser-output-limit-exceeded' },
        @{ Name = 'error-cap'
            Arguments = @('-NoProfile', '-NonInteractive', '-Command',
                '$e=[Console]::OpenStandardError();$b=[byte[]]::new(262144);' +
                '$e.Write($b,0,$b.Length);$e.Flush()')
            Bytes = [byte[]]::new(0)
            Limits = @{ MaximumErrorBytes = 1024 }
            Code = 'semantic-parser-output-limit-exceeded' }
    )
    foreach ($boundedCase in $boundedCases) {
        $boundedOutcome = 'completed'
        try {
            $arguments = @{
                FilePath = $pwshPath
                ArgumentList = $boundedCase.Arguments
                InputBytes = $boundedCase.Bytes
            }
            foreach ($limitName in $boundedCase.Limits.Keys) {
                $arguments[$limitName] = $boundedCase.Limits[$limitName]
            }
            [void](Invoke-Arm64BoundedProcess @arguments)
        }
        catch {
            $boundedOutcome = [string]$_.Exception.Message
        }
        Assert-Arm64 ($boundedOutcome -ceq $boundedCase.Code) `
            "bounded process case '$($boundedCase.Name)' produced '$boundedOutcome'"
    }

    $exitResult = Invoke-Arm64BoundedProcess `
        -FilePath $pwshPath `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', 'exit 7') `
        -InputBytes ([byte[]]::new(0))
    Assert-Arm64 ($exitResult.ExitCode -eq 7) 'bounded process exit status was not observed'

    $memoryResult = Invoke-Arm64BoundedProcess `
        -FilePath $pwshPath `
        -ArgumentList @(
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            '$ErrorActionPreference=''Stop'';' +
            '$b=[GC]::AllocateUninitializedArray[byte](314572800,$false);' +
            'for($i=0;$i -lt $b.Length;$i+=4096){$b[$i]=1};' +
            '[Console]::Out.Write($b.Length)'
        ) `
        -InputBytes ([byte[]]::new(0)) `
        -TimeoutMilliseconds 30000
    Assert-Arm64 ($memoryResult.ExitCode -ne 0) `
        'the child exceeded its process memory limit and still exited successfully'
    Assert-Arm64 ($utf8Strict.GetString($memoryResult.OutputBytes) -cne '314572800') `
        'the child completed an allocation larger than its enforced process memory cap'

    $descendantRoot = Join-Path $yamlProbeRoot 'descendant'
    [void](New-Item -ItemType Directory -Path $descendantRoot)
    $descendantSentinel = Join-Path $descendantRoot 'escaped.txt'
    $escapedSentinel = $descendantSentinel.Replace("'", "''")
    $escapedPwsh = $pwshPath.Replace("'", "''")
    $descendantCommand =
        "Start-Sleep -Seconds 2;[IO.File]::WriteAllText('$escapedSentinel','escaped')"
    $parentCommand =
        "`$p=Start-Process -FilePath '$escapedPwsh' -ArgumentList @(" +
        "'-NoProfile','-NonInteractive','-Command','" +
        $descendantCommand.Replace("'", "''") +
        "') -WindowStyle Hidden -PassThru;[Console]::Out.Write(`$p.Id)"
    $parentResult = Invoke-Arm64BoundedProcess `
        -FilePath $pwshPath `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $parentCommand) `
        -InputBytes ([byte[]]::new(0)) `
        -TimeoutMilliseconds 10000
    Assert-Arm64 ($parentResult.ExitCode -eq 0) `
        'the descendant containment probe parent did not exit cleanly'
    Start-Sleep -Seconds 3
    Assert-Arm64 (-not (Test-Path -LiteralPath $descendantSentinel)) `
        'a detached descendant survived the parser Job Object'
}
finally {
    Remove-Item -LiteralPath $yamlProbeRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Assert-Arm64 (-not (Test-Path -LiteralPath $yamlProbeRoot)) `
    'YAML probe scratch directory left residue behind'

# --- Token-layer gate: nothing forbidden may ever reach an object backend ---------------
$forbiddenTokenCases = [Collections.Generic.List[hashtable]]::new()
foreach ($base in @(
        @{ Name = 'anchor'; Text = "a: &x 1`nb: *x`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'punctuation-anchor'; Text = "a: &.base 1`nb: *.base`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'ampersand-anchor'; Text = "a: &&x 1`nb: *&x`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'flow-alias'; Text = "a: &x 1`nb: [*x]`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-key'; Text = "a: 1`n<<: *b`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'merge-key-plain'; Text = "a: 1`n<<: b`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'tagged-merge-key-short'
            Text = "!!merge <<: {permissions: write}`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'tagged-merge-key-verbatim'
            Text = "!<tag:yaml.org,2002:merge> <<: {permissions: write}`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'document-marker'; Text = "a: 1`n--- {b: 2}`n"
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'document-end'; Text = "a: 1`n...`n"
            Code = 'semantic-yaml-explicit-document-marker-forbidden' },
        @{ Name = 'alias-amplification'
            Text = "a: &a [1,1,1,1,1,1,1,1,1]`nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]`n" +
            "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]`nd: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c]`n" +
            "e: &e [*d,*d,*d,*d,*d,*d,*d,*d,*d]`nf: [*e,*e,*e,*e,*e,*e,*e,*e,*e]`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' },
        @{ Name = 'cloaked-amplification'
            Text = "on: push`nq:`n  bcd`n  `"x`na: &a [1,1,1,1,1,1,1,1,1]`n" +
            "b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]`nc: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]`n" +
            "d: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c]`ne: [*d,*d,*d,*d,*d,*d,*d,*d,*d]`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden' })) {
    [void]$forbiddenTokenCases.Add($base)
}
# The eight cloak families from the independent differential audit. Each hides a real anchor
# and alias behind a plain-scalar continuation that a hand-rolled lexer mis-tracked.
foreach ($cloak in @(
        @{ Name = 'own-line-double-quote'; Head = "a:`n  bcd`n  `"x`n" },
        @{ Name = 'own-line-single-quote'; Head = "a:`n  bcd`n  'x`n" },
        @{ Name = 'equal-indent'; Head = "a: bcd`n  `"x`n" },
        @{ Name = 'deep-indent'; Head = "a:`n  bcd`n      `"x`n" },
        @{ Name = 'nested'; Head = "m:`n  a:`n    bcd`n    `"x`n" },
        @{ Name = 'blank-between'; Head = "a: bcd`n`n  `"x`n" },
        @{ Name = 'blank-deep'; Head = "a:`n  bcd`n`n     `"x`n" },
        @{ Name = 'sequence-entry'; Head = "a:`n  - bcd`n    `"x`n" })) {
    [void]$forbiddenTokenCases.Add(@{
            Name = "cloak-$($cloak.Name)"
            Text = "on: push`n$($cloak.Head)j:`n  - p`n  - &z q`n  - *z`n"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden'
        })
}
foreach ($separator in @("`n", "`r`n", "`r", [string][char]0x85, [string][char]0x2028,
        [string][char]0x2029)) {
    [void]$forbiddenTokenCases.Add(@{
            Name = 'separator-marker'
            Text = "a: 1$separator---${separator}b: 2"
            Code = 'semantic-yaml-explicit-document-marker-forbidden'
        })
    [void]$forbiddenTokenCases.Add(@{
            Name = 'separator-anchor'
            Text = "a: &x 1${separator}b: *x"
            Code = 'semantic-yaml-anchor-alias-merge-forbidden'
        })
}

$tokenProbeRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'arm64-token-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $tokenProbeRoot -Force)
try {
    foreach ($tokenCase in $forbiddenTokenCases) {
        $observed = 'accepted'
        try {
            [void](Assert-Arm64YamlTokenPolicy -Text $tokenCase.Text)
        }
        catch {
            $observed = [string]$_.Exception.Message
        }
        Assert-Arm64 ($observed -ceq $tokenCase.Code) `
            "token case '$($tokenCase.Name)' produced '$observed' not '$($tokenCase.Code)'"

        $probePath = Join-Path $tokenProbeRoot 'candidate.yml'
        [IO.File]::WriteAllBytes($probePath, $utf8Plain.GetBytes($tokenCase.Text))
        $script:arm64BackendInvocationCount = 0
        $routed = 'accepted'
        try {
            [void](ConvertFrom-Arm64YamlFile -Path $probePath -Backend $semanticBackend)
        }
        catch {
            $routed = [string]$_.Exception.Message
        }
        Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue
        Assert-Arm64 ($routed -ceq $tokenCase.Code) `
            "routed token case '$($tokenCase.Name)' produced '$routed'"
        Assert-Arm64 ($script:arm64BackendInvocationCount -eq 0) `
            "token case '$($tokenCase.Name)' reached a backend $($script:arm64BackendInvocationCount) time(s)"
    }

    # A permitted document must still reach exactly one backend, so the counter is meaningful.
    $permittedPath = Join-Path $tokenProbeRoot 'permitted.yml'
    [IO.File]::WriteAllBytes(
        $permittedPath,
        $utf8Plain.GetBytes("on: push`njobs:`n  build:`n    runs-on: ubuntu-latest`n")
    )
    $script:arm64BackendInvocationCount = 0
    $permitted = ConvertFrom-Arm64YamlFile -Path $permittedPath -Backend $semanticBackend
    Assert-Arm64 ($script:arm64BackendInvocationCount -ge 1) `
        'a permitted document never reached an object backend'
    Assert-Arm64 ((Get-Arm64MapProperty -Map $permitted -Name 'on').Value -ceq 'push') `
        'the bounded backend did not return a usable document'
    Remove-Item -LiteralPath $permittedPath -Force -ErrorAction SilentlyContinue

    # Duplicate policy keys must fail in the first strict backend; the backend remains required
    # for every valid document so strict duplicate-key detection remains enforced.
    $duplicateKeyPath = Join-Path $tokenProbeRoot 'duplicate-key.yml'
    [IO.File]::WriteAllBytes(
        $duplicateKeyPath,
        $utf8Plain.GetBytes("permissions: read-all`npermissions: write-all`n")
    )
    $script:arm64BackendInvocationCount = 0
    $duplicateKeyOutcome = 'accepted'
    try {
        [void](ConvertFrom-Arm64YamlFile `
                -Path $duplicateKeyPath `
                -Backend $semanticBackend)
    }
    catch {
        $duplicateKeyOutcome = [string]$_.Exception.Message
    }
    Assert-Arm64 ($duplicateKeyOutcome -ceq 'semantic-yaml-backend-parse-failed') `
        "duplicate YAML mapping keys produced '$duplicateKeyOutcome'"
    Assert-Arm64 ($script:arm64BackendInvocationCount -eq 1) `
        'duplicate YAML mapping keys were not stopped by the first object backend'
    Remove-Item -LiteralPath $duplicateKeyPath -Force -ErrorAction SilentlyContinue
}
finally {
    Remove-Item -LiteralPath $tokenProbeRoot -Recurse -Force -ErrorAction SilentlyContinue
}

# An absent token layer is not an excuse to admit anything.
$scannerlessRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'arm64-noscanner-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $scannerlessRoot -Force)
$savedNodeExec2 = [Environment]::GetEnvironmentVariable('ARM64_NODE_EXECUTABLE')
try {
    $auditScriptPath = Join-Path $repoRoot '.github\scripts\audit-arm64-workflows.ps1'
    [Environment]::SetEnvironmentVariable('ARM64_NODE_EXECUTABLE', 'C:\nonexistent\node.exe')
    $scannerlessCommand =
    ". '$auditScriptPath'; " +
    "Reset-Arm64RuntimeIdentityCache; " +
    "try { [void](Assert-Arm64YamlTokenPolicy -Text 'a: 1'); [Console]::Out.Write('accepted') } " +
    "catch { [Console]::Out.Write([string]`$_.Exception.Message) }"
    $scannerlessResult = Invoke-Arm64BoundedProcess `
        -FilePath (Get-Process -Id $PID).Path `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $scannerlessCommand) `
        -InputBytes ([byte[]]::new(0))
    $scannerlessText = $utf8Strict.GetString($scannerlessResult.OutputBytes)
    Assert-Arm64 ($scannerlessText.Contains('semantic-yaml-token-scanner-unavailable',
            [StringComparison]::Ordinal)) `
        "an absent token scanner did not fail closed: $scannerlessText"
}
finally {
    [Environment]::SetEnvironmentVariable('ARM64_NODE_EXECUTABLE', $savedNodeExec2)
    Remove-Item -LiteralPath $scannerlessRoot -Recurse -Force -ErrorAction SilentlyContinue
}

# Runtime provenance: Node.js executable and js-yaml package tree are hash-bound.
$provenanceRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'arm64-provenance-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $provenanceRoot)
$savedNodeExecutable = [Environment]::GetEnvironmentVariable('ARM64_NODE_EXECUTABLE')
try {
    Reset-Arm64RuntimeIdentityCache
    $boundIdentity = Resolve-Arm64NodeJsYamlIdentity
    Assert-Arm64 (Test-Arm64RuntimeFileWriteLocked `
            -Path $boundIdentity.ParserHelperPath) `
        'the approved parse-yaml.js can be replaced after approval'
    $jsYamlFileCount = @(Get-ChildItem `
            -LiteralPath $boundIdentity.JsYamlRoot `
            -File `
            -Recurse `
            -Force).Count + 1
    Assert-Arm64 ($boundIdentity.Locks.Count -eq $jsYamlFileCount) `
        'the complete pinned js-yaml package tree is not persistently locked'
    Assert-Arm64 ([object]::ReferenceEquals(
            $boundIdentity,
            (Resolve-Arm64NodeJsYamlIdentity)
        )) 'the cached NodeJsYaml identity was not revalidated in place'

    $provenanceAttackPath = Join-Path $provenanceRoot 'attack.yml'
    [IO.File]::WriteAllText(
        $provenanceAttackPath,
        "a: &x 1`nb: *x`n",
        $utf8Plain
    )
    $script:arm64BackendInvocationCount = 0
    $provenanceAttack = 'accepted'
    try {
        [void](ConvertFrom-Arm64YamlFile `
                -Path $provenanceAttackPath `
                -Backend NodeJsYaml)
    }
    catch {
        $provenanceAttack = [string]$_.Exception.Message
    }
    Assert-Arm64 ($provenanceAttack -ceq
        'semantic-yaml-anchor-alias-merge-forbidden') `
        "the provenance attack changed token admission to '$provenanceAttack'"
    Assert-Arm64 ($script:arm64BackendInvocationCount -eq 0) `
        'the provenance attack reached an object backend'

    $fakeNode = Join-Path $provenanceRoot 'bin\node.exe'
    [void](New-Item -ItemType Directory -Path (Join-Path $provenanceRoot 'bin') -Force)
    Copy-Item -LiteralPath (Get-Process -Id $PID).Path -Destination $fakeNode
    [Environment]::SetEnvironmentVariable('ARM64_NODE_EXECUTABLE', $fakeNode)
    Reset-Arm64RuntimeIdentityCache
    $fakeNodeIdentity = Resolve-Arm64NodeJsYamlIdentity
    Assert-Arm64 ($fakeNodeIdentity.NodePath -ceq $fakeNode) `
        'ARM64_NODE_EXECUTABLE override was not respected'
}
finally {
    [Environment]::SetEnvironmentVariable('ARM64_NODE_EXECUTABLE', $savedNodeExecutable)
    Reset-Arm64RuntimeIdentityCache
    Remove-Item -LiteralPath $provenanceRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Assert-Arm64 (-not (Test-Path -LiteralPath $provenanceRoot)) `
    'runtime provenance probe left scratch residue'

# The bounded child must not inherit ambient proxy, Git, or module configuration.
$scrubVariables = @('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'GIT_DIR',
    'GIT_ALTERNATE_OBJECT_DIRECTORIES')
$scrubSaved = @{}
foreach ($scrubName in $scrubVariables) {
    $scrubSaved[$scrubName] = [Environment]::GetEnvironmentVariable($scrubName)
}
try {
    foreach ($scrubName in $scrubVariables) {
        [Environment]::SetEnvironmentVariable($scrubName, 'arm64-must-not-propagate')
    }
    $scrubCommand = '[Console]::Out.Write((@(' +
    "'HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','GIT_DIR','GIT_ALTERNATE_OBJECT_DIRECTORIES'" +
    ') | ForEach-Object { [Environment]::GetEnvironmentVariable($_) }) -join ''|'')'
    $scrubResult = Invoke-Arm64BoundedProcess `
        -FilePath (Get-Process -Id $PID).Path `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $scrubCommand) `
        -InputBytes ([byte[]]::new(0))
    $scrubText = $utf8Strict.GetString($scrubResult.OutputBytes)
    Assert-Arm64 (-not $scrubText.Contains('arm64-must-not-propagate',
            [StringComparison]::Ordinal)) `
        "the bounded child inherited scrubbed environment values: $scrubText"
}
finally {
    foreach ($scrubName in $scrubVariables) {
        [Environment]::SetEnvironmentVariable($scrubName, $scrubSaved[$scrubName])
    }
}

# Exact run-body identity: nothing is trimmed and no line ending is normalized.
$identityVariants = @('x', ' x', 'x ', ' x ', "x`n", "`nx", "x`r`n", "a`r`nb", "a`nb", "x`t")
$identityDigests = @($identityVariants | ForEach-Object { Get-Arm64Sha256Text -Text $_ })
Assert-Arm64 (@($identityDigests | Sort-Object -Unique -CaseSensitive).Count -eq
    $identityVariants.Count) `
    'distinct run-body byte sequences collapsed to the same identity'
Assert-Arm64 ((Get-Arm64Sha256Text -Text '') -ceq
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855') `
    'run-body identity is not the SHA-256 of its exact UTF-8 bytes'

$backendParameters = @((Get-Command Invoke-Arm64YamlBackend).Parameters.Keys)
Assert-Arm64 ($backendParameters -cnotcontains 'Path') `
    'the YAML backend can still reopen a candidate path instead of parsing validated bytes'
$textParameter = (Get-Command Invoke-Arm64YamlBackend).Parameters['Text']
Assert-Arm64 (@($textParameter.Attributes | Where-Object {
            $_ -is [Management.Automation.AllowEmptyStringAttribute]
        }).Count -eq 1) 'the bounded YAML backend does not accept an empty string structurally'
$emptyNodeJsYaml = Invoke-Arm64YamlBackend -Text '' -Backend NodeJsYaml
Assert-Arm64 ($null -eq $emptyNodeJsYaml) `
    'the NodeJsYaml child did not preserve an empty document as null'

foreach ($invalidBackendJson in @(
        '{"a":1,"a":2}',
        '{"a":1,"A":2}',
        '{"outer":{"x":1,"x":2}}',
        '{"a":1}{"b":2}',
        '{"a":1} trailing')) {
    $jsonOutcome = 'accepted'
    try {
        [void](ConvertFrom-Arm64StrictBackendJson `
                -Bytes $utf8Strict.GetBytes($invalidBackendJson))
    }
    catch {
        $jsonOutcome = [string]$_.Exception.Message
    }
    Assert-Arm64 ($jsonOutcome -ceq 'semantic-yaml-backend-parse-failed') `
        "duplicate or trailing backend JSON was accepted: $invalidBackendJson"
}
$nodeParserSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\parse-yaml.js') `
    -Raw
Assert-Arm64 ($nodeParserSource.Contains('process.stdin.fd', [StringComparison]::Ordinal)) `
    'the Node.js parser does not read from stdin'
foreach ($nodeFragment in @(
        "yamlPackage.version !== '4.3.2'",
        'process.stdin.fd',
        'MAX_INPUT_BYTES',
        'ANCHOR_SENTINEL',
        'readAnchorProperty',
        'readAlias',
        'CORE_SCHEMA',
        'hasMergeKey',
        '--scan-only')) {
    Assert-Arm64 ($nodeParserSource.Contains($nodeFragment, [StringComparison]::Ordinal)) `
        "the Node.js parser no longer contains '$nodeFragment'"
}


# Line-ending policy is explicit and identity is byte-exact: nothing is trimmed or normalized.
Assert-Arm64 ((Get-Arm64Sha256Text -Text "a`r`nb") -cne (Get-Arm64Sha256Text -Text "a`nb")) `
    'CRLF and LF run bodies collapse to the same identity'
Assert-Arm64 ((Get-Arm64Sha256Text -Text "a`n") -cne (Get-Arm64Sha256Text -Text 'a')) `
    'a terminal newline does not change run-body identity'
foreach ($whitespaceVariant in @(' x', 'x ', "`nx", "x`n", "`tx", "x`t", ' x ')) {
    Assert-Arm64 ((Get-Arm64Sha256Text -Text $whitespaceVariant) -cne
        (Get-Arm64Sha256Text -Text 'x')) `
        "leading or trailing whitespace variant '$whitespaceVariant' collapsed to the same identity"
}
Assert-Arm64 ((Get-Arm64Sha256Text -Text 'x') -ceq
    '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881') `
    'run-body identity is not the SHA-256 of its exact UTF-8 bytes'
$sha256Start = $auditSource.IndexOf(
    'function Get-Arm64Sha256Text',
    [StringComparison]::Ordinal
)
$sha256Body = $auditSource.Substring($sha256Start, 600)
Assert-Arm64 (-not $sha256Body.Contains('.Trim()', [StringComparison]::Ordinal)) `
    'run-body identity still trims whitespace before hashing'

# Every binding in this policy is a 40-hex SHA-1 object ID, so the object format is explicit.
$x64GitPin = @($script:arm64GitPins | Where-Object Architecture -ceq 'x64')
$arm64GitPin = @($script:arm64GitPins | Where-Object Architecture -ceq 'arm64')
Assert-Arm64 ($x64GitPin.Count -eq 1 -and
    $x64GitPin[0].LauncherSha256 -ceq
        '7b7971dd13f0c3a284e538601f2f9770b3a87dfaccb5fb52d68141c67ed22364' -and
    $x64GitPin[0].EngineSha256 -ceq
        '1a0043555d254618f2d56c936c3d9a1fbfb878bc878416a133c346bc7835eda9' -and
    $x64GitPin[0].RuntimeTreeSha256 -ceq
        '20c9c179dd4e9fddaf0b885fc1f3990345a4ad649b82e6a8818521e56b6b4862' -and
    $x64GitPin[0].RuntimeManifestSha256 -ceq
        'cd63c854cb26a8c1140685726374a82405cda7ea813ed86804d7145ecd33ba8c') `
    'the exact hosted x64 Git runtime pin changed'
Assert-Arm64 ($arm64GitPin.Count -eq 1 -and
    $arm64GitPin[0].LauncherSha256 -ceq
        'b05b2d7eb80933c602272b5ddf132adf288cf78ad8e32a7a47ca7e200076b9f3' -and
    $arm64GitPin[0].EngineSha256 -ceq
        '4cbb8ef70f1201e534fc3fab8f52b83080748a7115793d957d1b399e1ff55ad7' -and
    $arm64GitPin[0].RuntimeTreeSha256 -ceq
        'ae2dae0b859e7266b06894dbf377ecb30f04aeffe4b1e45e6d88f50fa8f1bbc0' -and
    $arm64GitPin[0].RuntimeManifestSha256 -ceq
        '721d63474d9f16be89a9aa3a00abf1415bd4848616f789d505db3cef1ab5dd4c') `
    'the exact local ARM64 Git runtime pin changed'
$approvedGitIdentity = Resolve-Arm64GitExecutable
$approvedGitPin = Resolve-Arm64GitRuntimePin `
    -LauncherPath $approvedGitIdentity.ExecutablePath
Assert-Arm64 ($approvedGitPin.Architecture -in @('x64', 'arm64') -and
    $approvedGitPin.Version -ceq '2.55.0.windows.3') `
    'the architecture-matched Git runtime was not selected'
$savedLauncherPin = $approvedGitPin.LauncherSha256
Reset-Arm64GitRuntimeIdentity
try {
    $approvedGitPin.LauncherSha256 = '0' * 64
    $wrongGitPinRejected = $false
    try {
        [void](Resolve-Arm64GitExecutable)
    }
    catch {
        $wrongGitPinRejected = $true
    }
    Assert-Arm64 $wrongGitPinRejected 'a changed Git launcher pin was accepted'
}
finally {
    $approvedGitPin.LauncherSha256 = $savedLauncherPin
    Reset-Arm64GitRuntimeIdentity
}
[void](Resolve-Arm64GitExecutable)
Assert-Arm64 ((Assert-Arm64GitObjectFormat -RepositoryRoot $repoRoot) -ceq 'sha1') `
    'the repository object format is not verified as sha1'
$objectFormatCases = @(
    @{ Name = 'absent'; Output = @() },
    @{ Name = 'null'; Output = $null },
    @{ Name = 'blank'; Output = @('   ') },
    @{ Name = 'sha256'; Output = @('sha256') },
    @{ Name = 'multiple'; Output = @('sha1', 'sha256') },
    @{ Name = 'duplicate'; Output = @('sha1', 'sha1') },
    @{ Name = 'uppercase'; Output = @('SHA1') },
    @{ Name = 'unexpected'; Output = @('sha1 --exec') },
    @{ Name = 'future'; Output = @('blake3') }
)
foreach ($objectFormatCase in $objectFormatCases) {
    $objectFormatRejected = $false
    try {
        [void](Assert-Arm64GitObjectFormatValue -Output $objectFormatCase.Output)
    }
    catch {
        $objectFormatRejected = $true
    }
    Assert-Arm64 $objectFormatRejected `
        "object format case '$($objectFormatCase.Name)' was accepted"
}
Assert-Arm64 ((Assert-Arm64GitObjectFormatValue -Output @("sha1`n")) -ceq 'sha1') `
    'a well-formed sha1 object format line was rejected'
$integritySource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\git-object-integrity.ps1') `
    -Raw
Assert-Arm64 ($integritySource.IndexOf(
        'Assert-Arm64GitObjectFormat -RepositoryRoot $RepositoryRoot',
        [StringComparison]::Ordinal
    ) -lt $integritySource.IndexOf(
        "'ls-tree', '-r', '-t', '-l', '--full-tree'",
        [StringComparison]::Ordinal
    )) 'the Git tree is enumerated before its object format is proven to be sha1'
Assert-Arm64 ($integritySource.IndexOf(
        'Assert-Arm64GitRepositoryHygiene -RepositoryRoot $RepositoryRoot',
        [StringComparison]::Ordinal
    ) -lt $integritySource.IndexOf(
        "'ls-tree', '-r', '-t', '-l', '--full-tree'",
        [StringComparison]::Ordinal
    )) 'the Git tree is enumerated before repository poisoning is ruled out'
$verifierSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\verify-protected-context.ps1') `
    -Raw
Assert-Arm64 ($verifierSource.Contains(
        'Assert-Arm64GitObjectFormat -RepositoryRoot $repositoryRoot',
        [StringComparison]::Ordinal
    )) 'the protected checkout does not assert a sha1 object format'

# --- Git object poisoning: replacement, grafts, alternates, and environment overrides ----
foreach ($hardening in @(
        "'--no-replace-objects'",
        "'core.hooksPath='",
        "'core.fsmonitor=false'",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_NO_REPLACE_OBJECTS",
        '$startInfo.Environment.Clear()')) {
    Assert-Arm64 ($integritySource.Contains($hardening, [StringComparison]::Ordinal)) `
        "hardened Git invocation no longer pins '$hardening'"
}

foreach ($gitOverride in @('GIT_DIR', 'GIT_OBJECT_DIRECTORY',
        'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_WORK_TREE',
        'GIT_INDEX_FILE', 'GIT_NAMESPACE', 'GIT_GRAFT_FILE', 'GIT_REPLACE_REF_BASE')) {
    $savedOverride = [Environment]::GetEnvironmentVariable($gitOverride)
    try {
        [Environment]::SetEnvironmentVariable($gitOverride, 'arm64-poison')
        $overrideRejected = $false
        try {
            [void](Assert-Arm64GitRepositoryHygiene -RepositoryRoot $repoRoot)
        }
        catch {
            $overrideRejected = $true
        }
        Assert-Arm64 $overrideRejected "Git environment override '$gitOverride' was accepted"
    }
    finally {
        [Environment]::SetEnvironmentVariable($gitOverride, $savedOverride)
    }
}

$syntheticRepoRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'arm64-gitprobe-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $syntheticRepoRoot -Force)
try {
    $initResult = Invoke-Arm64Git `
        -RepositoryRoot $syntheticRepoRoot `
        -GitArguments @('init', '--quiet', '--initial-branch=main')
    Assert-Arm64 ($initResult.ExitCode -eq 0) 'synthetic probe repository could not be created'
    Assert-Arm64 (Assert-Arm64GitRepositoryHygiene -RepositoryRoot $syntheticRepoRoot) `
        'a clean synthetic repository was reported as poisoned'

    $syntheticGitDir = Join-Path $syntheticRepoRoot '.git'
    foreach ($poison in @(
            @{ Name = 'grafts'; Path = 'info\grafts'
                Body = ('0' * 39) + '1 ' + ('0' * 39) + '2' },
            @{ Name = 'alternates'; Path = 'objects\info\alternates'
                Body = $syntheticRepoRoot },
            @{ Name = 'replace-ref'; Path = 'refs\replace\' + ('a' * 40)
                Body = ('b' * 40) })) {
        $poisonPath = Join-Path $syntheticGitDir $poison.Path
        [void](New-Item -ItemType Directory -Force -Path (Split-Path $poisonPath -Parent))
        [IO.File]::WriteAllText($poisonPath, $poison.Body + "`n",
            [Text.UTF8Encoding]::new($false))
        $poisonRejected = $false
        try {
            [void](Assert-Arm64GitRepositoryHygiene -RepositoryRoot $syntheticRepoRoot)
        }
        catch {
            $poisonRejected = $true
        }
        Remove-Item -LiteralPath $poisonPath -Force -ErrorAction SilentlyContinue
        Assert-Arm64 $poisonRejected "Git poisoning artifact '$($poison.Name)' was accepted"
    }

    Assert-Arm64 (Assert-Arm64GitRepositoryHygiene -RepositoryRoot $syntheticRepoRoot) `
        'the synthetic repository stayed poisoned after cleanup'

    # A hostile repository-local config must not change what the hardened invocation reports.
    [IO.File]::WriteAllText(
        (Join-Path $syntheticGitDir 'config'),
        "[core]`n`trepositoryformatversion = 0`n[uploadpack]`n`tallowFilter = true`n",
        [Text.UTF8Encoding]::new($false)
    )
    $syntheticFormat = Assert-Arm64GitObjectFormat -RepositoryRoot $syntheticRepoRoot
    Assert-Arm64 ($syntheticFormat -ceq 'sha1') `
        'the hardened Git invocation did not report a sha1 object format'
}
finally {
    Remove-Item -LiteralPath $syntheticRepoRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Assert-Arm64 (-not (Test-Path -LiteralPath $syntheticRepoRoot)) `
    'synthetic Git probe repository left residue behind'

# --- Mutation tests: every new token guard must be the thing that catches its attack ------
$mutationRoot = Join-Path (Join-Path $repoRoot '.github\scripts') (
    '.arm64-parser-mutation-' + [Guid]::NewGuid().ToString('n')
)
[void](New-Item -ItemType Directory -Path $mutationRoot -Force)
try {
    $mutationCases = @(
        @{ Name = 'anchor-guard'
            From = "throwError(state, '`${ANCHOR_SENTINEL}');"
            To = 'return state.input.charCodeAt(state.position) === 0x26 ? _unused_readAnchorProperty(state) : _unused_readAlias(state);'
            Attack = "a: &z q`nb: *z`n" },
        @{ Name = 'document-marker-guard'
            From = 'if (docMarkerRe.test(line)) {'
            To = 'if (false) {'
            Attack = "a: 1`n--- {b: 2}`n" },
        @{ Name = 'merge-guard'
            From = 'if (/!!merge\b/.test(text) ||'
            To = 'if (false ||'
            Attack = "a: !!merge value`n" },
        @{ Name = 'exotic-separator-guard'
            From = 'if (/[\x85\u2028\u2029]/.test(text)) {'
            To = 'if (false) {'
            Attack = "a: 1$([char]0x85)b: 2`n" },
        @{ Name = 'sentinel-classification-guard'
            From = "e.message.includes(ANCHOR_SENTINEL)"
            To = 'false'
            Attack = "a: &z q`n" }
    )
    foreach ($mutation in $mutationCases) {
        Assert-Arm64 ($nodeParserSource.Contains($mutation.From, [StringComparison]::Ordinal)) `
            "mutation target for '$($mutation.Name)' is no longer present in the source"
        $mutatedPath = Join-Path $mutationRoot 'parse-yaml.js'
        [IO.File]::WriteAllText(
            $mutatedPath,
            $nodeParserSource.Replace($mutation.From, $mutation.To),
            [Text.UTF8Encoding]::new($false)
        )
        $mutationResult = Invoke-Arm64BoundedProcess `
            -FilePath $nodeJsYamlIdentity.NodePath `
            -ArgumentList @($mutatedPath, '--scan-only') `
            -InputBytes ($utf8Strict.GetBytes($mutation.Attack))
        Assert-Arm64 ($mutationResult.ExitCode -eq 0) `
            "removing the '$($mutation.Name)' guard did not admit its attack, so the guard is not load-bearing"

        # The unmutated source must still refuse the same attack.
        $intactResult = Invoke-Arm64BoundedProcess `
            -FilePath $nodeJsYamlIdentity.NodePath `
            -ArgumentList @($nodeJsYamlIdentity.ParserHelperPath, '--scan-only') `
            -InputBytes ($utf8Strict.GetBytes($mutation.Attack))
        Assert-Arm64 ($intactResult.ExitCode -ne 0) `
            "the intact gate did not refuse the '$($mutation.Name)' attack"
    }
}
finally {
    Remove-Item -LiteralPath $mutationRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Assert-Arm64 (-not (Test-Path -LiteralPath $mutationRoot)) `
    'mutation scratch directory left residue behind'

$historicalActionPins = [ordered]@{
    'msys2/setup-msys2' = '66cd2cce69caa17b53920067426061ca1de3a884'
    'actions/upload-artifact' = 'ea165f8d65b6e75b540449e92b4886f43607fa02'
    'actions/download-artifact' = 'd3f86a106a0bac45b974a628896c90dbdf5c8093'
    'actions/cache/restore' = '0057852bfaa89a56745cba8c7296529d2fc39830'
    'actions/cache/save' = '0057852bfaa89a56745cba8c7296529d2fc39830'
    'actions/upload-pages-artifact' = '56afc609e74202658d3ffba0e8f6dda462b719fa'
    'actions/configure-pages' = '1f0c5cde4bc74cd7e1254d0cb4de8d49e9068c7d'
    'actions/deploy-pages' = 'd6db90164ac5ed86f2b6aed7e0febac5b3c0c03e'
}
$historicalActionRoot = Join-Path ([IO.Path]::GetTempPath()) "arm64-historical-action-$PID"
try {
    foreach ($historicalAction in $historicalActionPins.GetEnumerator()) {
        if (Test-Path -LiteralPath $historicalActionRoot) {
            Remove-Item -LiteralPath $historicalActionRoot -Recurse -Force
        }
        Copy-Item -LiteralPath $validRoot -Destination $historicalActionRoot -Recurse -Force
        $workflowPath = Join-Path $historicalActionRoot '.github\workflows\test.yml'
        $workflowText = @(
            'name: Historical action rejection'
            'on: pull_request'
            'jobs:'
            '  audit:'
            '    runs-on: ubuntu-latest'
            '    steps:'
            "      - uses: $($historicalAction.Key)@$($historicalAction.Value)"
        ) -join "`n"
        [IO.File]::WriteAllText(
            $workflowPath,
            "$workflowText`n",
            [Text.UTF8Encoding]::new($false)
        )
        $policy = New-WorkflowFixturePolicy -Root $historicalActionRoot
        $result = Test-Arm64WorkflowTree `
            -Root $historicalActionRoot `
            -Policy $policy `
            -Backend $semanticBackend `
            -SkipAuthoritativeSnapshot
        Assert-Arm64 (-not $result.Allowed) `
            "historical-only action was accepted: $($historicalAction.Key)"
        $expectedActionError = if ($historicalAction.Key -match
            '(?i)(?:upload-artifact|download-artifact|pages)') {
            'publication-action-forbidden:'
        }
        else {
            'remote-uses-not-reviewed:'
        }
        Assert-Arm64 (@($result.Errors | Where-Object {
                    $_.StartsWith($expectedActionError, [StringComparison]::Ordinal)
                }).Count -gt 0) `
            "historical-only action missed active allowlist denial: $($historicalAction.Key)"
    }
}
finally {
    if (Test-Path -LiteralPath $historicalActionRoot) {
        Remove-Item -LiteralPath $historicalActionRoot -Recurse -Force
    }
}

$governanceFixtureRoot = Join-Path ([IO.Path]::GetTempPath()) "arm64-governance-name-$PID"
$governanceCases = @(
    @{
        Name = 'case-prefix spoof'
        JobText = @(
            '  audit:'
            '    name: ARM64-Governance spoof'
            '    runs-on: ubuntu-latest'
            '    steps:'
            '      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
        )
        Error = 'governance-check-name-alias:'
    },
    @{
        Name = 'always masking'
        JobText = @(
            '  audit:'
            '    name: arm64-governance'
            '    if: always()'
            '    runs-on: ubuntu-latest'
            '    steps:'
            '      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
        )
        Error = 'governance-check-can-be-skipped:'
    },
    @{
        Name = 'dependency skipped success'
        JobText = @(
            '  audit:'
            '    name: arm64-governance'
            '    needs: preflight'
            '    runs-on: ubuntu-latest'
            '    steps:'
            '      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
        )
        Error = 'governance-check-can-be-skipped:'
    },
    @{
        Name = 'duplicate exact check'
        JobText = @(
            '  first:'
            '    name: arm64-governance'
            '    runs-on: ubuntu-latest'
            '    steps:'
            '      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
            '  second:'
            '    name: arm64-governance'
            '    runs-on: ubuntu-latest'
            '    steps:'
            '      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
        )
        Error = 'protected-check-name-not-unique'
    }
)
try {
    foreach ($governanceCase in $governanceCases) {
        if (Test-Path -LiteralPath $governanceFixtureRoot) {
            Remove-Item -LiteralPath $governanceFixtureRoot -Recurse -Force
        }
        Copy-Item -LiteralPath $validRoot -Destination $governanceFixtureRoot -Recurse -Force
        $workflowPath = Join-Path $governanceFixtureRoot '.github\workflows\test.yml'
        $workflowText = @(
            'name: Governance identity fixture'
            'on: pull_request'
            'jobs:'
        ) + $governanceCase.JobText
        [IO.File]::WriteAllText(
            $workflowPath,
            "$($workflowText -join "`n")`n",
            [Text.UTF8Encoding]::new($false)
        )
        $policy = New-WorkflowFixturePolicy -Root $governanceFixtureRoot
        $policy | Add-Member -MemberType NoteProperty -Name protected_verifier -Value (
            [pscustomobject]@{
                check_name = 'arm64-governance'
                sources = [pscustomobject]@{}
            }
        )
        $result = Test-Arm64WorkflowTree `
            -Root $governanceFixtureRoot `
            -Policy $policy `
            -Backend $semanticBackend `
            -SkipAuthoritativeSnapshot
        Assert-Arm64 (-not $result.Allowed) `
            "governance check spoofing passed: $($governanceCase.Name)"
        Assert-Arm64 (@($result.Errors | Where-Object {
                    $_.StartsWith($governanceCase.Error, [StringComparison]::Ordinal)
                }).Count -gt 0) `
            "governance check case missed denial: $($governanceCase.Name)"
    }
}
finally {
    if (Test-Path -LiteralPath $governanceFixtureRoot) {
        Remove-Item -LiteralPath $governanceFixtureRoot -Recurse -Force
    }
}

$parserFailure = Test-Arm64WorkflowTree `
    -Root $validRoot `
    -Policy $validWorkflowPolicy `
    -Backend Unavailable `
    -SkipAuthoritativeSnapshot
Assert-Arm64 (-not $parserFailure.Allowed) 'missing semantic parser did not fail closed'
Assert-Arm64 ($parserFailure.Errors -ccontains 'semantic-parser-unavailable') `
    'missing semantic parser did not report its denial'

$missingSnapshotRoot = Join-Path $workflowFixtureRoot 'yaml-inline'
$snapshotFailure = Test-Arm64WorkflowTree `
    -Root $missingSnapshotRoot `
    -Policy $validWorkflowPolicy `
    -Backend $semanticBackend
Assert-Arm64 (-not $snapshotFailure.Allowed) 'missing authoritative snapshot was accepted'
Assert-Arm64 ($snapshotFailure.Errors -ccontains 'authoritative-snapshot-missing') `
    'missing authoritative snapshot did not report its denial'

$fixtureTrustedPolicy = Join-Path $validRoot '.github\policies\arm64-quarantine-policy.json'
$snapshotSuccess = Test-Arm64WorkflowTree `
    -Root $validRoot `
    -Policy $validWorkflowPolicy `
    -TrustedPolicyPath $fixtureTrustedPolicy `
    -Backend $semanticBackend
Assert-Arm64 $snapshotSuccess.Allowed `
    "authoritative snapshot success case failed: $($snapshotSuccess.Errors -join ', ')"

$tamperRoot = Join-Path ([IO.Path]::GetTempPath()) "arm64-snapshot-tamper-$PID"
try {
    if (Test-Path -LiteralPath $tamperRoot) {
        Remove-Item -LiteralPath $tamperRoot -Recurse -Force
    }
    Copy-Item -LiteralPath $validRoot -Destination $tamperRoot -Recurse -Force
    $tamperedSnapshotPath = Join-Path $tamperRoot 'authoritative-snapshot.json'
    $tamperedSnapshot = Get-Content -LiteralPath $tamperedSnapshotPath -Raw |
        ConvertFrom-Json -Depth 32
    $tamperedSnapshot.files[0].oid = '9999999999999999999999999999999999999999'
    $tamperedSnapshot | ConvertTo-Json -Depth 32 |
        Set-Content -LiteralPath $tamperedSnapshotPath -Encoding utf8NoBOM
    $tamperPolicyPath = Join-Path $tamperRoot '.github\policies\arm64-quarantine-policy.json'
    $tamperResult = Test-Arm64WorkflowTree `
        -Root $tamperRoot `
        -Policy $validWorkflowPolicy `
        -TrustedPolicyPath $tamperPolicyPath `
        -Backend $semanticBackend
    Assert-Arm64 (-not $tamperResult.Allowed) 'tampered API snapshot passed'
    Assert-Arm64 (@($tamperResult.Errors | Where-Object {
                $_.StartsWith(
                    'authoritative-snapshot-source-binding-mismatch:',
                    [StringComparison]::Ordinal
                )
            }).Count -gt 0) 'tampered API snapshot missed its source binding denial'
}
finally {
    if (Test-Path -LiteralPath $tamperRoot) {
        Remove-Item -LiteralPath $tamperRoot -Recurse -Force
    }
}

$sourceVariantRoot = Join-Path ([IO.Path]::GetTempPath()) "arm64-source-variant-$PID"
$sourceVariants = @('crlf', 'utf8-bom', 'utf16')
try {
    foreach ($variant in $sourceVariants) {
        if (Test-Path -LiteralPath $sourceVariantRoot) {
            Remove-Item -LiteralPath $sourceVariantRoot -Recurse -Force
        }
        Copy-Item -LiteralPath $validRoot -Destination $sourceVariantRoot -Recurse -Force
        $workflowPath = Join-Path $sourceVariantRoot '.github\workflows\test.yml'
        $originalBytes = [IO.File]::ReadAllBytes($workflowPath)
        $originalText = [Text.UTF8Encoding]::new($false, $true).GetString($originalBytes).
            Replace("`r`n", "`n")
        $variantBytes = switch ($variant) {
            'crlf' {
                [Text.UTF8Encoding]::new($false).GetBytes(
                    $originalText.Replace("`n", "`r`n")
                )
            }
            'utf8-bom' {
                [byte[]](@(0xef, 0xbb, 0xbf) +
                    [Text.UTF8Encoding]::new($false).GetBytes($originalText))
            }
            'utf16' {
                [Text.Encoding]::Unicode.GetPreamble() +
                    [Text.Encoding]::Unicode.GetBytes($originalText)
            }
        }
        [IO.File]::WriteAllBytes($workflowPath, $variantBytes)
        $result = Test-Arm64WorkflowTree `
            -Root $sourceVariantRoot `
            -Policy $validWorkflowPolicy `
            -TrustedPolicyPath (Join-Path $sourceVariantRoot `
                '.github\policies\arm64-quarantine-policy.json') `
            -Backend $semanticBackend
        Assert-Arm64 (-not $result.Allowed) "source byte variant passed: $variant"
        Assert-Arm64 ($result.Errors -ccontains
            'authoritative-snapshot-source-binding-mismatch:.github/workflows/test.yml') `
            "source byte variant missed raw binding denial: $variant"
    }
}
finally {
    if (Test-Path -LiteralPath $sourceVariantRoot) {
        Remove-Item -LiteralPath $sourceVariantRoot -Recurse -Force
    }
}

$emptyBlobOid = Get-Arm64GitBlobOid -Bytes ([byte[]]::new(0))
Assert-Arm64 ($emptyBlobOid -ceq 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391') `
    'empty Git blob hashing does not match the canonical object ID'
$oneByteOid = Get-Arm64GitBlobOid -Bytes ([byte[]]@(0x61))
$modeExpected = New-Arm64SourceBinding `
    -Path '.github/workflows/test.yml' `
    -Mode '100644' `
    -ObjectType 'blob' `
    -ByteLength 1 `
    -Oid $oneByteOid
$modeChanged = New-Arm64SourceBinding `
    -Path '.github/workflows/test.yml' `
    -Mode '100755' `
    -ObjectType 'blob' `
    -ByteLength 1 `
    -Oid $oneByteOid
Assert-Arm64 (-not (Test-Arm64SourceBindingEqual `
        -Expected $modeExpected `
        -Actual $modeChanged)) 'executable-mode source change passed'
$rawPathChanged = Copy-JsonObject $modeExpected
$rawPathChanged.raw_path_utf8_base64 = 'ZmFrZQ=='
$rawPathRejected = $false
try {
    [void](Test-Arm64SourceBindingEqual -Expected $modeExpected -Actual $rawPathChanged)
}
catch {
    $rawPathRejected = $true
}
Assert-Arm64 $rawPathRejected 'raw path identity tampering passed'

$policyExpected = New-Arm64SourceBinding `
    -Path '.github/policies/arm64-quarantine-policy.json' `
    -Mode '100644' `
    -ObjectType 'blob' `
    -ByteLength 1 `
    -Oid (Get-Arm64GitBlobOid -Bytes ([byte[]]@(0x70)))
$scriptExpected = New-Arm64SourceBinding `
    -Path '.github/scripts/audit-arm64-workflows.ps1' `
    -Mode '100644' `
    -ObjectType 'blob' `
    -ByteLength 1 `
    -Oid (Get-Arm64GitBlobOid -Bytes ([byte[]]@(0x73)))
$policyChanged = Copy-JsonObject $policyExpected
$policyChanged.oid = Get-Arm64GitBlobOid -Bytes ([byte[]]@(0x71))
$scriptChanged = Copy-JsonObject $scriptExpected
$scriptChanged.oid = Get-Arm64GitBlobOid -Bytes ([byte[]]@(0x74))
$coordinatedChangeRejected = $false
try {
    Assert-Arm64SourceBindingSetsEqual `
        -Expected @($policyExpected, $scriptExpected) `
        -Actual @($policyChanged, $scriptChanged) `
        -Label 'protected-source'
}
catch {
    $coordinatedChangeRejected = $true
}
Assert-Arm64 $coordinatedChangeRejected `
    'coordinated policy and verifier source changes passed'
foreach ($changedSet in @(
        @($policyExpected),
        @($policyExpected, $scriptExpected, $modeExpected))) {
    $setRejected = $false
    try {
        Assert-Arm64SourceBindingSetsEqual `
            -Expected @($policyExpected, $scriptExpected) `
            -Actual $changedSet `
            -Label 'protected-source'
    }
    catch {
        $setRejected = $true
    }
    Assert-Arm64 $setRejected 'missing or extra protected source entry passed'
}

$script:mockApiRoot = 'https' + [char]58 + '//api.github.com/repos'
function New-MockedTreeEntry {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Mode,
        [Parameter(Mandatory)][string]$Type,
        [string]$Sha = '1111111111111111111111111111111111111111',
        [AllowNull()][object]$Size = 1
    )

    $entry = [pscustomobject][ordered]@{
        path = $Path
        mode = $Mode
        type = $Type
        sha = $Sha
        url = "$($script:mockApiRoot)/example/repo/git/$Type/$Sha"
    }
    if ($null -ne $Size) {
        $entry | Add-Member -MemberType NoteProperty -Name size -Value $Size
    }
    return $entry
}

$treeOid = '2222222222222222222222222222222222222222'
$treeCases = @(
    @{
        Name = 'workflow gitlink'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/workflows/linked' `
                -Mode '160000' `
                -Type 'commit' `
                -Size $null)
        Truncated = $false
    },
    @{
        Name = 'protected symlink'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/policies/policy.json' `
                -Mode '120000' `
                -Type 'blob')
        Truncated = $false
    },
    @{
        Name = 'invalid object id'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/workflows/test.yml' `
                -Mode '100644' `
                -Type 'blob' `
                -Sha 'abc')
        Truncated = $false
    },
    @{
        Name = 'blob at workflow directory'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/workflows' `
                -Mode '100644' `
                -Type 'blob')
        Truncated = $false
    },
    @{
        Name = 'nested workflow tree'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/workflows/nested' `
                -Mode '040000' `
                -Type 'tree' `
                -Size $null)
        Truncated = $false
    },
    @{
        Name = 'malformed mode'
        Entries = @(New-MockedTreeEntry `
                -Path '.github/workflows/test.yml' `
                -Mode '100600' `
                -Type 'blob')
        Truncated = $false
    },
    @{
        Name = 'duplicate path'
        Entries = @(
            (New-MockedTreeEntry -Path '.github/workflows/test.yml' -Mode '100644' -Type 'blob'),
            (New-MockedTreeEntry -Path '.github/workflows/test.yml' -Mode '100644' -Type 'blob')
        )
        Truncated = $false
    },
    @{
        Name = 'casefold alias'
        Entries = @(
            (New-MockedTreeEntry -Path '.github/workflows/test.yml' -Mode '100644' -Type 'blob'),
            (New-MockedTreeEntry -Path '.github/workflows/TEST.yml' -Mode '100644' -Type 'blob')
        )
        Truncated = $false
    },
    @{
        Name = 'truncated tree'
        Entries = @()
        Truncated = $true
    }
)
foreach ($treeCase in $treeCases) {
    $treeRejected = $false
    try {
        [void](Get-Arm64ValidatedRestTreeEntries `
                -TreeResponse ([pscustomobject]@{
                    sha = $treeOid
                    truncated = $treeCase.Truncated
                    tree = $treeCase.Entries
                }) `
                -ExpectedTree $treeOid)
    }
    catch {
        $treeRejected = $true
    }
    Assert-Arm64 $treeRejected "malformed tree fixture passed: $($treeCase.Name)"
}
$unicodePathRejected = $false
try {
    [void](Get-Arm64RawPathIdentity -Path ".github/workflows/e$([char]0x0301).yml")
}
catch {
    $unicodePathRejected = $true
}
Assert-Arm64 $unicodePathRejected 'non-ASCII/NFC path alias passed'

$currentWorkflowResult = Test-Arm64WorkflowTree `
    -Root $repoRoot `
    -Policy $livePolicy `
    -Backend $semanticBackend `
    -SkipAuthoritativeSnapshot
Assert-Arm64 $currentWorkflowResult.Allowed `
    "current active workflows failed semantic audit: $($currentWorkflowResult.Errors -join ', ')"

$activeWorkflowNames = @(Get-ChildItem (Join-Path $repoRoot '.github\workflows') -File |
        Where-Object { $_.Extension -in @('.yml', '.yaml') } |
        ForEach-Object { $_.Name } |
        Sort-Object)
Assert-Arm64 (($activeWorkflowNames -join ',') -ceq
    'arm64-bootstrap-diagnostics.yml,arm64-quarantine-policy.yml') `
    "unexpected active workflow set: $($activeWorkflowNames -join ', ')"

$protectedWorkflow = ConvertFrom-Arm64YamlFile `
    -Path (Join-Path $repoRoot '.github\workflows\arm64-quarantine-policy.yml') `
    -Backend $semanticBackend
$protectedEvents = @(Get-Arm64MapNames `
    -Map (Get-Arm64MapProperty -Map $protectedWorkflow -Name 'on').Value)
Assert-Arm64 (($protectedEvents -join ',') -ceq 'pull_request_target') `
    'protected workflow is not pull_request_target-only'
$protectedAudit = (Get-Arm64MapProperty `
        -Map (Get-Arm64MapProperty -Map $protectedWorkflow -Name 'jobs').Value `
        -Name 'governance').Value
Assert-Arm64 ((Get-Arm64MapProperty -Map $protectedAudit -Name 'name').Value -ceq
    'arm64-governance') 'protected verifier check name is not exact'
Assert-Arm64 ($null -eq (Get-Arm64MapProperty -Map $protectedAudit -Name 'if') -and
    $null -eq (Get-Arm64MapProperty -Map $protectedAudit -Name 'needs')) `
    'protected verifier can be skipped or masked by job dependencies'
$protectedSteps = @((Get-Arm64MapProperty -Map $protectedAudit -Name 'steps').Value)
$checkoutStep = @($protectedSteps | Where-Object {
        $usesProperty = Get-Arm64MapProperty -Map $_ -Name 'uses'
        $null -ne $usesProperty -and $usesProperty.Value -like 'actions/checkout@*'
    })[0]
Assert-Arm64 ((Get-Arm64MapProperty `
            -Map (Get-Arm64MapProperty -Map $checkoutStep -Name 'with').Value `
            -Name 'ref').Value -ceq '${{ github.event.pull_request.base.sha }}') `
    'protected verifier does not checkout the exact base SHA'
$checkoutIndex = [Array]::IndexOf($protectedSteps, $checkoutStep)
foreach ($step in $protectedSteps[($checkoutIndex + 1)..(
            $protectedSteps.Count - 1
        )] | Where-Object {
        $null -ne (Get-Arm64MapProperty -Map $_ -Name 'run')
    }) {
    Assert-Arm64 ((Get-Arm64MapProperty -Map $step -Name 'working-directory').Value -ceq
        'verifier') 'protected verifier can execute outside the base checkout'
}
$bootstrapWorkflow = ConvertFrom-Arm64YamlFile `
    -Path (Join-Path $repoRoot '.github\workflows\arm64-bootstrap-diagnostics.yml') `
    -Backend $semanticBackend
$bootstrapEvents = @(Get-Arm64MapNames `
    -Map (Get-Arm64MapProperty -Map $bootstrapWorkflow -Name 'on').Value)
Assert-Arm64 (($bootstrapEvents -join ',') -ceq 'pull_request') `
    'bootstrap diagnostic has a non-PR trigger'
$activeJobNames = @(
    foreach ($workflow in @($protectedWorkflow, $bootstrapWorkflow)) {
        $jobs = (Get-Arm64MapProperty -Map $workflow -Name 'jobs').Value
        foreach ($jobKey in Get-Arm64MapNames -Map $jobs) {
            $job = (Get-Arm64MapProperty -Map $jobs -Name $jobKey).Value
            $name = Get-Arm64MapProperty -Map $job -Name 'name'
            if ($null -eq $name) {
                [string]$jobKey
            }
            else {
                [string]$name.Value
            }
        }
    }
)
Assert-Arm64 (@($activeJobNames | Where-Object {
            $_ -ceq 'arm64-governance'
        }).Count -eq 1) 'arm64-governance check identity is absent or duplicated'
Assert-Arm64 (@($activeJobNames | Where-Object {
            $_ -cne 'arm64-governance' -and
            ($_.StartsWith('arm64-governance', [StringComparison]::OrdinalIgnoreCase) -or
                'arm64-governance'.StartsWith($_, [StringComparison]::OrdinalIgnoreCase))
        }).Count -eq 0) 'arm64-governance has a case or prefix alias'

$historicalRoot = Join-Path $repoRoot '.github\historical-workflows'
$historicalFiles = @(Get-ChildItem -LiteralPath $historicalRoot -Filter '*.disabled' -File)
Assert-Arm64 ($historicalFiles.Count -eq 5) 'all five operational workflows must be archived'
foreach ($historicalFile in $historicalFiles) {
    $document = ConvertFrom-Arm64YamlFile -Path $historicalFile.FullName -Backend $semanticBackend
    foreach ($uses in Find-SemanticUses -Node $document) {
        if ($uses.StartsWith('./', [StringComparison]::Ordinal)) {
            continue
        }
        $separator = $uses.LastIndexOf('@')
        Assert-Arm64 ($separator -gt 0) "$($historicalFile.Name) has an unpinned action"
        $action = $uses.Substring(0, $separator)
        $reference = $uses.Substring($separator + 1)
        Assert-Arm64 ($reference -cmatch '^[0-9a-f]{40}$') `
            "$($historicalFile.Name) has a mutable action: $uses"
        $pin = $livePolicy.external_action_pins.PSObject.Properties[$action]
        if ($action -ceq 'actions/checkout') {
            Assert-Arm64 ($null -ne $pin -and $reference -ceq $pin.Value.commit) `
                "$($historicalFile.Name) has the wrong active checkout pin"
        }
        else {
            Assert-Arm64 ($null -eq $pin) `
                "$($historicalFile.Name) action became active merely because it is historical: $action"
        }
    }
}

$expectedPins = [ordered]@{
    'actions/checkout' = '11d5960a326750d5838078e36cf38b85af677262'
}
Assert-Arm64 (@($livePolicy.external_action_pins.PSObject.Properties).Count -eq 1) `
    'active action allowlist contains historical-only actions'
foreach ($pin in $expectedPins.GetEnumerator()) {
    Assert-Arm64 ($livePolicy.external_action_pins.PSObject.Properties[$pin.Key].Value.commit -ceq
        $pin.Value) "reviewed action pin changed: $($pin.Key)"
}
foreach ($pin in $livePolicy.external_action_pins.PSObject.Properties) {
    Assert-Arm64 (Test-Arm64Sha $pin.Value.commit) "action commit is invalid: $($pin.Name)"
    Assert-Arm64 (Test-Arm64Sha $pin.Value.tree) "action tree is invalid: $($pin.Name)"
    Assert-Arm64 (-not [string]::IsNullOrWhiteSpace($pin.Value.verification)) `
        "action audit disposition is absent: $($pin.Name)"
}
Assert-Arm64 ($livePolicy.forbidden_msystems -ccontains 'MINGWARM64') `
    'MINGWARM64 incompatibility is not explicit'

$collectorSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\collect-arm64-evidence.ps1') `
    -Raw
$bootstrapIndex = $collectorSource.IndexOf(
    'Live ARM64 admission is bootstrap-disabled.',
    [StringComparison]::Ordinal
)
$collectionIndex = $collectorSource.IndexOf(
    '$script:Arm64GitHubToken = $env:GITHUB_TOKEN',
    [StringComparison]::Ordinal
)
Assert-Arm64 ($bootstrapIndex -ge 0 -and $collectionIndex -gt $bootstrapIndex) `
    'authoritative collector does not deny bootstrap before API access'
Assert-Arm64 ($collectorSource -notmatch '(?m)^param\([^)]*(?:RunId|ArtifactId|Metadata|Json)') `
    'authoritative collector exposes caller identity parameters'

$collectorTokens = $null
$collectorParseErrors = $null
$collectorAst = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repoRoot '.github\scripts\collect-arm64-evidence.ps1'),
    [ref]$collectorTokens,
    [ref]$collectorParseErrors
)
Assert-Arm64 ($collectorParseErrors.Count -eq 0) 'authoritative collector has parse errors'
foreach ($functionName in @(
        'Get-Arm64AnnotatedTagEvidence',
        'Get-Arm64ReleaseBundle')) {
    $definition = @($collectorAst.FindAll({
                param($node)
                return $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
                    $node.Name -ceq $functionName
            }, $true))
    Assert-Arm64 ($definition.Count -eq 1) "collector helper is absent or duplicated: $functionName"
    $ancestor = $definition[0].Parent
    $nested = $false
    while ($null -ne $ancestor) {
        if ($ancestor -is [Management.Automation.Language.FunctionDefinitionAst]) {
            $nested = $true
            break
        }
        $ancestor = $ancestor.Parent
    }
    Assert-Arm64 (-not $nested) "collector helper is nested: $functionName"
}

. ./.github/scripts/collect-arm64-evidence.ps1
function Invoke-Arm64GitHubApi {
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

    switch ($Endpoint) {
        'Release' {
            if ($ReleaseId -eq 404) {
                throw 'mocked HTTP 404'
            }
            return [pscustomobject]@{
                id = $ReleaseId
                url = "$($script:mockApiRoot)/$Repository/releases/$ReleaseId"
                immutable = $true
                draft = $false
                prerelease = $false
                tag_name = 'fixture-runtime'
                published_at = '2026-08-20T00:00:00Z'
                target_commitish = 'main'
            }
        }
        'ReleaseAssets' {
            return , [pscustomobject]@{
                id = 1
                url = "$($script:mockApiRoot)/$Repository/releases/assets/1"
                name = 'asset'
                size = 1024
                digest = "sha256:$('a' * 64)"
                state = 'uploaded'
            }
        }
        'TagRef' {
            return [pscustomobject]@{
                ref = "refs/tags/$TagName"
                url = "$($script:mockApiRoot)/$Repository/git/refs/tags/$TagName"
                object = [pscustomobject]@{
                    type = 'tag'
                    sha = '7777777777777777777777777777777777777777'
                    url = "$($script:mockApiRoot)/$Repository/git/tags/7777777777777777777777777777777777777777"
                }
            }
        }
        'TagObject' {
            return [pscustomobject]@{
                sha = $ObjectId
                url = "$($script:mockApiRoot)/$Repository/git/tags/$ObjectId"
                object = [pscustomobject]@{
                    type = 'commit'
                    sha = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                    url = "$($script:mockApiRoot)/$Repository/git/commits/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                }
            }
        }
        'Compare' {
            return [pscustomobject]@{
                status = 'ahead'
                ahead_by = 2
                behind_by = 0
                total_commits = 2
                base_commit = [pscustomobject]@{ sha = $BaseObjectId }
                merge_base_commit = [pscustomobject]@{ sha = $BaseObjectId }
                commits = @(
                    [pscustomobject]@{ sha = 'cccccccccccccccccccccccccccccccccccccccc' }
                )
            }
        }
        default {
            throw "Unexpected mocked API endpoint: $Endpoint"
        }
    }
}
$mockBundle = Get-Arm64ReleaseBundle `
    -Repository 'example/runtime-fixture' `
    -ReleaseId 400000001
Assert-Arm64 ($mockBundle.id -eq 400000001 -and $mockBundle.immutable) `
    'mocked collector did not bind immutable release identity'
Assert-Arm64 ($mockBundle.annotated_tag.peeled_commit -ceq
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb') `
    'mocked collector did not bind the peeled annotated tag'
Assert-Arm64 ($mockBundle.asset_manifest.count -eq 1 -and
    (Test-Arm64Sha256 $mockBundle.asset_manifest.sha256)) `
    'mocked collector did not build a complete asset manifest'

$invalidRequestRejected = $false
try {
    [void](New-GitHubRestRequest `
            -Repository 'example/repository' `
            -Endpoint Commit `
            -ObjectId 'abc')
}
catch {
    $invalidRequestRejected = $true
}
Assert-Arm64 $invalidRequestRejected 'invalid SHA reached the GitHub REST transport'

$redirect = [Net.Http.HttpResponseMessage]::new(
    [Net.HttpStatusCode]::Found
)
$redirect.Content = [Net.Http.ByteArrayContent]::new(
    [Text.Encoding]::UTF8.GetBytes('{}')
)
$redirect.Content.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new(
    'application/json'
)
$redirectRejected = $false
try {
    [void](ConvertFrom-GitHubRestResponse -Response $redirect)
}
catch {
    $redirectRejected = $true
}
finally {
    $redirect.Dispose()
}
Assert-Arm64 $redirectRejected 'GitHub REST redirect was accepted'

$truncatedBytes = [Text.Encoding]::UTF8.GetBytes('{"ok":true}')
$truncated = [Net.Http.HttpResponseMessage]::new([Net.HttpStatusCode]::OK)
$truncated.Content = [Net.Http.ByteArrayContent]::new($truncatedBytes)
$truncated.Content.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new(
    'application/json'
)
$truncated.Content.Headers.ContentLength = $truncatedBytes.Length + 1
$truncationRejected = $false
try {
    [void](ConvertFrom-GitHubRestResponse -Response $truncated)
}
catch {
    $truncationRejected = $true
}
finally {
    $truncated.Dispose()
}
Assert-Arm64 $truncationRejected 'truncated GitHub REST response was accepted'

$duplicateJson = [Net.Http.HttpResponseMessage]::new([Net.HttpStatusCode]::OK)
$duplicateJson.Content = [Net.Http.ByteArrayContent]::new(
    [Text.Encoding]::UTF8.GetBytes('{"sha":"a","SHA":"b"}')
)
$duplicateJson.Content.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new(
    'application/json'
)
$duplicateRejected = $false
try {
    [void](ConvertFrom-GitHubRestResponse -Response $duplicateJson)
}
catch {
    $duplicateRejected = $true
}
finally {
    $duplicateJson.Dispose()
}
Assert-Arm64 $duplicateRejected 'duplicate/casefold JSON properties were accepted'
$transportSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\github-rest.ps1') `
    -Raw
Assert-Arm64 ($transportSource.Contains(
        '$handler.AllowAutoRedirect = $false',
        [StringComparison]::Ordinal
    )) 'GitHub REST authorization can follow redirects'
foreach ($transportFragment in @(
        '$handler.UseProxy = $false',
        '$handler.Proxy = $null',
        '$handler.UseCookies = $false',
        '$handler.AutomaticDecompression = [Net.DecompressionMethods]::None')) {
    Assert-Arm64 ($transportSource.Contains($transportFragment, [StringComparison]::Ordinal)) `
        "GitHub REST transport no longer pins '$transportFragment'"
}
Assert-Arm64 ($transportSource.Contains(
        'Assert-GitHubRestHandler -Handler (New-GitHubRestHandler)',
        [StringComparison]::Ordinal
    )) 'GitHub REST transport does not verify its own handler before sending'

# Ambient proxy configuration must never be able to observe or redirect an authorized GET.
$proxyVariables = @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy')
$proxyProbeUrl = 'http' + [char]58 + '//127.0.0.1:9'
$savedProxyValues = @{}
foreach ($proxyVariable in $proxyVariables) {
    $savedProxyValues[$proxyVariable] = [Environment]::GetEnvironmentVariable($proxyVariable)
}
try {
    foreach ($proxyVariable in $proxyVariables) {
        [Environment]::SetEnvironmentVariable($proxyVariable, $proxyProbeUrl)
    }
    $restHandler = New-GitHubRestHandler
    try {
        Assert-Arm64 (-not $restHandler.UseProxy) 'REST transport can use an ambient proxy'
        Assert-Arm64 ($null -eq $restHandler.Proxy) 'REST transport carries a proxy instance'
        Assert-Arm64 (-not $restHandler.AllowAutoRedirect) 'REST transport can follow redirects'
        Assert-Arm64 (-not $restHandler.UseCookies) 'REST transport can carry cookies'
        Assert-Arm64 ($restHandler.AutomaticDecompression -eq
            [Net.DecompressionMethods]::None) 'REST transport can auto-decompress'
        [void](Assert-GitHubRestHandler -Handler $restHandler)
    }
    finally {
        $restHandler.Dispose()
    }

    foreach ($handlerMutation in @('UseProxy', 'Proxy', 'AllowAutoRedirect', 'UseCookies',
            'AutomaticDecompression')) {
        $mutatedHandler = New-GitHubRestHandler
        try {
            switch ($handlerMutation) {
                'UseProxy' { $mutatedHandler.UseProxy = $true }
                'Proxy' { $mutatedHandler.Proxy = [Net.WebProxy]::new($proxyProbeUrl) }
                'AllowAutoRedirect' { $mutatedHandler.AllowAutoRedirect = $true }
                'UseCookies' { $mutatedHandler.UseCookies = $true }
                'AutomaticDecompression' {
                    $mutatedHandler.AutomaticDecompression = [Net.DecompressionMethods]::GZip
                }
            }
            $handlerRejected = $false
            try {
                [void](Assert-GitHubRestHandler -Handler $mutatedHandler)
            }
            catch {
                $handlerRejected = $true
            }
            Assert-Arm64 $handlerRejected `
                "weakened REST transport handler '$handlerMutation' was accepted"
        }
        finally {
            $mutatedHandler.Dispose()
        }
    }
}
finally {
    foreach ($proxyVariable in $proxyVariables) {
        [Environment]::SetEnvironmentVariable(
            $proxyVariable,
            $savedProxyValues[$proxyVariable]
        )
    }
}
Assert-Arm64 ($transportSource -notmatch '(?i)Write-(?:Output|Host|Verbose|Debug).*(?:Token|Authorization)') `
    'GitHub REST transport can log authorization material'

$missingReleaseRejected = $false
try {
    [void](Get-Arm64ReleaseBundle `
            -Repository 'example/runtime-fixture' `
            -ReleaseId 404)
}
catch {
    $missingReleaseRejected = $true
}
Assert-Arm64 $missingReleaseRejected 'missing revoked release did not fail closed'

$mockAnchor = [pscustomobject]@{
    repository = 'example/runtime-fixture'
    id = 400000001
    tag_name = 'fixture-runtime'
    immutable = $true
    draft = $false
    prerelease = $false
    published_at = '2026-08-20T00:00:00Z'
    target_commitish = 'main'
    tag_ref = [pscustomobject]@{
        type = 'tag'
        sha = '7777777777777777777777777777777777777777'
    }
    annotated_tag = [pscustomobject]@{
        object_sha = '7777777777777777777777777777777777777777'
        peeled_commit = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    }
    asset_manifest = [pscustomobject]@{
        count = 1
        sha256 = $mockBundle.asset_manifest.sha256
    }
}
foreach ($decoyMutation in @('repository', 'tag')) {
    $decoyBundle = Copy-JsonObject $mockBundle
    if ($decoyMutation -ceq 'repository') {
        $decoyBundle.repository = 'example/decoy'
    }
    else {
        $decoyBundle.tag_ref.sha = '9999999999999999999999999999999999999999'
    }
    $decoyRejected = $false
    try {
        Assert-Arm64ReleaseAnchor `
            -Anchor $mockAnchor `
            -Bundle $decoyBundle `
            -Context 'mocked revoked release'
    }
    catch {
        $decoyRejected = $true
    }
    Assert-Arm64 $decoyRejected "revocation $decoyMutation decoy passed"
}

$incompleteCompareRejected = $false
try {
    [void](Get-Arm64AncestryCheck `
            -Repository 'crutkas/msys2-runtime' `
            -RevokedCommit 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' `
            -RevokedTree 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' `
            -CandidateCommit 'dddddddddddddddddddddddddddddddddddddddd')
}
catch {
    $incompleteCompareRejected = $true
}
Assert-Arm64 $incompleteCompareRejected 'incomplete descendant comparison passed'

$protectedTamperPolicy = Copy-JsonObject $livePolicy
$protectedTamperPolicy.protected_verifier.sources.PSObject.Properties[
    '.github/scripts/parse-yaml.js'
].Value.oid = '9999999999999999999999999999999999999999'
$protectedTamperResult = Test-Arm64WorkflowTree `
    -Root $repoRoot `
    -Policy $protectedTamperPolicy `
    -Backend $semanticBackend `
    -SkipAuthoritativeSnapshot
Assert-Arm64 (-not $protectedTamperResult.Allowed) `
    'tampered protected parser identity passed'
Assert-Arm64 ($protectedTamperResult.Errors -ccontains
    'protected-source-binding-mismatch:.github/scripts/parse-yaml.js') `
    'tampered protected parser identity missed its denial'

$offlineAsts = @(
    [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $repoRoot '.github\scripts\arm64-admission.ps1'),
        [ref]$null,
        [ref]$null
    ),
    [Management.Automation.Language.Parser]::ParseFile(
        $PSCommandPath,
        [ref]$null,
        [ref]$null
    )
)
foreach ($ast in $offlineAsts) {
    foreach ($command in $ast.FindAll({
                param($node)
                return $node -is [Management.Automation.Language.CommandAst]
            }, $true)) {
        $name = $command.GetCommandName()
        if ($null -ne $name) {
            Assert-Arm64 ($name.ToLowerInvariant() -notin @(
                    'invoke-webrequest',
                    'invoke-restmethod',
                    'start-bitstransfer',
                    'curl',
                    'curl.exe',
                    'wget',
                    'wget.exe',
                    'pacman',
                    'makepkg',
                    'repo-add',
                    'msbuild',
                    'dotnet',
                    'npm',
                    'pip',
                    'git',
                    'gh'
                )) "offline test path invokes forbidden command: $name"
        }
    }
}

Write-Output "Passed $assertionCount ARM64 adversarial policy assertions."
