[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Root,
    [Parameter(Mandatory)][string] $EvidenceRoot,
    [Parameter(Mandatory)][string] $ArtifactGate,
    [Parameter(Mandatory)][string] $ProcessGate,
    [string] $HttpsRepository,
    [string] $ExpectedHttpsCommit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'Arm64') {
    throw 'Native Git acceptance requires Windows ARM64.'
}
if ([bool]$HttpsRepository -ne [bool]$ExpectedHttpsCommit) {
    throw 'HTTPS repository and exact expected commit must be provided together.'
}
if ($HttpsRepository -and ($HttpsRepository -notmatch '^https://' -or
    $ExpectedHttpsCommit -notmatch '^[0-9a-f]{40}([0-9a-f]{24})?$')) {
    throw 'HTTPS requires an HTTPS URL and a full object ID.'
}
$Root = (Resolve-Path -LiteralPath $Root).Path
foreach ($gate in @($ArtifactGate, $ProcessGate)) {
    if (-not (Test-Path -LiteralPath $gate -PathType Leaf)) { throw "Missing acceptance helper: $gate" }
}
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'EvidenceRoot must be a new directory.' }
if ([IO.Path]::GetRelativePath($Root, $EvidenceRoot) -notmatch '^\.\.([\\/]|$)') {
    throw 'Evidence must be outside the tested artifact.'
}
[IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
$pwsh = (Get-Process -Id $PID).Path
$results = [Collections.Generic.List[object]]::new()
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.Directory]::CreateDirectory("$EvidenceRoot\home") | Out-Null
$globalConfigPath = Join-Path "$EvidenceRoot\home" 'empty.gitconfig'
[IO.File]::WriteAllText($globalConfigPath, '', $utf8)

function New-ToolProcess([string] $Exe, [string[]] $Arguments, [string] $WorkingDirectory) {
    $start = [Diagnostics.ProcessStartInfo]::new($Exe)
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $WorkingDirectory
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(GIT_|SSH_|PERL|BASH_ENV$|ENV$|CDPATH$|MSYS|MINGW)') {
            [void]$start.Environment.Remove($key)
        }
    }
    $start.Environment['PATH'] = "$Root\clangarm64\bin;$Root\usr\bin;$env:SystemRoot\System32"
    $start.Environment['GIT_CONFIG_NOSYSTEM'] = '1'
    $start.Environment['GIT_CONFIG_GLOBAL'] = $globalConfigPath
    $start.Environment['GIT_TERMINAL_PROMPT'] = '0'
    $start.Environment['GIT_EXEC_PATH'] = "$Root\clangarm64\libexec\git-core"
    $start.Environment['HOME'] = "$EvidenceRoot\home"
    $start.Environment['XDG_CONFIG_HOME'] = "$EvidenceRoot\home"
    $start.Environment['MSYSTEM'] = 'CLANGARM64'
    $start.Environment['MSYS2_PATH_TYPE'] = 'minimal'
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    [void]$process.Start()
    return $process
}

function Test-Within([string] $Parent, [string] $Child) {
    $relative = [IO.Path]::GetRelativePath($Parent, $Child)
    return -not [IO.Path]::IsPathRooted($relative) -and
        $relative -ne '..' -and $relative -notmatch '^\.\.[\\/]'
}

function Invoke-Tool([string] $Name, [string] $Exe, [string[]] $Arguments, [string] $InputText = '') {
    $process = New-ToolProcess $Exe $Arguments $EvidenceRoot
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($InputText)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(180000)) {
            $process.Kill($true)
            throw "Timed out: $Name"
        }
        $record = [ordered]@{
            Name = $Name; Executable = $Exe; Arguments = $Arguments; ExitCode = $process.ExitCode
            Stdout = $stdout.GetAwaiter().GetResult(); Stderr = $stderr.GetAwaiter().GetResult()
        }
        $results.Add($record)
        [IO.File]::WriteAllText((Join-Path $EvidenceRoot "$Name.json"),
            ($record | ConvertTo-Json -Depth 5), $utf8)
        if ($process.ExitCode -ne 0) { throw "$Name failed with exit $($process.ExitCode)" }
        return $record.Stdout
    }
    finally { $process.Dispose() }
}

function Test-HeldProcess([string] $Name, [string] $Exe, [string[]] $Arguments) {
    $process = New-ToolProcess $Exe $Arguments $EvidenceRoot
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        Invoke-Tool "identity-$Name" $pwsh @('-NoProfile', '-File', $ProcessGate,
            '-ProcessId', "$($process.Id)", '-ReportPath', "$EvidenceRoot\$Name-process.json") | Out-Null
        $identity = Get-Content -Raw -LiteralPath "$EvidenceRoot\$Name-process.json" | ConvertFrom-Json
        if (-not $identity.Passed -or $identity.MeasuredCount -ne 1 -or
            $identity.Processes[0].ImagePath -ine $Exe) { throw "$Name live identity mismatch" }
        $modules = @((Get-Process -Id $process.Id).Modules | ForEach-Object {
            $path = $_.FileName
            $inRoot = Test-Within $Root $path
            $inWindows = Test-Within $env:SystemRoot $path
            if (-not $inRoot -and -not $inWindows) { throw "Foreign loaded module: $path" }
            [ordered]@{ Path = $path; SHA256 = (Get-FileHash -LiteralPath $path).Hash; Artifact = $inRoot }
        })
        if ($modules.Count -eq 0) { throw 'No loaded modules observed' }
        [IO.File]::WriteAllText("$EvidenceRoot\$Name-modules.json", (ConvertTo-Json -InputObject $modules -Depth 4), $utf8)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000)) { throw "$Name did not exit after input closed" }
        $stdout.GetAwaiter().GetResult() | Out-Null
        $stderr.GetAwaiter().GetResult() | Out-Null
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}

