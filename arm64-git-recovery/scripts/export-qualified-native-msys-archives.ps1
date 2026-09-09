#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$handoffs = @(
    [ordered]@{
        path = 'C:\ap06-2160\msys-libxcrypt-package-02\libxcrypt-package-handoff-01.json'
        sha256 = '080860f3b73ff893574a6fcf98abc6e9380bcbf4693deaf6561d9bbe12022aa9'
    },
    [ordered]@{
        path = 'C:\ap06-2160\native-cygpath-package-02\cygpath-package-handoff-01.json'
        sha256 = 'e7e4b75bc5380ce4e688e06b52836f004a2ec49e7abc5d82f983450fd80d540e'
    },
    [ordered]@{
        path = 'C:\ap06-2160\native-msys-zlib-package-01\package-handoff-01.json'
        sha256 = '42a64acdb30a38f14e24cf58939ed070f07ccd1458647df8df4378ad58c70608'
    }
)

$archives = @(
    [ordered]@{
        name = 'libxcrypt'
        path = 'C:\ap06-2160\msys-libxcrypt-package-02\invocation\packages\libxcrypt-4.5.2-1-aarch64.pkg.tar.zst'
        sha256 = '088ad7afe49b41fe73886415b38b0b48089ae748dd945c50ec10f44775c83a98'
    },
    [ordered]@{
        name = 'libxcrypt-devel'
        path = 'C:\ap06-2160\msys-libxcrypt-package-02\invocation\packages\libxcrypt-devel-4.5.2-1-aarch64.pkg.tar.zst'
        sha256 = '9a06bd39e35e96d41c34047c278a9a3b5047946e83af5ea828ca26dc8cc0899b'
    },
    [ordered]@{
        name = 'cygpath'
        path = 'C:\ap06-2160\native-cygpath-package-02\invocation\packages\cygpath-3.6.10-1-aarch64.pkg.tar.zst'
        sha256 = 'af688ab25ce9a9bf9caf159302601e7ee0e0fea4597c30e0fda627a27d27ef84'
    },
    [ordered]@{
        name = 'zlib'
        path = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\packages\zlib-1.3.2-1-aarch64.pkg.tar.zst'
        sha256 = '901100b3e27679d20078045e01d39da07dc549dee5a18c44e13e26eb163d0da0'
    },
    [ordered]@{
        name = 'zlib-devel'
        path = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\packages\zlib-devel-1.3.2-1-aarch64.pkg.tar.zst'
        sha256 = 'd04ce84eea38aebc87a63031952ea68d326f9fc5db13a00cbe841a640e5e7775'
    }
)

function Get-Sha256([string] $Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

foreach ($item in @($handoffs) + @($archives)) {
    if (-not (Test-Path -LiteralPath $item.path -PathType Leaf)) {
        throw "Qualified input is missing: $($item.path)"
    }
    $actual = Get-Sha256 $item.path
    if ($actual -cne $item.sha256) {
        throw "Qualified input changed: $($item.path); expected $($item.sha256), got $actual"
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
New-Item -ItemType Directory -Path $output, "$output\packages" | Out-Null

$packages = foreach ($archive in $archives) {
    $destination = Join-Path "$output\packages" ([IO.Path]::GetFileName($archive.path))
    Copy-Item -LiteralPath $archive.path -Destination $destination
    if ((Get-Sha256 $destination) -cne $archive.sha256) {
        throw "Archive changed during intake: $($archive.name)"
    }
    [ordered]@{
        name = $archive.name
        path = "packages/$([IO.Path]::GetFileName($destination))"
        sha256 = $archive.sha256
    }
}

[ordered]@{
    schema = 1
    status = 'admitted-qualified-native-msys-archives-exported'
    packages = @($packages)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\export.json" -Encoding utf8

[ordered]@{
    schema = 1
    status = 'qualified-native-msys-archives-intaken'
    packages = @($packages)
    source_handoffs = $handoffs
    controls = [ordered]@{
        archive_bytes_unchanged = $true
        package_metadata_unchanged = $true
        installed_into_shared_prefix = $false
        compiler_jobs_started = 0
    }
    limitations = @(
        'These packages retain their original 1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16 runtime cohort.',
        'No compatibility claim is made against runtime d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d.',
        'The standalone cygpath split is preserved and is not relabeled as msys2-runtime.'
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\handoff.json" -Encoding utf8

[pscustomobject]@{
    Export = "$output\export.json"
    ExportSHA256 = Get-Sha256 "$output\export.json"
    Handoff = "$output\handoff.json"
    HandoffSHA256 = Get-Sha256 "$output\handoff.json"
    Packages = $packages.Count
}
