set same [lindex $argv 0]
set foreign [lindex $argv 1]
set shellscript [lindex $argv 2]
set native [lindex $argv 3]
set nativescript [lindex $argv 4]
foreach phase {inherited mutated} {
  if {$phase eq "mutated"} {
    set ::env(WOARM64_ENV_INHERITED) tcl-replaced
    set ::env(WOARM64_ENV_NEW) tcl-new
    set ::env(CCACHE_DISABLE) tcl-marker
  }
  puts "TCL PHASE $phase"
  foreach name {WOARM64_ENV_INHERITED WOARM64_ENV_NEW CCACHE_DISABLE TMPDIR PATH MSYSTEM} {
    if {[info exists ::env($name)]} {puts "TCL $name=<$::env($name)>"} else {puts "TCL $name=<absent>"}
  }
  puts [exec $same --inspect 2>@1]
  puts [exec $foreign --noprofile --norc $shellscript 2>@1]
  puts [exec $native -B $nativescript 2>@1]
}