$contract = Get-Content -LiteralPath "$PSScriptRoot\distribution.json" -Raw | ConvertFrom-Json
$required = @($contract.required_files)
$status = 'failed'
try {
    # Both gates run in fresh PowerShell processes, avoiding stale Add-Type state.
    $gateArgs = @('-NoProfile', '-File', $ArtifactGate, '-Root', $Root,
        '-ReportPath', "$EvidenceRoot\artifact-before.json")
    Invoke-Tool 'artifact-before-command' $pwsh $gateArgs | Out-Null
    $before = Get-Content -Raw "$EvidenceRoot\artifact-before.json" | ConvertFrom-Json
    if (-not $before.Passed -or $before.ParsedCount -lt 1 -or
        $before.ParsedCount -ne $before.CandidateCount -or $before.ArtifactRoot -ine $Root) {
        throw 'Artifact gate did not report a complete passing inventory of this root.'
    }
    foreach ($relative in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relative) -PathType Leaf)) {
            throw "Missing full distribution requirement: $relative"
        }
    }
    $git = "$Root\clangarm64\bin\git.exe"
    $bash = "$Root\usr\bin\bash.exe"
    $perl = "$Root\usr\bin\perl.exe"
    Test-HeldProcess 'git' $git @('hash-object', '--stdin')
    Test-HeldProcess 'bash' $bash @('--noprofile', '--norc', '-c', 'read -r unused')
    Test-HeldProcess 'perl' $perl @('-e', 'read STDIN, my $value, 1;')
    $fixtureScript = "$PSScriptRoot\git-fixtures.sh".Replace('\', '/')
    Invoke-Tool 'offline-fixtures' $bash @('--noprofile', '--norc', $fixtureScript,
        $git.Replace('\', '/'), "$Root/clangarm64/libexec/git-core".Replace('\', '/'),
        "$EvidenceRoot/offline-fixtures".Replace('\', '/'), 'native-msys',
        "$Root/clangarm64/share/git/builtins.txt".Replace('\', '/')) | Out-Null

    $keygen = "$Root\usr\bin\ssh-keygen.exe"
    Invoke-Tool 'ssh-keygen' $keygen @('-q', '-t', 'ed25519', '-N', '', '-f', "$EvidenceRoot\fixture-key") | Out-Null
    $public = Invoke-Tool 'ssh-public-key' $keygen @('-y', '-f', "$EvidenceRoot\fixture-key")
    $storedPublic = Get-Content -LiteralPath "$EvidenceRoot\fixture-key.pub" -Raw
    if ((($public.Trim() -split ' ')[0..1] -join ' ') -cne (($storedPublic.Trim() -split ' ')[0..1] -join ' ')) {
        throw 'SSH private/public key round trip failed'
    }
    if ($HttpsRepository) {
        Invoke-Tool 'https-clone' $git @('clone', '--no-checkout', $HttpsRepository, "$EvidenceRoot\https-clone") | Out-Null
        Invoke-Tool 'https-object' $git @('-C', "$EvidenceRoot\https-clone", 'cat-file', '-e', "$ExpectedHttpsCommit^{commit}") | Out-Null
        Invoke-Tool 'https-fsck' $git @('-C', "$EvidenceRoot\https-clone", 'fsck', '--strict') | Out-Null
    }
    Invoke-Tool 'artifact-after-command' $pwsh @('-NoProfile', '-File', $ArtifactGate,
        '-Root', $Root, '-ReportPath', "$EvidenceRoot\artifact-after.json") | Out-Null
    $after = Get-Content -Raw "$EvidenceRoot\artifact-after.json" | ConvertFrom-Json
    if (-not $after.Passed -or $after.ParsedCount -lt 1 -or
        $after.ParsedCount -ne $after.CandidateCount -or $after.ArtifactRoot -ine $Root) {
        throw 'Post-test artifact gate did not report a complete passing inventory.'
    }
    $old = @($before.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
    $new = @($after.Files | ForEach-Object { "$($_.Path) $($_.SHA256)" })
    if (@(Compare-Object $old $new).Count -ne 0) { throw 'Artifact changed during behavior tests' }
    $status = 'tested-subset-not-full-acceptance'
}
finally {
    $summary = [ordered]@{
        Status = $status
        Scope = 'Offline Git/hooks/submodules/helper dispatch, Perl fork, make shell, coreutils, SSH key generation, held Git/Bash/Perl identities and observed modules only.'
        HttpsRequested = [bool]$HttpsRepository
        Pending = @('real-SSH-session', 'real-credential-storage-and-prompts', 'GUI',
            'native-Windows-compiler-build-roundtrip', 'complete-loaded-module-closure') +
            $(if (-not $HttpsRepository) { @('HTTPS') } else { @() })
        ExecutedCommands = $results.Count
        ArtifactGateSHA256 = (Get-FileHash -LiteralPath $ArtifactGate).Hash
        ProcessGateSHA256 = (Get-FileHash -LiteralPath $ProcessGate).Hash
    }
    [IO.File]::WriteAllText("$EvidenceRoot\summary.json", ($summary | ConvertTo-Json -Depth 5), $utf8)
}
