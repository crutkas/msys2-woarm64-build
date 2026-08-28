[CmdletBinding(DefaultParameterSetName = 'Collect')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Seal')]
    [switch] $CaptureSharedRootSeal,

    [Parameter(Mandatory = $true, ParameterSetName = 'Seal')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $SharedRootPath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Seal')]
    [string] $SealOutputPath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $RepositoryRoot,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $OutputDirectory,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $ExpectedHead,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $BaseCommit,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $RepositoryId,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $RepositoryNodeId,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $RepositoryName,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [ValidateSet('push', 'pull_request')]
    [string] $EventName,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $EventRef,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $GitHubSha,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $Branch,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $BaseBranch,

    [Parameter(ParameterSetName = 'Collect')]
    [string] $PullRequestNumber = '',

    [Parameter(ParameterSetName = 'Collect')]
    [string] $PullRequestHead = '',

    [Parameter(ParameterSetName = 'Collect')]
    [string] $PullRequestBase = '',

    [Parameter(ParameterSetName = 'Collect')]
    [string] $PullRequestHeadRepositoryId = '',

    [Parameter(ParameterSetName = 'Collect')]
    [string] $PullRequestBaseRepositoryId = '',

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $RunId,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [int] $RunAttempt,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $WorkflowRef,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $ArtifactName,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $ExpectedSessionId,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $AssemblerLogPath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $EtwLogPath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $SharedRootBeforePath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Collect')]
    [string] $SharedRootAfterPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = [Text.UTF8Encoding]::new($false)
$script:StrictUtf8 = [Text.UTF8Encoding]::new($false, $true)
$script:EmptySha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
$script:GitWorkingDirectory = $null

function Test-OrdinalEqual {
    param(
        [AllowNull()][string] $Left,
        [AllowNull()][string] $Right
    )
    return [string]::Equals($Left, $Right, [StringComparison]::Ordinal)
}

function Assert-OrdinalEqual {
    param(
        [AllowNull()][string] $Expected,
        [AllowNull()][string] $Actual,
        [Parameter(Mandatory = $true)][string] $Message
    )
    if (-not (Test-OrdinalEqual -Left $Expected -Right $Actual)) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

function Get-SortedOrdinal {
    param([Parameter(Mandatory = $true)][object[]] $Values)
    $result = [string[]]@($Values | ForEach-Object { [string]$_ })
    [Array]::Sort($result, [StringComparer]::Ordinal)
    return $result
}

function Get-ByteSha256 {
    param([Parameter(Mandatory = $true)][byte[]] $Bytes)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return [Convert]::ToHexString($hasher.ComputeHash($Bytes)).ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-FileRecord {
    param([Parameter(Mandatory = $true)][string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required evidence input is absent: $Path"
    }
    $bytes = [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($Path))
    return [ordered]@{
        bytes = [int64]$bytes.Length
        sha256 = Get-ByteSha256 -Bytes $bytes
    }
}

function Write-CanonicalJson {
    param(
        [Parameter(Mandatory = $true)] $Value,
        [Parameter(Mandatory = $true)][string] $Path
    )
    $parent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $parent
    }
    $json = ($Value | ConvertTo-Json -Depth 100 -Compress) + "`n"
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Path), $json, $script:Utf8NoBom)
}

function Get-SharedRootSeal {
    param([Parameter(Mandatory = $true)][string] $RootPath)

    $canonicalRoot = [IO.Path]::GetFullPath($RootPath).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $canonicalRoot)) {
        return [ordered]@{
            rootPath = $canonicalRoot
            exists = $false
            observedPaths = @('var/log/pacman.log', 'var/lib/pacman/local')
            log = [ordered]@{
                exists = $false
                bytes = 0
                sha256 = $script:EmptySha256
            }
            database = [ordered]@{
                exists = $false
                directories = 0
                files = 0
                fileBytes = 0
                canonicalManifestSha256 = $script:EmptySha256
            }
        }
    }
    if (-not (Test-Path -LiteralPath $canonicalRoot -PathType Container)) {
        throw "Shared root is not a directory: $canonicalRoot"
    }
    if ((Get-Item -LiteralPath $canonicalRoot -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw "Shared root is a reparse point: $canonicalRoot"
    }

    $logPath = Join-Path $canonicalRoot 'var\log\pacman.log'
    $log = if (Test-Path -LiteralPath $logPath -PathType Leaf) {
        $item = Get-Item -LiteralPath $logPath -Force
        [ordered]@{
            exists = $true
            bytes = [int64]$item.Length
            sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).
                Hash.ToLowerInvariant()
        }
    }
    else {
        [ordered]@{
            exists = $false
            bytes = 0
            sha256 = $script:EmptySha256
        }
    }

    $databasePath = Join-Path $canonicalRoot 'var\lib\pacman\local'
    if (-not (Test-Path -LiteralPath $databasePath)) {
        $database = [ordered]@{
            exists = $false
            directories = 0
            files = 0
            fileBytes = 0
            canonicalManifestSha256 = $script:EmptySha256
        }
        return [ordered]@{
            rootPath = $canonicalRoot
            exists = $true
            observedPaths = @('var/log/pacman.log', 'var/lib/pacman/local')
            log = $log
            database = $database
        }
    }
    if (-not (Test-Path -LiteralPath $databasePath -PathType Container)) {
        throw "Shared package database is not a directory: $databasePath"
    }
    if ((Get-Item -LiteralPath $databasePath -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw "Shared package database is a reparse point: $databasePath"
    }

    $itemsByRelativePath =
        [Collections.Generic.Dictionary[string, IO.FileSystemInfo]]::new(
            [StringComparer]::Ordinal)
    foreach ($item in Get-ChildItem -LiteralPath $databasePath -Force -Recurse) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Shared package database contains a reparse point: $($item.FullName)"
        }
        $relative = [IO.Path]::GetRelativePath($databasePath, $item.FullName)
        if (-not $itemsByRelativePath.TryAdd($relative, $item)) {
            throw "Shared package database contains duplicate ordinal paths: $relative"
        }
    }

    $directoryCount = 0
    $fileCount = 0
    [int64]$fileBytes = 0
    $manifestLines = [Collections.Generic.List[string]]::new()
    foreach ($relative in Get-SortedOrdinal -Values @($itemsByRelativePath.Keys)) {
        $item = $itemsByRelativePath[$relative]
        if ($item -is [IO.DirectoryInfo]) {
            $directoryCount++
            $record = [ordered]@{ type = 'directory'; path = $relative }
        }
        elseif ($item -is [IO.FileInfo]) {
            $fileCount++
            $fileBytes += $item.Length
            $record = [ordered]@{
                type = 'file'
                path = $relative
                bytes = [int64]$item.Length
                sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).
                    Hash.ToLowerInvariant()
            }
        }
        else {
            throw "Shared package database contains an unsupported entry: $($item.FullName)"
        }
        $manifestLines.Add(($record | ConvertTo-Json -Compress))
    }
    $manifest = if ($manifestLines.Count -eq 0) {
        [byte[]]::new(0)
    }
    else {
        $script:Utf8NoBom.GetBytes(($manifestLines -join "`n") + "`n")
    }

    $database = [ordered]@{
        exists = $true
        directories = $directoryCount
        files = $fileCount
        fileBytes = $fileBytes
        canonicalManifestSha256 = Get-ByteSha256 -Bytes $manifest
    }
    return [ordered]@{
        rootPath = $canonicalRoot
        exists = $true
        observedPaths = @('var/log/pacman.log', 'var/lib/pacman/local')
        log = $log
        database = $database
    }
}

