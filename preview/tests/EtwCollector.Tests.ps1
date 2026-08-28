[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scripts = Join-Path $PSScriptRoot '..\scripts'
Import-Module (Join-Path $scripts 'Preview.Common.psm1') -Force
. (Join-Path $scripts 'Collect-Arm64EtwEvidence.ps1') -LibraryOnly

$script:passed = 0
function Assert-Equal($Expected, $Actual, [string]$Because = '') {
    $equal = if ($Expected -is [string] -or $Actual -is [string]) {
        [string]::Equals([string]$Expected, [string]$Actual, [StringComparison]::Ordinal)
    }
    else {
        $Expected -eq $Actual
    }
    if (-not $equal) { throw "Expected '$Expected', got '$Actual'. $Because" }
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    try { & $Action }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) {
            throw "Expected '$Pattern', got '$($_.Exception.Message)'"
        }
        return
    }
    throw "Expected an error matching '$Pattern'"
}
function Invoke-Test([string]$Name, [scriptblock]$Action) {
    & $Action
    $script:passed++
    Write-Host "PASS $Name"
}

function New-TestPe {
    param([string]$Path, [UInt16]$Machine = 0xAA64, [string]$Import)
    $bytes = [byte[]]::new(1024)
    $bytes[0] = 0x4d
    $bytes[1] = 0x5a
    [BitConverter]::GetBytes([UInt32]0x80).CopyTo($bytes, 0x3c)
    [BitConverter]::GetBytes([UInt32]0x4550).CopyTo($bytes, 0x80)
    [BitConverter]::GetBytes($Machine).CopyTo($bytes, 0x84)
    [BitConverter]::GetBytes([UInt16]1).CopyTo($bytes, 0x86)
    [BitConverter]::GetBytes([UInt16]0xf0).CopyTo($bytes, 0x94)
    [BitConverter]::GetBytes([UInt16]0x20b).CopyTo($bytes, 0x98)
    [BitConverter]::GetBytes([UInt32]16).CopyTo($bytes, 0x98 + 108)
    $section = 0x98 + 0xf0
    [Text.Encoding]::ASCII.GetBytes('.rdata').CopyTo($bytes, $section)
    [BitConverter]::GetBytes([UInt32]0x200).CopyTo($bytes, $section + 8)
    [BitConverter]::GetBytes([UInt32]0x1000).CopyTo($bytes, $section + 12)
    [BitConverter]::GetBytes([UInt32]0x200).CopyTo($bytes, $section + 16)
    [BitConverter]::GetBytes([UInt32]0x200).CopyTo($bytes, $section + 20)
    if (-not [string]::IsNullOrWhiteSpace($Import)) {
        [BitConverter]::GetBytes([UInt32]0x1000).CopyTo($bytes, 0x98 + 120)
        [BitConverter]::GetBytes([UInt32]40).CopyTo($bytes, 0x98 + 124)
        [BitConverter]::GetBytes([UInt32]0x1040).CopyTo($bytes, 0x200 + 12)
        [Text.Encoding]::ASCII.GetBytes($Import + [char]0).CopyTo($bytes, 0x240)
    }
    [IO.File]::WriteAllBytes($Path, $bytes)
}

function ConvertTo-XmlText([string]$Value) {
    return [Security.SecurityElement]::Escape($Value)
}

function New-TraceXml {
    param([object[]]$Events, [Nullable[int64]]$LostEvents = 0)
    $body = foreach ($event in $Events) {
        $data = @(
            "<Data Name=`"ProcessID`">$($event.pid)</Data>"
        )
        if ($event.kind -eq 'start') {
            $data += "<Data Name=`"ParentProcessID`">$($event.parent)</Data>"
            $data += "<Data Name=`"ImageName`">$(ConvertTo-XmlText $event.path)</Data>"
        }
        elseif ($event.kind -eq 'image') {
            $data += "<Data Name=`"ImageName`">$(ConvertTo-XmlText $event.path)</Data>"
        }
        $id = switch ($event.kind) { start { 1 } stop { 2 } image { 5 } }
        @"
<Event><System><Provider Guid="{$script:KernelProcessProvider}"/><EventID>$id</EventID><TimeCreated SystemTime="$($event.at)"/></System><EventData>$($data -join '')</EventData></Event>
"@
    }
    $lost = if ($null -eq $LostEvents) { '' } else { "<EventsLost>$LostEvents</EventsLost>" }
    return "<Events>$lost$($body -join '')</Events>"
}

