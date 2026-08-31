#!/bin/bash

# Host-independent regressions for the native toolchain boundary.
#
# Everything here runs with nothing but bash, coreutils and the Windows subst
# command, so it covers the identity, cleanup and argument-conversion rules on
# an AMD64 runner long before an admitted ARM64 binutils exists.

set -euo pipefail
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/tests/bootstrap/lib/native-fixtures.sh"
source "$repo_root/.github/scripts/lib/native-tooling.sh"
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"

failures=0
checks=0

report() {
  local outcome=$1
  local message=$2

  checks=$((checks + 1))
  if [[ "$outcome" == "ok" ]]; then
    printf 'ok   %s\n' "$message"
  else
    printf 'FAIL %s\n' "$message" >&2
    failures=$((failures + 1))
  fi
}

assert_equal() {
  local expected=$1
  local actual=$2
  local message=$3

  if [[ "$actual" == "$expected" ]]; then
    report ok "$message"
  else
    report fail "$message"
    printf '     expected: <%s>\n     actual:   <%s>\n' "$expected" "$actual" >&2
  fi
}

assert_contains() {
  local haystack=$1
  local needle=$2
  local message=$3

  if [[ "$haystack" == *"$needle"* ]]; then
    report ok "$message"
  else
    report fail "$message"
    printf '     missing <%s> in <%s>\n' "$needle" "$haystack" >&2
  fi
}

assert_ok() {
  local message=$1
  shift

  if "$@" >/dev/null 2>&1; then
    report ok "$message"
  else
    report fail "$message"
  fi
}

assert_fails() {
  local message=$1
  shift

  if "$@" >/dev/null 2>&1; then
    report fail "$message"
  else
    report ok "$message"
  fi
}

root=$(mktemp -d)
suite_process=$BASHPID
WOARM64_TEST_DRIVES=()
subst_tool=$(to_msys_path "${SYSTEMROOT:-C:\\Windows}\\System32\\subst.exe")
# The helper restores a caller EXIT trap by re-installing it, which makes an
# otherwise dormant inherited trap active inside a ( ) subshell. Guard on the
# owning process so a probe subshell cannot tear down the whole fixture root.
cleanup_suite() {
  local letter

  if [[ $BASHPID -ne $suite_process ]]; then
    return 0
  fi
  for letter in "${WOARM64_TEST_DRIVES[@]}"; do
    MSYS2_ARG_CONV_EXCL='*' "$subst_tool" "${letter^^}:" /D >/dev/null 2>&1 || true
  done
  rm -rf "$root"
}
trap cleanup_suite EXIT

printf '== PE machine identity ==\n'

make_pe_image "$root/pe/arm64.exe" aa64
make_pe_image "$root/pe/arm64ec.exe" a641
make_pe_image "$root/pe/arm64x.exe" a64e
make_pe_image "$root/pe/amd64.exe" 8664
printf 'definitely not a portable executable\n' > "$root/pe/text.bin"
head -c 3 /dev/zero > "$root/pe/truncated.exe"

assert_equal '0xaa64' "$(native_pe_machine "$root/pe/arm64.exe")" 'ARM64 machine word is read exactly'
assert_equal '0xa641' "$(native_pe_machine "$root/pe/arm64ec.exe")" 'ARM64EC machine word is read exactly'
assert_equal '0xa64e' "$(native_pe_machine "$root/pe/arm64x.exe")" 'ARM64X machine word is read exactly'
assert_ok 'pure ARM64 image is accepted' assert_native_arm64_pe "$root/pe/arm64.exe"
assert_fails 'ARM64EC image is rejected' assert_native_arm64_pe "$root/pe/arm64ec.exe"
assert_fails 'ARM64X image is rejected' assert_native_arm64_pe "$root/pe/arm64x.exe"
assert_fails 'AMD64 image is rejected' assert_native_arm64_pe "$root/pe/amd64.exe"
assert_fails 'non-PE payload is rejected' assert_native_arm64_pe "$root/pe/text.bin"
assert_fails 'truncated image is rejected' assert_native_arm64_pe "$root/pe/truncated.exe"

# e_lfanew must be validated against the real file size, otherwise the machine
# word is read from an unchecked offset.
make_pe_image "$root/pe/farheader.exe" aa64
printf '\xff\xff\xff\x7f' | dd of="$root/pe/farheader.exe" bs=1 seek=60 conv=notrunc status=none
assert_fails 'an out-of-range PE header offset is rejected' \
  assert_native_arm64_pe "$root/pe/farheader.exe"
make_pe_image "$root/pe/badsig.exe" aa64
printf 'XX' | dd of="$root/pe/badsig.exe" bs=1 seek=64 conv=notrunc status=none
assert_fails 'a bad PE signature is rejected' \
  assert_native_arm64_pe "$root/pe/badsig.exe"
make_pe_image "$root/pe/badmz.exe" aa64
printf 'XX' | dd of="$root/pe/badmz.exe" bs=1 seek=0 conv=notrunc status=none
assert_fails 'a bad MZ signature is rejected' \
  assert_native_arm64_pe "$root/pe/badmz.exe"
assert_fails 'a directory is rejected' assert_native_arm64_pe "$root/pe"

# The whole 20-byte COFF header, not just the 4-byte signature and the machine
# word, must be present before the machine is trusted. A file cut short one field
# into IMAGE_FILE_HEADER must not yield a Machine value the loader would reject.
head -c 70 "$root/pe/arm64.exe" > "$root/pe/shortcoff.exe"
assert_fails 'a truncated COFF header is rejected' \
  assert_native_arm64_pe "$root/pe/shortcoff.exe"
# e_lfanew that points back inside the 64-byte DOS header is rejected instead of
# reading the machine word from an overlapping offset.
make_pe_image "$root/pe/dosoverlap.exe" aa64
printf '\x04\x00\x00\x00' | dd of="$root/pe/dosoverlap.exe" bs=1 seek=60 conv=notrunc status=none
assert_fails 'a PE header offset inside the DOS header is rejected' \
  assert_native_arm64_pe "$root/pe/dosoverlap.exe"

printf '== native tool closure ==\n'

