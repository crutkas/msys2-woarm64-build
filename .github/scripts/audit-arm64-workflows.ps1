[CmdletBinding()]
param(
    [string]$CandidateRoot = $env:ARM64_CANDIDATE_ROOT,
    [string]$PolicyPath = (Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'),
    [ValidateSet('Auto', 'PowerShellYaml', 'RubyPsych', 'Unavailable')]
    [string]$ParserBackend = 'Auto',
    [switch]$FixtureMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'git-object-integrity.ps1')

function Get-Arm64MapProperty {
    param(
        [AllowNull()][object]$Map,
        [Parameter(Mandatory)][string]$Name
    )

    if ($null -eq $Map) {
        return $null
    }
    if ($Map -is [Collections.IDictionary]) {
        if ($Map.Contains($Name)) {
            return [pscustomobject]@{ Name = $Name; Value = $Map[$Name] }
        }
        return $null
    }
    return $Map.PSObject.Properties[$Name]
}

function Get-Arm64ExactMapProperty {
    param(
        [AllowNull()][object]$Map,
        [Parameter(Mandatory)][string]$Name
    )

    if ($null -eq $Map) {
        return $null
    }
    if ($Map -is [Collections.IDictionary]) {
        foreach ($key in $Map.Keys) {
            if ([string]$key -ceq $Name) {
                return [pscustomobject]@{ Name = [string]$key; Value = $Map[$key] }
            }
        }
        return $null
    }
    foreach ($property in $Map.PSObject.Properties) {
        if ($property.Name -ceq $Name) {
            return $property
        }
    }
    return $null
}

function Get-Arm64MapNames {
    param([AllowNull()][object]$Map)

    if ($null -eq $Map) {
        return @()
    }
    if ($Map -is [Collections.IDictionary]) {
        return @($Map.Keys | ForEach-Object { [string]$_ })
    }
    return @($Map.PSObject.Properties | ForEach-Object { $_.Name })
}

function Get-Arm64ApprovedYamlBackends {
    $backends = [Collections.Generic.List[string]]::new()
    $powershellYaml = Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue
    if ($null -ne $powershellYaml -and
        $null -ne $powershellYaml.Module -and
        $powershellYaml.Module.Version.ToString() -ceq '0.4.12') {
        [void]$backends.Add('PowerShellYaml')
    }

    $ruby = Get-Command ruby -ErrorAction SilentlyContinue
    if ($null -ne $ruby) {
        $versions = & ruby -r json -r psych -e `
            'STDOUT.write(JSON.generate({"ruby"=>RUBY_VERSION,"psych"=>Psych::VERSION}))'
        if ($LASTEXITCODE -eq 0) {
            try {
                $parsedVersions = $versions | ConvertFrom-Json
                if ($parsedVersions.ruby -ceq '3.2.3' -and
                    $parsedVersions.psych -ceq '5.1.2') {
                    [void]$backends.Add('RubyPsych')
                }
            }
            catch {
                throw 'semantic-parser-version-output-invalid'
            }
        }
    }
    return @($backends)
}

function Resolve-Arm64YamlBackend {
    param([Parameter(Mandatory)][string]$Requested)

    if ($Requested -ceq 'Unavailable') {
        throw 'semantic-parser-unavailable'
    }
    $approved = @(Get-Arm64ApprovedYamlBackends)
    if ($Requested -ceq 'PowerShellYaml') {
        $command = Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            throw 'semantic-parser-unavailable'
        }
        if ($command.Module.Version.ToString() -cne '0.4.12') {
            throw 'semantic-parser-version-unapproved:PowerShellYaml'
        }
    }
    if ($Requested -ceq 'RubyPsych' -and
        $null -ne (Get-Command ruby -ErrorAction SilentlyContinue) -and
        $approved -cnotcontains 'RubyPsych') {
        throw 'semantic-parser-version-unapproved:RubyPsych'
    }
    foreach ($candidate in @(
            if ($Requested -ceq 'Auto') {
                'PowerShellYaml'
                'RubyPsych'
            }
            else {
                $Requested
            })) {
        if ($approved -ccontains $candidate) {
            return $candidate
        }
    }
    throw 'semantic-parser-unavailable'
}

# Deliberate, policy-defined YAML rejection codes. Only these constants may be surfaced to
# an audit caller, so candidate-controlled backend text can never reach the error stream.
$script:arm64DeliberateYamlCodes = @(
    'semantic-yaml-byte-limit-exceeded',
    'semantic-yaml-bom-forbidden',
    'semantic-yaml-utf8-invalid',
    'semantic-yaml-nul-forbidden',
    'semantic-yaml-explicit-document-marker-forbidden',
    'semantic-yaml-anchor-alias-merge-forbidden',
    'semantic-yaml-backend-parse-failed',
    'semantic-parser-differential',
    'semantic-parser-helper-missing',
    'semantic-parser-unavailable',
    'semantic-parser-version-unapproved',
    'semantic-parser-version-output-invalid',
    'semantic-parser-input-limit-exceeded',
    'semantic-parser-output-limit-exceeded',
    'semantic-parser-timeout'
)

function Resolve-Arm64YamlErrorCode {
    param(
        [AllowNull()][object]$ErrorRecord,
        [Parameter(Mandatory)][string]$Relative
    )

    $message = ''
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $message = [string]$ErrorRecord.Exception.Message
    }
    $separator = $message.IndexOf(':', [StringComparison]::Ordinal)
    $code = if ($separator -lt 0) { $message } else { $message.Substring(0, $separator) }
    if ($script:arm64DeliberateYamlCodes -ccontains $code) {
        return "${code}:$Relative"
    }
    return "semantic-yaml-parse-failed:$Relative"
}

function ConvertTo-Arm64YamlLineFeeds {
    param([Parameter(Mandatory)][string]$Text)

    # Every line break form a YAML parser may honour is folded to LF before any line-anchored
    # policy check, so a CR, NEL, LS, or PS separator cannot hide a document marker or a node
    # property from a check that only understands LF. The parsed text itself is unchanged.
    return $Text.
        Replace("`r`n", "`n").
        Replace("`r", "`n").
        Replace([string][char]0x85, "`n").
        Replace([string][char]0x2028, "`n").
        Replace([string][char]0x2029, "`n")
}

function Get-Arm64YamlQuotedScalarEnd {
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Line,
        [Parameter(Mandatory)][int]$Start,
        [Parameter(Mandatory)][char]$Quote
    )

    # $Start is the first index of scalar content, after the opening quote when present.
    $index = $Start
    while ($index -lt $Line.Length) {
        $character = $Line[$index]
        if ($Quote -ceq '"' -and $character -ceq '\') {
            $index += 2
            continue
        }
        if ($character -ceq $Quote) {
            if ($Quote -ceq "'" -and $index + 1 -lt $Line.Length -and
                $Line[$index + 1] -ceq "'") {
                $index += 2
                continue
            }
            return [pscustomobject]@{ End = $index + 1; Closed = $true }
        }
        $index++
    }
    return [pscustomobject]@{ End = $Line.Length; Closed = $false }
}

function Assert-Arm64YamlNodeProperties {
    param([Parameter(Mandatory)][string]$Text)

    # A single left-to-right scan that tracks whether a plain scalar is currently open. An
    # anchor, alias, tag, quote, or block scalar header is an indicator only at a genuine node
    # position; once a plain scalar is open, `&`, `*`, `'`, `"`, `,`, `[`, `{`, `-`, `?`, `|`,
    # and `>` are ordinary content. Deciding this from scalar state rather than from the single
    # preceding character is what keeps ordinary shell text such as `echo a, "b" && ls` or
    # `cp *.txt out/` admissible while still catching every real node property.
    $lines = (ConvertTo-Arm64YamlLineFeeds -Text $Text).Split("`n")
    $blockIndent = -1
    $atNodeStart = $true
    $flowDepth = 0
    $openQuote = [char]0
    # Indentation of the block node whose plain scalar is still open at end of line, or -1.
    $plainIndent = -1
    $nodeColumn = 0
    $tokenColumn = 0
    $keyPending = $true
    foreach ($line in $lines) {
        $indent = 0
        while ($indent -lt $line.Length -and
            ($line[$indent] -ceq ' ' -or $line[$indent] -ceq "`t")) {
            $indent++
        }
        if ($blockIndent -ge 0) {
            if ($indent -ge $line.Length -or $indent -gt $blockIndent) {
                continue
            }
            $blockIndent = -1
            $atNodeStart = $true
            $flowDepth = 0
            $openQuote = [char]0
            $plainIndent = -1
        }

        $index = $indent
        if ($openQuote -cne [char]0) {
            # A quoted scalar left open on the previous line continues here as content.
            $resumed = Get-Arm64YamlQuotedScalarEnd -Line $line -Start 0 -Quote $openQuote
            if (-not $resumed.Closed) {
                continue
            }
            $openQuote = [char]0
            $index = $resumed.End
            $atNodeStart = $false
        }
        elseif ($plainIndent -ge 0 -and
            ($indent -ge $line.Length -or $indent -gt $plainIndent)) {
            # Continuation content of an open plain scalar: either a more indented line, or a
            # blank line that YAML folds into the scalar. Neither begins a node.
            continue
        }
        elseif ($flowDepth -eq 0) {
            # In block context every line begins a new node. Inside an open flow collection it
            # does not, so node position there stays governed by `,`, `[`, and `{`.
            $atNodeStart = $true
        }
        $plainIndent = -1
        $nodeColumn = $indent
        $tokenColumn = $indent
        $keyPending = $true

        while ($index -lt $line.Length) {
            $character = $line[$index]
            if ($character -ceq ' ' -or $character -ceq "`t") {
                $index++
                continue
            }
            if ($character -ceq '#' -and
                ($index -eq 0 -or $line[$index - 1] -ceq ' ' -or $line[$index - 1] -ceq "`t")) {
                break
            }
            $next = if ($index + 1 -lt $line.Length) { $line[$index + 1] } else { [char]0 }
            $separated = $next -ceq [char]0 -or $next -ceq ' ' -or $next -ceq "`t"
            if ($atNodeStart -and $keyPending) {
                # A plain scalar continues onto lines indented past its enclosing block
                # collection, which is the last `-`/`?` indicator column for a bare entry and
                # the key token's column once a `key:` arms a value.
                $tokenColumn = $index
            }

            if ($atNodeStart) {
                # An anchor or alias name is any run of printable characters that are neither
                # space nor a flow indicator, so `&.base`, `*&x`, and `&@0/x!` all count.
                if (($character -ceq '&' -or $character -ceq '*') -and
                    -not $separated -and ',[]{}'.IndexOf($next) -lt 0) {
                    throw 'semantic-yaml-anchor-alias-merge-forbidden'
                }
                # A merge key is only a merge key as a real key token, never inside a comment,
                # a quoted scalar, or a block scalar body.
                if ($character -ceq '<' -and $next -ceq '<' -and
                    $line.Substring($index) -cmatch '^<<[ \t]*:') {
                    throw 'semantic-yaml-anchor-alias-merge-forbidden'
                }
                if ($character -ceq '"' -or $character -ceq "'") {
                    $quoted = Get-Arm64YamlQuotedScalarEnd `
                        -Line $line `
                        -Start ($index + 1) `
                        -Quote $character
                    if (-not $quoted.Closed) {
                        $openQuote = $character
                        break
                    }
                    $index = $quoted.End
                    $atNodeStart = $false
                    continue
                }
                if ($character -ceq '!') {
                    while ($index -lt $line.Length -and
                        $line[$index] -cne ' ' -and $line[$index] -cne "`t") {
                        $index++
                    }
                    continue
                }
                if (($character -ceq '|' -or $character -ceq '>') -and
                    $line.Substring($index) -cmatch '^[|>][0-9+-]{0,2}[ \t]*(?:#.*)?$') {
                    $blockIndent = $indent
                    break
                }
                if (($character -ceq '-' -or $character -ceq '?') -and
                    ($separated -or ($character -ceq '?' -and $flowDepth -gt 0))) {
                    # A bare entry's plain scalar is enclosed by this indicator's column, so
                    # the indicator column stays the continuation threshold until a `key:`
                    # promotes the key token's column instead.
                    $nodeColumn = $index
                    $index++
                    continue
                }
                if ($character -ceq '[' -or $character -ceq '{') {
                    $flowDepth++
                    $index++
                    continue
                }
            }

            if ($character -ceq ']' -or $character -ceq '}') {
                if ($flowDepth -gt 0) {
                    $flowDepth--
                }
                $atNodeStart = $false
                $index++
                continue
            }
            if ($character -ceq ',' -and $flowDepth -gt 0) {
                $atNodeStart = $true
                $index++
                continue
            }
            if ($character -ceq ':') {
                # In flow context `:` needs no separation only after a JSON-like key, that is
                # one ending in a quote or a closed flow collection. After a plain key, `a:"b`
                # is still one plain scalar.
                $jsonLikeKey = $false
                if ($flowDepth -gt 0) {
                    $scan = $index - 1
                    while ($scan -ge 0 -and
                        ($line[$scan] -ceq ' ' -or $line[$scan] -ceq "`t")) {
                        $scan--
                    }
                    if ($scan -ge 0) {
                        $jsonLikeKey = '"'']}'.IndexOf($line[$scan]) -ge 0
                    }
                }
                if ($separated -or $jsonLikeKey) {
                    $atNodeStart = $true
                    if ($keyPending) {
                        $nodeColumn = $tokenColumn
                        $keyPending = $false
                    }
                    $index++
                    continue
                }
                # After a plain flow key `a:&x` is one scalar to the pinned backend, so this is
                # not a node start for quoting purposes. A node property here is still refused
                # so that a backend which disagrees cannot admit an anchor or alias.
                if ($flowDepth -gt 0 -and ($next -ceq '&' -or $next -ceq '*')) {
                    $after = if ($index + 2 -lt $line.Length) { $line[$index + 2] } else { [char]0 }
                    if ($after -cne [char]0 -and $after -cne ' ' -and $after -cne "`t" -and
                        ',[]{}'.IndexOf($after) -lt 0) {
                        throw 'semantic-yaml-anchor-alias-merge-forbidden'
                    }
                }
            }
            $atNodeStart = $false
            $index++
        }

        # A plain scalar still open at end of line may continue onto following lines that are
        # indented past this node's key column.
        if ($blockIndent -lt 0 -and $openQuote -ceq [char]0 -and $flowDepth -eq 0 -and
            -not $atNodeStart) {
            $plainIndent = $nodeColumn
        }
    }
}

