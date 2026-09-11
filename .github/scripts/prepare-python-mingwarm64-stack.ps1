#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceRoot,
    [Parameter(Mandatory)][string] $OutputRoot,
    [Parameter(Mandatory)][string] $PinnedCommit
)

$ErrorActionPreference = 'Stop'

$expectedCommit = 'f34f6df66a0a06157dd1b09dd1d1e026ce7c903c'
if ($PinnedCommit -cne $expectedCommit) {
    throw "Only the pinned WOA recipe commit $expectedCommit is accepted."
}

$expectedRecipes = [ordered]@{
    'mingw-w64-libtre'    = '0cf4ed46cf30890466fe733abfc60bf010d820e71e77e9349485a3c688e01dcd'
    'mingw-w64-libsystre' = '868c87ecfbda59b1eb1f67aeafd39e9ab3ab36b2785144043362092600a6b60c'
    'mingw-w64-mpdecimal' = '2e6a53b093bf4d1d82a2b83c859a272caccecb3795b83030d20c7574b5573c9d'
    'mingw-w64-ncurses'   = '8f87ab9cdb18044efcf4703a03593a82993f806bfd7d8c1b6e9d87a364c36072'
    'mingw-w64-sqlite3'   = '9c2e5800312dfd1a239bd7548505553677f84b5ef3152e382a02cc74cafb7b09'
    'mingw-w64-xz'        = '32ddcaefb16bd92c946c9497eb95ebceb5521070364c2a6d42b69e64482ee19b'
    'mingw-w64-tzdata'    = '6de41597bf2df1cf728a43cb330b6c87e4eab3981161e2c76c5266d462aaa28c'
    'mingw-w64-python'    = '155d256d8346498fb2afa881c13b9306f92b2a8b4a4d063ce589c68c99de34b1'
}
$mpdecimalMaintainedPatchName = '0003-mpdecimal-mingw-dll-thread-context.patch'
$mpdecimalPatchName = '0001-mingw-dll-thread-context.patch'
$mpdecimalPatch = (Resolve-Path -LiteralPath (
    Join-Path $PSScriptRoot "..\..\patches\runtime-providers\$mpdecimalMaintainedPatchName"
)).ProviderPath
$expectedMpdecimalPatchHash = 'd8782982c077ff0d425a83a2e486af3f2f16be4ec8d50ddbdb363b9ba5e4a86e'
if ((Get-FileHash -LiteralPath $mpdecimalPatch).Hash.ToLowerInvariant() -cne $expectedMpdecimalPatchHash) {
    throw 'Maintained mpdecimal MinGW TLS patch hash mismatch.'
}
$sqlitePatchName = '0004-wineditline-history-limit.patch'
$sqlitePatch = (Resolve-Path -LiteralPath (
    Join-Path $PSScriptRoot '..\..\patches\runtime-providers\0004-sqlite-wineditline-history-limit.patch'
)).ProviderPath
$expectedSqlitePatchHash = '0bb0b1baa910ca500782122c5c594a72d749e4a551a0d2026d95507449163c23'
if ((Get-FileHash -LiteralPath $sqlitePatch).Hash.ToLowerInvariant() -cne $expectedSqlitePatchHash) {
    throw 'Maintained SQLite wineditline compatibility patch hash mismatch.'
}
$pythonPatchName = '0123-mingw-pgo-link.patch'
$pythonPatch = (Resolve-Path -LiteralPath (
    Join-Path $PSScriptRoot '..\..\patches\runtime-providers\0005-python-mingw-pgo-link.patch'
)).ProviderPath
$expectedPythonPatchHash = '3d0c3282865dba72cd1dc83276cc09e909524949101f9af41efdc723d52eb3fd'
if ((Get-FileHash -LiteralPath $pythonPatch).Hash.ToLowerInvariant() -cne $expectedPythonPatchHash) {
    throw 'Maintained Python MinGW PGO link patch hash mismatch.'
}

