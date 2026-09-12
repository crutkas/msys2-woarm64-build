#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 7; then
    echo "usage: $0 OUTPUT BZIP2_STAGE BZIP2_SOURCE PCRE2_STAGE PCRE2_SOURCE COMPILER_ROOT RECIPE_ROOT" >&2
    exit 2
fi

output="$(cygpath -u "$1")"
bzip2_stage="$(cygpath -u "$2")"
bzip2_source="$(cygpath -u "$3")"
pcre2_stage="$(cygpath -u "$4")"
pcre2_source="$(cygpath -u "$5")"
compiler_root="$(cygpath -u "$6")"
recipe_root="$(cygpath -u "$7")"
host_bin="$(dirname "$(command -v bsdtar)")"
bsdtar="$host_bin/bsdtar.exe"
zstd="$host_bin/zstd.exe"
strip="$compiler_root/bin/strip.exe"
builddate="$(date -u +%s)"
packager="GitHub Copilot native ARM64 recovery"

if test -e "$output"; then
    echo "fresh package output required: $output" >&2
    exit 3
fi

for required in \
    "$bzip2_stage/bin/bzip2.exe" \
    "$bzip2_stage/bin/msys-bz2-1.dll" \
    "$bzip2_stage/include/bzlib.h" \
    "$bzip2_source/LICENSE" \
    "$pcre2_stage/usr/bin/msys-pcre2-8-0.dll" \
    "$pcre2_stage/usr/bin/msys-pcre2-16-0.dll" \
    "$pcre2_stage/usr/bin/msys-pcre2-32-0.dll" \
    "$pcre2_stage/usr/bin/msys-pcre2-posix-3.dll" \
    "$pcre2_stage/usr/bin/pcre2grep.exe" \
    "$pcre2_stage/usr/include/pcre2.h" \
    "$pcre2_source/LICENCE.md" \
    "$strip" \
    "$recipe_root/PKGBUILD.bzip2.upstream" \
    "$recipe_root/PKGBUILD.pcre2.aarch64" \
    "$bsdtar" \
    "$zstd"; do
    if ! test -f "$required"; then
        echo "required package input missing: $required" >&2
        exit 4
    fi
done

umask 022
mkdir -p "$output"/{packages,roots}

new_root()
{
    local name=$1
    local root="$output/roots/$name"
    mkdir -p "$root"
    printf '%s\n' "$root"
}

copy_exec()
{
    local source=$1 destination=$2
    install -Dm755 "$source" "$destination"
}

copy_data()
{
    local source=$1 destination=$2
    install -Dm644 "$source" "$destination"
}

copy_tree()
{
    local source=$1 destination=$2
    mkdir -p "$destination"
    cp -a "$source"/. "$destination"/
}

strip_root()
{
    local root=$1 file
    while IFS= read -r -d '' file; do
        case "$file" in
        *.exe|*.dll)
            "$strip" --strip-unneeded "$file"
            ;;
        *.a)
            "$strip" -g "$file"
            ;;
        esac
    done < <(find "$root/usr" -type f \( -name '*.exe' -o -name '*.dll' -o -name '*.a' \) -print0)
}

write_metadata()
{
    local root=$1 name=$2 base=$3 version=$4 description=$5 url=$6 license=$7
    shift 7
    local size field value
    size="$(find "$root/usr" -type f -printf '%s\n' | awk '{ total += $1 } END { print total + 0 }')"
    {
        printf 'pkgname = %s\n' "$name"
        printf 'pkgbase = %s\n' "$base"
        printf 'pkgver = %s\n' "$version"
        printf 'pkgdesc = %s\n' "$description"
        printf 'url = %s\n' "$url"
        printf 'builddate = %s\n' "$builddate"
        printf 'packager = %s\n' "$packager"
        printf 'size = %s\n' "$size"
        printf 'arch = aarch64\n'
        printf 'license = %s\n' "$license"
        for field in "$@"; do
            value="${field#*:}"
            case "$field" in
            group:*) printf 'group = %s\n' "$value" ;;
            depend:*) printf 'depend = %s\n' "$value" ;;
            *)
                echo "unknown metadata field: $field" >&2
                exit 5
                ;;
            esac
        done
    } >"$root/.PKGINFO"

    {
        printf 'format = 2\n'
        printf 'pkgname = %s\n' "$name"
        printf 'pkgbase = %s\n' "$base"
        printf 'pkgver = %s\n' "$version"
        printf 'pkgarch = aarch64\n'
        printf 'packager = %s\n' "$packager"
        printf 'builddate = %s\n' "$builddate"
        printf 'builddir = /build\n'
        printf 'buildtool = native-msys-provider-recovery\n'
        printf 'buildenv = !distcc color !ccache check !sign\n'
        printf 'options = strip docs !libtool staticlibs emptydirs zipman purge !debug !lto\n'
    } >"$root/.BUILDINFO"
}