function Invoke-GitRaw {
    param([Parameter(Mandatory = $true)][string[]] $Arguments)

    $git = @(Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue)[0]
    if ($null -eq $git) {
        $git = @(Get-Command git -CommandType Application -ErrorAction Stop)[0]
    }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $git.Source
    if (-not [string]::IsNullOrWhiteSpace($script:GitWorkingDirectory)) {
        $start.WorkingDirectory = $script:GitWorkingDirectory
    }
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    foreach ($argument in $Arguments) {
        $start.ArgumentList.Add($argument)
    }

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) {
            throw "Could not start git $($Arguments -join ' ')"
        }
        $errorTask = $process.StandardError.ReadToEndAsync()
        $output = [IO.MemoryStream]::new()
        try {
            $process.StandardOutput.BaseStream.CopyTo($output)
            $process.WaitForExit()
            $errorText = $errorTask.GetAwaiter().GetResult()
            if ($process.ExitCode -ne 0) {
                throw "git $($Arguments -join ' ') failed ($($process.ExitCode)): $errorText"
            }
            return ,([byte[]]$output.ToArray())
        }
        finally {
            $output.Dispose()
        }
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-GitText {
    param([Parameter(Mandatory = $true)][string[]] $Arguments)
    $bytes = Invoke-GitRaw -Arguments $Arguments
    return $script:StrictUtf8.GetString($bytes).TrimEnd([char[]]"`r`n")
}