function Replace-ExactlyOnce {
    param(
        [Parameter(Mandatory)][string] $Text,
        [Parameter(Mandatory)][string] $Old,
        [Parameter(Mandatory)][string] $New,
        [Parameter(Mandatory)][string] $Description
    )

    $normalizedOld = $Old.Replace("`r`n", "`n")
    $normalizedNew = $New.Replace("`r`n", "`n")
    if ([regex]::Matches($Text, [regex]::Escape($normalizedOld)).Count -ne 1) {
        throw "Expected exactly one $Description replacement."
    }
    $Text.Replace($normalizedOld, $normalizedNew)
}

$source = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw 'Prepared Python stack output must be new.'
}
if ($output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Prepared output must not be inside the immutable recipe source.'
}

$inventories = [ordered]@{}
foreach ($entry in $expectedRecipes.GetEnumerator()) {
    $recipeRoot = Join-Path $source $entry.Key
    $pkgbuild = Join-Path $recipeRoot 'PKGBUILD'
    if (-not (Test-Path -LiteralPath $pkgbuild)) {
        throw "Missing pinned recipe: $($entry.Key)"
    }
    if ((Get-FileHash -LiteralPath $pkgbuild).Hash.ToLowerInvariant() -cne $entry.Value) {
        throw "Pinned recipe hash mismatch: $($entry.Key)"
    }
    $inventories[$entry.Key] = @(
        Get-ChildItem -LiteralPath $recipeRoot -Recurse -File |
            ForEach-Object {
                [ordered]@{
                    Path = $_.FullName.Substring($recipeRoot.Length + 1)
                    SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()
                }
            }
    )
}

New-Item -ItemType Directory -Path $output | Out-Null
foreach ($name in $expectedRecipes.Keys) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $output $name) -Recurse
}
Copy-Item -LiteralPath $mpdecimalPatch -Destination (
    Join-Path $output "mingw-w64-mpdecimal\$mpdecimalPatchName"
)
Copy-Item -LiteralPath $sqlitePatch -Destination (
    Join-Path $output "mingw-w64-sqlite3\$sqlitePatchName"
)
Copy-Item -LiteralPath $pythonPatch -Destination (
    Join-Path $output "mingw-w64-python\$pythonPatchName"
)