archive_package()
{
    local root=$1 name=$2 version=$3 archive
    archive="$output/packages/$name-$version-aarch64.pkg.tar.zst"
    (
        cd "$root"
        "$bsdtar" -czf .MTREE \
            --format=mtree \
            --options='!all,use-set,type,uid,gid,mode,time,size,md5,sha256,link' \
            .PKGINFO .BUILDINFO usr
        "$bsdtar" --uid 0 --gid 0 --uname root --gname root \
            -cf - .PKGINFO .BUILDINFO .MTREE usr |
            "$zstd" -q -19 -T1 -o "$archive"
    )
}

bzip2_root="$(new_root bzip2)"
for file in "$bzip2_stage"/bin/b*; do
    copy_exec "$file" "$bzip2_root/usr/bin/$(basename "$file")"
done
copy_tree "$bzip2_stage/share" "$bzip2_root/usr/share"
copy_data "$bzip2_source/LICENSE" "$bzip2_root/usr/share/licenses/bzip2/LICENSE"
strip_root "$bzip2_root"
write_metadata "$bzip2_root" bzip2 bzip2 1.0.8-4 \
    "A high-quality data compression program" "http://www.bzip.org" \
    "spdx:bzip2-1.0.6" group:compression depend:libbz2
archive_package "$bzip2_root" bzip2 1.0.8-4

libbz2_root="$(new_root libbz2)"
copy_exec "$bzip2_stage/bin/msys-bz2-1.dll" \
    "$libbz2_root/usr/bin/msys-bz2-1.dll"
strip_root "$libbz2_root"
write_metadata "$libbz2_root" libbz2 bzip2 1.0.8-4 \
    "A high-quality data compression program" "http://www.bzip.org" \
    "spdx:bzip2-1.0.6" group:compression group:libraries depend:gcc-libs
archive_package "$libbz2_root" libbz2 1.0.8-4

libbz2_devel_root="$(new_root libbz2-devel)"
copy_tree "$bzip2_stage/include" "$libbz2_devel_root/usr/include"
copy_tree "$bzip2_stage/lib" "$libbz2_devel_root/usr/lib"
strip_root "$libbz2_devel_root"
write_metadata "$libbz2_devel_root" libbz2-devel bzip2 1.0.8-4 \
    "Libbz2 headers and libraries" "http://www.bzip.org" \
    "spdx:bzip2-1.0.6" group:compression group:development depend:libbz2=1.0.8
archive_package "$libbz2_devel_root" libbz2-devel 1.0.8-4

pcre2_root="$(new_root pcre2)"
copy_exec "$pcre2_stage/usr/bin/pcre2grep.exe" \
    "$pcre2_root/usr/bin/pcre2grep.exe"
copy_exec "$pcre2_stage/usr/bin/pcre2test.exe" \
    "$pcre2_root/usr/bin/pcre2test.exe"
copy_tree "$pcre2_stage/usr/share" "$pcre2_root/usr/share"
copy_data "$pcre2_source/LICENCE.md" \
    "$pcre2_root/usr/share/licenses/pcre2/LICENSE.md"
strip_root "$pcre2_root"
write_metadata "$pcre2_root" pcre2 pcre2 10.48-1 \
    "A library that implements Perl 5-style regular expressions" \
    "https://www.pcre.org/" "spdx:BSD-3-Clause WITH PCRE2-exception" \
    depend:libreadline depend:libbz2 depend:zlib \
    depend:libpcre2_8=10.48 depend:libpcre2_16=10.48 \
    depend:libpcre2_32=10.48 depend:libpcre2posix=10.48
archive_package "$pcre2_root" pcre2 10.48-1

for width in 8 16 32; do
    runtime_root="$(new_root "libpcre2_$width")"
    copy_exec "$pcre2_stage/usr/bin/msys-pcre2-$width-0.dll" \
        "$runtime_root/usr/bin/msys-pcre2-$width-0.dll"
    strip_root "$runtime_root"
    write_metadata "$runtime_root" "libpcre2_$width" pcre2 10.48-1 \
        "A library that implements Perl 5-style regular expressions" \
        "https://www.pcre.org/" "spdx:BSD-3-Clause WITH PCRE2-exception" \
        group:libraries depend:gcc-libs
    archive_package "$runtime_root" "libpcre2_$width" 10.48-1
