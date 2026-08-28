[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path
$policyPath = Join-Path (Join-Path (Join-Path $repoRoot '.github') 'policies') 'arm64-quarantine-policy.json'
$validatorPath = Join-Path (Join-Path (Join-Path $repoRoot '.github') 'scripts') 'arm64-admission.ps1'
$workflowRoot = Join-Path (Join-Path $repoRoot '.github') 'workflows'
$validPath = Join-Path (Join-Path $PSScriptRoot 'fixtures') 'valid.json'
$casesPath = Join-Path (Join-Path $PSScriptRoot 'fixtures') 'cases.json'

. $validatorPath

$assertionCount = 0
function Assert-Arm64 {
    param(
        [Parameter(Mandatory)]
        [bool]$Condition,
        [Parameter(Mandatory)]
        [string]$Message
    )

    $script:assertionCount++
    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

function Copy-ValidMetadata {
    return $script:validJson | ConvertFrom-Json -Depth 32
}

function Get-JsonMutationParent {
    param(
        [Parameter(Mandatory)]
        [object]$Root,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $segments = $Path.Split('.')
    $current = $Root
    for ($index = 0; $index -lt $segments.Length - 1; $index++) {
        $property = $current.PSObject.Properties[$segments[$index]]
        if ($null -eq $property) {
            throw "Fixture mutation parent does not exist: $Path"
        }
        $current = $property.Value
    }

    return [pscustomobject]@{
        Parent = $current
        Leaf   = $segments[-1]
    }
}

function Remove-JsonMutationPath {
    param(
        [Parameter(Mandatory)]
        [object]$Root,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $target = Get-JsonMutationParent -Root $Root -Path $Path
    if ($null -eq $target.Parent.PSObject.Properties[$target.Leaf]) {
        throw "Fixture mutation path does not exist: $Path"
    }
    $target.Parent.PSObject.Properties.Remove($target.Leaf)
}

function Set-JsonMutationPath {
    param(
        [Parameter(Mandatory)]
        [object]$Root,
        [Parameter(Mandatory)]
        [string]$Path,
        [AllowNull()]
        [object]$Value
    )

    $target = Get-JsonMutationParent -Root $Root -Path $Path
    $property = $target.Parent.PSObject.Properties[$target.Leaf]
    if ($null -eq $property) {
        $target.Parent | Add-Member -MemberType NoteProperty -Name $target.Leaf -Value $Value
    }
    else {
        $property.Value = $Value
    }
}

function Get-GitBlobSha {
    param([Parameter(Mandatory)][string]$Path)

    $text = [IO.File]::ReadAllText($Path).Replace("`r`n", "`n")
    $content = [Text.UTF8Encoding]::new($false).GetBytes($text)
    $prefix = [Text.Encoding]::UTF8.GetBytes("blob $($content.Length)`0")
    $payload = [byte[]]::new($prefix.Length + $content.Length)
    [Array]::Copy($prefix, 0, $payload, 0, $prefix.Length)
    [Array]::Copy($content, 0, $payload, $prefix.Length, $content.Length)
    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        $hash = $sha1.ComputeHash($payload)
    }
    finally {
        $sha1.Dispose()
    }

    return -join ($hash | ForEach-Object { $_.ToString('x2') })
}

$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json -Depth 32
$validJson = Get-Content -LiteralPath $validPath -Raw
$cases = Get-Content -LiteralPath $casesPath -Raw | ConvertFrom-Json -Depth 32

$valid = Copy-ValidMetadata
$validResult = Test-Arm64Admission -Metadata $valid -Policy $policy
Assert-Arm64 $validResult.Allowed "valid fixture denied: $($validResult.Errors -join ', ')"
Assert-Arm64 ($validResult.Errors.Count -eq 0) 'valid fixture returned errors'

foreach ($path in $cases.missing_paths) {
    $metadata = Copy-ValidMetadata
    Remove-JsonMutationPath -Root $metadata -Path $path
    $result = Test-Arm64Admission -Metadata $metadata -Policy $policy
    Assert-Arm64 (-not $result.Allowed) "missing path was admitted: $path"
    Assert-Arm64 ($result.Errors -ccontains "missing:$path") "missing path did not report its code: $path"
}

foreach ($case in $cases.mutations) {
    $metadata = Copy-ValidMetadata
    foreach ($mutation in $case.set.PSObject.Properties) {
        Set-JsonMutationPath -Root $metadata -Path $mutation.Name -Value $mutation.Value
    }
    $result = Test-Arm64Admission -Metadata $metadata -Policy $policy
    Assert-Arm64 (-not $result.Allowed) "mutation was admitted: $($case.name)"
    Assert-Arm64 ($result.Errors -ccontains $case.error) "mutation '$($case.name)' missed '$($case.error)'"
}

Assert-Arm64 ($policy.policy_id -ceq 'arm64-quarantine-policy') 'unexpected policy id'
Assert-Arm64 ($policy.mode -ceq 'deny-by-default') 'policy is not deny by default'
Assert-Arm64 ($policy.revocations.runtime.commits_and_descendants -ccontains
    'a527ace21c23b763bb96841745f0e2d8cd984f4a') 'runtime commit revocation missing'
Assert-Arm64 ($policy.revocations.runtime.release_ids -contains 376058416) 'runtime release revocation missing'
Assert-Arm64 ($policy.revocations.binutils.release_ids -contains 377908415) 'binutils release revocation missing'
Assert-Arm64 ($policy.revocations.binutils.package_sha256 -ccontains
    '3c7b47529181dab726d22cf6ed045184260af915eea583488c13c07e478ac02b') 'binutils digest revocation missing'
Assert-Arm64 ($policy.accepted_baseline.release_id -eq 368726166) 'baseline release changed'
Assert-Arm64 ($policy.accepted_baseline.tag_name -ceq 'v2.55.0.windows.4') 'baseline tag changed'
Assert-Arm64 ($policy.accepted_baseline.asset_id -eq 510402464) 'baseline asset changed'
Assert-Arm64 ($policy.accepted_baseline.asset_size -eq 171467184) 'baseline size changed'
Assert-Arm64 ($policy.accepted_baseline.asset_sha256 -ceq
    '7cc28b4431c9448c310d0093fbba5646517cd702690a9b965014d7df85319ad9') 'baseline digest changed'
Assert-Arm64 ($policy.owned_commit_terminal_trailers.Count -eq 2) 'terminal trailer pair count changed'
Assert-Arm64 ($policy.owned_commit_terminal_trailers[0] -ceq
    'Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>') 'co-author trailer changed'
Assert-Arm64 ($policy.owned_commit_terminal_trailers[1] -ceq
    'Copilot-Session: cbc02d21-36e2-4cf3-84cd-76e5bff6920c') 'session trailer changed'

$admissionWorkflowPath = Join-Path $workflowRoot 'arm64-admission.yml'
$admissionBlob = Get-GitBlobSha -Path $admissionWorkflowPath
Assert-Arm64 ($policy.admission_workflow.blob -ceq $admissionBlob) 'policy workflow blob does not match source'
Assert-Arm64 ($valid.workflow.blob -ceq $admissionBlob) 'valid fixture workflow blob does not match source'

$observedActions = @{}
foreach ($workflow in Get-ChildItem -LiteralPath $workflowRoot -Filter '*.yml') {
    $content = Get-Content -LiteralPath $workflow.FullName -Raw
    $actionMatches = [regex]::Matches(
        $content,
        '(?m)^\s*(?:-\s*)?uses:\s*(?<action>[^@\s]+)@(?<ref>[^\s#]+)'
    )
    foreach ($actionMatch in $actionMatches) {
        $action = $actionMatch.Groups['action'].Value
        if ($action.StartsWith('./', [StringComparison]::Ordinal)) {
            continue
        }

        $actionRef = $actionMatch.Groups['ref'].Value
        Assert-Arm64 ($actionRef -cmatch '^[0-9a-f]{40}$') "$($workflow.Name) has a mutable action ref: $action"
        $expected = $policy.external_action_pins.PSObject.Properties[$action]
        Assert-Arm64 ($null -ne $expected) "$($workflow.Name) uses an unreviewed action: $action"
        Assert-Arm64 ($actionRef -ceq $expected.Value) "$($workflow.Name) has the wrong pin for $action"
        $observedActions[$action] = $actionRef
    }
}
foreach ($expected in $policy.external_action_pins.PSObject.Properties) {
    Assert-Arm64 ($observedActions.ContainsKey($expected.Name)) "reviewed action pin is unused: $($expected.Name)"
}

$legacyWorkflows = @(
    'main.yml',
    'build-package.yml',
    'check-repository.yml',
    'mingw-cross-toolchain.yml',
    'mingw-native-toolchain.yml'
)
foreach ($legacyWorkflow in $legacyWorkflows) {
    $legacyPath = Join-Path $workflowRoot $legacyWorkflow
    $legacyText = Get-Content -LiteralPath $legacyPath -Raw
    Assert-Arm64 ($legacyText -match '(?m)^name: "Historical:') "$legacyWorkflow is not marked historical"
    $trigger = [regex]::Match($legacyText, '(?ms)^on:\s*\r?\n(?<block>.*?)(?=^\S)').Groups['block'].Value
    Assert-Arm64 ($trigger -notmatch '(?m)^\s{2}(?:pull_request|push):') "$legacyWorkflow has an automatic trigger"
}

$mainText = Get-Content -LiteralPath (Join-Path $workflowRoot 'main.yml') -Raw
$mainTrigger = [regex]::Match($mainText, '(?ms)^on:\s*\r?\n(?<block>.*?)(?=^\S)').Groups['block'].Value
Assert-Arm64 ($mainTrigger -match '(?m)^\s{2}workflow_dispatch:') 'historical entry point is not manual'

$diagnosticWorkflow = 'arm64-quarantine-policy.yml'
foreach ($workflow in Get-ChildItem -LiteralPath $workflowRoot -Filter '*.yml') {
    $content = Get-Content -LiteralPath $workflow.FullName -Raw
    $trigger = [regex]::Match($content, '(?ms)^on:\s*\r?\n(?<block>.*?)(?=^\S)').Groups['block'].Value
    if ($trigger -match '(?m)^\s{2}(?:pull_request|push):') {
        Assert-Arm64 ($workflow.Name -ceq $diagnosticWorkflow) "$($workflow.Name) is unexpectedly automatic"
    }
}

$diagnosticText = Get-Content -LiteralPath (Join-Path $workflowRoot $diagnosticWorkflow) -Raw
Assert-Arm64 ($diagnosticText -notmatch '(?i)runs-on:.*arm64') 'diagnostics schedule an ARM64 runner'
Assert-Arm64 ($diagnosticText -notmatch 'actions/(?:upload|download)-artifact@') 'diagnostics expose or consume artifacts'
Assert-Arm64 ($diagnosticText -notmatch 'uses:\s*\./\.github/workflows/') 'diagnostics invoke a legacy build'

$admissionText = Get-Content -LiteralPath $admissionWorkflowPath -Raw
$preflight = [regex]::Match(
    $admissionText,
    '(?ms)^  preflight:\r?\n(?<block>.*?)(?=^  validate:)'
).Groups['block'].Value
Assert-Arm64 (-not [string]::IsNullOrWhiteSpace($preflight)) 'admission preflight job missing'
Assert-Arm64 ($preflight -notmatch '(?m)^\s+uses:') 'admission preflight invokes an external action'
Assert-Arm64 ($admissionText -match '(?m)^\s{4}needs: preflight\r?$') 'policy validation does not depend on preflight'
foreach ($path in $cases.missing_paths) {
    Assert-Arm64 ($preflight.Contains("'$path'", [StringComparison]::Ordinal)) "preflight does not require $path"
}

$forbiddenCommands = @(
    'invoke-webrequest',
    'invoke-restmethod',
    'start-bitstransfer',
    'curl',
    'curl.exe',
    'wget',
    'wget.exe',
    'gh',
    'gh.exe',
    'pacman',
    'choco',
    'winget',
    'npm',
    'pip'
)
foreach ($offlineSource in @($validatorPath, $PSCommandPath)) {
    $tokens = $null
    $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile(
        $offlineSource,
        [ref]$tokens,
        [ref]$parseErrors
    )
    Assert-Arm64 ($parseErrors.Count -eq 0) "$offlineSource has PowerShell parse errors"
    $commands = $ast.FindAll({
            param($node)
            return $node -is [Management.Automation.Language.CommandAst]
        }, $true)
    foreach ($command in $commands) {
        $commandName = $command.GetCommandName()
        if ($null -ne $commandName) {
            Assert-Arm64 ($forbiddenCommands -cnotcontains $commandName.ToLowerInvariant()) "$offlineSource invokes $commandName"
        }
    }
}

Write-Output "Passed $assertionCount ARM64 quarantine policy assertions."
