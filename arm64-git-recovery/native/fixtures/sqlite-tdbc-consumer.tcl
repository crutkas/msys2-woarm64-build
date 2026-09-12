proc require {condition message} {
    if {![uplevel 1 [list expr $condition]]} {error $message}
}
require {[info patchlevel] eq "8.6.12"} "Pinned MSYS Tcl version"
require {$tcl_platform(platform) eq "unix" && $tcl_platform(wordSize) == 8 &&
         $tcl_platform(pointerSize) == 8} "MSYS LP64 Tcl ABI"
require {[package require sqlite3] eq "3.53.4"} "Pinned SQLite version"
require {[package require tdbc::sqlite3] eq "1.1.3"} "Pinned TDBC SQLite module"
set database [lindex $argv 0]
tdbc::sqlite3::connection create connection $database -timeout 2000
connection allrows {CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT)}
set insert [connection prepare {INSERT INTO records VALUES(:id, :value)}]
set id 1
set value "native \u03bb \u96ea"
set result [$insert execute]
$result close
connection begintransaction
set result [$insert execute [dict create id 2 value rollback]]
$result close
connection rollback
connection begintransaction
set result [$insert execute [dict create id 3 value committed]]
$result close
connection commit
set query [connection prepare {SELECT id,value FROM records ORDER BY id}]
set result [$query execute]
set rows [$result allrows -as dicts]
$result close
require {[llength $rows] == 2} "Commit/rollback row count"
require {[dict get [lindex $rows 0] id] == 1 &&
         [dict get [lindex $rows 0] value] eq $value} "Parameterized Unicode value"
require {[dict get [lindex $rows 1] id] == 3 &&
         [dict get [lindex $rows 1] value] eq "committed"} "Committed bound value"
require {[dict exists [connection tables] records]} "TDBC table metadata"
require {[dict exists [connection columns records] value]} "TDBC column metadata"
set integrity [connection allrows -as lists {PRAGMA integrity_check}]
require {$integrity eq "ok"} "TDBC integrity check"
$query close
$insert close
connection close
require {[file isfile $database]} "Actual Unicode database filename"
puts "native-msys-sqlite-tdbc-consumer-passed"
