if {[llength $argv] != 1} { error "Expected one owned fixture directory" }
set work [lindex $argv 0]
if {[file normalize [info library]] ne [file normalize $env(TCL_LIBRARY)]} {
    error "Tcl library came from outside the explicit relocated stage"
}
if {[info patchlevel] ne "8.6.12"} { error "Unexpected Tcl version" }
if {$tcl_platform(platform) ne "unix" || $tcl_platform(wordSize) != 8 ||
    $tcl_platform(pointerSize) != 8 || !$tcl_platform(threaded)} {
    error "Expected threaded MSYS LP64 Tcl, not MinGW Tcl"
}
set text "native Tcl \u03bb \u96ea caf\u00e9"
set bytes [encoding convertto utf-8 $text]
if {[encoding convertfrom utf-8 $bytes] ne $text} { error "UTF-8 roundtrip failed" }
if {[zlib decompress [zlib compress $bytes]] ne $bytes} { error "Zlib roundtrip failed" }
if {[expr {wide(1) << 40}] != 1099511627776} { error "Wide arithmetic failed" }
set data [dict create unicode $text values [list 1 2 3]]
if {[dict get $data unicode] ne $text || [llength [dict get $data values]] != 3} {
    error "Dictionary/list API failed"
}
if {![regexp {Tcl (.+) caf} $text match symbols] || $symbols ne "\u03bb \u96ea"} {
    error "Unicode regexp failed"
}
file mkdir $work
set path [file join $work "roundtrip-\u03bb.txt"]
set channel [open $path wb]
puts -nonewline $channel $bytes
close $channel
set channel [open $path rb]
set actual [read $channel]
close $channel
if {$actual ne $bytes} { error "Unicode file roundtrip failed" }
if {[package require Itcl] ne "4.2.2"} { error "Itcl package missing" }
if {[package require tdbc] ne "1.1.3"} { error "TDBC core missing" }
if {[package require Thread] ne "2.8.7"} { error "Thread package missing" }
set worker [thread::create -joinable {thread::wait}]
set answer [thread::send $worker {expr {6 * 7}}]
thread::release $worker
thread::join $worker
if {$answer != 42} { error "Native Tcl thread exchange failed" }
puts "native-msys-tcl-core-api-passed"
