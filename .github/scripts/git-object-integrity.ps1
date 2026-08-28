[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Arm64GitObjectFormatValue {
    param([AllowNull()][object]$Output)

    $values = @(@($Output) |
            Where-Object { $null -ne $_ } |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_.Length -gt 0 })
    if ($values.Count -ne 1) {
        throw 'Git object format is absent or ambiguous.'
    }
    $format = $values[0]
    if ($format -cnotmatch '^[a-z0-9]{1,16}$') {
        throw 'Git object format is not a recognizable identifier.'
    }
    if ($format -cne 'sha1') {
        # Every binding in this policy is a 40-hex SHA-1 object ID. A sha256 (or future)
        # repository is not supported and must fail closed rather than be misread.
        throw "Git object format is not sha1: $format"
    }
    return $format
}

function Assert-Arm64GitObjectFormat {
    param([Parameter(Mandatory)][string]$RepositoryRoot)

    $output = @(& git -C $RepositoryRoot rev-parse --show-object-format)
    if ($LASTEXITCODE -ne 0) {
        throw 'Git object format could not be determined.'
    }
    return Assert-Arm64GitObjectFormatValue -Output $output
}

function Test-Arm64GitObjectId {
    param([AllowNull()][object]$Value)

    return $Value -is [string] -and
        $Value -cmatch '^[0-9a-f]{40}$' -and
        $Value -cne ('0' * 40)
}

function Get-Arm64RawPathIdentity {
    param([Parameter(Mandatory)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or
        $Path -cnotmatch '^[\x20-\x7e]+$' -or
        $Path.Contains('\', [StringComparison]::Ordinal) -or
        $Path.StartsWith('/', [StringComparison]::Ordinal) -or
        $Path.EndsWith('/', [StringComparison]::Ordinal) -or
        $Path -match '(?:^|/)\.{1,2}(?:/|$)' -or
        $Path.Normalize([Text.NormalizationForm]::FormC) -cne $Path) {
        throw "Git path is not a canonical ASCII repository path: $Path"
    }

    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Path))
}

function Get-Arm64GitBlobOid {
    [CmdletBinding(DefaultParameterSetName = 'Stream')]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Stream')]
        [IO.Stream]$Stream,
        [Parameter(Mandatory, ParameterSetName = 'Stream')]
        [long]$Length,
        [Parameter(Mandatory, ParameterSetName = 'Bytes')]
        [byte[]]$Bytes
    )

    if ($PSCmdlet.ParameterSetName -ceq 'Bytes') {
        $Stream = [IO.MemoryStream]::new($Bytes, $false)
        $Length = $Bytes.LongLength
        $disposeStream = $true
    }
    else {
        $disposeStream = $false
    }

    if ($Length -lt 0 -or -not $Stream.CanRead) {
        throw 'Git blob input must be a readable stream with a non-negative length.'
    }

    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        $prefix = [Text.Encoding]::UTF8.GetBytes("blob $Length`0")
        [void]$sha1.TransformBlock($prefix, 0, $prefix.Length, $null, 0)

        $remaining = $Length
        $buffer = [byte[]]::new(65536)
        while ($remaining -gt 0) {
            $requested = [int][Math]::Min($buffer.Length, $remaining)
            $read = $Stream.Read($buffer, 0, $requested)
            if ($read -le 0) {
                throw 'Git blob stream ended before its declared byte length.'
            }
            [void]$sha1.TransformBlock($buffer, 0, $read, $null, 0)
            $remaining -= $read
        }
        if ($Stream.ReadByte() -ne -1) {
            throw 'Git blob stream exceeds its declared byte length.'
        }
        [void]$sha1.TransformFinalBlock([byte[]]::new(0), 0, 0)
        return -join ($sha1.Hash | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha1.Dispose()
        if ($disposeStream) {
            $Stream.Dispose()
        }
    }
}

function Get-Arm64FileBlobIdentity {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    try {
        $length = $stream.Length
        $oid = Get-Arm64GitBlobOid -Stream $stream -Length $length
        return [pscustomobject][ordered]@{
            byte_length = [long]$length
            oid         = [string]$oid
        }
    }
    finally {
        $stream.Dispose()
    }
}

