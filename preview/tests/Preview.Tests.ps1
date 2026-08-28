[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scripts = Join-Path $PSScriptRoot '..\scripts'
Import-Module (Join-Path $scripts 'Preview.Common.psm1') -Force

$script:passed = 0
function Assert-Equal {
    param($Expected, $Actual, [string] $Because)
    if ($Expected -cne $Actual) {
        throw "Assertion failed: expected '$Expected', got '$Actual'. $Because"
    }
}
function Assert-Throws {
    param([scriptblock] $Action, [string] $Pattern)
    try {
        & $Action
    }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) {
            throw "Expected error matching '$Pattern', got '$($_.Exception.Message)'"
        }
        return
    }
    throw "Expected action to throw an error matching '$Pattern'"
}
function Invoke-Test {
    param([string] $Name, [scriptblock] $Action)
    & $Action
    $script:passed++
    Write-Host "PASS $Name"
}
function Copy-Object {
    param($Value)
    return ($Value | ConvertTo-Json -Depth 20 | ConvertFrom-Json)
}
function New-TestPe {
    param([string] $Path, [UInt16] $Machine)
    $bytes = [byte[]]::new(256)
    $bytes[0] = 0x4d
    $bytes[1] = 0x5a
    [BitConverter]::GetBytes([UInt32]128).CopyTo($bytes, 0x3c)
    $bytes[128] = 0x50
    $bytes[129] = 0x45
    [BitConverter]::GetBytes($Machine).CopyTo($bytes, 132)
    [IO.File]::WriteAllBytes($Path, $bytes)
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) "arm64-preview-tests-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $lockPath = Join-Path $PSScriptRoot '..\locks\portable-git-arm64-preview.v1.json'
    $lock = Read-PreviewLock -Path $lockPath

    Invoke-Test 'current lock reports only admitted gaps' {
        $raw = Get-Content -LiteralPath $lockPath -Raw -Encoding utf8
        Assert-Equal $true ($raw | Test-Json -SchemaFile (Join-Path $PSScriptRoot '..\schemas\preview-lock.schema.json')) ''
        $unresolved = @(Assert-PreviewLock -Lock $lock)
        Assert-Equal 'bash,ncurses-devel,ncurses-runtime,readline' (($unresolved | Sort-Object) -join ',') 'No immutable pins may be invented.'
    }

    Invoke-Test 'preparation extractors cannot enter the payload' {
        $extractors = @($lock.inputs | Where-Object role -eq 'archive-extractor')
        Assert-Equal 2 $extractors.Count ''
        foreach ($extractor in $extractors) {
            Assert-Equal $false $extractor.overlay.enabled ''
            Assert-Equal 0 @($extractor.overlay.mappings).Count ''
        }
        $payload = Join-Path $temporary 'forbidden-tool-payload'
        New-Item -ItemType Directory -Path $payload | Out-Null
        $evidenceTools = Join-Path $payload 'preview-evidence\tools'
        New-Item -ItemType Directory -Path $evidenceTools -Force | Out-Null
        [IO.File]::WriteAllBytes((Join-Path $evidenceTools '7zr.exe'), [byte[]](0))
        Assert-NoPreparationTools -Root $payload
        [IO.File]::WriteAllBytes((Join-Path $payload '7zr.exe'), [byte[]](0))
        Assert-Throws { Assert-NoPreparationTools -Root $payload } 'Preparation-only tools leaked'
    }

    Invoke-Test 'preparation roles cannot declare payload overlays' {
        $candidate = Copy-Object $lock
        $scanner = @($candidate.inputs | Where-Object id -eq 'fixed-binutils')[0]
        $scanner.overlay.enabled = $true
        $scanner.overlay.mappings = @([pscustomobject]@{ source = 'opt/bin'; destination = 'usr/bin'; overwrite = @() })
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'Preparation-only input'
    }

    Invoke-Test 'resolved payload mappings are explicit and collision-free' {
        $candidate = Copy-Object $lock
        $runtime = @($candidate.inputs | Where-Object id -eq 'runtime')[0]
        $runtime.overlay.mappings = @()
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'must declare at least one overlay mapping'

        $candidate = Copy-Object $lock
        $runtime = @($candidate.inputs | Where-Object id -eq 'runtime')[0]
        $runtime.overlay.mappings = @(
            [pscustomobject]@{
                source = 'opt/aarch64-pc-msys/bin/msys-2.0.dll'
                destination = 'usr/bin/msys-2.0.dll'
                allowOverwrite = $true
            },
            [pscustomobject]@{
                source = 'opt/aarch64-pc-msys/bin/other.dll'
                destination = 'USR/BIN/MSYS-2.0.DLL'
                allowOverwrite = $true
            }
        )
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'duplicate or case-colliding overlay destination'
    }

    Invoke-Test 'missing pin fails closed' {
        $candidate = Copy-Object $lock
        $candidate.inputs[0].asset.sha256 = $null
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'missing or placeholder'
    }

    Invoke-Test 'placeholder pin fails closed' {
        $candidate = Copy-Object $lock
        $candidate.inputs[0].identity.tag = 'TBD'
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'missing or placeholder'
    }

    Invoke-Test 'duplicate pin fails closed' {
        $candidate = Copy-Object $lock
        $candidate.inputs[1].asset.url = $candidate.inputs[0].asset.url
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'Duplicate input URL'
    }

    Invoke-Test 'immutable source identities stay on the approved forks' {
        $candidate = Copy-Object $lock
        $candidate.inputs[0].identity.repository = 'unapproved/example'
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'outside the immutable allowlist'

        $candidate = Copy-Object $lock
        $scanner = @($candidate.inputs | Where-Object id -eq 'fixed-pseudo-reloc-scanner')[0]
        $scanner.asset.url = $scanner.asset.url.Replace('/3356eec1411983cc252b04afac32bca5f3b8d824/', "/$('f' * 40)/")
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'unsafe or mismatched source path'
    }

    Invoke-Test 'unresolved lock blocks assembly' {
        Assert-Throws { Assert-PreviewLock -Lock $lock -RequireResolved } 'ncurses-runtime'
    }

    Invoke-Test 'removing a required unresolved slot fails closed' {
        $candidate = Copy-Object $lock
        $candidate.inputs = @($candidate.inputs | Where-Object id -ne 'bash')
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'must contain exactly one.*bash'
    }

    Invoke-Test 'native shell closure paths fail closed' {
        $candidate = Copy-Object $lock
        $candidate.nativeShellClosure += '../outside.exe'
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'path traversal'
        $candidate = Copy-Object $lock
        $candidate.nativeShellClosure += 'CMD/GIT.EXE'
        Assert-Throws { Assert-PreviewLock -Lock $candidate } 'unsafe or duplicate'
    }

    Invoke-Test 'cached size mismatch fails closed' {
        $cache = Join-Path $temporary 'cache'
        New-Item -ItemType Directory -Path $cache | Out-Null
        $entry = [pscustomobject]@{
            id = 'fixture'
            asset = [pscustomobject]@{
                name = 'fixture.bin'
                url = 'https://example.invalid/fixture.bin'
                expectedBytes = 2
                sha256 = 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb'
            }
        }
        [IO.File]::WriteAllBytes((Join-Path $cache 'fixture--fixture.bin'), [byte[]](0x61))
        Assert-Throws { Get-VerifiedInput -InputEntry $entry -CacheDirectory $cache } 'does not match'
    }

    Invoke-Test 'cached hash mismatch fails closed' {
        $cache = Join-Path $temporary 'hash-cache'
        New-Item -ItemType Directory -Path $cache | Out-Null
        $entry = [pscustomobject]@{
            id = 'fixture'
            asset = [pscustomobject]@{
                name = 'fixture.bin'
                url = 'https://example.invalid/fixture.bin'
                expectedBytes = 1
                sha256 = ('0' * 64)
            }
        }
        [IO.File]::WriteAllBytes((Join-Path $cache 'fixture--fixture.bin'), [byte[]](0x61))
        Assert-Throws { Get-VerifiedInput -InputEntry $entry -CacheDirectory $cache } 'does not match'
    }

    Invoke-Test 'archive traversal fails closed' {
        Assert-Throws { Assert-ArchiveMemberNames -Members @('../escape.dll') } 'path traversal'
        Assert-Throws { Assert-ArchiveMemberNames -Members @('safe/../../escape.dll') } 'path traversal'
        $root = Join-Path $temporary 'link-root'
        $link = Join-Path $root 'usr\bin\unsafe-link'
        Assert-Throws {
            Assert-LinkTargetSafe -LinkPath $link -LinkTarget '..\..\..\escape.dll' -Root $root
        } 'escapes root'
    }

    Invoke-Test 'archive links are contained complete and acyclic' {
        $safeMembers = @(
            [pscustomobject]@{ path = 'usr/lib/target.dll'; type = 'file'; target = $null },
            [pscustomobject]@{ path = 'usr/bin/alias.dll'; type = 'symlink'; target = '../lib/target.dll' },
            [pscustomobject]@{ path = 'usr/bin/hard.dll'; type = 'hardlink'; target = 'usr/lib/target.dll' }
        )
        Assert-ArchiveLinks -Members $safeMembers
        Assert-Throws {
            Assert-ArchiveLinks -Members @(
                [pscustomobject]@{ path = 'usr/bin/alias.dll'; type = 'symlink'; target = 'missing.dll' }
            )
        } 'targets missing member'
        Assert-Throws {
            Assert-ArchiveLinks -Members @(
                [pscustomobject]@{ path = 'usr/bin/a.dll'; type = 'symlink'; target = 'b.dll' },
                [pscustomobject]@{ path = 'usr/bin/b.dll'; type = 'symlink'; target = 'a.dll' }
            )
        } 'cyclic'
    }

    Invoke-Test 'archive collisions fail closed' {
        Assert-Throws { Assert-ArchiveMemberNames -Members @('usr/bin/Bash.exe', 'usr/bin/bash.exe') } 'case-colliding'
        Assert-Throws { Assert-ArchiveMemberNames -Members @('usr/bin/bash.exe', './usr/bin/bash.exe') } 'case-colliding'
        Assert-Throws { Assert-ArchiveMemberNames -Members @('usr/bin/name', 'usr/bin/name.') } 'distinct Windows path'
        Assert-Throws { Assert-ArchiveMemberNames -Members @('usr/bin/NUL.txt') } 'reserved Windows device'
    }

    Invoke-Test 'shared-root and alias paths are rejected' {
        Assert-Throws { Assert-PrivatePath -Path 'C:\msys64\preview' } 'prohibited shared root'
        Assert-Throws { Assert-PrivatePath -Path '\\?\C:\msys64\preview' } 'must not use UNC'
        Assert-Throws { Assert-PrivatePath -Path 'C:\MSYS64~1\preview' } 'short-name aliases'
    }

    Invoke-Test 'canonical directory manifest uses pinned CSV bytes' {
        $manifestRoot = Join-Path $temporary 'canonical-manifest'
        New-Item -ItemType Directory -Path $manifestRoot | Out-Null
        $manifestFile = Join-Path $manifestRoot 'a,b.txt'
        Set-Content -LiteralPath $manifestFile -Value 'x' -NoNewline -Encoding ascii
        (Get-Item -LiteralPath $manifestFile).LastWriteTimeUtc = [DateTime]'2026-01-01T00:00:00Z'
        $manifest = Get-CanonicalDirectoryManifest -Root $manifestRoot
        Assert-Equal 1 $manifest.files ''
        Assert-Equal 154 $manifest.bytes ''
        Assert-Equal 'b8520108bce421fa7fa2bbca48e851c41fa16792c75ee31814ce29be74317f7a' `
            $manifest.canonicalManifestSha256 ''
    }

    Invoke-Test 'PE architectures are classified' {
        $arm64 = Join-Path $temporary 'arm64.exe'
        $x64 = Join-Path $temporary 'x64.exe'
        $arm64ec = Join-Path $temporary 'arm64ec.exe'
        New-TestPe -Path $arm64 -Machine 0xAA64
        New-TestPe -Path $x64 -Machine 0x8664
        New-TestPe -Path $arm64ec -Machine 0xA641
        Assert-Equal 'arm64' (Get-PeArchitecture -Path $arm64) ''
        Assert-Equal 'x64' (Get-PeArchitecture -Path $x64) ''
        Assert-Equal 'arm64ec' (Get-PeArchitecture -Path $arm64ec) ''
    }

    Invoke-Test 'malformed PE fails closed' {
        $malformed = Join-Path $temporary 'malformed.exe'
        $bytes = [byte[]]::new(64)
        $bytes[0] = 0x4d
        $bytes[1] = 0x5a
        [BitConverter]::GetBytes([UInt32]4096).CopyTo($bytes, 0x3c)
        [IO.File]::WriteAllBytes($malformed, $bytes)
        Assert-Throws { Get-PeArchitecture -Path $malformed } 'Malformed PE'
    }

    Invoke-Test 'scanner failure propagates' {
        $scanner = Join-Path $temporary 'failing-scanner.ps1'
        @'
param($PePath, $OutputPath, $Objdump, $Nm)
exit 17
'@ | Set-Content -LiteralPath $scanner -Encoding utf8
        $objdump = Join-Path $temporary 'objdump.exe'
        $nm = Join-Path $temporary 'nm.exe'
        [IO.File]::WriteAllBytes($objdump, [byte[]](0))
        [IO.File]::WriteAllBytes($nm, [byte[]](0))
        $pe = Join-Path $temporary 'scanner-input.exe'
        New-TestPe -Path $pe -Machine 0xAA64
        Assert-Throws {
            Invoke-PseudoRelocScanner -ScannerPath $scanner -PePath $pe `
                -OutputPath (Join-Path $temporary 'scanner.json') `
                -ObjdumpPath $objdump -NmPath $nm
        } 'exit code 17'
    }

    Invoke-Test 'non-scalar64 pseudo-relocs fail closed' {
        $scanner = Join-Path $temporary 'width-scanner.ps1'
        @'
param($PePath, $OutputPath, $Objdump, $Nm)
@{ result = 'pass'; policy_violations = @(); flags = @(32) } |
    ConvertTo-Json | Set-Content -LiteralPath $OutputPath -Encoding utf8
'@ | Set-Content -LiteralPath $scanner -Encoding utf8
        $objdump = Join-Path $temporary 'width-objdump.exe'
        $nm = Join-Path $temporary 'width-nm.exe'
        [IO.File]::WriteAllBytes($objdump, [byte[]](0))
        [IO.File]::WriteAllBytes($nm, [byte[]](0))
        $pe = Join-Path $temporary 'width-input.exe'
        New-TestPe -Path $pe -Machine 0xAA64
        Assert-Throws {
            Invoke-PseudoRelocScanner -ScannerPath $scanner -PePath $pe `
                -OutputPath (Join-Path $temporary 'width.json') `
                -ObjdumpPath $objdump -NmPath $nm -RequireScalar64
        } 'non-scalar64'
    }

    Invoke-Test 'evidence completeness is enforced' {
        $ids = @(
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
        )
        $evidence = [pscustomobject]@{
            schemaVersion = 1
            previewId = 'fixture'
            machine = [pscustomobject]@{}
            processes = @()
            modules = @()
            tests = @($ids | ForEach-Object { [pscustomobject]@{ id = $_; passed = $true } })
            artifacts = @(
                [pscustomobject]@{ kind = 'lock' },
                [pscustomobject]@{ kind = 'provenance' },
                [pscustomobject]@{ kind = 'payload' }
            )
            result = 'pass'
        }
        Assert-EvidenceComplete -Evidence $evidence
        $evidence.tests = @($evidence.tests | Where-Object id -ne 'git-hook')
        Assert-Throws { Assert-EvidenceComplete -Evidence $evidence } 'git-hook'
    }

    Invoke-Test 'ARM smoke uses deterministic process and symlink probes' {
        $validatorSource = Get-Content -LiteralPath (Join-Path $scripts 'Validate-Arm64Preview.ps1') -Raw
        $diagnosticsSource = Get-Content -LiteralPath (
            Join-Path $scripts 'Collect-PreviewDiagnostics.ps1'
        ) -Raw
        Assert-Equal $true $validatorSource.Contains('end=$((SECONDS+1)); while ((SECONDS < end)); do :; done;') ''
        Assert-Equal $false $validatorSource.Contains('$end=$((SECONDS+1))') ''
        Assert-Equal $true $validatorSource.Contains('$info.RedirectStandardInput = $true') ''
        Assert-Equal $true $validatorSource.Contains("test -L 'space ü/link.txt'") ''
        Assert-Equal $true $validatorSource.Contains("winsymlinks:nativestrict") ''
        Assert-Equal $true $validatorSource.Contains('preview-evidence\source-lock.json') ''
        Assert-Equal $true $validatorSource.Contains('preview-evidence\bundle-lock.v1.json') ''
        Assert-Equal $false $validatorSource.Contains('preview-evidence\portable-git-arm64-preview.v1.json') ''
        Assert-Equal $true $validatorSource.Contains('-Mode Runtime') ''
        Assert-Equal $true $validatorSource.Contains('-StaticReport $staticReportPath') ''
        Assert-Equal $true $validatorSource.Contains(
            'Canonical bundle lock does not bind the runtime collector identity') ''
        Assert-Equal $true $validatorSource.Contains('tools\runtime-collector') ''
        Assert-Equal $true $validatorSource.Contains('Assert-PinnedRawValidationTools') ''
        Assert-Equal $true $validatorSource.Contains(
            'does not match its source lock') ''
        Assert-Equal $true $validatorSource.Contains(
            'Source lock is not authenticated by the canonical bundle lock') ''
        Assert-Equal $true $validatorSource.Contains(
            'Authoritative Runtime validator emitted an incomplete or non-passing report') ''
        Assert-Equal $true $diagnosticsSource.Contains('runtime-evidence.v1.json') ''
        Assert-Equal $true $diagnosticsSource.Contains('authoritative-runtime-report.v1.json') ''
        Assert-Equal $true $diagnosticsSource.Contains('$runtimeStatus = ''collector-failed''') ''
        Assert-Equal $true $diagnosticsSource.Contains('$runtimeStatus = ''validator-failed''') ''
        Assert-Equal $true $diagnosticsSource.Contains(
            'Runtime outputs are incomplete and have no preserved collector failure diagnostics') ''
    }

    Invoke-Test 'immutable artifact bindings are acyclic' {
        $assemblerSource = Get-Content -LiteralPath (Join-Path $scripts 'Assemble-Arm64Preview.ps1') -Raw
        $payloadSchema = Get-Content -LiteralPath (
            Join-Path $PSScriptRoot '..\schemas\payload-manifest.schema.json'
        ) -Raw
        Assert-Equal $true $assemblerSource.Contains('lockSha256 = Get-Sha256 -Path $bundleLockPath') ''
        Assert-Equal $true $assemblerSource.Contains('provenanceSha256 = Get-Sha256 -Path $ProvenancePath') ''
        Assert-Equal $false $assemblerSource.Contains('payloadSha256 =') ''
        Assert-Equal $false $assemblerSource.Contains('Get-PeArchitecture') ''
        Assert-Equal $true $assemblerSource.Contains('pseudoReloc = [ordered]@{ candidates = $pseudoRelocCandidates }') ''
        Assert-Equal $false $assemblerSource.Contains('Invoke-PseudoRelocScanner -') ''
        Assert-Equal $false $assemblerSource.Contains('[string] $AuthoritativeValidatorPath') ''
        Assert-Equal $true $assemblerSource.Contains(
            '(Get-Sha256 -Path $authoritativeValidatorPath) -cne') ''
        Assert-Equal $true $assemblerSource.Contains(
            'Authoritative validator modified an immutable input artifact') ''
        Assert-Equal $true $assemblerSource.Contains(
            'Authoritative validator modified an immutable validation tool') ''
        Assert-Equal $true $assemblerSource.Contains(
            'Shared C:\msys64 Git cannot be used by the assembler') ''
        Assert-Equal $true $assemblerSource.Contains('GetFinalPathNameByHandle') ''
        Assert-Equal $true $assemblerSource.Contains(
            '^(?i)(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)') ''
        Assert-Equal $true $assemblerSource.Contains(
            'Materialized payload occupies the reserved preview-evidence subtree') ''
        Assert-Equal $true $assemblerSource.Contains(
            'Validation input destination collides with an existing path') ''
        Assert-Equal $true $assemblerSource.Contains('''enumerate-database-manifest''') ''
        Assert-Equal $true $assemblerSource.Contains('''hash-database-manifest''') ''
        Assert-Equal $true $assemblerSource.Contains('''hash-package-log''') ''
        Assert-Equal $true $assemblerSource.Contains('''stat-package-log''') ''
        Assert-Equal $false $payloadSchema.Contains('"architecture"') ''
        Assert-Equal $false $payloadSchema.Contains('"sourceInput"') ''
        Assert-Equal $false $payloadSchema.Contains('"sourcePackage"') ''
    }

    Invoke-Test 'assembler lock-only entry point is deliberately blocked' {
        $output = Join-Path $temporary 'output'
        $cache = Join-Path $temporary 'entry-cache'
        $work = Join-Path $temporary 'work'
        $json = @(& pwsh -NoLogo -NoProfile -File (Join-Path $scripts 'Assemble-Arm64Preview.ps1') `
            -LockPath $lockPath -OutputRoot $output -CacheDirectory $cache `
            -WorkDirectory $work -ValidateLockOnly 2>&1)
        Assert-Equal 2 $LASTEXITCODE 'Unresolved required pins must use a distinct blocked exit.'
        $result = ($json -join [Environment]::NewLine) | ConvertFrom-Json
        Assert-Equal $false $result.ready ''
        Assert-Equal 4 @($result.unresolved).Count ''
    }
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force -Recurse
    }
}
Write-Host "$script:passed targeted preview tests passed."