function Write-Trace([string]$Path, [object[]]$Events, [Nullable[int64]]$LostEvents = 0) {
    New-TraceXml -Events $Events -LostEvents $LostEvents |
        Set-Content -LiteralPath $Path -Encoding utf8 -NoNewline
}

function Write-Summary([string]$Path, [int64]$LostEvents = 0) {
    "Files Processed:`t1`r`nTotal Events Processed`t42`r`nTotal Events Lost`t$LostEvents`r`n" |
        Set-Content -LiteralPath $Path -NoNewline
}

function New-Event([string]$Kind, [int]$ProcessId, [string]$At, [int]$Parent = 0, [string]$Path = '') {
    return [pscustomobject]@{ kind = $Kind; pid = $ProcessId; at = $At; parent = $Parent; path = $Path }
}

function New-CompleteEvidence([string]$ProcessPath) {
    $module = [ordered]@{
        path = $ProcessPath; sha256 = ('1' * 64); architecture = 'ARM64'; personality = 'MinGW'
    }
    $process = [ordered]@{
        instanceId = '42-1'; parentInstanceId = $null; processId = 42
        startUtc = '2026-01-01T00:00:00.1000000Z'; endUtc = '2026-01-01T00:00:00.9000000Z'
        role = 'role'; path = $ProcessPath; sha256 = ('1' * 64); architecture = 'ARM64'
        personality = 'MinGW'; modulesComplete = $true; modules = @($module)
    }
    $scenarios = foreach ($id in $script:ScenarioOrder) {
        $scenarioProcess = $process | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $contract = $script:ScenarioCommandContracts[$id]
        $scenarioPath = Join-Path 'C:\fixture' $contract.suffix
        $scenarioProcess.path = $scenarioPath
        $scenarioProcess.modules[0].path = $scenarioPath
        if ($id -in @('Git Bash', 'hook', 'rebase', 'git-svn')) {
            $scenarioProcess.personality = 'MSYS'
            $scenarioProcess.modules[0].personality = 'MSYS'
        }
        [ordered]@{
            id = $id; status = 'pass'; reason = $null
            command = @($scenarioPath) + @($contract.args)
            behavior = [ordered]@{
                operation = $script:ScenarioOperations[$id]; passed = $true; exitCode = 0
            }
            trace = [ordered]@{
                complete = $true; processEventsComplete = $true; imageLoadEventsComplete = $true
                processTreeComplete = $true; lostEvents = 0
                startUtc = '2026-01-01T00:00:00.0000000Z'; endUtc = '2026-01-01T00:00:01.0000000Z'
                processes = @($scenarioProcess)
            }
        }
    }
    return [pscustomobject][ordered]@{
        schemaVersion = 1; previewId = 'fixture'; admissionMode = 'Preview'
        sourceLockSha256 = ('0' * 64); lockSha256 = ('0' * 64); provenanceSha256 = ('0' * 64)
        payloadManifestSha256 = ('0' * 64); rootInventorySha256 = ('0' * 64)
        staticReportSha256 = ('0' * 64)
        validator = [ordered]@{
            repository = 'crutkas/build-extra'; commit = ('a' * 40)
            path = 'C:\fixture\preview-evidence\tools\build-extra\validate-arm64-bundle.ps1'
            bytes = 1; sha256 = ('d' * 64); mode = 'Runtime'
        }
        host = [ordered]@{ os = 'Windows'; architecture = 'ARM64' }
        collector = [ordered]@{
            inputId = 'arm64-etw-runtime-collector'
            repository = 'crutkas/msys2-woarm64-build'; commit = ('b' * 40)
            sourcePath = 'preview/scripts/Collect-Arm64EtwEvidence.ps1'
            url = 'https://raw.githubusercontent.com/crutkas/msys2-woarm64-build/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/preview/scripts/Collect-Arm64EtwEvidence.ps1'
            bytes = 1; sha256 = ('c' * 64); method = 'ETW-Kernel-Process-ImageLoad'
        }
        collectedUtc = '2026-01-01T00:00:02.0000000Z'; scenarios = @($scenarios)
    }
}

