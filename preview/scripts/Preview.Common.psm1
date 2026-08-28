Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CanonicalDirectoryManifest {
    param([Parameter(Mandatory = $true)][string] $Root)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Canonical manifest root is absent: $Root"
    }
    if ((Get-Item -LiteralPath $Root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Canonical manifest root is a reparse point: $Root"
    }
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force -Recurse) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Canonical manifest root contains a reparse point: $($item.FullName)"
        }
    }
    $files = @(Get-ChildItem -LiteralPath $Root -File -Force -Recurse | Sort-Object FullName)
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $records = @($files | ForEach-Object {
        $relative = $_.FullName.Substring($Root.TrimEnd('\').Length + 1)
        if (-not $seen.Add($relative)) {
            throw "Canonical manifest contains a case-insensitive path collision: $relative"
        }
        [pscustomobject][ordered]@{
            path = $relative
            length = $_.Length
            lastWriteUtc = $_.LastWriteTimeUtc.ToString('o')
            sha256 = Get-Sha256 -Path $_.FullName
        }
    })
    $csv = (@($records | ConvertTo-Csv -NoTypeInformation) -join "`r`n") + "`r`n"
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($csv)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [Convert]::ToHexString($hasher.ComputeHash($bytes)).ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
    return [ordered]@{
        files = $files.Count
        bytes = $bytes.Length
        canonicalManifestSha256 = $digest
    }
}

function Get-RelativeUnixPath {
    param(
        [Parameter(Mandatory = $true)][string] $Root,
        [Parameter(Mandatory = $true)][string] $Path
    )
    return [IO.Path]::GetRelativePath(
        [IO.Path]::GetFullPath($Root),
        [IO.Path]::GetFullPath($Path)
    ).Replace('\', '/')
}

function Assert-PrivatePath {
    param([Parameter(Mandatory = $true)][string] $Path)

    if ($Path.StartsWith('\\', [StringComparison]::Ordinal) -or $Path.Contains('~')) {
        throw "Private paths must not use UNC, device, or short-name aliases: $Path"
    }
    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($candidate -notmatch '^[A-Za-z]:\\') {
        throw "Private paths must be drive-letter rooted: $candidate"
    }
    $driveName = $candidate.Substring(0, 1)
    $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction Stop
    if (-not [string]::IsNullOrWhiteSpace([string]$drive.DisplayRoot)) {
        throw "Private paths must not use mapped drive aliases: $candidate"
    }
    foreach ($substitution in @(& subst 2>$null)) {
        if ([string]$substitution -match "^$([regex]::Escape($driveName)):\\: => ") {
            throw "Private paths must not use SUBST drive aliases: $candidate"
        }
    }
    $shared = [IO.Path]::GetFullPath('C:\msys64').TrimEnd('\')
    if ($candidate.Equals($shared, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith("$shared\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is inside the prohibited shared root C:\msys64: $candidate"
    }

    $cursor = $candidate
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Private path traverses a reparse point: $cursor"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) {
            break
        }
        $cursor = $parent
    }

    $git = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $git -and $git.Source -match '(?i)\\cmd\\git\.exe$') {
        $gitRoot = [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($git.Source)).TrimEnd('\')
        if ($candidate.Equals($gitRoot, [StringComparison]::OrdinalIgnoreCase) -or
            $candidate.StartsWith("$gitRoot\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "Path is inside the production Git installation: $candidate"
        }
    }
}

function Assert-PreviewLock {
    param(
        [Parameter(Mandatory = $true)] $Lock,
        [switch] $RequireResolved
    )

    if ($Lock.schemaVersion -ne 1) {
        throw "Unsupported lock schemaVersion '$($Lock.schemaVersion)'; expected 1"
    }
    if (@($Lock.inputs).Count -eq 0) {
        throw "Lock has no inputs"
    }
    $closurePaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($closurePath in @($Lock.nativeShellClosure)) {
        $safeClosurePath = ConvertTo-SafeArchivePath -Member ([string]$closurePath)
        if ($safeClosurePath -cne [string]$closurePath -or
            -not $closurePaths.Add($safeClosurePath)) {
            throw "Native shell closure contains an unsafe or duplicate path: '$closurePath'"
        }
    }
    if (@($Lock.inputs | Where-Object role -eq 'base').Count -ne 1) {
        throw "Lock must contain exactly one base input"
    }
    $requiredInputs = [ordered]@{
        'archive-extractor-7zr' = 'archive-extractor'
        'archive-extractor-7zip-extra' = 'archive-extractor'
        'portable-git-arm64-base' = 'base'
        'scanner-host-portable-git-x64' = 'scanner-host'
        'runtime-headers' = 'build-support-package'
        'runtime-default-manifest' = 'build-support-package'
        'runtime-sysroot' = 'build-support-package'
        'runtime' = 'runtime-package'
        'runtime-devel' = 'build-support-package'
        'gcc-libstdcxx-headers' = 'build-support-package'
        'gcc-w32api-runtime' = 'build-support-package'
        'fixed-binutils' = 'scanner-tool-package'
        'fixed-pseudo-reloc-scanner' = 'scanner-script'
        'ncurses-runtime' = 'native-shell-package'
        'ncurses-devel' = 'build-support-package'
        'readline' = 'native-shell-package'
        'bash' = 'native-shell-package'
    }
    foreach ($required in $requiredInputs.GetEnumerator()) {
        $matches = @($Lock.inputs | Where-Object id -ceq $required.Key)
        if ($matches.Count -ne 1 -or $matches[0].role -cne $required.Value) {
            throw "Lock must contain exactly one '$($required.Key)' input with role '$($required.Value)'"
        }
    }

    $ids = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $urls = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $hashes = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $unresolved = [Collections.Generic.List[string]]::new()
    $placeholder = '(?i)(todo|tbd|placeholder|example|replace[-_ ]?me|<[^>]+>)'

    foreach ($input in @($Lock.inputs)) {
        if ([string]::IsNullOrWhiteSpace($input.id) -or -not $ids.Add([string]$input.id)) {
            throw "Missing or duplicate input id '$($input.id)'"
        }
        $payloadRoles = @('base', 'runtime-package', 'native-shell-package')
        if ($input.overlay.enabled -and $input.role -notin $payloadRoles) {
            throw "Preparation-only input '$($input.id)' cannot be overlaid into the preview"
        }
        if (-not $input.overlay.enabled -and @($input.overlay.mappings).Count -ne 0) {
            throw "Non-overlay input '$($input.id)' must not declare payload mappings"
        }
        if ($input.status -eq 'resolved' -and $input.overlay.enabled -and
            @($input.overlay.mappings).Count -eq 0) {
            throw "Resolved payload input '$($input.id)' must declare at least one overlay mapping"
        }
        $mappingSources = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $mappingDestinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($mapping in @($input.overlay.mappings)) {
            $source = ConvertTo-SafeArchivePath -Member ([string]$mapping.source)
            $destination = ConvertTo-SafeArchivePath -Member ([string]$mapping.destination)
            if ($source -cne [string]$mapping.source -or
                $destination -cne [string]$mapping.destination) {
                throw "Input '$($input.id)' has a non-canonical overlay mapping"
            }
            if (-not $mappingSources.Add($source)) {
                throw "Input '$($input.id)' has a duplicate or case-colliding overlay source '$source'"
            }
            if (-not $mappingDestinations.Add($destination)) {
                throw "Input '$($input.id)' has a duplicate or case-colliding overlay destination '$destination'"
            }
        }
        if ($input.status -notin @('resolved', 'unresolved')) {
            throw "Input '$($input.id)' has invalid status '$($input.status)'"
        }
        if ($input.status -eq 'unresolved') {
            if ($null -ne $input.identity -or $null -ne $input.asset -or $null -ne $input.package) {
                throw "Unresolved input '$($input.id)' must not carry partial pins"
            }
            $unresolved.Add([string]$input.id)
            continue
        }

        if ($null -eq $input.identity -or $null -eq $input.asset) {
            throw "Resolved input '$($input.id)' lacks identity or asset metadata"
        }
        $repository = [string]$input.identity.repository
        if ($repository -cne 'git-for-windows/git' -and
            $repository -cne 'ip7z/7zip' -and
            -not $repository.StartsWith('crutkas/', [StringComparison]::Ordinal)) {
            throw "Input '$($input.id)' repository is outside the immutable allowlist"
        }
        $tagProperty = $input.identity.PSObject.Properties['tag']
        $sourcePathProperty = $input.identity.PSObject.Properties['sourcePath']
        $identityRef = if ($null -ne $tagProperty -and
            -not [string]::IsNullOrWhiteSpace([string]$tagProperty.Value)) {
            [string]$tagProperty.Value
        } else {
            if ($null -eq $sourcePathProperty) { $null } else { [string]$sourcePathProperty.Value }
        }
        foreach ($value in @(
            $input.identity.repository,
            $identityRef,
            $input.identity.commit,
            $input.asset.name,
            $input.asset.url,
            $input.asset.sha256
        )) {
            if ([string]::IsNullOrWhiteSpace([string]$value) -or [string]$value -match $placeholder) {
                throw "Resolved input '$($input.id)' contains a missing or placeholder pin"
            }
        }
        if ([string]$input.identity.commit -notmatch '^[0-9a-f]{40}$') {
            throw "Input '$($input.id)' commit is not a full lowercase SHA"
        }
        if ([string]$input.asset.sha256 -notmatch '^[0-9a-f]{64}$' -or
            [string]$input.asset.sha256 -eq ('0' * 64)) {
            throw "Input '$($input.id)' SHA-256 is invalid"
        }
        if ([Int64]$input.asset.expectedBytes -le 0) {
            throw "Input '$($input.id)' expectedBytes must be positive"
        }
        if ([string]$input.asset.url -notmatch '^https://') {
            throw "Input '$($input.id)' URL must use HTTPS"
        }
        if (-not $urls.Add([string]$input.asset.url)) {
            throw "Duplicate input URL '$($input.asset.url)'"
        }
        if (-not $names.Add([string]$input.asset.name)) {
            throw "Duplicate input asset name '$($input.asset.name)'"
        }
        if (-not $hashes.Add([string]$input.asset.sha256)) {
            throw "Duplicate input SHA-256 '$($input.asset.sha256)'"
        }
        if ($null -ne $sourcePathProperty -and
            -not [string]::IsNullOrWhiteSpace([string]$sourcePathProperty.Value)) {
            $safeSourcePath = ConvertTo-SafeArchivePath -Member ([string]$sourcePathProperty.Value)
            $expectedRawUrl = "https://raw.githubusercontent.com/$repository/$($input.identity.commit)/$safeSourcePath"
            if ($safeSourcePath -cne [string]$sourcePathProperty.Value -or
                [string]$input.asset.url -cne $expectedRawUrl -or
                [string]$input.asset.name -cne [IO.Path]::GetFileName($safeSourcePath)) {
                throw "Raw commit input '$($input.id)' has an unsafe or mismatched source path"
            }
        } else {
            $encodedAssetName = [Uri]::EscapeDataString([string]$input.asset.name)
            $expectedReleaseUrl = "https://github.com/$repository/releases/download/$($tagProperty.Value)/$encodedAssetName"
            if ([string]$input.asset.url -cne $expectedReleaseUrl) {
                throw "Release input '$($input.id)' has a repository, tag, or asset URL mismatch"
            }
        }
        if ($null -ne $input.asset.PSObject.Properties['members']) {
            $memberPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            $memberHashes = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($member in @($input.asset.members)) {
                $safeMember = ConvertTo-SafeArchivePath -Member ([string]$member.path)
                if (-not $memberPaths.Add($safeMember)) {
                    throw "Input '$($input.id)' has duplicate or colliding pinned member '$safeMember'"
                }
                if ([Int64]$member.expectedBytes -le 0 -or
                    [string]$member.sha256 -notmatch '^[0-9a-f]{64}$' -or
                    [string]$member.sha256 -eq ('0' * 64)) {
                    throw "Input '$($input.id)' has an invalid pinned member size/SHA-256"
                }
                if (-not $memberHashes.Add([string]$member.sha256)) {
                    throw "Input '$($input.id)' has duplicate pinned member SHA-256"
                }
            }
        }
        if ($input.role -like '*package' -and $null -eq $input.package) {
            throw "Package input '$($input.id)' lacks package metadata"
        }
        if ($null -ne $input.package) {
            if ([string]::IsNullOrWhiteSpace($input.package.name) -or
                [string]::IsNullOrWhiteSpace($input.package.version) -or
                $input.package.name -match $placeholder -or
                $input.package.version -match $placeholder) {
                throw "Input '$($input.id)' has invalid package metadata"
            }
            $provides = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
            foreach ($provide in @($input.package.provides)) {
                if ([string]::IsNullOrWhiteSpace([string]$provide) -or -not $provides.Add([string]$provide)) {
                    throw "Input '$($input.id)' has missing or duplicate provides metadata"
                }
            }
        }
    }

    if ($RequireResolved -and $unresolved.Count -gt 0) {
        throw "Assembly is blocked by unresolved lock inputs: $($unresolved -join ', ')"
    }
    return @($unresolved)
}

function Read-PreviewLock {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [switch] $RequireResolved
    )
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $json = Get-Content -LiteralPath $resolved -Raw -Encoding utf8
    $schemaPath = Join-Path $PSScriptRoot '..\schemas\preview-lock.schema.json'
    if (-not ($json | Test-Json -SchemaFile $schemaPath -ErrorAction Stop)) {
        throw "Lock does not conform to the versioned JSON schema: $resolved"
    }
    $lock = $json | ConvertFrom-Json
    $null = Assert-PreviewLock -Lock $lock -RequireResolved:$RequireResolved
    return $lock
}

function Get-VerifiedInput {
    param(
        [Parameter(Mandatory = $true)] $InputEntry,
        [Parameter(Mandatory = $true)][string] $CacheDirectory
    )

    Assert-PrivatePath -Path $CacheDirectory
    New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null
    $safeName = "$($InputEntry.id)--$($InputEntry.asset.name)" -replace '[<>:"/\\|?*]', '_'
    $destination = Join-Path $CacheDirectory $safeName
    if (Test-Path -LiteralPath $destination) {
        $actualBytes = (Get-Item -LiteralPath $destination).Length
        $actualHash = Get-Sha256 -Path $destination
        if ($actualBytes -ne [Int64]$InputEntry.asset.expectedBytes -or
            $actualHash -ne [string]$InputEntry.asset.sha256) {
            throw "Cached input '$($InputEntry.id)' does not match its size/SHA-256 pin: $destination"
        }
        return $destination
    }

    $partial = "$destination.partial.$PID"
    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial -Force
    }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $InputEntry.asset.url -OutFile $partial
        $actualBytes = (Get-Item -LiteralPath $partial).Length
        $actualHash = Get-Sha256 -Path $partial
        if ($actualBytes -ne [Int64]$InputEntry.asset.expectedBytes) {
            throw "Downloaded input '$($InputEntry.id)' size mismatch: expected $($InputEntry.asset.expectedBytes), got $actualBytes"
        }
        if ($actualHash -ne [string]$InputEntry.asset.sha256) {
            throw "Downloaded input '$($InputEntry.id)' SHA-256 mismatch: expected $($InputEntry.asset.sha256), got $actualHash"
        }
        Move-Item -LiteralPath $partial -Destination $destination
    }
    finally {
        if (Test-Path -LiteralPath $partial) {
            Remove-Item -LiteralPath $partial -Force
        }
    }
    return $destination
}

function ConvertTo-SafeArchivePath {
    param([Parameter(Mandatory = $true)][string] $Member)

    $path = $Member.Replace('\', '/')
    while ($path.StartsWith('./', [StringComparison]::Ordinal)) {
        $path = $path.Substring(2)
    }
    if ([string]::IsNullOrWhiteSpace($path) -or $path -eq '.') {
        return '.'
    }
    if ($path.StartsWith('/', [StringComparison]::Ordinal) -or
        $path -match '^[A-Za-z]:' -or
        $path.Contains(':')) {
        throw "Unsafe absolute or device archive member '$Member'"
    }
    $segments = [Collections.Generic.List[string]]::new()
    foreach ($segment in $path.Split('/')) {
        if ([string]::IsNullOrEmpty($segment) -or $segment -eq '.') {
            continue
        }
        if ($segment -eq '..') {
            throw "Archive member contains path traversal: '$Member'"
        }
        if ($segment.EndsWith(' ', [StringComparison]::Ordinal) -or
            $segment.EndsWith('.', [StringComparison]::Ordinal) -or
            $segment.IndexOfAny([char[]]'<>"|?*') -ge 0 -or
            @($segment.ToCharArray() | Where-Object { [int]$_ -lt 32 }).Count -ne 0) {
            throw "Archive member is not representable as a distinct Windows path: '$Member'"
        }
        $deviceStem = $segment.Split('.')[0]
        if ($deviceStem -match '(?i)^(CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9]|LPT[1-9])$') {
            throw "Archive member uses a reserved Windows device name: '$Member'"
        }
        $segments.Add($segment)
    }
    if ($segments.Count -eq 0) {
        return '.'
    }
    return $segments -join '/'
}

function Assert-ArchiveMemberNames {
    param([Parameter(Mandatory = $true)][string[]] $Members)

    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $result = [Collections.Generic.List[object]]::new()
    foreach ($raw in $Members) {
        $isDirectory = $raw.EndsWith('/', [StringComparison]::Ordinal)
        $normalized = ConvertTo-SafeArchivePath -Member $raw
        if ($normalized -eq '.') {
            continue
        }
        if (-not $seen.Add($normalized)) {
            throw "Archive contains a duplicate or case-colliding path '$normalized'"
        }
        $result.Add([pscustomobject]@{
            path = $normalized
            archivePath = $raw
            isDirectory = $isDirectory
        })
    }
    return @($result)
}

function Get-ArchiveMembers {
    param(
        [Parameter(Mandatory = $true)][string] $ArchivePath,
        [Parameter(Mandatory = $true)][string] $SevenZipPath
    )

    $lines = @(& $SevenZipPath l -slt $ArchivePath 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to list archive '$ArchivePath': $($lines -join [Environment]::NewLine)"
    }
    $blocks = [Collections.Generic.List[hashtable]]::new()
    $current = @{}
    $inEntries = $false
    foreach ($line in $lines) {
        $text = [string]$line
        if ($text -eq '----------') {
            $inEntries = $true
            continue
        }
        if (-not $inEntries) {
            continue
        }
        if ([string]::IsNullOrWhiteSpace($text)) {
            if ($current.ContainsKey('Path')) {
                $blocks.Add($current)
            }
            $current = @{}
            continue
        }
        if ($text -match '^([^=]+) = (.*)$') {
            $current[$matches[1].Trim()] = $matches[2]
        }
    }
    if ($current.ContainsKey('Path')) {
        $blocks.Add($current)
    }
    if ($blocks.Count -eq 0) {
        throw "Pinned 7-Zip returned no archive members for '$ArchivePath'"
    }

    $entryBlocks = @($blocks | Where-Object {
        (ConvertTo-SafeArchivePath -Member ([string]$_.Path)) -ne '.'
    })
    $validatedNames = @(Assert-ArchiveMemberNames -Members @($entryBlocks | ForEach-Object { [string]$_.Path }))
    $members = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $entryBlocks.Count; $index++) {
        $block = $entryBlocks[$index]
        $symbolicLink = if ($block.ContainsKey('Symbolic Link')) { [string]$block['Symbolic Link'] } else { '' }
        $hardLink = if ($block.ContainsKey('Hard Link')) { [string]$block['Hard Link'] } else { '' }
        $type = if (-not [string]::IsNullOrWhiteSpace($symbolicLink)) {
            'symlink'
        } elseif (-not [string]::IsNullOrWhiteSpace($hardLink)) {
            'hardlink'
        } elseif ($block.ContainsKey('Folder') -and $block.Folder -eq '+') {
            'directory'
        } else {
            'file'
        }
        $members.Add([pscustomobject]@{
            path = $validatedNames[$index].path
            archivePath = $validatedNames[$index].archivePath
            type = $type
            target = if ($type -eq 'symlink') { $symbolicLink } elseif ($type -eq 'hardlink') { $hardLink } else { $null }
        })
    }

    Assert-ArchiveLinks -Members $members
    return @($members)
}

function Resolve-ArchiveLinkTarget {
    param([Parameter(Mandatory = $true)] $Member)

    if ($Member.type -eq 'hardlink') {
        return ConvertTo-SafeArchivePath -Member ([string]$Member.target)
    }
    $parent = [IO.Path]::GetDirectoryName(([string]$Member.path).Replace('/', '\'))
    $candidate = if ([string]::IsNullOrEmpty($parent)) {
        [string]$Member.target
    } else {
        "$($parent.Replace('\', '/'))/$($Member.target)"
    }
    $segments = [Collections.Generic.List[string]]::new()
    foreach ($segment in $candidate.Replace('\', '/').Split('/')) {
        if ([string]::IsNullOrEmpty($segment) -or $segment -eq '.') {
            continue
        }
        if ($segment -eq '..') {
            if ($segments.Count -eq 0) {
                throw "Archive link '$($Member.path)' escapes extraction root"
            }
            $segments.RemoveAt($segments.Count - 1)
            continue
        }
        $segments.Add($segment)
    }
    return ConvertTo-SafeArchivePath -Member ($segments -join '/')
}

function Assert-ArchiveLinks {
    param([Parameter(Mandatory = $true)] $Members)

    $memberByPath = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($member in $Members) {
        $memberByPath.Add([string]$member.path, $member)
    }
    foreach ($member in $members | Where-Object type -in @('symlink', 'hardlink')) {
        if ([string]::IsNullOrWhiteSpace($member.target) -or
            $member.target.StartsWith('/', [StringComparison]::Ordinal) -or
            $member.target -match '^[A-Za-z]:') {
            throw "Archive link '$($member.path)' has unsafe target '$($member.target)'"
        }
        $targetPath = Resolve-ArchiveLinkTarget -Member $member
        if (-not $memberByPath.ContainsKey($targetPath)) {
            throw "Archive link '$($member.path)' targets missing member '$targetPath'"
        }
        if ($member.type -eq 'hardlink' -and $memberByPath[$targetPath].type -ne 'file') {
            throw "Archive hard link '$($member.path)' does not target a regular archive member"
        }
    }

    foreach ($member in $members | Where-Object type -eq 'symlink') {
        $visited = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $cursor = $member
        while ($cursor.type -eq 'symlink') {
            if (-not $visited.Add([string]$cursor.path)) {
                throw "Archive symlink '$($member.path)' is cyclic"
            }
            $targetPath = Resolve-ArchiveLinkTarget -Member $cursor
            $cursor = $memberByPath[$targetPath]
        }
        if ($cursor.type -ne 'file') {
            throw "Archive symlink '$($member.path)' does not resolve to a regular archive member"
        }
    }
}

function Assert-LinkTargetSafe {
    param(
        [Parameter(Mandatory = $true)][string] $LinkPath,
        [Parameter(Mandatory = $true)][string] $LinkTarget,
        [Parameter(Mandatory = $true)][string] $Root
    )
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($LinkTarget) -or
        [IO.Path]::IsPathRooted($LinkTarget) -or
        $LinkTarget -match '^[A-Za-z]:') {
        throw "Link '$LinkPath' has unsafe target '$LinkTarget'"
    }
    $resolvedTarget = [IO.Path]::GetFullPath(
        (Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($LinkPath))) $LinkTarget))
    if (-not $resolvedTarget.StartsWith("$rootFull\", [StringComparison]::OrdinalIgnoreCase) -and
        -not $resolvedTarget.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Link '$LinkPath' escapes root '$Root'"
    }
}

function Assert-ExtractedLinksSafe {
    param([Parameter(Mandatory = $true)][string] $Root)

    foreach ($item in Get-ChildItem -LiteralPath $Root -Force -Recurse) {
        if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            continue
        }
        if ($item.PSIsContainer) {
            throw "Extracted archive contains an unsupported directory reparse point: $($item.FullName)"
        }
        $target = [string]$item.LinkTarget
        Assert-LinkTargetSafe -LinkPath $item.FullName -LinkTarget $target -Root $Root
    }
}

function Expand-VerifiedArchive {
    param(
        [Parameter(Mandatory = $true)][string] $ArchivePath,
        [Parameter(Mandatory = $true)][string] $Destination,
        [string] $SevenZipPath
    )

    Assert-PrivatePath -Path $Destination
    if (Test-Path -LiteralPath $Destination) {
        throw "Extraction destination must be fresh: $Destination"
    }
    if ([string]::IsNullOrWhiteSpace($SevenZipPath) -or
        -not (Test-Path -LiteralPath $SevenZipPath -PathType Leaf)) {
        throw "Pinned 7-Zip extractor is required for '$ArchivePath'"
    }
    $archiveToExtract = $ArchivePath
    $intermediateDirectory = $null
    try {
        if ($ArchivePath.EndsWith('.pkg.tar.zst', [StringComparison]::OrdinalIgnoreCase)) {
            $intermediateDirectory = "$Destination.archive"
            if (Test-Path -LiteralPath $intermediateDirectory) {
                throw "Intermediate extraction path must be fresh: $intermediateDirectory"
            }
            New-Item -ItemType Directory -Path $intermediateDirectory | Out-Null
            $output = @(& $SevenZipPath x $ArchivePath "-o$intermediateDirectory" -y 2>&1)
            if ($LASTEXITCODE -ne 0) {
                throw "7-Zip decompression failed for '$ArchivePath': $($output -join [Environment]::NewLine)"
            }
            $inner = @(Get-ChildItem -LiteralPath $intermediateDirectory -File -Force)
            if ($inner.Count -ne 1 -or -not $inner[0].Name.EndsWith('.tar', [StringComparison]::OrdinalIgnoreCase)) {
                throw "Package input must decompress to exactly one tar archive: $ArchivePath"
            }
            $archiveToExtract = $inner[0].FullName
        }
        $members = @(Get-ArchiveMembers -ArchivePath $archiveToExtract -SevenZipPath $SevenZipPath)
        $output = @(& $SevenZipPath x $archiveToExtract "-o$Destination" -y -snl -snh 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw "7-Zip extraction failed for '$ArchivePath': $($output -join [Environment]::NewLine)"
        }
        if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
            throw "Archive extraction did not create '$Destination'"
        }
        Assert-ExtractedLinksSafe -Root $Destination

        $expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($member in $members) {
            $path = Join-Path $Destination $member.path.Replace('/', '\')
            if (-not (Test-Path -LiteralPath $path)) {
                throw "Extractor omitted archive member '$($member.path)'"
            }
            $item = Get-Item -LiteralPath $path -Force
            if ($member.type -eq 'directory' -and -not $item.PSIsContainer) {
                throw "Archive directory changed type during extraction: $($member.path)"
            }
            if ($member.type -eq 'symlink' -and
                (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                [string]$item.LinkTarget.Replace('\', '/') -cne [string]$member.target.Replace('\', '/'))) {
                throw "Archive symlink was not preserved exactly: $($member.path)"
            }
            if ($member.type -eq 'hardlink' -and $item.LinkType -ne 'HardLink') {
                throw "Archive hard link was not preserved: $($member.path)"
            }
            if ($member.type -ne 'directory') {
                $null = $expected.Add($member.path)
            }
        }
        foreach ($item in Get-ChildItem -LiteralPath $Destination -Force -Recurse |
            Where-Object { -not $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }) {
            $relative = Get-RelativeUnixPath -Root $Destination -Path $item.FullName
            if (-not $expected.Contains($relative)) {
                throw "Extractor created unexpected archive output '$relative'"
            }
        }
        return @($members)
    }
    finally {
        if ($null -ne $intermediateDirectory -and (Test-Path -LiteralPath $intermediateDirectory)) {
            Remove-Item -LiteralPath $intermediateDirectory -Force -Recurse
        }
    }
}

function Get-PeArchitecture {
    param([Parameter(Mandatory = $true)][string] $Path)

    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) {
            return $null
        }
        $stream.Position = 0x3c
        $peOffset = $reader.ReadUInt32()
        if ($peOffset -gt $stream.Length - 6) {
            throw "Malformed PE header offset in '$Path'"
        }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Malformed PE signature in '$Path'"
        }
        $machine = $reader.ReadUInt16()
        switch ($machine) {
            0xAA64 { return 'arm64' }
            0x8664 { return 'x64' }
            0x014c { return 'x86-or-clr' }
            0xA641 { return 'arm64ec' }
            0xA64E { return 'arm64x' }
            default { return ('unknown-0x{0:x4}' -f $machine) }
        }
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Invoke-PseudoRelocScanner {
    param(
        [Parameter(Mandatory = $true)][string] $ScannerPath,
        [Parameter(Mandatory = $true)][string] $PePath,
        [Parameter(Mandatory = $true)][string] $OutputPath,
        [Parameter(Mandatory = $true)][string] $ObjdumpPath,
        [Parameter(Mandatory = $true)][string] $NmPath,
        [string] $PrivateToolPath,
        [switch] $RequireScalar64
    )

    foreach ($required in @($ScannerPath, $PePath, $ObjdumpPath, $NmPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Pseudo-reloc scanner input is missing: $required"
        }
    }
    $oldPath = $env:PATH
    try {
        if (-not [string]::IsNullOrWhiteSpace($PrivateToolPath)) {
            Assert-PrivatePath -Path $PrivateToolPath
            $env:PATH = "$PrivateToolPath;$oldPath"
        }
        & pwsh -NoLogo -NoProfile -File $ScannerPath `
            -PePath $PePath `
            -OutputPath $OutputPath `
            -Objdump $ObjdumpPath `
            -Nm $NmPath
        if ($LASTEXITCODE -ne 0) {
            throw "Pseudo-reloc scanner failed for '$PePath' with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:PATH = $oldPath
    }
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
        throw "Pseudo-reloc scanner did not emit evidence for '$PePath'"
    }
    $result = Get-Content -LiteralPath $OutputPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($result.result -ne 'pass' -or @($result.policy_violations).Count -ne 0) {
        throw "Pseudo-reloc scanner rejected '$PePath'"
    }
    if ($RequireScalar64) {
        $nonScalar64 = @($result.flags | Where-Object { [int]$_ -ne 64 })
        if ($nonScalar64.Count -ne 0) {
            throw "Pseudo-reloc scanner found non-scalar64 records in '$PePath': $($nonScalar64 -join ', ')"
        }
    }
    return $result
}

function Assert-EvidenceComplete {
    param([Parameter(Mandatory = $true)] $Evidence)

    if ($Evidence.schemaVersion -ne 1) {
        throw "Unsupported validation evidence schema"
    }
    foreach ($field in @('previewId', 'machine', 'processes', 'modules', 'tests', 'artifacts', 'result')) {
        if ($null -eq $Evidence.PSObject.Properties[$field]) {
            throw "Validation evidence is missing '$field'"
        }
    }
    foreach ($testId in @(
        'bash-startup',
        'bash-noninteractive',
        'bash-interactive',
        'shell-semantics',
        'fork-spawn',
        'terminal',
        'git-worktree',
        'git-bare-transport',
        'git-hook',
        'symlink-path'
    )) {
        if (@($Evidence.tests | Where-Object id -eq $testId).Count -ne 1) {
            throw "Validation evidence is missing test '$testId'"
        }
    }
    if (@($Evidence.artifacts | Where-Object { $_.kind -in @('lock', 'provenance', 'payload') }).Count -ne 3) {
        throw "Validation evidence must bind lock, provenance, and payload artifacts"
    }
}

function Assert-NoPreparationTools {
    param([Parameter(Mandatory = $true)][string] $Root)

    $forbiddenNames = @(
        '7zr.exe',
        '7za.exe',
        'aarch64-pc-cygwin-objdump.exe',
        'aarch64-pc-cygwin-nm.exe',
        'aarch64-pc-cygwin-ld.exe',
        'aarch64-pc-msys-objdump.exe',
        'aarch64-pc-msys-nm.exe',
        'aarch64-pc-msys-ld.exe'
    )
    $evidencePrefix = ([IO.Path]::GetFullPath((Join-Path $Root 'preview-evidence'))).TrimEnd('\') + '\'
    $leaks = @(Get-ChildItem -LiteralPath $Root -File -Force -Recurse |
        Where-Object {
            $_.Name -in $forbiddenNames -and
            -not $_.FullName.StartsWith($evidencePrefix, [StringComparison]::OrdinalIgnoreCase)
        })
    if ($leaks.Count -ne 0) {
        throw "Preparation-only tools leaked into the preview payload: $($leaks.FullName -join ', ')"
    }
}

Export-ModuleMember -Function @(
    'Assert-ArchiveMemberNames',
    'Assert-ArchiveLinks',
    'Assert-EvidenceComplete',
    'Assert-LinkTargetSafe',
    'Assert-NoPreparationTools',
    'Assert-PreviewLock',
    'Assert-PrivatePath',
    'ConvertTo-SafeArchivePath',
    'Expand-VerifiedArchive',
    'Get-ArchiveMembers',
    'Get-CanonicalDirectoryManifest',
    'Get-PeArchitecture',
    'Get-RelativeUnixPath',
    'Get-Sha256',
    'Get-VerifiedInput',
    'Invoke-PseudoRelocScanner',
    'Read-PreviewLock'
)