$changes = [ordered]@{
    'mingw-w64-libtre' = @(
        @{
            Description = 'libtre dependency identities'
            Old = @'
makedepends=("${MINGW_PACKAGE_PREFIX}-cc" "git" "mingw-w64-x86_64-autotools" "${MINGW_PACKAGE_PREFIX}-gettext-tools")
depends=("${MINGW_PACKAGE_PREFIX}-gcc-libs" "${MINGW_PACKAGE_PREFIX}-gettext-runtime")
'@
            New = @'
makedepends=("${MINGW_PACKAGE_PREFIX}-cc" "git" "mingw-w64-x86_64-autotools"
             "mingw-w64-x86_64-gettext-tools")
depends=("${MINGW_PACKAGE_PREFIX}-gcc" "${MINGW_PACKAGE_PREFIX}-gettext")
'@
        }
    )
    'mingw-w64-libsystre' = @()
    'mingw-w64-mpdecimal' = @(
        @{
            Description = 'mpdecimal MINGWARM64 namespace'
            Old = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
            New = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
        },
        @{
            Description = 'mpdecimal dependency identities'
            Old = @'
depends=("${MINGW_PACKAGE_PREFIX}-gcc-libs")
makedepends=("${MINGW_PACKAGE_PREFIX}-autotools" "${MINGW_PACKAGE_PREFIX}-cc")
'@
            New = @'
depends=("${MINGW_PACKAGE_PREFIX}-gcc")
makedepends=("mingw-w64-x86_64-autotools" "${MINGW_PACKAGE_PREFIX}-cc")
'@
        },
        @{
            Description = 'mpdecimal complete test dependencies'
            Old = 'checkdepends=("wget")'
            New = 'checkdepends=("wget" "unzip")'
        },
        @{
            Description = 'mpdecimal maintained MinGW TLS patch source'
            Old = @'
source=("http://www.bytereef.org/software/${_realname}/releases/${_realname}-$pkgver.tar.gz")
sha256sums=('942445c3245b22730fd41a67a7c5c231d11cb1b9936b9c0f76334fb7d0b4468c')
'@
            New = @"
source=("http://www.bytereef.org/software/`${_realname}/releases/`${_realname}-`$pkgver.tar.gz"
        '$mpdecimalPatchName')
sha256sums=('942445c3245b22730fd41a67a7c5c231d11cb1b9936b9c0f76334fb7d0b4468c'
            '$expectedMpdecimalPatchHash')
"@
        },
        @{
            Description = 'mpdecimal maintained MinGW TLS patch application'
            Old = @'
  cd $srcdir/${_realname}-${pkgver}

  autoreconf -fiv
'@
            New = @'
  cd $srcdir/${_realname}-${pkgver}

  patch -Np1 -i "${srcdir}/0001-mingw-dll-thread-context.patch"
  autoreconf -fiv
'@
        },
        @{
            Description = 'mpdecimal shared C++ runtime ownership'
            Old = @'
build() {
  [[ -d "${srcdir}"/build-${MSYSTEM} ]] && rm -rf "${srcdir}"/build-${MSYSTEM}
'@
            New = @'
build() {
  CXXFLAGS="${CXXFLAGS//-static-libstdc++/}"
  [[ -d "${srcdir}"/build-${MSYSTEM} ]] && rm -rf "${srcdir}"/build-${MSYSTEM}
'@
        }
    )
    'mingw-w64-ncurses' = @(
        @{
            Description = 'ncurses retained signed source series'
            Old = @'
source=("https://invisible-mirror.net/archives/ncurses/current/${_realname}-${_base_ver}-${_date_rev}.tgz"{,.asc}
        002-ncurses-config-win-paths.patch
        ncurses-6.3-cflags-private.patch
        ncurses-6.3-pkgconfig.patch)
sha256sums=('cbeaf1d42c138711678e25f9945c97d6806ace510b090cd890fc70555c21b9bb'
            'SKIP'
            '5367d8f49aff92884b9daa014502df13e1812f1b7ee1b3a3cb18139f10039408'
            '3107029dfb807e338d34641d78329cd6725c58e6b873352621f4b9611a8380bf'
            'b8544a607dfbeffaba2b087f03b57ed1fa81286afca25df65f61b04b5f3b3738')
'@
            New = @'
_patch_series=(
  '20240504:66ab6dff7e3b8a58d5f9a40b71a2f3126a726f295f407739b4a5ef82b0c8f0e7'
  '20240511:0ca7e1749e6c3fd2ff121f1d4ed72ea9601bc8aa2b064661bfee11ad609b09ad'
  '20240518:d458f573cab563e13905076cf9c2e74e7d6144f68d5cfec7e6b6da8ccc5c9dd9'
  '20240519:830809eb19fb95dacb3d10ee0347f9a1f0c4eca7b7c73eb19d7889412e17e285'
  '20240525:75c7006f7a2e1983f5a0af4c47e2867f466b930eabde56d3357c59fd6da72cd9'
  '20240601:824d30d6b54f1539f74b89ac74cace92934eb6471e5f3e1d5b50727aeca0b8a4'
  '20240608:54560922af4f5419397dffeb0b8d2c0da66a38e0905650108ae6487ad9636662'
  '20240615:3426e0ae68bd3eebed318a92b296d3265f80df857d3dfa0600fc9be86def7453'
  '20240622:4bf932099c0137933efa6df797fb73b7b46613f2d7dc25fdbf45fa8e91a39eb4'
  '20240629:a95a36939e906c894799573d1ed5d0331be91358e0b95e21ebc90459d2130d90'
  '20240706:61eccca59e6406ca3d9e0c31424b4ad1f84517a4c5b3a25e6b489c14c04fd516'
  '20240713:d24355ac443d65cfaccd56cfc893c0fb0fc0f543c3eee20551be5020a1cf7052'
  '20240720:3ce0b2a9f8bf6941017ea6b5c4f35008357e8be938f05c367ecb59354bd3abdc'
  '20240727:267960964891d41086b19a558925236828248d5b8aef6acaaad835f9e20f49f2'
  '20240810:3666eb8ed5caa1b531c579af3d8a283a13eed99387f57933d4b2dbe757c17199'
  '20240817:5742cc5bd090385e42c1b72933bbf272b5b8db37af7a077cb49cb649eec145d2'
  '20240824:ddbb4213651f93361a0caabe001a9b8a963b93be8294b00a84a50aab16846cec'
  '20240831:d5295d74f181b55fd26fbf9d9ebeddb4894e030ff597cc032b2cb1406fca203b'
  '20240914:3a55e4751c505c460b9596da592cc5c2e6f708d08afc1ec88e544f9e60c938fa'
  '20240922:8ebed5fe6b3421fef98516cff54d92b8bd2141a63dbc49819be2880bd340264d'
  '20240928:dffe2699ae43b1d0f4462bff2ac3c2a2dfe39e29ee4297a88999ed6eeb5e8066'
  '20241006:e6a283ea77b85a7725e5a4f5b3183e62708252439447203843ed3440500f9f97'
  '20241019:832e34161b350b7e8f4790c2808b81898ccdd3433ae094a32868e5178b188caf'
  '20241026:53869ee0e4e5bc918f26dc1fc7322f44cad95f5ed24146a651133ae14982348a'
  '20241102:177dfa598b2ad69d86126a8606917a31b4b9125ba264d41a727958dc55dcef38'
  '20241109:c9fe2d99b5043d79fa1318fe8e2bac97db3b8ae83e092291b1025b00ee00bf6d'
  '20241123:ef4acf678ce5b6e184f6923ace29cfb792420ae3029d0d31be4049635ee18ae3'
  '20241130:b718cff8cc0369219de26b7afbe2610856971f05c74ccef217e9990642d45161'
  '20241207:f83701e7f551e0472750ee234016c4a006a86d0b73c576bcd9cad1be80f5efb0'
  '20241214:c49b9716a8542dfe494d3fce8041a1fc960591e3998601142552ffe4d7356ef4'
  '20241221:813c07a7fd3cb0a65b73b6ffb9d21dd874fd7d7df750e59cd6838ade8721fd07'
  '20241228:a48046bc81d926383acd6da582091dbbadf67e71b048de1f0660227c00e95030'
)
source=("https://ftp.gnu.org/gnu/ncurses/${_realname}-${_base_ver}.tar.gz"{,.sig})
sha256sums=('136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6'
            'SKIP')
for _patch in "${_patch_series[@]}"; do
  _patch_date=${_patch%%:*}
  source+=("https://invisible-island.net/archives/ncurses/${_base_ver}/${_realname}-${_base_ver}-${_patch_date}.patch.gz"{,.asc})
  sha256sums+=("${_patch#*:}" 'SKIP')
done
source+=(002-ncurses-config-win-paths.patch
         ncurses-6.3-cflags-private.patch
         ncurses-6.3-pkgconfig.patch)
sha256sums+=('5367d8f49aff92884b9daa014502df13e1812f1b7ee1b3a3cb18139f10039408'
             '3107029dfb807e338d34641d78329cd6725c58e6b873352621f4b9611a8380bf'
             'b8544a607dfbeffaba2b087f03b57ed1fa81286afca25df65f61b04b5f3b3738')
'@
        },
        @{
            Description = 'ncurses dependency identities'
            Old = @'
depends=("${MINGW_PACKAGE_PREFIX}-gcc-libs"
         "${MINGW_PACKAGE_PREFIX}-gettext-runtime"
         "${MINGW_PACKAGE_PREFIX}-libsystre")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "mingw-w64-x86_64-autotools")
'@
            New = @'
depends=("${MINGW_PACKAGE_PREFIX}-gcc"
         "${MINGW_PACKAGE_PREFIX}-gettext"
         "${MINGW_PACKAGE_PREFIX}-libsystre")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "mingw-w64-x86_64-autotools")
'@
        },
        @{
            Description = 'ncurses reconstruct retained snapshot'
            Old = @'
prepare() {
  cd ${_realname}-${_base_ver}-${_date_rev}
'@
            New = @'
prepare() {
  cd ${_realname}-${_base_ver}
  for _patch in "${_patch_series[@]}"; do
    _patch_date=${_patch%%:*}
    gzip -cd "${srcdir}/${_realname}-${_base_ver}-${_patch_date}.patch.gz" | patch --binary -p1
  done
  cd ..
  mv "${_realname}-${_base_ver}" "${_realname}-${_base_ver}-${_date_rev}"
  cd ${_realname}-${_base_ver}-${_date_rev}
'@
        }
    )
    'mingw-w64-sqlite3' = @(
        @{
            Description = 'sqlite MINGWARM64 namespace'
            Old = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
            New = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
        },
        @{
            Description = 'sqlite dependency identities'
            Old = @'
depends=($([[ ${CARCH} == i686 ]] || echo "${MINGW_PACKAGE_PREFIX}-readline")
         "${MINGW_PACKAGE_PREFIX}-zlib")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "${MINGW_PACKAGE_PREFIX}-autotools"
             "${MINGW_PACKAGE_PREFIX}-tcl")
'@
            New = @'
depends=($([[ ${CARCH} == i686 ]] || echo "${MINGW_PACKAGE_PREFIX}-wineditline")
         "${MINGW_PACKAGE_PREFIX}-zlib")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "mingw-w64-x86_64-autotools"
             "${MINGW_PACKAGE_PREFIX}-pkgconf"
             "${MINGW_PACKAGE_PREFIX}-tcl")
'@
        },
        @{
            Description = 'sqlite maintained wineditline patch source'
            Old = @'
        README.md.in
        LICENSE)
'@
            New = @"
        README.md.in
        LICENSE
        '$sqlitePatchName')
"@
        },
        @{
            Description = 'sqlite maintained wineditline patch checksum'
            Old = "            '0b76663a90e034f3d7f2af5bfada4cedec5ebc275361899eccc5c18e6f01ff1f')"
            New = @"
            '0b76663a90e034f3d7f2af5bfada4cedec5ebc275361899eccc5c18e6f01ff1f'
            '$expectedSqlitePatchHash')
