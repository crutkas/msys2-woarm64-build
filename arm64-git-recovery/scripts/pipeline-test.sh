#!/bin/bash
set +e
cache=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/refpkgs
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
REPO=/tmp/pipe-repo
ROOT=/tmp/pipe-root
CONF=/tmp/pipe.conf

# 1. Rebuild ephemeral pkgs wiped from /tmp (GCM stub, leaves) before assembling repo
MK2=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
[ -f /tmp/gcm-pkg/*.pkg.tar.zst ] 2>/dev/null || { tr -d '\r' < "$MK2/build-gcm-stub.sh" > /tmp/bgs.sh; bash /tmp/bgs.sh >/dev/null 2>&1; }
ls /tmp/leaves/*.pkg.tar.zst >/dev/null 2>&1 || { tr -d '\r' < "$MK2/build-leaves.sh" > /tmp/bl.sh; bash /tmp/bl.sh >/dev/null 2>&1; }
ls /tmp/bb-pkg/*.pkg.tar.zst >/dev/null 2>&1 || { tr -d '\r' < "$MK2/make-busybox-standin.sh" > /tmp/mbs.sh; bash /tmp/mbs.sh >/dev/null 2>&1; }
ls /tmp/basestubs/*.pkg.tar.zst >/dev/null 2>&1 || { tr -d '\r' < "$MK2/make-base-stubs.sh" > /tmp/mbst.sh; bash /tmp/mbst.sh >/dev/null 2>&1; }

# 1. Assemble sync repo: reference closure + upstream git + busybox standin + my GCM stub + leaves
rm -rf "$REPO"; mkdir -p "$REPO"
cp "$cache"/*.pkg.tar.zst "$REPO"/ 2>/dev/null            # 28 reference incl upstream git
cp /tmp/bb-pkg/*.pkg.tar.zst "$REPO"/ 2>/dev/null          # busybox standin
cp /tmp/gcm-pkg/*.pkg.tar.zst "$REPO"/ 2>/dev/null         # my GCM stub
cp /tmp/leaves/*.pkg.tar.zst "$REPO"/ 2>/dev/null          # my leaves
cp /tmp/basestubs/*.pkg.tar.zst "$REPO"/ 2>/dev/null       # base/msys dep stubs (cc-libs, nano, msys2-runtime, ...)
echo "repo pkgs: $(ls "$REPO"/*.pkg.tar.zst | wc -l)"
repo-add "$REPO/pipe.db.tar.gz" "$REPO"/*.pkg.tar.zst >/tmp/pipe-ra.log 2>&1
echo "repo-add exit=$? added=$(grep -ci 'adding package' /tmp/pipe-ra.log)"

printf '[options]\nArchitecture = any\nSigLevel = Never\n\n[pipe]\nServer = file://%s\n' "$REPO" > "$CONF"

# 2. Fresh root, sync, install EVERYTHING --nodeps so payloads land on disk
rm -rf "$ROOT"; mkdir -p "$ROOT/var/lib/pacman"
pacman --config "$CONF" --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Sy --noconfirm >/tmp/pipe-sy.log 2>&1
allpkgs=$(pacman --config "$CONF" --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Sl pipe 2>/dev/null | awk '{print $2}')
# install directly from package FILES with -U --nodeps to bypass the resolver.
# Dedup by pkgname (reference closure and my leaves both provide c-ares/libffi/etc) — keep one file per pkgname.
declare -A seen; instlist=""
for f in "$REPO"/*.pkg.tar.zst; do
  base=$(basename "$f"); pn=$(echo "$base" | sed -E 's/-[0-9].*//')
  if [ -z "${seen[$pn]}" ]; then seen[$pn]=1; instlist="$instlist $f"; fi
done
pacman --config "$CONF" --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -U --noconfirm -dd $instlist >/tmp/pipe-inst.log 2>&1
echo "install exit=$? ; files under root/clangarm64: $(find "$ROOT/clangarm64" -type f 2>/dev/null | wc -l)"
sudo ln -sfn "$ROOT/clangarm64" /clangarm64
# has_pacman_package (line 166) checks the ABSOLUTE /var/lib/pacman/local (ignores --dbpath),
# so point it at our root's local db, else it misses installed pkgs and re-runs the required install.
sudo mkdir -p /var/lib/pacman
sudo rm -rf /var/lib/pacman/local
sudo ln -sfn "$ROOT/var/lib/pacman/local" /var/lib/pacman/local

# 3. rebuild pactree if wiped
if [ ! -x /tmp/pactree ]; then
  cd /tmp; [ -d pacman-contrib ] || git clone --depth 1 https://gitlab.archlinux.org/pacman/pacman-contrib.git >/dev/null 2>&1
  printf '#define PACKAGE_VERSION "1.10.6"\n#define DBPATH "/var/lib/pacman"\n#define CONFFILE "/etc/pacman.conf"\n#define ROOTDIR "/"\n#define GPGDIR "/etc/pacman.d/gnupg"\n#define LOCALEDIR "/usr/share/locale"\n' > /tmp/pt_config.h
  gcc -include /tmp/pt_config.h -o /tmp/pactree pacman-contrib/src/pactree.c -lalpm 2>/dev/null
fi

# 4. shims + patched make-file-list.sh
mkdir -p /tmp/shims
printf '#!/bin/bash\nexec /usr/bin/pacman --config %s --root %s --dbpath %s/var/lib/pacman "$@"\n' "$CONF" "$ROOT" "$ROOT" > /tmp/shims/pacman
printf '#!/bin/bash\nexec /tmp/pactree --config %s --dbpath %s/var/lib/pacman "$@"\n' "$CONF" "$ROOT" > /tmp/shims/pactree
chmod +x /tmp/shims/*
mkdir -p /tmp/mkpkg; tr -d '\r' < "$MK/mfl-patched.sh" > /tmp/mkpkg/mfl-patched.sh

# 5. RUN the pipeline
echo "=== make-file-list.sh MINIMAL_GIT_WITH_BUSYBOX=1 (upstream git+busybox standins) ==="
cd /tmp
PATH=/tmp/shims:$PATH ARCH=aarch64 MINIMAL_GIT_WITH_BUSYBOX=1 \
  bash /tmp/mkpkg/mfl-patched.sh > /tmp/pipe-filelist.txt 2>/tmp/pipe-mfl.err
echo "make-file-list exit=$? ; file-list lines=$(wc -l < /tmp/pipe-filelist.txt)"
echo "--- first 15 files listed ---"; head -15 /tmp/pipe-filelist.txt
echo "--- stderr tail ---"; tail -12 /tmp/pipe-mfl.err
echo "--- does the list include git.exe ? ---"; grep -c 'git\.exe$' /tmp/pipe-filelist.txt
echo "--- does it include busybox/ash ? ---"; grep -iE 'busybox|ash\.exe' /tmp/pipe-filelist.txt