function New-Arm64SourceBinding {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Mode,
        [Parameter(Mandatory)][string]$ObjectType,
        [Parameter(Mandatory)][long]$ByteLength,
        [Parameter(Mandatory)][string]$Oid
    )

    if ($Mode -notin @('100644', '100755') -or
        $ObjectType -cne 'blob' -or
        $ByteLength -lt 0 -or
        -not (Test-Arm64GitObjectId $Oid)) {
        throw "Invalid Git blob source binding: $Path"
    }

    return [pscustomobject][ordered]@{
        path                 = $Path
        raw_path_utf8_base64 = Get-Arm64RawPathIdentity -Path $Path
        mode                 = $Mode
        object_type          = $ObjectType
        byte_length          = $ByteLength
        oid                  = $Oid
    }
}

function Assert-Arm64SourceBinding {
    param(
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][string]$Label
    )

    $expectedProperties = @(
        'path',
        'raw_path_utf8_base64',
        'mode',
        'object_type',
        'byte_length',
        'oid'
    )
    $actualProperties = @($Binding.PSObject.Properties.Name | Sort-Object)
    if (($actualProperties -join "`0") -cne (($expectedProperties | Sort-Object) -join "`0")) {
        throw "Source binding schema is not exact: $Label"
    }
    $expectedRawPath = Get-Arm64RawPathIdentity -Path ([string]$Binding.path)
    if ($Binding.raw_path_utf8_base64 -cne $expectedRawPath -or
        $Binding.mode -notin @('100644', '100755') -or
        $Binding.object_type -cne 'blob' -or
        -not ($Binding.byte_length -is [int] -or $Binding.byte_length -is [long]) -or
        [long]$Binding.byte_length -lt 0 -or
        -not (Test-Arm64GitObjectId $Binding.oid)) {
        throw "Source binding values are invalid: $Label"
    }
}

function Test-Arm64SourceBindingEqual {
    param(
        [Parameter(Mandatory)][object]$Expected,
        [Parameter(Mandatory)][object]$Actual
    )

    Assert-Arm64SourceBinding -Binding $Expected -Label 'expected'
    Assert-Arm64SourceBinding -Binding $Actual -Label 'actual'
    foreach ($property in @(
            'path',
            'raw_path_utf8_base64',
            'mode',
            'object_type',
            'byte_length',
            'oid')) {
        if ($Expected.$property -cne $Actual.$property) {
            return $false
        }
    }
    return $true
}

function Assert-Arm64SourceBindingSetsEqual {
    param(
        [Parameter(Mandatory)][object[]]$Expected,
        [Parameter(Mandatory)][object[]]$Actual,
        [string]$Label = 'source'
    )

    $expectedSorted = @($Expected | Sort-Object path)
    $actualSorted = @($Actual | Sort-Object path)
    if ($expectedSorted.Count -ne $actualSorted.Count) {
        throw "$Label-set-mismatch"
    }
    for ($index = 0; $index -lt $expectedSorted.Count; $index++) {
        if (-not (Test-Arm64SourceBindingEqual `
                -Expected $expectedSorted[$index] `
                -Actual $actualSorted[$index])) {
            throw "$Label-binding-mismatch:$($expectedSorted[$index].path)"
        }
    }
}