function Get-GitBlobRecord {
    param(
        [Parameter(Mandatory = $true)][string] $Commit,
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $Root,
        [Parameter(Mandatory = $true)][string] $Role
    )

    $blob = Invoke-GitRaw -Arguments @('cat-file', 'blob', "$Commit`:$Path")
    $blobId = Invoke-GitText -Arguments @('rev-parse', "$Commit`:$Path")
    $diskPath = Join-Path $Root $Path
    if (-not (Test-Path -LiteralPath $diskPath -PathType Leaf)) {
        throw "Changed Git blob is absent from the attached worktree: $Path"
    }
    $disk = [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($diskPath))
    $blobSha256 = Get-ByteSha256 -Bytes $blob
    if ($disk.Length -ne $blob.Length -or
        -not (Test-OrdinalEqual -Left (Get-ByteSha256 -Bytes $disk) -Right $blobSha256)) {
        throw "Worktree bytes do not match the attached raw Git blob: $Path"
    }
    return [ordered]@{
        path = $Path
        role = $Role
        blobId = $blobId
        bytes = [int64]$blob.Length
        sha256 = $blobSha256
    }
}

function Read-TestResult {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $Suite,
        [Parameter(Mandatory = $true)][string] $SummaryPattern,
        [Parameter(Mandatory = $true)][int] $Minimum,
        [switch] $RequireExactMinimum
    )

    $text = [IO.File]::ReadAllText([IO.Path]::GetFullPath($Path), $script:StrictUtf8)
    $lines = @([regex]::Split($text.TrimEnd(), '\r?\n'))
    $passLines = @($lines | Where-Object { $_.StartsWith('PASS ', [StringComparison]::Ordinal) })
    $summary = @($lines | Where-Object { $_ -match $SummaryPattern })
    if ($summary.Count -ne 1) {
        throw "$Suite test log does not have one canonical summary."
    }
    $reported = [int]([regex]::Match($summary[0], $SummaryPattern).Groups['count'].Value)
    if ($passLines.Count -ne $reported -or $reported -lt $Minimum -or
        ($RequireExactMinimum -and $reported -ne $Minimum)) {
        throw "$Suite test log is incomplete: passed=$($passLines.Count), reported=$reported."
    }
    if (@($lines | Where-Object { $_ -match '^(?:FAIL|ERROR)\b' }).Count -ne 0) {
        throw "$Suite test log contains a failure marker."
    }
    $record = Get-FileRecord -Path $Path
    return [ordered]@{
        status = 'passed'
        passed = $reported
        total = $reported
        log = $record
    }
}

function Get-PrivatePathMatches {
    param(
        [Parameter(Mandatory = $true)][object[]] $SourceBlobs,
        [Parameter(Mandatory = $true)][string] $CommitMessage
    )

    $pattern =
        '(?i)(?:[A-Z]:\\Users\\[A-Z0-9._-]+(?:\\[^\s"''`]+)*|/(?:home|Users)/[A-Z0-9._-]+(?:/[^\s"''`]+)*)'
    $matches = [Collections.Generic.List[object]]::new()
    foreach ($source in $SourceBlobs) {
        $bytes = Invoke-GitRaw -Arguments @('cat-file', 'blob', $source.blobId)
        $text = $script:StrictUtf8.GetString($bytes)
        $lineNumber = 0
        foreach ($line in [regex]::Split($text, '\r?\n')) {
            $lineNumber++
            foreach ($match in [regex]::Matches($line, $pattern)) {
                $matches.Add([ordered]@{
                        path = $source.path
                        line = $lineNumber
                        value = $match.Value
                    })
            }
        }
    }
    $lineNumber = 0
    foreach ($line in [regex]::Split($CommitMessage, '\r?\n')) {
        $lineNumber++
        foreach ($match in [regex]::Matches($line, $pattern)) {
            $matches.Add([ordered]@{
                    path = '<commit-message>'
                    line = $lineNumber
                    value = $match.Value
                })
        }
    }
    return @($matches)
}

if (Test-OrdinalEqual -Left $PSCmdlet.ParameterSetName -Right 'Seal') {
    $seal = Get-SharedRootSeal -RootPath $SharedRootPath
    Write-CanonicalJson -Value $seal -Path $SealOutputPath
    return
}

