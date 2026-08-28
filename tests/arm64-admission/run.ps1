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
    @{ Name = 'alias'; Error = 'semantic-yaml-parse-failed:.github/workflows/test.yml' },
    @{ Name = 'yaml-merge'; Error = 'semantic-yaml-parse-failed:.github/workflows/test.yml' },
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

$semanticBackend = Resolve-Arm64YamlBackend -Requested Auto
if ($semanticBackend -ceq 'PowerShellYaml') {
    $parserCommand = Get-Command ConvertFrom-Yaml
    Assert-Arm64 ($parserCommand.Module.Version.ToString() -ceq '0.4.12') `
        'PowerShell-Yaml parser version is not exactly 0.4.12'
}
else {
    $parserVersions = & ruby -r json -r psych -e `
        'STDOUT.write(JSON.generate({"ruby"=>RUBY_VERSION,"psych"=>Psych::VERSION}))' |
        ConvertFrom-Json
    Assert-Arm64 ($parserVersions.ruby -ceq '3.2.3' -and
        $parserVersions.psych -ceq '5.1.2') `
        'Ruby/Psych parser pair is not exactly the tested lock'
}
$auditSource = Get-Content `
    -LiteralPath (Join-Path $repoRoot '.github\scripts\audit-arm64-workflows.ps1') `
    -Raw
Assert-Arm64 ($auditSource.Contains(
        'semantic-parser-differential:',
        [StringComparison]::Ordinal
    )) 'cross-backend semantic differential is not fail-closed'
$validRoot = Join-Path $workflowFixtureRoot 'valid'
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
Assert-Arm64 ($validWorkflowResult.Parser -in @('PowerShellYaml', 'RubyPsych')) `
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
    '.github/scripts/parse-yaml.rb'
].Value.oid = '9999999999999999999999999999999999999999'
$protectedTamperResult = Test-Arm64WorkflowTree `
    -Root $repoRoot `
    -Policy $protectedTamperPolicy `
    -Backend $semanticBackend `
    -SkipAuthoritativeSnapshot
Assert-Arm64 (-not $protectedTamperResult.Allowed) `
    'tampered protected parser identity passed'
Assert-Arm64 ($protectedTamperResult.Errors -ccontains
    'protected-source-binding-mismatch:.github/scripts/parse-yaml.rb') `
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
