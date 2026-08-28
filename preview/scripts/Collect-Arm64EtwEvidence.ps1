[CmdletBinding()]
param(
    [string] $PortableRoot,
    [ValidateSet('Preview', 'Final')][string] $AdmissionMode,
    [string] $LockPath,
    [string] $ProvenancePath,
    [string] $PayloadManifestPath,
    [string] $AssemblyEvidencePath,
    [string] $StaticReportPath,
    [string] $ValidatorCommit,
    [string] $ValidatorRoot,
    [string] $OutputPath,
    [switch] $LibraryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ScenarioOrder = @('Git Bash', 'Git', 'SSH', 'GPG', 'hook', 'submodule', 'rebase', 'git-svn')
$script:ScenarioOperations = [ordered]@{
    'Git Bash' = 'git-bash-startup'
    Git = 'git-command'
    SSH = 'ssh-command'
    GPG = 'gpg-command'
    hook = 'git-hook'
    submodule = 'git-submodule'
    rebase = 'git-rebase'
    'git-svn' = 'git-svn'
}
$script:ScenarioCommandContracts = [ordered]@{
    'Git Bash' = [ordered]@{ suffix = 'usr\bin\bash.exe'; args = @('--noprofile', '--norc', '-lc', 'exit 0') }
    Git = [ordered]@{ suffix = 'bin\git.exe'; args = @('--version') }
    SSH = [ordered]@{ suffix = 'usr\bin\ssh.exe'; args = @('-V') }
    GPG = [ordered]@{ suffix = 'usr\bin\gpg.exe'; args = @('--version') }
    hook = [ordered]@{ suffix = 'usr\bin\bash.exe'; args = @('--noprofile', '--norc', '-lc', 'exit 0') }
    submodule = [ordered]@{ suffix = 'bin\git.exe'; args = @('submodule', 'status', '--recursive') }
    rebase = [ordered]@{ suffix = 'usr\bin\bash.exe'; args = @('--noprofile', '--norc', '-lc', 'git rebase --show-current-patch') }
    'git-svn' = [ordered]@{ suffix = 'usr\bin\bash.exe'; args = @('--noprofile', '--norc', '-lc', 'git svn --version') }
}
$script:KernelProcessProvider = '22fb2cd6-0e7b-422b-a0c7-2fad1fd0e716'

function Get-EtwSha256 {
    param([Parameter(Mandatory)][string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-EtwOrdinalStrings {
    param([AllowEmptyCollection()][string[]] $Values)
    $result = [string[]]@($Values)
    [Array]::Sort($result, [StringComparer]::Ordinal)
    return @($result)
}

function Test-EtwOrdinalEqual {
    param($Left, $Right)
    return [string]::Equals([string]$Left, [string]$Right, [StringComparison]::Ordinal)
}

function Test-EtwOrdinalIgnoreCaseEqual {
    param($Left, $Right)
    return [string]::Equals(
        [string]$Left, [string]$Right, [StringComparison]::OrdinalIgnoreCase)
}

function Test-EtwOrdinalIn {
    param($Value, [string[]]$Allowed)
    foreach ($candidate in $Allowed) {
        if (Test-EtwOrdinalEqual $Value $candidate) { return $true }
    }
    return $false
}

function Test-EtwOrdinalSequence {
    param($Actual, $Expected)
    $actualItems = @($Actual)
    $expectedItems = @($Expected)
    if ($actualItems.Count -ne $expectedItems.Count) { return $false }
    for ($index = 0; $index -lt $actualItems.Count; $index++) {
        if (-not (Test-EtwOrdinalEqual $actualItems[$index] $expectedItems[$index])) {
            return $false
        }
    }
    return $true
}

function Get-EtwEventKindRank {
    param([Parameter(Mandatory)][string] $Kind)
    if (Test-EtwOrdinalEqual $Kind 'start') { return 0 }
    if (Test-EtwOrdinalEqual $Kind 'image') { return 1 }
    if (Test-EtwOrdinalEqual $Kind 'stop') { return 2 }
    throw "Trace contains an invalid event kind: $Kind"
}

function Get-EtwSortedEvents {
    param([Parameter(Mandatory)] $Events)
    $indexed = [object[]]@(
        for ($index = 0; $index -lt @($Events).Count; $index++) {
            [pscustomobject]@{ event = @($Events)[$index]; index = $index }
        }
    )
    [Array]::Sort($indexed, [Comparison[object]] {
            param($left, $right)
            $result = [DateTimeOffset]::Compare(
                [DateTimeOffset]::Parse([string]$left.event.timestamp),
                [DateTimeOffset]::Parse([string]$right.event.timestamp))
            if ($result -eq 0) {
                $result = (Get-EtwEventKindRank $left.event.kind).CompareTo(
                    (Get-EtwEventKindRank $right.event.kind))
            }
            if ($result -eq 0) { $result = $left.index.CompareTo($right.index) }
            return $result
        })
    return @($indexed | ForEach-Object event)
}

function ConvertTo-EtwUtc {
    param([Parameter(Mandatory)] $Value)
    if ($Value -is [DateTimeOffset]) {
        return $Value.ToUniversalTime().ToString(
            'yyyy-MM-ddTHH:mm:ss.fffffffZ', [Globalization.CultureInfo]::InvariantCulture)
    }
    return ([DateTimeOffset]::Parse(
        [string]$Value,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
    ).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'))
}

function Get-XmlChildText {
    param([Parameter(Mandatory)][System.Xml.XmlNode] $Node, [Parameter(Mandatory)][string] $Name)
    $child = @($Node.ChildNodes | Where-Object {
            Test-EtwOrdinalEqual $_.LocalName $Name
        } | Select-Object -First 1)
    if ($child.Count -eq 0) { return $null }
    return [string]$child[0].InnerText
}

function Get-EtwDataMap {
    param([Parameter(Mandatory)][System.Xml.XmlNode] $EventNode)
    $map = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($data in @($EventNode.SelectNodes(".//*[local-name()='Data']"))) {
        $name = $data.GetAttribute('Name')
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            $map[$name] = [string]$data.InnerText
        }
    }
    return $map
}

function Get-EtwDataValue {
    param(
        [Parameter(Mandatory)][Collections.Generic.Dictionary[string, string]] $Map,
        [Parameter(Mandatory)][string[]] $Names
    )
    foreach ($name in $Names) {
        if ($Map.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($Map[$name])) {
            return $Map[$name]
        }
    }
    return $null
}

function ConvertFrom-EtwInteger {
    param([Parameter(Mandatory)][string] $Value, [Parameter(Mandatory)][string] $Field)
    [long]$parsed = 0
    if ($Value -match '^0[xX]([0-9a-fA-F]+)$') {
        try { return [Convert]::ToInt64($Matches[1], 16) }
        catch { throw "ETW field '$Field' is outside its valid integer range" }
    }
    if (-not [long]::TryParse($Value, [Globalization.NumberStyles]::Integer,
            [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        throw "ETW field '$Field' is not an invariant integer"
    }
    return $parsed
}

function Get-TracerptLostEvents {
    param([Parameter(Mandatory)][string] $SummaryPath)
    if (-not (Test-Path -LiteralPath $SummaryPath -PathType Leaf)) {
        throw "tracerpt summary is missing: $SummaryPath"
    }
    $summary = Get-Content -LiteralPath $SummaryPath -Raw
    $matches = [regex]::Matches(
        $summary, '(?im)^\s*Total Events Lost\s*:?\s*([0-9]+)\s*$')
    if ($matches.Count -ne 1) {
        throw "tracerpt summary does not contain exactly one Total Events Lost field"
    }
    [long]$lost = 0
    if (-not [long]::TryParse(
            $matches[0].Groups[1].Value,
            [Globalization.NumberStyles]::Integer,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$lost)) {
        throw "tracerpt summary has an unreadable Total Events Lost value"
    }
    if ($lost -ne 0) { throw "Trace reports lost events: $lost" }
    return $lost
}

function ConvertFrom-TracerptXml {
    param(
        [Parameter(Mandatory)][string[]] $Path,
        [Parameter(Mandatory)][long] $LostEvents
    )
    if ($LostEvents -ne 0) { throw "Trace reports lost events: $LostEvents" }
    $documents = @()
    foreach ($item in $Path) {
        if (-not (Test-Path -LiteralPath $item -PathType Leaf)) {
            throw "tracerpt output is missing: $item"
        }
        try { $documents += [xml](Get-Content -LiteralPath $item -Raw) }
        catch { throw "Unable to parse tracerpt XML '$item': $($_.Exception.Message)" }
    }
    $events = [Collections.Generic.List[object]]::new()
    foreach ($document in $documents) {
        foreach ($eventNode in @($document.SelectNodes("//*[local-name()='Event']"))) {
            $system = @($eventNode.ChildNodes | Where-Object {
                    Test-EtwOrdinalEqual $_.LocalName 'System'
                } | Select-Object -First 1)
            if ($system.Count -eq 0) { continue }
            $provider = @($system[0].ChildNodes | Where-Object {
                    Test-EtwOrdinalEqual $_.LocalName 'Provider'
                } | Select-Object -First 1)
            if ($provider.Count -eq 0) { continue }
            $guid = ([string]$provider[0].GetAttribute('Guid')).Trim('{}').ToLowerInvariant()
            $providerName = [string]$provider[0].GetAttribute('Name')
            if (-not (Test-EtwOrdinalEqual $guid $script:KernelProcessProvider) -and
                -not (Test-EtwOrdinalEqual $providerName 'Microsoft-Windows-Kernel-Process')) {
                continue
            }
            $eventIdText = Get-XmlChildText -Node $system[0] -Name 'EventID'
            [int]$eventId = 0
            if (-not [int]::TryParse($eventIdText, [ref]$eventId)) {
                throw "Kernel Process event has no numeric EventID"
            }
            if ($eventId -notin @(1, 2, 5)) { continue }
            $timeNode = @($system[0].ChildNodes | Where-Object {
                    Test-EtwOrdinalEqual $_.LocalName 'TimeCreated'
                } | Select-Object -First 1)
            if ($timeNode.Count -eq 0 -or [string]::IsNullOrWhiteSpace($timeNode[0].GetAttribute('SystemTime'))) {
                throw "Kernel Process event $eventId has no timestamp"
            }
            $map = Get-EtwDataMap -EventNode $eventNode
            $pidText = Get-EtwDataValue -Map $map -Names @('ProcessID', 'ProcessId')
            $eventProcessId64 = ConvertFrom-EtwInteger $pidText 'ProcessID'
            if ($eventProcessId64 -le 0 -or $eventProcessId64 -gt [int]::MaxValue) {
                throw "Kernel Process event $eventId has no valid process ID"
            }
            [int]$eventProcessId = $eventProcessId64
            $kind = switch ($eventId) { 1 { 'start' } 2 { 'stop' } 5 { 'image' } }
            $record = [ordered]@{
                kind = $kind
                processId = $eventProcessId
                timestamp = ConvertTo-EtwUtc $timeNode[0].GetAttribute('SystemTime')
                parentProcessId = $null
                imagePath = $null
            }
            if (Test-EtwOrdinalEqual $kind 'start') {
                $parentText = Get-EtwDataValue -Map $map -Names @('ParentProcessID', 'ParentProcessId')
                $parent64 = ConvertFrom-EtwInteger $parentText 'ParentProcessID'
                if ($parent64 -lt 0 -or $parent64 -gt [int]::MaxValue) {
                    throw "Process start event for PID $eventProcessId has no valid parent process ID"
                }
                $record.parentProcessId = [int]$parent64
                $record.imagePath = Get-EtwDataValue -Map $map -Names @('ImageName', 'ImageFileName', 'FileName')
            }
            elseif (Test-EtwOrdinalEqual $kind 'image') {
                $record.imagePath = Get-EtwDataValue -Map $map -Names @('ImageName', 'ImageFileName', 'FileName')
                if ([string]::IsNullOrWhiteSpace($record.imagePath)) {
                    throw "Image-load event for PID $eventProcessId has no image path"
                }
            }
            $events.Add([pscustomobject]$record)
        }
    }
    if (@($events | Where-Object { Test-EtwOrdinalEqual $_.kind 'start' }).Count -eq 0) {
        throw "Trace has no process start events"
    }
    if (@($events | Where-Object { Test-EtwOrdinalEqual $_.kind 'stop' }).Count -eq 0) {
        throw "Trace has no process stop events"
    }
    if (@($events | Where-Object { Test-EtwOrdinalEqual $_.kind 'image' }).Count -eq 0) {
        throw "Trace has no image-load events"
    }
    return [pscustomobject]@{ lostEvents = 0; events = @(Get-EtwSortedEvents $events) }
}

function Get-PeImportNames {
    param([Parameter(Mandatory)][string] $Path)
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5a4d) { throw "Not a PE image: $Path" }
        $stream.Position = 0x3c
        $peOffset = $reader.ReadUInt32()
        if ($peOffset -gt $stream.Length - 24) { throw "Malformed PE image: $Path" }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x4550) { throw "Malformed PE image: $Path" }
        $null = $reader.ReadUInt16()
        $sectionCount = $reader.ReadUInt16()
        $stream.Position += 12
        $optionalSize = $reader.ReadUInt16()
        $stream.Position += 2
        $optionalStart = $stream.Position
        if ($optionalSize -lt 112 -or $optionalStart + $optionalSize -gt $stream.Length) {
            throw "Malformed PE optional header: $Path"
        }
        $magic = $reader.ReadUInt16()
        $directoryOffset = switch ($magic) { 0x20b { 112 } 0x10b { 96 } default { throw "Unknown PE format: $Path" } }
        if ($optionalSize -lt $directoryOffset + 16) { throw "PE has no import directory: $Path" }
        $stream.Position = $optionalStart + $directoryOffset + 8
        $importRva = $reader.ReadUInt32()
        $importSize = $reader.ReadUInt32()
        $sectionStart = $optionalStart + $optionalSize
        $sections = @()
        for ($i = 0; $i -lt $sectionCount; $i++) {
            $stream.Position = $sectionStart + (40 * $i) + 8
            $virtualSize = $reader.ReadUInt32()
            $virtualAddress = $reader.ReadUInt32()
            $rawSize = $reader.ReadUInt32()
            $rawPointer = $reader.ReadUInt32()
            $sections += [pscustomobject]@{
                va = [uint32]$virtualAddress
                size = [uint32][Math]::Max($virtualSize, $rawSize)
                raw = [uint32]$rawPointer
            }
        }
        function Convert-Rva([uint32]$Rva) {
            foreach ($section in $sections) {
                if ($Rva -ge $section.va -and [uint64]$Rva -lt ([uint64]$section.va + $section.size)) {
                    return [uint64]$section.raw + ($Rva - $section.va)
                }
            }
            throw "PE RVA 0x$($Rva.ToString('x')) is outside its sections: $Path"
        }
        if (($importRva -eq 0) -xor ($importSize -eq 0)) { throw "Malformed PE import directory: $Path" }
        if ($importRva -eq 0) { return @() }
        $descriptorOffset = Convert-Rva $importRva
        $imports = [Collections.Generic.List[string]]::new()
        for ($i = 0; $i -lt 4096; $i++) {
            $stream.Position = $descriptorOffset + (20 * $i)
            if ($stream.Position + 20 -gt $stream.Length) { throw "Truncated PE import table: $Path" }
            $originalThunk = $reader.ReadUInt32()
            $time = $reader.ReadUInt32()
            $forward = $reader.ReadUInt32()
            $nameRva = $reader.ReadUInt32()
            $firstThunk = $reader.ReadUInt32()
            if (($originalThunk -bor $time -bor $forward -bor $nameRva -bor $firstThunk) -eq 0) { return @($imports) }
            if ($nameRva -eq 0) { throw "PE import has no name: $Path" }
            $stream.Position = Convert-Rva $nameRva
            $bytes = [Collections.Generic.List[byte]]::new()
            while ($bytes.Count -lt 1024) {
                if ($stream.Position -ge $stream.Length) { throw "Truncated PE import name: $Path" }
                $value = $reader.ReadByte()
                if ($value -eq 0) { break }
                $bytes.Add($value)
            }
            if ($bytes.Count -eq 1024) { throw "Overlong PE import name: $Path" }
            $imports.Add([Text.Encoding]::ASCII.GetString($bytes.ToArray()))
        }
        throw "PE import table is not terminated: $Path"
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Get-EtwPersonality {
    param([Parameter(Mandatory)][string] $Path, [Parameter(Mandatory)][string] $WindowsRoot)
    if ($Path.StartsWith($WindowsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { return 'Native' }
    $fileName = [IO.Path]::GetFileName($Path)
    if ((Test-EtwOrdinalIgnoreCaseEqual $fileName 'cygwin1.dll') -or
        [regex]::IsMatch(
            $fileName,
            '^cyg[^\\]*-[0-9]+\.dll$',
            [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
                [Text.RegularExpressions.RegexOptions]::CultureInvariant)) {
        return 'Cygwin'
    }
    $imports = @(Get-PeImportNames -Path $Path)
    if (@($imports | Where-Object {
                Test-EtwOrdinalIgnoreCaseEqual $_ 'cygwin1.dll'
            }).Count -ne 0) { return 'Cygwin' }
    if (@($imports | Where-Object {
                Test-EtwOrdinalIgnoreCaseEqual $_ 'msys-2.0.dll'
            }).Count -ne 0) { return 'MSYS' }
    return 'MinGW'
}

function Get-EtwArchitecture {
    param(
        [Parameter(Mandatory)][string] $Path,
        [string] $WindowsRoot
    )
    $architecture = Get-PeArchitecture -Path $Path
    $underWindows = -not [string]::IsNullOrWhiteSpace($WindowsRoot) -and
        [IO.Path]::GetFullPath($Path).StartsWith(
            [IO.Path]::GetFullPath($WindowsRoot).TrimEnd('\') + '\',
            [StringComparison]::OrdinalIgnoreCase)
    if (($underWindows -and -not (Test-EtwOrdinalIn $architecture @('arm64', 'arm64ec', 'arm64x'))) -or
        (-not $underWindows -and -not (Test-EtwOrdinalEqual $architecture 'arm64'))) {
        throw "ETW image is not native ARM64 ('$architecture'): $Path"
    }
    return 'ARM64'
}

function Get-EtwPayloadHashes {
    param(
        [Parameter(Mandatory)] $Entries,
        [Parameter(Mandatory)][string] $PortableRoot
    )
    $root = [IO.Path]::GetFullPath($PortableRoot).TrimEnd('\')
    $entryPaths = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    $payloadHashes = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in @($Entries)) {
        if (-not (Test-EtwOrdinalIn $entry.type @('file', 'hardlink', 'directory', 'symlink'))) {
            throw "Payload manifest contains an invalid ordinal entry type: $($entry.type)"
        }
        $entryPath = [IO.Path]::GetFullPath(
            (Join-Path $root ([string]$entry.path).Replace('/', '\')))
        if (-not $entryPath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) -or
            -not $entryPaths.Add($entryPath)) {
            throw "Payload manifest contains an unsafe or duplicate path: $($entry.path)"
        }
        if (-not (Test-EtwOrdinalIn $entry.type @('file', 'hardlink'))) { continue }
        if ([string]$entry.sha256 -cnotmatch '^[0-9a-f]{64}$') {
            throw "Payload manifest entry has no immutable hash: $($entry.path)"
        }
        if (-not $payloadHashes.TryAdd($entryPath, [string]$entry.sha256)) {
            throw "Payload manifest contains a duplicate hashed path: $($entry.path)"
        }
    }
    return $payloadHashes
}

function Get-EtwValidatorBinding {
    param(
        [Parameter(Mandatory)] $SourceLock,
        [Parameter(Mandatory)] $BundleLock,
        [Parameter(Mandatory)][string] $ValidatorCommit
    )
    $sourceInputs = @($SourceLock.inputs | Where-Object {
            Test-EtwOrdinalEqual $_.role 'authoritative-validator-main'
        })
    if ($sourceInputs.Count -ne 1) {
        throw "Source lock must identify exactly one authoritative validator main input"
    }
    $sourceInput = $sourceInputs[0]
    $bundleInputs = @($BundleLock.inputs | Where-Object {
            Test-EtwOrdinalEqual $_.id $sourceInput.id
        })
    if ($bundleInputs.Count -ne 1) {
        throw "Canonical lock must bind the exact authoritative validator input ID"
    }
    $bundleInput = $bundleInputs[0]
    if (-not (Test-EtwOrdinalEqual $sourceInput.status 'resolved') -or
        -not (Test-EtwOrdinalEqual $sourceInput.identity.repository 'crutkas/build-extra') -or
        -not (Test-EtwOrdinalEqual $sourceInput.identity.commit $ValidatorCommit) -or
        -not (Test-EtwOrdinalEqual $sourceInput.identity.sourcePath 'validate-arm64-bundle.ps1') -or
        -not (Test-EtwOrdinalEqual $bundleInput.role 'validation-tool') -or
        -not (Test-EtwOrdinalEqual $bundleInput.status 'resolved') -or
        -not (Test-EtwOrdinalEqual $bundleInput.resolution.method 'github-raw-commit') -or
        -not (Test-EtwOrdinalEqual $bundleInput.release.repository $sourceInput.identity.repository) -or
        -not (Test-EtwOrdinalEqual $bundleInput.release.targetCommit $sourceInput.identity.commit) -or
        -not (Test-EtwOrdinalEqual $bundleInput.release.sourcePath $sourceInput.identity.sourcePath) -or
        -not (Test-EtwOrdinalEqual $bundleInput.asset.url $sourceInput.asset.url) -or
        [Int64]$bundleInput.asset.bytes -ne [Int64]$sourceInput.asset.expectedBytes -or
        -not (Test-EtwOrdinalEqual $bundleInput.asset.sha256 $sourceInput.asset.sha256)) {
        throw "Canonical lock does not bind the exact source-lock validator identity"
    }
    return $bundleInput
}

function Assert-NotSharedRoot {
    param([Parameter(Mandatory)][string] $Path)
    $expanded = $Path -replace '^\\\\\?\\', '' -replace '^\\\?\?\\', ''
    if ($expanded -match '^(?i)C:\\msys64(?:\\|$)') {
        throw "C:\msys64 is prohibited as an evidence input or output: $Path"
    }
}

function Initialize-EtwNativeApi {
    if ('Arm64EtwNative' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class Arm64EtwNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct JobAccounting {
        public long TotalUserTime, TotalKernelTime, ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount, TotalProcesses, ActiveProcesses, TotalTerminatedProcesses;
    }

    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr security,
        uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern uint GetFinalPathNameByHandle(IntPtr handle, StringBuilder path, uint length, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern uint QueryDosDevice(string deviceName, StringBuilder targetPath, int maxLength);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool QueryInformationJobObject(IntPtr job, int infoClass, out JobAccounting info,
        int infoLength, IntPtr returnLength);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool TerminateJobObject(IntPtr job, uint exitCode);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr handle);
}
'@
}

function ConvertFrom-NtImagePath {
    param([Parameter(Mandatory)][string] $Path)
    if ($Path -notmatch '^(?i)\\Device\\') { return $Path }
    Initialize-EtwNativeApi
    foreach ($drive in [IO.DriveInfo]::GetDrives()) {
        $name = $drive.Name.Substring(0, 2)
        $target = [Text.StringBuilder]::new(32768)
        if ([Arm64EtwNative]::QueryDosDevice($name, $target, $target.Capacity) -eq 0) { continue }
        $device = $target.ToString()
        if ($Path.Equals($device, [StringComparison]::OrdinalIgnoreCase) -or
            $Path.StartsWith($device + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return $name + $Path.Substring($device.Length)
        }
    }
    throw "ETW reported an unmappable NT image path: $Path"
}

function Get-FinalEtwPath {
    param(
        [Parameter(Mandatory)][string] $Path,
        [switch] $Directory
    )
    Initialize-EtwNativeApi
    $flags = if ($Directory) { 0x02000000 } else { 0 }
    $handle = [Arm64EtwNative]::CreateFile($Path, 0, 7, [IntPtr]::Zero, 3, $flags, [IntPtr]::Zero)
    if ($handle -eq [IntPtr](-1)) { throw "Unable to open ETW image path: $Path" }
    try {
        $buffer = [Text.StringBuilder]::new(32768)
        $length = [Arm64EtwNative]::GetFinalPathNameByHandle($handle, $buffer, $buffer.Capacity, 0)
        if ($length -eq 0 -or $length -ge $buffer.Capacity) {
            throw "Unable to resolve final ETW image path: $Path"
        }
        return ($buffer.ToString() -replace '^\\\\\?\\', '')
    }
    finally {
        $null = [Arm64EtwNative]::CloseHandle($handle)
    }
}

function Resolve-EtwImagePath {
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $WindowsRoot
    )
    $candidate = $Path.Trim().Trim('"')
    $candidate = $candidate -replace '^\\\\\?\\', '' -replace '^\\\?\?\\', ''
    $candidate = ConvertFrom-NtImagePath $candidate
    if ($candidate -match '^(?i)\\SystemRoot\\') {
        $candidate = Join-Path $WindowsRoot $candidate.Substring(12)
    }
    if (-not [IO.Path]::IsPathFullyQualified($candidate)) {
        throw "ETW reported a non-absolute image path: $Path"
    }
    Assert-NotSharedRoot $candidate
    try { $resolved = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path }
    catch { throw "ETW image path is unreadable: $candidate" }
    $resolved = [IO.Path]::GetFullPath((Get-FinalEtwPath $resolved)).TrimEnd('\')
    $root = [IO.Path]::GetFullPath($PortableRoot).TrimEnd('\')
    $windows = [IO.Path]::GetFullPath($WindowsRoot).TrimEnd('\')
    $underPortable = $resolved.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)
    $underWindows = $resolved.Equals($windows, [StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($windows + '\', [StringComparison]::OrdinalIgnoreCase)
    if (-not ($underPortable -or $underWindows)) {
        throw "ETW image path escapes the portable and Windows roots: $resolved"
    }
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "ETW image is not a readable file: $resolved"
    }
    return $resolved
}

function ConvertTo-EtwProcessTree {
    param(
        [Parameter(Mandatory)] $ParsedTrace,
        [Parameter(Mandatory)][int] $RootProcessId,
        [Parameter(Mandatory)][DateTimeOffset] $RootStartedAfterUtc,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $WindowsRoot,
        [Parameter(Mandatory)][ValidateSet('MSYS', 'MinGW')][string] $ExpectedRolePersonality,
        $PayloadHashes
    )
    $instances = [Collections.Generic.List[object]]::new()
    $active = @{}
    foreach ($event in @(Get-EtwSortedEvents $ParsedTrace.events)) {
        $at = [DateTimeOffset]::Parse($event.timestamp)
        if (Test-EtwOrdinalEqual $event.kind 'start') {
            $key = [string]$event.processId
            $parent = $null
            if ($active.ContainsKey([string]$event.parentProcessId)) {
                $parent = $active[[string]$event.parentProcessId]
            }
            $instance = [pscustomobject]@{
                instanceId = ('{0}-{1:x16}' -f $event.processId, $at.UtcTicks)
                processId = [int]$event.processId
                parentCandidate = $parent
                start = $at
                stop = $null
                startImage = [string]$event.imagePath
                imageEvents = [Collections.Generic.List[object]]::new()
            }
            $instances.Add($instance)
            $active[$key] = $instance
        }
        elseif (Test-EtwOrdinalEqual $event.kind 'image') {
            $key = [string]$event.processId
            if ($active.ContainsKey($key)) {
                $active[$key].imageEvents.Add([pscustomobject]@{ at = $at; path = [string]$event.imagePath })
            }
        }
        else {
            $key = [string]$event.processId
            if (-not $active.ContainsKey($key)) {
                # The provider can report stops for processes that predate this short trace.
                continue
            }
            $active[$key].stop = $at
            $active.Remove($key)
        }
    }
    $root = @($instances | Where-Object {
            $_.processId -eq $RootProcessId -and $_.start -ge $RootStartedAfterUtc
        } | Sort-Object start | Select-Object -First 1)
    if ($root.Count -ne 1) { throw "Trace does not contain the designated role process start" }
    $included = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $null = $included.Add($root[0].instanceId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($instance in $instances) {
            if ($null -ne $instance.parentCandidate -and
                $included.Contains($instance.parentCandidate.instanceId) -and
                $included.Add($instance.instanceId)) {
                $changed = $true
            }
        }
    }
    $tree = @($instances | Where-Object { $included.Contains($_.instanceId) } | Sort-Object start)
    foreach ($instance in $tree) {
        if ($null -eq $instance.stop) { throw "Incomplete descendant: PID $($instance.processId) has no process stop event" }
        if ($instance.imageEvents.Count -eq 0) {
            throw "Incomplete descendant: PID $($instance.processId) has no image-load event"
        }
    }
    $result = @()
    foreach ($instance in $tree) {
        $modulePaths = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($image in $instance.imageEvents) {
            $resolved = Resolve-EtwImagePath -Path $image.path -PortableRoot $PortableRoot -WindowsRoot $WindowsRoot
            if (-not $modulePaths.TryAdd($resolved, $resolved)) {
                throw "Duplicate image-load event for PID $($instance.processId): $resolved"
            }
        }
        $processPath = $null
        if (-not [string]::IsNullOrWhiteSpace($instance.startImage) -and
            [IO.Path]::IsPathFullyQualified(($instance.startImage -replace '^\\\\\?\\', ''))) {
            $processPath = Resolve-EtwImagePath $instance.startImage $PortableRoot $WindowsRoot
        }
        if ($null -eq $processPath) {
            $leaf = [IO.Path]::GetFileName($instance.startImage)
            $processPath = @($modulePaths.Values | Where-Object {
                    Test-EtwOrdinalIgnoreCaseEqual ([IO.Path]::GetFileName($_)) $leaf
                })
            if ($processPath.Count -ne 1) {
                throw "No process image-load event matches PID $($instance.processId)"
            }
            $processPath = [string]$processPath[0]
        }
        if (-not $modulePaths.ContainsKey($processPath)) {
            throw "Process image for PID $($instance.processId) is absent from image-load events"
        }
        $architecture = Get-EtwArchitecture $processPath $WindowsRoot
        $personality = Get-EtwPersonality $processPath $WindowsRoot
        if (Test-EtwOrdinalEqual $personality 'Cygwin') {
            throw "Cygwin personality is prohibited: $processPath"
        }
        $modules = @()
        foreach ($modulePath in @(Get-EtwOrdinalStrings -Values @($modulePaths.Values))) {
            $moduleArchitecture = Get-EtwArchitecture $modulePath $WindowsRoot
            $modulePersonality = Get-EtwPersonality $modulePath $WindowsRoot
            if (Test-EtwOrdinalEqual $modulePersonality 'Cygwin') {
                throw "Cygwin personality is prohibited: $modulePath"
            }
            $moduleHash = Get-EtwSha256 $modulePath
            if ($null -ne $PayloadHashes -and
                $modulePath.StartsWith($PortableRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                if (-not $PayloadHashes.ContainsKey($modulePath) -or
                    -not (Test-EtwOrdinalEqual $PayloadHashes[$modulePath] $moduleHash)) {
                    throw "ETW image is not bound to the immutable payload manifest: $modulePath"
                }
            }
            $modules += [ordered]@{
                path = $modulePath
                sha256 = $moduleHash
                architecture = $moduleArchitecture
                personality = $modulePersonality
            }
        }
        $isRoot = Test-EtwOrdinalEqual $instance.instanceId $root[0].instanceId
        if ($isRoot -and -not (Test-EtwOrdinalEqual $personality $ExpectedRolePersonality)) {
            throw "Role personality is '$personality', expected '$ExpectedRolePersonality'"
        }
        $result += [ordered]@{
            instanceId = $instance.instanceId
            parentInstanceId = if ($isRoot) { $null } else { $instance.parentCandidate.instanceId }
            processId = $instance.processId
            startUtc = ConvertTo-EtwUtc $instance.start
            endUtc = ConvertTo-EtwUtc $instance.stop
            role = if ($isRoot) { 'role' } else { 'support' }
            path = $processPath
            sha256 = Get-EtwSha256 $processPath
            architecture = $architecture
            personality = $personality
            modulesComplete = $true
            modules = $modules
        }
    }
    return @($result)
}

function Assert-RuntimeEvidenceShape {
    param(
        [Parameter(Mandatory)] $Evidence,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $ValidatorPath
    )
    $Evidence = $Evidence | ConvertTo-Json -Depth 30 | ConvertFrom-Json -DateKind String
    $portableRootPath = [IO.Path]::GetFullPath($PortableRoot).TrimEnd('\')
    $canonicalValidatorPath = [IO.Path]::GetFullPath($ValidatorPath)
    function Assert-ClosedObject($Object, [string[]]$Fields, [string]$Name) {
        $actualFields = @($Object.PSObject.Properties.Name)
        if ($actualFields.Count -ne $Fields.Count) {
            throw "Runtime evidence has an open or incomplete shape: $Name"
        }
        $allowedFields = [Collections.Generic.HashSet[string]]::new(
            $Fields, [StringComparer]::Ordinal)
        foreach ($actualField in $actualFields) {
            if (-not $allowedFields.Contains([string]$actualField)) {
                throw "Runtime evidence has an open or incomplete shape: $Name"
            }
        }
    }
    $top = @('schemaVersion', 'previewId', 'admissionMode', 'sourceLockSha256', 'lockSha256', 'provenanceSha256',
        'payloadManifestSha256', 'rootInventorySha256', 'staticReportSha256', 'validator', 'host', 'collector',
        'collectedUtc', 'scenarios')
    $actualTop = @($Evidence.PSObject.Properties.Name)
    Assert-ClosedObject $Evidence $top 'top-level'
    if ($Evidence.schemaVersion -ne 1 -or
        -not (Test-EtwOrdinalIn $Evidence.admissionMode @('Preview', 'Final'))) {
        throw "Runtime evidence has invalid version or admission mode"
    }
    if ([string]::IsNullOrWhiteSpace($Evidence.previewId) -or
        [string]$Evidence.collectedUtc -cnotmatch 'Z$') {
        throw "Runtime evidence has an invalid preview ID or collection time"
    }
    foreach ($hash in @($Evidence.sourceLockSha256, $Evidence.lockSha256, $Evidence.provenanceSha256,
            $Evidence.payloadManifestSha256, $Evidence.rootInventorySha256,
            $Evidence.staticReportSha256, $Evidence.validator.sha256, $Evidence.collector.sha256)) {
        if ([string]$hash -cnotmatch '^[0-9a-f]{64}$') { throw "Runtime evidence has an invalid SHA-256" }
    }
    if ([string]$Evidence.validator.commit -cnotmatch '^[0-9a-f]{40}$' -or
        [string]$Evidence.collector.commit -cnotmatch '^[0-9a-f]{40}$') {
        throw "Runtime evidence has an invalid immutable commit"
    }
    if (-not (Test-EtwOrdinalEqual $Evidence.host.os 'Windows') -or
        -not (Test-EtwOrdinalEqual $Evidence.host.architecture 'ARM64') -or
        -not (Test-EtwOrdinalEqual $Evidence.validator.repository 'crutkas/build-extra') -or
        -not (Test-EtwOrdinalEqual $Evidence.validator.mode 'Runtime') -or
        -not [IO.Path]::IsPathFullyQualified([string]$Evidence.validator.path) -or
        -not (Test-EtwOrdinalEqual $Evidence.validator.path $canonicalValidatorPath) -or
        $Evidence.validator.bytes -le 0 -or
        -not (Test-EtwOrdinalEqual $Evidence.collector.repository 'crutkas/msys2-woarm64-build') -or
        -not (Test-EtwOrdinalEqual $Evidence.collector.sourcePath 'preview/scripts/Collect-Arm64EtwEvidence.ps1') -or
        -not (Test-EtwOrdinalEqual $Evidence.collector.url (
            "https://raw.githubusercontent.com/$($Evidence.collector.repository)/" +
            "$($Evidence.collector.commit)/$($Evidence.collector.sourcePath)"
        )) -or
        -not (Test-EtwOrdinalEqual $Evidence.collector.method 'ETW-Kernel-Process-ImageLoad') -or
        $Evidence.collector.bytes -le 0) {
        throw "Runtime evidence identity is invalid"
    }
    Assert-ClosedObject $Evidence.validator @('repository', 'commit', 'path', 'bytes', 'sha256', 'mode') 'validator'
    Assert-ClosedObject $Evidence.host @('os', 'architecture') 'host'
    Assert-ClosedObject $Evidence.collector @('inputId', 'repository', 'commit', 'sourcePath', 'url', 'bytes', 'sha256', 'method') 'collector'
    if (-not (Test-EtwOrdinalEqual $Evidence.collector.inputId 'arm64-etw-runtime-collector')) {
        throw "Runtime evidence collector is not bound to the canonical lock input"
    }
    if (-not (Test-EtwOrdinalSequence @($Evidence.scenarios.id) $script:ScenarioOrder)) {
        throw "Runtime scenarios are not in canonical order"
    }
    foreach ($scenario in $Evidence.scenarios) {
        $scenarioFields = @('id', 'status', 'reason', 'command', 'behavior', 'trace')
        Assert-ClosedObject $scenario $scenarioFields "scenario '$($scenario.id)'"
        if (Test-EtwOrdinalEqual $scenario.status 'unresolved') {
            if ((Test-EtwOrdinalEqual $Evidence.admissionMode 'Final') -or
                [string]::IsNullOrWhiteSpace($scenario.reason) -or
                @($scenario.command).Count -ne 0 -or $null -ne $scenario.behavior -or $null -ne $scenario.trace) {
                throw "Invalid unresolved scenario '$($scenario.id)'"
            }
            continue
        }
        if (-not (Test-EtwOrdinalEqual $scenario.status 'pass') -or
            $null -ne $scenario.reason -or @($scenario.command).Count -eq 0) {
            throw "Invalid passing scenario '$($scenario.id)'"
        }
        if (@($scenario.command | Where-Object { [string]::IsNullOrWhiteSpace([string]$_) }).Count -ne 0) {
            throw "Scenario '$($scenario.id)' has an empty command element"
        }
        $commandContract = $script:ScenarioCommandContracts[[string]$scenario.id]
        $actualArguments = @($scenario.command | Select-Object -Skip 1 | ForEach-Object { [string]$_ })
        $expectedArguments = @($commandContract.args | ForEach-Object { [string]$_ })
        $expectedExecutable = ([string]$commandContract.suffix).Replace('/', '\')
        $expectedExecutablePath = Join-Path $portableRootPath $expectedExecutable
        if (-not [IO.Path]::IsPathFullyQualified([string]$scenario.command[0]) -or
            -not (Test-EtwOrdinalEqual $scenario.command[0] $expectedExecutablePath) -or
            -not (Test-EtwOrdinalSequence $actualArguments $expectedArguments)) {
            throw "Scenario '$($scenario.id)' does not use its canonical command vector"
        }
        Assert-ClosedObject $scenario.behavior @('operation', 'passed', 'exitCode') "behavior for '$($scenario.id)'"
        if (-not (Test-EtwOrdinalEqual $scenario.behavior.operation (
                    $script:ScenarioOperations[[string]$scenario.id])) -or
            $scenario.behavior.passed -ne $true -or $scenario.behavior.exitCode -ne 0) {
            throw "Scenario '$($scenario.id)' has invalid behavior evidence"
        }
        $trace = $scenario.trace
        $traceFields = @('complete', 'processEventsComplete', 'imageLoadEventsComplete',
            'processTreeComplete', 'lostEvents', 'startUtc', 'endUtc', 'processes')
        Assert-ClosedObject $trace $traceFields "trace for '$($scenario.id)'"
        if (-not ($trace.complete -and $trace.processEventsComplete -and $trace.imageLoadEventsComplete -and
                $trace.processTreeComplete) -or $trace.lostEvents -ne 0 -or @($trace.processes).Count -eq 0) {
            throw "Incomplete trace for '$($scenario.id)'"
        }
        $traceStart = [DateTimeOffset]::Parse([string]$trace.startUtc)
        $traceEnd = [DateTimeOffset]::Parse([string]$trace.endUtc)
        if ($traceStart -ge $traceEnd) {
            throw "Trace interval for '$($scenario.id)' is invalid"
        }
        $roles = @($trace.processes | Where-Object {
                Test-EtwOrdinalEqual $_.role 'role'
            })
        if ($roles.Count -ne 1 -or $null -ne $roles[0].parentInstanceId -or
            -not [IO.Path]::IsPathFullyQualified([string]$roles[0].path) -or
            -not (Test-EtwOrdinalEqual $roles[0].path $scenario.command[0])) {
            throw "Scenario '$($scenario.id)' does not bind its designated role"
        }
        $ids = @($trace.processes.instanceId)
        if (@($ids | Select-Object -Unique).Count -ne $ids.Count) {
            throw "Scenario '$($scenario.id)' has duplicate process instance IDs"
        }
        $rolePersonalities = @{
            'Git Bash' = 'MSYS'; Git = 'MinGW'; SSH = 'MinGW'; GPG = 'MinGW'
            hook = 'MSYS'; submodule = 'MinGW'; rebase = 'MSYS'; 'git-svn' = 'MSYS'
        }
        if (-not (Test-EtwOrdinalEqual $roles[0].personality $rolePersonalities[$scenario.id])) {
            throw "Scenario '$($scenario.id)' has the wrong role personality"
        }
        foreach ($process in $trace.processes) {
            $processFields = @('instanceId', 'parentInstanceId', 'processId', 'startUtc', 'endUtc',
                'role', 'path', 'sha256', 'architecture', 'personality', 'modulesComplete', 'modules')
            Assert-ClosedObject $process $processFields "process for '$($scenario.id)'"
            if ((Test-EtwOrdinalEqual $process.role 'support') -and
                -not (Test-EtwOrdinalIn $process.parentInstanceId $ids)) {
                throw "Scenario '$($scenario.id)' has an orphan support process"
            }
            if (-not (Test-EtwOrdinalIn $process.role @('role', 'support')) -or
                ((Test-EtwOrdinalEqual $process.role 'support') -and
                    $null -eq $process.parentInstanceId) -or
                $process.processId -le 0 -or [string]::IsNullOrWhiteSpace($process.instanceId) -or
                [string]$process.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
                -not (Test-EtwOrdinalEqual $process.architecture 'ARM64') -or
                -not (Test-EtwOrdinalIn $process.personality @('MSYS', 'MinGW', 'Native'))) {
                throw "Scenario '$($scenario.id)' has invalid process evidence"
            }
            $processStart = [DateTimeOffset]::Parse([string]$process.startUtc)
            $processEnd = [DateTimeOffset]::Parse([string]$process.endUtc)
            if ($processStart -le $traceStart -or $processEnd -ge $traceEnd -or
                $processStart -ge $processEnd) {
                throw "Scenario '$($scenario.id)' process interval escapes its ETW trace"
            }
            if (-not $process.modulesComplete -or @($process.modules).Count -eq 0) {
                throw "Scenario '$($scenario.id)' has incomplete modules"
            }
            $canonicalProcessPath = [IO.Path]::GetFullPath([string]$process.path)
            if (-not (Test-EtwOrdinalEqual $canonicalProcessPath $process.path)) {
                throw "Scenario '$($scenario.id)' has a non-canonical process path"
            }
            $modulePaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($module in $process.modules) {
                $moduleFields = @('path', 'sha256', 'architecture', 'personality')
                Assert-ClosedObject $module $moduleFields "module for '$($scenario.id)'"
                $canonicalModulePath = [IO.Path]::GetFullPath([string]$module.path)
                if (-not (Test-EtwOrdinalEqual $canonicalModulePath $module.path) -or
                    -not $modulePaths.Add($canonicalModulePath)) {
                    throw "Scenario '$($scenario.id)' has duplicate module paths"
                }
                if ([string]$module.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
                    -not (Test-EtwOrdinalEqual $module.architecture 'ARM64') -or
                    -not (Test-EtwOrdinalIn $module.personality @('MSYS', 'MinGW', 'Native'))) {
                    throw "Scenario '$($scenario.id)' has invalid module evidence"
                }
            }
            $processModules = @($process.modules | Where-Object {
                    Test-EtwOrdinalEqual $_.path $process.path
                })
            if ($processModules.Count -ne 1 -or
                -not (Test-EtwOrdinalEqual $processModules[0].sha256 $process.sha256) -or
                -not (Test-EtwOrdinalEqual $processModules[0].architecture $process.architecture) -or
                -not (Test-EtwOrdinalEqual $processModules[0].personality $process.personality)) {
                throw "Scenario '$($scenario.id)' process identity is not cross-bound to exactly one module"
            }
        }
    }
}

function New-ScenarioDefinitions {
    param([Parameter(Mandatory)][string] $Root, [Parameter(Mandatory)][string] $WorkRoot)
    $bash = Join-Path $Root 'usr\bin\bash.exe'
    $git = Join-Path $Root 'bin\git.exe'
    $ssh = Join-Path $Root 'usr\bin\ssh.exe'
    $gpg = Join-Path $Root 'usr\bin\gpg.exe'
    $gitSvn = Join-Path $Root 'mingw64\libexec\git-core\git-svn'
    $perl = Join-Path $Root 'usr\bin\perl.exe'
    $rebaseSetup = 'set -e; git init -q .; git config user.name Evidence; git config user.email evidence@example.invalid; ' +
        'printf base >conflict; git add conflict; git commit -qm base; git checkout -qb topic; ' +
        'printf topic >conflict; git commit -qam topic; git checkout -q master; printf main >conflict; ' +
        'git commit -qam main; git checkout -q topic; if git rebase master; then exit 1; fi'
    return @(
        [pscustomobject]@{ id = 'Git Bash'; operation = 'git-bash-startup'; path = $bash; requiredPaths = @($bash); personality = 'MSYS'; args = @('--noprofile', '--norc', '-lc', 'exit 0'); required = $true; setupArgs = @() },
        [pscustomobject]@{ id = 'Git'; operation = 'git-command'; path = $git; requiredPaths = @($git); personality = 'MinGW'; args = @('--version'); required = $true; setupArgs = @() },
        [pscustomobject]@{ id = 'SSH'; operation = 'ssh-command'; path = $ssh; requiredPaths = @($ssh); personality = 'MinGW'; args = @('-V'); required = $false; setupArgs = @() },
        [pscustomobject]@{ id = 'GPG'; operation = 'gpg-command'; path = $gpg; requiredPaths = @($gpg); personality = 'MinGW'; args = @('--version'); required = $false; setupArgs = @() },
        [pscustomobject]@{ id = 'hook'; operation = 'git-hook'; path = $bash; requiredPaths = @($bash); personality = 'MSYS'; args = @('--noprofile', '--norc', '-lc', 'exit 0'); required = $true; setupArgs = @() },
        [pscustomobject]@{ id = 'submodule'; operation = 'git-submodule'; path = $git; requiredPaths = @($git); personality = 'MinGW'; args = @('submodule', 'status', '--recursive'); required = $true; setupArgs = @('init', '-q', '.') },
        [pscustomobject]@{ id = 'rebase'; operation = 'git-rebase'; path = $bash; requiredPaths = @($bash, $git); personality = 'MSYS'; args = @('--noprofile', '--norc', '-lc', 'git rebase --show-current-patch'); required = $true; setupArgs = @('--noprofile', '--norc', '-lc', $rebaseSetup) },
        [pscustomobject]@{ id = 'git-svn'; operation = 'git-svn'; path = $bash; requiredPaths = @($bash, $git, $gitSvn, $perl); personality = 'MSYS'; args = @('--noprofile', '--norc', '-lc', 'git svn --version'); required = $false; setupArgs = @() }
    )
}

function New-EtwProcessJob {
    Initialize-EtwNativeApi
    $job = [Arm64EtwNative]::CreateJobObject([IntPtr]::Zero, $null)
    if ($job -eq [IntPtr]::Zero) { throw "Unable to create scenario process job" }
    return $job
}

function Get-EtwJobActiveCount {
    param([Parameter(Mandatory)][IntPtr] $Job)
    $accounting = [Arm64EtwNative+JobAccounting]::new()
    $size = [Runtime.InteropServices.Marshal]::SizeOf([type][Arm64EtwNative+JobAccounting])
    if (-not [Arm64EtwNative]::QueryInformationJobObject($Job, 1, [ref]$accounting, $size, [IntPtr]::Zero)) {
        throw "Unable to query scenario process job"
    }
    return [int]$accounting.ActiveProcesses
}

function Wait-EtwProcessJob {
    param([Parameter(Mandatory)][IntPtr] $Job, [int] $TimeoutSeconds = 120)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ((Get-EtwJobActiveCount $Job) -ne 0) {
        if ([DateTime]::UtcNow -ge $deadline) { throw "Scenario descendants did not exit before timeout" }
        Start-Sleep -Milliseconds 50
    }
}

function Set-EtwScenarioEnvironment {
    param(
        [Parameter(Mandatory)] [Diagnostics.ProcessStartInfo] $ProcessStartInfo,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $ScenarioRoot,
        [Parameter(Mandatory)][string] $WindowsRoot
    )

    $privateHome = Join-Path $ScenarioRoot 'home'
    $privateTemp = Join-Path $ScenarioRoot 'temp'
    foreach ($directory in @($privateHome, $privateTemp)) {
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory | Out-Null
        }
    }
    $ProcessStartInfo.Environment['HOME'] = $privateHome
    $ProcessStartInfo.Environment['USERPROFILE'] = $privateHome
    $ProcessStartInfo.Environment['PATH'] = ((Join-Path $PortableRoot 'bin'), (Join-Path $PortableRoot 'usr\bin'),
        (Join-Path $WindowsRoot 'System32')) -join ';'
    $ProcessStartInfo.Environment['LC_ALL'] = 'C.UTF-8'
    $ProcessStartInfo.Environment['MSYS'] = 'winsymlinks:nativestrict'
    $ProcessStartInfo.Environment['GIT_CONFIG_NOSYSTEM'] = '1'
    $ProcessStartInfo.Environment['GIT_TERMINAL_PROMPT'] = '0'
    $ProcessStartInfo.Environment['TEMP'] = $privateTemp
    $ProcessStartInfo.Environment['TMP'] = $privateTemp
    foreach ($name in @('GIT_DIR', 'GIT_WORK_TREE', 'GIT_EXEC_PATH', 'GIT_TEMPLATE_DIR')) {
        $null = $ProcessStartInfo.Environment.Remove($name)
    }
}

function Invoke-EtwScenarioSetup {
    param(
        [Parameter(Mandatory)] $Definition,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $ScenarioRoot,
        [Parameter(Mandatory)][string] $WindowsRoot
    )

    if (@($Definition.setupArgs).Count -eq 0) { return }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Definition.path
    $info.UseShellExecute = $false
    $info.WorkingDirectory = $ScenarioRoot
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Definition.setupArgs) { $info.ArgumentList.Add([string]$argument) }
    Set-EtwScenarioEnvironment -ProcessStartInfo $info -PortableRoot $PortableRoot `
        -ScenarioRoot $ScenarioRoot -WindowsRoot $WindowsRoot
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) { throw "Unable to start setup for scenario '$($Definition.id)'" }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(120000)) {
        $process.Kill($true)
        $process.WaitForExit()
        throw "Setup for scenario '$($Definition.id)' timed out"
    }
    $stdout.GetAwaiter().GetResult() | Out-Null
    $errorText = $stderr.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) {
        throw "Setup for scenario '$($Definition.id)' failed with code $($process.ExitCode): $errorText"
    }
}

function Invoke-EtwScenario {
    param(
        [Parameter(Mandatory)] $Definition,
        [Parameter(Mandatory)][string] $PortableRoot,
        [Parameter(Mandatory)][string] $WorkRoot,
        [Parameter(Mandatory)][string] $Logman,
        [Parameter(Mandatory)][string] $Tracerpt,
        [Parameter(Mandatory)][string] $WindowsRoot,
        [Parameter(Mandatory)] $PayloadHashes
    )
    $safeId = $Definition.id -replace '[^A-Za-z0-9-]', '-'
    $scenarioRoot = Join-Path $WorkRoot $safeId
    if (Test-Path -LiteralPath $scenarioRoot) { throw "Scenario work directory already exists: $scenarioRoot" }
    New-Item -ItemType Directory -Path $scenarioRoot | Out-Null
    $etl = Join-Path $scenarioRoot 'trace.etl'
    $xml = Join-Path $scenarioRoot 'events.xml'
    $summary = Join-Path $scenarioRoot 'summary.xml'
    $stdout = Join-Path $scenarioRoot 'stdout.txt'
    $stderr = Join-Path $scenarioRoot 'stderr.txt'
    $session = "Arm64Preview-$([Guid]::NewGuid().ToString('N'))"
    $started = $false
    $job = [IntPtr]::Zero
    $process = $null
    $completed = $false
    try {
    Invoke-EtwScenarioSetup -Definition $Definition -PortableRoot $PortableRoot `
        -ScenarioRoot $scenarioRoot -WindowsRoot $WindowsRoot
    & $Logman start $session -ets -o $etl -p "{$script:KernelProcessProvider}" 0x50 5 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "logman failed to start ETW session '$session'" }
        $started = $true
        $startBoundary = [DateTimeOffset]::UtcNow
        $psi = [Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $Definition.path
        $psi.UseShellExecute = $false
        $psi.WorkingDirectory = $scenarioRoot
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.RedirectStandardInput = $true
        foreach ($argument in $Definition.args) { $null = $psi.ArgumentList.Add([string]$argument) }
        Set-EtwScenarioEnvironment -ProcessStartInfo $psi -PortableRoot $PortableRoot `
            -ScenarioRoot $scenarioRoot -WindowsRoot $WindowsRoot
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $psi
        $job = New-EtwProcessJob
        if (-not $process.Start()) { throw "Unable to launch scenario '$($Definition.id)'" }
        $process.StandardInput.Close()
        if (-not [Arm64EtwNative]::AssignProcessToJobObject($job, $process.Handle)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "Unable to assign scenario '$($Definition.id)' to its process job"
        }
        $rootPid = $process.Id
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(120000)) {
            $null = [Arm64EtwNative]::TerminateJobObject($job, 1)
            $process.WaitForExit()
            throw "Scenario '$($Definition.id)' did not exit before timeout"
        }
        Wait-EtwProcessJob $job
        $outTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stdout -Encoding utf8
        $errorTask.GetAwaiter().GetResult() | Set-Content -LiteralPath $stderr -Encoding utf8
        $exitCode = $process.ExitCode
        $process.Dispose()
        if ($exitCode -ne 0) { throw "Scenario '$($Definition.id)' exited with code $exitCode" }
        & $Logman stop $session -ets | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "logman failed to stop ETW session '$session'" }
        $started = $false
        $endBoundary = [DateTimeOffset]::UtcNow
        & $Tracerpt $etl -of XML -o $xml -summary $summary -y | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "tracerpt failed for scenario '$($Definition.id)'" }
        $lostEvents = Get-TracerptLostEvents -SummaryPath $summary
        $parsed = ConvertFrom-TracerptXml -Path @($xml) -LostEvents $lostEvents
        $processes = @(ConvertTo-EtwProcessTree -ParsedTrace $parsed -RootProcessId $rootPid `
            -RootStartedAfterUtc $startBoundary -PortableRoot $PortableRoot -WindowsRoot $WindowsRoot `
            -ExpectedRolePersonality $Definition.personality -PayloadHashes $PayloadHashes)
        $result = [ordered]@{
            id = $Definition.id
            status = 'pass'
            reason = $null
            command = @([string]$Definition.path) +
                @($Definition.args | ForEach-Object { [string]$_ })
            behavior = [ordered]@{
                operation = $Definition.operation
                passed = $true
                exitCode = $exitCode
            }
            trace = [ordered]@{
                complete = $true
                processEventsComplete = $true
                imageLoadEventsComplete = $true
                processTreeComplete = $true
                lostEvents = 0
                startUtc = ConvertTo-EtwUtc $startBoundary
                endUtc = ConvertTo-EtwUtc $endBoundary
                processes = $processes
            }
        }
        $completed = $true
        return $result
    }
    finally {
        if ($job -ne [IntPtr]::Zero) {
            try {
                if ((Get-EtwJobActiveCount $job) -ne 0) {
                    $null = [Arm64EtwNative]::TerminateJobObject($job, 1)
                    Wait-EtwProcessJob $job 10
                }
            }
            finally {
                $null = [Arm64EtwNative]::CloseHandle($job)
                $job = [IntPtr]::Zero
            }
        }
        if ($null -ne $process) { $process.Dispose() }
        if ($started) {
            & $Logman stop $session -ets 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to stop ETW session '$session' during cleanup"
            }
            $started = $false
        }
        if ($completed) {
            foreach ($artifact in @($etl, $xml, $summary)) {
                if (Test-Path -LiteralPath $artifact) { Remove-Item -LiteralPath $artifact -Force }
            }
        }
    }
}

function Invoke-Arm64EtwCollector {
    foreach ($value in @($PortableRoot, $AdmissionMode, $LockPath, $ProvenancePath,
            $PayloadManifestPath, $AssemblyEvidencePath, $StaticReportPath,
            $ValidatorCommit, $ValidatorRoot, $OutputPath)) {
        if ([string]::IsNullOrWhiteSpace($value)) { throw "All collector parameters are required" }
    }
    foreach ($path in @($PortableRoot, $LockPath, $ProvenancePath, $PayloadManifestPath,
            $AssemblyEvidencePath, $StaticReportPath, $ValidatorRoot, $OutputPath)) {
        Assert-NotSharedRoot $path
        Assert-PrivatePath $path
    }
    if (-not $IsWindows) { throw "The ETW collector requires Windows" }
    if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [Runtime.InteropServices.Architecture]::Arm64 -or
        [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne [Runtime.InteropServices.Architecture]::Arm64) {
        throw "The ETW collector requires Windows ARM64 and native ARM64 PowerShell"
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "The ETW collector requires elevation"
    }
    $windowsRoot = (Resolve-Path -LiteralPath 'C:\Windows').Path.TrimEnd('\')
    if (-not $windowsRoot.Equals('C:\Windows', [StringComparison]::OrdinalIgnoreCase) -or
        -not ([IO.Path]::GetFullPath($env:WINDIR).TrimEnd('\')).Equals(
            $windowsRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "The evidence contract requires the native C:\Windows installation"
    }
    $root = [IO.Path]::GetFullPath(
        (Get-FinalEtwPath (Resolve-Path -LiteralPath $PortableRoot).Path -Directory)).TrimEnd('\')
    $workRoot = "$root.etw-work"
    $failureDiagnostics = "$OutputPath.diagnostics"
    Assert-NotSharedRoot $workRoot
    Assert-PrivatePath $workRoot
    Assert-NoPreparationTools -Root $root
    foreach ($inputPath in @($LockPath, $ProvenancePath, $PayloadManifestPath, $AssemblyEvidencePath, $StaticReportPath)) {
        if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) { throw "Collector input is missing: $inputPath" }
    }
    if (Test-Path -LiteralPath $OutputPath) { throw "OutputPath must not exist: $OutputPath" }
    if (Test-Path -LiteralPath $failureDiagnostics) {
        throw "Failure diagnostics path must not exist: $failureDiagnostics"
    }
    if (Test-Path -LiteralPath $workRoot) { throw "Collector work directory must not exist: $workRoot" }
    $lockHash = Get-EtwSha256 $LockPath
    $provenanceHash = Get-EtwSha256 $ProvenancePath
    $manifestHash = Get-EtwSha256 $PayloadManifestPath
    $staticReportHash = Get-EtwSha256 $StaticReportPath
    $bundleLock = Get-Content -LiteralPath $LockPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not (Test-EtwOrdinalEqual $bundleLock.sourceLock.path 'preview-evidence/source-lock.json') -or
        [string]$bundleLock.sourceLock.sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Canonical lock has an invalid source lock binding"
    }
    $sourceLockPath = [IO.Path]::GetFullPath((Join-Path $root ([string]$bundleLock.sourceLock.path).Replace('/', '\')))
    if (-not $sourceLockPath.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $sourceLockPath -PathType Leaf)) {
        throw "Canonical lock source lock path is absent or unsafe"
    }
    $sourceLockHash = Get-EtwSha256 $sourceLockPath
    if (-not (Test-EtwOrdinalEqual $sourceLockHash $bundleLock.sourceLock.sha256)) {
        throw "Canonical lock source lock digest does not match"
    }
    $sourceLock = Get-Content -LiteralPath $sourceLockPath -Raw -Encoding utf8 | ConvertFrom-Json
    $provenance = Get-Content -LiteralPath $ProvenancePath -Raw -Encoding utf8 | ConvertFrom-Json
    $manifest = Get-Content -LiteralPath $PayloadManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    $assembly = Get-Content -LiteralPath $AssemblyEvidencePath -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not (Test-EtwOrdinalEqual $provenance.assembler.repository 'crutkas/msys2-woarm64-build') -or
        [string]$provenance.assembler.commit -cnotmatch '^[0-9a-f]{40}$') {
        throw "Provenance has no deterministic assembler identity"
    }
    if (-not (Test-EtwOrdinalEqual $provenance.lockSha256 $lockHash) -or
        -not (Test-EtwOrdinalEqual $manifest.lockSha256 $lockHash) -or
        -not (Test-EtwOrdinalEqual $manifest.provenanceSha256 $provenanceHash)) {
        throw "Lock, provenance, and payload manifest hashes are not mutually bound"
    }
    $payloadHashes = Get-EtwPayloadHashes -Entries $manifest.entries -PortableRoot $root
    foreach ($binding in @('sourceLockSha256', 'lockSha256', 'provenanceSha256', 'payloadManifestSha256',
            'rootInventorySha256', 'staticReportSha256', 'previewId')) {
        if ($null -eq $assembly.PSObject.Properties[$binding]) { throw "Assembly evidence is missing '$binding'" }
    }
    if (-not (Test-EtwOrdinalEqual $assembly.sourceLockSha256 $sourceLockHash) -or
        -not (Test-EtwOrdinalEqual $assembly.lockSha256 $lockHash) -or
        -not (Test-EtwOrdinalEqual $assembly.provenanceSha256 $provenanceHash) -or
        -not (Test-EtwOrdinalEqual $assembly.payloadManifestSha256 $manifestHash) -or
        -not (Test-EtwOrdinalEqual $assembly.staticReportSha256 $staticReportHash)) {
        throw "Assembly evidence does not bind the exact collector inputs"
    }
    if ([string]$assembly.rootInventorySha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [string]::IsNullOrWhiteSpace($assembly.previewId)) {
        throw "Assembly evidence has an invalid preview or root inventory identity"
    }
    if ($ValidatorCommit -cnotmatch '^[0-9a-f]{40}$' -or
        -not (Test-EtwOrdinalEqual $ValidatorCommit $ValidatorCommit.ToLowerInvariant())) {
        throw "ValidatorCommit must be a full lowercase commit"
    }
    $scriptPath = [IO.Path]::GetFullPath($PSCommandPath)
    $scriptBytes = (Get-Item -LiteralPath $scriptPath).Length
    $collectorInputs = @($bundleLock.inputs | Where-Object {
            Test-EtwOrdinalEqual $_.id 'arm64-etw-runtime-collector'
        })
    if ($collectorInputs.Count -ne 1) {
        throw "Canonical lock must contain exactly one runtime collector input"
    }
    $collectorInput = $collectorInputs[0]
    $collectorHash = Get-EtwSha256 $scriptPath
    $expectedCollectorUrl = "https://raw.githubusercontent.com/$($collectorInput.release.repository)/" +
        "$($collectorInput.release.targetCommit)/$($collectorInput.release.sourcePath)"
    if (-not (Test-EtwOrdinalEqual $collectorInput.role 'validation-tool') -or
        -not (Test-EtwOrdinalEqual $collectorInput.status 'resolved') -or
        -not (Test-EtwOrdinalEqual $collectorInput.resolution.method 'github-raw-commit') -or
        $collectorInput.overlay.enabled -ne $false -or
        -not (Test-EtwOrdinalEqual $collectorInput.release.repository 'crutkas/msys2-woarm64-build') -or
        -not (Test-EtwOrdinalEqual $collectorInput.release.sourcePath 'preview/scripts/Collect-Arm64EtwEvidence.ps1') -or
        [string]$collectorInput.release.targetCommit -cnotmatch '^[0-9a-f]{40}$' -or
        -not (Test-EtwOrdinalEqual $collectorInput.asset.url $expectedCollectorUrl) -or
        [Int64]$collectorInput.asset.bytes -ne [Int64]$scriptBytes -or
        -not (Test-EtwOrdinalEqual $collectorInput.asset.sha256 $collectorHash)) {
        throw "Runtime collector does not match its canonical lock input"
    }
    $validatorInput = Get-EtwValidatorBinding -SourceLock $sourceLock `
        -BundleLock $bundleLock -ValidatorCommit $ValidatorCommit
    $expectedValidatorUrl = "https://raw.githubusercontent.com/$($validatorInput.release.repository)/" +
        "$($validatorInput.release.targetCommit)/$($validatorInput.release.sourcePath)"
    if (-not (Test-EtwOrdinalEqual $validatorInput.asset.url $expectedValidatorUrl) -or
        [Int64]$validatorInput.asset.bytes -le 0 -or
        [string]$validatorInput.asset.sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Authoritative validator does not match its canonical raw-commit identity"
    }
    $canonicalValidatorRoot = [IO.Path]::GetFullPath(
        (Get-FinalEtwPath (Resolve-Path -LiteralPath $ValidatorRoot).Path -Directory)).TrimEnd('\')
    $validatorRelative = ConvertTo-SafeArchivePath -Member ([string]$validatorInput.release.sourcePath)
    $validatorPath = [IO.Path]::GetFullPath(
        (Join-Path $canonicalValidatorRoot $validatorRelative.Replace('/', '\')))
    if (-not $validatorPath.StartsWith("$canonicalValidatorRoot\", [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $validatorPath -PathType Leaf)) {
        throw "Authoritative validator canonical source path is absent or unsafe"
    }
    $joinedValidatorPath = $validatorPath
    $validatorPath = [IO.Path]::GetFullPath((Get-FinalEtwPath $joinedValidatorPath))
    if (-not (Test-EtwOrdinalEqual $validatorPath $joinedValidatorPath) -or
        (Get-Item -LiteralPath $validatorPath).Length -ne [Int64]$validatorInput.asset.bytes -or
        -not (Test-EtwOrdinalEqual (Get-EtwSha256 $validatorPath) $validatorInput.asset.sha256)) {
        throw "Authoritative validator canonical source file does not match its lock identity"
    }
    $logman = Join-Path $windowsRoot 'System32\logman.exe'
    $tracerpt = Join-Path $windowsRoot 'System32\tracerpt.exe'
    foreach ($tool in @($logman, $tracerpt)) {
        if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
            throw "Required System32 ETW tool is missing or not ARM64: $tool"
        }
        $null = Get-EtwArchitecture $tool $windowsRoot
    }
    New-Item -ItemType Directory -Path $workRoot | Out-Null
    $collectionCompleted = $false
    try {
        $scenarios = @()
        foreach ($definition in @(New-ScenarioDefinitions -Root $root -WorkRoot $workRoot)) {
            $unavailableReason = $null
            $missingPaths = @($definition.requiredPaths | Where-Object {
                    -not (Test-Path -LiteralPath $_ -PathType Leaf)
                })
            $available = $missingPaths.Count -eq 0
            if ($available) {
                try {
                    $null = Get-EtwArchitecture $definition.path $windowsRoot
                    $actualPersonality = Get-EtwPersonality $definition.path $windowsRoot
                    if (-not (Test-EtwOrdinalEqual $actualPersonality $definition.personality)) {
                        throw "Role personality is '$actualPersonality', expected '$($definition.personality)'"
                    }
                }
                catch {
                    if ($definition.required -or
                        (Test-EtwOrdinalEqual $AdmissionMode 'Final')) { throw }
                    $available = $false
                    $unavailableReason = $_.Exception.Message
                }
            }
            if (-not $available) {
                if ($definition.required -or
                    (Test-EtwOrdinalEqual $AdmissionMode 'Final')) {
                    throw "Required scenario '$($definition.id)' has no admissible native role binary: $($definition.path)"
                }
                if ([string]::IsNullOrWhiteSpace($unavailableReason)) {
                    $unavailableReason = "Scenario input is absent: $($missingPaths -join ', ')"
                }
                $scenarios += [ordered]@{
                    id = $definition.id; status = 'unresolved'; reason = $unavailableReason
                    command = @(); behavior = $null; trace = $null
                }
                continue
            }
            $scenarios += Invoke-EtwScenario -Definition $definition -PortableRoot $root -WorkRoot $workRoot `
                -Logman $logman -Tracerpt $tracerpt -WindowsRoot $windowsRoot -PayloadHashes $payloadHashes
        }
        $evidence = [ordered]@{
            schemaVersion = 1
            previewId = [string]$assembly.previewId
            admissionMode = $AdmissionMode
            sourceLockSha256 = $sourceLockHash
            lockSha256 = $lockHash
            provenanceSha256 = $provenanceHash
            payloadManifestSha256 = $manifestHash
            rootInventorySha256 = [string]$assembly.rootInventorySha256
            staticReportSha256 = $staticReportHash
            validator = [ordered]@{
                repository = 'crutkas/build-extra'
                commit = $ValidatorCommit
                path = $validatorPath
                bytes = [Int64]$validatorInput.asset.bytes
                sha256 = [string]$validatorInput.asset.sha256
                mode = 'Runtime'
            }
            host = [ordered]@{ os = 'Windows'; architecture = 'ARM64' }
            collector = [ordered]@{
                inputId = 'arm64-etw-runtime-collector'
                repository = 'crutkas/msys2-woarm64-build'
                commit = [string]$collectorInput.release.targetCommit
                sourcePath = [string]$collectorInput.release.sourcePath
                url = [string]$collectorInput.asset.url
                bytes = $scriptBytes
                sha256 = $collectorHash
                method = 'ETW-Kernel-Process-ImageLoad'
            }
            collectedUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')
            scenarios = $scenarios
        }
        Assert-RuntimeEvidenceShape -Evidence ([pscustomobject]$evidence) -PortableRoot $root `
            -ValidatorPath $validatorPath
        $evidence | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $OutputPath -Encoding utf8 -NoNewline
        $collectionCompleted = $true
    }
    finally {
        if (Test-Path -LiteralPath $workRoot) {
            if ($collectionCompleted) {
                Remove-Item -LiteralPath $workRoot -Recurse -Force
            } else {
                Move-Item -LiteralPath $workRoot -Destination $failureDiagnostics
            }
        }
    }
}

if (-not $LibraryOnly) {
    Import-Module (Join-Path $PSScriptRoot 'Preview.Common.psm1') -Force
    Invoke-Arm64EtwCollector
}
