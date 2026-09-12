proc requireEqual {actual expected description} {
    if {$actual ne $expected} {error "$description: unexpected result"}
}
set root [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
requireEqual [info patchlevel] 8.6.18 version
requireEqual [file normalize [info library]] [file join $root lib tcl8.6] library
set auto_path [list [file join $root lib] [info library]]
set text "native Tcl \u03bb \u96ea\n"
set bytes [encoding convertto utf-8 [string repeat $text 4096]]
requireEqual [zlib decompress [zlib compress $bytes]] $bytes zlib
requireEqual [expr {wide(2147483647) * 4}] 8589934588 wide-arithmetic
requireEqual [expr {2.25 * 4.0}] 9.0 floating-arithmetic
set path [file join $output "roundtrip-\u03bb.txt"]
set stream [open $path wb]
puts -nonewline $stream $bytes
close $stream
set stream [open $path rb]
requireEqual [read $stream] $bytes file-roundtrip
close $stream
package require sqlite3
sqlite3 database :memory:
database eval {create table records(value text); insert into records values($text)}
requireEqual [database onecolumn {select value from records}] $text sqlite
database close
package require tdbc::sqlite3
tdbc::sqlite3::connection create connection :memory:
connection allrows {create table records(value integer)}
connection allrows {insert into records values(42)}
requireEqual [connection allrows -as lists {select value from records}] 42 tdbc
connection close
package require Thread
set worker [thread::create {thread::wait}]
requireEqual [thread::send $worker {expr {6 * 7}}] 42 thread
thread::release $worker
set testTk [expr {[llength $argv] == 3 && [lindex $argv 2] eq "tk"}]
if {$testTk} {
    source [file join [file dirname [info script]] native-tk-widgets.tcl]
}
set stream [open [file join $output ready.pending] w]
puts $stream [pid]
close $stream
file rename -- [file join $output ready.pending] [file join $output ready]
proc waitForRelease {} {
    if {[file exists [file join $::output continue]]} {
        set ::released 1
    } else {
        after 50 waitForRelease
    }
}
after [expr {$testTk ? 150000 : 20000}] {puts stderr "Native observer did not release Tcl"; exit 1}
waitForRelease
if {![info exists released]} {vwait released}
puts "native-tcl-smoke-passed"
if {$testTk} {destroy .; exit 0}
