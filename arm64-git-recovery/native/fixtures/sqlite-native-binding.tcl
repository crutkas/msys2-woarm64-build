set root [lindex $argv 0]
set libdir [lindex $argv 1]
lappend auto_path $libdir
if {[info patchlevel] ne "8.6.12" || $tcl_platform(platform) ne "unix" ||
    $tcl_platform(wordSize) != 8 || $tcl_platform(pointerSize) != 8} {
  error "Not the pinned MSYS LP64 Tcl interpreter"
}
if {[package require sqlite3] ne "3.53.4"} {error "Wrong SQLite binding"}
set database [file join $root "binding-\u03bb.sqlite"]
sqlite3 db $database
db eval {PRAGMA journal_mode=WAL; CREATE TABLE t(id INTEGER PRIMARY KEY, value TEXT);}
set value "native \u03bb \u96ea"
db transaction {
  db eval {INSERT INTO t(value) VALUES($value)}
}
if {[db onecolumn {SELECT value FROM t}] ne $value} {error "UTF-8 Tcl binding roundtrip"}
if {[db onecolumn {SELECT sqrt(81)}] != 9} {error "Tcl binding floating point"}
db eval {CREATE VIRTUAL TABLE ft USING fts5(value); INSERT INTO ft VALUES('native sqlite');}
if {[db onecolumn {SELECT count(*) FROM ft WHERE ft MATCH 'sqlite'}] != 1} {error "Tcl FTS5"}
set errors [db onecolumn {PRAGMA integrity_check}]
if {$errors ne "ok"} {error "Database integrity failure: $errors"}
db close
if {![file isfile $database]} {error "Native Tcl did not create actual Unicode filename"}
puts "sqlite-native-tcl-binding-passed [info patchlevel] [package require sqlite3]"