"@
        },
        @{
            Description = 'sqlite maintained wineditline patch application'
            Old = @'
prepare() {
  cd "sqlite-src-${_amalgamationver}"
  patch -p1 -i "${srcdir}/0001-sqlite-pcachetrace-include-sqlite3.patch"
'@
            New = @'
prepare() {
  cd "sqlite-src-${_amalgamationver}"
  patch -p1 -i "${srcdir}/0004-wineditline-history-limit.patch"
  patch -p1 -i "${srcdir}/0001-sqlite-pcachetrace-include-sqlite3.patch"
'@
        },
        @{
            Description = 'sqlite wineditline configure mode'
            Old = '_extra_config+=("--enable-readline" "--enable-tcl")'
            New = '_extra_config+=("--enable-editline" "--disable-readline" "--enable-tcl")'
        },
        @{
            Description = 'sqlite remove GNU readline configuration'
            Old = @'
    --disable-editline \
    --enable-all \
    --enable-session \
    --with-readline-inc=-I${MINGW_PREFIX}/include \
    --with-tcl=${MINGW_PREFIX}/lib \
'@
            New = @'
    --enable-all \
    --enable-session \
    --with-tcl=${MINGW_PREFIX}/lib \
'@
        },
        @{
            Description = 'sqlite extension target include path'
            Old = @'
  # build extensions
  ./config.status --file=ext/misc/Makefile:../Makefile.ext.in
  make -C ext/misc
'@
            New = @'
  # build extensions
  ./config.status --file=ext/misc/Makefile:../Makefile.ext.in
  make -C ext/misc CPPFLAGS="-I../.. -I../../../sqlite-src-${_amalgamationver}/src -I${MINGW_PREFIX}/include"
'@
        },
        @{
            Description = 'sqlite required quick tests'
            Old = '  make quicktest || warning "Tests failed"'
            New = '  make quicktest'
        }
    )
    'mingw-w64-xz' = @(
        @{
            Description = 'xz MINGWARM64 namespace'
            Old = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
            New = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
        },
        @{
            Description = 'xz dependency identities'
            Old = @'
depends=("${MINGW_PACKAGE_PREFIX}-gettext-runtime")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "${MINGW_PACKAGE_PREFIX}-autotools"
             "${MINGW_PACKAGE_PREFIX}-gettext-tools"
             $([[ ${CARCH} == i686 ]] || echo "${MINGW_PACKAGE_PREFIX}-doxygen")
             "po4a")
'@
            New = @'
depends=("${MINGW_PACKAGE_PREFIX}-gettext")
makedepends=("${MINGW_PACKAGE_PREFIX}-cc"
             "mingw-w64-x86_64-autotools"
             "mingw-w64-x86_64-gettext-tools"
             "mingw-w64-x86_64-doxygen" "po4a")
'@
        },
        @{
            Description = 'xz isolated x64 autotools'
            Old = './autogen.sh'
            New = 'PATH="/mingw64/bin:$PATH" ./autogen.sh'
        },
        @{
            Description = 'xz isolated x64 documentation generator'
            Old = '../${_realname}-${pkgver}/configure \'
            New = 'PATH="/mingw64/bin:$PATH" ../${_realname}-${pkgver}/configure \'
        },
        @{
            Description = 'xz retain x64 documentation generator during build'
            Old = @'
    "${_extra_config[@]}"

  make
}
'@
            New = @'
    "${_extra_config[@]}"

  PATH="/mingw64/bin:$PATH" make
}
'@
        }
    )
    'mingw-w64-tzdata' = @(
        @{
            Description = 'tzdata MINGWARM64 namespace'
            Old = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
            New = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
        }
    )
    'mingw-w64-python' = @(
        @{
            Description = 'Python MINGWARM64 namespace'
            Old = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
            New = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
        },
        @{
            Description = 'Python GCC runtime ownership'
            Old = 'depends=("${MINGW_PACKAGE_PREFIX}-gcc-libs"'
            New = 'depends=("${MINGW_PACKAGE_PREFIX}-gcc"'
        },
        @{
            Description = 'Python host generator dependencies'
            Old = @'
  "${MINGW_PACKAGE_PREFIX}-cc"
  "${MINGW_PACKAGE_PREFIX}-autotools"
  "autoconf-archive"
'@
            New = @'
  "${MINGW_PACKAGE_PREFIX}-cc"
  "mingw-w64-x86_64-autotools"
  "${MINGW_PACKAGE_PREFIX}-pkgconf"
  "autoconf-archive"
'@
        },
        @{
            Description = 'Python immutable commit patch regenerated checksum'
            Old = "            'b5c9ad802d6f3614aefbaec593c1c670dd1918b56e4ac9a682a6f23dfba579fa'"
            New = "            '6c52a31db51c8dc8146dd365629906ce5915db649aef3f98f89886fc15af9497'"
        },
        @{
            Description = 'Python maintained PGO patch source'
            Old = '        0122-fixup-add-python-config-sh.patch)'
            New = @'
        0122-fixup-add-python-config-sh.patch
        0123-mingw-pgo-link.patch)
'@
        },
        @{
            Description = 'Python maintained PGO patch checksum'
            Old = "            '66eca4fc8ca80fbe3510be4a7c9e460aaf01f6374dedfc7a13b993f8b73d36b3')"
            New = @"
            '66eca4fc8ca80fbe3510be4a7c9e460aaf01f6374dedfc7a13b993f8b73d36b3'
            '$expectedPythonPatchHash')
