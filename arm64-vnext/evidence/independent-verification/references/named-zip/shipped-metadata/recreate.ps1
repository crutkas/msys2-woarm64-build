param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
& "$PSScriptRoot\mingwarm64\bin\python.exe" -B "$PSScriptRoot\recreation\artifact.py" zip --root $PSScriptRoot --output $Output
exit $LASTEXITCODE
