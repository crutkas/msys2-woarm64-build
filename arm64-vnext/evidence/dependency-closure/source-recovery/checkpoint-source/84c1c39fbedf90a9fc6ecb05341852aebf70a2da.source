param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Identities,
    [Parameter(Mandatory)][string] $Proof,
    [Parameter(Mandatory)][string] $CacheHandoff
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$prefixPath = (Resolve-Path -LiteralPath $Prefix).ProviderPath.TrimEnd('\')
$identityPath = (Resolve-Path -LiteralPath $Identities).ProviderPath
$proofPath = (Resolve-Path -LiteralPath $Proof).ProviderPath
$handoffPath = (Resolve-Path -LiteralPath $CacheHandoff).ProviderPath
$proofData = Get-Content -Raw -LiteralPath $proofPath | ConvertFrom-Json
$handoff = Get-Content -Raw -LiteralPath $handoffPath | ConvertFrom-Json
$images = @(Get-Content -Raw -LiteralPath $identityPath | ConvertFrom-Json)
$epochPath = Join-Path $prefixPath 'share\toolchain-epochs\windows-cache\manifest.json'
$epochManifest = Get-Content -Raw -LiteralPath $epochPath | ConvertFrom-Json

function Get-Digest([string] $File) {
    (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($handoff.Status -ne 'windows-arm64-cache-runtime-fixed' -or
    [IO.Path]::GetFullPath($handoff.Prefixes.WindowsNative).TrimEnd('\') -ine $prefixPath) {
    throw 'Cache handoff does not qualify the requested native prefix.'
}
$proofHash = Get-Digest $proofPath
$proofBinding = @($handoff.Proofs | Where-Object {
    [IO.Path]::GetFullPath($_.Path) -ieq $proofPath -and $_.SHA256 -eq $proofHash
})
if ($proofBinding.Count -ne 1 -or $proofData.Passed -ne $true -or
    $proofData.Target -ne 'aarch64-w64-mingw32' -or
    [IO.Path]::GetFullPath($proofData.CompilerProcess.Image) -ine (Join-Path $prefixPath 'bin\gcc.exe') -or
    $proofData.CompilerProcess.Machine -ne '0xAA64' -or
    @($proofData.Runs).Count -eq 0 -or @($proofData.Runs | Where-Object ExitCode -ne 0).Count -ne 0) {
    throw 'Native qualification proof is missing, failed, or not bound by the cache handoff.'
}

$inputs = [Collections.Generic.List[object]]::new()
$seen = @{}
if ($epochManifest.LibrarySHA256 -ne $handoff.Archives.MinGW -or $epochManifest.GCC -ne $handoff.GCC) {
    throw 'Full-prefix manifest does not match the cache handoff source/library epoch.'
}
$changed = 0
foreach ($row in $epochManifest.BaselineFiles) {
    if ([IO.Path]::IsPathRooted($row.Path)) { throw "Expected relative manifest path: $($row.Path)" }
    $path = [IO.Path]::GetFullPath((Join-Path $prefixPath $row.Path))
    if (-not $path.StartsWith("$prefixPath\", [StringComparison]::OrdinalIgnoreCase) -or $seen.ContainsKey($path)) {
        throw "Duplicate or out-of-prefix toolchain input: $path"
    }
    $expected = $row.SHA256
    if ($row.Path -ceq $epochManifest.ChangedFile) {
        $expected = $epochManifest.LibrarySHA256
        $changed++
    }
    if ($expected -notmatch '^[0-9a-fA-F]{64}$' -or (Get-Digest $path) -ne $expected.ToLowerInvariant()) {
        throw "Qualified toolchain input hash mismatch: $path"
    }
    $seen[$path] = $expected.ToLowerInvariant()
    $inputs.Add([pscustomobject]@{ Path = $row.Path; SHA256 = $expected.ToLowerInvariant() })
}
if ($changed -ne 1) { throw 'Full-prefix manifest must replace exactly one libgcc input.' }
$metadata = @('build-log.txt', 'cache-source.sha256', 'gcc-patch.sha256', 'gcc-source.patch', 'manifest.json', 'recipe.txt')
foreach ($file in Get-ChildItem -LiteralPath $prefixPath -File -Recurse) {
    $relative = $file.FullName.Substring($prefixPath.Length + 1)
    if (-not $seen.ContainsKey($file.FullName) -and
        $relative -notin @($metadata | ForEach-Object { "share\toolchain-epochs\windows-cache\$_" })) {
        throw "Unqualified extra file in toolchain prefix: $relative"
    }
}
foreach ($row in @($images) + @($proofData.RuntimeInputs)) {
    $path = [IO.Path]::GetFullPath($row.Path)
    if (-not $seen.ContainsKey($path) -or $seen[$path] -ne $row.SHA256.ToLowerInvariant()) {
        throw "Qualification and full-prefix inventory disagree: $path"
    }
}
foreach ($image in $images) {
    if ($image.Machine -ne '0xAA64' -or $image.NativeArm64 -ne $true) {
        throw "Non-native executable in qualification inventory: $($image.Path)"
    }
}
foreach ($tool in 'gcc.exe', 'g++.exe', 'ar.exe', 'as.exe', 'ld.exe', 'ranlib.exe', 'windres.exe', 'strip.exe', 'objcopy.exe') {
    if (-not $seen.ContainsKey((Join-Path $prefixPath "bin\$tool"))) {
        throw "Qualification inventory omits required tool: $tool"
    }
}
$libgcc = @($proofData.RuntimeInputs | Where-Object Name -eq 'libgcc.a')
if ($libgcc.Count -ne 1 -or $libgcc[0].SHA256 -ne $handoff.Archives.MinGW) {
    throw 'Runtime input libgcc.a does not match the qualified cache-repair epoch.'
}
foreach ($name in 'crt2.o', 'crt2u.o', 'libstdc++.a', 'libwinpthread.a', 'libmingw32.a', 'libmingwex.a', 'libmsvcrt.a') {
    if (@($proofData.RuntimeInputs | Where-Object Name -eq $name).Count -ne 1) {
        throw "Qualification omits required link input: $name"
    }
}
$descriptors = @(
    [pscustomobject]@{ Path = $identityPath; SHA256 = Get-Digest $identityPath },
    [pscustomobject]@{ Path = $proofPath; SHA256 = $proofHash },
    [pscustomobject]@{ Path = $handoffPath; SHA256 = Get-Digest $handoffPath },
    [pscustomobject]@{ Path = $epochPath; SHA256 = Get-Digest $epochPath }
)
$epoch = & "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs @($inputs)
[pscustomobject]@{
    Prefix = $prefixPath
    Epoch = $epoch
    Target = $proofData.Target
    Inputs = @($inputs)
    Descriptors = $descriptors
    Scope = 'Identity binding to supplied local qualification, not a new toolchain qualification'
}
