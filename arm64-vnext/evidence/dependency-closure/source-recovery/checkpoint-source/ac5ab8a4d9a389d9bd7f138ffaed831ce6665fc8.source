$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\reader-fixture.ps1"
$reader = Join-Path $PSScriptRoot '..\..\.github\scripts\msys\read-qualified-toolchain.ps1'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    foreach ($case in @(
        @{ Name = 'false acceptance'; Error = '*acceptance is not a passing native MSYS*'; Mutate = { param($f) } },
        @{ Name = 'unlisted prefix file'; Error = '*extra file outside qualified inventory*'; Mutate = {
            param($f) [IO.File]::WriteAllText((Join-Path $f.Prefix 'unexpected.txt'), 'not inventoried') } },
        @{ Name = 'compiler bytes changed'; Error = '*file hash mismatch*'; Mutate = {
            param($f) [IO.File]::AppendAllText((Join-Path $f.Prefix $f.Data.Components.GCC.Path), ' changed') } },
        @{ Name = 'unbound proof bytes'; Error = '*file hash mismatch*'; Mutate = {
            param($f) [IO.File]::AppendAllText($f.ProofPath, ' ') } },
        @{ Name = 'wrong retained DLL source'; Error = '*runtime DLL is not paired*'; Mutate = {
            param($f) $f.Data.RuntimePairing.SourceDll = '/fixture/different.dll' } },
        @{ Name = 'claimed pass with no native images'; Error = '*tool identities omit a prefix PE image*'; Mutate = {
            param($f)
            $f.Proof.Passed = $true
            [IO.File]::WriteAllText($f.ProofPath, ($f.Proof | ConvertTo-Json -Depth 5))
            $f.Data.Acceptance.SHA256 = (Get-FileHash -LiteralPath $f.ProofPath).Hash.ToLowerInvariant()
        } }
    )) {
        $directory = Join-Path $temporary ($case.Name.Replace(' ', '-'))
        $fixture = New-MsysReaderFixture $directory
        $null = & $case.Mutate $fixture
        [IO.File]::WriteAllText($fixture.Manifest, ($fixture.Data | ConvertTo-Json -Depth 10))
        $rejected = $false
        try { $null = & $reader -Prefix $fixture.Prefix -Manifest $fixture.Manifest } catch {
            if ($_.Exception.Message -notlike "Invalid native MSYS contract: $($case.Error)") { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw "Reader admitted a nonexecutable fixture: $($case.Name)" }
        "PASS: reader rejects $($case.Name), no compiler execution"
    }
    $fixture = New-MsysReaderFixture (Join-Path $temporary 'context-rejection')
    $contextOutput = Join-Path $temporary 'must-not-be-created'
    $rejected = $false
    try {
        $null = & "$PSScriptRoot\..\..\.github\scripts\msys\new-package-context.ps1" `
            -Prefix $fixture.Prefix -Manifest $fixture.Manifest -MsysRoot 'C:\unreached-bootstrap' `
            -OutputDirectory $contextOutput -Jobs 1
    } catch {
        if ($_.Exception.Message -notlike 'Invalid native MSYS contract: *acceptance is not a passing native MSYS*') { throw }
        $rejected = $true
    }
    if (-not $rejected -or (Test-Path -LiteralPath $contextOutput)) {
        throw 'Unqualified input must not create a package context.'
    }
    'PASS: unqualified compiler cannot prepare package context or create output'
    $rejected = $false
    try {
        $null = & "$PSScriptRoot\..\..\.github\scripts\msys\invoke-package.ps1" `
            -Prefix $fixture.Prefix -Manifest $fixture.Manifest -MsysRoot 'C:\unreached-bootstrap' `
            -PackageDirectory "$PSScriptRoot\..\package-controls" -OutputDirectory $contextOutput -Jobs 1
    } catch {
        if ($_.Exception.Message -notlike 'Invalid native MSYS contract: *acceptance is not a passing native MSYS*') { throw }
        $rejected = $true
    }
    if (-not $rejected -or (Test-Path -LiteralPath $contextOutput)) {
        throw 'Unqualified input must not reach MSYS package execution.'
    }
    'PASS: unqualified compiler cannot reach package runner or create output'
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
