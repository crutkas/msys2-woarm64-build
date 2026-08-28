[CmdletBinding()]
param(
    [switch]$OfflineFixture,
    [string]$EvidencePath,
    [string]$FixturePolicyPath,
    [DateTimeOffset]$TrustedNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-Arm64Sha {
    param([object]$Value)

    return $Value -is [string] -and
        $Value -cmatch '^[0-9a-f]{40}$' -and
        $Value -cne ('0' * 40)
}

function Test-Arm64Digest {
    param([object]$Value)

    return $Value -is [string] -and
        $Value -cmatch '^sha256:[0-9a-f]{64}$' -and
        $Value -cne "sha256:$('0' * 64)"
}

function Test-Arm64Sha256 {
    param([object]$Value)

    return $Value -is [string] -and
        $Value -cmatch '^[0-9a-f]{64}$' -and
        $Value -cne ('0' * 64)
}

function Test-Arm64PositiveInteger {
    param([object]$Value)

    return ($Value -is [int] -or $Value -is [long]) -and [long]$Value -gt 0
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

    return $parsed.ToUniversalTime()
}

function Get-Arm64Property {
    param(
        [AllowNull()]
        [object]$InputObject,
        [Parameter(Mandatory)]
        [string]$Name
    )

    if ($null -eq $InputObject) {
        return $null
    }

    return $InputObject.PSObject.Properties[$Name]
}

function Get-Arm64PathValue {
    param(
        [AllowNull()]
        [object]$InputObject,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $current = $InputObject
    foreach ($segment in $Path.Split('.')) {
        $property = Get-Arm64Property -InputObject $current -Name $segment
        if ($null -eq $property) {
            return [pscustomobject]@{ Exists = $false; Value = $null }
        }
        $current = $property.Value
    }

    return [pscustomobject]@{ Exists = $true; Value = $current }
}

function Compare-Arm64ExactObject {
    param(
        [AllowNull()]
        [object]$Expected,
        [AllowNull()]
        [object]$Actual,
        [string]$Path = 'value'
    )

    $differences = [Collections.Generic.List[string]]::new()
    function Compare-Node {
        param(
            [AllowNull()]
            [object]$ExpectedNode,
            [AllowNull()]
            [object]$ActualNode,
            [string]$NodePath
        )

        if ($null -eq $ExpectedNode -or $null -eq $ActualNode) {
            if ($null -ne $ExpectedNode -or $null -ne $ActualNode) {
                [void]$differences.Add($NodePath)
            }
            return
        }

        $expectedIsMap = $ExpectedNode -is [Collections.IDictionary] -or
            $ExpectedNode -is [pscustomobject]
        $actualIsMap = $ActualNode -is [Collections.IDictionary] -or
            $ActualNode -is [pscustomobject]
        if ($expectedIsMap -or $actualIsMap) {
            if (-not ($expectedIsMap -and $actualIsMap)) {
                [void]$differences.Add($NodePath)
                return
            }

            $expectedNames = @($ExpectedNode.PSObject.Properties.Name | Sort-Object)
            $actualNames = @($ActualNode.PSObject.Properties.Name | Sort-Object)
            if (($expectedNames -join "`0") -cne ($actualNames -join "`0")) {
                [void]$differences.Add("$NodePath.properties")
                return
            }

            foreach ($name in $expectedNames) {
                Compare-Node `
                    -ExpectedNode $ExpectedNode.PSObject.Properties[$name].Value `
                    -ActualNode $ActualNode.PSObject.Properties[$name].Value `
                    -NodePath "$NodePath.$name"
            }
            return
        }

        $expectedIsList = $ExpectedNode -is [Collections.IEnumerable] -and
            $ExpectedNode -isnot [string]
        $actualIsList = $ActualNode -is [Collections.IEnumerable] -and
            $ActualNode -isnot [string]
        if ($expectedIsList -or $actualIsList) {
            if (-not ($expectedIsList -and $actualIsList)) {
                [void]$differences.Add($NodePath)
                return
            }

            $expectedItems = @($ExpectedNode)
            $actualItems = @($ActualNode)
            if ($expectedItems.Count -ne $actualItems.Count) {
                [void]$differences.Add("$NodePath.count")
                return
            }

            for ($index = 0; $index -lt $expectedItems.Count; $index++) {
                Compare-Node `
                    -ExpectedNode $expectedItems[$index] `
                    -ActualNode $actualItems[$index] `
                    -NodePath "$NodePath[$index]"
            }
            return
        }

        $expectedTimestamp = ConvertTo-Arm64Timestamp $ExpectedNode
        $actualTimestamp = ConvertTo-Arm64Timestamp $ActualNode
        if ($null -ne $expectedTimestamp -or $null -ne $actualTimestamp) {
            if ($null -eq $expectedTimestamp -or $null -eq $actualTimestamp -or
                $expectedTimestamp -ne $actualTimestamp) {
                [void]$differences.Add($NodePath)
            }
            return
        }

        if ($ExpectedNode.GetType() -ne $ActualNode.GetType() -or $ExpectedNode -cne $ActualNode) {
            [void]$differences.Add($NodePath)
        }
    }

    Compare-Node -ExpectedNode $Expected -ActualNode $Actual -NodePath $Path
    return @($differences)
}

function ConvertTo-Arm64LexicalWindowsPath {
    param([Parameter(Mandatory)][string]$Path)

    $normalized = $Path.Replace('/', '\')
    if ($normalized -cnotmatch '^[A-Za-z]:\\') {
        return $null
    }

    $segments = $normalized.Substring(3).Split(
        '\',
        [StringSplitOptions]::RemoveEmptyEntries
    )
    $clean = [Collections.Generic.List[string]]::new()
    foreach ($segment in $segments) {
        if ($segment -ceq '.') {
            continue
        }
        if ($segment -ceq '..') {
            if ($clean.Count -eq 0) {
                return $null
            }
            $clean.RemoveAt($clean.Count - 1)
            continue
        }
        $windowsSegment = $segment.TrimEnd([char[]]@(' ', '.'))
        if ([string]::IsNullOrEmpty($windowsSegment)) {
            return $null
        }
        [void]$clean.Add($windowsSegment)
    }

    $drive = $normalized.Substring(0, 1).ToUpperInvariant()
    if ($clean.Count -eq 0) {
        return "${drive}:\"
    }
    return "${drive}:\$($clean -join '\')"
}

function Test-Arm64WorkspaceEvidence {
    param(
        [Parameter(Mandatory)]
        [object]$Workspace,
        [Parameter(Mandatory)]
        [object]$Policy
    )

    $errors = [Collections.Generic.List[string]]::new()
    function Add-WorkspaceError {
        param([string]$Code)

        if (-not $errors.Contains($Code)) {
            [void]$errors.Add($Code)
        }
    }

    foreach ($path in @(
            'input_path',
            'canonical_path',
            'exists',
            'absolute',
            'final_path_resolved',
            'reparse_components',
            'volume_id')) {
        if ($null -eq (Get-Arm64Property -InputObject $Workspace -Name $path)) {
            Add-WorkspaceError "workspace-missing:$path"
        }
    }
    if ($errors.Count -ne 0) {
        return @($errors)
    }

    $inputPath = $Workspace.input_path
    $canonicalPath = $Workspace.canonical_path
    if ($inputPath -isnot [string] -or [string]::IsNullOrWhiteSpace($inputPath)) {
        Add-WorkspaceError 'workspace-input-not-string'
        return @($errors)
    }
    if ($canonicalPath -isnot [string] -or [string]::IsNullOrWhiteSpace($canonicalPath)) {
        Add-WorkspaceError 'workspace-canonical-not-string'
        return @($errors)
    }

    if ($inputPath -match '^(?:(?:\\\\|//)[?.](?:\\|/)|\\\?\?\\)') {
        Add-WorkspaceError 'workspace-device-namespace'
    }
    elseif ($inputPath -match '^(?:\\\\|//)') {
        Add-WorkspaceError 'workspace-unc'
    }

    $isWindowsPath = $inputPath -match '^[A-Za-z]:[\\/]'
    $isPosixPath = $inputPath.StartsWith('/', [StringComparison]::Ordinal)
    if (-not ($isWindowsPath -or $isPosixPath)) {
        Add-WorkspaceError 'workspace-relative'
    }
    if ($inputPath -match '(?i)(?:^|[\\/])[^\\/]*~[0-9]+(?:[\\/]|$)') {
        Add-WorkspaceError 'workspace-short-name'
    }

    if ($Workspace.exists -isnot [bool] -or -not $Workspace.exists) {
        Add-WorkspaceError 'workspace-not-existing'
    }
    if ($Workspace.absolute -isnot [bool] -or -not $Workspace.absolute) {
        Add-WorkspaceError 'workspace-not-absolute'
    }
    if ($Workspace.final_path_resolved -isnot [bool] -or -not $Workspace.final_path_resolved) {
        Add-WorkspaceError 'workspace-final-path-unresolved'
    }
    if ($Workspace.reparse_components -is [string] -or
        $Workspace.reparse_components -isnot [Collections.IEnumerable]) {
        Add-WorkspaceError 'workspace-reparse-evidence-invalid'
    }
    elseif (@($Workspace.reparse_components).Count -ne 0) {
        Add-WorkspaceError 'workspace-reparse-component'
    }
    if ($Workspace.volume_id -isnot [string] -or
        [string]::IsNullOrWhiteSpace($Workspace.volume_id)) {
        Add-WorkspaceError 'workspace-volume-missing'
    }

    if ($isWindowsPath) {
        $lexical = ConvertTo-Arm64LexicalWindowsPath -Path $inputPath
        $canonicalLexical = ConvertTo-Arm64LexicalWindowsPath -Path $canonicalPath
        if ($null -eq $lexical -or $null -eq $canonicalLexical -or
            $canonicalPath.Contains('/', [StringComparison]::Ordinal) -or
            $canonicalLexical -cne $canonicalPath) {
            Add-WorkspaceError 'workspace-canonical-invalid'
        }

        $forbidden = ConvertTo-Arm64LexicalWindowsPath -Path $Policy.workspace.forbidden_canonical_root
        foreach ($candidate in @($lexical, $canonicalLexical)) {
            if ($null -ne $candidate -and
                ($candidate.Equals($forbidden, [StringComparison]::OrdinalIgnoreCase) -or
                    $candidate.StartsWith("$forbidden\", [StringComparison]::OrdinalIgnoreCase))) {
                Add-WorkspaceError 'workspace-forbidden-root'
            }
        }
    }
    elseif ($canonicalPath -cne $inputPath -or $canonicalPath -match '/(?:\.{1,2})(?:/|$)') {
        Add-WorkspaceError 'workspace-canonical-invalid'
    }

    return @($errors)
}

function Initialize-Arm64FinalPathResolver {
    if (-not $IsWindows -or ('Arm64PathResolver' -as [type])) {
        return
    }

    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static class Arm64PathResolver
{
    private const uint FILE_SHARE_READ = 1;
    private const uint FILE_SHARE_WRITE = 2;
    private const uint FILE_SHARE_DELETE = 4;
    private const uint OPEN_EXISTING = 3;
    private const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(
        string name, uint access, uint share, IntPtr security, uint creation,
        uint flags, IntPtr template);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(
        SafeFileHandle file, StringBuilder path, uint length, uint flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool GetVolumePathNameW(
        string fileName, StringBuilder volumePath, uint length);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool GetVolumeNameForVolumeMountPointW(
        string volumePath, StringBuilder volumeName, uint length);

    public static string Resolve(string path)
    {
        using (SafeFileHandle handle = CreateFileW(
            path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            IntPtr.Zero, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, IntPtr.Zero))
        {
            if (handle.IsInvalid)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            StringBuilder buffer = new StringBuilder(32768);
            uint length = GetFinalPathNameByHandleW(handle, buffer, (uint)buffer.Capacity, 0);
            if (length == 0 || length >= buffer.Capacity)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            string result = buffer.ToString();
            return result.StartsWith(@"\\?\") ? result.Substring(4) : result;
        }
    }

    public static string GetVolumeId(string path)
    {
        StringBuilder volumePath = new StringBuilder(32768);
        if (!GetVolumePathNameW(path, volumePath, (uint)volumePath.Capacity))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        StringBuilder volumeName = new StringBuilder(32768);
        if (!GetVolumeNameForVolumeMountPointW(
            volumePath.ToString(), volumeName, (uint)volumeName.Capacity))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return volumeName.ToString();
    }
}
'@
}

function Get-Arm64CanonicalWorkspaceEvidence {
    param(
        [Parameter(Mandatory)]
        [object]$Path,
        [Parameter(Mandatory)]
        [object]$Policy
    )

    if ($Path -isnot [string] -or [string]::IsNullOrWhiteSpace($Path)) {
        throw 'Workspace path must be a non-empty string from the trusted runner context.'
    }
    if ($Path -match '^(?:(?:\\\\|//)[?.](?:\\|/)|\\\?\?\\)') {
        throw 'Workspace device namespaces are forbidden.'
    }
    if ($Path -match '^(?:\\\\|//)') {
        throw 'UNC workspaces are forbidden.'
    }
    if ($Path -match '(?i)(?:^|[\\/])[^\\/]*~[0-9]+(?:[\\/]|$)') {
        throw 'Workspace short-name aliases are forbidden.'
    }
    if (-not [IO.Path]::IsPathFullyQualified($Path)) {
        throw 'Workspace path must be absolute.'
    }
    if ($Path -match '^[A-Za-z]:[\\/]') {
        $lexical = ConvertTo-Arm64LexicalWindowsPath -Path $Path
        $forbidden = ConvertTo-Arm64LexicalWindowsPath `
            -Path $Policy.workspace.forbidden_canonical_root
        if ($null -ne $lexical -and
            ($lexical.Equals($forbidden, [StringComparison]::OrdinalIgnoreCase) -or
                $lexical.StartsWith("$forbidden\", [StringComparison]::OrdinalIgnoreCase))) {
            throw 'Workspace aliases the forbidden shared root.'
        }
    }

    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath -match '^[A-Za-z]:[\\/]') {
        $normalizedFullPath = ConvertTo-Arm64LexicalWindowsPath -Path $fullPath
        $forbidden = ConvertTo-Arm64LexicalWindowsPath `
            -Path $Policy.workspace.forbidden_canonical_root
        if ($null -ne $normalizedFullPath -and
            ($normalizedFullPath.Equals(
                    $forbidden,
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                $normalizedFullPath.StartsWith(
                    "$forbidden\",
                    [StringComparison]::OrdinalIgnoreCase
                ))) {
            throw 'Normalized workspace aliases the forbidden shared root.'
        }
    }

    $reparseComponents = [Collections.Generic.List[string]]::new()
    $root = [IO.Path]::GetPathRoot($fullPath)
    $relative = $fullPath.Substring($root.Length)
    $current = $root
    foreach ($segment in $relative.Split(
            [IO.Path]::DirectorySeparatorChar,
            [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $segment
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            [void]$reparseComponents.Add($current)
            break
        }
    }
    if ($reparseComponents.Count -ne 0) {
        throw "Workspace contains reparse components: $($reparseComponents -join ', ')"
    }

    if ($IsWindows) {
        Initialize-Arm64FinalPathResolver
        $finalPath = [Arm64PathResolver]::Resolve($fullPath).TrimEnd('\')
        $volumeId = [Arm64PathResolver]::GetVolumeId($finalPath)
    }
    else {
        $finalPath = (Resolve-Path -LiteralPath $fullPath).Path.TrimEnd('/')
        $volumeId = [IO.Path]::GetPathRoot($finalPath)
    }

    $evidence = [pscustomobject][ordered]@{
        input_path          = $Path
        canonical_path      = $finalPath
        exists             = $true
        absolute           = $true
        final_path_resolved = $true
        reparse_components = @()
        volume_id          = $volumeId
    }
    $errors = @(Test-Arm64WorkspaceEvidence -Workspace $evidence -Policy $Policy)
    if ($errors.Count -ne 0) {
        throw "Workspace rejected: $($errors -join ', ')"
    }

    return $evidence
}

function Test-Arm64AdmissionEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Evidence,
        [Parameter(Mandatory)]
        [object]$Policy,
        [Parameter(Mandatory)]
        [DateTimeOffset]$TrustedNow,
        [Parameter(Mandatory)]
        [ValidateSet('TrustedCollector', 'OfflineFixture')]
        [string]$Mode
    )

    $errors = [Collections.Generic.List[string]]::new()
    function Add-AdmissionError {
        param([string]$Code)

        if (-not $errors.Contains($Code)) {
            [void]$errors.Add($Code)
        }
    }

    if ($Mode -ceq 'OfflineFixture') {
        $fixtureOnly = Get-Arm64Property -InputObject $Policy -Name 'fixture_only'
        if ($null -eq $fixtureOnly -or $fixtureOnly.Value -isnot [bool] -or
            -not $fixtureOnly.Value) {
            Add-AdmissionError 'fixture-policy-required'
        }
        if ($Evidence.authority.kind -cne 'offline-fixture' -or
            $Evidence.authority.fixture_only -isnot [bool] -or
            -not $Evidence.authority.fixture_only) {
            Add-AdmissionError 'fixture-authority-required'
        }
    }
    else {
        $fixtureOnly = Get-Arm64Property -InputObject $Policy -Name 'fixture_only'
        if ($null -ne $fixtureOnly -and $fixtureOnly.Value) {
            Add-AdmissionError 'fixture-policy-never-live'
        }
        if ($Policy.live_admission_enabled -isnot [bool] -or
            -not $Policy.live_admission_enabled) {
            Add-AdmissionError 'live-admission-bootstrap-disabled'
        }
        if ($Evidence.authority.kind -cne $Policy.trusted_collector.authority -or
            $Evidence.authority.repository -cne $Policy.producer_repository -or
            $Evidence.authority.protected_ref -cne $Policy.protected_ref -or
            $Evidence.authority.workflow_ref -cne $Policy.trusted_collector.workflow_ref -or
            $Evidence.authority.fixture_only -isnot [bool] -or
            $Evidence.authority.fixture_only) {
            Add-AdmissionError 'untrusted-authority'
        }
    }

    if ($Evidence.schema_version -ne $Policy.schema_version) {
        Add-AdmissionError 'schema-version-mismatch'
    }

    $collectedAt = ConvertTo-Arm64Timestamp $Evidence.authority.collected_at
    if ($null -eq $collectedAt) {
        Add-AdmissionError 'invalid-collected-at'
    }
    elseif ($collectedAt -gt $TrustedNow.ToUniversalTime() -or
        $collectedAt -lt $TrustedNow.ToUniversalTime().AddMinutes(-5)) {
        Add-AdmissionError 'collector-clock-out-of-window'
    }

    foreach ($difference in Compare-Arm64ExactObject `
            -Expected $Policy.accepted_baseline `
            -Actual $Evidence.baseline `
            -Path 'baseline') {
        Add-AdmissionError "baseline-mismatch:$difference"
    }

    if (-not (Test-Arm64Sha $Evidence.baseline.annotated_tag.object_sha) -or
        -not (Test-Arm64Sha $Evidence.baseline.annotated_tag.peeled_commit)) {
        Add-AdmissionError 'baseline-tag-invalid'
    }
    if (-not (Test-Arm64PositiveInteger $Evidence.baseline.asset_manifest.count) -or
        -not (Test-Arm64Sha256 $Evidence.baseline.asset_manifest.sha256) -or
        -not (Test-Arm64PositiveInteger $Evidence.baseline.asset_manifest.required_asset.id) -or
        -not (Test-Arm64PositiveInteger $Evidence.baseline.asset_manifest.required_asset.size) -or
        -not (Test-Arm64Digest $Evidence.baseline.asset_manifest.required_asset.digest)) {
        Add-AdmissionError 'baseline-asset-manifest-invalid'
    }
    if ($Evidence.baseline.release.immutable -isnot [bool] -or
        -not $Evidence.baseline.release.immutable -or
        $Evidence.baseline.release.draft -isnot [bool] -or
        $Evidence.baseline.release.draft -or
        $Evidence.baseline.release.prerelease -isnot [bool] -or
        $Evidence.baseline.release.prerelease) {
        Add-AdmissionError 'baseline-release-not-immutable-final'
    }

    $admissionId = $Evidence.candidate.admission_id
    $admission = @($Policy.explicit_admissions | Where-Object {
            $_.admission_id -ceq $admissionId
        })
    if ($admission.Count -ne 1) {
        Add-AdmissionError 'candidate-not-explicitly-allowlisted'
    }
    else {
        foreach ($difference in Compare-Arm64ExactObject `
                -Expected $admission[0].identity `
                -Actual $Evidence.candidate.identity `
                -Path 'candidate.identity') {
            Add-AdmissionError "candidate-identity-mismatch:$difference"
        }
    }

    $identity = $Evidence.candidate.identity
    foreach ($shaPath in @(
            'producer.commit',
            'producer.tree',
            'workflow.blob',
            'run.head_sha',
            'runtime.commit')) {
        $result = Get-Arm64PathValue -InputObject $identity -Path $shaPath
        if (-not $result.Exists -or -not (Test-Arm64Sha $result.Value)) {
            Add-AdmissionError "invalid-sha:$shaPath"
        }
    }
    foreach ($integerPath in @(
            'run.id',
            'run.attempt',
            'artifact.id',
            'artifact.size',
            'runtime.release.id',
            'binutils.release.id')) {
        $result = Get-Arm64PathValue -InputObject $identity -Path $integerPath
        if (-not $result.Exists -or -not (Test-Arm64PositiveInteger $result.Value)) {
            Add-AdmissionError "invalid-integer:$integerPath"
        }
    }
    if (-not (Test-Arm64Digest $identity.artifact.digest) -or
        -not (Test-Arm64Digest $identity.binutils.package_digest)) {
        Add-AdmissionError 'invalid-candidate-digest'
    }
    if ($identity.artifact.size -le 1) {
        Add-AdmissionError 'candidate-artifact-size-invalid'
    }
    foreach ($releaseName in @('runtime', 'binutils')) {
        $release = $identity.$releaseName.release
        if ($release.immutable -isnot [bool] -or -not $release.immutable -or
            $release.draft -isnot [bool] -or $release.draft -or
            $release.prerelease -isnot [bool] -or $release.prerelease) {
            Add-AdmissionError 'candidate-release-not-immutable'
        }
        if (-not (Test-Arm64Sha $release.annotated_tag.object_sha) -or
            -not (Test-Arm64Sha $release.annotated_tag.peeled_commit)) {
            Add-AdmissionError "candidate-release-tag-invalid:$releaseName"
        }
        if (-not (Test-Arm64PositiveInteger $release.asset_manifest.count) -or
            -not (Test-Arm64Sha256 $release.asset_manifest.sha256)) {
            Add-AdmissionError "candidate-release-manifest-invalid:$releaseName"
        }
    }
    if ($identity.runtime.release.annotated_tag.peeled_commit -cne $identity.runtime.commit -or
        $identity.binutils.release.annotated_tag.peeled_commit -cne
        $identity.binutils.source_commit) {
        Add-AdmissionError 'candidate-release-peeled-commit-mismatch'
    }
    if (-not (Test-Arm64Sha $identity.binutils.source_commit) -or
        $identity.binutils.asset.digest -cne $identity.binutils.package_digest) {
        Add-AdmissionError 'candidate-binutils-identity-invalid'
    }

    $expiresAt = ConvertTo-Arm64Timestamp $identity.artifact.expires_at
    if ($null -eq $expiresAt) {
        Add-AdmissionError 'artifact-expiry-invalid'
    }
    elseif ($expiresAt -le $TrustedNow.ToUniversalTime()) {
        Add-AdmissionError 'artifact-expired'
    }

    if ($identity.producer.repository -cne $Policy.producer_repository) {
        Add-AdmissionError 'producer-repository-mismatch'
    }
    if (@($identity.producer.parents).Count -ne 1 -or
        -not (Test-Arm64Sha @($identity.producer.parents)[0])) {
        Add-AdmissionError 'synthetic-merge-producer'
    }
    if ($identity.run.ref -match '^refs/pull/[0-9]+/merge$' -or
        $identity.run.ref -cne $Policy.protected_ref -or
        $identity.run.head_sha -cne $identity.producer.commit) {
        Add-AdmissionError 'run-context-mismatch'
    }

    $message = [string]$identity.producer.commit_message
    $normalizedMessage = $message.Replace("`r`n", "`n").TrimEnd("`n")
    $terminalPair = $Policy.owned_commit_terminal_trailers -join "`n"
    if (-not $normalizedMessage.EndsWith($terminalPair, [StringComparison]::Ordinal)) {
        Add-AdmissionError 'producer-terminal-trailers-invalid'
    }
    else {
        $prefix = $normalizedMessage.Substring(0, $normalizedMessage.Length - $terminalPair.Length)
        if (-not $prefix.EndsWith("`n`n", [StringComparison]::Ordinal)) {
            Add-AdmissionError 'producer-terminal-trailers-invalid'
        }
        foreach ($trailer in $Policy.owned_commit_terminal_trailers) {
            if (@($normalizedMessage.Split("`n") | Where-Object { $_ -ceq $trailer }).Count -ne 1) {
                Add-AdmissionError 'producer-terminal-trailers-invalid'
            }
        }
    }

    foreach ($action in $identity.workflow.actions.PSObject.Properties) {
        $expectedPin = $Policy.external_action_pins.PSObject.Properties[$action.Name]
        if ($null -eq $expectedPin -or $action.Value -cne $expectedPin.Value.commit) {
            Add-AdmissionError "workflow-action-not-reviewed:$($action.Name)"
        }
    }

    if (@($Policy.revocations.runtime.release_ids) -contains [long]$identity.runtime.release.id) {
        Add-AdmissionError 'revoked-runtime-release'
    }
    if (@($Policy.revocations.binutils.release_ids) -contains [long]$identity.binutils.release.id) {
        Add-AdmissionError 'revoked-binutils-release'
    }
    if (@($Policy.revocations.binutils.package_sha256) -ccontains
        $identity.binutils.package_digest.Substring(7)) {
        Add-AdmissionError 'revoked-binutils-package'
    }

    $ancestryProperty = Get-Arm64Property `
        -InputObject $Evidence.candidate `
        -Name 'ancestry_checks'
    $ancestryChecks = @(
        if ($null -ne $ancestryProperty) {
            $ancestryProperty.Value
        }
    )
    $revokedRoots = @($Policy.revocations.runtime.commits_and_descendants)
    if ($ancestryChecks.Count -ne $revokedRoots.Count) {
        Add-AdmissionError 'runtime-ancestry-incomplete'
    }
    foreach ($revokedRoot in $revokedRoots) {
        $matches = @($ancestryChecks | Where-Object {
                $_.revoked_commit -ceq $revokedRoot -and
                $_.candidate_commit -ceq $identity.runtime.commit
            })
        if ($matches.Count -ne 1 -or
            $matches[0].query_complete -isnot [bool] -or
            -not $matches[0].query_complete) {
            Add-AdmissionError 'runtime-ancestry-incomplete'
        }
        elseif ($matches[0].is_descendant -isnot [bool] -or $matches[0].is_descendant) {
            Add-AdmissionError 'revoked-runtime-commit-or-descendant'
        }
    }

    foreach ($workspaceError in Test-Arm64WorkspaceEvidence `
            -Workspace $Evidence.candidate.workspace `
            -Policy $Policy) {
        Add-AdmissionError $workspaceError
    }

    return [pscustomobject]@{
        Allowed = $errors.Count -eq 0
        Errors  = @($errors)
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $OfflineFixture) {
        throw 'Live admission has no caller-data interface. Only the protected authoritative collector may invoke it.'
    }
    if ([string]::IsNullOrWhiteSpace($EvidencePath) -or
        [string]::IsNullOrWhiteSpace($FixturePolicyPath) -or
        $TrustedNow -eq [DateTimeOffset]::MinValue) {
        throw 'Offline fixtures require -EvidencePath, -FixturePolicyPath, and -TrustedNow.'
    }

    $evidence = Get-Content -LiteralPath $EvidencePath -Raw | ConvertFrom-Json -Depth 64
    $policy = Get-Content -LiteralPath $FixturePolicyPath -Raw | ConvertFrom-Json -Depth 64
    $result = Test-Arm64AdmissionEvidence `
        -Evidence $evidence `
        -Policy $policy `
        -TrustedNow $TrustedNow `
        -Mode OfflineFixture
    if (-not $result.Allowed) {
        foreach ($errorCode in $result.Errors) {
            [Console]::Error.WriteLine("Offline fixture denied: $errorCode")
        }
        exit 1
    }

    Write-Output 'Offline fixture accepted; this result has no live admission authority.'
}
