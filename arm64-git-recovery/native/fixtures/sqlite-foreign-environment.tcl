puts "native interpreter [info nameofexecutable]"
foreach name {autosetup_tclsh CCACHE_DISABLE MSYS2_ARG_CONV_EXCL SQLITE_TEST_TCL_CONFIG TMPDIR} {
  if {[info exists ::env($name)]} {puts "TCL $name=$::env($name)"} else {puts "TCL $name=<absent>"}
}
set shell [lindex $argv 0]
set jim [lindex $argv 1]
set test [lindex $argv 2]
puts "BEGIN foreign child environment"
puts [exec $shell --noprofile --norc -c {
  printf 'BASH autosetup_tclsh=%s CCACHE_DISABLE=%s MSYS2_ARG_CONV_EXCL=%s SQLITE_TEST_TCL_CONFIG=%s TMPDIR=%s\n' \
    "${autosetup_tclsh-<absent>}" "${CCACHE_DISABLE-<absent>}" "${MSYS2_ARG_CONV_EXCL-<absent>}" \
    "${SQLITE_TEST_TCL_CONFIG-<absent>}" "${TMPDIR-<absent>}"
} 2>@1]
puts "BEGIN direct named host Jim selftest"
puts [exec $jim $test 2>@1]