$temporary = Join-Path $PSScriptRoot ".etw-test-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $portable = Join-Path $temporary 'portable'
    New-Item -ItemType Directory -Path $portable | Out-Null
    $rootPe = Join-Path $portable 'root.exe'
    $childPe = Join-Path $portable 'child.dll'
    New-TestPe $rootPe
    New-TestPe $childPe

    Invoke-Test 'lost events must be explicit and zero' {
        $path = Join-Path $temporary 'lost.xml'
        $summary = Join-Path $temporary 'summary.txt'
        Write-Trace $path @()
        Write-Summary $summary 3
        Assert-Throws { Get-TracerptLostEvents $summary } 'lost events'
        Set-Content -LiteralPath $summary -Value 'Files Processed: 1'
        Assert-Throws { Get-TracerptLostEvents $summary } 'exactly one Total Events Lost'
    }

    Invoke-Test 'missing process stop fails closed' {
        $path = Join-Path $temporary 'missing-stop.xml'
        Write-Trace $path @(
            (New-Event start 42 '2026-01-01T00:00:01Z' 7 $rootPe),
            (New-Event image 42 '2026-01-01T00:00:01.1Z' 0 $rootPe)
        )
        Assert-Throws {
            $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
            ConvertTo-EtwProcessTree $parsed 42 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MinGW
        } 'no process stop|no stop event'
    }

    Invoke-Test 'missing process image module fails closed' {
        $path = Join-Path $temporary 'missing-image.xml'
        Write-Trace $path @(
            (New-Event start 42 '2026-01-01T00:00:01Z' 7 $rootPe),
            (New-Event stop 42 '2026-01-01T00:00:02Z')
        )
        Assert-Throws { ConvertFrom-TracerptXml @($path) -LostEvents 0 } 'no image-load events'
    }

    Invoke-Test 'PID reuse and active-parent correlation are deterministic' {
        $path = Join-Path $temporary 'reuse.xml'
        Write-Trace $path @(
            (New-Event start 42 '2026-01-01T00:00:01Z' 7 $rootPe),
            (New-Event image 42 '2026-01-01T00:00:01.1Z' 0 $rootPe),
            (New-Event stop 42 '2026-01-01T00:00:02Z'),
            (New-Event start 42 '2026-01-01T00:00:03Z' 7 $rootPe),
            (New-Event image 42 '2026-01-01T00:00:03.1Z' 0 $rootPe),
            (New-Event start 99 '2026-01-01T00:00:04Z' 42 $rootPe),
            (New-Event image 99 '2026-01-01T00:00:04.1Z' 0 $rootPe),
            (New-Event image 99 '2026-01-01T00:00:04.2Z' 0 $childPe),
            (New-Event stop 99 '2026-01-01T00:00:05Z'),
            (New-Event stop 42 '2026-01-01T00:00:06Z')
        )
        $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
        $tree = @(ConvertTo-EtwProcessTree $parsed 42 ([DateTimeOffset]'2026-01-01T00:00:02.5Z') `
            $portable 'C:\Windows' MinGW)
        Assert-Equal 2 $tree.Count
        Assert-Equal $tree[0].instanceId $tree[1].parentInstanceId
        Assert-Equal 2 $tree[1].modules.Count
    }

    Invoke-Test 'ETW images bind to payload manifest hashes' {
        $path = Join-Path $temporary 'payload-binding.xml'
        Write-Trace $path @(
            (New-Event start 43 '2026-01-01T00:00:01Z' 7 $rootPe),
            (New-Event image 43 '2026-01-01T00:00:01.1Z' 0 $rootPe),
            (New-Event stop 43 '2026-01-01T00:00:02Z')
        )
        $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
        $payloadHashes = [Collections.Generic.Dictionary[string, string]]::new(
            [StringComparer]::OrdinalIgnoreCase)
        $payloadHashes[$rootPe] = ('0' * 64)
        Assert-Throws {
            ConvertTo-EtwProcessTree $parsed 43 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MinGW $payloadHashes
        } 'not bound to the immutable payload manifest'
    }

    Invoke-Test 'x64 process images are rejected' {
        $x64 = Join-Path $portable 'x64.exe'
        New-TestPe $x64 0x8664
        $path = Join-Path $temporary 'x64.xml'
        Write-Trace $path @(
            (New-Event start 52 '2026-01-01T00:00:01Z' 7 $x64),
            (New-Event image 52 '2026-01-01T00:00:01.1Z' 0 $x64),
            (New-Event stop 52 '2026-01-01T00:00:02Z')
        )
        $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
        Assert-Throws {
            ConvertTo-EtwProcessTree $parsed 52 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MinGW
        } 'not native ARM64'
    }

    Invoke-Test 'role personality mismatch and Cygwin are rejected' {
        $msys = Join-Path $portable 'msys.exe'
        $cygwin = Join-Path $portable 'cygwin.exe'
        New-TestPe $msys 0xAA64 'msys-2.0.dll'
        New-TestPe $cygwin 0xAA64 'cygwin1.dll'
        Assert-Equal 'MSYS' (Get-EtwPersonality $msys 'C:\Windows')
        Assert-Equal 'Cygwin' (Get-EtwPersonality $cygwin 'C:\Windows')
        $path = Join-Path $temporary 'personality.xml'
        Write-Trace $path @(
            (New-Event start 62 '2026-01-01T00:00:01Z' 7 $msys),
            (New-Event image 62 '2026-01-01T00:00:01.1Z' 0 $msys),
            (New-Event stop 62 '2026-01-01T00:00:02Z')
        )
        $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
        Assert-Throws {
            ConvertTo-EtwProcessTree $parsed 62 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MinGW
        } 'expected'
        $cygwinPath = Join-Path $temporary 'cygwin.xml'
        Write-Trace $cygwinPath @(
            (New-Event start 63 '2026-01-01T00:00:01Z' 7 $cygwin),
            (New-Event image 63 '2026-01-01T00:00:01.1Z' 0 $cygwin),
            (New-Event stop 63 '2026-01-01T00:00:02Z')
        )
        $cygwinTrace = ConvertFrom-TracerptXml @($cygwinPath) -LostEvents 0
        Assert-Throws {
            ConvertTo-EtwProcessTree $cygwinTrace 63 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MSYS
        } 'Cygwin personality is prohibited'
        $cygwinRuntime = Join-Path $portable 'cygwin1.dll'
        New-TestPe $cygwinRuntime
        Assert-Equal 'Cygwin' (Get-EtwPersonality $cygwinRuntime 'C:\Windows')
    }

    Invoke-Test 'start-image leaf matching rejects Unicode lookalikes' {
        $helper = Join-Path $portable 'helper.exe'
        $softHelper = Join-Path $portable "hel$([char]0x00ad)per.exe"
        New-TestPe $helper
        New-TestPe $softHelper
        $path = Join-Path $temporary 'soft-helper.xml'
        Write-Trace $path @(
            (New-Event start 64 '2026-01-01T00:00:01Z' 7 'helper.exe'),
            (New-Event image 64 '2026-01-01T00:00:01.1Z' 0 $softHelper),
            (New-Event stop 64 '2026-01-01T00:00:02Z')
        )
        $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
        Assert-Throws {
            ConvertTo-EtwProcessTree $parsed 64 ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                $portable 'C:\Windows' MinGW
        } 'No process image-load event matches'
    }

    Invoke-Test 'duplicate image-load aliases fail closed' {
        $aliases = @($rootPe, $rootPe.ToUpperInvariant(), $rootPe.Replace('\', '/'))
        for ($index = 1; $index -lt $aliases.Count; $index++) {
            $path = Join-Path $temporary "duplicate-image-$index.xml"
            Write-Trace $path @(
                (New-Event start (70 + $index) '2026-01-01T00:00:01Z' 7 $rootPe),
                (New-Event image (70 + $index) '2026-01-01T00:00:01.1Z' 0 $aliases[0]),
                (New-Event image (70 + $index) '2026-01-01T00:00:01.2Z' 0 $aliases[$index]),
                (New-Event stop (70 + $index) '2026-01-01T00:00:02Z')
            )
            $parsed = ConvertFrom-TracerptXml @($path) -LostEvents 0
            Assert-Throws {
                ConvertTo-EtwProcessTree $parsed (70 + $index) `
                    ([DateTimeOffset]'2026-01-01T00:00:00Z') `
                    $portable 'C:\Windows' MinGW
            } 'Duplicate image-load event'
        }
    }

    Invoke-Test 'payload entry types and paths use explicit ordinal semantics' {
        $valid = [pscustomobject]@{ type = 'file'; path = 'bin/tool.exe'; sha256 = ('1' * 64) }
        $hashes = Get-EtwPayloadHashes -Entries @($valid) -PortableRoot 'C:\fixture'
        Assert-Equal 1 $hashes.Count
        foreach ($spoofedType in @("fi$([char]0x00ad)le", "f$([char]0x0130)le")) {
            $invalidType = [pscustomobject]@{
                type = $spoofedType; path = 'bin/other.exe'; sha256 = ('2' * 64)
            }
            Assert-Throws {
                Get-EtwPayloadHashes -Entries @($invalidType) -PortableRoot 'C:\fixture'
            } 'invalid ordinal entry type'
        }
        foreach ($alias in @('BIN/tool.exe', 'bin\tool.exe')) {
            $duplicate = [pscustomobject]@{
                type = 'file'; path = $alias; sha256 = ('1' * 64)
            }
            Assert-Throws {
                Get-EtwPayloadHashes -Entries @($valid, $duplicate) -PortableRoot 'C:\fixture'
            } 'unsafe or duplicate path'
        }
        foreach ($alias in @('BIN/SUB', 'bin\sub')) {
            $directories = @(
                [pscustomobject]@{ type = 'directory'; path = 'bin/sub'; sha256 = $null },
                [pscustomobject]@{ type = 'directory'; path = $alias; sha256 = $null }
            )
            Assert-Throws {
                Get-EtwPayloadHashes -Entries $directories -PortableRoot 'C:\fixture'
            } 'unsafe or duplicate path'
        }
    }

    Invoke-Test 'validator binding uses the exact source-lock input identity' {
        $commit = 'a' * 40
        $sourceInput = [pscustomobject]@{
            id = 'validator-main'; role = 'authoritative-validator-main'; status = 'resolved'
            identity = [pscustomobject]@{
                repository = 'crutkas/build-extra'; commit = $commit
                sourcePath = 'validate-arm64-bundle.ps1'
            }
            asset = [pscustomobject]@{
                url = "https://raw.githubusercontent.com/crutkas/build-extra/$commit/validate-arm64-bundle.ps1"
                expectedBytes = 10; sha256 = ('1' * 64)
            }
        }
        $bundleInput = [pscustomobject]@{
            id = 'validator-main'; role = 'validation-tool'; status = 'resolved'
            resolution = [pscustomobject]@{ method = 'github-raw-commit' }
            release = [pscustomobject]@{
                repository = 'crutkas/build-extra'; targetCommit = $commit
                sourcePath = 'validate-arm64-bundle.ps1'
            }
            asset = [pscustomobject]@{
                url = $sourceInput.asset.url; bytes = 10; sha256 = ('1' * 64)
            }
        }
        $binding = Get-EtwValidatorBinding `
            -SourceLock ([pscustomobject]@{ inputs = @($sourceInput) }) `
            -BundleLock ([pscustomobject]@{ inputs = @($bundleInput) }) `
            -ValidatorCommit $commit
        Assert-Equal 'validator-main' $binding.id
        $alternate = $bundleInput | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $alternate.id = 'alternate-validator'
        $alternate.release.sourcePath = 'alternate/validate-arm64-bundle.ps1'
        Assert-Throws {
            Get-EtwValidatorBinding `
                -SourceLock ([pscustomobject]@{ inputs = @($sourceInput) }) `
                -BundleLock ([pscustomobject]@{ inputs = @($alternate) }) `
                -ValidatorCommit $commit
        } 'exact authoritative validator input ID'
        $alternateSource = $sourceInput | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $alternateBundle = $bundleInput | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $alternateSource.identity.sourcePath = 'alternate/validate-arm64-bundle.ps1'
        $alternateBundle.release.sourcePath = $alternateSource.identity.sourcePath
        $alternateSource.asset.url = "https://raw.githubusercontent.com/crutkas/build-extra/$commit/alternate/validate-arm64-bundle.ps1"
        $alternateBundle.asset.url = $alternateSource.asset.url
        Assert-Throws {
            Get-EtwValidatorBinding `
                -SourceLock ([pscustomobject]@{ inputs = @($alternateSource) }) `
                -BundleLock ([pscustomobject]@{ inputs = @($alternateBundle) }) `
                -ValidatorCommit $commit
        } 'exact source-lock validator identity'
    }

    Invoke-Test 'UTC formatting does not depend on current culture' {
        $oldCulture = [Globalization.CultureInfo]::CurrentCulture
        try {
            [Globalization.CultureInfo]::CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('de-DE')
            Assert-Equal '2026-01-02T03:04:05.0000000Z' `
                (ConvertTo-EtwUtc ([DateTimeOffset]'2026-01-02T03:04:05Z'))
        }
        finally {
            [Globalization.CultureInfo]::CurrentCulture = $oldCulture
        }
    }

    Invoke-Test 'canonical order and exact closed output shapes are enforced' {
        $fixtureRoot = 'C:\fixture'
        $fixtureValidator = 'C:\fixture\preview-evidence\tools\build-extra\validate-arm64-bundle.ps1'
        $evidence = New-CompleteEvidence $rootPe
        Assert-RuntimeEvidenceShape -Evidence $evidence -PortableRoot $fixtureRoot `
            -ValidatorPath $fixtureValidator
        $copy = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $first = $copy.scenarios[0]
        $copy.scenarios[0] = $copy.scenarios[1]
        $copy.scenarios[1] = $first
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $copy -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical order'
        $open = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $open.scenarios[0].trace | Add-Member unexpected $true
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $open -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'open or incomplete shape'
        $wrongCommand = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $wrongCommand.scenarios[0].command[3] = '-c'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $wrongCommand -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical command vector'
        $relativeCommand = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $relativeCommand.scenarios[0].command[0] = 'usr/bin/bash.exe'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $relativeCommand -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical command vector'
        $outsideCommand = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $outsideCommand.scenarios[0].command[0] = 'C:\outside\usr\bin\bash.exe'
        $outsideCommand.scenarios[0].trace.processes[0].path = 'C:\outside\usr\bin\bash.exe'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $outsideCommand -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical command vector'
        $wrongBehavior = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $wrongBehavior.scenarios[0].behavior.operation = 'git-hook'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $wrongBehavior -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'invalid behavior evidence'
        $relativeRole = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $relativeRole.scenarios[0].trace.processes[0].path = '\usr\bin\bash.exe'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $relativeRole -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'designated role'
        $wrongRoleCase = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $wrongRoleCase.scenarios[0].trace.processes[0].path = $wrongRoleCase.scenarios[0].trace.processes[0].path.ToUpperInvariant()
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $wrongRoleCase -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'designated role'
        $softHyphenPath = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $softHyphenPath.scenarios[0].command[0] = "C:\fixture\usr\bin\ba$([char]0x00ad)sh.exe"
        $softHyphenPath.scenarios[0].trace.processes[0].path = $softHyphenPath.scenarios[0].command[0]
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $softHyphenPath -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical command vector'
        $softHyphenPersonality = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $softHyphenPersonality.scenarios[2].trace.processes[0].personality = "Min$([char]0x00ad)GW"
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $softHyphenPersonality -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'wrong role personality'
        $turkishPersonality = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $turkishPersonality.scenarios[2].trace.processes[0].personality = "M$([char]0x0130)nGW"
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $turkishPersonality -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'wrong role personality'
        $collapsedArguments = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $collapsedArguments.scenarios[0].command = @(
            $collapsedArguments.scenarios[0].command[0],
            "--noprofile`0--norc`0-lc`0exit 0"
        )
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $collapsedArguments -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical command vector'
        $alternateValidator = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $alternateValidator.validator.path = 'C:\alternate\validate-arm64-bundle.ps1'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $alternateValidator -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'Runtime evidence identity is invalid'
        foreach ($mutation in @(
                @{ field = 'processSha'; value = ('2' * 64); error = 'process identity is not cross-bound' },
                @{ field = 'moduleSha'; value = ('2' * 64); error = 'process identity is not cross-bound' },
                @{ field = 'modulePersonality'; value = 'Native'; error = 'process identity is not cross-bound' },
                @{ field = 'moduleArchitecture'; value = 'ARM64EC'; error = 'invalid module evidence' }
            )) {
            $identity = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
            switch ($mutation.field) {
                processSha { $identity.scenarios[0].trace.processes[0].sha256 = $mutation.value }
                moduleSha { $identity.scenarios[0].trace.processes[0].modules[0].sha256 = $mutation.value }
                modulePersonality { $identity.scenarios[0].trace.processes[0].modules[0].personality = $mutation.value }
                moduleArchitecture { $identity.scenarios[0].trace.processes[0].modules[0].architecture = $mutation.value }
            }
            Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $identity -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } $mutation.error
        }
        $missingModule = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $missingModule.scenarios[0].trace.processes[0].modules[0].path = 'C:\fixture\usr\bin\other.dll'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $missingModule -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'process identity is not cross-bound'
        foreach ($alias in @(
                'C:\fixture\usr\bin\bash.exe',
                'C:\FIXTURE\USR\BIN\BASH.EXE',
                'C:/fixture/usr/bin/bash.exe'
            )) {
            $extraModule = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
            $module = $extraModule.scenarios[0].trace.processes[0].modules[0] |
                ConvertTo-Json | ConvertFrom-Json
            $module.path = $alias
            $extraModule.scenarios[0].trace.processes[0].modules = @(
                $extraModule.scenarios[0].trace.processes[0].modules[0], $module)
            Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $extraModule -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'duplicate module paths'
        }
        $wrongCollector = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $wrongCollector.collector.inputId = 'self-attested-collector'
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $wrongCollector -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'canonical lock input'
        $final = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $final.admissionMode = 'Final'
        $final.scenarios[2].status = 'unresolved'
        $final.scenarios[2].reason = 'fixture missing'
        $final.scenarios[2].trace = $null
        $final.scenarios[2].behavior = $null
        $final.scenarios[2].command = @()
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $final -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'Invalid unresolved'
        $unresolvedCommand = $evidence | ConvertTo-Json -Depth 20 | ConvertFrom-Json
        $unresolvedCommand.scenarios[2].status = 'unresolved'
        $unresolvedCommand.scenarios[2].reason = 'fixture missing'
        $unresolvedCommand.scenarios[2].behavior = $null
        $unresolvedCommand.scenarios[2].trace = $null
        Assert-Throws { Assert-RuntimeEvidenceShape -Evidence $unresolvedCommand -PortableRoot $fixtureRoot -ValidatorPath $fixtureValidator } 'Invalid unresolved'
    }

    Invoke-Test 'collector script has a valid PowerShell parser tree' {
        Assert-Equal $true ([IO.Path]::IsPathFullyQualified(
                (Get-FinalEtwPath $rootPe -Directory))) `
            'Portable root directory must have a canonical final path'
        $tokens = $null
        $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $scripts 'Collect-Arm64EtwEvidence.ps1'), [ref]$tokens, [ref]$errors)
        Assert-Equal 0 @($errors).Count ($errors | ForEach-Object Message) -join '; '
        $source = Get-Content -LiteralPath (Join-Path $scripts 'Collect-Arm64EtwEvidence.ps1') -Raw -Encoding utf8
        Assert-Equal $true $source.Contains(
            'Move-Item -LiteralPath $workRoot -Destination $failureDiagnostics') ''
    }
}
finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}

Write-Host "PASS: $script:passed ETW collector tests"