tool_bin="$root/closure/bin"
make_native_tool_fixtures "$tool_bin" aa64
disable_fixture_execution() {
  local bindir=$1

  chmod 0644 "$bindir"/*.exe
}
disable_fixture_execution "$tool_bin"
assert_equal '10' "${#WOARM64_NATIVE_TOOLS[@]}" 'the pinned closure covers ten tools'

closure_probe() {
  local bindir=$1
  shift

  (
    export WOARM64_NATIVE_BIN="$bindir"
    export PATH="$bindir:$PATH"
    verify_native_tool_closure "$@"
  )
}

# Synthetic PE headers deliberately cannot execute. They exercise the
# structural gate, but must never impersonate an admitted closure.
assert_fails 'a non-executable synthetic closure is rejected' closure_probe "$tool_bin"
assert_ok 'the synthetic GCC image passes the structural ARM64 gate' \
  assert_native_arm64_pe "$tool_bin/gcc.exe"
assert_ok 'the synthetic g++ image passes the structural ARM64 gate' \
  assert_native_arm64_pe "$tool_bin/g++.exe"

hybrid_bin="$root/hybrid/bin"
make_native_tool_fixtures "$hybrid_bin" aa64
make_pe_image "$hybrid_bin/strip.exe" a641
disable_fixture_execution "$hybrid_bin"
assert_fails 'an ARM64EC tool fails the closure' closure_probe "$hybrid_bin"

missing_bin="$root/missing/bin"
make_native_tool_fixtures "$missing_bin" aa64
rm -f "$missing_bin/dlltool.exe"
disable_fixture_execution "$missing_bin"
assert_fails 'a missing tool fails the closure' closure_probe "$missing_bin"

shadow_bin="$root/shadow/bin"
shadow_front="$root/shadow/front"
make_native_tool_fixtures "$shadow_bin" aa64
mkdir -p "$shadow_front"
make_pe_image "$shadow_front/strip.exe" 8664
disable_fixture_execution "$shadow_bin"
disable_fixture_execution "$shadow_front"
shadowed_probe() (
  export WOARM64_NATIVE_BIN="$shadow_bin"
  export PATH="$shadow_front:$shadow_bin:$PATH"
  verify_native_tool_closure
)
assert_fails 'a PATH shadow fails the closure' shadowed_probe

disabled_version_probe() (
  export WOARM64_NATIVE_BIN="$tool_bin"
  export WOARM64_TOOL_VERSION_PROBE=0
  export PATH="$tool_bin:$PATH"
  verify_native_tool_closure
)
assert_fails 'WOARM64_TOOL_VERSION_PROBE cannot bypass version verification' \
  disabled_version_probe

printf '== launcher cache identity ==\n'

install_dir="$root/launcher/libexec"
mkdir -p "$install_dir"
cp -f "$repo_root/.github/scripts/lib/native-compiler-launcher.c" \
  "$install_dir/native-compiler-launcher.c"
launcher_bin="$root/launcher/bin"
make_native_tool_fixtures "$launcher_bin" aa64
fake_compiler="$root/launcher/fake-gcc"
counter="$root/launcher/calls"
make_fake_launcher_compiler "$fake_compiler" "$counter"

launcher_run() (
  export WOARM64_LAUNCHER_INSTALL_DIR="$install_dir"
  export WOARM64_NATIVE_BIN="$launcher_bin"
  export WOARM64_NATIVE_LAUNCHER_COMPILER="$fake_compiler"
  export WOARM64_NATIVE_CXX="$fake_compiler"
  export WOARM64_FAKE_COMPILER_COUNTER="$counter"
  export WOARM64_FAKE_COMPILER_FAIL="${1:-0}"
  ensure_native_compiler_launchers
)

assert_ok 'the first launcher build succeeds' launcher_run
assert_equal '2' "$(fake_compiler_call_count "$counter")" 'the first build compiles and links once'
stamp_file="$install_dir/native-compiler-launcher.identity"
assert_contains "$(cat "$stamp_file")" 'launcher-identity-v4' 'the stamp is versioned'
assert_contains "$(cat "$stamp_file")" 'toolchain=' 'the stamp binds the toolchain identity'
assert_contains "$(cat "$stamp_file")" 'launcher-pair size=' \
  'the stamp binds one identical generated launcher pair'
assert_ok 'the installed gcc launcher is a pure ARM64 image' \
  assert_native_arm64_pe "$install_dir/woarm64-gcc.exe"
assert_ok 'the installed g++ launcher is a pure ARM64 image' \
  assert_native_arm64_pe "$install_dir/woarm64-g++.exe"

assert_ok 'an unchanged toolchain reuses the launchers' launcher_run
assert_equal '2' "$(fake_compiler_call_count "$counter")" 'reuse does not recompile'

# The regression this whole scheme exists for: the launcher source is untouched,
# only the linker changed, and the cached launcher must not survive.
perturb_pe_image "$launcher_bin/ld.exe" 'corrected-binutils'
assert_ok 'a changed linker still builds' launcher_run
assert_equal '4' "$(fake_compiler_call_count "$counter")" \
  'a changed linker forces a launcher rebuild even though the source is identical'

perturb_pe_image "$launcher_bin/gcc.exe" 'newer-gcc'
printf '# toolchain revision marker\n' >> "$fake_compiler"
assert_ok 'a changed compiler still builds' launcher_run
assert_equal '6' "$(fake_compiler_call_count "$counter")" \
  'a changed compiler forces a launcher rebuild'

# A stamp written by the old source-only scheme must never compare equal.
sha256sum "$install_dir/native-compiler-launcher.c" | cut -d' ' -f1 > "$stamp_file"
assert_ok 'a legacy stamp still builds' launcher_run
assert_equal '8' "$(fake_compiler_call_count "$counter")" \
  'a legacy source-only stamp forces a launcher rebuild'

rm -f "$stamp_file"
assert_fails 'a failing compiler fails the launcher build' launcher_run 1
if [[ -f "$stamp_file" ]]; then
  report fail 'a failed launcher build leaves no valid stamp'
else
  report ok 'a failed launcher build leaves no valid stamp'
fi
if [[ -d "$install_dir/.launcher-lock" ]]; then
  report fail 'a failed launcher build releases its lock'
else
  report ok 'a failed launcher build releases its lock'
fi
assert_equal '0' "$(ls "$install_dir" | grep -c 'staged' || true)" \
  'a failed launcher build leaves no staged images'

# Partial install recovery: one launcher was replaced and the other was not, so
# the cache must be treated as invalid even if a stamp were present.
assert_ok 'the launcher build recovers after a failure' launcher_run
recovery_calls=$(fake_compiler_call_count "$counter")
rm -f "$install_dir/woarm64-g++.exe"
assert_ok 'a half-installed launcher pair still builds' launcher_run
assert_equal "$(( recovery_calls + 2 ))" "$(fake_compiler_call_count "$counter")" \
  'a missing second launcher forces a rebuild'
assert_ok 'the recovered g++ launcher is a pure ARM64 image' \
  assert_native_arm64_pe "$install_dir/woarm64-g++.exe"

# A cache hit must re-verify the installed launchers are still pure ARM64 PEs
# rather than trust a matching stamp. A launcher swapped for an AMD64 image after
# the stamp was written has to invalidate the cache and force one clean rebuild.
revalidation_calls=$(fake_compiler_call_count "$counter")
printf '\x64\x86' | dd of="$install_dir/woarm64-gcc.exe" bs=1 seek=68 conv=notrunc status=none
assert_fails 'a launcher swapped to AMD64 is detected as non-ARM64' \
  assert_native_arm64_pe "$install_dir/woarm64-gcc.exe"
assert_ok 'a cache hit revalidates the installed launchers' launcher_run
assert_equal "$(( revalidation_calls + 2 ))" "$(fake_compiler_call_count "$counter")" \
  'an installed launcher swapped to AMD64 forces a rebuild'
assert_ok 'the revalidated gcc launcher is a pure ARM64 image' \
  assert_native_arm64_pe "$install_dir/woarm64-gcc.exe"

# A forged stamp cannot authorize a mixed pair. Both images can be individually
# valid ARM64 PEs and the stamp can name one of them, but launchers are generated
# from the same output and must be byte-for-byte identical.
output_identity_calls=$(fake_compiler_call_count "$counter")
perturb_pe_image "$install_dir/woarm64-g++.exe" 'unexpected-valid-arm64-bytes'
forge_mixed_launcher_stamp() (
  export WOARM64_LAUNCHER_INSTALL_DIR="$install_dir"
  export WOARM64_NATIVE_BIN="$launcher_bin"
  export WOARM64_NATIVE_LAUNCHER_COMPILER="$fake_compiler"
  export WOARM64_NATIVE_CXX="$fake_compiler"
  identity=$(native_launcher_identity "$install_dir")
  printf '%s\nlauncher-pair size=%s sha256=%s\n' "$identity" \
    "$(stat -c %s -- "$install_dir/woarm64-g++.exe")" \
    "$(sha256sum -- "$install_dir/woarm64-g++.exe" | cut -d' ' -f1)" > "$stamp_file"
)
assert_ok 'a forged mixed launcher stamp rebuilds the pair' launcher_run
assert_equal "$(( output_identity_calls + 2 ))" "$(fake_compiler_call_count "$counter")" \
  'a mixed valid ARM64 launcher pair cannot reuse a forged output stamp'

# A lock left behind by a killed builder must be reclaimed once it is stale,
# and a fresh lock must fail on a bounded timeout instead of hanging.
( exit 0 ) &
dead_owner_pid=$!
wait "$dead_owner_pid"
dead_owner_token="${dead_owner_pid}:0:0"
mkdir -p "$install_dir/.launcher-lock"
printf '%s\n' "$dead_owner_token" \
  > "$install_dir/.launcher-lock/owner.${dead_owner_token//:/_}"
touch -d '2000-01-01' "$install_dir/.launcher-lock" 2>/dev/null || true
rm -f "$stamp_file"
stale_lock_status=0
( export WOARM64_LAUNCHER_LOCK_STALE=1; launcher_run ) || stale_lock_status=$?
assert_equal '0' "$stale_lock_status" 'a stale launcher lock is reclaimed'
if [[ -d "$install_dir/.launcher-lock" ]]; then
  report fail 'a reclaimed launcher lock is released'
else
  report ok 'a reclaimed launcher lock is released'
fi

mkdir -p "$install_dir/.launcher-lock"
rm -f "$stamp_file"
held_lock_status=0
(
  export WOARM64_LAUNCHER_LOCK_TIMEOUT=1
  export WOARM64_LAUNCHER_LOCK_STALE=100000
  launcher_run
) >/dev/null 2>&1 || held_lock_status=$?
assert_equal '1' "$held_lock_status" \
  'a held launcher lock fails on a bounded timeout instead of hanging'
rm -rf "$install_dir/.launcher-lock"
assert_ok 'the launcher build succeeds once the lock is gone' launcher_run

# The interval between mkdir and marker creation cannot be safely distinguished
# from a paused owner. It must fail closed instead of reclaiming that directory
# and allowing the paused owner to join a later lock.
incomplete_lock="$root/launcher/incomplete-lock"
mkdir "$incomplete_lock"
touch -d '2000-01-01' "$incomplete_lock" 2>/dev/null || true
incomplete_lock_status=0
(
  export WOARM64_LAUNCHER_LOCK_TIMEOUT=0
  export WOARM64_LAUNCHER_LOCK_STALE=1
  woarm64_acquire_launcher_lock "$incomplete_lock"
) >/dev/null 2>&1 || incomplete_lock_status=$?
assert_equal '1' "$incomplete_lock_status" \
  'an unowned stale launcher lock is not reclaimed'
if [[ -d "$incomplete_lock" ]]; then
  report ok 'an incomplete launcher lock remains diagnosable'
else
  report fail 'an incomplete launcher lock remains diagnosable'
fi
rmdir "$incomplete_lock"

live_owner_lock="$root/launcher/live-owner-lock"
live_owner_token="${BASHPID}:0:0"
mkdir "$live_owner_lock"
printf '%s\n' "$live_owner_token" \
  > "$live_owner_lock/owner.${live_owner_token//:/_}"
touch -d '2000-01-01' "$live_owner_lock" 2>/dev/null || true
live_owner_status=0
(
  export WOARM64_LAUNCHER_LOCK_TIMEOUT=0
  export WOARM64_LAUNCHER_LOCK_STALE=1
  woarm64_acquire_launcher_lock "$live_owner_lock"
) >/dev/null 2>&1 || live_owner_status=$?
assert_equal '1' "$live_owner_status" \
  'a live stale launcher owner is not reclaimed'
if [[ -d "$live_owner_lock" &&
      -f "$live_owner_lock/owner.${live_owner_token//:/_}" ]]; then
  report ok 'a live stale launcher lock remains owned'
else
  report fail 'a live stale launcher lock remains owned'
fi
rm -f -- "$live_owner_lock/owner.${live_owner_token//:/_}"
rmdir "$live_owner_lock"

printf '== launcher lock ownership ==\n'

# A builder whose lock was reclaimed while paused must never delete the lock a
# new owner acquired after the atomic rename. The old ownership marker is moved
# out with the stale directory before the new lock exists.
ownership_lock="$root/launcher/ownership-lock"
woarm64_acquire_launcher_lock "$ownership_lock"
stale_ownership_lock="${ownership_lock}.stale"
mv -- "$ownership_lock" "$stale_ownership_lock"
woarm64_remove_stale_launcher_lock "$stale_ownership_lock"
mkdir "$ownership_lock"
printf 'new-owner\n' > "$ownership_lock/owner.new-owner"
assert_fails 'a reclaimed owner loses the right to publish launcher output' \
  woarm64_launcher_lock_is_owned "$ownership_lock"
woarm64_release_launcher_lock "$ownership_lock"
if [[ -d "$ownership_lock" ]]; then
  report ok 'a reclaimed lock is left for its new owner'
else
  report fail 'a reclaimed lock is left for its new owner'
fi
if [[ -f "$ownership_lock/owner.new-owner" ]]; then
  report ok 'a paused owner cannot remove a new ownership marker'
else
  report fail 'a paused owner cannot remove a new ownership marker'
fi
_WOARM64_LAUNCHER_LOCK_TOKEN='new-owner'
woarm64_release_launcher_lock "$ownership_lock"
if [[ -d "$ownership_lock" ]]; then
  report fail 'the true owner releases its own lock'
else
  report ok 'the true owner releases its own lock'
fi
_WOARM64_LAUNCHER_LOCK_TOKEN=

acquire_interleave_lock="$root/launcher/acquire-interleave-lock"
acquire_interleave_bin="$root/launcher/acquire-interleave-bin"
mkdir -p "$acquire_interleave_lock" "$acquire_interleave_bin"
acquire_interleave_token="${dead_owner_pid}:1:1"
acquire_interleave_marker=\
"$acquire_interleave_lock/owner.${acquire_interleave_token//:/_}"
printf '%s\n' "$acquire_interleave_token" > "$acquire_interleave_marker"
touch -d '2000-01-01' "$acquire_interleave_lock" 2>/dev/null || true
real_mv=$(command -v mv)
real_mkdir=$(command -v mkdir)
real_rm=$(command -v rm)
real_rmdir=$(command -v rmdir)
cat > "$acquire_interleave_bin/mv" <<'EOF'
#!/bin/bash
for argument in "$@"; do
  if [[ "$argument" == "$WOARM64_ACQUIRE_INTERLEAVE_MARKER" ]]; then
    "$WOARM64_REAL_RM" -f -- "$argument"
    "$WOARM64_REAL_RMDIR" -- "$WOARM64_ACQUIRE_INTERLEAVE_LOCK"
    "$WOARM64_REAL_MKDIR" -- "$WOARM64_ACQUIRE_INTERLEAVE_LOCK"
    printf 'new-owner\n' > "$WOARM64_ACQUIRE_INTERLEAVE_LOCK/owner.new-owner"
    exit 1
  fi
done
exec "$WOARM64_REAL_MV" "$@"
EOF
chmod +x "$acquire_interleave_bin/mv"
acquire_interleave_status=0
(
  export PATH="$acquire_interleave_bin:$PATH"
  export WOARM64_REAL_MV="$real_mv"
  export WOARM64_REAL_MKDIR="$real_mkdir"
  export WOARM64_REAL_RM="$real_rm"
  export WOARM64_REAL_RMDIR="$real_rmdir"
  export WOARM64_ACQUIRE_INTERLEAVE_LOCK="$acquire_interleave_lock"
  export WOARM64_ACQUIRE_INTERLEAVE_MARKER="$acquire_interleave_marker"
  export WOARM64_LAUNCHER_LOCK_TIMEOUT=0
  export WOARM64_LAUNCHER_LOCK_STALE=1
  woarm64_acquire_launcher_lock "$acquire_interleave_lock"
) >/dev/null 2>&1 || acquire_interleave_status=$?
assert_equal '1' "$acquire_interleave_status" \
  'a stale-reclaim interleaving cannot claim a new owner lock'
if [[ -d "$acquire_interleave_lock" &&
      -f "$acquire_interleave_lock/owner.new-owner" ]]; then
  report ok 'a reclaim contender leaves the interleaved new lock intact'
else
  report fail 'a reclaim contender leaves the interleaved new lock intact'
fi
"$real_rm" -f -- "$acquire_interleave_lock/owner.new-owner"
"$real_rmdir" -- "$acquire_interleave_lock"

lock_failure_bin="$root/launcher/lock-failure-bin"
mkdir -p "$lock_failure_bin"
cat > "$lock_failure_bin/rm" <<'EOF'
#!/bin/bash
for argument in "$@"; do
  if [[ -n "${WOARM64_RELEASE_INTERLEAVE_HOOK:-}" && "$argument" == */owner.* ]]; then
    "$WOARM64_RELEASE_INTERLEAVE_HOOK" || exit 1
  fi
  if [[ "${WOARM64_INJECT_RM_FAILURE:-}" == 1 && "$argument" == */owner.* ]]; then
    exit 1
  fi