function Get-Arm64LocalGitTreeEntries {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$Revision = 'HEAD'
    )

    if ($Revision -cnotmatch '^(?:HEAD|[0-9a-f]{40})$') {
        throw "Invalid Git revision for source binding: $Revision"
    }
    [void](Assert-Arm64GitObjectFormat -RepositoryRoot $RepositoryRoot)
    $topLevel = (& git -C $RepositoryRoot rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or
        [IO.Path]::GetFullPath($topLevel) -cne [IO.Path]::GetFullPath($RepositoryRoot)) {
        throw 'Git source-binding root must be the exact repository top level.'
    }
    $lines = @(
        & git -C $RepositoryRoot -c core.quotePath=false ls-tree -r -t -l --full-tree $Revision
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to enumerate Git tree: $Revision"
    }

    $entries = [Collections.Generic.List[object]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($line in $lines) {
        if ($line -cnotmatch '^(?<mode>[0-9]{6}) (?<type>[a-z]+) (?<oid>[0-9a-f]+) +(?<size>[0-9]+|-)\t(?<path>.+)$') {
            throw 'Malformed or truncated Git tree entry.'
        }
        $mode = $Matches.mode
        $type = $Matches.type
        $oid = $Matches.oid
        $sizeText = $Matches.size
        $path = $Matches.path
        [void](Get-Arm64RawPathIdentity -Path $path)
        if (-not (Test-Arm64GitObjectId $oid)) {
            throw "Git tree entry has an invalid object ID: $path"
        }

        $validShape = ($type -ceq 'tree' -and $mode -ceq '040000' -and $sizeText -ceq '-') -or
            ($type -ceq 'blob' -and $mode -in @('100644', '100755', '120000') -and
                $sizeText -cmatch '^[0-9]+$') -or
            ($type -ceq 'commit' -and $mode -ceq '160000' -and $sizeText -ceq '-')
        if (-not $validShape) {
            throw "Git tree entry has an invalid type/mode/size tuple: $path"
        }

        if (-not $exactPaths.Add($path)) {
            throw "Git tree contains a duplicate path: $path"
        }
        $aliasKey = $path.Normalize([Text.NormalizationForm]::FormC).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "Git tree contains a casefold or NFC path alias: $path"
        }

        [void]$entries.Add([pscustomobject][ordered]@{
                path        = $path
                mode        = $mode
                object_type = $type
                oid         = $oid
                byte_length = if ($sizeText -ceq '-') { $null } else { [long]$sizeText }
            })
    }
    return @($entries)
}

function Get-Arm64ValidatedRestTreeEntries {
    param(
        [Parameter(Mandatory)][object]$TreeResponse,
        [Parameter(Mandatory)][string]$ExpectedTree,
        [int]$MaximumRecords = 10000
    )

    if (-not (Test-Arm64GitObjectId $ExpectedTree) -or
        $TreeResponse.sha -cne $ExpectedTree -or
        $TreeResponse.truncated -isnot [bool] -or
        $TreeResponse.truncated -or
        $TreeResponse.tree -is [string] -or
        $TreeResponse.tree -isnot [Collections.IEnumerable]) {
        throw 'Candidate tree response is malformed, moved, or truncated.'
    }
    $rawEntries = @($TreeResponse.tree)
    if ($rawEntries.Count -gt $MaximumRecords) {
        throw 'Candidate tree response exceeds the record limit.'
    }

    $entries = [Collections.Generic.List[object]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($entry in $rawEntries) {
        foreach ($propertyName in @('path', 'mode', 'type', 'sha', 'url')) {
            if ($null -eq $entry.PSObject.Properties[$propertyName]) {
                throw "Candidate tree entry is missing $propertyName."
            }
        }
        $path = [string]$entry.path
        $mode = [string]$entry.mode
        $type = [string]$entry.type
        $oid = [string]$entry.sha
        [void](Get-Arm64RawPathIdentity -Path $path)
        if (-not (Test-Arm64GitObjectId $oid)) {
            throw "Candidate tree entry has an invalid object ID: $path"
        }
        if (-not $exactPaths.Add($path)) {
            throw "Candidate tree contains a duplicate path: $path"
        }
        $aliasKey = $path.Normalize([Text.NormalizationForm]::FormC).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "Candidate tree contains a casefold or NFC path alias: $path"
        }

        $sizeProperty = $entry.PSObject.Properties['size']
        $validShape = ($type -ceq 'tree' -and $mode -ceq '040000' -and
                $null -eq $sizeProperty) -or
            ($type -ceq 'blob' -and $mode -in @('100644', '100755', '120000') -and
                $null -ne $sizeProperty -and
                ($sizeProperty.Value -is [int] -or $sizeProperty.Value -is [long]) -and
                [long]$sizeProperty.Value -ge 0) -or
            ($type -ceq 'commit' -and $mode -ceq '160000' -and
                $null -eq $sizeProperty)
        if (-not $validShape) {
            throw "Candidate tree entry has an invalid type/mode/size tuple: $path"
        }

        if ($type -ceq 'commit' -or $mode -ceq '120000') {
            throw "Candidate tree contains a gitlink or symlink: $path"
        }
        if ($path -in @('.github/workflows', '.github/scripts', '.github/policies') -and
            $type -cne 'tree') {
            throw "Candidate blob occupies a protected directory namespace: $path"
        }
        if ($path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -and
            (($type -ceq 'tree') -or
                ($type -ceq 'blob' -and $path -cnotmatch '^\.github/workflows/[^/]+\.ya?ml$'))) {
            throw "Candidate workflow namespace contains an unexpected entry: $path"
        }

        [void]$entries.Add([pscustomobject][ordered]@{
                path        = $path
                mode        = $mode
                object_type = $type
                oid         = $oid
                byte_length = if ($null -eq $sizeProperty) {
                    $null
                }
                else {
                    [long]$sizeProperty.Value
                }
                api_url     = [string]$entry.url
            })
    }
    return @($entries)
}

