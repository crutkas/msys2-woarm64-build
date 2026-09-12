set script [lindex $argv 0]
set argv [lrange $argv 1 end]
set argc [llength $argv]
try {
    source $script
} on error {message options} {
    set stream [open [file join [lindex $argv 1] fixture-error.txt] w]
    puts $stream [dict get $options -errorinfo]
    close $stream
    puts stderr $message
    exit 1
}
