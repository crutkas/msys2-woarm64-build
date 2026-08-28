[CmdletBinding()]
param(
    [string]$MetadataPath,
    [string]$MetadataJson,
    [string]$PolicyPath = (Join-Path (Join-Path (Join-Path $PSScriptRoot '..') 'policies') 'arm64-quarantine-policy.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Arm64JsonPath {
    param(
        [Parameter(Mandatory)]
        [object]$InputObject,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $current = $InputObject
    foreach ($segment in $Path.Split('.')) {
        if ($null -eq $current) {
            return [pscustomobject]@{ Exists = $false; Value = $null }
        }

        $property = $current.PSObject.Properties[$segment]
        if ($null -eq $property) {
            return [pscustomobject]@{ Exists = $false; Value = $null }
        }

        $current = $property.Value
    }

    return [pscustomobject]@{ Exists = $true; Value = $current }
}

function Test-Arm64Sha {
    param([object]$Value)

    return $Value -is [string] -and $Value -cmatch '^[0-9a-f]{40}$'
}

function Test-Arm64Sha256 {
    param([object]$Value)

    return $Value -is [string] -and $Value -cmatch '^[0-9a-f]{64}$'
}

function Test-Arm64PositiveInteger {
    param([object]$Value)

    return ($Value -is [int] -or $Value -is [long]) -and $Value -gt 0
}

function ConvertTo-Arm64Timestamp {
    param([object]$Value)

    if ($Value -is [DateTimeOffset]) {
        return $Value.ToUniversalTime()
    }
    if ($Value -is [DateTime]) {
        return [DateTimeOffset]$Value.ToUniversalTime()
    }
    if ($Value -isnot [string]) {
        return $null
    }

    $parsed = [DateTimeOffset]::MinValue
    $valid = [DateTimeOffset]::TryParseExact(
        $Value,
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal,
        [ref]$parsed
    )

    if (-not $valid) {
        return $null
    }

    return $parsed
}

function Test-Arm64Admission {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Metadata,
        [Parameter(Mandatory)]
        [object]$Policy
    )

    $errors = [Collections.Generic.List[string]]::new()
    function Add-AdmissionError {
        param([string]$Code)

        if (-not $errors.Contains($Code)) {
            [void]$errors.Add($Code)
        }
    }

    $requiredPaths = @(
        'schema_version',
        'admission.mode',
        'admission.evaluated_at',
        'safety.network',
        'safety.setup',
        'safety.download',
        'safety.install',
        'safety.package',
        'safety.build',
        'safety.artifact_consumption',
        'safety.payload_assembly',
        'safety.native_execution',
        'safety.release_publish',
        'safety.release_settings_change',
        'safety.candidate_output',
        'baseline.repository',
        'baseline.release.id',
        'baseline.release.immutable',
        'baseline.release.state',
        'baseline.release.draft',
        'baseline.release.prerelease',
        'baseline.release.tag_name',
        'baseline.tag.name',
        'baseline.tag.object_type',
        'baseline.tag.object_sha',
        'baseline.tag.peeled_commit',
        'baseline.asset.id',
        'baseline.asset.name',
        'baseline.asset.size',
        'baseline.asset.sha256',
        'producer.repository',
        'producer.commit',
        'producer.tree',
        'producer.parents',
        'producer.commit_message',
        'workflow.path',
        'workflow.blob',
        'workflow.actions',
        'workflow.actions.actions/checkout',
        'workflow.actions.msys2/setup-msys2',
        'workflow.actions.actions/upload-artifact',
        'workflow.actions.actions/download-artifact',
        'workflow.actions.actions/cache/restore',
        'workflow.actions.actions/cache/save',
        'workflow.actions.actions/upload-pages-artifact',
        'workflow.actions.actions/configure-pages',
        'workflow.actions.actions/deploy-pages',
        'run.id',
        'run.attempt',
        'run.job',
        'run.event_name',
        'run.ref',
        'run.head_sha',
        'artifact.id',
        'artifact.name',
        'artifact.size',
        'artifact.digest',
        'artifact.expires_at',
        'runtime.release.id',
        'runtime.release.immutable',
        'runtime.commit',
        'runtime.ancestors',
        'binutils.release.id',
        'binutils.release.immutable',
        'binutils.package_sha256',
        'revocation_checks',
        'revocation_checks.runtime_commit_and_descendants',
        'revocation_checks.runtime_release',
        'revocation_checks.binutils_release',
        'revocation_checks.binutils_package_sha256',
        'workspace.root',
        'workspace.shared_root_observed',
        'workspace.shared_root_transaction'
    )

    $values = @{}
    foreach ($path in $requiredPaths) {
        $result = Get-Arm64JsonPath -InputObject $Metadata -Path $path
        $missing = -not $result.Exists -or $null -eq $result.Value
        if (-not $missing -and $result.Value -is [string]) {
            $missing = [string]::IsNullOrWhiteSpace($result.Value)
        }

        if ($missing) {
            Add-AdmissionError "missing:$path"
        }
        else {
            $values[$path] = $result.Value
        }
    }

    if ($values.ContainsKey('schema_version') -and $values['schema_version'] -ne $Policy.schema_version) {
        Add-AdmissionError 'invalid:schema_version'
    }

    if ($values.ContainsKey('admission.mode') -and $values['admission.mode'] -cne 'metadata-only') {
        Add-AdmissionError 'invalid:admission.mode'
    }

    $safetyPaths = @(
        'safety.network',
        'safety.setup',
        'safety.download',
        'safety.install',
        'safety.package',
        'safety.build',
        'safety.artifact_consumption',
        'safety.payload_assembly',
        'safety.native_execution',
        'safety.release_publish',
        'safety.release_settings_change',
        'safety.candidate_output'
    )
    foreach ($path in $safetyPaths) {
        if ($values.ContainsKey($path) -and ($values[$path] -isnot [bool] -or $values[$path])) {
            Add-AdmissionError "operation-not-metadata-only:$path"
        }
    }

    $releasePaths = @('baseline.release', 'runtime.release', 'binutils.release')
    foreach ($releasePath in $releasePaths) {
        $immutablePath = "$releasePath.immutable"
        if ($values.ContainsKey($immutablePath) -and
            ($values[$immutablePath] -isnot [bool] -or -not $values[$immutablePath])) {
            Add-AdmissionError "release-not-immutable:$releasePath"
        }
    }

    if ($values.ContainsKey('baseline.repository') -and
        $values['baseline.repository'] -cne $Policy.accepted_baseline.repository) {
        Add-AdmissionError 'baseline-mismatch:repository'
    }
    if ($values.ContainsKey('baseline.release.id')) {
        if (-not (Test-Arm64PositiveInteger $values['baseline.release.id'])) {
            Add-AdmissionError 'invalid:baseline.release.id'
        }
        elseif ([long]$values['baseline.release.id'] -ne [long]$Policy.accepted_baseline.release_id) {
            Add-AdmissionError 'baseline-mismatch:release.id'
        }
    }
    if ($values.ContainsKey('baseline.release.state') -and $values['baseline.release.state'] -cne 'released') {
        Add-AdmissionError 'baseline-not-released'
    }
    if ($values.ContainsKey('baseline.release.draft') -and
        ($values['baseline.release.draft'] -isnot [bool] -or $values['baseline.release.draft'])) {
        Add-AdmissionError 'baseline-draft'
    }
    if ($values.ContainsKey('baseline.release.prerelease') -and
        ($values['baseline.release.prerelease'] -isnot [bool] -or $values['baseline.release.prerelease'])) {
        Add-AdmissionError 'baseline-prerelease'
    }
    foreach ($tagPath in @('baseline.release.tag_name', 'baseline.tag.name')) {
        if ($values.ContainsKey($tagPath) -and $values[$tagPath] -cne $Policy.accepted_baseline.tag_name) {
            Add-AdmissionError "baseline-mismatch:$tagPath"
        }
    }
    if ($values.ContainsKey('baseline.tag.object_type') -and $values['baseline.tag.object_type'] -cne 'tag') {
        Add-AdmissionError 'baseline-tag-not-annotated'
    }
    foreach ($shaPath in @('baseline.tag.object_sha', 'baseline.tag.peeled_commit')) {
        if ($values.ContainsKey($shaPath) -and -not (Test-Arm64Sha $values[$shaPath])) {
            Add-AdmissionError "invalid:$shaPath"
        }
    }
    if ($values.ContainsKey('baseline.asset.id')) {
        if (-not (Test-Arm64PositiveInteger $values['baseline.asset.id'])) {
            Add-AdmissionError 'invalid:baseline.asset.id'
        }
        elseif ([long]$values['baseline.asset.id'] -ne [long]$Policy.accepted_baseline.asset_id) {
            Add-AdmissionError 'baseline-mismatch:asset.id'
        }
    }
    if ($values.ContainsKey('baseline.asset.size')) {
        if (-not (Test-Arm64PositiveInteger $values['baseline.asset.size'])) {
            Add-AdmissionError 'invalid:baseline.asset.size'
        }
        elseif ([long]$values['baseline.asset.size'] -ne [long]$Policy.accepted_baseline.asset_size) {
            Add-AdmissionError 'baseline-mismatch:asset.size'
        }
    }
    if ($values.ContainsKey('baseline.asset.sha256') -and
        $values['baseline.asset.sha256'] -cne $Policy.accepted_baseline.asset_sha256) {
        Add-AdmissionError 'baseline-mismatch:asset.sha256'
    }

    if ($values.ContainsKey('producer.repository') -and
        $values['producer.repository'] -cne $Policy.producer_repository) {
        Add-AdmissionError 'producer-repository-not-allowed'
    }
    foreach ($shaPath in @('producer.commit', 'producer.tree')) {
        if ($values.ContainsKey($shaPath) -and -not (Test-Arm64Sha $values[$shaPath])) {
            Add-AdmissionError "invalid:$shaPath"
        }
    }
    if ($values.ContainsKey('producer.parents')) {
        $parents = $values['producer.parents']
        if ($parents -is [string] -or $parents -isnot [Collections.IEnumerable]) {
            Add-AdmissionError 'invalid:producer.parents'
        }
        else {
            $parentList = @($parents)
            if ($parentList.Count -ne 1) {
                Add-AdmissionError 'synthetic-merge:producer.parents'
            }
            elseif (-not (Test-Arm64Sha $parentList[0])) {
                Add-AdmissionError 'invalid:producer.parents'
            }
        }
    }

    if ($values.ContainsKey('producer.commit_message')) {
        $message = $values['producer.commit_message'].Replace("`r`n", "`n")
        if ($message.EndsWith("`n")) {
            $message = $message.Substring(0, $message.Length - 1)
        }

        $terminalPair = $Policy.owned_commit_terminal_trailers -join "`n"
        $pairValid = $message.EndsWith($terminalPair, [StringComparison]::Ordinal)
        if ($pairValid) {
            $prefix = $message.Substring(0, $message.Length - $terminalPair.Length)
            $pairValid = $prefix.EndsWith("`n`n", [StringComparison]::Ordinal)
        }

        foreach ($trailer in $Policy.owned_commit_terminal_trailers) {
            $occurrences = @($message.Split("`n") | Where-Object { $_ -ceq $trailer }).Count
            if ($occurrences -ne 1) {
                $pairValid = $false
            }
        }

        if (-not $pairValid) {
            Add-AdmissionError 'producer-trailer-pair-invalid'
        }
    }

    if ($values.ContainsKey('workflow.path') -and
        $values['workflow.path'] -cne $Policy.admission_workflow.path) {
        Add-AdmissionError 'workflow-mismatch:path'
    }
    if ($values.ContainsKey('workflow.blob')) {
        if (-not (Test-Arm64Sha $values['workflow.blob'])) {
            Add-AdmissionError 'invalid:workflow.blob'
        }
        elseif ($values['workflow.blob'] -cne $Policy.admission_workflow.blob) {
            Add-AdmissionError 'workflow-mismatch:blob'
        }
    }
    if ($values.ContainsKey('workflow.actions')) {
        $metadataActions = $values['workflow.actions']
        foreach ($expectedAction in $Policy.external_action_pins.PSObject.Properties) {
            $actualAction = $metadataActions.PSObject.Properties[$expectedAction.Name]
            if ($null -ne $actualAction -and $actualAction.Value -cne $expectedAction.Value) {
                Add-AdmissionError "action-pin-mismatch:$($expectedAction.Name)"
            }
        }
        foreach ($actualAction in $metadataActions.PSObject.Properties) {
            if ($null -eq $Policy.external_action_pins.PSObject.Properties[$actualAction.Name]) {
                Add-AdmissionError "action-unreviewed:$($actualAction.Name)"
            }
        }
    }

    foreach ($integerPath in @('run.id', 'run.attempt', 'artifact.id', 'artifact.size',
            'runtime.release.id', 'binutils.release.id')) {
        if ($values.ContainsKey($integerPath) -and -not (Test-Arm64PositiveInteger $values[$integerPath])) {
            Add-AdmissionError "invalid:$integerPath"
        }
    }
    if ($values.ContainsKey('run.job') -and $values['run.job'] -cne $Policy.admission_workflow.job) {
        Add-AdmissionError 'run-mismatch:job'
    }
    if ($values.ContainsKey('run.event_name') -and $values['run.event_name'] -cne 'workflow_dispatch') {
        Add-AdmissionError 'synthetic-merge:event'
    }
    if ($values.ContainsKey('run.ref')) {
        if ($values['run.ref'] -match '^refs/pull/[0-9]+/merge$') {
            Add-AdmissionError 'synthetic-merge:ref'
        }
        elseif ($values['run.ref'] -cne $Policy.admission_workflow.ref) {
            Add-AdmissionError 'run-mismatch:ref'
        }
    }
    if ($values.ContainsKey('run.head_sha')) {
        if (-not (Test-Arm64Sha $values['run.head_sha'])) {
            Add-AdmissionError 'invalid:run.head_sha'
        }
        elseif ($values.ContainsKey('producer.commit') -and
            $values['run.head_sha'] -cne $values['producer.commit']) {
            Add-AdmissionError 'producer-head-mismatch'
        }
    }

    if ($values.ContainsKey('artifact.name') -and $values['artifact.name'] -cne $Policy.artifact_name) {
        Add-AdmissionError 'artifact-mismatch:name'
    }
    if ($values.ContainsKey('artifact.digest') -and
        ($values['artifact.digest'] -isnot [string] -or
            $values['artifact.digest'] -cnotmatch '^sha256:[0-9a-f]{64}$')) {
        Add-AdmissionError 'invalid:artifact.digest'
    }
    if ($values.ContainsKey('admission.evaluated_at') -and $values.ContainsKey('artifact.expires_at')) {
        $evaluatedAt = ConvertTo-Arm64Timestamp $values['admission.evaluated_at']
        $expiresAt = ConvertTo-Arm64Timestamp $values['artifact.expires_at']
        if ($null -eq $evaluatedAt) {
            Add-AdmissionError 'invalid:admission.evaluated_at'
        }
        if ($null -eq $expiresAt) {
            Add-AdmissionError 'invalid:artifact.expires_at'
        }
        elseif ($null -ne $evaluatedAt -and $expiresAt -le $evaluatedAt) {
            Add-AdmissionError 'artifact-expired'
        }
    }

    if ($values.ContainsKey('runtime.commit')) {
        if (-not (Test-Arm64Sha $values['runtime.commit'])) {
            Add-AdmissionError 'invalid:runtime.commit'
        }
        elseif (@($Policy.revocations.runtime.commits_and_descendants) -ccontains $values['runtime.commit']) {
            Add-AdmissionError 'revoked:runtime-commit'
        }
    }
    if ($values.ContainsKey('runtime.ancestors')) {
        $ancestors = $values['runtime.ancestors']
        if ($ancestors -is [string] -or $ancestors -isnot [Collections.IEnumerable]) {
            Add-AdmissionError 'invalid:runtime.ancestors'
        }
        else {
            foreach ($ancestor in @($ancestors)) {
                if (-not (Test-Arm64Sha $ancestor)) {
                    Add-AdmissionError 'invalid:runtime.ancestors'
                }
                elseif (@($Policy.revocations.runtime.commits_and_descendants) -ccontains $ancestor) {
                    Add-AdmissionError 'revoked:runtime-commit-descendant'
                }
            }
        }
    }
    if ($values.ContainsKey('runtime.release.id') -and
        (Test-Arm64PositiveInteger $values['runtime.release.id']) -and
        @($Policy.revocations.runtime.release_ids) -contains [long]$values['runtime.release.id']) {
        Add-AdmissionError 'revoked:runtime-release'
    }
    if ($values.ContainsKey('binutils.release.id') -and
        (Test-Arm64PositiveInteger $values['binutils.release.id']) -and
        @($Policy.revocations.binutils.release_ids) -contains [long]$values['binutils.release.id']) {
        Add-AdmissionError 'revoked:binutils-release'
    }
    if ($values.ContainsKey('binutils.package_sha256')) {
        if (-not (Test-Arm64Sha256 $values['binutils.package_sha256'])) {
            Add-AdmissionError 'invalid:binutils.package_sha256'
        }
        elseif (@($Policy.revocations.binutils.package_sha256) -ccontains
            $values['binutils.package_sha256']) {
            Add-AdmissionError 'revoked:binutils-package'
        }
    }

    foreach ($checkName in @(
            'runtime_commit_and_descendants',
            'runtime_release',
            'binutils_release',
            'binutils_package_sha256')) {
        $checkPath = "revocation_checks.$checkName"
        if ($values.ContainsKey($checkPath) -and
            ($values[$checkPath] -isnot [bool] -or -not $values[$checkPath])) {
            Add-AdmissionError "revocation-check-not-complete:$checkName"
        }
    }

    if ($values.ContainsKey('workspace.root')) {
        $escapedSharedRoot = [regex]::Escape($Policy.forbidden_shared_root)
        if ($values['workspace.root'] -match "(?i)^$escapedSharedRoot(?:\\|$)") {
            Add-AdmissionError 'shared-root:workspace'
        }
    }
    if ($values.ContainsKey('workspace.shared_root_observed') -and
        ($values['workspace.shared_root_observed'] -isnot [bool] -or
            $values['workspace.shared_root_observed'])) {
        Add-AdmissionError 'shared-root:observed'
    }
    if ($values.ContainsKey('workspace.shared_root_transaction') -and
        ($values['workspace.shared_root_transaction'] -isnot [bool] -or
            $values['workspace.shared_root_transaction'])) {
        Add-AdmissionError 'shared-root:transaction'
    }

    return [pscustomobject]@{
        Allowed = $errors.Count -eq 0
        Errors  = @($errors)
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $hasPath = -not [string]::IsNullOrWhiteSpace($MetadataPath)
    $hasJson = -not [string]::IsNullOrWhiteSpace($MetadataJson)
    if ($hasPath -eq $hasJson) {
        throw 'Specify exactly one of -MetadataPath or -MetadataJson.'
    }

    $policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json -Depth 32
    $metadata = if ($hasPath) {
        Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json -Depth 32
    }
    else {
        $MetadataJson | ConvertFrom-Json -Depth 32
    }

    $result = Test-Arm64Admission -Metadata $metadata -Policy $policy
    if (-not $result.Allowed) {
        foreach ($code in $result.Errors) {
            [Console]::Error.WriteLine("ARM64 admission denied: $code")
        }
        exit 1
    }

    Write-Output 'ARM64 admission metadata accepted.'
}