function Get-Arm64ProtectedGitSourceBindings {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$Revision = 'HEAD'
    )

    $protectedPrefixes = @('.github/workflows/', '.github/scripts/', '.github/policies/')
    $directoryNamespaces = @('.github/workflows', '.github/scripts', '.github/policies')
    $bindings = [Collections.Generic.List[object]]::new()
    foreach ($entry in Get-Arm64LocalGitTreeEntries `
            -RepositoryRoot $RepositoryRoot `
            -Revision $Revision) {
        $isProtected = @($protectedPrefixes | Where-Object {
                $entry.path.StartsWith($_, [StringComparison]::Ordinal)
            }).Count -gt 0
        if (-not $isProtected -and $directoryNamespaces -cnotcontains $entry.path) {
            continue
        }
        if ($entry.object_type -ceq 'commit' -or $entry.mode -ceq '120000') {
            throw "Protected Git namespace contains a gitlink or symlink: $($entry.path)"
        }
        if ($directoryNamespaces -ccontains $entry.path) {
            if ($entry.object_type -cne 'tree') {
                throw "Protected directory namespace is not a tree: $($entry.path)"
            }
            continue
        }
        if ($entry.path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -and
            ($entry.object_type -cne 'blob' -or
                $entry.path.Substring('.github/workflows/'.Length).Contains(
                    '/',
                    [StringComparison]::Ordinal
                ) -or
                $entry.path -cnotmatch '\.ya?ml$')) {
            throw "Unexpected entry under the active workflow namespace: $($entry.path)"
        }
        if ($entry.object_type -ceq 'tree') {
            continue
        }
        if ($entry.object_type -cne 'blob') {
            throw "Unexpected protected Git tree entry: $($entry.path)"
        }

        $filePath = Join-Path $RepositoryRoot (
            $entry.path.Replace('/', [IO.Path]::DirectorySeparatorChar)
        )
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "Protected Git blob is absent from the checkout: $($entry.path)"
        }
        $identity = Get-Arm64FileBlobIdentity -Path $filePath
        if ($identity.byte_length -ne $entry.byte_length -or $identity.oid -cne $entry.oid) {
            throw "Protected checkout bytes differ from the Git object: $($entry.path)"
        }
        [void]$bindings.Add((New-Arm64SourceBinding `
                    -Path $entry.path `
                    -Mode $entry.mode `
                    -ObjectType $entry.object_type `
                    -ByteLength $entry.byte_length `
                    -Oid $entry.oid))
    }
    return @($bindings | Sort-Object path)
}

if ($MyInvocation.InvocationName -ne '.') {
    throw 'git-object-integrity.ps1 is a dot-source-only helper.'
}