done
exec "$WOARM64_REAL_RM" "$@"
EOF
cat > "$lock_failure_bin/rmdir" <<'EOF'
#!/bin/bash
exit 1
EOF
chmod +x "$lock_failure_bin/rm" "$lock_failure_bin/rmdir"

release_interleave_lock="$root/launcher/release-interleave-lock"
release_interleave_hook="$root/launcher/release-interleave-hook"
woarm64_acquire_launcher_lock "$release_interleave_lock"
cat > "$release_interleave_hook" <<'EOF'
#!/bin/bash
mv -- "$WOARM64_INTERLEAVE_LOCK" "${WOARM64_INTERLEAVE_LOCK}.stale"
mkdir -- "$WOARM64_INTERLEAVE_LOCK"
printf 'new-owner\n' > "$WOARM64_INTERLEAVE_LOCK/owner.new-owner"
EOF
chmod +x "$release_interleave_hook"
release_interleave_status=0
PATH="$lock_failure_bin:$PATH" WOARM64_REAL_RM="$real_rm" \
  WOARM64_INTERLEAVE_LOCK="$release_interleave_lock" \
  WOARM64_RELEASE_INTERLEAVE_HOOK="$release_interleave_hook" \
  woarm64_release_launcher_lock "$release_interleave_lock" ||
  release_interleave_status=$?
