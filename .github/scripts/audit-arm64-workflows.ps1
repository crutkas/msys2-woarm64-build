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
    return @($Map.PSObject.Properties.Name)
}

function Resolve-Arm64YamlBackend {
    param([Parameter(Mandatory)][string]$Requested)

    if ($Requested -ceq 'Unavailable') {
        throw 'semantic-parser-unavailable'
    }
    if ($Requested -in @('Auto', 'PowerShellYaml') -and
        $null -ne (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue)) {
        return 'PowerShellYaml'
    }
    if ($Requested -in @('Auto', 'RubyPsych') -and
        $null -ne (Get-Command ruby -ErrorAction SilentlyContinue)) {
        return 'RubyPsych'
    }
    throw 'semantic-parser-unavailable'
}

function ConvertFrom-Arm64YamlFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Backend
    )

    if ($Backend -ceq 'PowerShellYaml') {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Yaml
    }

    $parserPath = Join-Path $PSScriptRoot 'parse-yaml.rb'
    if (-not (Test-Path -LiteralPath $parserPath -PathType Leaf)) {
        throw 'semantic-parser-helper-missing'
    }
    $json = & ruby $parserPath $Path
    if ($LASTEXITCODE -ne 0) {
        throw "semantic-yaml-parse-failed:$Path"
    }
    return $json | ConvertFrom-Json -Depth 64
}

function Get-Arm64GitBlobHash {
    param([Parameter(Mandatory)][string]$Path)

    $text = [IO.File]::ReadAllText($Path).Replace("`r`n", "`n")
    $content = [Text.UTF8Encoding]::new($false).GetBytes($text)
    $prefix = [Text.Encoding]::UTF8.GetBytes("blob $($content.Length)`0")
    $payload = [byte[]]::new($prefix.Length + $content.Length)
    [Array]::Copy($prefix, 0, $payload, 0, $prefix.Length)
    [Array]::Copy($content, 0, $payload, $prefix.Length, $content.Length)
    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        return -join ($sha1.ComputeHash($payload) | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha1.Dispose()
    }
}

function Get-Arm64Sha256Text {
    param([Parameter(Mandatory)][string]$Text)

    $normalized = $Text.Replace("`r`n", "`n").Trim()
    return -join (
        [Security.Cryptography.SHA256]::HashData(
            [Text.UTF8Encoding]::new($false).GetBytes($normalized)
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
    if ($snapshot.authority -cne 'github-rest-api' -or
        $snapshot.complete -isnot [bool] -or -not $snapshot.complete -or
        $snapshot.repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or
        $snapshot.commit -notmatch '^[0-9a-f]{40}$' -or
        $snapshot.tree -notmatch '^[0-9a-f]{40}$') {
        throw 'authoritative-snapshot-invalid'
    }

    $expectedPaths = @($snapshot.files | ForEach-Object { [string]$_.path } | Sort-Object)
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
        if ($file.mode -cne '100644' -and $file.mode -cne '100755') {
            throw "authoritative-snapshot-mode-invalid:$($file.path)"
        }
        if ((Get-Arm64GitBlobHash -Path $path) -cne $file.blob) {
            throw "authoritative-snapshot-blob-mismatch:$($file.path)"
        }
    }
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

    $rootFull = [IO.Path]::GetFullPath($Root)
    if (-not $SkipAuthoritativeSnapshot) {
        try {
            Test-Arm64AuthoritativeSnapshot -Root $rootFull
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
        elseif ((Get-Arm64GitBlobHash -Path $TrustedPolicyPath) -cne
            (Get-Arm64GitBlobHash -Path $candidatePolicyPath)) {
            Add-AuditError 'protected-policy-change-requires-bootstrap'
        }
    }

    $protectedVerifierProperty = Get-Arm64MapProperty `
        -Map $Policy `
        -Name 'protected_verifier'
    if ($null -ne $protectedVerifierProperty) {
        $protectedScriptsProperty = Get-Arm64MapProperty `
            -Map $protectedVerifierProperty.Value `
            -Name 'scripts'
        if ($null -eq $protectedScriptsProperty) {
            Add-AuditError 'protected-source-allowlist-missing'
        }
        else {
            foreach ($protectedPath in Get-Arm64MapNames -Map $protectedScriptsProperty.Value) {
                try {
                    $resolvedProtectedPath = Resolve-Arm64DataPath `
                        -Root $rootFull `
                        -RelativePath $protectedPath
                    $expectedProtectedBlob = (
                        Get-Arm64MapProperty `
                            -Map $protectedScriptsProperty.Value `
                            -Name $protectedPath
                    ).Value
                    if (-not (Test-Path -LiteralPath $resolvedProtectedPath -PathType Leaf) -or
                        (Get-Arm64GitBlobHash -Path $resolvedProtectedPath) -cne
                        [string]$expectedProtectedBlob) {
                        Add-AuditError "protected-source-blob-mismatch:$protectedPath"
                    }
                }
                catch {
                    Add-AuditError "protected-source-invalid:$protectedPath"
                }
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

        $allowedBlobsProperty = Get-Arm64MapProperty `
            -Map $WorkflowRule `
            -Name 'allowed_local_shell_blobs'
        if ($null -eq $allowedBlobsProperty) {
            Add-AuditError "delegated-script-blob-allowlist-missing:$relative"
            return
        }
        $expectedBlob = Get-Arm64MapProperty -Map $allowedBlobsProperty.Value -Name $relative
        if ($null -eq $expectedBlob -or
            (Get-Arm64GitBlobHash -Path $ScriptPath) -cne [string]$expectedBlob.Value) {
            Add-AuditError "delegated-script-blob-mismatch:$relative"
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

        $authority = [string](Get-Arm64MapProperty -Map $WorkflowRule -Name 'authority').Value
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
                Add-AuditError "semantic-yaml-parse-failed:$relative"
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
        if ($reference -cnotmatch '^[0-9a-f]{40}$') {
            Add-AuditError "remote-uses-not-commit-pinned:${Location}:$action"
            return
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
                @($Policy.setup_msys2.supported_msystems) -cnotcontains $msystemProperty.Value -or
                @($Policy.setup_msys2.forbidden_msystems) -ccontains $msystemProperty.Value) {
                Add-AuditError "unsupported-msystem-before-setup:$Location"
            }
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
                allowed_local_shell_blobs = [pscustomobject]@{}
                allowed_inline_shell_sha256 = @()
                allowed_shells = @()
                authority = 'unknown'
            }
        }
        else {
            $workflowRule = $ruleProperty.Value
            $workflowBlobProperty = Get-Arm64MapProperty `
                -Map $workflowRule `
                -Name 'workflow_blob'
            if ($null -ne $workflowBlobProperty -and
                (Get-Arm64GitBlobHash -Path $WorkflowPath) -cne
                [string]$workflowBlobProperty.Value) {
                Add-AuditError "workflow-blob-mismatch:$relative"
            }
        }

        try {
            $workflow = ConvertFrom-Arm64YamlFile -Path $WorkflowPath -Backend $resolvedBackend
        }
        catch {
            Add-AuditError "semantic-yaml-parse-failed:$relative"
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
        }

        $jobsProperty = Get-Arm64MapProperty -Map $workflow -Name 'jobs'
        if ($null -eq $jobsProperty) {
            Add-AuditError "workflow-jobs-missing:$relative"
            return
        }
        foreach ($jobName in Get-Arm64MapNames -Map $jobsProperty.Value) {
            $job = (Get-Arm64MapProperty -Map $jobsProperty.Value -Name $jobName).Value
            $location = "${relative}:job[$jobName]"
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
