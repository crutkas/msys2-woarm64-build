[CmdletBinding()]
param(
    [string]$Output = 'C:\ap11-native-provider-intake\operational-prefix-lineage-v1.json',
    [string]$Strings = 'C:\agtc-libs-01\sdk\bin\aarch64-pc-cygwin-strings.exe'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

function Extract-And-Verify {
    param(
        [Parameter(Mandatory)]
        [string]$Archive,
        [Parameter(Mandatory)]
        [string]$ArchiveHash,
        [Parameter(Mandatory)]
        [string]$RelativePath,
        [Parameter(Mandatory)]
        [string]$FileHash,
        [Parameter(Mandatory)]
        [string]$Destination
    )

    Assert-FileHash -Path $Archive -Expected $ArchiveHash
    New-Item -ItemType Directory -Path $Destination | Out-Null
    & tar -xf $Archive -C $Destination $RelativePath
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $RelativePath from $Archive"
    }
    $path = Join-Path $Destination ($RelativePath -replace '/', '\')
    Assert-FileHash -Path $path -Expected $FileHash
    return $path
}

if (Test-Path -LiteralPath $Output) {
    throw "Versioned lineage receipt already exists: $Output"
}

$audit = 'C:\ap11-native-provider-intake\audit-v12-revoked-free.json'
$curlArchive = 'C:\ap09-ca5f\curl-packages-v2\export-12\packages\mingw-w64-aarch64-curl-8.22.0-1-any.pkg.tar.zst'
$tclArchive = 'C:\ap12-ca5f\python-provider-export-02\packages\mingw-w64-aarch64-tcl-8.6.13-1-any.pkg.tar.zst'
$curlConfigShared = 'C:\ap08-d207\curl-chain-01\build\curl-openssl-shared\lib\curl_config.h'
$curlConfigStatic = 'C:\ap08-d207\curl-chain-01\build\curl-openssl-static\lib\curl_config.h'
$curlVtlsSource = 'C:\ap08-d207\curl-chain-01\src\curl-8.22.0\lib\vtls\vtls_config.c'
$curlPathToolsSource = 'C:\ap08-d207\curl-chain-01\src\curl-8.22.0\lib\pathtools.c'

Assert-FileHash -Path $audit -Expected '7afd380831d93cbdb7b66751fbb1e991cb1b9a64bf6bf2ed78b99ff4dd134938'
Assert-FileHash -Path $curlConfigShared -Expected 'c5cd19fe8aedf5ed4fd9f159b54e348e00321fcac9e280b86ff3dbf9fe0a5272'
Assert-FileHash -Path $curlConfigStatic -Expected 'c5cd19fe8aedf5ed4fd9f159b54e348e00321fcac9e280b86ff3dbf9fe0a5272'
Assert-FileHash -Path $curlVtlsSource -Expected '74523ba55ddcb39581a526ce517fc4046d9a180926ecf5f1263f11e4fbd523b0'
Assert-FileHash -Path $curlPathToolsSource -Expected 'ebf471173f5ee9c4416c10a78760cea8afaf1a4a6e653977321e8547ce7bf3c0'

$scratch = 'C:\ap11-native-provider-intake\operational-prefix-lineage-temp'
if (Test-Path -LiteralPath $scratch) {
    Remove-Item -LiteralPath $scratch -Recurse -Force
}
New-Item -ItemType Directory -Path $scratch | Out-Null
try {
    $curlDll = Extract-And-Verify `
        -Archive $curlArchive `
        -ArchiveHash 'aa063bac5fc41496d69ce2508036ecf5af557e0d47c2ee3655c31fefb2d93378' `
        -RelativePath 'mingwarm64/bin/libcurl-4.dll' `
        -FileHash 'd060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669' `
        -Destination (Join-Path $scratch 'curl')
    $tclDll = Extract-And-Verify `
        -Archive $tclArchive `
        -ArchiveHash '72aa94a360986451ae10e52b21624ec8247bbf45a6d6711cbd0fbd19fe08d65e' `
        -RelativePath 'mingwarm64/bin/tcl86.dll' `
        -FileHash '28dfc8ae4069a3fbf31bd461aff0d1c01d9701fe219c70de199b0087943e22d9' `
        -Destination (Join-Path $scratch 'tcl')

    $curlPaths = @(
        & $Strings -a $curlDll |
            Select-String -Pattern '(?i)[A-Z]:[/\\][ -~]*mingwarm64[/\\]bin' |
            ForEach-Object { $_.Line.Trim() } |
            Sort-Object -Unique
    )
    $tclPaths = @(
        & $Strings -a $tclDll |
            Select-String -Pattern (
                '(?i)[A-Z]:[/\\][ -~]*mingwarm64[/\\]' +
                '(?:bin|lib[/\\]tcl|share[/\\]man)'
            ) |
            ForEach-Object { $_.Line.Trim() } |
            Sort-Object -Unique
    )
    if ($curlPaths -notcontains 'C:/ap08-d207/curl-chain-01/variants/openssl/prefix/mingwarm64/bin') {
        throw 'libcurl operational bindir evidence is missing'
    }
    foreach ($expected in @(
        'C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/bin',
        'C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/lib/tcl8.6',
        'C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/share/man'
    )) {
        if ($tclPaths -notcontains $expected) {
            throw "Tcl operational path evidence is missing: $expected"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $scratch) {
        Remove-Item -LiteralPath $scratch -Recurse -Force
    }
}

[ordered]@{
    schema = 1
    status = 'operational-private-prefix-source-lineage-confirmed'
    audit = [ordered]@{
        path = $audit
        sha256 = Get-Hash $audit
    }
    curl = [ordered]@{
        package = [ordered]@{
            path = $curlArchive
            sha256 = Get-Hash $curlArchive
        }
        binary = [ordered]@{
            name = 'libcurl-4.dll'
            sha256 = 'd060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669'
            operational_paths = $curlPaths
        }
        generated_configuration = @(
            [ordered]@{
                path = $curlConfigShared
                sha256 = Get-Hash $curlConfigShared
                line = 41
                definition = '#define CURL_BINDIR "C:/ap08-d207/curl-chain-01/variants/openssl/prefix/mingwarm64/bin"'
            },
            [ordered]@{
                path = $curlConfigStatic
                sha256 = Get-Hash $curlConfigStatic
                line = 41
                definition = '#define CURL_BINDIR "C:/ap08-d207/curl-chain-01/variants/openssl/prefix/mingwarm64/bin"'
            }
        )
        source_behavior = @(
            [ordered]@{
                path = $curlVtlsSource
                sha256 = Get-Hash $curlVtlsSource
                lines = @('270', '283', '344', '358')
                behavior = 'CURL_BINDIR is passed to single_path_relocation_lib for CA path and bundle relocation.'
            },
            [ordered]@{
                path = $curlPathToolsSource
                sha256 = Get-Hash $curlPathToolsSource
                line = 578
                behavior = 'single_path_relocation_lib computes DLL-relative relocation from the compiled source path.'
            }
        )
        disposition = 'Pinned-source canonical-bindir rebuild required; archive repack cannot clear this behavior.'
    }
    tcl = [ordered]@{
        package = [ordered]@{
            path = $tclArchive
            sha256 = Get-Hash $tclArchive
        }
        binary = [ordered]@{
            name = 'tcl86.dll'
            sha256 = '28dfc8ae4069a3fbf31bd461aff0d1c01d9701fe219c70de199b0087943e22d9'
            operational_paths = $tclPaths
        }
        disposition = 'Pinned-source canonical-prefix rebuild required; archive repack cannot rewrite compiled Tcl installation keys.'
    }
    controls = [ordered]@{
        archives_modified = $false
        binaries_modified = $false
        source_modified = $false
        source_rebuilds_launched = $false
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $Output -Encoding utf8NoBOM

Get-Item -LiteralPath $Output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