$authoritativeRepositoryId = '1333319462'
$authoritativeRepositoryNodeId = 'R_kgDOT3jXJg'
$authoritativeRepositoryName = 'crutkas/msys2-woarm64-build'
$workflowPath = '.github/workflows/preview-harness.yml'
$schemaPath = 'preview/schemas/admission-evidence.schema.json'
$collectorPath = 'preview/scripts/Collect-Arm64EtwEvidence.ps1'
$expectedSignedOffBy = 'Signed-off-by: Clint Rutkas <clint.rutkas@gmail.com>'
$expectedCoAuthor = 'Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>'
$expectedSession = "Copilot-Session: $ExpectedSessionId"
$expectedActionPins = @(
    [ordered]@{
        repository = 'actions/checkout'
        tag = 'v4.3.0'
        tagRef = 'refs/tags/v4.3.0'
        commit = '08eba0b27e820071cde6df949e0beb9ba4906955'
        tree = '1a393f9431c907405e5daacefe7884ab7131a657'
        verified = $true
    },
    [ordered]@{
        repository = 'actions/upload-artifact'
        tag = 'v4.6.2'
        tagRef = 'refs/tags/v4.6.2'
        commit = 'ea165f8d65b6e75b540449e92b4886f43607fa02'
        tree = '90fba5b2fb462e7dd5b3b810757b73327d2d66bc'
        verified = $true
    }
)

foreach ($value in @($ExpectedHead, $BaseCommit, $GitHubSha)) {
    if ($value -notmatch '^[0-9a-f]{40}$') {
        throw "Commit identity is not a lowercase full Git object ID: $value"
    }
}
if ($RunId -notmatch '^[0-9]+$' -or $RunAttempt -lt 1) {
    throw "GitHub run identity is invalid."
}
Assert-OrdinalEqual -Expected $authoritativeRepositoryId -Actual $RepositoryId `
    -Message 'Repository numeric ID is not authoritative.'
Assert-OrdinalEqual -Expected $authoritativeRepositoryNodeId -Actual $RepositoryNodeId `
    -Message 'Repository node ID is not authoritative.'
Assert-OrdinalEqual -Expected $authoritativeRepositoryName -Actual $RepositoryName `
    -Message 'Repository name is not authoritative.'
Assert-OrdinalEqual -Expected 'main' -Actual $BaseBranch `
    -Message 'Base branch is not authoritative.'

