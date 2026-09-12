namespace eval ::native_git_fixture {
    variable root [file normalize [lindex $::argv 0]]
    variable output [file normalize [lindex $::argv 1]]
    variable tool [lindex $::argv 2]
    variable attempts 0
    if {$tool eq "gitk"} {
        variable script [file join $root clangarm64 bin gitk]
        variable expected [list "Native ARM64 second fixture" "second native content \u03bb"]
    } elseif {$tool eq "git-gui"} {
        variable script [file join $root clangarm64 libexec git-core git-gui]
        variable expected [list "tracked.txt"]
    } else {
        error "Unknown native Git GUI fixture"
    }
    proc write_file {name content} {
        variable output
        set stream [open [file join $output $name] w]
        fconfigure $stream -encoding utf-8 -translation lf
        puts -nonewline $stream $content
        close $stream
    }
    proc text_tree {widget} {
        set result ""
        switch -- [winfo class $widget] {
            Text { append result "$widget: [$widget get 1.0 end]\n" }
            Listbox { append result "$widget: [$widget get 0 end]\n" }
            Label - TLabel - Button - TButton {
                append result "$widget: [$widget cget -text]\n"
            }
            Canvas {
                foreach item [$widget find all] {
                    if {[$widget type $item] eq "text"} {
                        append result "$widget/$item: [$widget itemcget $item -text]\n"
                    }
                }
            }
        }
        foreach child [winfo children $widget] {
            append result [text_tree $child]
        }
        return $result
    }
    proc observe {} {
        variable expected
        variable attempts
        incr attempts
        set text [text_tree .]
        set missing 0
        foreach item $expected {
            if {[string first $item $text] < 0} { set missing 1 }
        }
        if {$missing} {
            if {$attempts >= 100} {
                write_file widget-text.txt $text
                error "Actual Git GUI did not show the expected repository content"
            }
            after 100 ::native_git_fixture::observe
            return
        }
        write_file widget-text.txt $text
        write_file window.txt [wm frame .]
        write_file title.txt [wm title .]
        write_file ready [pid]
        after 50 ::native_git_fixture::wait_for_controller
    }
    proc wait_for_controller {} {
        variable output
        if {[file exists [file join $output continue]]} {
            puts "native-git-gui-fixture-passed"
            exit 0
        }
        after 50 ::native_git_fixture::wait_for_controller
    }
}
proc bgerror {message} {
    ::native_git_fixture::write_file fixture-error.txt "$message\n$::errorInfo"
    exit 1
}
set argv {}
set argc 0
set argv0 $::native_git_fixture::script
after 100 ::native_git_fixture::observe
source $::native_git_fixture::script
