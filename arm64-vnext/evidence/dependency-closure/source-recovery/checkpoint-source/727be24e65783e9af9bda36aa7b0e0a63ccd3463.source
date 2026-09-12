#requires -Version 7.3
param(
    [Parameter(Mandatory)][ValidateSet('gcc', 'cmake', 'ninja', 'pkgconf', 'rust')][string] $Tool,
    [Parameter(Mandatory)][string] $Payload,
    [Parameter(Mandatory)][string] $Inventory,
    [Parameter(Mandatory)][string] $Provenance,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\cohort-inventory.ps1"
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Tool package output must be new.' }
foreach ($inputRoot in $Payload, $Provenance) {
    $protected = (Resolve-Path -LiteralPath $inputRoot).ProviderPath.TrimEnd('\')
    if ($output.StartsWith("$protected\", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Tool package output must be outside its immutable inputs.'
    }
}
$files = @(Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json)
Assert-CohortInventory $Payload $files
$originFiles = @(Get-CohortInventory $Provenance)
$proof = Get-Content -Raw -LiteralPath (Join-Path $Provenance 'origin.json') | ConvertFrom-Json
$version = @{ gcc = '15.0.1'; cmake = '4.4.3'; ninja = '1.13.2'; pkgconf = '3.0.5'; rust = '1.98.1' }[$Tool]
if ($proof.Tool -cne $Tool -or $proof.Version -cne $version -or
    $proof.Architecture -cne 'ARM64' -or $proof.Passed -ne $true) {
    throw 'Matching checked tool origin evidence is required.'
}
if ($Tool -eq 'gcc') {
    $headerDelta = $proof.PSObject.Properties['HeaderDeltaManifest']
    $descriptor = if ($headerDelta) { $proof.HeaderDeltaManifest } else { $proof.CohortManifest }
    if ((Get-FileHash -LiteralPath $descriptor.Path).Hash.ToLowerInvariant() -cne $descriptor.SHA256) {
        throw 'Compiler qualification descriptor changed.'
    }
    $reader = if ($headerDelta) { 'test-qualified-header-delta.ps1' } else { 'test-qualified-native-cohort.ps1' }
    $qualified = & (Join-Path $PSScriptRoot $reader) -Prefix $Payload -Manifest $descriptor.Path
    if ((& "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs $files) -cne $qualified.Epoch) {
        throw 'Compiler package inventory is not the qualified cohort.'
    }
} elseif ($Tool -eq 'pkgconf') {
    if ((Get-FileHash -LiteralPath $proof.ProducerReceipt.Path).Hash.ToLowerInvariant() -cne
        '29cc3d92eb29e354a1db2ca9b88ab731c0eba48c7eaeafdf7cc518bf593a2c09') {
        throw 'Native pkgconf producer receipt differs from the accepted source-build pin.'
    }
    $producer = Get-Content -Raw -LiteralPath $proof.ProducerReceipt.Path | ConvertFrom-Json -AsHashtable
    if ($producer.status -cne 'native-pkgconf-built-upstream-and-independent-controls-passed' -or
        $producer.source.version -cne $version -or $producer.build_host -cne 'windows-arm64-native' -or
        @($producer.commands | Where-Object {
            $expectedExit = if ($_.name -cin @('missing', 'unsatisfied-version')) { 1 } else { 0 }
            $_.exit -ne $expectedExit
        }).Count -or $producer.passed_tests.Count -ne 29) {
        throw 'Native pkgconf source-build controls are incomplete.'
    }
    $producerFiles = @($producer.files.GetEnumerator() | ForEach-Object {
        @{Path=$_.Key.Replace('/','\');SHA256=$_.Value.sha256}
    })
    Assert-CohortInventory $Payload $producerFiles
} elseif ($Tool -eq 'rust') {
    if ((Get-FileHash -LiteralPath $proof.Qualification.Path).Hash.ToLowerInvariant() -cne
        '12ffeaf77233e962326014e62648f8b3c3220e37fe7aa54cf8e053e88c0cba5b') {
        throw 'Native Rust bootstrap qualification differs from the accepted pin.'
    }
    $qualification = Get-Content -Raw -LiteralPath $proof.Qualification.Path | ConvertFrom-Json
    foreach ($binding in $qualification.Inventory, $qualification.Interop) {
        if ((Get-FileHash -LiteralPath $binding.Path).Hash.ToLowerInvariant() -cne $binding.SHA256) {
            throw 'Native Rust qualification evidence changed.'
        }
    }
    Assert-CohortInventory $Payload @(Get-Content -Raw -LiteralPath $qualification.Inventory.Path | ConvertFrom-Json)
    $interop = Get-Content -Raw -LiteralPath $qualification.Interop.Path | ConvertFrom-Json
    if ($interop.Status -cne 'native-rust-gcc-explicit-llvm-linker-interop-passed' -or
        $interop.GccRun.ExitCode -ne 0 -or $interop.RustRun.ExitCode -ne 0 -or
        $qualification.RustHost -cne 'aarch64-pc-windows-gnullvm' -or $qualification.Version -cne $version) {
        throw 'Native Rust GNU/GCC interoperability is incomplete.'
    }
} else {
    $expected = if ($Tool -eq 'cmake') {
        '7b410ddd00e24c7250eec7452da2348a4a70437aa87e9cda0a20d6a85662fcff'
    } else {
        'e52f0bdef9dfb1003229dbd6508a508c4073fd017247002adc66e5e806cb0391'
    }
    if ($proof.Archive.SHA256 -cne $expected -or (Get-FileHash -LiteralPath $proof.Archive.Path).Hash.ToLowerInvariant() -cne $expected) {
        throw 'Official ARM64 tool archive identity differs from its pin.'
    }
}
$required = switch ($Tool) {
    gcc { @('bin\gcc.exe', 'bin\g++.exe', 'share\licenses\gcc\COPYING3', 'share\licenses\gcc\COPYING.RUNTIME') }
    cmake { @('bin\cmake.exe', 'bin\ctest.exe', 'doc\cmake\LICENSE.rst') }
    ninja { @('bin\ninja.exe') }
    pkgconf { @('bin\pkgconf.exe', 'bin\pkg-config.exe', 'bin\libpkgconf-8.dll', 'share\licenses\pkgconf\COPYING') }
    rust { @('bin\rustc.exe', 'bin\cargo.exe', 'bin\libunwind.dll', 'share\doc\rust\licenses\MIT.txt', 'share\doc\rust\licenses\Apache-2.0.txt') }
}
foreach ($name in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Payload $name) -PathType Leaf)) { throw "Missing actual package payload: $name" }
}
if ($Tool -eq 'ninja' -and -not (Test-Path -LiteralPath (Join-Path $Provenance 'COPYING'))) { throw 'Ninja license is required.' }
New-Item -ItemType Directory -Path $output | Out-Null
if ($Tool -in 'cmake', 'ninja') {
    # Bind the payload to the pinned archive, not just a caller-supplied inventory.
    $archiveSource = Join-Path $output 'archive-source'
    New-Item -ItemType Directory -Path $archiveSource | Out-Null
    & "$env:SystemRoot\System32\tar.exe" -xf $proof.Archive.Path -C $archiveSource
    if ($LASTEXITCODE) { throw 'Official tool archive extraction failed.' }
    if ($Tool -eq 'cmake') {
        Assert-CohortInventory "$archiveSource\cmake-4.4.3-windows-arm64" $files
    } else {
        if ($files.Count -ne 1 -or $files[0].Path.Replace('\', '/') -cne 'bin/ninja.exe' -or
            (Get-FileHash -LiteralPath "$archiveSource\ninja.exe").Hash.ToLowerInvariant() -cne $files[0].SHA256) {
            throw 'Ninja payload is not the pinned official executable.'
        }
        $sourceHash = '974d6b2f4eeefa25625d34da3cb36bdcebe7fbce40f4c16ac0835fd1c0cbae17'
        if ($proof.SourceArchive.SHA256 -cne $sourceHash -or
            (Get-FileHash -LiteralPath $proof.SourceArchive.Path).Hash.ToLowerInvariant() -cne $sourceHash) {
            throw 'Ninja license source archive differs from its pin.'
        }
        & "$env:SystemRoot\System32\tar.exe" -xf $proof.SourceArchive.Path -C $archiveSource 'ninja-1.13.2/COPYING'
        if ($LASTEXITCODE) { throw 'Ninja license extraction failed.' }
        if ((Get-FileHash -LiteralPath "$archiveSource\ninja-1.13.2\COPYING").Hash -cne
            (Get-FileHash -LiteralPath (Join-Path $Provenance 'COPYING')).Hash) {
            throw 'Ninja license does not match the pinned source.'
        }
    }
    Remove-Item -LiteralPath $archiveSource -Recurse
}
Copy-Item -LiteralPath $Payload -Destination "$output\payload" -Recurse
Copy-Item -LiteralPath $Provenance -Destination "$output\provenance" -Recurse
Assert-CohortInventory "$output\payload" $files
Assert-CohortInventory $Payload $files
Assert-CohortInventory "$output\provenance" $originFiles
$lines = @($files | Sort-Object Path | ForEach-Object {
    if ($_.Path -match '[\r\n]') { throw 'Invalid payload path.' }
    "$($_.SHA256)  payload/$($_.Path.Replace('\','/'))"
})
[IO.File]::WriteAllText("$output\payload-files.sha256", ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
& "$env:SystemRoot\System32\tar.exe" -cf "$output\payload.tar" -C $output payload
if ($LASTEXITCODE) { throw 'Payload archive failed.' }
& "$env:SystemRoot\System32\tar.exe" -cf "$output\provenance.tar" -C $output provenance
if ($LASTEXITCODE) { throw 'Provenance archive failed.' }
$template = Join-Path $PSScriptRoot "..\..\packages\native-$Tool\PKGBUILD.in"
$text = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
if ($Tool -eq 'gcc' -and $headerDelta) {
    if ([regex]::Matches($text,'(?m)^pkgrel=1$').Count -ne 1) { throw 'Unexpected compiler package release template.' }
    $text = $text.Replace('pkgrel=1','pkgrel=2')
}
foreach ($entry in @(
    @{ Token = '@PAYLOAD_SHA256@'; Path = "$output\payload.tar" },
    @{ Token = '@FILES_SHA256@'; Path = "$output\payload-files.sha256" },
    @{ Token = '@PROVENANCE_SHA256@'; Path = "$output\provenance.tar" }
)) {
    if ([regex]::Matches($text, [regex]::Escape($entry.Token)).Count -ne 1) { throw 'Unexpected template token count.' }
    $text = $text.Replace($entry.Token, (Get-FileHash -LiteralPath $entry.Path).Hash.ToLowerInvariant())
}
[IO.File]::WriteAllText("$output\PKGBUILD", $text, [Text.UTF8Encoding]::new($false))
[ordered]@{
    Tool = $Tool; SourcePayload = $Payload; SourceInventory = $Inventory
    Files = $files.Count; Output = $output; PackagingOnly = $true
    TemplateSHA256 = (Get-FileHash -LiteralPath $template).Hash.ToLowerInvariant()
    RecipeSHA256 = (Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    Scope = 'Actual previously built/qualified native tools packaged with provenance; not a new compiler rebuild or a dummy provider'
} | ConvertTo-Json | Set-Content -LiteralPath "$output\preparation.json" -Encoding utf8