$expectedArtifactName = "arm64-admission-$EventName-$ExpectedHead-$RunId-$RunAttempt"
Assert-OrdinalEqual -Expected $expectedArtifactName -Actual $ArtifactName `
    -Message 'Artifact name is not exactly bound to event, head, run, and attempt.'

if (Test-OrdinalEqual -Left $EventName -Right 'pull_request') {
    foreach ($value in @(
            $PullRequestNumber,
            $PullRequestHead,
            $PullRequestBase,
            $PullRequestHeadRepositoryId,
            $PullRequestBaseRepositoryId
        )) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "Pull request event identity is incomplete."
        }
    }
    if ($PullRequestNumber -notmatch '^[1-9][0-9]*$') {
        throw "Pull request number is invalid."
    }
    Assert-OrdinalEqual -Expected $ExpectedHead -Actual $PullRequestHead `
        -Message 'Pull request event head is not attached HEAD.'
    Assert-OrdinalEqual -Expected $BaseCommit -Actual $PullRequestBase `
        -Message 'Pull request event base moved from the authoritative base.'
    Assert-OrdinalEqual -Expected $RepositoryId -Actual $PullRequestHeadRepositoryId `
        -Message 'Fork pull requests cannot produce admission evidence.'
    Assert-OrdinalEqual -Expected $RepositoryId -Actual $PullRequestBaseRepositoryId `
        -Message 'Pull request base repository is not authoritative.'
}
else {
    foreach ($value in @(
            $PullRequestNumber,
            $PullRequestHead,
            $PullRequestBase,
            $PullRequestHeadRepositoryId,
            $PullRequestBaseRepositoryId
        )) {
        if (-not [string]::IsNullOrEmpty($value)) {
            throw "Push evidence contains pull request identity."
        }
    }
}

$canonicalRoot = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
$canonicalOutput = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (-not (Test-Path -LiteralPath $canonicalRoot -PathType Container)) {
    throw "Repository root is absent: $canonicalRoot"
}
if (Test-Path -LiteralPath $canonicalOutput) {
    if (@(Get-ChildItem -LiteralPath $canonicalOutput -Force).Count -ne 0) {
        throw "Admission evidence output directory is not empty: $canonicalOutput"
    }
}
else {
    $null = New-Item -ItemType Directory -Path $canonicalOutput
}
$script:GitWorkingDirectory = $canonicalRoot

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $canonicalRoot

    $attachedHead = Invoke-GitText -Arguments @('rev-parse', 'HEAD')
    Assert-OrdinalEqual -Expected $ExpectedHead -Actual $attachedHead `
        -Message 'Attached HEAD does not match the admitted head.'
    $tree = Invoke-GitText -Arguments @('rev-parse', 'HEAD^{tree}')
    $parentsText = Invoke-GitText -Arguments @('show', '-s', '--format=%P', 'HEAD')
    $parents = @($parentsText -split ' ' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($parents.Count -ne 1) {
        throw "Admission evidence requires exactly one parent."
    }
    Assert-OrdinalEqual -Expected $BaseCommit -Actual $parents[0] `
        -Message 'Attached HEAD parent is not the authoritative base.'
    $mergeBase = Invoke-GitText -Arguments @('merge-base', $BaseCommit, $ExpectedHead)
    Assert-OrdinalEqual -Expected $BaseCommit -Actual $mergeBase `
        -Message 'Attached HEAD is not based on the authoritative base.'

    $originHeadRef = "refs/remotes/origin/$Branch"
    $originBaseRef = "refs/remotes/origin/$BaseBranch"
    $originHead = Invoke-GitText -Arguments @('show-ref', '--verify', '--hash', $originHeadRef)
    $originBase = Invoke-GitText -Arguments @('show-ref', '--verify', '--hash', $originBaseRef)
    Assert-OrdinalEqual -Expected $ExpectedHead -Actual $originHead `
        -Message 'Fetched origin branch ref does not match attached HEAD.'
    Assert-OrdinalEqual -Expected $BaseCommit -Actual $originBase `
        -Message 'Fetched origin base ref moved from the authoritative base.'

    $status = Invoke-GitText -Arguments @('status', '--porcelain=v1', '--untracked-files=all')
    if (-not [string]::IsNullOrEmpty($status)) {
        throw "Attached worktree is not clean:`n$status"
    }

    $nameStatus = Invoke-GitText -Arguments @(
        'diff', '--name-status', '--no-renames', "$BaseCommit..$ExpectedHead", '--')
    $numStat = Invoke-GitText -Arguments @(
        'diff', '--numstat', '--no-renames', "$BaseCommit..$ExpectedHead", '--')
    $statsByPath = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::Ordinal)
    foreach ($line in @($numStat -split "`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $parts = $line.TrimEnd("`r") -split "`t", 3
        if ($parts.Count -ne 3 -or $parts[0] -notmatch '^[0-9]+$' -or
            $parts[1] -notmatch '^[0-9]+$') {
            throw "Changed-file numstat is not canonical: $line"
        }
        if (-not $statsByPath.TryAdd($parts[2], [ordered]@{
                    additions = [int]$parts[0]
                    deletions = [int]$parts[1]
                })) {
            throw "Changed-file numstat contains a duplicate path: $($parts[2])"
        }
    }

    $statusesByPath = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::Ordinal)
    foreach ($line in @($nameStatus -split "`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $parts = $line.TrimEnd("`r") -split "`t", 2
        if ($parts.Count -ne 2 -or $parts[0] -notmatch '^[AM]$') {
            throw "Changed-file status is unsupported or noncanonical: $line"
        }
        if (-not $statusesByPath.TryAdd($parts[1], $parts[0])) {
            throw "Changed-file manifest contains a duplicate path: $($parts[1])"
        }
    }
    if ($statusesByPath.Count -eq 0 -or $statusesByPath.Count -ne $statsByPath.Count) {
        throw "Changed-file manifests are incomplete."
    }

    $sourceBlobs = [Collections.Generic.List[object]]::new()
    $changedFiles = [Collections.Generic.List[object]]::new()
    foreach ($path in Get-SortedOrdinal -Values @($statusesByPath.Keys)) {
        if (-not $statsByPath.ContainsKey($path)) {
            throw "Changed-file statistics are missing for: $path"
        }
        $role = if (Test-OrdinalEqual -Left $path -Right $collectorPath) {
            'collector'
        }
        else {
            'support'
        }
        $blob = Get-GitBlobRecord -Commit $ExpectedHead -Path $path -Root $canonicalRoot `
            -Role $role
        $sourceBlobs.Add($blob)
        $changedFiles.Add([ordered]@{
                path = $path
                status = $statusesByPath[$path]
                additions = $statsByPath[$path].additions
                deletions = $statsByPath[$path].deletions
                blobId = $blob.blobId
                bytes = $blob.bytes
                sha256 = $blob.sha256
            })
    }
    if (@($sourceBlobs | Where-Object {
                Test-OrdinalEqual -Left $_.role -Right 'collector'
            }).Count -ne 1) {
        throw "Raw source manifest must bind exactly one authoritative collector."
    }

    $workflowBlob = @($sourceBlobs | Where-Object {
            Test-OrdinalEqual -Left $_.path -Right $workflowPath
        })
    if ($workflowBlob.Count -ne 1) {
        throw "Changed source does not contain exactly one workflow blob."
    }
    $workflowText = $script:StrictUtf8.GetString(
        (Invoke-GitRaw -Arguments @('cat-file', 'blob', $workflowBlob[0].blobId)))
    $usesMatches = @([regex]::Matches(
            $workflowText,
            '(?m)^[ \t]*(?:-[ \t]+)?uses:[ \t]+(?<uses>[^ \t\r\n#]+)(?:[ \t]+#.*)?$'
        ))
    if ($usesMatches.Count -ne $expectedActionPins.Count) {
        throw "Workflow uses entries do not exactly match the independently resolved pin set."
    }
    $seenActions = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($match in $usesMatches) {
        $uses = $match.Groups['uses'].Value
        if ($uses -notmatch '^(?<repository>[^@]+)@(?<commit>[0-9a-f]{40})$') {
            throw "Workflow action is not pinned to a lowercase full commit: $uses"
        }
        $expected = @($expectedActionPins | Where-Object {
                Test-OrdinalEqual -Left $_.repository -Right $Matches['repository']
            })
        if ($expected.Count -ne 1 -or
            -not (Test-OrdinalEqual -Left $expected[0].commit -Right $Matches['commit']) -or
            -not $seenActions.Add($uses)) {
            throw "Workflow action pin is unexpected or duplicated: $uses"
        }
    }
    if ($seenActions.Count -ne $expectedActionPins.Count) {
        throw "Workflow action pin set is incomplete."
    }

    $commitMessage = Invoke-GitText -Arguments @('show', '-s', '--format=%B', 'HEAD')
    $messageLines = @([regex]::Split($commitMessage.TrimEnd(), '\r?\n'))
    if ($messageLines.Count -lt 3) {
        throw "Commit message does not contain terminal trailers."
    }
    $expectedTrailerLines = @($expectedSignedOffBy, $expectedCoAuthor, $expectedSession)
    for ($index = 0; $index -lt $expectedTrailerLines.Count; $index++) {
        $actualIndex = $messageLines.Count - $expectedTrailerLines.Count + $index
        Assert-OrdinalEqual -Expected $expectedTrailerLines[$index] `
            -Actual $messageLines[$actualIndex] `
            -Message 'Commit trailers are not terminal, contiguous, and canonical.'
    }
    $parsedTrailerText = Invoke-GitText -Arguments @('show', '-s', '--format=%B', 'HEAD')
    $parsedTrailerBytes = $script:Utf8NoBom.GetBytes($parsedTrailerText + "`n")
    $parseStart = [Diagnostics.ProcessStartInfo]::new()
    $gitCommand = @(
        Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue
    )[0]
    if ($null -eq $gitCommand) {
        $gitCommand = @(Get-Command git -CommandType Application -ErrorAction Stop)[0]
    }
    $parseStart.FileName = $gitCommand.Source
    $parseStart.UseShellExecute = $false
    $parseStart.RedirectStandardInput = $true
    $parseStart.RedirectStandardOutput = $true
    $parseStart.RedirectStandardError = $true
    $parseStart.ArgumentList.Add('interpret-trailers')
    $parseStart.ArgumentList.Add('--parse')
    $parseProcess = [Diagnostics.Process]::new()
    $parseProcess.StartInfo = $parseStart
    try {
        if (-not $parseProcess.Start()) {
            throw "Could not start git interpret-trailers."
        }
        $parseProcess.StandardInput.Write($script:StrictUtf8.GetString($parsedTrailerBytes))
        $parseProcess.StandardInput.Close()
        $parsedTrailers = $parseProcess.StandardOutput.ReadToEnd().TrimEnd([char[]]"`r`n")
        $parseError = $parseProcess.StandardError.ReadToEnd()
        $parseProcess.WaitForExit()
        if ($parseProcess.ExitCode -ne 0) {
            throw "git interpret-trailers failed: $parseError"
        }
    }
    finally {
        $parseProcess.Dispose()
    }
    $parsedTrailerLines = @([regex]::Split($parsedTrailers, '\r?\n'))
    if ($parsedTrailerLines.Count -ne 3) {
        throw "Commit has an unexpected parsed trailer count."
    }
    for ($index = 0; $index -lt $expectedTrailerLines.Count; $index++) {
        Assert-OrdinalEqual -Expected $expectedTrailerLines[$index] `
            -Actual $parsedTrailerLines[$index] `
            -Message 'Parsed commit trailer is not canonical.'
    }

    $privateMatches = @(Get-PrivatePathMatches -SourceBlobs @($sourceBlobs) `
            -CommitMessage $commitMessage)
    if ($privateMatches.Count -ne 0) {
        throw "Private machine paths were found in committed source: $($privateMatches | ConvertTo-Json -Compress)"
    }

    $beforeText = [IO.File]::ReadAllText(
        [IO.Path]::GetFullPath($SharedRootBeforePath), $script:StrictUtf8)
    $afterText = [IO.File]::ReadAllText(
        [IO.Path]::GetFullPath($SharedRootAfterPath), $script:StrictUtf8)
    $beforeSeal = $beforeText | ConvertFrom-Json
    $afterSeal = $afterText | ConvertFrom-Json
    Assert-OrdinalEqual -Expected ([IO.Path]::GetFullPath($SharedRootPath).TrimEnd('\')) `
        -Actual ([string]$beforeSeal.rootPath) -Message 'Before seal has the wrong shared root.'
    Assert-OrdinalEqual -Expected ([string]$beforeSeal.rootPath) `
        -Actual ([string]$afterSeal.rootPath) -Message 'Shared-root seal paths differ.'
    Assert-OrdinalEqual -Expected (Get-ByteSha256 -Bytes $script:StrictUtf8.GetBytes($beforeText)) `
        -Actual (Get-ByteSha256 -Bytes $script:StrictUtf8.GetBytes($afterText)) `
        -Message 'Shared C:\msys64 changed during the admission run.'

    $assemblerResult = Read-TestResult -Path $AssemblerLogPath -Suite 'assembler' `
        -SummaryPattern '^(?<count>[0-9]+) targeted preview tests passed\.$' `
        -Minimum 26 -RequireExactMinimum
    $etwResult = Read-TestResult -Path $EtwLogPath -Suite 'ETW' `
        -SummaryPattern '^PASS: (?<count>[0-9]+) ETW collector tests$' -Minimum 14

    $pullRequest = if (Test-OrdinalEqual -Left $EventName -Right 'pull_request') {
        [ordered]@{
            number = [int64]$PullRequestNumber
            headSha = $PullRequestHead
            baseSha = $PullRequestBase
            headRepositoryId = $PullRequestHeadRepositoryId
            baseRepositoryId = $PullRequestBaseRepositoryId
        }
    }
    else {
        $null
    }

    $artifactExpectedFiles = @(
        'SHA256SUMS',
        'admission-evidence.schema.json',
        'admission-evidence.v1.json',
        'assembler-tests.log',
        'content-manifest.json',
        'etw-tests.log',
        'shared-root-after.json',
        'shared-root-before.json'
    )
    $evidence = [ordered]@{
        schemaVersion = 1
        repository = [ordered]@{
            id = $RepositoryId
            nodeId = $RepositoryNodeId
            name = $RepositoryName
            defaultBranch = $BaseBranch
        }
        run = [ordered]@{
            id = $RunId
            attempt = $RunAttempt
            workflowRef = $WorkflowRef
            producerJob = 'admission-evidence'
            artifactName = $ArtifactName
        }
        event = [ordered]@{
            name = $EventName
            ref = $EventRef
            branch = $Branch
            githubSha = $GitHubSha
            pullRequest = $pullRequest
        }
        git = [ordered]@{
            base = $BaseCommit
            head = $ExpectedHead
            attachedHead = $attachedHead
            tree = $tree
            parents = @($parents)
            originHead = [ordered]@{ ref = $originHeadRef; sha = $originHead }
            originBase = [ordered]@{ ref = $originBaseRef; sha = $originBase }
            clean = $true
        }
        workflow = [ordered]@{
            path = $workflowPath
            blobId = $workflowBlob[0].blobId
            bytes = $workflowBlob[0].bytes
            sha256 = $workflowBlob[0].sha256
            actionPins = @($expectedActionPins)
        }
        tests = [ordered]@{
            assembler = $assemblerResult
            etw = $etwResult
        }
        changedFiles = @($changedFiles)
        sourceBlobs = @($sourceBlobs)
        commitTrailers = [ordered]@{
            terminal = $true
            contiguous = $true
            values = @(
                [ordered]@{
                    key = 'Signed-off-by'
                    value = 'Clint Rutkas <clint.rutkas@gmail.com>'
                },
                [ordered]@{
                    key = 'Co-authored-by'
                    value = 'Copilot App <223556219+Copilot@users.noreply.github.com>'
                },
                [ordered]@{
                    key = 'Copilot-Session'
                    value = $ExpectedSessionId
                }
            )
        }
        privatePathScan = [ordered]@{
            scope = 'changed-git-blobs-and-commit-message'
            scannedSourceBlobs = $sourceBlobs.Count
            clean = $true
            matches = @()
        }
        sharedRoot = [ordered]@{
            path = [IO.Path]::GetFullPath($SharedRootPath).TrimEnd('\')
            unchanged = $true
            before = $beforeSeal
            after = $afterSeal
            beforeFile = Get-FileRecord -Path $SharedRootBeforePath
            afterFile = Get-FileRecord -Path $SharedRootAfterPath
        }
        artifact = [ordered]@{
            expectedFiles = $artifactExpectedFiles
            contentManifestIncludes = @(
                'admission-evidence.schema.json',
                'admission-evidence.v1.json',
                'assembler-tests.log',
                'etw-tests.log',
                'shared-root-after.json',
                'shared-root-before.json'
            )
            sha256SumsIncludes = @(
                'admission-evidence.schema.json',
                'admission-evidence.v1.json',
                'assembler-tests.log',
                'content-manifest.json',
                'etw-tests.log',
                'shared-root-after.json',
                'shared-root-before.json'
            )
        }
    }

    [IO.File]::Copy(
        [IO.Path]::GetFullPath($AssemblerLogPath),
        (Join-Path $canonicalOutput 'assembler-tests.log')
    )
    [IO.File]::Copy(
        [IO.Path]::GetFullPath($EtwLogPath),
        (Join-Path $canonicalOutput 'etw-tests.log')
    )
    [IO.File]::Copy(
        [IO.Path]::GetFullPath($SharedRootBeforePath),
        (Join-Path $canonicalOutput 'shared-root-before.json')
    )
    [IO.File]::Copy(
        [IO.Path]::GetFullPath($SharedRootAfterPath),
        (Join-Path $canonicalOutput 'shared-root-after.json')
    )
    $schemaBytes = Invoke-GitRaw -Arguments @('cat-file', 'blob', "$ExpectedHead`:$schemaPath")
    [IO.File]::WriteAllBytes(
        (Join-Path $canonicalOutput 'admission-evidence.schema.json'), $schemaBytes)
    Write-CanonicalJson -Value $evidence `
        -Path (Join-Path $canonicalOutput 'admission-evidence.v1.json')

    $evidenceJson = Get-Content -LiteralPath (
        Join-Path $canonicalOutput 'admission-evidence.v1.json') -Raw -Encoding utf8
    if (-not ($evidenceJson | Test-Json -SchemaFile (
                Join-Path $canonicalOutput 'admission-evidence.schema.json'))) {
        throw "Admission evidence does not satisfy its closed schema."
    }

    $manifestNames = @($evidence.artifact.contentManifestIncludes)
    $manifestEntries = @($manifestNames | ForEach-Object {
            $record = Get-FileRecord -Path (Join-Path $canonicalOutput $_)
            [ordered]@{ path = $_; bytes = $record.bytes; sha256 = $record.sha256 }
        })
    Write-CanonicalJson -Value ([ordered]@{
            schemaVersion = 1
            files = $manifestEntries
        }) -Path (Join-Path $canonicalOutput 'content-manifest.json')

    $sumNames = @($evidence.artifact.sha256SumsIncludes)
    $sumLines = @($sumNames | ForEach-Object {
            $record = Get-FileRecord -Path (Join-Path $canonicalOutput $_)
            "$($record.sha256)  $_"
        })
    [IO.File]::WriteAllText(
        (Join-Path $canonicalOutput 'SHA256SUMS'),
        ($sumLines -join "`n") + "`n",
        $script:Utf8NoBom
    )

    $actualFiles = Get-SortedOrdinal -Values @(
        Get-ChildItem -LiteralPath $canonicalOutput -File -Force |
            ForEach-Object Name
    )
    $expectedFiles = Get-SortedOrdinal -Values $artifactExpectedFiles
    if ($actualFiles.Count -ne $expectedFiles.Count) {
        throw "Admission artifact has an unexpected file count."
    }
    for ($index = 0; $index -lt $expectedFiles.Count; $index++) {
        Assert-OrdinalEqual -Expected $expectedFiles[$index] -Actual $actualFiles[$index] `
            -Message 'Admission artifact file set is not closed.'
    }
}
finally {
    Set-Location -LiteralPath $previousLocation
}
