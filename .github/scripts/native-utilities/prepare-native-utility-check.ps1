param(
    [Parameter(Mandatory)][string]$Root
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\less\invoke-private-command.ps1"
$driver = Join-Path $Root 'dos2unix\transport'
$source = Join-Path $PSScriptRoot '..\..\..\tests\native-utilities\native-utility-exec.c'
$output = Join-Path $Root 'dos2unix\src\dos2unix-7.5.7\native-utility-exec.exe'
if (Test-Path -LiteralPath $output) { throw 'Test-only native exec output must be new.' }
New-Item -ItemType Directory -Path $driver -Force | Out-Null
Copy-Item -LiteralPath "$PSScriptRoot\NativeUtilityTransport.pm" -Destination $driver
Invoke-LessPrivateCommand -Name 'dos2unix-compile-native-exec-control' `
    -Executable "$Root\compiler\bin\aarch64-pc-cygwin-gcc.exe" -Root $Root `
    -Arguments @('-O2', '-g', '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2',
                 (Resolve-Path -LiteralPath $source).Path, '-o', $output)
