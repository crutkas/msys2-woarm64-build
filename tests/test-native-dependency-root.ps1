#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Compiler,
    [Parameter(Mandatory)][string] $DependencyPrefix,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Dependency root control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$source = "$PSScriptRoot\native-dependency-root.c"
$header = Join-Path $DependencyPrefix 'include\expat.h'
$dll = Join-Path $DependencyPrefix 'bin\libexpat-1.dll'
foreach ($file in $header, $dll) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing real native Expat prerequisite: $file" }
}
$runs = @()
foreach ($case in @(
    @{Name='missing-include';Flags=@();Expected=1;Diagnostic='expat.h: No such file'},
    @{Name='missing-library';Flags=@('-idirafter',"$DependencyPrefix\include");Expected=1;Diagnostic='cannot find -lexpat'},
    @{Name='explicit-roots';Flags=@('-idirafter',"$DependencyPrefix\include","-L$DependencyPrefix\lib");Expected=0;Diagnostic=$null}
)) {
    $exe = "$OutputDirectory\$($case.Name).exe"
    $log = & $Compiler @($case.Flags) $source '-lexpat' '-o' $exe 2>&1
    $code = $LASTEXITCODE
    $log | Set-Content -LiteralPath "$OutputDirectory\$($case.Name).log" -Encoding utf8
    if ($code -ne $case.Expected -or ($case.Diagnostic -and ($log -join "`n") -notmatch $case.Diagnostic)) {
        throw "Unexpected native dependency-root result: $($case.Name), exit $code"
    }
    $runs += @{Name=$case.Name;Exit=$code;Flags=$case.Flags}
}
Copy-Item -LiteralPath $dll -Destination $OutputDirectory
$copied = Join-Path $OutputDirectory 'libexpat-1.dll'
if ((Get-FileHash -LiteralPath $copied).Hash -cne (Get-FileHash -LiteralPath $dll).Hash) {
    throw 'Expat dependency changed while being copied.'
}
& "$OutputDirectory\explicit-roots.exe"
if ($LASTEXITCODE -ne 0) { throw "Actual relocated native Expat consumer failed, raw exit $LASTEXITCODE" }
[ordered]@{
    Status='passed';Compiler=$Compiler;DependencyPrefix=$DependencyPrefix;Runs=$runs;ConsumerRawExit=0
    HeaderSHA256=(Get-FileHash -LiteralPath $header).Hash.ToLowerInvariant()
    DllSHA256=(Get-FileHash -LiteralPath $copied).Hash.ToLowerInvariant()
    Scope='Real native Expat prerequisite exercises include/library search roots; not a zlib package or OpenSSL admission'
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$OutputDirectory\result.json" -Encoding utf8
'PASS: actual separate dependency include/library roots and relocated native consumer'