done

pcre2_posix_root="$(new_root libpcre2posix)"
copy_exec "$pcre2_stage/usr/bin/msys-pcre2-posix-3.dll" \
    "$pcre2_posix_root/usr/bin/msys-pcre2-posix-3.dll"
strip_root "$pcre2_posix_root"
write_metadata "$pcre2_posix_root" libpcre2posix pcre2 10.48-1 \
    "A library that implements Perl 5-style regular expressions" \
    "https://www.pcre.org/" "spdx:BSD-3-Clause WITH PCRE2-exception" \
    group:libraries depend:libpcre2_8=10.48
archive_package "$pcre2_posix_root" libpcre2posix 10.48-1

pcre2_devel_root="$(new_root pcre2-devel)"
copy_exec "$pcre2_stage/usr/bin/pcre2-config" \
    "$pcre2_devel_root/usr/bin/pcre2-config"
copy_tree "$pcre2_stage/usr/include" "$pcre2_devel_root/usr/include"
mkdir -p "$pcre2_devel_root/usr/lib"
find "$pcre2_stage/usr/lib" -maxdepth 1 -type f \
    \( -name '*.a' -o -name '*.dll.a' \) \
    -exec cp -p '{}' "$pcre2_devel_root/usr/lib/" \;
copy_tree "$pcre2_stage/usr/lib/pkgconfig" \
    "$pcre2_devel_root/usr/lib/pkgconfig"
strip_root "$pcre2_devel_root"
write_metadata "$pcre2_devel_root" pcre2-devel pcre2 10.48-1 \
    "PCRE headers and libraries" "https://www.pcre.org/" \
    "spdx:BSD-3-Clause WITH PCRE2-exception" group:development \
    depend:libpcre2_8=10.48 depend:libpcre2_16=10.48 \
    depend:libpcre2_32=10.48 depend:libpcre2posix=10.48
archive_package "$pcre2_devel_root" pcre2-devel 10.48-1

write_export()
{
    local destination=$1
    shift
    local first=true spec name package_name package
    {
        printf '{\n  "schema": 1,\n  "packages": [\n'
        for spec in "$@"; do
            name="${spec%%:*}"
            package_name="${spec#*:}"
            package="$output/packages/$package_name"
            if ! test -f "$package"; then
                echo "package resolution failed for $name: $package" >&2
                exit 6
            fi
            if ! $first; then
                printf ',\n'
            fi
            first=false
            printf '    {"name": "%s", "path": "packages/%s", "sha256": "%s"}' \
                "$name" "$(basename "$package")" \
                "$(sha256sum "$package" | cut -d' ' -f1)"
        done
        printf '\n  ]\n}\n'
    } >"$destination"
}

write_export "$output/bzip2-export.json" \
    bzip2:bzip2-1.0.8-4-aarch64.pkg.tar.zst \
    libbz2:libbz2-1.0.8-4-aarch64.pkg.tar.zst \
    libbz2-devel:libbz2-devel-1.0.8-4-aarch64.pkg.tar.zst
write_export "$output/pcre2-export.json" \
    pcre2:pcre2-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_8:libpcre2_8-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_16:libpcre2_16-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_32:libpcre2_32-10.48-1-aarch64.pkg.tar.zst \
    libpcre2posix:libpcre2posix-10.48-1-aarch64.pkg.tar.zst \
    pcre2-devel:pcre2-devel-10.48-1-aarch64.pkg.tar.zst
write_export "$output/export.json" \
    bzip2:bzip2-1.0.8-4-aarch64.pkg.tar.zst \
    libbz2:libbz2-1.0.8-4-aarch64.pkg.tar.zst \
    libbz2-devel:libbz2-devel-1.0.8-4-aarch64.pkg.tar.zst \
    pcre2:pcre2-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_8:libpcre2_8-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_16:libpcre2_16-10.48-1-aarch64.pkg.tar.zst \
    libpcre2_32:libpcre2_32-10.48-1-aarch64.pkg.tar.zst \
    libpcre2posix:libpcre2posix-10.48-1-aarch64.pkg.tar.zst \
    pcre2-devel:pcre2-devel-10.48-1-aarch64.pkg.tar.zst

printf '%s\n' "native MSYS bzip2 and PCRE2 packages completed" \
    >"$output/package-complete.txt"
