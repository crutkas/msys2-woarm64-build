#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\..\.github\scripts\build-gettext-mingwarm64.ps1"
)
foreach ($required in @(
    '[ValidateRange(1, 6)][int] $Jobs = 6',
    '[Parameter(Mandatory)][string] $LibtoolMsysPatch',
    '[Parameter(Mandatory)][string] $PythonTestCrlfPatch',
    '71132a3fb71e68245b8f2ac4e9e97137d3e5c02f415636eb508ae607bc01add7',
    'f0a94f0bde80f56a7dc079b9a22aaf3594915acd66fdd916e1508a10ccee506a',
    'E0FFBD975397F77A32AB76ECB6301D9E1BBEAC08',
    '94aed342463655ea6fdbf459a46add99c1158d7b9a0fc4a89ac69ac7c150c442',
    'e3377481d3934e8dc14ea49afe85ba74fb2b56837a403472e269a52d722ba42c',
    'ab07da5e02a758a3b6c277ef8732632d496eb007b57f5ccd374cdfc4b7b7cf6f',
    '36aeb014c1c872d2fcb84b47ed3ca78ef70f543d9ce23fd2b08b51e48f047976',
    'Version 1.0 - January 2026',
    '--prefix=/mingwarm64',
    '--with-libiconv-prefix=/mingwarm64',
    "'-DLOCALEDIR='",
    "'-DINSTALLDIR='",
    "'-DBINDIR='",
    "'-DLIBDIR='",
    "'-DLIBEXECDIR='",
    "'-DGETTEXTDATADIR='",
    "'-DPROJECTSDIR='",
    "'-DGETTEXTJAR='",
    'installMacroArgumentExclusions',
    "CPPFLAGS='-I/mingwarm64/include'",
    "LDFLAGS='-L/mingwarm64/lib'",
    '-fno-omit-frame-pointer',
    '-mno-omit-leaf-frame-pointer',
    '5a52e4ef64b1db22b7aa36b736407601577ff338ebb3289f1e06ff47326dff15',
    'b2696cc54b2cd26dc6d50885e3256ec13add9617823bd5c782c3625763b4d0b0',
    "build-aux\ltmain.sh",
    "libtextstyle\build-aux\ltmain.sh",
    'func_convert_core_msys_to_w32_with_cygpath_result',
    'Gettext bundled-libtool patch token count changed',
    'Gettext native-Python test patch context changed',
    '[Text.Encoding]::Latin1.GetString',
    '[Text.Encoding]::Latin1.GetBytes',
    "LC_ALL=C tr -d '\r' < prog.tmp > prog.out",
    'workingCopy',
    'appliedPatches',
    'originalPatchSourceHashes',
    'patchedSourceHashes',
    '-ffile-prefix-map=$sourceMsys=/usr/src/gettext-1.0',
    '-fdebug-prefix-map=$outputMsys/build=/usr/src/gettext-1.0-build',
    'retainArm64FramePointers',
    "make -j`$Jobs check",
    "DESTDIR='`$outputMsys/stage'",
    "logs/configure.log' 2>&1",
    'gettext-1.0-canonical-prefix-built-tested-staged'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext builder lost invariant: $required"
    }
}
if ($script.Contains('| tee', [StringComparison]::Ordinal)) {
    throw 'Gettext builder must not pipe long-running output through tee.'
}
if ($script.Contains("MSYS2_ARG_CONV_EXCL='*'", [StringComparison]::Ordinal)) {
    throw 'Gettext builder must preserve conversion for real filesystem arguments.'
}

'PASS: gettext builder is source-bound, canonical-prefix, six-job bounded, and SIGPIPE-safe'
