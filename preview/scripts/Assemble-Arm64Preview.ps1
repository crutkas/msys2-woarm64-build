[CmdletBinding()]
param(
    [string] $LockPath = (Join-Path $PSScriptRoot '..\locks\portable-git-arm64-preview.v1.json'),
    [Parameter(Mandatory = $true)][string] $OutputRoot,
    [Parameter(Mandatory = $true)][string] $CacheDirectory,
    [Parameter(Mandatory = $true)][string] $WorkDirectory,
    [switch] $ValidateLockOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Preview.Common.psm1') -Force
$previewId = 'portable-git-arm64-preview-1'

function Get-SharedRootObservation {
    $logPath = 'C:\msys64\var\log\pacman.log'
    $dbPath = 'C:\msys64\var\lib\pacman\local'
    if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
        throw "Shared pacman log is absent; full external observation is impossible"
    }
    $database = Get-CanonicalDirectoryManifest -Root $dbPath
    return [ordered]@{
        log = [ordered]@{
            bytes = (Get-Item -LiteralPath $logPath).Length
            sha256 = Get-Sha256 -Path $logPath
        }
        database = $database
    }
}

function Test-SharedObservationEqual {
    param(
        [Parameter(Mandatory = $true)] $Before,
        [Parameter(Mandatory = $true)] $After
    )
    return (($Before | ConvertTo-Json -Compress -Depth 8) -ceq
        ($After | ConvertTo-Json -Compress -Depth 8))
}

function Initialize-PrivateCache {
    param([Parameter(Mandatory = $true)][string] $Path)

    $markerName = '.arm64-preview-private-cache.v1'
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    $marker = Join-Path $Path $markerName
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        $existing = @(Get-ChildItem -LiteralPath $Path -Force)
        if ($existing.Count -ne 0) {
            throw "CacheDirectory is not empty and lacks the private preview cache marker: $Path"
        }
        'portable-git-arm64-preview-cache-v1' |
            Set-Content -LiteralPath $marker -Encoding ascii -NoNewline
    }
    $markerValue = Get-Content -LiteralPath $marker -Raw -Encoding ascii
    if ($markerValue -cne 'portable-git-arm64-preview-cache-v1') {
        throw "CacheDirectory has an invalid private preview cache marker: $Path"
    }
}

function Get-FinalFileSystemPath {
    param([Parameter(Mandatory = $true)][string] $Path)

    if (-not ('PreviewNativePath' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static class PreviewNativePath
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle, StringBuilder path, uint pathLength, uint flags);
}
'@
    }
    $stream = [IO.File]::Open(
        $Path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        $buffer = [Text.StringBuilder]::new(32768)
        $length = [PreviewNativePath]::GetFinalPathNameByHandle(
            $stream.SafeFileHandle, $buffer, [uint32]$buffer.Capacity, 0)
        if ($length -eq 0 -or $length -ge $buffer.Capacity) {
            throw "Unable to resolve final filesystem path for '$Path'"
        }
        $finalPath = $buffer.ToString()
        if ($finalPath.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
            return '\\' + $finalPath.Substring(8)
        }
        if ($finalPath.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
            return $finalPath.Substring(4)
        }
        return $finalPath
    }
    finally {
        $stream.Dispose()
    }
}

function Copy-GitBlob {
    param(
        [Parameter(Mandatory = $true)][string] $GitPath,
        [Parameter(Mandatory = $true)][string] $RepositoryRoot,
        [Parameter(Mandatory = $true)][string] $Commit,
        [Parameter(Mandatory = $true)][string] $SourcePath,
        [Parameter(Mandatory = $true)][string] $Destination
    )

    $gitPath = $SourcePath.Replace('\', '/')
    if ((ConvertTo-SafeArchivePath -Member $gitPath) -cne $gitPath) {
        throw "Git blob source path is unsafe: $SourcePath"
    }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $GitPath
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @('-C', $RepositoryRoot, 'cat-file', 'blob', "${Commit}:$gitPath")) {
        $info.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) {
        throw "Unable to start git while materializing '$gitPath'"
    }
    $stderrTask = $process.StandardError.ReadToEndAsync()
    try {
        $parent = [IO.Path]::GetDirectoryName($Destination)
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $output = [IO.File]::Open(
            $Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $process.StandardOutput.BaseStream.CopyTo($output)
        }
        finally {
            $output.Dispose()
        }
        $process.WaitForExit()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Unable to materialize committed git blob '$gitPath': $stderr"
        }
    }
    finally {
        $process.Dispose()
        if ($null -ne $stderrTask -and -not $stderrTask.IsCompleted) {
            $stderrTask.GetAwaiter().GetResult() | Out-Null
        }
    }
}

function Get-OrdinalSortedStrings {
    param([object[]] $Values)
    $strings = @($Values | ForEach-Object { [string]$_ })
    [Array]::Sort($strings, [StringComparer]::Ordinal)
    return $strings
}

function Get-VerifiedTreeMembers {
    param(
        [Parameter(Mandatory = $true)][string] $Root,
        [Parameter(Mandatory = $true)][object[]] $ArchiveMembers
    )

    $byPath = @{}
    foreach ($archiveMember in $ArchiveMembers) {
        $path = [string]$archiveMember.path
        if ($byPath.ContainsKey($path)) {
            throw "Tree contains a duplicate member path: $path"
        }
        $item = Get-Item -LiteralPath (Join-Path $Root $path.Replace('/', '\')) -Force
        $type = [string]$archiveMember.type
        $byPath[$path] = [ordered]@{
            path = $path
            type = $type
            bytes = if ($type -eq 'directory') { 0 } else { $item.Length }
            sha256 = if ($type -eq 'directory') { $null } else { Get-Sha256 -Path $item.FullName }
            linkTarget = if ($type -in @('symlink', 'hardlink')) {
                Resolve-ManifestLinkTarget -MemberPath $path -LinkTarget ([string]$archiveMember.target) -Type $type
            } else {
                $null
            }
        }
    }
    $paths = [string[]]@($byPath.Keys)
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    return @($paths | ForEach-Object { $byPath[$_] })
}

function Get-DirectInputMember {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][string] $Path
    )

    $memberPath = if ($null -ne $InputEntry.identity.PSObject.Properties['sourcePath']) {
        [string]$InputEntry.identity.sourcePath
    } else {
        [string]$InputEntry.asset.name
    }
    [ordered]@{
        path = ConvertTo-SafeArchivePath -Member $memberPath
        type = 'file'
        bytes = (Get-Item -LiteralPath $Path).Length
        sha256 = Get-Sha256 -Path $Path
        linkTarget = $null
    }
}

