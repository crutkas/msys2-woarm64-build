lappend auto_path [lindex $argv 0]
package require Expect
set timeout 10
log_user 1
if {[lindex $argv 1] in {"--direct-stty" "--bare" "--exec-true" "--open-slave"}} {
    exp_spawn -nottyinit cat -u
} else {
    exp_spawn cat -u
}
puts "slave=$spawn_out(slave,name)"
if {[lindex $argv 1] in {"--bare" "--exec-true" "--open-slave"}} {
    if {[lindex $argv 1] eq "--exec-true"} {
        exec /bin/true
    } elseif {[lindex $argv 1] eq "--open-slave"} {
        set probe [open $spawn_out(slave,name) r]
        close $probe
    }
    set status 0
    set message "no stty subprocess"
    set options {}
} elseif {[lindex $argv 1] eq "--direct-stty"} {
    set status [catch {exec /bin/stty < $spawn_out(slave,name) > /dev/null} message options]
} else {
    set status [catch {exp_stty < $spawn_out(slave,name)} message options]
}
puts "stty_status=$status message=$message options=$options"
send -- "native-pty-roundtrip\r"
expect {
    "native-pty-roundtrip" { puts "PTY_ROUNDTRIP_OK" }
    timeout { error "native PTY round trip timed out" }
    eof {
        puts stderr "EOF_BUFFER=$expect_out(buffer)"
        puts stderr "EOF_WAIT=[wait]"
        error "native PTY ended before round trip"
    }
}
send -- "\004"
expect {
    eof {}
    timeout { error "native PTY child did not finish after EOF" }
}
puts "child_wait=[wait]"
if {$status != 0} {
    error "original stty operation failed: $message"
}