function Assert-Arm64YamlLexicalPolicy {
    param([Parameter(Mandatory)][string]$Text)

    # A document marker is `---` or `...` at a line start after optional indentation that is
    # followed by separation or the end of the line. That covers inline-content documents such
    # as `--- {a: b}` and second documents, while `---not-a-marker` stays an ordinary scalar.
    $lineFolded = ConvertTo-Arm64YamlLineFeeds -Text $Text
    if ($lineFolded -cmatch '(?m)^[ \t]*(?:---|\.\.\.)(?=[ \t\n]|$)') {
        throw 'semantic-yaml-explicit-document-marker-forbidden'
    }
    Assert-Arm64YamlNodeProperties -Text $Text
}

function Get-Arm64YamlText {
    param([Parameter(Mandatory)][string]$Path)

    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.LongLength -gt 1048576) {
        throw 'semantic-yaml-byte-limit-exceeded'
    }
    if (($bytes.Length -ge 2 -and
            (($bytes[0] -eq 0xff -and $bytes[1] -eq 0xfe) -or
                ($bytes[0] -eq 0xfe -and $bytes[1] -eq 0xff))) -or
        ($bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and
            $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf)) {
        throw 'semantic-yaml-bom-forbidden'
    }
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        throw 'semantic-yaml-utf8-invalid'
    }
    if ($text.Contains("`0", [StringComparison]::Ordinal)) {
        throw 'semantic-yaml-nul-forbidden'
    }
    Assert-Arm64YamlLexicalPolicy -Text $text
    return $text
}