"@
        },
        @{
            Description = 'Python maintained PGO patch application'
            Old = @'
  0121-CI-update-actions.patch \
  0122-fixup-add-python-config-sh.patch
'@
            New = @'
  0121-CI-update-actions.patch \
  0122-fixup-add-python-config-sh.patch \
  0123-mingw-pgo-link.patch
'@
        },
        @{
            Description = 'Python in-tree extension smoke-test import library path'
            Old = @'
  ./python.exe "../Python-${pkgver}/mingw_smoketests.py"
  MSYSTEM= ./python.exe "../Python-${pkgver}/mingw_smoketests.py"
'@
            New = @'
  local _check_library_path="$PWD${LIBRARY_PATH:+:$LIBRARY_PATH}"
  LIBRARY_PATH="${_check_library_path}" ./python.exe "../Python-${pkgver}/mingw_smoketests.py"
  MSYSTEM= LIBRARY_PATH="${_check_library_path}" ./python.exe "../Python-${pkgver}/mingw_smoketests.py"
'@
        },
        @{
            Description = 'Python installed build metadata relocation'
            Old = @'
  # PEP668
  install -Dm644 "${srcdir}/EXTERNALLY-MANAGED" -t "${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}/"

  # fixup shebangs
'@
            New = @'
  # PEP668
  install -Dm644 "${srcdir}/EXTERNALLY-MANAGED" -t "${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}/"

  local _installed_config="${MINGW_PREFIX}/lib/python${_pybasever}/config-${_pybasever}"
  local _config_makefile="${pkgdir}${_installed_config}/Makefile"
  local _sysconfig_data="${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}/_sysconfigdata__win32_.py"
  local _build_prefix_native
  local _source_native
  local _build_native
  _build_prefix_native="$(cygpath -am "${MINGW_PREFIX}")"
  _source_native="$(cygpath -am "${srcdir}/Python-${pkgver}")"
  _build_native="$(cygpath -am "${srcdir}/build-${MSYSTEM}")"

  sed -i \
    -e "s|${_source_native}|${_installed_config}|g" \
    -e "s|${_build_native}|${_installed_config}|g" \
    -e "s|${srcdir}/Python-${pkgver}|${_installed_config}|g" \
    -e "s|${srcdir}/build-${MSYSTEM}|${_installed_config}|g" \
    -e "s|${_build_prefix_native}|${MINGW_PREFIX}|g" \
    "${_config_makefile}" "${_sysconfig_data}"
  find "${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}" -type d -name __pycache__ -prune -exec rm -rf {} +
  ./python.exe -c "import compileall, re, sys; excluded = re.compile(r'[/\\\\](?:test|tests)[/\\\\]'); raise SystemExit(not compileall.compile_dir(sys.argv[1], quiet=1, force=True, optimize=[0, 1, 2], rx=excluded, stripdir=sys.argv[2], prependdir='${MINGW_PREFIX}/lib/python${_pybasever}', workers=6))" \
    "$(cygpath -am "${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}")" \
    "$(cygpath -am "${pkgdir}${MINGW_PREFIX}/lib/python${_pybasever}")"
  strip --strip-debug "${pkgdir}${_installed_config}/python.o"

  # fixup shebangs
'@
        },
        @{
            Description = 'Python post-check relocatable getpath relink'
            Old = @'
  make -j1 install DESTDIR="${pkgdir}"
'@
            New = @'
  rm -f Modules/getpath.o
  MSYS2_ARG_CONV_EXCL='-DPYTHONPATH=;-DPREFIX=;-DEXEC_PREFIX=;-DVPATH=' make Modules/getpath.o
  make build_all
  make -j1 install DESTDIR="${pkgdir}"
'@
        },
        @{
            Description = 'Python staged installed runtime qualification'
            Old = @'
  if [[ "${_primary_python}" != "yes" ]]; then
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3.exe
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3w.exe
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3-config
    rm "${pkgdir}${MINGW_PREFIX}"/bin/idle3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/pydoc3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/2to3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/libpython3.dll
    rm "${pkgdir}${MINGW_PREFIX}"/lib/libpython3.dll.a
    rm "${pkgdir}${MINGW_PREFIX}"/lib/pkgconfig/python3-embed.pc
    rm "${pkgdir}${MINGW_PREFIX}"/lib/pkgconfig/python3.pc
    rm "${pkgdir}${MINGW_PREFIX}"/share/man/man1/python3.1
  fi
'@
            New = @'
  if [[ "${_primary_python}" != "yes" ]]; then
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3.exe
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3w.exe
    rm "${pkgdir}${MINGW_PREFIX}"/bin/python3-config
    rm "${pkgdir}${MINGW_PREFIX}"/bin/idle3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/pydoc3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/2to3
    rm "${pkgdir}${MINGW_PREFIX}"/bin/libpython3.dll
    rm "${pkgdir}${MINGW_PREFIX}"/lib/libpython3.dll.a
    rm "${pkgdir}${MINGW_PREFIX}"/lib/pkgconfig/python3-embed.pc
    rm "${pkgdir}${MINGW_PREFIX}"/lib/pkgconfig/python3.pc
    rm "${pkgdir}${MINGW_PREFIX}"/share/man/man1/python3.1
  fi

  local _staged_python="${pkgdir}${MINGW_PREFIX}/bin/python${_pybasever}.exe"
  local _dependency_bin
  _dependency_bin="$(cygpath -am "${MINGW_PREFIX}/bin")"
  local _staged_check="import os, sys; os.add_dll_directory(r'${_dependency_bin}'); import _ssl, _sqlite3, _decimal, _ctypes, _bz2, _lzma, _curses, _tkinter; expected = os.path.dirname(os.path.dirname(sys.executable)); assert os.path.normcase(sys.prefix) == os.path.normcase(expected), (sys.prefix, expected)"
  "${_staged_python}" -I -c "${_staged_check}"
  MSYSTEM= "${_staged_python}" -I -c "${_staged_check}"
'@
        },
        @{
            Description = 'Python isolated x64 autoreconf'
            Old = '  autoreconf -vfi'
            New = '  PATH="/mingw64/bin:$PATH" autoreconf -vfi'
        }
    )
}

