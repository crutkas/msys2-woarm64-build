#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $SourceArchive,
    [Parameter(Mandatory)][string] $SourceSignature,
    [Parameter(Mandatory)][string] $SignatureVerificationLog,
    [Parameter(Mandatory)][string] $LibtoolMsysPatch,
    [Parameter(Mandatory)][string] $PythonTestCrlfPatch,
    [Parameter(Mandatory)][string] $IntegrationRoot,
    [Parameter(Mandatory)][string] $OutputRoot,
    [ValidateRange(1, 6)][int] $Jobs = 6
)

$ErrorActionPreference = 'Stop'

function Convert-ToMsysPath([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Only absolute drive paths are supported: $Path"
    }
    "/$($Matches[1].ToLowerInvariant())/$($Matches[2].Replace('\', '/'))"
}

$source = Get-Item -LiteralPath $SourceDirectory
$archive = Get-Item -LiteralPath $SourceArchive
$signature = Get-Item -LiteralPath $SourceSignature
$signatureLog = Get-Item -LiteralPath $SignatureVerificationLog
$libtoolPatch = Get-Item -LiteralPath $LibtoolMsysPatch
$pythonTestPatch = Get-Item -LiteralPath $PythonTestCrlfPatch
$integration = Get-Item -LiteralPath $IntegrationRoot
$sourceHashes = [ordered]@{
    'configure' = '94aed342463655ea6fdbf459a46add99c1158d7b9a0fc4a89ac69ac7c150c442'
    'configure.ac' = 'e2ad9a858d965506414b862f11e44ac745ef9d767e9ef5b1572ce60957b2053f'
    'gettext-runtime\configure' = 'e3377481d3934e8dc14ea49afe85ba74fb2b56837a403472e269a52d722ba42c'
    'gettext-runtime\configure.ac' = '6d1161beabc9758ba9df9f97769ad2914661d2261a9317acca53ed209bd825b2'
    'gettext-tools\configure' = 'ab07da5e02a758a3b6c277ef8732632d496eb007b57f5ccd374cdfc4b7b7cf6f'
    'gettext-tools\configure.ac' = '9794268868b81f0f56f5cf6e13544a62ee2c617a41a2425a977c21d9eb3374b5'
    'NEWS' = '36aeb014c1c872d2fcb84b47ed3ca78ef70f543d9ce23fd2b08b51e48f047976'
    '.tarball-version' = '5717e7c840171019a4eeab5b79a7f894a4986eaff93d04ec5b12c9a189f594bf'
}
$archiveHash = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$signatureHash = (Get-FileHash $signature.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$libtoolPatchHash = (Get-FileHash $libtoolPatch.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$pythonTestPatchHash =
    (Get-FileHash $pythonTestPatch.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($archiveHash -cne '71132a3fb71e68245b8f2ac4e9e97137d3e5c02f415636eb508ae607bc01add7' -or
    $signatureHash -cne 'f0a94f0bde80f56a7dc079b9a22aaf3594915acd66fdd916e1508a10ccee506a') {
    throw 'Official gettext 1.0 archive or detached signature hash changed.'
}
if ($libtoolPatchHash -cne '5a52e4ef64b1db22b7aa36b736407601577ff338ebb3289f1e06ff47326dff15') {
    throw 'Gettext bundled-libtool MSYS path patch hash changed.'
}
if ($pythonTestPatchHash -cne 'b2696cc54b2cd26dc6d50885e3256ec13add9617823bd5c782c3625763b4d0b0') {
    throw 'Gettext native-Python CRLF test patch hash changed.'
}
$signatureText = Get-Content $signatureLog.FullName -Raw
if (-not $signatureText.Contains(
    'VALIDSIG E0FFBD975397F77A32AB76ECB6301D9E1BBEAC08',
    [StringComparison]::Ordinal
)) {
    throw 'Gettext source signature verification evidence is not valid.'
}
foreach ($entry in $sourceHashes.GetEnumerator()) {
    $actual = (Get-FileHash (Join-Path $source.FullName $entry.Key) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $entry.Value) {
        throw "Retained gettext 1.0 source hash changed: $($entry.Key)"
    }
}
if ((Get-Content "$($source.FullName)\.tarball-version" -Raw).Trim() -cne '1.0' -or
    (Get-Content "$($source.FullName)\NEWS" -First 1) -cne 'Version 1.0 - January 2026') {
    throw 'Retained gettext source does not identify as GNU gettext 1.0.'
}
$bash = "$($integration.FullName)\usr\bin\bash.exe"
foreach ($required in $bash, "$($integration.FullName)\mingwarm64\bin\gcc.exe",
    "$($integration.FullName)\mingwarm64\bin\libiconv-2.dll") {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Integration prerequisite is missing: $required"
    }
}
if (Test-Path -LiteralPath $OutputRoot) {
    throw 'Gettext build output must be new.'
}

New-Item -ItemType Directory -Path "$OutputRoot\build", "$OutputRoot\stage",
    "$OutputRoot\logs", "$OutputRoot\source\gettext-1.0" | Out-Null
$sourceWork = Get-Item "$OutputRoot\source\gettext-1.0"
Get-ChildItem -LiteralPath $source.FullName -Force |
    Copy-Item -Destination $sourceWork.FullName -Recurse

$originalPatchSourceHashes = [ordered]@{}
$patchedSourceHashes = [ordered]@{}
foreach ($relativePath in 'build-aux\ltmain.sh', 'libtextstyle\build-aux\ltmain.sh') {
    $path = Join-Path $sourceWork.FullName $relativePath
    $originalPatchSourceHashes[$relativePath] =
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $text = [IO.File]::ReadAllText($path)
    $startMarker = 'func_convert_core_msys_to_w32_with_cygpath ()'
    $endMarker = '#end: func_convert_core_msys_to_w32_with_cygpath'
    $start = $text.IndexOf($startMarker, [StringComparison]::Ordinal)
    $end = $text.IndexOf($endMarker, $start, [StringComparison]::Ordinal)
    if ($start -lt 0 -or $end -lt 0) {
        throw "Gettext bundled-libtool patch context is missing or ambiguous: $relativePath"
    }
    $end += $endMarker.Length
    $functionText = $text.Substring($start, $end - $start)
    $oldToken = 'func_convert_core_msys_to_w32_result'
    $newToken = 'func_convert_core_msys_to_w32_with_cygpath_result'
    if ([regex]::Matches($functionText, [regex]::Escape($oldToken)).Count -ne 2 -or
        $functionText.Contains($newToken, [StringComparison]::Ordinal)) {
        throw "Gettext bundled-libtool patch token count changed: $relativePath"
    }
    $patchedFunction = $functionText.Replace(
        $oldToken,
        $newToken,
        [StringComparison]::Ordinal
    )
    [IO.File]::WriteAllText(
        $path,
        $text.Substring(0, $start) + $patchedFunction + $text.Substring($end),
        [Text.UTF8Encoding]::new($false)
    )
    $patchedSourceHashes[$relativePath] =
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
foreach ($test in @(
    [ordered]@{ path = 'gettext-tools\tests\lang-python-1'; program = 'prog1.py' },
    [ordered]@{ path = 'gettext-tools\tests\lang-python-2'; program = 'prog2.py' }
)) {
    $path = Join-Path $sourceWork.FullName $test.path
    $originalPatchSourceHashes[$test.path] =
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $text = [Text.Encoding]::Latin1.GetString([IO.File]::ReadAllBytes($path))
    foreach ($encoding in 'UTF-8', 'ISO-8859-1') {
        $old = "PYTHONIOENCODING=$encoding `$PYTHON $($test.program) 2 > prog.out || Exit 1"
        $new = @(
            "PYTHONIOENCODING=$encoding `$PYTHON $($test.program) 2 > prog.tmp || Exit 1",
            "  LC_ALL=C tr -d '\r' < prog.tmp > prog.out || Exit 1"
        ) -join "`n"
        if ($text.IndexOf($old, [StringComparison]::Ordinal) -lt 0 -or
            $text.IndexOf($old, [StringComparison]::Ordinal) -ne
                $text.LastIndexOf($old, [StringComparison]::Ordinal)) {
            throw "Gettext native-Python test patch context changed: $($test.path) $encoding"
        }
        $text = $text.Replace($old, $new, [StringComparison]::Ordinal)
    }
    [IO.File]::WriteAllBytes($path, [Text.Encoding]::Latin1.GetBytes($text))
    $patchedSourceHashes[$test.path] =
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$sourceMsys = Convert-ToMsysPath $sourceWork.FullName
$outputMsys = Convert-ToMsysPath $OutputRoot
$installMacroArgExclusions = @(
    '-DLOCALEDIR=',
    '-DINSTALLDIR=',
    '-DBINDIR=',
    '-DLIBDIR=',
    '-DLIBEXECDIR=',
    '-DGETTEXTDATADIR=',
    '-DPROJECTSDIR=',
    '-DGETTEXTJAR='
)
$argConversionExclusions = @(
    '--prefix=',
    '--with-libiconv-prefix='
) + $installMacroArgExclusions
$argConversionExclusionsText = $argConversionExclusions -join ';'
$command = @"
set -euo pipefail
export MSYSTEM=MINGWARM64 CHERE_INVOKING=1 PATH=/mingwarm64/bin:/usr/bin
export MSYS2_ARG_CONV_EXCL='$argConversionExclusionsText'
cd '$outputMsys/build'
'$sourceMsys/configure' \
  --prefix=/mingwarm64 \
  --build=aarch64-w64-mingw32 \
  --host=aarch64-w64-mingw32 \
  --enable-shared \
  --enable-static \
  --enable-threads=windows \
  --enable-relocatable \
  --with-libiconv-prefix=/mingwarm64 \
  CC=gcc CXX=g++ \
  CFLAGS='-O2 -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer -ffile-prefix-map=$sourceMsys=/usr/src/gettext-1.0 -fdebug-prefix-map=$outputMsys/build=/usr/src/gettext-1.0-build' \
  CXXFLAGS='-O2 -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer -ffile-prefix-map=$sourceMsys=/usr/src/gettext-1.0 -fdebug-prefix-map=$outputMsys/build=/usr/src/gettext-1.0-build' \
  CPPFLAGS='-I/mingwarm64/include' \
  LDFLAGS='-L/mingwarm64/lib' \
  lt_cv_deplibs_check_method=pass_all \
  > '$outputMsys/logs/configure.log' 2>&1
test -f gettext-runtime/intl/Makefile
test -f gettext-tools/Makefile
make -j$Jobs > '$outputMsys/logs/build.log' 2>&1
make -j$Jobs check > '$outputMsys/logs/check.log' 2>&1
make DESTDIR='$outputMsys/stage' install > '$outputMsys/logs/install.log' 2>&1
test -x '$outputMsys/stage/mingwarm64/bin/gettext.exe'
"@

& $bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Gettext configure/build/check/install failed with exit code $LASTEXITCODE."
}

$logs = foreach ($name in 'configure.log', 'build.log', 'check.log', 'install.log') {
    $path = Join-Path "$OutputRoot\logs" $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item $path).Length -eq 0) {
        throw "Gettext build evidence is missing or empty: $path"
    }
    [ordered]@{
        path = (Get-Item $path).FullName
        sha256 = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$receipt = [ordered]@{
    schema = 1
    status = 'gettext-1.0-canonical-prefix-built-tested-staged'
    target = 'MINGWARM64/aarch64-w64-mingw32'
    source = [ordered]@{
        path = $source.FullName
        version = '1.0'
        archive = $archive.FullName
        archiveSha256 = $archiveHash
        signature = $signature.FullName
        signatureSha256 = $signatureHash
        signerFingerprint = 'E0FFBD975397F77A32AB76ECB6301D9E1BBEAC08'
        signatureVerificationLog = $signatureLog.FullName
        signatureVerificationLogSha256 =
            (Get-FileHash $signatureLog.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        hashes = $sourceHashes
        workingCopy = $sourceWork.FullName
        appliedPatches = @(
            [ordered]@{
                path = $libtoolPatch.FullName
                sha256 = $libtoolPatchHash
                purpose = 'Correct bundled libtool MSYS-to-Windows cygpath result-variable assignment.'
            },
            [ordered]@{
                path = $pythonTestPatch.FullName
                sha256 = $pythonTestPatchHash
                purpose = 'Normalize native Windows Python CRLF output before exact locale-output comparison.'
            }
        )
        originalPatchSourceHashes = $originalPatchSourceHashes
        patchedSourceHashes = $patchedSourceHashes
    }
    jobs = $Jobs
    compilerPathPolicy = [ordered]@{
        retainArm64FramePointers = $true
        sourcePrefixMap = '/usr/src/gettext-1.0'
        buildPrefixMap = '/usr/src/gettext-1.0-build'
        installMacroArgumentExclusions = $installMacroArgExclusions
    }
    prefix = '/mingwarm64'
    stage = (Get-Item "$OutputRoot\stage\mingwarm64").FullName
    logs = @($logs)
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content "$OutputRoot\build-receipt.json" -Encoding utf8
$receipt