function Read-Arm64BoundedStreamPair {
    param(
        [Parameter(Mandatory)][IO.Stream]$Primary,
        [Parameter(Mandatory)][IO.Stream]$Secondary,
        [Parameter(Mandatory)][int]$PrimaryLimit,
        [Parameter(Mandatory)][int]$SecondaryLimit,
        [Parameter(Mandatory)][Diagnostics.Stopwatch]$Timer,
        [Parameter(Mandatory)][int]$TimeoutMilliseconds
    )

    $streams = @($Primary, $Secondary)
    $limits = @($PrimaryLimit, $SecondaryLimit)
    $buffers = @([byte[]]::new(8192), [byte[]]::new(8192))
    $sinks = @([IO.MemoryStream]::new(), [IO.MemoryStream]::new())
    $tasks = [object[]]::new(2)
    try {
        for ($slot = 0; $slot -lt 2; $slot++) {
            $tasks[$slot] = $streams[$slot].ReadAsync($buffers[$slot], 0, $buffers[$slot].Length)
        }
        while ($null -ne $tasks[0] -or $null -ne $tasks[1]) {
            $activeSlots = @(0, 1 | Where-Object { $null -ne $tasks[$_] })
            $activeTasks = [Threading.Tasks.Task[]]@($activeSlots | ForEach-Object { $tasks[$_] })
            $remaining = $TimeoutMilliseconds - [int]$Timer.ElapsedMilliseconds
            if ($remaining -le 0) {
                throw 'semantic-parser-timeout'
            }
            $completed = [Threading.Tasks.Task]::WaitAny($activeTasks, $remaining)
            if ($completed -lt 0) {
                throw 'semantic-parser-timeout'
            }
            $slot = $activeSlots[$completed]
            $read = $tasks[$slot].GetAwaiter().GetResult()
            if ($read -le 0) {
                $tasks[$slot] = $null
                continue
            }
            if ($sinks[$slot].Length + $read -gt $limits[$slot]) {
                throw 'semantic-parser-output-limit-exceeded'
            }
            $sinks[$slot].Write($buffers[$slot], 0, $read)
            $tasks[$slot] = $streams[$slot].ReadAsync($buffers[$slot], 0, $buffers[$slot].Length)
        }
        return [pscustomobject]@{
            Primary   = $sinks[0].ToArray()
            Secondary = $sinks[1].ToArray()
        }
    }
    finally {
        $sinks[0].Dispose()
        $sinks[1].Dispose()
    }
}

function Invoke-Arm64BoundedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory)][AllowEmptyCollection()][byte[]]$InputBytes,
        [int]$MaximumInputBytes = 1048576,
        [int]$MaximumOutputBytes = 4194304,
        [int]$MaximumErrorBytes = 65536,
        [int]$TimeoutMilliseconds = 60000
    )

    if ($InputBytes.LongLength -gt $MaximumInputBytes) {
        throw 'semantic-parser-input-limit-exceeded'
    }

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    foreach ($argument in $ArgumentList) {
        $startInfo.ArgumentList.Add($argument)
    }
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $timer = [Diagnostics.Stopwatch]::StartNew()
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $inputStream = $process.StandardInput.BaseStream
        $inputStream.Write($InputBytes, 0, $InputBytes.Length)
        $inputStream.Flush()
        $process.StandardInput.Close()

        $streams = Read-Arm64BoundedStreamPair `
            -Primary $process.StandardOutput.BaseStream `
            -Secondary $process.StandardError.BaseStream `
            -PrimaryLimit $MaximumOutputBytes `
            -SecondaryLimit $MaximumErrorBytes `
            -Timer $timer `
            -TimeoutMilliseconds $TimeoutMilliseconds

        $remaining = $TimeoutMilliseconds - [int]$timer.ElapsedMilliseconds
        if ($remaining -le 0 -or -not $process.WaitForExit($remaining)) {
            throw 'semantic-parser-timeout'
        }
        return [pscustomobject]@{
            ExitCode     = [int]$process.ExitCode
            OutputBytes  = $streams.Primary
            ErrorBytes   = $streams.Secondary
        }
    }
    finally {
        $timer.Stop()
        try {
            if (-not $process.HasExited) {
                $process.Kill($true)
            }
        }
        catch {
            Write-Verbose 'Bounded parser process could not be inspected or terminated.'
        }
        $process.Dispose()
    }
}

function Invoke-Arm64YamlBackend {
    param(
        [Parameter(Mandatory)][string]$Text,
        [Parameter(Mandatory)][string]$Backend
    )

    if ($Backend -ceq 'PowerShellYaml') {
        try {
            return $Text | ConvertFrom-Yaml
        }
        catch {
            throw 'semantic-yaml-backend-parse-failed'
        }
    }

    $parserPath = Join-Path $PSScriptRoot 'parse-yaml.rb'
    if (-not (Test-Path -LiteralPath $parserPath -PathType Leaf)) {
        throw 'semantic-parser-helper-missing'
    }
    $ruby = Get-Command ruby -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $ruby) {
        throw 'semantic-parser-unavailable'
    }

    # The helper parses the exact bytes that Get-Arm64YamlText already validated. The source
    # path is never reopened, so a post-validation mutation of the file cannot change what is
    # parsed.
    $result = Invoke-Arm64BoundedProcess `
        -FilePath $ruby.Source `
        -ArgumentList @($parserPath) `
        -InputBytes ([Text.UTF8Encoding]::new($false, $true).GetBytes($Text))
    if ($result.ExitCode -ne 0) {
        throw 'semantic-yaml-backend-parse-failed'
    }
    try {
        $json = [Text.UTF8Encoding]::new($false, $true).GetString($result.OutputBytes)
    }
    catch {
        throw 'semantic-yaml-backend-parse-failed'
    }
    try {
        return $json | ConvertFrom-Json -Depth 64
    }
    catch {
        throw 'semantic-yaml-backend-parse-failed'
    }
}

function ConvertFrom-Arm64YamlFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Backend
    )

    $text = Get-Arm64YamlText -Path $Path
    $document = Invoke-Arm64YamlBackend -Text $text -Backend $Backend
    $approved = @(Get-Arm64ApprovedYamlBackends)
    if ($approved.Count -gt 1) {
        $representations = @($approved | ForEach-Object {
                Invoke-Arm64YamlBackend -Text $text -Backend $_ |
                    ConvertTo-Json -Compress -Depth 64
            } | Sort-Object -Unique)
        if ($representations.Count -ne 1) {
            throw "semantic-parser-differential:$Path"
        }
    }
    return $document
}

function Get-Arm64GitBlobHash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-Arm64FileBlobIdentity -Path $Path).oid
}

function Get-Arm64Sha256Text {
    param([Parameter(Mandatory)][string]$Text)

    # Identity is the exact intended text. Only CRLF is folded to LF, so a checkout's
    # line-ending policy cannot change identity; no other normalization is applied and
    # leading or trailing whitespace is significant.
    $exact = $Text.Replace("`r`n", "`n")
    return -join (
        [Security.Cryptography.SHA256]::HashData(
            [Text.UTF8Encoding]::new($false, $true).GetBytes($exact)
        ) | ForEach-Object { $_.ToString('x2') }
    )
}