$results = @()
foreach ($name in $expectedRecipes.Keys) {
    $pkgbuild = Join-Path $output "$name\PKGBUILD"
    $text = [IO.File]::ReadAllText($pkgbuild).Replace("`r`n", "`n")
    foreach ($change in $changes[$name]) {
        $text = Replace-ExactlyOnce -Text $text -Old $change.Old -New $change.New -Description $change.Description
    }
    [IO.File]::WriteAllText($pkgbuild, $text, [Text.UTF8Encoding]::new($false))

    foreach ($member in $inventories[$name] | Where-Object Path -cne 'PKGBUILD') {
        $copied = Join-Path (Join-Path $output $name) $member.Path
        if ((Get-FileHash -LiteralPath $copied).Hash.ToLowerInvariant() -cne $member.SHA256) {
            throw "Prepared companion changed: $name/$($member.Path)"
        }
    }

    $results += [ordered]@{
        Name = $name
        SourcePKGBUILDSHA256 = $expectedRecipes[$name]
        PreparedPKGBUILDSHA256 = (Get-FileHash -LiteralPath $pkgbuild).Hash.ToLowerInvariant()
    }
}

[ordered]@{
    Status = 'python-stack-namespace-prepared-not-package-admitted'
    PinnedRepository = 'Windows-on-ARM-Experiments/MINGW-packages'
    PinnedCommit = $expectedCommit
    Source = $source
    Output = $output
    Recipes = $results
    Boundary = 'MSYS/x64 host generators are build-only under /usr and /mingw64; all package payloads remain MINGWARM64'
}
