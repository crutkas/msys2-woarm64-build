if {$tcl_version ne "8.6" || [info patchlevel] ne "8.6.12" ||
    $tcl_platform(platform) ne "unix" || $tcl_platform(wordSize) != 8 ||
    $tcl_platform(pointerSize) != 8} {
  error "Expected actual MSYS LP64 Tcl 8.6.12"
}
set root [lindex $argv 0]
foreach key {PATH HOME TMP TEMP TMPDIR CCACHE CCACHE_DISABLE CCACHE_DIR MSYS2_ARG_CONV_EXCL MSYS2_ENV_CONV_EXCL} {
  if {[info exists ::env($key)]} {puts "native-env $key=$::env($key)"} else {puts "native-env $key=<absent>"}
}
foreach path [lrange $argv 1 end] {
  set f [open $path rb]
  if {[string length [read $f 16]] != 16} {error "Unreadable full absolute input: $path"}
  close $f
}
set filename [file join $root "native-path-\u03bb.txt"]
set f [open $filename w]
fconfigure $f -encoding utf-8
puts -nonewline $f "SQLite native Tcl \u03bb"
close $f
set f [open $filename r]
fconfigure $f -encoding utf-8
set value [read $f]
close $f
if {$value ne "SQLite native Tcl \u03bb"} {error "Unicode file roundtrip mismatch"}
puts "sqlite-native-tcl-path-interop-passed [info nameofexecutable] [info patchlevel]"