function Resolve-ManifestLinkTarget {
    param(
        [Parameter(Mandatory = $true)][string] $MemberPath,
        [Parameter(Mandatory = $true)][string] $LinkTarget,
        [ValidateSet('symlink', 'hardlink')][string] $Type = 'symlink'
    )

    $anchor = 'C:\preview-manifest-root'
    $target = $LinkTarget.Replace('\', '/')
    $candidate = if ($Type -eq 'hardlink' -or $target.StartsWith('/', [StringComparison]::Ordinal)) {
        Join-Path $anchor $target.TrimStart('/').Replace('/', '\')
    } else {
        Join-Path (Join-Path $anchor ([IO.Path]::GetDirectoryName($MemberPath.Replace('/', '\')))) `
            $target.Replace('/', '\')
    }
    $resolved = [IO.Path]::GetFullPath($candidate)
    if (-not $resolved.StartsWith("$anchor\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest link target escapes its input root: $MemberPath -> $LinkTarget"
    }
    return ConvertTo-SafeArchivePath -Member (
        [IO.Path]::GetRelativePath($anchor, $resolved).Replace('\', '/')
    )
}

function Copy-VerifiedRawInput {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][string] $VerifiedPath,
        [Parameter(Mandatory = $true)][string] $DestinationRoot
    )

    $sourcePath = ConvertTo-SafeArchivePath -Member ([string]$InputEntry.identity.sourcePath)
    $destination = Join-Path $DestinationRoot $sourcePath.Replace('/', '\')
    if (Test-Path -LiteralPath $destination) {
        throw "Validation input destination collides with an existing path: $sourcePath"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $VerifiedPath -Destination $destination
    if ((Get-Item -LiteralPath $destination).Length -ne [Int64]$InputEntry.asset.expectedBytes -or
        (Get-Sha256 -Path $destination) -cne [string]$InputEntry.asset.sha256) {
        throw "Materialized validation input failed immutable verification: $($InputEntry.id)"
    }
    return $destination
}

function Sort-ObjectsOrdinal {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]] $Items,
        [Parameter(Mandatory = $true)][string[]] $Properties
    )

    $result = [object[]]@($Items)
    $comparison = [Comparison[object]]{
        param($left, $right)
        foreach ($property in $Properties) {
            $order = [StringComparer]::Ordinal.Compare(
                [string]$left.$property,
                [string]$right.$property)
            if ($order -ne 0) {
                return $order
            }
        }
        return 0
    }
    [Array]::Sort($result, $comparison)
    return @($result)
}

function Get-OverlaySelection {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][object[]] $ArchiveMembers
    )

    if (-not $InputEntry.overlay.enabled) {
        return @()
    }
    $memberByPath = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($member in $ArchiveMembers) {
        if (-not $memberByPath.TryAdd([string]$member.path, $member)) {
            throw "Input '$($InputEntry.id)' has duplicate or case-colliding archive members"
        }
    }
    $selectedSources = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    $selectedDestinations = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    $selection = [Collections.Generic.List[object]]::new()
    foreach ($mapping in @($InputEntry.overlay.mappings)) {
        $source = ConvertTo-SafeArchivePath -Member ([string]$mapping.source)
        $destination = ConvertTo-SafeArchivePath -Member ([string]$mapping.destination)
        $sourceMembers = if ($source -ceq '.') {
            @($ArchiveMembers)
        } else {
            if (-not $memberByPath.ContainsKey($source)) {
                throw "Overlay source '$source' is absent from '$($InputEntry.id)'"
            }
            $sourceEntry = $memberByPath[$source]
            if ([string]$sourceEntry.type -ceq 'directory') {
                @($ArchiveMembers | Where-Object {
                    [string]$_.path -ceq $source -or
                    ([string]$_.path).StartsWith("$source/", [StringComparison]::Ordinal)
                })
            } else {
                @($sourceEntry)
            }
        }
        foreach ($member in $sourceMembers) {
            $sourceMember = [string]$member.path
            $suffix = if ($source -ceq '.') {
                $sourceMember
            } elseif ($sourceMember -ceq $source) {
                ''
            } else {
                $sourceMember.Substring($source.Length + 1)
            }
            $destinationPath = if ($destination -ceq '.') {
                if ([string]::IsNullOrEmpty($suffix)) { '.' } else { $suffix }
            } elseif ([string]::IsNullOrEmpty($suffix)) {
                $destination
            } else {
                "$destination/$suffix"
            }
            $destinationPath = ConvertTo-SafeArchivePath -Member $destinationPath
            if (-not $selectedSources.Add($sourceMember)) {
                throw "Input '$($InputEntry.id)' selects archive member '$sourceMember' more than once"
            }
            if (-not $selectedDestinations.Add($destinationPath)) {
                throw "Input '$($InputEntry.id)' maps multiple members to '$destinationPath'"
            }
            $selection.Add([ordered]@{
                sourceMember = $sourceMember
                destinationPath = $destinationPath
                type = $member.type
                bytes = $member.bytes
                sha256 = $member.sha256
                linkTarget = $member.linkTarget
                allowOverwrite = [bool]$mapping.allowOverwrite
            })
        }
    }
    return @(Sort-ObjectsOrdinal -Items @($selection) -Properties @('sourceMember', 'destinationPath'))
}

function Write-CanonicalBundleLock {
    param(
        [Parameter(Mandatory = $true)] $SourceLock,
        [Parameter(Mandatory = $true)][string] $SourceLockPath,
        [Parameter(Mandatory = $true)] $OverlaySelectionsByInput,
        [Parameter(Mandatory = $true)][string] $OutputPath
    )

    $inputIds = Get-OrdinalSortedStrings @($SourceLock.inputs.id)
    $canonicalInputs = @($inputIds | ForEach-Object {
        $input = @($SourceLock.inputs | Where-Object id -ceq $_)[0]
        if ($input.status -eq 'unresolved') {
            return [ordered]@{
                id = $input.id
                role = if ($input.role -eq 'native-shell-package') { 'payload' } else { 'validation-tool' }
                status = 'unresolved'
                resolution = $null
                release = $null
                asset = $null
                package = $null
                overlay = $null
            }
        }
        $sourcePathProperty = $input.identity.PSObject.Properties['sourcePath']
        $isRawCommit = $null -ne $sourcePathProperty
        $canonicalRole = if ($input.role -eq 'base') {
            'base-bundle'
        } elseif ($input.overlay.enabled) {
            'payload'
        } else {
            'validation-tool'
        }
        $selections = if ($OverlaySelectionsByInput.ContainsKey([string]$input.id)) {
            @($OverlaySelectionsByInput[$input.id])
        } else {
            @()
        }
        $canonicalMappings = @($selections | ForEach-Object {
            [ordered]@{
                sourceMember = $_.sourceMember
                destinationPath = $_.destinationPath
            }
        })
        $canonicalPackage = $null
        if ($null -ne $input.package -and $canonicalRole -eq 'payload') {
            $canonicalPackage = [ordered]@{
                name = $input.package.name
                version = $input.package.version
                personality = if ($canonicalRole -eq 'validation-tool') {
                    'tool'
                } elseif ([string]$input.package.name -like 'mingw-*') {
                    'mingw'
                } else {
                    'msys'
                }
                provides = Get-OrdinalSortedStrings @($selections.destinationPath)
            }
        }
        [ordered]@{
            id = $input.id
            role = $canonicalRole
            status = 'resolved'
            resolution = [ordered]@{
                method = if ($isRawCommit) { 'github-raw-commit' } else { 'github-release' }
            }
            release = if ($isRawCommit) {
                [ordered]@{
                    repository = $input.identity.repository
                    targetCommit = $input.identity.commit
                    sourcePath = $sourcePathProperty.Value
                }
            } else {
                [ordered]@{
                    repository = $input.identity.repository
                    tag = $input.identity.tag
                    targetCommit = $input.identity.commit
                }
            }
            asset = [ordered]@{
                url = $input.asset.url
                name = $input.asset.name
                bytes = [Int64]$input.asset.expectedBytes
                sha256 = $input.asset.sha256
            }
            package = $canonicalPackage
            overlay = [ordered]@{
                enabled = [bool]$input.overlay.enabled
                destination = if ($input.overlay.enabled) { '.' } else { $null }
                include = if ($input.overlay.enabled) {
                    Get-OrdinalSortedStrings @($selections.sourceMember)
                } else {
                    @()
                }
                exclude = @()
                mappings = $canonicalMappings
            }
        }
    })
    $document = [ordered]@{
        schemaVersion = 1
        sourceLock = [ordered]@{
            path = 'preview-evidence/source-lock.json'
            sha256 = Get-Sha256 -Path $SourceLockPath
        }
        sourceDateEpoch = [Int64]$SourceLock.sourceDateEpoch
        nativeShellClosure = Get-OrdinalSortedStrings @($SourceLock.nativeShellClosure)
        inputs = $canonicalInputs
    }
    $json = ($document | ConvertTo-Json -Depth 15).Replace("`r`n", "`n") + "`n"
    [IO.File]::WriteAllText($OutputPath, $json, [Text.UTF8Encoding]::new($false))
}

function Assert-PackageMetadata {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][string] $PackageRoot
    )
    $metadataPath = Join-Path $PackageRoot '.PKGINFO'
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        throw "Package '$($InputEntry.id)' has no readable .PKGINFO"
    }
    $lines = @(Get-Content -LiteralPath $metadataPath -Encoding utf8)
    $name = @($lines | Where-Object { $_ -match '^pkgname = ' } | ForEach-Object { $_ -replace '^pkgname = ', '' })
    $version = @($lines | Where-Object { $_ -match '^pkgver = ' } | ForEach-Object { $_ -replace '^pkgver = ', '' })
    $provides = @($lines | Where-Object { $_ -match '^provides = ' } | ForEach-Object { $_ -replace '^provides = ', '' })
    if ($name.Count -ne 1 -or $name[0] -ne $InputEntry.package.name) {
        throw "Package name mismatch for '$($InputEntry.id)'"
    }

    if ($version.Count -ne 1 -or $version[0] -ne $InputEntry.package.version) {
        throw "Package version mismatch for '$($InputEntry.id)'"
    }
    $expectedProvides = @(Get-OrdinalSortedStrings @($InputEntry.package.provides))
    $actualProvides = @(Get-OrdinalSortedStrings @($provides))
    if (($expectedProvides -join "`n") -cne ($actualProvides -join "`n")) {
        throw "Package provides mismatch for '$($InputEntry.id)'"
    }
}

function Assert-PinnedMembers {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][string] $ExtractedRoot
    )
    if ($null -eq $InputEntry.asset.PSObject.Properties['members']) {
        return
    }
    foreach ($member in @($InputEntry.asset.members)) {
        $safePath = ConvertTo-SafeArchivePath -Member ([string]$member.path)
        $path = Join-Path $ExtractedRoot $safePath.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Pinned member '$($InputEntry.id):$safePath' is missing"
        }
        $bytes = (Get-Item -LiteralPath $path).Length
        $hash = Get-Sha256 -Path $path
        if ($bytes -ne [Int64]$member.expectedBytes -or $hash -ne [string]$member.sha256) {
            throw "Pinned member '$($InputEntry.id):$safePath' failed size/SHA-256 verification"
        }
    }
}