assert_equal '1' "$release_interleave_status" \
  'an interleaved reclaim makes the old marker unlink fail closed'
if [[ -d "$release_interleave_lock" &&
      -f "$release_interleave_lock/owner.new-owner" ]]; then
  report ok 'an old owner cannot remove a lock acquired during its release'
else
  report fail 'an old owner cannot remove a lock acquired during its release'
fi
"$real_rm" -f -- "$release_interleave_lock.stale"/owner.*
"$real_rmdir" -- "$release_interleave_lock.stale"
_WOARM64_LAUNCHER_LOCK_TOKEN='new-owner'
woarm64_release_launcher_lock "$release_interleave_lock"

rm_failure_lock="$root/launcher/rm-failure-lock"
woarm64_acquire_launcher_lock "$rm_failure_lock"
rm_failure_marker="${rm_failure_lock}/owner.${_WOARM64_LAUNCHER_LOCK_TOKEN//:/_}"
rm_failure_status=0
PATH="$lock_failure_bin:$PATH" WOARM64_INJECT_RM_FAILURE=1 WOARM64_REAL_RM="$real_rm" \
  woarm64_release_launcher_lock "$rm_failure_lock" || rm_failure_status=$?
assert_equal '1' "$rm_failure_status" \
  'a failed ownership-marker removal returns a nonzero cleanup status'
if [[ -d "$rm_failure_lock" && -f "$rm_failure_marker" ]]; then
  report ok 'a failed ownership-marker removal retains a diagnosable lock'
else
  report fail 'a failed ownership-marker removal retains a diagnosable lock'
fi
"$real_rm" -f -- "$rm_failure_marker"
"$real_rmdir" -- "$rm_failure_lock"

rm -f "$stamp_file"
launcher_release_failure_status=0
(
  export WOARM64_LAUNCHER_INSTALL_DIR="$install_dir"
  export WOARM64_NATIVE_BIN="$launcher_bin"
  export WOARM64_NATIVE_LAUNCHER_COMPILER="$fake_compiler"
  export WOARM64_NATIVE_CXX="$fake_compiler"
  export WOARM64_FAKE_COMPILER_COUNTER="$counter"
  export WOARM64_FAKE_COMPILER_FAIL=0
  export PATH="$lock_failure_bin:$PATH"
  export WOARM64_INJECT_RM_FAILURE=1
  export WOARM64_REAL_RM="$real_rm"
  ensure_native_compiler_launchers
) || launcher_release_failure_status=$?
assert_equal '1' "$launcher_release_failure_status" \
  'launcher provisioning propagates an ownership-marker cleanup failure'
if [[ -d "$install_dir/.launcher-lock" ]] &&
    find "$install_dir/.launcher-lock" -maxdepth 1 -name 'owner.*' -print -quit | grep -q .; then
  report ok 'a launcher cleanup failure leaves its lock diagnosable'
else
  report fail 'a launcher cleanup failure leaves its lock diagnosable'
fi
"$real_rm" -f -- "$install_dir/.launcher-lock"/owner.*
"$real_rmdir" -- "$install_dir/.launcher-lock"

rmdir_failure_lock="$root/launcher/rmdir-failure-lock"
woarm64_acquire_launcher_lock "$rmdir_failure_lock"
rmdir_failure_status=0
PATH="$lock_failure_bin:$PATH" WOARM64_REAL_RM="$real_rm" \
  woarm64_release_launcher_lock "$rmdir_failure_lock" || rmdir_failure_status=$?
assert_equal '1' "$rmdir_failure_status" \
  'a failed lock-directory removal returns a nonzero cleanup status'
if [[ -d "$rmdir_failure_lock" ]]; then
  report ok 'a failed lock-directory removal retains a diagnosable lock'
else
  report fail 'a failed lock-directory removal retains a diagnosable lock'
fi
"$real_rmdir" -- "$rmdir_failure_lock"

printf '== recipe root alias ==\n'

assert_equal '160' "$WOARM64_NATIVE_RECIPE_PATH_RESERVE_DEFAULT" \
  'the path reserve default is published for the fixtures'

short_root="$root/s"
mkdir -p "$short_root"
assert_fails 'a short recipe root needs no alias' \
  native_recipe_root_needs_alias "$short_root"