function Resolve-Arm64DataPath {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$RelativePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        $RelativePath -match '^(?:[A-Za-z]:|/|\\)' -or
        $RelativePath -match '(?:^|[\\/])\.\.(?:[\\/]|$)') {
        throw "local-path-invalid:$RelativePath"
    }
    $normalized = $RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar).
        Replace('\', [IO.Path]::DirectorySeparatorChar)
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolved = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
    if (-not $resolved.StartsWith(
            "$rootFull$([IO.Path]::DirectorySeparatorChar)",
            [StringComparison]::Ordinal)) {
        throw "local-path-escape:$RelativePath"
    }
    return $resolved
}

function Test-Arm64AuthoritativeSnapshot {
    param([Parameter(Mandatory)][string]$Root)

    $snapshotPath = Join-Path $Root 'authoritative-snapshot.json'
    if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
        throw 'authoritative-snapshot-missing'
    }
    $snapshot = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json -Depth 64
    $snapshotProperties = @($snapshot.PSObject.Properties.Name | Sort-Object)
    $expectedSnapshotProperties = @(
        'authority',
        'repository',
        'commit',
        'tree',
        'complete',
        'files'
    ) | Sort-Object
    if (($snapshotProperties -join "`0") -cne ($expectedSnapshotProperties -join "`0") -or
        $snapshot.authority -cne 'github-rest-api' -or
        $snapshot.complete -isnot [bool] -or -not $snapshot.complete -or
        $snapshot.repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or
        -not (Test-Arm64GitObjectId $snapshot.commit) -or
        -not (Test-Arm64GitObjectId $snapshot.tree) -or
        $snapshot.files -is [string] -or
        $snapshot.files -isnot [Collections.IEnumerable]) {
        throw 'authoritative-snapshot-invalid'
    }

    $expectedPaths = [Collections.Generic.List[string]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($file in @($snapshot.files)) {
        Assert-Arm64SourceBinding -Binding $file -Label 'authoritative snapshot file'
        if (-not $exactPaths.Add([string]$file.path)) {
            throw "authoritative-snapshot-duplicate-path:$($file.path)"
        }
        $aliasKey = ([string]$file.path).Normalize(
            [Text.NormalizationForm]::FormC
        ).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "authoritative-snapshot-path-alias:$($file.path)"
        }
        [void]$expectedPaths.Add([string]$file.path)
    }
    $expectedPaths = @($expectedPaths | Sort-Object)
    $actualPaths = @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force | Where-Object {
            $_.FullName -cne $snapshotPath
        } | ForEach-Object {
            $_.FullName.Substring([IO.Path]::GetFullPath($Root).Length + 1).
                Replace([IO.Path]::DirectorySeparatorChar, '/')
        } | Sort-Object)
    if (($expectedPaths -join "`0") -cne ($actualPaths -join "`0")) {
        throw 'authoritative-snapshot-file-set-mismatch'
    }
    foreach ($file in $snapshot.files) {
        $path = Resolve-Arm64DataPath -Root $Root -RelativePath $file.path
        $identity = Get-Arm64FileBlobIdentity -Path $path
        $actualBinding = New-Arm64SourceBinding `
            -Path $file.path `
            -Mode $file.mode `
            -ObjectType 'blob' `
            -ByteLength $identity.byte_length `
            -Oid $identity.oid
        if (-not (Test-Arm64SourceBindingEqual -Expected $file -Actual $actualBinding)) {
            throw "authoritative-snapshot-source-binding-mismatch:$($file.path)"
        }
    }
    return $snapshot
}

function Test-Arm64WorkflowTree {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][object]$Policy,
        [string]$TrustedPolicyPath,
        [ValidateSet('Auto', 'PowerShellYaml', 'RubyPsych', 'Unavailable')]
        [string]$Backend = 'Auto',
        [switch]$SkipAuthoritativeSnapshot
    )

    $errors = [Collections.Generic.List[string]]::new()
    $inventory = [Collections.Generic.List[object]]::new()
    $visitedWorkflows = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    $visitedScripts = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    $governanceCheckLocations = [Collections.Generic.List[string]]::new()
    function Add-AuditError {
        param([string]$Code)

        if (-not $errors.Contains($Code)) {
            [void]$errors.Add($Code)
        }
    }

    try {
        $resolvedBackend = Resolve-Arm64YamlBackend -Requested $Backend
    }
    catch {
        Add-AuditError $_.Exception.Message
        return [pscustomobject]@{
            Allowed = $false
            Errors = @($errors)
            Inventory = @()
            Parser = $null
        }
    }

    $publicationProperty = Get-Arm64MapProperty -Map $Policy -Name 'publication'
    if ($null -eq $publicationProperty -or
        $publicationProperty.Value.enabled -isnot [bool] -or
        $publicationProperty.Value.enabled -or
        $publicationProperty.Value.protected_environment_confirmed -isnot [bool] -or
        $publicationProperty.Value.protected_environment_confirmed -or
        $publicationProperty.Value.mode -cne 'unconditional-deny') {
        Add-AuditError 'publication-policy-must-remain-unconditionally-disabled'
    }
    $actionNames = @(Get-Arm64MapNames -Map $Policy.external_action_pins | Sort-Object)
    if (($actionNames -join "`0") -cne 'actions/checkout') {
        Add-AuditError 'active-action-allowlist-not-minimal'
    }

    $rootFull = [IO.Path]::GetFullPath($Root)
    $authoritativeSnapshot = $null
    if (-not $SkipAuthoritativeSnapshot) {
        try {
            $authoritativeSnapshot = Test-Arm64AuthoritativeSnapshot -Root $rootFull
        }
        catch {
            Add-AuditError $_.Exception.Message
        }
        $candidatePolicyPath = Join-Path $rootFull '.github\policies\arm64-quarantine-policy.json'
        if ([string]::IsNullOrWhiteSpace($TrustedPolicyPath) -or
            -not (Test-Path -LiteralPath $TrustedPolicyPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $candidatePolicyPath -PathType Leaf)) {
            Add-AuditError 'protected-policy-data-missing'
        }
        else {
            $trustedPolicy = Get-Arm64FileBlobIdentity -Path $TrustedPolicyPath
            $candidatePolicy = Get-Arm64FileBlobIdentity -Path $candidatePolicyPath
            if ($trustedPolicy.byte_length -ne $candidatePolicy.byte_length -or
                $trustedPolicy.oid -cne $candidatePolicy.oid) {
                Add-AuditError 'protected-policy-source-binding-mismatch'
            }
        }
    }

    $protectedVerifierProperty = Get-Arm64MapProperty `
        -Map $Policy `
        -Name 'protected_verifier'
    if ($null -ne $protectedVerifierProperty) {
        $protectedSourcesProperty = Get-Arm64MapProperty `
            -Map $protectedVerifierProperty.Value `
            -Name 'sources'
        if ($null -eq $protectedSourcesProperty) {
            Add-AuditError 'protected-source-allowlist-missing'
        }
        else {
            foreach ($protectedPath in Get-Arm64MapNames -Map $protectedSourcesProperty.Value) {
                try {
                    $resolvedProtectedPath = Resolve-Arm64DataPath `
                        -Root $rootFull `
                        -RelativePath $protectedPath
                    $expectedProtectedBinding = (
                        Get-Arm64MapProperty `
                            -Map $protectedSourcesProperty.Value `
                            -Name $protectedPath
                    ).Value
                    Assert-Arm64SourceBinding `
                        -Binding $expectedProtectedBinding `
                        -Label $protectedPath
                    $identity = Get-Arm64FileBlobIdentity -Path $resolvedProtectedPath
                    $actualProtectedBinding = New-Arm64SourceBinding `
                        -Path $protectedPath `
                        -Mode $expectedProtectedBinding.mode `
                        -ObjectType 'blob' `
                        -ByteLength $identity.byte_length `
                        -Oid $identity.oid
                    if (-not (Test-Arm64SourceBindingEqual `
                            -Expected $expectedProtectedBinding `
                            -Actual $actualProtectedBinding)) {
                        Add-AuditError "protected-source-binding-mismatch:$protectedPath"
                    }
                }
                catch {
                    Add-AuditError "protected-source-invalid:$protectedPath"
                }
            }
        }
        if (-not $SkipAuthoritativeSnapshot -and $null -ne $authoritativeSnapshot -and
            -not [string]::IsNullOrWhiteSpace($TrustedPolicyPath)) {
            try {
                $trustedRoot = [IO.Path]::GetFullPath((
                        Join-Path (Split-Path $TrustedPolicyPath -Parent) '..\..'
                    ))
                $trustedSources = @(Get-Arm64ProtectedGitSourceBindings `
                        -RepositoryRoot $trustedRoot)
                $candidateSources = @($authoritativeSnapshot.files | Where-Object {
                        $_.path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -or
                        $_.path.StartsWith('.github/scripts/', [StringComparison]::Ordinal) -or
                        $_.path.StartsWith('.github/policies/', [StringComparison]::Ordinal)
                    } | Sort-Object path)
                Assert-Arm64SourceBindingSetsEqual `
                    -Expected $trustedSources `
                    -Actual $candidateSources `
                    -Label 'protected-source'
            }
            catch {
                Add-AuditError $_.Exception.Message
            }
        }
    }

    function Get-RelativeDataPath {
        param([Parameter(Mandatory)][string]$Path)

        return [IO.Path]::GetFullPath($Path).Substring($rootFull.Length + 1).
            Replace([IO.Path]::DirectorySeparatorChar, '/')
    }

    function Test-ContainerImage {
        param(
            [AllowNull()][object]$Image,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Image -isnot [string] -or
            $Image -cnotmatch '^[^@\s]+@sha256:[0-9a-f]{64}$') {
            Add-AuditError "container-not-digest-pinned:$Location"
            return
        }
        $expected = Get-Arm64MapProperty -Map $Policy.allowed_container_images -Name $Image
        if ($null -eq $expected) {
            Add-AuditError "container-not-allowlisted:$Location"
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'container'
                Location = $Location
                Target = $Image
            })
    }

    function Test-DelegatedScript {
        param(
            [Parameter(Mandatory)][string]$ScriptPath,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        $relative = Get-RelativeDataPath -Path $ScriptPath
        if (-not $visitedScripts.Add($relative)) {
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'shell'
                Location = $Location
                Target = $relative
            })

        if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
            Add-AuditError "delegated-script-missing:$relative"
            return
        }
        if ([IO.Path]::GetExtension($ScriptPath) -cne '.ps1') {
            Add-AuditError "delegated-script-parser-unavailable:$relative"
            return
        }

        $allowedSourcesProperty = Get-Arm64MapProperty `
            -Map $WorkflowRule `
            -Name 'allowed_local_shell_sources'
        if ($null -eq $allowedSourcesProperty) {
            Add-AuditError "delegated-script-source-allowlist-missing:$relative"
            return
        }
        $expectedSource = Get-Arm64MapProperty `
            -Map $allowedSourcesProperty.Value `
            -Name $relative
        if ($null -eq $expectedSource) {
            Add-AuditError "delegated-script-source-not-allowlisted:$relative"
            return
        }
        try {
            Assert-Arm64SourceBinding -Binding $expectedSource.Value -Label $relative
            $identity = Get-Arm64FileBlobIdentity -Path $ScriptPath
            $actualSource = New-Arm64SourceBinding `
                -Path $relative `
                -Mode $expectedSource.Value.mode `
                -ObjectType 'blob' `
                -ByteLength $identity.byte_length `
                -Oid $identity.oid
            if (-not (Test-Arm64SourceBindingEqual `
                    -Expected $expectedSource.Value `
                    -Actual $actualSource)) {
                Add-AuditError "delegated-script-source-binding-mismatch:$relative"
                return
            }
        }
        catch {
            Add-AuditError "delegated-script-source-invalid:$relative"
            return
        }

        $tokens = $null
        $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile(
            $ScriptPath,
            [ref]$tokens,
            [ref]$parseErrors
        )
        if ($parseErrors.Count -ne 0) {
            Add-AuditError "delegated-script-syntax-invalid:$relative"
            return
        }

        $authorityProperty = Get-Arm64MapProperty -Map $WorkflowRule -Name 'authority'
        if ($null -eq $authorityProperty) {
            Add-AuditError "delegated-script-authority-missing:$relative"
            return
        }
        $authority = [string]$authorityProperty.Value
        if ($authority -ceq 'untrusted-diagnostic') {
            $forbiddenCommands = @(
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
                'gh',
                'git'
            )
            $commands = $ast.FindAll({
                    param($node)
                    return $node -is [Management.Automation.Language.CommandAst]
                }, $true)
            foreach ($command in $commands) {
                $commandName = $command.GetCommandName()
                if ($null -eq $commandName) {
                    Add-AuditError "diagnostic-dynamic-command:$relative"
                    continue
                }
                if ($forbiddenCommands -ccontains $commandName.ToLowerInvariant()) {
                    Add-AuditError "diagnostic-operation-forbidden:${relative}:$commandName"
                }
            }
            $urlFragments = $ast.FindAll({
                    param($node)
                    return ($node -is [Management.Automation.Language.StringConstantExpressionAst] -or
                        $node -is [Management.Automation.Language.ExpandableStringExpressionAst]) -and
                        $node.Value -match '(?i)(?:://|git@)'
                }, $true)
            if (@($urlFragments).Count -ne 0) {
                Add-AuditError "diagnostic-url-forbidden:$relative"
            }
        }
    }

    function Test-RunStep {
        param(
            [AllowNull()][object]$Run,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Run -isnot [string] -or [string]::IsNullOrWhiteSpace($Run)) {
            Add-AuditError "shell-run-invalid:$Location"
            return
        }
        $normalized = $Run.Replace("`r`n", "`n").Trim()
        $scriptMatch = [regex]::Match(
            $normalized,
            '^(?:&\s+)?(?:[''"])?(?<path>(?:\./|\.\\)[A-Za-z0-9_.\\/:-]+\.(?:ps1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb))(?:[''"])?$',
            [Text.RegularExpressions.RegexOptions]::CultureInvariant
        )
        $delegatedPrefix = [regex]::IsMatch(
            $normalized,
            '^(?:&\s+)?(?:[''"])?(?:\./|\.\\)[A-Za-z0-9_.\\/:-]+\.(?:ps1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb)',
            [Text.RegularExpressions.RegexOptions]::CultureInvariant
        )
        if ($scriptMatch.Success -and $normalized -notmatch "`n") {
            $relative = $scriptMatch.Groups['path'].Value.Substring(2).Replace('\', '/')
            $allowedProperty = Get-Arm64MapProperty `
                -Map $WorkflowRule `
                -Name 'allowed_local_shell_entrypoints'
            $allowed = if ($null -eq $allowedProperty) { @() } else { @($allowedProperty.Value) }
            if ($allowed -cnotcontains $relative) {
                Add-AuditError "shell-entrypoint-not-allowlisted:${Location}:$relative"
            }
            try {
                $resolved = Resolve-Arm64DataPath -Root $rootFull -RelativePath $relative
                Test-DelegatedScript `
                    -ScriptPath $resolved `
                    -WorkflowRule $WorkflowRule `
                    -Location $Location
            }
            catch {
                Add-AuditError $_.Exception.Message
            }
            return
        }
        if ($delegatedPrefix) {
            if ($normalized -match '[;|><`&\r\n]') {
                Add-AuditError "shell-command-chain-forbidden:$Location"
            }
            else {
                Add-AuditError "shell-arguments-forbidden:$Location"
            }
        }

        $inlineProperty = Get-Arm64MapProperty `
            -Map $WorkflowRule `
            -Name 'allowed_inline_shell_sha256'
        $allowedInline = if ($null -eq $inlineProperty) { @() } else { @($inlineProperty.Value) }
        $hash = Get-Arm64Sha256Text -Text $normalized
        if ($allowedInline -cnotcontains $hash) {
            Add-AuditError "inline-shell-not-allowlisted:$Location"
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'inline-shell'
                Location = $Location
                Target = $hash
            })
    }

    function Test-UsesReference {
        param(
            [AllowNull()][object]$Uses,
            [Parameter(Mandatory)][object]$Owner,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Uses -isnot [string] -or [string]::IsNullOrWhiteSpace($Uses) -or
            $Uses.Contains('${{', [StringComparison]::Ordinal)) {
            Add-AuditError "uses-reference-invalid:$Location"
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'uses'
                Location = $Location
                Target = $Uses
            })

        if ($Uses.StartsWith('docker://', [StringComparison]::Ordinal)) {
            Test-ContainerImage -Image $Uses.Substring(9) -Location $Location
            return
        }
        if ($Uses.StartsWith('./', [StringComparison]::Ordinal)) {
            $relative = $Uses.Substring(2).Replace('\', '/')
            try {
                $resolved = Resolve-Arm64DataPath -Root $rootFull -RelativePath $relative
            }
            catch {
                Add-AuditError $_.Exception.Message
                return
            }

            if ($relative -match '(?i)\.ya?ml$') {
                Test-WorkflowFile -WorkflowPath $resolved -InvokedFrom $Location
                return
            }

            Add-AuditError "local-action-not-allowlisted:${Location}:$relative"
            $descriptors = @(@(
                    Join-Path $resolved 'action.yml'
                    Join-Path $resolved 'action.yaml'
                ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
            if ($descriptors.Count -ne 1) {
                Add-AuditError "local-action-descriptor-invalid:${Location}:$relative"
                return
            }
            try {
                $action = ConvertFrom-Arm64YamlFile -Path $descriptors[0] -Backend $resolvedBackend
            }
            catch {
                Add-AuditError (Resolve-Arm64YamlErrorCode `
                        -ErrorRecord $_ `
                        -Relative $relative)
                return
            }
            $runsProperty = Get-Arm64MapProperty -Map $action -Name 'runs'
            $usingProperty = if ($null -eq $runsProperty) {
                $null
            }
            else {
                Get-Arm64MapProperty -Map $runsProperty.Value -Name 'using'
            }
            if ($null -eq $usingProperty) {
                Add-AuditError "local-action-runs-missing:${Location}:$relative"
                return
            }
            if ($usingProperty.Value -ceq 'composite') {
                $steps = (Get-Arm64MapProperty -Map $runsProperty.Value -Name 'steps').Value
                Test-Steps -Steps $steps -WorkflowRule $WorkflowRule -Location "${Location}:local-action"
            }
            elseif ($usingProperty.Value -ceq 'docker') {
                Add-AuditError "local-docker-action-forbidden:${Location}:$relative"
            }
            else {
                foreach ($entry in @('main', 'pre', 'post')) {
                    $pathProperty = Get-Arm64MapProperty -Map $runsProperty.Value -Name $entry
                    if ($null -ne $pathProperty) {
                        [void]$inventory.Add([pscustomobject]@{
                                Kind = 'local-action-runtime'
                                Location = "${Location}:$entry"
                                Target = [string]$pathProperty.Value
                            })
                    }
                }
            }
            return
        }

        $separator = $Uses.LastIndexOf('@')
        if ($separator -lt 1) {
            Add-AuditError "remote-uses-unpinned:$Location"
            return
        }
        $action = $Uses.Substring(0, $separator)
        $reference = $Uses.Substring($separator + 1)
        if ($action -match '(?i)(?:^|/)(?:upload-artifact|download-artifact|upload-pages-artifact|configure-pages|deploy-pages|release|pages)(?:$|/)') {
            Add-AuditError "publication-action-forbidden:$Location"
            return
        }
        if ($reference -cnotmatch '^[0-9a-f]{40}$') {
            Add-AuditError "remote-uses-not-commit-pinned:${Location}:$action"
            return
        }
        if ($action -ceq 'msys2/setup-msys2') {
            $withProperty = Get-Arm64MapProperty -Map $Owner -Name 'with'
            $msystemProperty = if ($null -eq $withProperty) {
                $null
            }
            else {
                Get-Arm64MapProperty -Map $withProperty.Value -Name 'msystem'
            }
            if ($null -eq $msystemProperty -or
                $msystemProperty.Value -isnot [string] -or
                @($Policy.forbidden_msystems) -ccontains $msystemProperty.Value) {
                Add-AuditError "unsupported-msystem-before-setup:$Location"
            }
        }
        $pin = Get-Arm64ExactMapProperty -Map $Policy.external_action_pins -Name $action
        if ($null -eq $pin) {
            Add-AuditError "remote-uses-not-reviewed:${Location}:$action"
            return
        }
        $commit = Get-Arm64MapProperty -Map $pin.Value -Name 'commit'
        if ($null -eq $commit -or $reference -cne $commit.Value) {
            Add-AuditError "remote-uses-pin-mismatch:${Location}:$action"
        }

    }

    function Test-Steps {
        param(
            [AllowNull()][object]$Steps,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Steps -is [string] -or $Steps -isnot [Collections.IEnumerable]) {
            Add-AuditError "steps-invalid:$Location"
            return
        }
        $index = 0
        foreach ($step in @($Steps)) {
            $usesProperty = Get-Arm64MapProperty -Map $step -Name 'uses'
            $runProperty = Get-Arm64MapProperty -Map $step -Name 'run'
            if ($null -ne $usesProperty -and $null -ne $runProperty) {
                Add-AuditError "step-uses-and-run:${Location}:$index"
            }
            elseif ($null -ne $usesProperty) {
                Test-UsesReference `
                    -Uses $usesProperty.Value `
                    -Owner $step `
                    -WorkflowRule $WorkflowRule `
                    -Location "${Location}:step[$index]"
            }
            elseif ($null -ne $runProperty) {
                if ($runProperty.Value -is [string] -and
                    $runProperty.Value -match '(?i)(?:\bgh\s+release\b|/releases(?:/|\b)|\bartifact(?:s)?\b|\bpages\b)') {
                    Add-AuditError "publication-shell-route-forbidden:${Location}:step[$index]"
                }
                $shellProperty = Get-Arm64MapProperty -Map $step -Name 'shell'
                $allowedShellsProperty = Get-Arm64MapProperty `
                    -Map $WorkflowRule `
                    -Name 'allowed_shells'
                $allowedShells = if ($null -eq $allowedShellsProperty) {
                    @()
                }
                else {
                    @($allowedShellsProperty.Value)
                }
                if ($null -eq $shellProperty -or
                    $shellProperty.Value -isnot [string] -or
                    $allowedShells -cnotcontains $shellProperty.Value) {
                    Add-AuditError "shell-template-not-allowlisted:${Location}:step[$index]"
                }
                Test-RunStep `
                    -Run $runProperty.Value `
                    -WorkflowRule $WorkflowRule `
                    -Location "${Location}:step[$index]"
            }
            else {
                Add-AuditError "step-operation-missing:${Location}:$index"
            }
            $index++
        }
    }

    function Get-WorkflowEvents {
        param(
            [AllowNull()][object]$OnValue,
            [Parameter(Mandatory)][string]$Location
        )

        if ($OnValue -is [string]) {
            return @($OnValue)
        }
        if ($OnValue -is [Collections.IDictionary] -or $OnValue -is [pscustomobject]) {
            return @(Get-Arm64MapNames -Map $OnValue)
        }
        if ($OnValue -is [Collections.IEnumerable]) {
            $events = @($OnValue)
            if (@($events | Where-Object { $_ -isnot [string] }).Count -ne 0) {
                Add-AuditError "workflow-events-invalid:$Location"
                return @()
            }
            return $events
        }
        Add-AuditError "workflow-events-invalid:$Location"
        return @()
    }

    function Test-WorkflowFile {
        param(
            [Parameter(Mandatory)][string]$WorkflowPath,
            [string]$InvokedFrom = 'entrypoint'
        )

        if (-not (Test-Path -LiteralPath $WorkflowPath -PathType Leaf)) {
            Add-AuditError "workflow-file-missing:$WorkflowPath"
            return
        }
        $relative = Get-RelativeDataPath -Path $WorkflowPath
        if (-not $visitedWorkflows.Add($relative)) {
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'workflow'
                Location = $InvokedFrom
                Target = $relative
            })

        $ruleProperty = Get-Arm64MapProperty -Map $Policy.active_workflows -Name $relative
        if ($null -eq $ruleProperty) {
            Add-AuditError "workflow-not-allowlisted:$relative"
            $workflowRule = [pscustomobject]@{
                allowed_events = @()
                allowed_local_shell_entrypoints = @()
                allowed_local_shell_sources = [pscustomobject]@{}
                allowed_inline_shell_sha256 = @()
                allowed_shells = @()
                authority = 'unknown'
            }
        }
        else {
            $workflowRule = $ruleProperty.Value
            $workflowSourceProperty = Get-Arm64MapProperty `
                -Map $workflowRule `
                -Name 'source'
            if ($null -eq $workflowSourceProperty) {
                Add-AuditError "workflow-source-binding-missing:$relative"
            }
            else {
                try {
                    Assert-Arm64SourceBinding `
                        -Binding $workflowSourceProperty.Value `
                        -Label $relative
                    $identity = Get-Arm64FileBlobIdentity -Path $WorkflowPath
                    $actualSource = New-Arm64SourceBinding `
                        -Path $relative `
                        -Mode $workflowSourceProperty.Value.mode `
                        -ObjectType 'blob' `
                        -ByteLength $identity.byte_length `
                        -Oid $identity.oid
                    if (-not (Test-Arm64SourceBindingEqual `
                            -Expected $workflowSourceProperty.Value `
                            -Actual $actualSource)) {
                        Add-AuditError "workflow-source-binding-mismatch:$relative"
                    }
                }
                catch {
                    Add-AuditError "workflow-source-binding-invalid:$relative"
                }
            }
        }

        try {
            $workflow = ConvertFrom-Arm64YamlFile -Path $WorkflowPath -Backend $resolvedBackend
        }
        catch {
            Add-AuditError (Resolve-Arm64YamlErrorCode -ErrorRecord $_ -Relative $relative)
            return
        }
        if ($null -eq $workflow) {
            Add-AuditError "workflow-empty:$relative"
            return
        }

        foreach ($defaultsOwner in @(
                [pscustomobject]@{ Value = $workflow; Location = $relative })) {
            $defaultsProperty = Get-Arm64MapProperty -Map $defaultsOwner.Value -Name 'defaults'
            if ($null -ne $defaultsProperty) {
                $runDefaults = Get-Arm64MapProperty -Map $defaultsProperty.Value -Name 'run'
                $shellDefault = if ($null -eq $runDefaults) {
                    $null
                }
                else {
                    Get-Arm64MapProperty -Map $runDefaults.Value -Name 'shell'
                }
                if ($null -ne $shellDefault) {
                    Add-AuditError "default-shell-template-forbidden:$($defaultsOwner.Location)"
                }
            }
        }

        $onProperty = Get-Arm64MapProperty -Map $workflow -Name 'on'
        if ($null -eq $onProperty) {
            Add-AuditError "workflow-trigger-missing:$relative"
        }
        else {
            $actualEvents = @(Get-WorkflowEvents -OnValue $onProperty.Value -Location $relative |
                    Sort-Object -Unique)
            $allowedEventsProperty = Get-Arm64MapProperty `
                -Map $workflowRule `
                -Name 'allowed_events'
            $allowedEvents = if ($null -eq $allowedEventsProperty) {
                @()
            }
            else {
                @($allowedEventsProperty.Value | Sort-Object -Unique)
            }
            if (($actualEvents -join "`0") -cne ($allowedEvents -join "`0")) {
                Add-AuditError "workflow-trigger-not-allowlisted:$relative"
            }
            if (@($actualEvents | Where-Object {
                        $_ -match '^(?i:release|pages_build|workflow_dispatch)$'
                    }).Count -ne 0) {
                Add-AuditError "publication-trigger-forbidden:$relative"
            }
        }

        $workflowPermissions = Get-Arm64MapProperty -Map $workflow -Name 'permissions'
        if ($null -ne $workflowPermissions -and
            @('write', 'write-all') -ccontains [string]$workflowPermissions.Value) {
            Add-AuditError "publication-permissions-forbidden:$relative"
        }
        elseif ($null -ne $workflowPermissions) {
            foreach ($permissionName in Get-Arm64MapNames -Map $workflowPermissions.Value) {
                $permission = Get-Arm64MapProperty `
                    -Map $workflowPermissions.Value `
                    -Name $permissionName
                if ($null -ne $permission -and $permission.Value -ceq 'write') {
                    Add-AuditError "publication-permissions-forbidden:${relative}:$permissionName"
                }
            }
        }

        $jobsProperty = Get-Arm64MapProperty -Map $workflow -Name 'jobs'
        if ($null -eq $jobsProperty) {
            Add-AuditError "workflow-jobs-missing:$relative"
            return
        }
        foreach ($jobName in Get-Arm64MapNames -Map $jobsProperty.Value) {
            $job = (Get-Arm64MapProperty -Map $jobsProperty.Value -Name $jobName).Value
            $location = "${relative}:job[$jobName]"
            $jobNameProperty = Get-Arm64MapProperty -Map $job -Name 'name'
            $displayName = if ($null -eq $jobNameProperty) {
                [string]$jobName
            }
            else {
                [string]$jobNameProperty.Value
            }
            if ($displayName -ceq 'arm64-governance') {
                [void]$governanceCheckLocations.Add($location)
                $ifProperty = Get-Arm64MapProperty -Map $job -Name 'if'
                $needsProperty = Get-Arm64MapProperty -Map $job -Name 'needs'
                if ($null -ne $ifProperty -or $null -ne $needsProperty) {
                    Add-AuditError "governance-check-can-be-skipped:$location"
                }
            }
            elseif ($displayName.StartsWith(
                    'arm64-governance',
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                'arm64-governance'.StartsWith(
                    $displayName,
                    [StringComparison]::OrdinalIgnoreCase
                )) {
                Add-AuditError "governance-check-name-alias:$location"
            }
            $environmentProperty = Get-Arm64MapProperty -Map $job -Name 'environment'
            if ($null -ne $environmentProperty) {
                Add-AuditError "publication-environment-forbidden:$location"
            }
            $jobPermissions = Get-Arm64MapProperty -Map $job -Name 'permissions'
            if ($null -ne $jobPermissions -and
                @('write', 'write-all') -ccontains [string]$jobPermissions.Value) {
                Add-AuditError "publication-permissions-forbidden:$location"
            }
            elseif ($null -ne $jobPermissions) {
                foreach ($permissionName in Get-Arm64MapNames -Map $jobPermissions.Value) {
                    $permission = Get-Arm64MapProperty `
                        -Map $jobPermissions.Value `
                        -Name $permissionName
                    if ($null -ne $permission -and $permission.Value -ceq 'write') {
                        Add-AuditError "publication-permissions-forbidden:${location}:$permissionName"
                    }
                }
            }
            $jobDefaults = Get-Arm64MapProperty -Map $job -Name 'defaults'
            if ($null -ne $jobDefaults -and
                $null -ne (Get-Arm64MapProperty -Map $jobDefaults.Value -Name 'run')) {
                Add-AuditError "default-shell-template-forbidden:$location"
            }
            $jobUses = Get-Arm64MapProperty -Map $job -Name 'uses'
            if ($null -ne $jobUses) {
                Test-UsesReference `
                    -Uses $jobUses.Value `
                    -Owner $job `
                    -WorkflowRule $workflowRule `
                    -Location $location
            }

            $containerProperty = Get-Arm64MapProperty -Map $job -Name 'container'
            if ($null -ne $containerProperty) {
                $imageProperty = Get-Arm64MapProperty -Map $containerProperty.Value -Name 'image'
                $image = if ($null -eq $imageProperty) {
                    $containerProperty.Value
                }
                else {
                    $imageProperty.Value
                }
                Test-ContainerImage -Image $image -Location "${location}:container"
            }
            $servicesProperty = Get-Arm64MapProperty -Map $job -Name 'services'
            if ($null -ne $servicesProperty) {
                foreach ($serviceName in Get-Arm64MapNames -Map $servicesProperty.Value) {
                    $service = (Get-Arm64MapProperty -Map $servicesProperty.Value -Name $serviceName).Value
                    $imageProperty = Get-Arm64MapProperty -Map $service -Name 'image'
                    $image = if ($null -eq $imageProperty) { $service } else { $imageProperty.Value }
                    Test-ContainerImage -Image $image -Location "${location}:service[$serviceName]"
                }
            }

            $stepsProperty = Get-Arm64MapProperty -Map $job -Name 'steps'
            if ($null -ne $stepsProperty) {
                Test-Steps `
                    -Steps $stepsProperty.Value `
                    -WorkflowRule $workflowRule `
                    -Location $location
            }
            elseif ($null -eq $jobUses) {
                Add-AuditError "job-operation-missing:$location"
            }
        }
    }

    $workflowRoot = Join-Path $rootFull '.github\workflows'
    if (-not (Test-Path -LiteralPath $workflowRoot -PathType Container)) {
        Add-AuditError 'workflow-directory-missing'
    }
    else {
        $workflowFiles = @(Get-ChildItem -LiteralPath $workflowRoot -File -Recurse -Force |
                Where-Object { $_.Extension -in @('.yml', '.yaml') } |
                Sort-Object FullName)
        foreach ($workflowFile in $workflowFiles) {
            Test-WorkflowFile -WorkflowPath $workflowFile.FullName
        }

        $expectedWorkflows = @(Get-Arm64MapNames -Map $Policy.active_workflows | Sort-Object)
        $actualWorkflows = @($workflowFiles | ForEach-Object {
                Get-RelativeDataPath -Path $_.FullName
            } | Sort-Object)
        if (($expectedWorkflows -join "`0") -cne ($actualWorkflows -join "`0")) {
            Add-AuditError 'active-workflow-set-mismatch'
        }
    }

    if ($null -ne $protectedVerifierProperty) {
        if ($protectedVerifierProperty.Value.check_name -cne 'arm64-governance') {
            Add-AuditError 'protected-check-name-invalid'
        }
        if ($governanceCheckLocations.Count -ne 1) {
            Add-AuditError 'protected-check-name-not-unique'
        }
    }

    return [pscustomobject]@{
        Allowed = $errors.Count -eq 0
        Errors = @($errors)
        Inventory = @($inventory)
        Parser = $resolvedBackend
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if ([string]::IsNullOrWhiteSpace($CandidateRoot) -or
        [string]::IsNullOrWhiteSpace($PolicyPath)) {
        throw 'Specify -CandidateRoot and -PolicyPath.'
    }
    $policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json -Depth 64
    $result = Test-Arm64WorkflowTree `
        -Root $CandidateRoot `
        -Policy $policy `
        -TrustedPolicyPath $PolicyPath `
        -Backend $ParserBackend `
        -SkipAuthoritativeSnapshot:$FixtureMode
    if (-not $result.Allowed) {
        foreach ($errorCode in $result.Errors) {
            [Console]::Error.WriteLine("Workflow audit denied: $errorCode")
        }
        exit 1
    }

    Write-Output "Semantic workflow audit passed with $($result.Parser)."
}
