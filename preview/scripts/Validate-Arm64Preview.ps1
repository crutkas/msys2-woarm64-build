[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $PortableRoot,
    [Parameter(Mandatory = $true)][string] $EvidenceDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Preview.Common.psm1') -Force

function Test-ValidationOrdinalEqual {
    param($Left, $Right)
    return [string]::Equals([string]$Left, [string]$Right, [StringComparison]::Ordinal)
}

function Test-ValidationOrdinalIn {
    param($Value, [string[]]$Allowed)
    foreach ($candidate in $Allowed) {
        if (Test-ValidationOrdinalEqual $Value $candidate) { return $true }
    }
    return $false
}

function Get-ValidationSortedRecords {
    param([Parameter(Mandatory)] $Records)
    $items = [object[]]@($Records)
    [Array]::Sort($items, [Comparison[object]] {
            param($left, $right)
            $result = ([int]$left.processId).CompareTo([int]$right.processId)
            if ($result -eq 0) {
                $result = [StringComparer]::Ordinal.Compare(
                    [string]$left.path, [string]$right.path)
            }
            return $result
        })
    return @($items)
}

function Assert-PinnedRawValidationTools {
    param(
        [Parameter(Mandatory = $true)] $SourceLock,
        [Parameter(Mandatory = $true)][string] $PreviewEvidence
    )

    $roleRoots = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::Ordinal)
    $roleRoots.Add('authoritative-validator-main', 'tools\build-extra')
    $roleRoots.Add('authoritative-validator-support', 'tools\build-extra')
    $roleRoots.Add('authoritative-validator-schema', 'tools\build-extra')
    $roleRoots.Add('authoritative-runtime-collector', 'tools\runtime-collector')
    $roleRoots.Add('authoritative-runtime-support', 'tools\runtime-collector')
    foreach ($input in @($SourceLock.inputs | Where-Object { $roleRoots.ContainsKey([string]$_.role) })) {
        if (-not (Test-ValidationOrdinalEqual $input.status 'resolved') -or
            $null -eq $input.identity.PSObject.Properties['sourcePath']) {
            throw "Validation tool '$($input.id)' is not a resolved raw-commit input"
        }
        $relative = ConvertTo-SafeArchivePath -Member ([string]$input.identity.sourcePath)
        $materializationRoot = [IO.Path]::GetFullPath((Join-Path $PreviewEvidence $roleRoots[[string]$input.role])).TrimEnd('\')
        $path = [IO.Path]::GetFullPath((Join-Path $materializationRoot $relative.Replace('/', '\')))
        if (-not $path.StartsWith("$materializationRoot\", [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Pinned validation tool '$($input.id)' is absent or unsafe"
        }
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            [Int64]$item.Length -ne [Int64]$input.asset.expectedBytes -or
            -not (Test-ValidationOrdinalEqual (Get-Sha256 -Path $path) $input.asset.sha256)) {
            throw "Pinned validation tool '$($input.id)' does not match its source lock"
        }
    }
}

function Get-ProcessSnapshot {
    param(
        [Parameter(Mandatory = $true)][int] $RootProcessId,
        [Parameter(Mandatory = $true)] $ProcessRecords,
        [Parameter(Mandatory = $true)] $ModuleRecords,
        [Parameter(Mandatory = $true)] $ObservationErrors,
        [Parameter(Mandatory = $true)] $ObservationWarnings
    )

    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $ids = [Collections.Generic.HashSet[int]]::new()
    $null = $ids.Add($RootProcessId)
    do {
        $changed = $false
        foreach ($process in $all) {
            if ($ids.Contains([int]$process.ParentProcessId) -and $ids.Add([int]$process.ProcessId)) {
                $changed = $true
            }
        }
    } while ($changed)

    foreach ($id in $ids) {
        try {
            $process = [Diagnostics.Process]::GetProcessById($id)
            $image = $process.MainModule.FileName
            $key = "$id|$image"
            if (-not $ProcessRecords.ContainsKey($key)) {
                $ProcessRecords[$key] = [ordered]@{
                    processId = $id
                    path = $image
                    architecture = Get-PeArchitecture -Path $image
                }
            }
            foreach ($module in $process.Modules) {
                $moduleKey = "$id|$($module.FileName)"
                if (-not $ModuleRecords.ContainsKey($moduleKey)) {
                    $ModuleRecords[$moduleKey] = [ordered]@{
                        processId = $id
                        path = $module.FileName
                        architecture = Get-PeArchitecture -Path $module.FileName
                    }
                }
            }
        }
        catch {
            $key = "$id|$($_.Exception.Message)"
            $record = [ordered]@{
                processId = $id
                error = $_.Exception.Message
            }
            if ($_.Exception -is [ArgumentException] -or
                $_.Exception -is [InvalidOperationException]) {
                $ObservationWarnings[$key] = $record
            } else {
                $ObservationErrors[$key] = $record
            }
        }
    }
}

function Invoke-NativeSmoke {
    param(
        [Parameter(Mandatory = $true)][string] $Id,
        [Parameter(Mandatory = $true)][string] $Script,
        [switch] $Interactive,
        [Parameter(Mandatory = $true)][string] $BashPath,
        [Parameter(Mandatory = $true)][string] $WorkingDirectory,
        [Parameter(Mandatory = $true)][string] $PortablePath,
        [Parameter(Mandatory = $true)] $ProcessRecords,
        [Parameter(Mandatory = $true)] $ModuleRecords,
        [Parameter(Mandatory = $true)] $ObservationErrors,
        [Parameter(Mandatory = $true)] $ObservationWarnings
    )

    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $BashPath
    $info.UseShellExecute = $false
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.CreateNoWindow = $true
    $info.WorkingDirectory = $WorkingDirectory
    $info.ArgumentList.Add('--noprofile')
    $info.ArgumentList.Add('--norc')
    if ($Interactive) {
        $info.ArgumentList.Add('-i')
    }
    $info.ArgumentList.Add('-c')
    $hold = 'end=$((SECONDS+1)); while ((SECONDS < end)); do :; done; '
    $info.ArgumentList.Add($hold + $Script)
    $info.Environment['PATH'] = $PortablePath
    $info.Environment['HOME'] = (Join-Path $WorkingDirectory 'home')
    $info.Environment['MSYSTEM'] = 'CLANGARM64'
    $info.Environment['TERM'] = 'xterm-256color'
    $info.Environment['LC_ALL'] = 'C.UTF-8'
    $info.Environment['MSYS'] = 'winsymlinks:nativestrict'

    $started = [DateTime]::UtcNow
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) {
        throw "Failed to start smoke test '$Id'"
    }
    $process.StandardInput.Close()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    while (-not $process.HasExited) {
        Get-ProcessSnapshot -RootProcessId $process.Id -ProcessRecords $ProcessRecords `
            -ModuleRecords $ModuleRecords -ObservationErrors $ObservationErrors `
            -ObservationWarnings $ObservationWarnings
        Start-Sleep -Milliseconds 10
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $exitCode = $process.ExitCode
    $process.Dispose()

    return [ordered]@{
        id = $Id
        passed = ($exitCode -eq 0)
        exitCode = $exitCode
        startedAtUtc = $started.ToString('o')
        durationMilliseconds = [int]([DateTime]::UtcNow - $started).TotalMilliseconds
        interactive = [bool]$Interactive
        stdout = $stdout
        stderr = $stderr
    }
}

Assert-PrivatePath -Path $PortableRoot
Assert-PrivatePath -Path $EvidenceDirectory
if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne
    [Runtime.InteropServices.Architecture]::Arm64) {
    throw "ARM-box validation requires Windows ARM64; detected $([Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
}
if ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne
    [Runtime.InteropServices.Architecture]::Arm64) {
    throw "ARM-box validation requires native ARM64 PowerShell; detected $([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture)"
}
if (-not (Test-Path -LiteralPath $PortableRoot -PathType Container)) {
    throw "Portable root does not exist: $PortableRoot"
}
Assert-NoPreparationTools -Root $PortableRoot
if (Test-Path -LiteralPath $EvidenceDirectory) {
    throw "EvidenceDirectory must be fresh: $EvidenceDirectory"
}
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$work = Join-Path $EvidenceDirectory 'validation-work'
if (Test-Path -LiteralPath $work) {
    throw "Validation work directory must be fresh: $work"
}
New-Item -ItemType Directory -Path $work | Out-Null
New-Item -ItemType Directory -Path (Join-Path $work 'home') | Out-Null

$bash = Join-Path $PortableRoot 'usr\bin\bash.exe'
if (-not (Test-ValidationOrdinalEqual (Get-PeArchitecture -Path $bash) 'arm64')) {
    throw "Validation bash is not ARM64: $bash"
}
$portablePath = @(
    (Join-Path $PortableRoot 'cmd'),
    (Join-Path $PortableRoot 'clangarm64\bin'),
    (Join-Path $PortableRoot 'mingw64\bin'),
    (Join-Path $PortableRoot 'usr\bin')
) -join ';'
$processes = @{}
$modules = @{}
$observationErrors = @{}
$observationWarnings = @{}
$validatorImage = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$processes["$PID|$validatorImage"] = [ordered]@{
    processId = $PID
    path = $validatorImage
    architecture = Get-PeArchitecture -Path $validatorImage
}
foreach ($module in [Diagnostics.Process]::GetCurrentProcess().Modules) {
    $modules["$PID|$($module.FileName)"] = [ordered]@{
        processId = $PID
        path = $module.FileName
        architecture = Get-PeArchitecture -Path $module.FileName
    }
}
$tests = [Collections.Generic.List[object]]::new()
$commandClosure = [Collections.Generic.List[object]]::new()
foreach ($relative in @(
    'usr/bin/bash.exe',
    'usr/bin/sh.exe',
    'cmd/git.exe',
    'usr/bin/uname.exe',
    'usr/bin/tr.exe',
    'usr/bin/touch.exe',
    'usr/bin/grep.exe',
    'usr/bin/mkdir.exe',
    'usr/bin/rm.exe',
    'usr/bin/ln.exe',
    'usr/bin/cat.exe',
    'usr/bin/chmod.exe',
    'usr/bin/cygpath.exe',
    'usr/bin/wc.exe'
)) {
    $commandPath = Join-Path $PortableRoot $relative.Replace('/', '\')
    if (-not (Test-Path -LiteralPath $commandPath -PathType Leaf)) {
        throw "Smoke command closure file is absent: $relative"
    }
    $commandClosure.Add([ordered]@{
        path = $relative
        architecture = Get-PeArchitecture -Path $commandPath
    })
}
foreach ($gitCoreRoot in @(
    (Join-Path $PortableRoot 'clangarm64\libexec\git-core'),
    (Join-Path $PortableRoot 'mingw64\libexec\git-core')
)) {
    if (-not (Test-Path -LiteralPath $gitCoreRoot -PathType Container)) {
        continue
    }
    foreach ($helper in Get-ChildItem -LiteralPath $gitCoreRoot -Filter '*.exe' -File -Force) {
        $commandClosure.Add([ordered]@{
            path = Get-RelativeUnixPath -Root $PortableRoot -Path $helper.FullName
            architecture = Get-PeArchitecture -Path $helper.FullName
        })
    }
}

$definitions = @(
    [ordered]@{
        id = 'bash-startup'
        script = 'printf "startup:%s\n" "$BASH_VERSION"; uname -a; test -n "$BASH_VERSION"'
        interactive = $false
    },
    [ordered]@{
        id = 'bash-noninteractive'
        script = 'test "$(bash --noprofile --norc -c ''printf noninteractive'')" = noninteractive'
        interactive = $false
    },
    [ordered]@{
        id = 'bash-interactive'
        script = 'case $- in *i*) printf "interactive\n";; *) exit 40;; esac'
        interactive = $true
    },
    [ordered]@{
        id = 'shell-semantics'
        script = @'
set -eu
mkdir -p semantics
cd semantics
touch alpha.txt beta.txt
set -- *.txt
test "$#" -eq 2
test "$(printf '%s\n' "a b" | tr ' ' '_')" = a_b
test "$(printf 'UTF-8:Grüße')" = "UTF-8:Grüße"
bash -c 'exit 23' && exit 41 || test "$?" -eq 23
trap 'exit 0' TERM
kill -TERM $$
exit 42
'@
        interactive = $false
    },
    [ordered]@{
        id = 'fork-spawn'
        script = 'test "$(bash --noprofile --norc -c ''printf child'')" = child; (printf forked) | grep -q forked'
        interactive = $false
    },
    [ordered]@{
        id = 'terminal'
        script = 'printf "TERM=%s\n" "$TERM"; test "$TERM" = xterm-256color; test ! -t 0'
        interactive = $false
    },
    [ordered]@{
        id = 'git-worktree'
        script = @'
set -eu
rm -rf worktree
mkdir worktree
cd worktree
git init -q
git config user.name Preview
git config user.email preview@example.invalid
printf one > tracked.txt
git add tracked.txt
git commit -qm initial
printf two >> tracked.txt
git status --porcelain | grep -q '^ M tracked.txt'
git add tracked.txt
git commit -qm second
test "$(git log --format=%s -1)" = second
'@
        interactive = $false
    },
    [ordered]@{
        id = 'git-bare-transport'
        script = @'
set -eu
rm -rf source.git clone.git
git clone -q --bare worktree source.git
git clone -q source.git clone.git
cd clone.git
git fetch -q origin
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/HEAD)"
'@
        interactive = $false
    },
    [ordered]@{
        id = 'git-hook'
        script = @'
set -eu
cd worktree
printf '#!/usr/bin/env bash\nprintf hook-ran > ../hook.txt\n' > .git/hooks/post-commit
chmod +x .git/hooks/post-commit
printf three >> tracked.txt
git add tracked.txt
git commit -qm hook
test "$(cat ../hook.txt)" = hook-ran
'@
        interactive = $false
    },
    [ordered]@{
        id = 'symlink-path'
        script = @'
set -eu
rm -rf 'space ü'
mkdir 'space ü'
printf target > 'space ü/target.txt'
ln -s target.txt 'space ü/link.txt'
test -L 'space ü/link.txt'
test "$(cat 'space ü/link.txt')" = target
test "$(cygpath -w 'space ü/target.txt')" != ""
'@
        interactive = $false
    }
)

foreach ($definition in $definitions) {
    $tests.Add((Invoke-NativeSmoke -Id $definition.id -Script $definition.script `
        -Interactive:$definition.interactive -BashPath $bash -WorkingDirectory $work `
        -PortablePath $portablePath -ProcessRecords $processes -ModuleRecords $modules `
        -ObservationErrors $observationErrors -ObservationWarnings $observationWarnings))
}

$artifactFiles = @(
    [ordered]@{ kind = 'source-lock'; path = Join-Path $PortableRoot 'preview-evidence\source-lock.json' },
    [ordered]@{ kind = 'lock'; path = Join-Path $PortableRoot 'preview-evidence\bundle-lock.v1.json' },
    [ordered]@{ kind = 'provenance'; path = Join-Path $PortableRoot 'preview-evidence\provenance.v1.json' },
    [ordered]@{ kind = 'payload'; path = Join-Path $PortableRoot 'preview-evidence\payload-manifest.v1.json' },
    [ordered]@{ kind = 'assembly-run'; path = Join-Path $PortableRoot 'preview-evidence\assembly-run-evidence.v1.json' },
    [ordered]@{ kind = 'static-report'; path = Join-Path $PortableRoot 'preview-evidence\authoritative-preview-report.v1.json' }
)
$artifacts = @($artifactFiles | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_.path -PathType Leaf)) {
        throw "Required validation artifact is absent: $($_.path)"
    }
    [ordered]@{
        kind = $_.kind
        path = Get-RelativeUnixPath -Root $PortableRoot -Path $_.path
        bytes = (Get-Item -LiteralPath $_.path).Length
        sha256 = Get-Sha256 -Path $_.path
    }
})
$assemblyEvidence = Get-Content -LiteralPath (
    @($artifactFiles | Where-Object {
            Test-ValidationOrdinalEqual $_.kind 'assembly-run'
        })[0].path
) -Raw | ConvertFrom-Json
$processEvidence = @(Get-ValidationSortedRecords $processes.Values)
$moduleEvidence = @(Get-ValidationSortedRecords $modules.Values)
$x64Processes = @($processEvidence | Where-Object {
        Test-ValidationOrdinalEqual $_.architecture 'x64'
    })
$x64Modules = @($moduleEvidence | Where-Object {
        Test-ValidationOrdinalEqual $_.architecture 'x64'
    })
$x64Commands = @($commandClosure | Where-Object {
        Test-ValidationOrdinalEqual $_.architecture 'x64'
    })
$foreignProcesses = @($processEvidence | Where-Object {
        -not (Test-ValidationOrdinalIn $_.architecture @('arm64', 'arm64x'))
    })
$foreignModules = @($moduleEvidence | Where-Object {
    $null -ne $_.architecture -and
        -not (Test-ValidationOrdinalIn $_.architecture @('arm64', 'arm64x'))
})
$foreignCommands = @($commandClosure | Where-Object {
        -not (Test-ValidationOrdinalEqual $_.architecture 'arm64')
    })
$failedTests = @($tests | Where-Object { -not $_.passed })
$evidence = [ordered]@{
    schemaVersion = 1
    previewId = $assemblyEvidence.previewId
    collectedAtUtc = [DateTime]::UtcNow.ToString('o')
    machine = [ordered]@{
        computerName = $env:COMPUTERNAME
        osDescription = [Runtime.InteropServices.RuntimeInformation]::OSDescription
        osArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        processArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
        windowsOsArchitecture = (Get-CimInstance Win32_OperatingSystem).OSArchitecture
    }
    processes = $processEvidence
    modules = $moduleEvidence
    processObservationErrors = @($observationErrors.Values)
    processObservationWarnings = @($observationWarnings.Values)
    commandClosure = @($commandClosure)
    tests = @($tests)
    artifacts = $artifacts
    leakage = [ordered]@{
        x64Processes = $x64Processes
        x64Modules = $x64Modules
        x64Commands = $x64Commands
        foreignProcesses = $foreignProcesses
        foreignModules = $foreignModules
        foreignCommands = $foreignCommands
    }
    pty = [ordered]@{
        attempted = $false
        reason = 'No independently admitted native ARM64 PTY helper is part of the locked shell closure yet.'
    }
    result = if ($failedTests.Count -eq 0 -and $foreignProcesses.Count -eq 0 -and
        $foreignModules.Count -eq 0 -and $foreignCommands.Count -eq 0 -and
        $observationErrors.Count -eq 0) {
        'pass'
    } else {
        'fail'
    }
}
Assert-EvidenceComplete -Evidence ([pscustomobject]$evidence)
$evidencePath = Join-Path $EvidenceDirectory 'arm64-validation-evidence.v1.json'
$evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $evidencePath -Encoding utf8
$schemaPath = Join-Path $PSScriptRoot 'schemas\arm64-validation-evidence.schema.json'
if (-not (Test-Path -LiteralPath $schemaPath)) {
    $schemaPath = Join-Path $PSScriptRoot '..\schemas\arm64-validation-evidence.schema.json'
}
$evidenceJson = Get-Content -LiteralPath $evidencePath -Raw -Encoding utf8
if (-not ($evidenceJson | Test-Json -SchemaFile $schemaPath)) {
    throw "Generated ARM64 validation evidence failed its versioned schema"
}

if (-not (Test-ValidationOrdinalEqual $evidence.result 'pass')) {
    Write-Error "ARM64 preview validation failed: $($failedTests.Count) smoke failures, $($foreignProcesses.Count) foreign processes, $($foreignModules.Count) foreign modules, $($foreignCommands.Count) foreign command-closure files, $($observationErrors.Count) observation errors"
    exit 1
}

$previewEvidence = Join-Path $PortableRoot 'preview-evidence'
$sourceLockPath = Join-Path $previewEvidence 'source-lock.json'
$lockPath = Join-Path $previewEvidence 'bundle-lock.v1.json'
$provenancePath = Join-Path $previewEvidence 'provenance.v1.json'
$payloadManifestPath = Join-Path $previewEvidence 'payload-manifest.v1.json'
$assemblyEvidencePath = Join-Path $previewEvidence 'assembly-run-evidence.v1.json'
$staticReportPath = Join-Path $previewEvidence 'authoritative-preview-report.v1.json'
$toolRoot = Join-Path $previewEvidence 'tools\validator-runtime'
$runtimeEvidencePath = Join-Path $EvidenceDirectory 'runtime-evidence.v1.json'
$runtimeReportPath = Join-Path $EvidenceDirectory 'authoritative-runtime-report.v1.json'
$collectorLogPath = Join-Path $EvidenceDirectory 'runtime-collector.log'
$runtimeValidatorLogPath = Join-Path $EvidenceDirectory 'authoritative-runtime-validator.log'
foreach ($required in @(
        $sourceLockPath, $lockPath, $provenancePath, $payloadManifestPath,
        $assemblyEvidencePath, $staticReportPath
    )) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required authoritative validation input is absent: $required"
    }
}
if (-not (Test-Path -LiteralPath $toolRoot -PathType Container)) {
    throw "Pinned authoritative validator tool root is absent: $toolRoot"
}
$sourceLock = Get-Content -LiteralPath $sourceLockPath -Raw -Encoding utf8 | ConvertFrom-Json
$bundleLock = Get-Content -LiteralPath $lockPath -Raw -Encoding utf8 | ConvertFrom-Json
if (-not (Test-ValidationOrdinalEqual $bundleLock.sourceLock.path 'preview-evidence/source-lock.json') -or
    [string]$bundleLock.sourceLock.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
    -not (Test-ValidationOrdinalEqual (Get-Sha256 -Path $sourceLockPath) $bundleLock.sourceLock.sha256)) {
    throw "Source lock is not authenticated by the canonical bundle lock"
}
Assert-PinnedRawValidationTools -SourceLock $sourceLock -PreviewEvidence $previewEvidence
$validatorInputs = @($sourceLock.inputs | Where-Object {
        Test-ValidationOrdinalEqual $_.role 'authoritative-validator-main'
    })
if ($validatorInputs.Count -ne 1 -or
    [string]$validatorInputs[0].identity.commit -cnotmatch '^[0-9a-f]{40}$') {
    throw "Source lock must identify exactly one pinned authoritative validator"
}
$canonicalValidatorInputs = @($bundleLock.inputs | Where-Object {
        Test-ValidationOrdinalEqual $_.id $validatorInputs[0].id
    })
if ($canonicalValidatorInputs.Count -ne 1 -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].role 'validation-tool') -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].status 'resolved') -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].release.repository 'crutkas/build-extra') -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].release.targetCommit $validatorInputs[0].identity.commit) -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].release.sourcePath $validatorInputs[0].identity.sourcePath) -or
    [Int64]$canonicalValidatorInputs[0].asset.bytes -ne [Int64]$validatorInputs[0].asset.expectedBytes -or
    -not (Test-ValidationOrdinalEqual $canonicalValidatorInputs[0].asset.sha256 $validatorInputs[0].asset.sha256)) {
    throw "Canonical bundle lock does not bind the authoritative validator identity"
}
$validatorCommit = [string]$canonicalValidatorInputs[0].release.targetCommit
$validatorRelative = ConvertTo-SafeArchivePath -Member ([string]$validatorInputs[0].identity.sourcePath)
$validatorRoot = [IO.Path]::GetFullPath((Join-Path $previewEvidence 'tools\build-extra')).TrimEnd('\')
$validatorPath = [IO.Path]::GetFullPath((Join-Path $validatorRoot $validatorRelative.Replace('/', '\')))
if (-not $validatorPath.StartsWith("$validatorRoot\", [StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $validatorPath -PathType Leaf) -or
    -not (Test-ValidationOrdinalEqual (Get-Sha256 -Path $validatorPath) $canonicalValidatorInputs[0].asset.sha256)) {
    throw "Authenticated authoritative validator main input is absent or changed"
}
$collectorInputs = @($sourceLock.inputs | Where-Object {
        Test-ValidationOrdinalEqual $_.role 'authoritative-runtime-collector'
    })
if ($collectorInputs.Count -ne 1 -or
    -not (Test-ValidationOrdinalEqual $collectorInputs[0].id 'arm64-etw-runtime-collector')) {
    throw "Source lock must identify exactly one canonical runtime collector"
}
$canonicalCollectorInputs = @($bundleLock.inputs | Where-Object {
        Test-ValidationOrdinalEqual $_.id $collectorInputs[0].id
    })
if ($canonicalCollectorInputs.Count -ne 1 -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].role 'validation-tool') -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].status 'resolved') -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].release.repository 'crutkas/msys2-woarm64-build') -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].release.targetCommit $collectorInputs[0].identity.commit) -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].release.sourcePath $collectorInputs[0].identity.sourcePath) -or
    [Int64]$canonicalCollectorInputs[0].asset.bytes -ne [Int64]$collectorInputs[0].asset.expectedBytes -or
    -not (Test-ValidationOrdinalEqual $canonicalCollectorInputs[0].asset.sha256 $collectorInputs[0].asset.sha256)) {
    throw "Canonical bundle lock does not bind the runtime collector identity"
}
$collectorRelative = ConvertTo-SafeArchivePath -Member ([string]$collectorInputs[0].identity.sourcePath)
$collectorRoot = [IO.Path]::GetFullPath((Join-Path $previewEvidence 'tools\runtime-collector')).TrimEnd('\')
$runtimeCollectorPath = [IO.Path]::GetFullPath((Join-Path $collectorRoot $collectorRelative.Replace('/', '\')))
if (-not $runtimeCollectorPath.StartsWith("$collectorRoot\", [StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $runtimeCollectorPath -PathType Leaf) -or
    -not (Test-ValidationOrdinalEqual (Get-Sha256 -Path $runtimeCollectorPath) $canonicalCollectorInputs[0].asset.sha256)) {
    throw "Authenticated runtime collector input is absent or changed"
}

$collectorOutput = @(& pwsh -NoLogo -NoProfile -File $runtimeCollectorPath `
    -PortableRoot $PortableRoot `
    -AdmissionMode Preview `
    -LockPath $lockPath `
    -ProvenancePath $provenancePath `
    -PayloadManifestPath $payloadManifestPath `
    -AssemblyEvidencePath $assemblyEvidencePath `
    -StaticReportPath $staticReportPath `
    -ValidatorCommit $validatorCommit `
    -ValidatorRoot $validatorRoot `
    -OutputPath $runtimeEvidencePath 2>&1)
$collectorExitCode = $LASTEXITCODE
$collectorOutput | Set-Content -LiteralPath $collectorLogPath -Encoding utf8
if ($collectorExitCode -ne 0) {
    throw "Authoritative ETW runtime collection failed with exit code $collectorExitCode; see $collectorLogPath"
}
Assert-PinnedRawValidationTools -SourceLock $sourceLock -PreviewEvidence $previewEvidence

$runtimeReportExisted = Test-Path -LiteralPath $runtimeReportPath
if ($runtimeReportExisted) {
    throw "Authoritative Runtime report path must not exist before validation: $runtimeReportPath"
}
$runtimeValidatorOutput = @(& pwsh -NoLogo -NoProfile -File $validatorPath `
    -Mode Runtime `
    -Root $PortableRoot `
    -Lock $lockPath `
    -Provenance $provenancePath `
    -PayloadManifest $payloadManifestPath `
    -ToolRoot $toolRoot `
    -Report $runtimeReportPath `
    -AssemblyEvidence $assemblyEvidencePath `
    -StaticReport $staticReportPath `
    -RuntimeEvidence $runtimeEvidencePath 2>&1)
$runtimeValidatorExitCode = $LASTEXITCODE
$runtimeValidatorOutput | Set-Content -LiteralPath $runtimeValidatorLogPath -Encoding utf8
if ($runtimeValidatorExitCode -ne 0) {
    throw "Authoritative Runtime validation failed with exit code $runtimeValidatorExitCode; see $runtimeValidatorLogPath"
}
Assert-PinnedRawValidationTools -SourceLock $sourceLock -PreviewEvidence $previewEvidence
if (-not (Test-Path -LiteralPath $runtimeReportPath -PathType Leaf)) {
    throw "Authoritative Runtime validator emitted no report"
}
$runtimeReport = Get-Content -LiteralPath $runtimeReportPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($null -eq $runtimeReport.PSObject.Properties['schemaVersion'] -or
    $null -eq $runtimeReport.PSObject.Properties['result'] -or
    -not (Test-ValidationOrdinalEqual $runtimeReport.result 'pass')) {
    throw "Authoritative Runtime validator emitted an incomplete or non-passing report"
}

[ordered]@{
    behavioralEvidence = $evidencePath
    runtimeEvidence = $runtimeEvidencePath
    authoritativeRuntimeReport = $runtimeReportPath
} | ConvertTo-Json