long_root="$root/long"
while :; do
  long_native=$(to_native_path "$long_root")
  if (( ${#long_native} + WOARM64_NATIVE_RECIPE_PATH_RESERVE_DEFAULT > 259 )); then
    break
  fi
  long_root="${long_root}x"
done
mkdir -p "$long_root"
assert_ok 'a long recipe root needs an alias' \
  native_recipe_root_needs_alias "$long_root"

invalid_reserve() (
  WOARM64_NATIVE_RECIPE_PATH_RESERVE=0 native_recipe_root_needs_alias "$long_root"
)
invalid_status=0
invalid_reserve >/dev/null 2>&1 || invalid_status=$?
assert_equal '2' "$invalid_status" 'an invalid path reserve is rejected with status 2'

# The decision must use the physical directory, because that is what the alias
# is created for. A symlinked short path in front of a long real path used to
# take the wrong branch.
if ln -s "$long_root" "$root/link" 2>/dev/null && [[ -L "$root/link" && -d "$root/link" ]]; then
  symlink_status=0
  ( cd "$root/link" && native_recipe_root_needs_alias ) || symlink_status=$?
  assert_equal '0' "$symlink_status" \
    'the alias decision follows the physical recipe root through a symlink'
else
  rm -rf "$root/link"
  if WOARM64_JUNCTION_LINK=$(cygpath -aw "$root/link") \
      WOARM64_JUNCTION_TARGET=$(cygpath -aw "$long_root") \
      MSYS2_ARG_CONV_EXCL='*' \
      /c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe \
        -NoProfile -NonInteractive -Command \
        '$ErrorActionPreference = "Stop"; New-Item -ItemType Junction -Path $env:WOARM64_JUNCTION_LINK -Target $env:WOARM64_JUNCTION_TARGET | Out-Null' \
      >/dev/null 2>&1 && [[ -d "$root/link" ]]; then
    symlink_status=0
    ( cd "$root/link" && native_recipe_root_needs_alias ) || symlink_status=$?
    assert_equal '0' "$symlink_status" \
      'the alias decision follows the physical recipe root through a junction'
  else
    report fail 'a symlink or non-privileged junction is required for the physical-root test'
  fi
fi

alias_probe_root="$root/alias"
mkdir -p "$alias_probe_root"
WOARM64_TEST_DRIVES+=(y)
alias_success_status=0
alias_capture="$root/alias.capture"
(
  cd "$alias_probe_root"
  WOARM64_SUBST_DRIVES=Y with_short_native_recipe_root \
    bash -c 'cygpath -am . > "$0"' "$alias_capture"
) >/dev/null 2>&1 || alias_success_status=$?
assert_equal '0' "$alias_success_status" 'the alias helper reports success'
assert_equal 'Y:/' "$(cat "$alias_capture" 2>/dev/null || true)" \
  'the command runs at the root of the alias drive'
if [[ -e /y ]]; then
  report fail 'the alias is removed after a successful command'
else
  report ok 'the alias is removed after a successful command'
fi

alias_failure_status=0
(
  cd "$alias_probe_root"
  WOARM64_SUBST_DRIVES=Y with_short_native_recipe_root bash -c 'exit 37'
) >/dev/null 2>&1 || alias_failure_status=$?
assert_equal '37' "$alias_failure_status" 'the alias helper preserves the command status'
if [[ -e /y ]]; then
  report fail 'the alias is removed after a failing command'
else
  report ok 'the alias is removed after a failing command'
fi

signal_probe="$root/signal.probe"
cat > "$signal_probe" <<EOF
#!/bin/bash
set -e
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
cd "$alias_probe_root"
WOARM64_SUBST_DRIVES=Z with_short_native_recipe_root bash -c '
  trap "exit 0" HUP INT TERM
  echo "\$\$" > "\$WOARM64_SIGNAL_CHILD"
  bash -c '"'"'
    trap "" HUP INT TERM
    echo "\$\$" > "\$WOARM64_SIGNAL_GRANDCHILD"
    while :; do sleep 1; done
  '"'"' &
  kill -s "\$WOARM64_SIGNAL" "\$MSYS2_WOARM64_RECIPE_HELPER_PID"
  while :; do sleep 1; done
'
EOF
chmod +x "$signal_probe"
for signal_spec in 'HUP 129' 'INT 130' 'TERM 143'; do
  read -r signal expected_status <<< "$signal_spec"
  signal_child="$root/$signal.child"
  signal_grandchild="$root/$signal.grandchild"
  signal_status=0
  WOARM64_SIGNAL="$signal" WOARM64_SIGNAL_CHILD="$signal_child" \
    WOARM64_SIGNAL_GRANDCHILD="$signal_grandchild" \
    WOARM64_ALIAS_SIGNAL_WAIT_SECONDS=2 \
    timeout --foreground --kill-after=2s 8s "$signal_probe" >/dev/null 2>&1 ||
    signal_status=$?
  assert_equal "$expected_status" "$signal_status" \
    "the alias helper forwards $signal and returns its exact status"
  if [[ -e /z ]]; then
    report fail "the alias is removed after $signal"
    MSYS2_ARG_CONV_EXCL='*' "$subst_tool" Z: /D >/dev/null 2>&1 || true
  else
    report ok "the alias is removed after $signal"
  fi
  if [[ -f "$signal_child" ]] && kill -0 "$(< "$signal_child")" 2>/dev/null; then
    report fail "the alias child does not survive $signal"
  else
    report ok "the alias child does not survive $signal"
  fi
  if [[ -f "$signal_grandchild" ]] && kill -0 "$(< "$signal_grandchild")" 2>/dev/null; then
    report fail "the signal-ignoring alias grandchild does not survive $signal"
  else
    report ok "the signal-ignoring alias grandchild does not survive $signal"
  fi
done

# A command can remove the physical recipe root before its alias cleanup runs.
# The stored SUBST mapping is still owned and must be removed unconditionally.
deleted_alias_root="$root/deleted-alias"
mkdir -p "$deleted_alias_root"
delete_root_probe="$root/delete-root.probe"
cat > "$delete_root_probe" <<EOF
#!/bin/bash
set -e
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
cd "$deleted_alias_root"
WOARM64_SUBST_DRIVES=Z with_short_native_recipe_root bash -c '
  cd /
  rm -rf -- "\$WOARM64_DELETE_RECIPE_ROOT"
'
EOF
chmod +x "$delete_root_probe"
delete_root_status=0
WOARM64_DELETE_RECIPE_ROOT="$deleted_alias_root" \
  WOARM64_ALIAS_CLEANUP_WAIT_SECONDS=2 \
  "$delete_root_probe" >/dev/null 2>&1 || delete_root_status=$?
assert_equal '1' "$delete_root_status" \
  'a deleted recipe root reports its failed caller-directory restoration'
if [[ -e /z ]]; then
  report fail 'a deleted recipe root still removes its stored alias mapping'
  MSYS2_ARG_CONV_EXCL='*' "$subst_tool" Z: /D >/dev/null 2>&1 || true
else
  report ok 'a deleted recipe root still removes its stored alias mapping'
fi

# Traps belonging to the caller must survive the helper.
trap_probe="$root/trap.probe"
cat > "$trap_probe" <<EOF
#!/bin/bash
set -e
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
trap 'echo caller-exit-trap' EXIT
cd "$alias_probe_root"
WOARM64_SUBST_DRIVES=Y with_short_native_recipe_root bash -c 'true' >/dev/null 2>&1
trap -p EXIT
EOF
chmod +x "$trap_probe"
assert_contains "$(/usr/bin/bash "$trap_probe" 2>/dev/null)" 'caller-exit-trap' \
  'the caller EXIT trap is restored after a successful run'

# The leak regression. A stub subst maps the drive somewhere other than the
# recipe root, so the identity check fails. Ownership must be released and the
# traps restored instead of leaving a silently unreclaimable mapping behind.
stub_root="$root/stub"
decoy="$root/decoy"
mkdir -p "$stub_root/System32" "$decoy"
decoy_native=$(to_native_path "$decoy")
real_subst=$subst_tool
cat > "$stub_root/System32/subst.exe" <<EOF
#!/bin/bash
if [[ "\$2" == "/D" ]]; then
  exec "$real_subst" "\$1" /D
fi
exec "$real_subst" "\$1" "$decoy_native"
EOF
chmod +x "$stub_root/System32/subst.exe"

WOARM64_TEST_DRIVES+=(x)
mismatch_probe="$root/mismatch.probe"
cat > "$mismatch_probe" <<EOF
#!/bin/bash
set -e
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
trap 'echo caller-exit-trap' EXIT
cd "$alias_probe_root"
status=0
SYSTEMROOT='$(to_native_path "$stub_root" | sed 's|/|\\\\|g')' \
  WOARM64_SUBST_DRIVES=X \
  with_short_native_recipe_root bash -c 'true' >/dev/null 2>&1 || status=\$?
echo "status=\$status"
echo "owned=\$_WOARM64_ALIAS_OWNED"
trap -p EXIT
EOF
chmod +x "$mismatch_probe"
mismatch_output=$(/usr/bin/bash "$mismatch_probe" 2>/dev/null || true)
assert_contains "$mismatch_output" 'status=1' \
  'an alias identity mismatch fails the helper'
assert_contains "$mismatch_output" 'owned=0' \
  'an alias identity mismatch releases ownership instead of leaking it'
assert_contains "$mismatch_output" 'caller-exit-trap' \
  'an alias identity mismatch restores the caller EXIT trap'
MSYS2_ARG_CONV_EXCL='*' "$subst_tool" 'X:' /D >/dev/null 2>&1 || true

# Exhaustion has to be a loud failure, not a silent fall back to the long path.
exhaust_root="$stub_root/exhaust"
mkdir -p "$exhaust_root/System32"
cat > "$exhaust_root/System32/subst.exe" <<'EOF'
#!/bin/bash
exit 1
EOF
chmod +x "$exhaust_root/System32/subst.exe"
exhaust_probe="$root/exhaust.probe"
cat > "$exhaust_probe" <<EOF
#!/bin/bash
set -e
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
trap 'echo caller-exit-trap' EXIT
cd "$alias_probe_root"
status=0
SYSTEMROOT='$(to_native_path "$exhaust_root" | sed 's|/|\\\\|g')' \
  WOARM64_SUBST_DRIVES='W V U T S R Q P' \
  with_short_native_recipe_root bash -c 'true' >/dev/null 2>&1 || status=\$?
echo "status=\$status"
echo "owned=\$_WOARM64_ALIAS_OWNED"
echo "active=\$_WOARM64_ALIAS_ACTIVE"
trap -p EXIT
EOF
chmod +x "$exhaust_probe"
exhaust_output=$(/usr/bin/bash "$exhaust_probe" 2>/dev/null || true)
assert_contains "$exhaust_output" 'status=1' 'drive exhaustion fails the helper'
assert_contains "$exhaust_output" 'owned=0' 'drive exhaustion owns no alias'
assert_contains "$exhaust_output" 'active=0' 'drive exhaustion releases helper state'
assert_contains "$exhaust_output" 'caller-exit-trap' \
  'drive exhaustion restores the caller EXIT trap'

printf '== alias residue scan ==\n'

residue_root="$root/residue/pkg"
mkdir -p "$residue_root/mingwarm64/lib"
printf 'libdir=/mingwarm64/lib\n' > "$residue_root/mingwarm64/lib/clean.la"
assert_ok 'a clean staged tree passes the residue scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"

# gettext bakes its homepage and bug-report URLs into staged artifacts. An
# unanchored "<letter>:/" match finds "p:/" inside "http://" and "s:/" inside
# "https://", so both of those candidate drives would fail a perfectly good
# build. Keep these before the positive case so a regression cannot hide.
printf 'PACKAGE_URL="https://www.gnu.org/software/gettext/"\n' \
  > "$residue_root/mingwarm64/lib/urls.la"
printf 'PACKAGE_BUGREPORT="http://example.invalid/bugs"\n' \
  >> "$residue_root/mingwarm64/lib/urls.la"
assert_ok 'an https URL does not look like alias residue on drive s' \
  assert_no_native_recipe_alias_residue s "$residue_root"
assert_ok 'an http URL does not look like alias residue on drive p' \
  assert_no_native_recipe_alias_residue p "$residue_root"

printf "libdir='W:/src/build/.libs'\n" > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'alias residue in staged output fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'libdir=W:\\src\\build\\.libs\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'backslash alias residue in staged output fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'W:/src/build/.libs\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'alias residue at the start of a line fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'W://src/build/.libs\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'alias residue with repeated separators fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'builddir = W:\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'a bare bounded alias drive token fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"

# libtool writes the joined form into .la dependency_libs, with no separator
# before the drive letter. A scan anchored on a preceding non-letter would miss
# exactly this and ship a package with a dangling build path.
printf "dependency_libs=' -LW:/src/gettext/gnulib-lib/.libs -lintl'\n" \
  > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'joined -L alias residue fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf -- '-IW:/src/gettext/include\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'joined -I alias residue fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf -- '-BW:/src/gettext/tool-prefix\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'joined -B alias residue fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf -- '-isystemW:/src/gettext/system-include\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'joined -isystem alias residue fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf -- '-isystem/usr/include\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_ok 'a joined compiler path without the alias drive passes the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'builddir = W:/\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'alias residue at end of line fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
rm -f "$residue_root/mingwarm64/lib/dirty.la"

# makepkg writes .BUILDINFO into the staged tree before it tars the package, and
# it records the build directory. That is the metadata most likely to capture
# the alias, so it has to be inside the scanned scope.
printf 'builddir = W:/\npkgname = mingw-w64-aarch64-gettext\n' \
  > "$residue_root/.BUILDINFO"
assert_fails 'alias residue in staged package metadata fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'builddir = /build\npkgname = mingw-w64-aarch64-gettext\n' \
  > "$residue_root/.BUILDINFO"
assert_ok 'clean staged package metadata passes the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"

# Binary content has to be searched too: debug information and .pc files are not
# guaranteed to be text.
printf 'prefix=W:/mingwarm64\x00\x01\x02binary tail\n' \
  > "$residue_root/mingwarm64/lib/binary.pc"
assert_fails 'alias residue inside binary content fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'W\0:\0/\0s\0r\0c\0\n' > "$residue_root/mingwarm64/lib/utf16le.pc"
assert_fails 'alias residue inside UTF-16LE content fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
rm -f "$residue_root/mingwarm64/lib/binary.pc"
rm -f "$residue_root/mingwarm64/lib/utf16le.pc"

archive_root="$root/residue/archive"
mkdir -p "$archive_root"
printf 'builddir = /clean/archive\n' > "$archive_root/.BUILDINFO"
tar --create --gzip --file="$residue_root/clean.pkg.tar.gz" -C "$archive_root" .
assert_ok 'a clean compressed package archive passes the member scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
printf 'builddir = W:/hidden-in-compressed-member\n' > "$archive_root/.BUILDINFO"
tar --create --gzip --file="$residue_root/gettext.pkg.tar.gz" -C "$archive_root" .
assert_fails 'alias residue hidden in a compressed archive member fails the scan' \
  assert_no_native_recipe_alias_residue w "$residue_root"
rm -f "$residue_root/clean.pkg.tar.gz" "$residue_root/gettext.pkg.tar.gz"
rm -rf "$archive_root"

archive_error_root="$root/residue/archive-errors"
archive_tar_stub="$root/residue/tar-stub"
archive_tar_capture="$root/residue/tar-capture"
mkdir -p "$archive_error_root" "$archive_tar_stub"
printf 'opaque archive bytes\n' > "$archive_error_root/error.pkg.tar"
cat > "$archive_tar_stub/tar" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$WOARM64_TAR_CAPTURE"
case "$WOARM64_TAR_MODE" in
  list-fail)
    exit 1
    ;;
  extract-fail)
    if [[ "$*" == *'--list'* ]]; then
      printf 'hidden-member\n'
      exit 0
    fi
    exit 1
    ;;
esac
exit 2
EOF
chmod +x "$archive_tar_stub/tar"
archive_list_error_status=0
PATH="$archive_tar_stub:$PATH" WOARM64_TAR_CAPTURE="$archive_tar_capture" \
  WOARM64_TAR_MODE=list-fail \
  assert_no_native_recipe_alias_residue w "$archive_error_root" >/dev/null 2>&1 ||
  archive_list_error_status=$?
assert_equal '2' "$archive_list_error_status" \
  'a package archive traversal-list error fails the scan'
archive_extract_error_status=0
PATH="$archive_tar_stub:$PATH" WOARM64_TAR_CAPTURE="$archive_tar_capture" \
  WOARM64_TAR_MODE=extract-fail \
  assert_no_native_recipe_alias_residue w "$archive_error_root" >/dev/null 2>&1 ||
  archive_extract_error_status=$?
assert_equal '2' "$archive_extract_error_status" \
  'a package archive member-extract error fails the scan'
assert_contains "$(cat "$archive_tar_capture")" '--file=' \
  'archive traversal passes the archive through an explicit file option'

external_pkgdest="$root/residue-external/pkgdest"
external_srcdest="$root/residue-external/srcdest"
mkdir -p "$external_pkgdest" "$external_srcdest"
effective_destination_config="$root/residue-external/makepkg_mingw.conf"
{
  printf 'PKGDEST=%q\n' "$external_pkgdest"
  printf 'SRCDEST=%q\n' "$external_srcdest"
  printf 'SRCPKGDEST=%q\n' ''
  printf 'LOGDEST=%q\n' ''
  printf 'BUILDDIR=%q\n' ''
} > "$effective_destination_config"
MSYSTEM=MINGWARM64 load_native_makepkg_output_destinations \
  "$effective_destination_config"
assert_equal "$external_pkgdest" \
  "${WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS[0]}" \
  'effective makepkg configuration supplies PKGDEST for scanning'
assert_equal "$external_srcdest" \
  "${WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS[1]}" \
  'effective makepkg configuration supplies SRCDEST for scanning'
resolve_native_recipe_output_scan_roots \
  "$residue_root" "${WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS[@]}"
resolved_config_destinations=$(printf '%s\n' "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}")
assert_contains "$resolved_config_destinations" "$(cd "$external_pkgdest" && pwd -P)" \
  'configured PKGDEST is resolved as a residue scan root'
assert_contains "$resolved_config_destinations" "$(cd "$external_srcdest" && pwd -P)" \
  'configured SRCDEST is resolved as a residue scan root'

PKGDEST="$external_pkgdest"
SRCDEST="$external_srcdest"
resolve_native_recipe_output_scan_roots "$residue_root"
resolved_destinations=$(printf '%s\n' "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}")
assert_contains "$resolved_destinations" "$(cd "$external_pkgdest" && pwd -P)" \
  'an external PKGDEST is an explicit residue scan root'
assert_contains "$resolved_destinations" "$(cd "$external_srcdest" && pwd -P)" \
  'an external SRCDEST is an explicit residue scan root'
assert_ok 'clean external artifact destinations pass the residue scan' \
  assert_no_native_recipe_alias_residue w "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}"
printf 'builddir = W:/external-package\n' > "$external_pkgdest/gettext.pkg.tar.zst"
assert_fails 'alias residue in external PKGDEST fails the scan' \
  assert_no_native_recipe_alias_residue w "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}"
rm -f "$external_pkgdest/gettext.pkg.tar.zst"
printf 'source evidence W:/external-source\n' > "$external_srcdest/gettext.tar.xz"
assert_fails 'alias residue in external SRCDEST fails the scan' \
  assert_no_native_recipe_alias_residue w "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}"
rm -f "$external_srcdest/gettext.tar.xz"
external_destination_error="$root/residue-external/not-a-directory"
printf 'not a directory\n' > "$external_destination_error"
PKGDEST="$external_destination_error"
destination_error_status=0
resolve_native_recipe_output_scan_roots "$residue_root" >/dev/null 2>&1 ||
  destination_error_status=$?
assert_equal '2' "$destination_error_status" \
  'a non-directory external artifact destination fails the scan setup'
unset PKGDEST SRCDEST

printf 'prefix=W:/cannot-bypass\n' > "$residue_root/mingwarm64/lib/dirty.la"
assert_fails 'WOARM64_SKIP_ALIAS_RESIDUE_SCAN cannot bypass a real leak' \
  env WOARM64_SKIP_ALIAS_RESIDUE_SCAN=1 \
    bash -c 'source "$1"; assert_no_native_recipe_alias_residue w "$2"' \
    bash "$repo_root/.github/scripts/lib/native-recipe-root.sh" "$residue_root"
rm -f "$residue_root/mingwarm64/lib/dirty.la"

assert_ok 'a residue scan of a missing tree is a no-op' \
  assert_no_native_recipe_alias_residue w "$root/residue/absent"

printf '== argument conversion policy ==\n'

assert_equal '-Wl,;-Xlinker;-Wp,;-Wa,;-specs=' "$WOARM64_MSYS2_ARG_CONV_EXCL" \
  'the production argument conversion policy is exact'
assert_contains "$(cat "$repo_root/.github/scripts/build-package.sh")" \
  'export MSYS2_ARG_CONV_EXCL="$WOARM64_MSYS2_ARG_CONV_EXCL"' \
  'the package driver exports the production policy'
assert_contains "$(cat "$repo_root/.github/scripts/build-package.sh")" \
  'load_native_makepkg_output_destinations /etc/makepkg_mingw.conf' \
  'the package driver loads effective makepkg output destinations'
multi_arch_status=0
MINGW_ARCH='mingwarm64 mingw64' \
  bash "$repo_root/.github/scripts/build-package.sh" "$root/no-such-repository" \
  >/dev/null 2>&1 || multi_arch_status=$?
assert_equal '2' "$multi_arch_status" \
  'the package driver rejects unscannable multi-architecture native builds'

capture="$root/args/capture.txt"
capturing_compiler="$root/args/compiler"
make_capturing_compiler "$capturing_compiler"
convert_root="$root/args/work"
mkdir -p "$convert_root/.libs" "$convert_root/deps"
printf 'archive\n' > "$convert_root/.libs/libgettextlib.a"
printf 'script\n' > "$convert_root/version.map"

run_boundary() {
  local status=0

  (
    cd "$convert_root"
    WOARM64_NATIVE_COMPILER_NAME=woarm64-gcc \
      WOARM64_NATIVE_COMPILER="$capturing_compiler" \
      WOARM64_ARGUMENT_CAPTURE="$capture" \
      "$repo_root/.github/scripts/lib/native-compiler.sh" "$@"
  ) || status=$?
  cat "$capture"
  return "$status"
}

# Same invocation, but reporting the boundary's own exit status rather than the
# status of reading the capture file.
run_boundary_status() {
  (
    cd "$convert_root"
    WOARM64_NATIVE_COMPILER_NAME=woarm64-gcc \
      WOARM64_NATIVE_COMPILER="$capturing_compiler" \
      WOARM64_ARGUMENT_CAPTURE="$capture" \
      "$repo_root/.github/scripts/lib/native-compiler.sh" "$@"
  )
}

native_convert_root=$(to_native_path "$convert_root")

expect_arguments() {
  local message=$1
  local expected=$2
  shift 2

  local actual
  actual=$(run_boundary "$@")
  assert_equal "$expected" "$actual" "$message"

  # Idempotence is what makes the policy safe: if the MSYS2 runtime converted an
  # argument first, feeding the converted form back through must not change it.
  local -a second=()
  mapfile -t second <<< "$actual"
  local again
  again=$(run_boundary "${second[@]}")
  assert_equal "$expected" "$again" "$message (idempotent under prior conversion)"
}

expect_arguments 'the linker implib payload is converted' \
  "-Wl,--out-implib,$native_convert_root/.libs/libgettextlib.a" \
  "-Wl,--out-implib,$convert_root/.libs/libgettextlib.a"

expect_arguments 'an absolute rpath payload is converted' \
  "-Wl,-rpath,$native_convert_root/.libs" \
  "-Wl,-rpath,$convert_root/.libs"

expect_arguments 'a joined version-script payload is converted' \
  "-Wl,--version-script=$native_convert_root/version.map" \
  "-Wl,--version-script=$convert_root/version.map"

expect_arguments 'a single-dash Map payload is converted' \
  "-Wl,-Map=$native_convert_root/link.map" \
  "-Wl,-Map=$convert_root/link.map"

expect_arguments 'a joined library path payload is converted' \
  "-Wl,-L$native_convert_root/.libs" \
  "-Wl,-L$convert_root/.libs"

expect_arguments 'an Xlinker pair is converted' \
  "-Xlinker
--out-implib
-Xlinker
$native_convert_root/.libs/libgettextlib.a" \
  -Xlinker --out-implib -Xlinker "$convert_root/.libs/libgettextlib.a"

expect_arguments 'a preprocessor dependency payload is converted' \
  "-Wp,-MD,$native_convert_root/deps/scratch.d" \
  "-Wp,-MD,$convert_root/deps/scratch.d"

expect_arguments 'a joined preprocessor include payload is converted' \
  "-Wp,-I$native_convert_root/deps" \
  "-Wp,-I$convert_root/deps"

expect_arguments 'an assembler include payload is converted' \
  "-Wa,-I,$native_convert_root/deps" \
  "-Wa,-I,$convert_root/deps"

expect_arguments 'a specs path is converted' \
  "-specs=$native_convert_root/deps/native.specs" \
  "-specs=$convert_root/deps/native.specs"

printf '== argument conversion negatives ==\n'

expect_arguments 'whole-archive flags are untouched' \
  '-Wl,--whole-archive
-Wl,--no-whole-archive' \
  -Wl,--whole-archive -Wl,--no-whole-archive

expect_arguments 'a wrapped symbol is untouched' \
  '-Wl,--wrap,malloc' -Wl,--wrap,malloc

expect_arguments 'a defsym assignment is untouched' \
  '-Wl,--defsym,woarm64_marker=1' -Wl,--defsym,woarm64_marker=1

expect_arguments 'an excluded library list is untouched' \
  '-Wl,--exclude-libs,ALL' -Wl,--exclude-libs,ALL

expect_arguments 'an entry symbol is untouched' \
  '-Wl,-e,mainCRTStartup' -Wl,-e,mainCRTStartup

expect_arguments 'an image version number is untouched' \
  '-Wl,--major-image-version,1' -Wl,--major-image-version,1

expect_arguments 'static linking flags are untouched' \
  '-Wl,-Bstatic' -Wl,-Bstatic

expect_arguments 'a dependency target name is untouched' \
  '-Wp,-MT,scratch_buffer.lo' -Wp,-MT,scratch_buffer.lo

expect_arguments 'a bare object stays bare for libtool' \
  'local-input.o' local-input.o

expect_arguments 'a library name is untouched' \
  '-lintl' -lintl

printf '== response file contents ==\n'

response="$convert_root/link.rsp"
{
  printf -- '--out-implib %s/.libs/libgettextsrc.dll.a\n' "$convert_root"
  printf -- '%s/.libs/libgettextlib.a\n' "$convert_root"
  printf -- '--exclude-libs ALL\n'
} > "$response"
response_capture="$root/args/response.txt"
export WOARM64_RESPONSE_CAPTURE="$response_capture"
response_output=$(run_boundary "@$response")
assert_equal '1' "$(printf '%s\n' "$response_output" | wc -l | tr -d ' ')" \
  'a response file collapses to one argument'
rewritten_body=$(cat "$response_capture" 2>/dev/null || true)
assert_contains "$rewritten_body" \
  "$native_convert_root/.libs/libgettextsrc.dll.a" \
  'the response file implib path is converted'
assert_contains "$rewritten_body" \
  "$native_convert_root/.libs/libgettextlib.a" \
  'the response file archive path is converted'
assert_contains "$rewritten_body" '"--out-implib"' \
  'the response file keeps the option that introduced the path'
assert_contains "$rewritten_body" '"ALL"' \
  'the response file leaves a non-path operand alone'
if [[ "$rewritten_body" == *'"--exclude-libs"'* ]]; then
  report ok 'the response file leaves a non-path option alone'
else
  report fail 'the response file leaves a non-path option alone'
fi

quoted_response="$convert_root/quoted.rsp"
printf -- "--out-implib '%s/.libs/q.a'\n" "$convert_root" > "$quoted_response"
quoted_status=0
: > "$capture"
quoted_output=$(run_boundary "@$quoted_response" 2>/dev/null) || quoted_status=$?
assert_equal '2' "$quoted_status" \
  'a single-quoted response file fails before compiler invocation'
assert_equal '' "$quoted_output" \
  'a single-quoted response file is never passed through'

nested_response="$convert_root/nested.rsp"
printf -- '--out-implib %s/.libs/n.a\n@%s\n' "$convert_root" "$response" > "$nested_response"
nested_status=0
: > "$capture"
nested_output=$(run_boundary "@$nested_response" 2>/dev/null) || nested_status=$?
assert_equal '2' "$nested_status" \
  'a nested response file fails before compiler invocation'
assert_equal '' "$nested_output" \
  'a nested response file is never passed through'

missing_tmp_status=0
TMPDIR="$root/does-not-exist/child" \
  run_boundary_status "@$response" >/dev/null 2>&1 || missing_tmp_status=$?
assert_equal '2' "$missing_tmp_status" \
  'a response rewrite mktemp failure fails before compiler invocation'

cleanup_failure_bin="$root/args/cleanup-failure-bin"
cleanup_failure_marker="$root/args/cleanup-failure-marker"
real_rm=$(command -v rm)
mkdir -p "$cleanup_failure_bin"
cat > "$cleanup_failure_bin/rm" <<'EOF'
#!/bin/bash
if [[ ! -e "$WOARM64_RM_FAILURE_MARKER" ]]; then
  : > "$WOARM64_RM_FAILURE_MARKER"
  exit 1
fi
exec "$WOARM64_REAL_RM" "$@"
EOF
chmod +x "$cleanup_failure_bin/rm"
cleanup_failure_status=0
: > "$capture"
PATH="$cleanup_failure_bin:$PATH" \
  WOARM64_REAL_RM="$real_rm" \
  WOARM64_RM_FAILURE_MARKER="$cleanup_failure_marker" \
  run_boundary_status "@$response" >/dev/null 2>&1 || cleanup_failure_status=$?
assert_equal '2' "$cleanup_failure_status" \
  'a response cleanup failure fails before compiler invocation'
assert_equal '' "$(cat "$capture")" \
  'a response cleanup failure is never passed to the compiler'

crlf_response="$convert_root/crlf.rsp"
printf -- '--out-implib %s/.libs/c.a\r\n%s/.libs/libgettextlib.a\r\n' \
  "$convert_root" "$convert_root" > "$crlf_response"
crlf_before=$(sha256sum "$crlf_response" | cut -d' ' -f1)
run_boundary "@$crlf_response" >/dev/null
crlf_body=$(cat "$response_capture" 2>/dev/null || true)
assert_contains "$crlf_body" "\"$native_convert_root/.libs/c.a\"" \
  'a CRLF response file converts without trapping the carriage return'
assert_contains "$crlf_body" "\"$native_convert_root/.libs/libgettextlib.a\"" \
  'a CRLF response file converts every line'
if [[ "$crlf_body" == *$'\r'* ]]; then
  report fail 'a rewritten response file carries no carriage returns'
else
  report ok 'a rewritten response file carries no carriage returns'
fi
assert_equal "$crlf_before" "$(sha256sum "$crlf_response" | cut -d' ' -f1)" \
  'the caller response file is never mutated'

# Parse failures must be rejected before the compiler can observe the original
# response file, and a rewritten response file must not leak or rewrite status.
unterminated_response="$convert_root/unterminated.rsp"
printf -- '--out-implib "%s/.libs/u.a\n' "$convert_root" > "$unterminated_response"
unterminated_status=0
: > "$capture"
unterminated_output=$(run_boundary "@$unterminated_response" 2>/dev/null) ||
  unterminated_status=$?
assert_equal '2' "$unterminated_status" \
  'an unterminated response quote fails before compiler invocation'
assert_equal '' "$unterminated_output" \
  'an unterminated response file is never passed through'

before_temps=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'woarm64-response.*' 2>/dev/null | wc -l)
export WOARM64_FAKE_COMPILER_STATUS=41
response_status=0
run_boundary_status "@$response" >/dev/null 2>&1 || response_status=$?
assert_equal '41' "$response_status" \
  'a rewritten response file preserves a failing compiler status'
