requireEqual [package require Tk] 8.6.18 Tk-version
requireEqual [file normalize $tk_library] [file join $root lib tk8.6] Tk-library
wm title . "Native ARM64 Tcl/Tk fixture"
wm geometry . 620x300
ttk::frame .body -padding 20
pack .body -fill both -expand 1
ttk::label .body.heading -text "Source-built ARM64 Tcl/Tk" -font TkHeadingFont
ttk::label .body.explanation -text "Unicode entry, native keyboard events, PNG and callbacks"
ttk::entry .body.entry -width 52
ttk::button .body.save -text "Save fixture" -command saveFixture
ttk::label .body.status -text "Waiting for keyboard input"
pack .body.heading .body.explanation .body.entry .body.save .body.status -anchor w -pady 8
proc saveFixture {} {
    set stream [open [file join $::output tk-saved.pending] w]
    fconfigure $stream -encoding utf-8 -translation lf
    puts -nonewline $stream [.body.entry get]
    close $stream
    file rename -- [file join $::output tk-saved.pending] [file join $::output tk-saved.txt]
    .body.status configure -text "Saved exact Unicode fixture"
}
bind .body.entry <Return> {.body.save invoke; break}
image create photo sample -width 3 -height 2
sample put #123456 -to 0 0 3 2
sample write [file join $output tk-image.png] -format png
image create photo decoded -file [file join $output tk-image.png]
requireEqual [decoded get 1 1] {18 52 86} PNG-readback
if {[font measure TkDefaultFont "ARM64 \u03bb"] <= 0} {error "Native font measurement failed"}
update
focus -force .body.entry
set stream [open [file join $output widgets.json] w]
puts $stream [format {{"window":"%s","entry":"%s"}} [wm frame .] [winfo id .body.entry]]
close $stream