function Copy-OverlayMapping {
    param(
        [Parameter(Mandatory = $true)][string] $StagingRoot,
        [Parameter(Mandatory = $true)][string] $PortableRoot,
        [Parameter(Mandatory = $true)] $Mapping,
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)] $Ownership,
        [Parameter(Mandatory = $true)] $ReplacementRecords
    )

    $safeSource = ConvertTo-SafeArchivePath -Member ([string]$Mapping.source)
    $safeDestination = ConvertTo-SafeArchivePath -Member ([string]$Mapping.destination)
    $source = if ($safeSource -eq '.') { $StagingRoot } else { Join-Path $StagingRoot $safeSource.Replace('/', '\') }
    $destination = if ($safeDestination -eq '.') { $PortableRoot } else { Join-Path $PortableRoot $safeDestination.Replace('/', '\') }
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Declared overlay source is absent for '$($InputEntry.id)': $($Mapping.source)"
    }

    $sourceItem = Get-Item -LiteralPath $source -Force
    $sourceIsDirectory = $sourceItem.PSIsContainer -and
        -not ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint)
    $items = if ($sourceIsDirectory) {
        @($sourceItem) + @(Get-ChildItem -LiteralPath $source -Force -Recurse)
    } else {
        @($sourceItem)
    }
    foreach ($item in $items) {
        $relative = if ($sourceIsDirectory) {
            [IO.Path]::GetRelativePath($source, $item.FullName)
        } else {
            ''
        }
        $target = if ([string]::IsNullOrEmpty($relative) -or $relative -eq '.') {
            $destination
        } else {
            Join-Path $destination $relative
        }
        $payloadPath = Get-RelativeUnixPath -Root $PortableRoot -Path $target
        $exists = Test-Path -LiteralPath $target
        $sourceMember = Get-RelativeUnixPath -Root $StagingRoot -Path $item.FullName

        if ($item.PSIsContainer -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            if ($exists -and -not (Get-Item -LiteralPath $target -Force).PSIsContainer) {
                throw "Overlay directory collides with file '$payloadPath'"
            }
            if ($exists -and $payloadPath -cne '.' -and -not [bool]$Mapping.allowOverwrite) {
                throw "Unexpected overlay directory overwrite by '$($InputEntry.id)': $payloadPath"
            }
            if (-not $exists) {
                New-Item -ItemType Directory -Path $target | Out-Null
            }
            if ($exists -and $payloadPath -cne '.') {
                $previousOwner = $Ownership[$payloadPath]
                if ($null -eq $previousOwner) {
                    throw "Overlay directory replacement has no previous source owner: $payloadPath"
                }
                $ReplacementRecords.Add([ordered]@{
                    destinationPath = $payloadPath
                    replacedInputId = $previousOwner.inputId
                    replacedSourceMember = $previousOwner.sourceMember
                    winnerInputId = $InputEntry.id
                    winnerSourceMember = $sourceMember
                })
            }
            $Ownership[$payloadPath] = [ordered]@{
                inputId = $InputEntry.id
                package = if ($null -ne $InputEntry.package) { $InputEntry.package.name } else { $null }
                packageVersion = if ($null -ne $InputEntry.package) { $InputEntry.package.version } else { $null }
                sourceMember = $sourceMember
            }
            continue
        }
        if ($exists -and -not [bool]$Mapping.allowOverwrite) {
            throw "Unexpected overlay overwrite by '$($InputEntry.id)': $payloadPath"
        }
        if ($item.LinkType -eq 'HardLink') {
            throw "Declared overlay contains a hard link whose identity cannot be preserved safely: $($item.FullName)"
        }
        if ($exists) {
            $previousOwner = $Ownership[$payloadPath]
            if ($null -eq $previousOwner) {
                throw "Overlay replacement has no previous source owner: $payloadPath"
            }
            $ReplacementRecords.Add([ordered]@{
                destinationPath = $payloadPath
                replacedInputId = $previousOwner.inputId
                replacedSourceMember = $previousOwner.sourceMember
                winnerInputId = $InputEntry.id
                winnerSourceMember = $sourceMember
            })
            Remove-Item -LiteralPath $target -Force
        }
        $parent = Split-Path -Parent $target
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            if ([string]::IsNullOrWhiteSpace([string]$item.LinkTarget)) {
                throw "Overlay link has no target: $($item.FullName)"
            }
            $linkTarget = [string]$item.LinkTarget
            Assert-LinkTargetSafe -LinkPath $target -LinkTarget $linkTarget.Replace('/', '\') -Root $PortableRoot
            New-Item -ItemType SymbolicLink -Path $target -Target $item.LinkTarget | Out-Null
        } else {
            Copy-Item -LiteralPath $item.FullName -Destination $target
        }
        $Ownership[$payloadPath] = [ordered]@{
            inputId = $InputEntry.id
            package = if ($null -ne $InputEntry.package) { $InputEntry.package.name } else { $null }
            packageVersion = if ($null -ne $InputEntry.package) { $InputEntry.package.version } else { $null }
            sourceMember = $sourceMember
        }
    }
}

function Get-MaterializedMemberIdentity {
    param(
        [Parameter(Mandatory = $true)][string] $Root,
        [Parameter(Mandatory = $true)] $Item
    )

    $memberPath = Get-RelativeUnixPath -Root $Root -Path $Item.FullName
    if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        return [ordered]@{
            type = 'symlink'
            linkTarget = Resolve-ManifestLinkTarget -MemberPath $memberPath -LinkTarget ([string]$Item.LinkTarget)
        }
    }
    if ($Item.PSIsContainer) {
        return [ordered]@{ type = 'directory'; linkTarget = $null }
    }
    if ($Item.LinkType -ne 'HardLink') {
        return [ordered]@{ type = 'file'; linkTarget = $null }
    }

    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $null = $paths.Add($memberPath)
    foreach ($target in @($Item.LinkTarget)) {
        $targetPath = [string]$target
        if (-not [IO.Path]::IsPathFullyQualified($targetPath)) {
            $targetPath = Join-Path ([IO.Path]::GetPathRoot($rootPath)) $targetPath.TrimStart('\', '/')
        }
        $targetPath = [IO.Path]::GetFullPath($targetPath)
        if (-not $targetPath.StartsWith("$rootPath\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "Hardlink identity escapes the payload root: $memberPath -> $target"
        }
        $null = $paths.Add((Get-RelativeUnixPath -Root $rootPath -Path $targetPath))
    }
    $ordered = Get-OrdinalSortedStrings @($paths)
    if ($ordered.Count -lt 2) {
        throw "Hardlink identity has no declared alias: $memberPath"
    }
    if ($memberPath -ceq $ordered[0]) {
        return [ordered]@{ type = 'file'; linkTarget = $null }
    }
    return [ordered]@{ type = 'hardlink'; linkTarget = $ordered[0] }
}

function Write-PayloadManifest {
    param(
        [Parameter(Mandatory = $true)][string] $PortableRoot,
        [Parameter(Mandatory = $true)] $Ownership,
        [Parameter(Mandatory = $true)][string] $OutputPath,
        [Parameter(Mandatory = $true)][string] $LockPath,
        [Parameter(Mandatory = $true)][string] $ProvenancePath
    )

    $evidencePrefix = ([IO.Path]::GetFullPath((Join-Path $PortableRoot 'preview-evidence'))).TrimEnd('\') + '\'
    $unsortedEntries = @(Get-ChildItem -LiteralPath $PortableRoot -Force -Recurse |
        Where-Object { -not $_.FullName.StartsWith($evidencePrefix, [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object {
            $relative = Get-RelativeUnixPath -Root $PortableRoot -Path $_.FullName
            $owner = $Ownership[$relative]
            if ($null -eq $owner) {
                throw "Payload member lacks source ownership: $relative"
            }
            $identity = Get-MaterializedMemberIdentity -Root $PortableRoot -Item $_
            $type = $identity.type
            [ordered]@{
                path = $relative
                type = $type
                bytes = if ($type -eq 'directory') { 0 } else { $_.Length }
                sha256 = if ($type -eq 'directory') { $null } else { Get-Sha256 -Path $_.FullName }
                linkTarget = $identity.linkTarget
            }
        })
    $entries = @(Sort-ObjectsOrdinal -Items $unsortedEntries -Properties @('path'))
    $document = [ordered]@{
        schemaVersion = 1
        lockSha256 = Get-Sha256 -Path $LockPath
        provenanceSha256 = Get-Sha256 -Path $ProvenancePath
        scope = [ordered]@{
            root = '.'
            excludedPrefixes = @('preview-evidence/')
        }
        entries = $entries
    }
    $text = ($document | ConvertTo-Json -Depth 8).Replace("`r`n", "`n") + "`n"
    [IO.File]::WriteAllText($OutputPath, $text, [Text.UTF8Encoding]::new($false))
    $payloadJson = Get-Content -LiteralPath $OutputPath -Raw -Encoding utf8
    if (-not ($payloadJson | Test-Json -SchemaFile (Join-Path $PSScriptRoot '..\schemas\payload-manifest.schema.json'))) {
        throw "Generated payload manifest failed its versioned schema"
    }
}

function Assert-PayloadManifestUnchanged {
    param(
        [Parameter(Mandatory = $true)][string] $PortableRoot,
        [Parameter(Mandatory = $true)][string] $ManifestPath
    )

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    $expected = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in @($manifest.entries)) {
        if (-not $expected.TryAdd([string]$entry.path, $entry)) {
            throw "Payload manifest has a duplicate or case-colliding path: $($entry.path)"
        }
    }
    $evidencePrefix = ([IO.Path]::GetFullPath((Join-Path $PortableRoot 'preview-evidence'))).TrimEnd('\') + '\'
    $actualPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($item in Get-ChildItem -LiteralPath $PortableRoot -Force -Recurse |
        Where-Object { -not $_.FullName.StartsWith($evidencePrefix, [StringComparison]::OrdinalIgnoreCase) }) {
        $relative = Get-RelativeUnixPath -Root $PortableRoot -Path $item.FullName
        if (-not $actualPaths.Add($relative) -or -not $expected.ContainsKey($relative)) {
            throw "Payload changed after manifest generation: unexpected path '$relative'"
        }
        $entry = $expected[$relative]
        $identity = Get-MaterializedMemberIdentity -Root $PortableRoot -Item $item
        $type = $identity.type
        if ([string]$entry.type -cne $type) {
            throw "Payload changed type after manifest generation: $relative"
        }
        if ([string]$entry.linkTarget -cne [string]$identity.linkTarget) {
            throw "Payload changed link target after manifest generation: $relative"
        }
        if ($type -ne 'directory' -and
            ($item.Length -ne [Int64]$entry.bytes -or (Get-Sha256 $item.FullName) -cne [string]$entry.sha256)) {
            throw "Payload changed bytes after manifest generation: $relative"
        }
    }
    if ($actualPaths.Count -ne $expected.Count) {
        $missing = @($expected.Keys | Where-Object { -not $actualPaths.Contains($_) })
        throw "Payload changed after manifest generation: missing paths '$($missing -join ', ')'"
    }
}

function Get-ToolTreeSnapshot {
    param([Parameter(Mandatory = $true)][string] $Root)

    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    return @(
        Get-ChildItem -LiteralPath $rootPath -Force -Recurse |
            Sort-Object { Get-RelativeUnixPath -Root $rootPath -Path $_.FullName } |
            ForEach-Object {
                $isDirectory = $_.PSIsContainer
                [ordered]@{
                    path = Get-RelativeUnixPath -Root $rootPath -Path $_.FullName
                    type = if ($isDirectory) { 'directory' } else { 'file' }
                    bytes = if ($isDirectory) { $null } else { [Int64]$_.Length }
                    sha256 = if ($isDirectory) { $null } else { Get-Sha256 -Path $_.FullName }
                    linkType = if ([string]::IsNullOrWhiteSpace([string]$_.LinkType)) { $null } else { [string]$_.LinkType }
                    linkTarget = if ($null -eq $_.LinkTarget) { $null } else { [string]$_.LinkTarget }
                }
            }
    )
}

foreach ($path in @($OutputRoot, $CacheDirectory, $WorkDirectory)) {
    Assert-PrivatePath -Path $path
}
$privatePaths = @(@($OutputRoot, $CacheDirectory, $WorkDirectory) | ForEach-Object {
    [IO.Path]::GetFullPath($_).TrimEnd('\')
})
for ($left = 0; $left -lt $privatePaths.Count; $left++) {
    for ($right = $left + 1; $right -lt $privatePaths.Count; $right++) {
        if ($privatePaths[$left].Equals($privatePaths[$right], [StringComparison]::OrdinalIgnoreCase) -or
            $privatePaths[$left].StartsWith("$($privatePaths[$right])\", [StringComparison]::OrdinalIgnoreCase) -or
            $privatePaths[$right].StartsWith("$($privatePaths[$left])\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "OutputRoot, CacheDirectory, and WorkDirectory must be distinct non-nested paths"
        }
    }
    if ([IO.Path]::GetPathRoot($privatePaths[0]) -cne [IO.Path]::GetPathRoot($privatePaths[2])) {
        throw "OutputRoot and WorkDirectory must be on the same volume for atomic materialization"
    }
}
$lock = Read-PreviewLock -Path $LockPath
$unresolved = @(Assert-PreviewLock -Lock $lock)
if ($ValidateLockOnly) {
    [ordered]@{
        schemaVersion = 1
        ready = ($unresolved.Count -eq 0)
        unresolved = $unresolved
        lockSha256 = Get-Sha256 -Path $LockPath
    } | ConvertTo-Json -Depth 4
    if ($unresolved.Count -gt 0) {
        exit 2
    }
    exit 0
}
$null = Assert-PreviewLock -Lock $lock -RequireResolved
$lockResolved = (Resolve-Path -LiteralPath $LockPath).Path
$gitCommand = Get-Command git.exe -CommandType Application -ErrorAction Stop
$gitExecutable = Get-FinalFileSystemPath -Path $gitCommand.Source
if ($gitExecutable.StartsWith('C:\msys64\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Shared C:\msys64 Git cannot be used by the assembler"
}
$repositoryRoot = @(& $gitExecutable -C $PSScriptRoot rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0 -or $repositoryRoot.Count -ne 1) {
    throw "Assembler source must run from a Git checkout"
}
$repositoryRoot = [string]$repositoryRoot[0]
$assemblerCommit = [string](& $gitExecutable -C $repositoryRoot rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $assemblerCommit -notmatch '^[0-9a-f]{40}$') {
    throw "Unable to resolve immutable assembler commit"
}
$origin = [string](& $gitExecutable -C $repositoryRoot remote get-url origin)
$approvedOrigin = '^(?i)(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)' +
    'crutkas/msys2-woarm64-build(?:\.git)?$'
if ($LASTEXITCODE -ne 0 -or $origin -notmatch $approvedOrigin) {
    throw "Assembler source must come from the crutkas/msys2-woarm64-build fork"
}
$dirty = @(& $gitExecutable -C $repositoryRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) {
    throw "Assembler checkout must be clean so its source commit is immutable"
}
$lockRepositoryPath = [IO.Path]::GetRelativePath($repositoryRoot, $lockResolved).Replace('\', '/')
if ($lockRepositoryPath.StartsWith('../', [StringComparison]::Ordinal) -or
    $lockRepositoryPath -eq '..') {
    throw "LockPath must be a committed file in the assembler repository"
}
$trackedLock = @(& $gitExecutable -C $repositoryRoot ls-files --error-unmatch -- $lockRepositoryPath 2>&1)
if ($LASTEXITCODE -ne 0 -or $trackedLock.Count -ne 1) {
    throw "LockPath must be tracked at the immutable assembler commit"
}

if (Test-Path -LiteralPath $OutputRoot) {
    throw "OutputRoot must not exist: $OutputRoot"
}
if (Test-Path -LiteralPath $WorkDirectory) {
    throw "WorkDirectory must not exist: $WorkDirectory"
}
Initialize-PrivateCache -Path $CacheDirectory
New-Item -ItemType Directory -Path $WorkDirectory | Out-Null
$sharedCutoffUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')
$sharedBefore = Get-SharedRootObservation
try {
$downloads = @{}
foreach ($input in $lock.inputs) {
    $downloads[$input.id] = Get-VerifiedInput -InputEntry $input -CacheDirectory $CacheDirectory
}

$ownership = @{}
$base = @($lock.inputs | Where-Object id -ceq 'portable-git-arm64-base')[0]
$scannerHostInput = @($lock.inputs | Where-Object id -ceq 'scanner-host-portable-git-x64')[0]
$extractorBootstrap = @($lock.inputs | Where-Object id -ceq 'archive-extractor-7zr')[0]
$extractorBundle = @($lock.inputs | Where-Object id -ceq 'archive-extractor-7zip-extra')[0]
$extractorRoot = Join-Path $WorkDirectory 'extractor'
$extractorArchiveMembers = @(Expand-VerifiedArchive -ArchivePath $downloads[$extractorBundle.id] `
    -Destination $extractorRoot -SevenZipPath $downloads[$extractorBootstrap.id])
Assert-PinnedMembers -InputEntry $extractorBundle -ExtractedRoot $extractorRoot
$archiveMembersByInput = @{
    $extractorBootstrap.id = @(Get-DirectInputMember -InputEntry $extractorBootstrap -Path $downloads[$extractorBootstrap.id])
    $extractorBundle.id = @(Get-VerifiedTreeMembers -Root $extractorRoot -ArchiveMembers $extractorArchiveMembers)
}
$sevenZip = Join-Path $extractorRoot 'x64\7za.exe'

$packageRoots = @{}
foreach ($input in @($lock.inputs | Where-Object { $null -ne $_.package })) {
    $packageRoot = Join-Path $WorkDirectory "extract\$($input.id)"
    $packageArchiveMembers = @(Expand-VerifiedArchive -ArchivePath $downloads[$input.id] `
        -Destination $packageRoot -SevenZipPath $sevenZip)
    Assert-PackageMetadata -InputEntry $input -PackageRoot $packageRoot
    Assert-PinnedMembers -InputEntry $input -ExtractedRoot $packageRoot
    $packageRoots[$input.id] = $packageRoot
    $archiveMembersByInput[$input.id] = @(
        Get-VerifiedTreeMembers -Root $packageRoot -ArchiveMembers $packageArchiveMembers
    )
}

$scannerHost = Join-Path $WorkDirectory 'scanner-host'
$scannerHostArchiveMembers = @(Expand-VerifiedArchive -ArchivePath $downloads[$scannerHostInput.id] `
    -Destination $scannerHost -SevenZipPath $sevenZip)
$archiveMembersByInput[$scannerHostInput.id] = @(
    Get-VerifiedTreeMembers -Root $scannerHost -ArchiveMembers $scannerHostArchiveMembers
)
$portableRoot = Join-Path $WorkDirectory 'portable-root'
$baseArchiveMembers = @(Expand-VerifiedArchive -ArchivePath $downloads[$base.id] `
    -Destination $portableRoot -SevenZipPath $sevenZip)
$archiveMembersByInput[$base.id] = @(
    Get-VerifiedTreeMembers -Root $portableRoot -ArchiveMembers $baseArchiveMembers
)
foreach ($input in @($lock.inputs | Where-Object { -not $archiveMembersByInput.ContainsKey([string]$_.id) })) {
    $archiveMembersByInput[$input.id] = @(Get-DirectInputMember -InputEntry $input -Path $downloads[$input.id])
}
$overlaySelectionsByInput = @{}
foreach ($input in @($lock.inputs | Where-Object { $_.overlay.enabled })) {
    $overlaySelectionsByInput[$input.id] = @(
        Get-OverlaySelection -InputEntry $input -ArchiveMembers @($archiveMembersByInput[$input.id])
    )
}
foreach ($member in Get-ChildItem -LiteralPath $portableRoot -Force -Recurse) {
    $relative = Get-RelativeUnixPath -Root $portableRoot -Path $member.FullName
    $ownership[$relative] = [ordered]@{
        inputId = $base.id
        package = $null
        packageVersion = $null
        sourceMember = $relative
    }
}

$replacementRecords = [Collections.Generic.List[object]]::new()
foreach ($input in @($lock.inputs | Where-Object { $_.overlay.enabled -and $_.role -ne 'base' })) {
    $staging = $packageRoots[$input.id]
    foreach ($mapping in $input.overlay.mappings) {
        Copy-OverlayMapping -StagingRoot $staging -PortableRoot $portableRoot `
            -Mapping $mapping -InputEntry $input -Ownership $ownership `
            -ReplacementRecords $replacementRecords
    }
}

$evidenceDirectory = Join-Path $portableRoot 'preview-evidence'
if (Test-Path -LiteralPath $evidenceDirectory) {
    throw "Materialized payload occupies the reserved preview-evidence subtree"
}
New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null
$previewTools = Join-Path $evidenceDirectory 'tools\assembler'
New-Item -ItemType Directory -Path $previewTools -Force | Out-Null
$toolSources = @(
    (Join-Path $PSScriptRoot 'Preview.Common.psm1'),
    (Join-Path $PSScriptRoot 'Validate-Arm64Preview.ps1'),
    (Join-Path $PSScriptRoot 'Collect-PreviewDiagnostics.ps1'),
    (Join-Path $PSScriptRoot '..\TESTING.md')
)
foreach ($toolSource in $toolSources) {
    $toolDestination = Join-Path $previewTools ([IO.Path]::GetFileName($toolSource))
    $sourceMember = Get-RelativeUnixPath -Root $repositoryRoot -Path $toolSource
    Copy-GitBlob -GitPath $gitExecutable -RepositoryRoot $repositoryRoot -Commit $assemblerCommit `
        -SourcePath $sourceMember -Destination $toolDestination
}
$previewSchemas = Join-Path $previewTools 'schemas'
New-Item -ItemType Directory -Path $previewSchemas | Out-Null
foreach ($schemaSource in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..\schemas') -Filter '*.schema.json' -File) {
    $schemaDestination = Join-Path $previewSchemas $schemaSource.Name
    $sourceMember = Get-RelativeUnixPath -Root $repositoryRoot -Path $schemaSource.FullName
    Copy-GitBlob -GitPath $gitExecutable -RepositoryRoot $repositoryRoot -Commit $assemblerCommit `
        -SourcePath $sourceMember -Destination $schemaDestination
}

$sourceLockPath = Join-Path $evidenceDirectory 'source-lock.json'
Copy-GitBlob -GitPath $gitExecutable -RepositoryRoot $repositoryRoot -Commit $assemblerCommit `
    -SourcePath $lockRepositoryPath -Destination $sourceLockPath
$committedLock = Read-PreviewLock -Path $sourceLockPath -RequireResolved
if (($committedLock | ConvertTo-Json -Compress -Depth 20) -cne
    ($lock | ConvertTo-Json -Compress -Depth 20)) {
    throw "Working lock semantics differ from its immutable committed blob"
}
$bundleLockPath = Join-Path $evidenceDirectory 'bundle-lock.v1.json'
Write-CanonicalBundleLock -SourceLock $committedLock -SourceLockPath $sourceLockPath `
    -OverlaySelectionsByInput $overlaySelectionsByInput -OutputPath $bundleLockPath
$binutilsInput = @($lock.inputs | Where-Object id -ceq 'fixed-binutils')[0]
$scannerInput = @($lock.inputs | Where-Object id -ceq 'fixed-pseudo-reloc-scanner')[0]
$binutilsRoot = $packageRoots[$binutilsInput.id]

$payloadPath = Join-Path $evidenceDirectory 'payload-manifest.v1.json'
Assert-NoPreparationTools -Root $portableRoot
$sharedAfter = Get-SharedRootObservation
if (-not (Test-SharedObservationEqual -Before $sharedBefore -After $sharedAfter)) {
    throw "Prohibited shared C:\msys64 pacman log/database state changed during assembly"
}
$provenancePath = Join-Path $evidenceDirectory 'provenance.v1.json'
$canonicalLock = Get-Content -LiteralPath $bundleLockPath -Raw -Encoding utf8 | ConvertFrom-Json
$inputEvidence = @($canonicalLock.inputs | Where-Object status -ceq 'resolved' | ForEach-Object {
    $canonicalInput = $_
    $selectionBySource = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($selection in @($overlaySelectionsByInput[[string]$canonicalInput.id])) {
        if (-not $selectionBySource.TryAdd([string]$selection.sourceMember, $selection)) {
            throw "Input '$($canonicalInput.id)' has duplicate selected source members"
        }
    }
    $archiveMembers = @($archiveMembersByInput[[string]$canonicalInput.id] | ForEach-Object {
        $member = $_
        $selected = $selectionBySource.ContainsKey([string]$member.path)
        [ordered]@{
            sourceMember = $member.path
            type = $member.type
            bytes = if ($member.type -eq 'directory') { 0 } else { [Int64]$member.bytes }
            sha256 = $member.sha256
            selected = $selected
            destinationPath = if ($selected) {
                [string]$selectionBySource[[string]$member.path].destinationPath
            } else {
                $null
            }
            linkTarget = $member.linkTarget
        }
    })
    [ordered]@{
        id = $canonicalInput.id
        release = $canonicalInput.release
        asset = $canonicalInput.asset
        package = $canonicalInput.package
        archiveMembers = $archiveMembers
    }
})
$overlayOrder = @(
    $base.id
    $lock.inputs |
        Where-Object { $_.overlay.enabled -and $_.role -ne 'base' } |
        ForEach-Object id
)
$replacements = @(Sort-ObjectsOrdinal -Items @($replacementRecords) -Properties @('destinationPath', 'winnerInputId'))
$unsortedFinalMembers = @($ownership.GetEnumerator() | Where-Object Key -cne '.' | ForEach-Object {
    $memberPath = Join-Path $portableRoot $_.Key.Replace('/', '\')
    $member = Get-Item -LiteralPath $memberPath -Force
    $identity = Get-MaterializedMemberIdentity -Root $portableRoot -Item $member
    $memberType = $identity.type
    [ordered]@{
        destinationPath = $_.Key
        inputId = $_.Value.inputId
        sourceMember = $_.Value.sourceMember
        type = $memberType
        bytes = if ($memberType -eq 'directory') { 0 } else { [Int64]$member.Length }
        sha256 = if ($memberType -eq 'directory') { $null } else { Get-Sha256 -Path $member.FullName }
        linkTarget = $identity.linkTarget
    }
})
$finalMembers = @(Sort-ObjectsOrdinal -Items $unsortedFinalMembers -Properties @('destinationPath'))
$pseudoRelocCandidates = @($finalMembers | Where-Object {
        $_.type -in @('file', 'hardlink') -and $_.destinationPath -match '(?i)\.(?:exe|dll)$'
    } | ForEach-Object {
        [ordered]@{
            destinationPath = $_.destinationPath
            inputId = $_.inputId
            sourceMember = $_.sourceMember
        }
    })
$provenanceDocument = [ordered]@{
    schemaVersion = 1
    lockSha256 = Get-Sha256 -Path $bundleLockPath
    sourceDateEpoch = $lock.sourceDateEpoch
    nativeShellClosure = @($canonicalLock.nativeShellClosure)
    assembler = [ordered]@{
        repository = 'crutkas/msys2-woarm64-build'
        commit = $assemblerCommit
    }
    inputs = $inputEvidence
    overlayOrder = $overlayOrder
    replacements = $replacements
    finalMembers = $finalMembers
    pseudoReloc = [ordered]@{ candidates = $pseudoRelocCandidates }
}
$provenanceText = ($provenanceDocument | ConvertTo-Json -Depth 15).Replace("`r`n", "`n") + "`n"
[IO.File]::WriteAllText($provenancePath, $provenanceText, [Text.UTF8Encoding]::new($false))
$provenanceJson = Get-Content -LiteralPath $provenancePath -Raw -Encoding utf8
if (-not ($provenanceJson | Test-Json -SchemaFile (Join-Path $PSScriptRoot '..\schemas\provenance.schema.json'))) {
    throw "Generated provenance failed its versioned schema"
}
Write-PayloadManifest -PortableRoot $portableRoot -Ownership $ownership `
    -OutputPath $payloadPath -LockPath $bundleLockPath `
    -ProvenancePath $provenancePath

$validatorToolRoot = Join-Path $evidenceDirectory 'tools\validator-runtime'
New-Item -ItemType Directory -Path $validatorToolRoot -Force | Out-Null
Move-Item -LiteralPath $scannerHost -Destination (Join-Path $validatorToolRoot $scannerHostInput.id)
Move-Item -LiteralPath $binutilsRoot -Destination (Join-Path $validatorToolRoot $binutilsInput.id)
$scannerMaterializationRoot = Join-Path $validatorToolRoot $scannerInput.id
$null = Copy-VerifiedRawInput -InputEntry $scannerInput `
    -VerifiedPath $downloads[$scannerInput.id] -DestinationRoot $scannerMaterializationRoot

$buildExtraRoot = Join-Path $evidenceDirectory 'tools\build-extra'
foreach ($validatorInput in @($lock.inputs | Where-Object {
            $_.role -in @(
                'authoritative-validator-main',
                'authoritative-validator-support',
                'authoritative-validator-schema'
            )
        })) {
    $null = Copy-VerifiedRawInput -InputEntry $validatorInput `
        -VerifiedPath $downloads[$validatorInput.id] -DestinationRoot $buildExtraRoot
}
$runtimeCollectorRoot = Join-Path $evidenceDirectory 'tools\runtime-collector'
foreach ($collectorInput in @($lock.inputs | Where-Object {
            $_.role -in @('authoritative-runtime-collector', 'authoritative-runtime-support')
        })) {
    $null = Copy-VerifiedRawInput -InputEntry $collectorInput `
        -VerifiedPath $downloads[$collectorInput.id] -DestinationRoot $runtimeCollectorRoot
}
$validatorMainInputs = @($lock.inputs | Where-Object role -ceq 'authoritative-validator-main')
if ($validatorMainInputs.Count -ne 1) {
    throw "Exactly one immutable authoritative validator main input is required"
}
$authoritativeValidatorPath = Join-Path $buildExtraRoot (
    ConvertTo-SafeArchivePath -Member ([string]$validatorMainInputs[0].identity.sourcePath)
).Replace('/', '\')
if (-not (Test-Path -LiteralPath $authoritativeValidatorPath -PathType Leaf) -or
    (Get-Sha256 -Path $authoritativeValidatorPath) -cne [string]$validatorMainInputs[0].asset.sha256) {
    throw "Materialized authoritative validator main input is absent or changed"
}
$preValidatorArtifactHashes = [ordered]@{
    lock = Get-Sha256 -Path $bundleLockPath
    provenance = Get-Sha256 -Path $provenancePath
    payload = Get-Sha256 -Path $payloadPath
}
$preValidatorToolSnapshot = Get-ToolTreeSnapshot -Root (Join-Path $evidenceDirectory 'tools')
$authoritativeEvidencePath = Join-Path $evidenceDirectory 'authoritative-preview-report.v1.json'
$authoritativeEvidenceWorkingPath = Join-Path $WorkDirectory 'authoritative-preview-report.v1.json'
& pwsh -NoLogo -NoProfile -File $authoritativeValidatorPath `
    -Mode Preview `
    -Root $portableRoot `
    -Lock $bundleLockPath `
    -Provenance $provenancePath `
    -PayloadManifest $payloadPath `
    -ToolRoot $validatorToolRoot `
    -Report $authoritativeEvidenceWorkingPath
if ($LASTEXITCODE -ne 0) {
    throw "Authoritative build-extra payload gate failed with exit code $LASTEXITCODE"
}
if ((Get-Sha256 -Path $bundleLockPath) -cne $preValidatorArtifactHashes.lock -or
    (Get-Sha256 -Path $provenancePath) -cne $preValidatorArtifactHashes.provenance -or
    (Get-Sha256 -Path $payloadPath) -cne $preValidatorArtifactHashes.payload) {
    throw "Authoritative validator modified an immutable input artifact"
}
$postValidatorToolSnapshot = Get-ToolTreeSnapshot -Root (Join-Path $evidenceDirectory 'tools')
if (($postValidatorToolSnapshot | ConvertTo-Json -Compress -Depth 8) -cne
    ($preValidatorToolSnapshot | ConvertTo-Json -Compress -Depth 8)) {
    throw "Authoritative validator modified an immutable validation tool"
}
if (-not (Test-Path -LiteralPath $authoritativeEvidenceWorkingPath -PathType Leaf)) {
    throw "Authoritative build-extra payload gate emitted no evidence"
}
$authoritativeEvidence = Get-Content -LiteralPath $authoritativeEvidenceWorkingPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($null -eq $authoritativeEvidence.PSObject.Properties['schemaVersion'] -or
    $null -eq $authoritativeEvidence.PSObject.Properties['result'] -or
    $authoritativeEvidence.result -ne 'pass') {
    throw "Authoritative build-extra payload gate evidence is incomplete or non-passing"
}
Move-Item -LiteralPath $authoritativeEvidenceWorkingPath -Destination $authoritativeEvidencePath
Assert-PayloadManifestUnchanged -PortableRoot $portableRoot -ManifestPath $payloadPath
$sharedFinal = Get-SharedRootObservation
if (-not (Test-SharedObservationEqual -Before $sharedBefore -After $sharedFinal)) {
    throw "Prohibited shared C:\msys64 pacman log/database state changed during final validation"
}
$runEvidencePath = Join-Path $evidenceDirectory 'assembly-run-evidence.v1.json'
$hostArchitecture = switch ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
    ([Runtime.InteropServices.Architecture]::X64) { 'AMD64' }
    ([Runtime.InteropServices.Architecture]::Arm64) { 'ARM64' }
    default { throw "Unsupported assembly host architecture: $_" }
}
$processArchitecture = switch ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture) {
    ([Runtime.InteropServices.Architecture]::X64) { 'AMD64' }
    ([Runtime.InteropServices.Architecture]::Arm64) { 'ARM64' }
    default { throw "Unsupported assembly process architecture: $_" }
}
[ordered]@{
    schemaVersion = 1
    previewId = $previewId
    sourceLockSha256 = Get-Sha256 -Path $sourceLockPath
    lockSha256 = Get-Sha256 -Path $bundleLockPath
    provenanceSha256 = Get-Sha256 -Path $provenancePath
    payloadManifestSha256 = Get-Sha256 -Path $payloadPath
    rootInventorySha256 = [string]$authoritativeEvidence.digests.rootInventorySha256
    staticReportSha256 = Get-Sha256 -Path $authoritativeEvidencePath
    host = [ordered]@{
        os = 'Windows'
        architecture = $hostArchitecture
        processArchitecture = $processArchitecture
    }
    observedUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')
    externalObservation = [ordered]@{
        rootPath = 'C:\msys64'
        authoritative = $false
        usedAsInput = $false
        cutoffUtc = $sharedCutoffUtc
        before = $sharedBefore
        after = $sharedFinal
        commands = @(
            'enumerate-database-manifest',
            'hash-database-manifest',
            'hash-package-log',
            'stat-package-log'
        )
    }
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $runEvidencePath -Encoding utf8
$runEvidenceJson = Get-Content -LiteralPath $runEvidencePath -Raw -Encoding utf8
if (-not ($runEvidenceJson | Test-Json -SchemaFile (Join-Path $PSScriptRoot '..\schemas\assembly-run-evidence.schema.json'))) {
    throw "Generated assembly run evidence failed its versioned schema"
}
Move-Item -LiteralPath $portableRoot -Destination $OutputRoot
Remove-Item -LiteralPath $WorkDirectory -Force -Recurse
$finalEvidenceDirectory = Join-Path $OutputRoot 'preview-evidence'

[ordered]@{
    schemaVersion = 1
    previewId = $previewId
    outputRoot = [IO.Path]::GetFullPath($OutputRoot)
    provenance = Join-Path $finalEvidenceDirectory 'provenance.v1.json'
    payloadManifest = Join-Path $finalEvidenceDirectory 'payload-manifest.v1.json'
    unresolved = @()
    readyForArmValidation = $true
} | ConvertTo-Json -Depth 4
}
finally {
    try {
        if (Test-Path -LiteralPath $WorkDirectory) {
            Remove-Item -LiteralPath $WorkDirectory -Force -Recurse
        }
    }
    finally {
        $sharedOnExit = Get-SharedRootObservation
        if (-not (Test-SharedObservationEqual -Before $sharedBefore -After $sharedOnExit)) {
            throw "Prohibited shared C:\msys64 pacman log/database state changed before assembler exit"
        }
    }
}
