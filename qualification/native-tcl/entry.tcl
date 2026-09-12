namespace eval ::qualification {
    variable mode [lindex $::argv 0]
    variable script [lindex $::argv 1]
    set ::argv [lrange $::argv 2 end]
    proc hold {} {
        set ready [open [file join $::env(TCL_QUALIFICATION_WORK) ready] w]
        puts $ready ready
        close $ready
        set deadline [expr {[clock milliseconds] + 20000}]
        while {![file exists [file join $::env(TCL_QUALIFICATION_WORK) continue]]} {
            if {[clock milliseconds] > $deadline} {
                error "Native process/module handshake timed out"
            }
            after 25
        }
    }
}
if {[file normalize [info library]] ne [file normalize $env(TCL_LIBRARY)] ||
    [info patchlevel] ne "8.6.12" || $tcl_platform(platform) ne "unix" ||
    $tcl_platform(wordSize) != 8 || $tcl_platform(pointerSize) != 8 ||
    !$tcl_platform(threaded)} {
    error "Expected the exact private native MSYS LP64 Tcl 8.6.12"
}
if {$::qualification::mode eq "suite"} {
    ::qualification::hold
}
source $::qualification::script
if {$::qualification::mode eq "api"} {
    ::qualification::hold
}
