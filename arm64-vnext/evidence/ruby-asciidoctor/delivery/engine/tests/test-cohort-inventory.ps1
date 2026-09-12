param([Parameter(Mandatory)][string] $OutputDirectory)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\.github\scripts\cohort-inventory.ps1"
$temporary = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $temporary) { throw 'Control output directory must be new.' }
New-Item -ItemType Directory -Path $temporary | Out-Null
& {
    $path = Join-Path $temporary 'input.txt'
    [IO.File]::WriteAllText($path, 'original')
    $inventory = @(Get-CohortInventory $temporary)
    Assert-CohortInventory $temporary $inventory
    'PASS: exact cohort accepted'
    [IO.File]::WriteAllText($path, 'changed')
    $rejected = $false
    try { Assert-CohortInventory $temporary $inventory } catch {
        if ($_.Exception.Message -notlike 'Cohort input changed:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Changed file accepted.' }
    'PASS: changed input rejected'
    [IO.File]::WriteAllText($path, 'original')
    [IO.File]::WriteAllText((Join-Path $temporary 'extra.txt'), 'extra')
    $rejected = $false
    try { Assert-CohortInventory $temporary $inventory } catch {
        if ($_.Exception.Message -notlike 'Cohort file set changed:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Unlisted file accepted.' }
    'PASS: unlisted input rejected'
    foreach ($case in @(
        @{ Name = 'traversal'; Rows = @(@{ Path = '..\outside'; SHA256 = 'a' * 64 }) },
        @{ Name = 'absolute'; Rows = @(@{ Path = 'C:\outside'; SHA256 = 'a' * 64 }) },
        @{ Name = 'digest'; Rows = @(@{ Path = 'input.txt'; SHA256 = 'bad' }) },
        @{ Name = 'duplicate'; Rows = @($inventory[0], $inventory[0]) }
    )) {
        $rejected = $false
        try { Assert-CohortInventory $temporary $case.Rows } catch {
            if ($_.Exception.Message -notlike 'Invalid cohort inventory entry:*') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'Invalid inventory accepted.' }
        "PASS: invalid $($case.Name) inventory rejected"
    }
}