after_temps=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'woarm64-response.*' 2>/dev/null | wc -l)
assert_equal "$before_temps" "$after_temps" \
  'a failing compile removes its rewritten response file'
unset WOARM64_FAKE_COMPILER_STATUS
success_status=0
run_boundary_status "@$response" >/dev/null 2>&1 || success_status=$?
assert_equal '0' "$success_status" \
  'a successful compile through a response file still reports success'
assert_equal "$before_temps" \
  "$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'woarm64-response.*' 2>/dev/null | wc -l)" \
  'a successful compile removes its rewritten response file'
unset WOARM64_RESPONSE_CAPTURE

printf '== MSYS to native PE argument representation ==\n'

# The production policy deliberately leaves the simple argument classes to the
# MSYS2 runtime and owns only the payload dialects. That split is only safe if
# the runtime really does convert the simple classes, so pin the behaviour here
# rather than assuming it.
observer_ps1="$root/observer/dump.ps1"
powershell_exe=/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
observer_out="$root/observer/out.txt"
if [[ -x "$powershell_exe" ]]; then
  make_commandline_observer "$observer_ps1"
  observe_arguments() {
    local mode=$1
    shift

    rm -f "$observer_out"
    if [[ "$mode" == "policy" ]]; then
      WOARM64_PROBE_OUT=$(to_native_path "$observer_out") \
        MSYS2_ARG_CONV_EXCL="$WOARM64_MSYS2_ARG_CONV_EXCL" \
        "$powershell_exe" -NoProfile -File "$(to_native_path "$observer_ps1")" "$@" \
        >/dev/null 2>&1 || return 1
    else
      WOARM64_PROBE_OUT=$(to_native_path "$observer_out") \
        env -u MSYS2_ARG_CONV_EXCL \
        "$powershell_exe" -NoProfile -File "$(to_native_path "$observer_ps1")" "$@" \
        >/dev/null 2>&1 || return 1
    fi
    [[ -f "$observer_out" ]] || return 1
    tr -d '\r' < "$observer_out"
  }

  if ! observed=$(observe_arguments policy \
      "-I$convert_root/.libs" \
      "-DLOCALEDIR=\"$convert_root/.libs\"" \
      "$convert_root/.libs/libgettextlib.a" \
      -o "$convert_root/out.o" \
      -Xlinker "$convert_root/.libs/libgettextlib.a" \
      "-Wl,--out-implib,$convert_root/.libs/libgettextlib.a"); then
    report fail 'the runtime representation observer executes successfully'
  elif [[ -z "$observed" ]]; then
    # PowerShell is present, so an empty capture means the observer broke rather
    # than that the probe is unavailable. Failing here keeps a real runtime
    # conversion regression from being silently tolerated.
    report fail 'the runtime representation observer produced output'
  else
    assert_contains "$observed" "-I$native_convert_root/.libs" \
      'the runtime converts a joined include path under the production policy'
    assert_contains "$observed" "-DLOCALEDIR=\"$native_convert_root/.libs\"" \
      'the runtime converts a quoted define and preserves its quotes'
    assert_contains "$observed" "$native_convert_root/.libs/libgettextlib.a" \
      'the runtime converts a bare path operand'
    assert_contains "$observed" "$native_convert_root/out.o" \
      'the runtime converts an output operand'
    # This is the assertion that proves the exclusion list is in force: the
    # payload stays POSIX so native-compiler.sh is its single explicit owner.
    assert_contains "$observed" "-Wl,--out-implib,$convert_root/.libs/libgettextlib.a" \
      'the production policy leaves the linker payload for the boundary to convert'

    # Composition: what the runtime delivers, fed through the boundary, must
    # reach the compiler in the intended native form.
    mapfile -t observed_arguments <<< "$observed"
    composed=$(run_boundary "${observed_arguments[@]}")
    assert_contains "$composed" "-I$native_convert_root/.libs" \
      'the boundary leaves an already-converted include path alone'
    assert_contains "$composed" "-DLOCALEDIR=\"$native_convert_root/.libs\"" \
      'the boundary leaves an already-converted quoted define alone'
    assert_contains "$composed" "-Wl,--out-implib,$native_convert_root/.libs/libgettextlib.a" \
      'the boundary converts the linker payload the runtime left alone'

    # @ remains under ordinary MSYS conversion so direct native tools do not
    # inherit a POSIX path. The compiler boundary converts it back only to read
    # and rewrite its contents.
    direct_response=$(observe_arguments policy "@$response") ||
      direct_response=
    if [[ -z "$direct_response" ]]; then
      report fail 'the direct native response observer produced output'
    else
      assert_contains "$direct_response" "@$(to_native_path "$response")" \
        'a direct native tool receives a usable Windows response path'
    fi
  fi
else
  report fail 'Windows PowerShell is required for the runtime representation observer'
fi

# Documents why the policy is a prefix list and not '*': the boundary
# deliberately does not rewrite -D values, so disabling runtime conversion
# entirely would bake a POSIX path into the compiled artefact.
define_output=$(run_boundary "-DLOCALEDIR=\"/mingwarm64/share/locale\"")
assert_equal '-DLOCALEDIR="/mingwarm64/share/locale"' "$define_output" \
  'the boundary relies on the runtime for defines and never rewrites them'

printf '\n%s checks, %s failures\n' "$checks" "$failures"
if [[ $failures -ne 0 ]]; then
  echo "native boundary regression tests failed" >&2
  exit 1
fi
echo "native boundary regression tests passed"
