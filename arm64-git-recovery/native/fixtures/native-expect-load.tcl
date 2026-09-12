puts "native Tcl [info patchlevel]"
if {[llength $argv] == 1} {
    lappend auto_path [lindex $argv 0]
    package require Expect
    puts "native Expect [package provide Expect]"
}
