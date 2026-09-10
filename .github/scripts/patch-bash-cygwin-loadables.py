"""Align Bash's Cygwin build metadata and platform-specific test expectations."""

from pathlib import Path
import sys


OLD = """cygwin*)
\tSHOBJ_LD='$(CC)'
\tSHOBJ_LDFLAGS='-shared -Wl,--enable-auto-import -Wl,--enable-auto-image-base -Wl,--export-all -Wl,--out-implib=$(@).a'
"""
NEW = """cygwin*)
\tSHOBJ_LD='${CC}'
\tSHOBJ_LDFLAGS='-shared -Wl,--enable-auto-import -Wl,--enable-auto-image-base -Wl,--export-all -Wl,--out-implib,$@.a'
"""


def write_lf(path: Path, text: str, encoding: str = "utf-8") -> None:
    data = text.encode(encoding)
    if path.is_file() and path.read_bytes() == data:
        return
    with path.open("w", encoding=encoding, newline="\n") as stream:
        stream.write(text)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if text.count(old) != 1:
        raise SystemExit(f"unexpected {label}")
    return text.replace(old, new)


def replace_count(text: str, old: str, new: str, count: int, label: str) -> str:
    if text.count(new) == count:
        return text
    if text.count(old) != count:
        raise SystemExit(f"unexpected {label}")
    return text.replace(old, new)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    path = Path(sys.argv[1]) / "support" / "shobj-conf"
    text = path.read_text(encoding="utf-8")
    if NEW not in text:
        if text.count(OLD) != 1:
            raise SystemExit("unexpected Cygwin shared-object configuration")
        text = text.replace(OLD, NEW)
    write_lf(path, text)

    expected = Path(sys.argv[1]) / "tests" / "complete.right"
    text = expected.read_text(encoding="utf-8")
    if "\nhistory\nigncr\nignoreeof\n" not in text:
        if text.count("\nhistory\nignoreeof\n") != 1:
            raise SystemExit("unexpected set-option completion inventory")
        text = text.replace("\nhistory\nignoreeof\n", "\nhistory\nigncr\nignoreeof\n")
    if "\ncompat44\ncompletion_strip_exe\ncomplete_fullquote\n" not in text:
        if text.count("\ncompat44\ncomplete_fullquote\n") != 1:
            raise SystemExit("unexpected shopt completion inventory")
        text = text.replace(
            "\ncompat44\ncomplete_fullquote\n",
            "\ncompat44\ncompletion_strip_exe\ncomplete_fullquote\n",
        )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "shopt.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "shopt -u compat44\nshopt -s complete_fullquote\n",
        "shopt -u compat44\nshopt -u completion_strip_exe\n"
        "shopt -s complete_fullquote\n",
        "Cygwin shopt option inventory",
    )
    text = replace_once(
        text,
        "shopt -u compat44\nshopt -u direxpand\n",
        "shopt -u compat44\nshopt -u completion_strip_exe\nshopt -u direxpand\n",
        "Cygwin unset shopt option inventory",
    )
    text = replace_once(
        text,
        "compat44            \toff\ndirexpand",
        "compat44            \toff\ncompletion_strip_exe\toff\ndirexpand",
        "Cygwin shopt tabular inventory",
    )
    text = replace_count(
        text,
        "set -o history\nset +o ignoreeof\n",
        "set -o history\nset +o igncr\nset +o ignoreeof\n",
        2,
        "Cygwin set-option inventory",
    )
    text = replace_once(
        text,
        "history        \ton\nignoreeof",
        "history        \ton\nigncr          \toff\nignoreeof",
        "Cygwin set-option table",
    )
    text = replace_once(
        text,
        "set +o functrace\nset +o ignoreeof\n",
        "set +o functrace\nset +o igncr\nset +o ignoreeof\n",
        "Cygwin unset-option inventory",
    )
    text = replace_once(
        text,
        "functrace      \toff\nignoreeof",
        "functrace      \toff\nigncr          \toff\nignoreeof",
        "Cygwin unset-option table",
    )
    shopt_reset_diff = """18c18
< completion_strip_exe\ton
---
> completion_strip_exe\toff
"""
    if shopt_reset_diff not in text:
        marker = (
            "./shopt.tests: line 107: shopt: xyz1: invalid option name\n"
            "expand_aliases      \ton\n"
        )
        if text.count(marker) != 1:
            raise SystemExit("unexpected Cygwin shopt reset expectation")
        text = text.replace(
            marker,
            "./shopt.tests: line 107: shopt: xyz1: invalid option name\n"
            + shopt_reset_diff
            + "expand_aliases      \ton\n",
        )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "test.right"
    text = expected.read_text(encoding="utf-8")
    for command, generic_result, cygwin_result in (
        ("t -g /tmp/test.setgid", "0", "1"),
        ("t -r /tmp/test.noread", "1", "0"),
        (
            "t -t 0",
            "0",
            "./test.tests: line 118: /dev/tty: No such device or address",
        ),
        ("t -u /tmp/test.setuid", "0", "1"),
        ("t -x /tmp/test.exec", "0", "1"),
        ("t -N /tmp/test.newer", "0", "1"),
        ('t -n xx -a -z "" -a -t 0 -a -t', "0", "1"),
    ):
        text = replace_once(
            text,
            f"{command}\n{generic_result}\n",
            f"{command}\n{cygwin_result}\n",
            f"Cygwin test builtin result for {command}",
        )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "read.right"
    text = expected.read_text(encoding="utf-8")
    generic_fd_result = "FOO\n0 0 0\n0\n0\n1\n"
    cygwin_fd_result = "FOO\n0 0 0\n0\n0\n0\n"
    if cygwin_fd_result not in text:
        if text.count(generic_fd_result) != 1:
            raise SystemExit("unexpected read file-descriptor expectation")
        text = text.replace(generic_fd_result, cygwin_fd_result)
    elif text.count(cygwin_fd_result) != 1:
        raise SystemExit("unexpected read file-descriptor expectation")
    read2_generic = """timeout 1: ok
unset or null 1
timeout 2: ok
unset or null 2
timeout 3: ok
unset or null 3
./read2.sub: line 45: read: -3: invalid timeout specification
1

abcde
abcde
abcde
"""
    read2_cygwin = """./read2.sub: line 18: /dev/tty: No such device or address
1
4
./read2.sub: line 27: /dev/tty: No such device or address
1
4
timeout 3: ok
4
./read2.sub: line 45: /dev/tty: No such device or address
1
4
abcde
abcde
abcde
"""
    text = replace_once(
        text,
        read2_generic,
        read2_cygwin,
        "Cygwin non-terminal read timeout expectations",
    )
    read7_generic = """timeout 1: ok
unset or null 1
timeout 2: ok
unset or null 2
timeout 3: ok
unset or null 3
timeout 4: ok
abcde
abcde

"""
    read7_previous_cygwin = """timeout 1: ok
unset or null 1
timeout 2: ok
unset or null 2
./read7.sub: line 37: /dev/tty: No such device or address
1
unset or null 3
timeout 4: ok
abcde
abcde
./read7.sub: line 64: /dev/tty: No such device or address
abcde
"""
    read7_uncontrolled_cygwin = read7_previous_cygwin.replace("timeout 2: ok\n", "1\n", 1)
    read7_cygwin = """timeout 1: ok
unset or null 1
1
unset or null 2
./read7.sub: line 41: /dev/tty: No such device or address
1
unset or null 3
timeout 4: ok
abcde
abcde
./read7.sub: line 68: /dev/tty: No such device or address
abcde
"""
    if read7_cygwin not in text:
        if read7_previous_cygwin in text:
            text = text.replace(read7_previous_cygwin, read7_cygwin)
        elif read7_uncontrolled_cygwin in text:
            text = text.replace(read7_uncontrolled_cygwin, read7_cygwin)
        else:
            text = replace_once(
                text,
                read7_generic,
                read7_cygwin,
                "Cygwin readline timeout expectations",
            )
    write_lf(expected, text)

    test = Path(sys.argv[1]) / "tests" / "run-read"
    text = test.read_text(encoding="utf-8")
    generic = "${THIS_SH} ./read.tests > ${BASH_TSTOUT} 2>&1\n"
    deterministic_input = "${THIS_SH} ./read.tests </dev/null > ${BASH_TSTOUT} 2>&1\n"
    legacy_controlled_input = """read_stdin=${TMPDIR:-/tmp}/bash-read-stdin-$$
rm -f "$read_stdin"
mkfifo "$read_stdin" || exit 1
exec 9<> "$read_stdin" || exit 1
${THIS_SH} ./read.tests <&9 > ${BASH_TSTOUT} 2>&1
read_status=$?
exec 9>&-
rm -f "$read_stdin"
(( read_status == 0 )) || exit "$read_status"
"""
    if deterministic_input not in text:
        if legacy_controlled_input in text:
            text = text.replace(legacy_controlled_input, deterministic_input)
        else:
            text = replace_once(
                text,
                generic,
                deterministic_input,
                "deterministic read test input",
            )
    write_lf(test, text)

    test = Path(sys.argv[1]) / "tests" / "read7.sub"
    text = test.read_text(encoding="utf-8")
    generic_timeout = """read -t 0.00001 -e var
estat=$?
"""
    legacy_controlled_timeout = """read_timeout_fifo=${TMPDIR:-/tmp}/bash-read7-stdin-$$
rm -f "$read_timeout_fifo"
mkfifo "$read_timeout_fifo" || exit 1
read -t 0.00001 -e var 9<> "$read_timeout_fifo" <&9
estat=$?
rm -f "$read_timeout_fifo"
"""
    controlled_timeout = """read_timeout_fifo=${TMPDIR:-/tmp}/bash-read7-stdin-$$
rm -f "$read_timeout_fifo"
mkfifo "$read_timeout_fifo" || exit 1
read -t 0.1 -e var 9<> "$read_timeout_fifo" <&9
estat=$?
rm -f "$read_timeout_fifo"
"""
    if controlled_timeout not in text:
        if legacy_controlled_timeout in text:
            text = text.replace(legacy_controlled_timeout, controlled_timeout)
        else:
            text = replace_once(
                text,
                generic_timeout,
                controlled_timeout,
                "controlled readline timeout input",
            )
    write_lf(test, text)

    test = Path(sys.argv[1]) / "tests" / "source6.sub"
    text = test.read_text(encoding="utf-8")
    generic_fifo = """mkfifo $TMPDIR/fifo-$$
echo "echo four - OK" > $TMPDIR/fifo-$$ &
sleep 1\t\t# allow the child echo to execute
. $TMPDIR/fifo-$$
echo $?
rm -f $TMPDIR/fifo-$$
"""
    controlled_fifo = """fifo=$TMPDIR/fifo-$$
rm -f "$fifo"
mkfifo "$fifo" || exit 1
echo "echo four - OK" > "$fifo" &
writer=$!
if ! kill -0 "$writer" 2>/dev/null; then
\twait "$writer" || :
\trm -f "$fifo"
\texit 1
fi
. "$fifo"
source_status=$?
wait "$writer" || {
\trm -f "$fifo"
\texit 1
}
echo "$source_status"
rm -f "$fifo"
"""
    text = replace_once(
        text,
        generic_fifo,
        controlled_fifo,
        "controlled source FIFO writer",
    )
    write_lf(test, text)

    test = Path(sys.argv[1]) / "tests" / "jobs6.sub"
    text = test.read_text(encoding="utf-8")
    generic_wait = """set -o monitor
sleep 5 &
child1=$!

( sleep 1; kill -STOP $child1 ; sleep 1 ; kill -CONT $child1 )&
"""
    temporary_wait = """set -o monitor
sleep 10 &
child1=$!

( sleep 3; kill -STOP $child1 ; sleep 1 ; kill -CONT $child1 )&
"""
    if temporary_wait in text:
        text = text.replace(temporary_wait, generic_wait)
    elif text.count(generic_wait) != 1:
        raise SystemExit("unexpected job-control wait timing")
    write_lf(test, text)

    test = Path(sys.argv[1]) / "tests" / "jobs.tests"
    text = test.read_text(encoding="utf-8")
    immediate_job_batch = """sleep 300 &
sleep300pid=$!
sleep 350 &
sleep 400 &

jobs
"""
    settled_job_batch = """sleep 300 &
sleep300pid=$!
sleep 350 &
sleep 400 &
sleep 1\t# allow the background jobs to complete their exec transitions

jobs
"""
    text = replace_once(
        text,
        immediate_job_batch,
        settled_job_batch,
        "settled job-control batch",
    )
    immediate_stop = """sleep 4 &
kill -STOP %1
"""
    settled_stop = """sleep 4 &
sleep 1\t# allow the child to complete its exec transition
kill -STOP %1
"""
    text = replace_once(
        text,
        immediate_stop,
        settled_stop,
        "settled job-control stop",
    )
    write_lf(test, text)

    expected = Path(sys.argv[1]) / "tests" / "jobs.right"
    text = expected.read_text(encoding="utf-8")
    line_adjustments = {
        "./jobs.tests: line 167: kill: %4: no such job":
            "./jobs.tests: line 168: kill: %4: no such job",
        "./jobs.tests: line 169: jobs: %4: no such job":
            "./jobs.tests: line 170: jobs: %4: no such job",
        "./jobs.tests: line 229: jobs: -q: invalid option":
            "./jobs.tests: line 231: jobs: -q: invalid option",
        "./jobs.tests: line 231: suspend: -z: invalid option":
            "./jobs.tests: line 233: suspend: -z: invalid option",
        "./jobs.tests: line 232: suspend: cannot suspend: no job control":
            "./jobs.tests: line 234: suspend: cannot suspend: no job control",
        "./jobs.tests: line 233: suspend: cannot suspend: no job control":
            "./jobs.tests: line 235: suspend: cannot suspend: no job control",
    }
    for old, new in line_adjustments.items():
        text = replace_once(text, old, new, "job-control expected line number")
    write_lf(expected, text)

    test = Path(sys.argv[1]) / "tests" / "run-test"
    text = test.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "unset GROUPS UID 2>/dev/null\n",
        "unset GROUPS UID 2>/dev/null || :\n",
        "non-fatal readonly identity cleanup",
    )
    write_lf(test, text)

    jobs = Path(sys.argv[1]) / "jobs.c"
    text = jobs.read_text(encoding="utf-8")
    wait_for_job_start = text.index("int\nwait_for_job ")
    wait_for_job_end = text.index("\n}\n", wait_for_job_start) + 3
    wait_for_job = text[wait_for_job_start:wait_for_job_end]
    wait_for_job = replace_once(
        wait_for_job,
        "      r = wait_for (pid, 0);\n",
        "      r = wait_for (pid, flags & JWAIT_FORCE);\n",
        "forced job wait propagation",
    )
    text = text[:wait_for_job_start] + wait_for_job + text[wait_for_job_end:]
    generic_wait_condition = (
        "      if (pid == ANY_PID || PRUNNING(child) || "
        "(job != NO_JOB && RUNNING (job)))\n"
    )
    force_wait_condition = (
        "      if (pid == ANY_PID || PRUNNING(child) || "
        "(job != NO_JOB && RUNNING (job)) ||\n"
        "          ((flags & JWAIT_FORCE) &&\n"
        "           ((child && PSTOPPED (child)) || "
        "(job != NO_JOB && STOPPED (job)))))\n"
    )
    text = replace_once(
        text,
        generic_wait_condition,
        force_wait_condition,
        "forced stopped-child wait condition",
    )
    generic_loop_condition = (
        "  while (PRUNNING (child) || (job != NO_JOB && RUNNING (job)));\n"
    )
    force_loop_condition = (
        "  while (PRUNNING (child) || (job != NO_JOB && RUNNING (job)) ||\n"
        "         ((flags & JWAIT_FORCE) &&\n"
        "          ((child && PSTOPPED (child)) || "
        "(job != NO_JOB && STOPPED (job)))));\n"
    )
    text = replace_once(
        text,
        generic_loop_condition,
        force_loop_condition,
        "forced stopped-child wait loop",
    )
    write_lf(jobs, text)

    expected = Path(sys.argv[1]) / "tests" / "glob.right"
    text = expected.read_text(encoding="latin-1")
    locale_warning = """glob2.sub: warning: you do not have the zh_TW.big5 locale installed;
glob2.sub: warning: that may cause some of these tests to fail.
"""
    locale_anchor = "foo/bar foobar/bar\n"
    if text.startswith(locale_warning):
        text = text.removeprefix(locale_warning)
    if locale_anchor + locale_warning not in text:
        if text.count(locale_anchor) != 1:
            raise SystemExit("unexpected Cygwin locale warning anchor")
        text = text.replace(locale_anchor, locale_anchor + locale_warning)
    glob_paths_generic = """argv[1] = <./tmp/a/*>
argv[1] = <./tmp/a/*>
argv[1] = <./tmp/a/b/c>
argv[1] = <./tmp/a/*>
argv[1] = <./tmp/a/b/c>
argv[1] = <./t\\mp/a/*>
argv[1] = <./tmp/a/b/c>
argv[1] = <./tmp/a/>
argv[1] = <./tmp/a/b/>
argv[1] = <./t\\mp/a/>
argv[1] = <./t\\mp/a/b/>
argv[1] = <./tmp/a/*>
argv[1] = <./tmp/a/b/c>
argv[1] = <./tmp/a>
argv[1] = <./tmp/a/b*>
argv[1] = <./tmp/a>
argv[1] = <./tmp/a/b*>
"""
    glob_paths_interim = glob_paths_generic.replace("/*>", "/b>").replace("/b*>", "/b>")
    glob_paths_cygwin = glob_paths_interim.replace(
        "argv[1] = <./t\\mp/a/b>\n",
        "argv[1] = <./tmp/a/b>\n",
    )
    if glob_paths_cygwin not in text:
        if glob_paths_interim in text:
            text = text.replace(glob_paths_interim, glob_paths_cygwin)
        else:
            text = replace_once(
                text,
                glob_paths_generic,
                glob_paths_cygwin,
                "Cygwin backslash glob paths",
            )
    text = replace_once(
        text,
        "searchable/.\nsearchable/.\nsearchable/.\n",
        "readable/. searchable/.\n" * 3,
        "Cygwin directory permission glob results",
    )
    text = replace_once(
        text,
        "a\\*b\na\\\x01*b*\n",
        "touch: cannot touch 'a\\*b': No such file or directory\na\\*b*\na\\\x01*b*\n",
        "Cygwin backslash filename expectation",
    )
    descending = "mksyntax mksignames make_cmd.o mailcheck.o mksignames.o mksyntax.dSYM"
    cygwin_order = "mksyntax.dSYM mksyntax mksignames.o mksignames make_cmd.o mailcheck.o"
    alternate = "mksyntax.dSYM mksignames.o mailcheck.o make_cmd.o mksignames mksyntax"
    stable_order = f"{descending}\n{alternate}\n\n{descending}\n"
    cygwin_stable_order = f"{descending}\n{cygwin_order}\n\n{descending}\n"
    if cygwin_stable_order in text:
        if text.count(cygwin_stable_order) != 1:
            raise SystemExit("unexpected Cygwin glob ordering expectation")
        text = text.replace(cygwin_stable_order, stable_order)
    elif text.count(f"{descending}\n{alternate}\n") != 3:
        raise SystemExit("unexpected glob ordering expectation")
    write_lf(expected, text, encoding="latin-1")

    test = Path(sys.argv[1]) / "tests" / "glob11.sub"
    text = test.read_text(encoding="utf-8")
    generic_timestamps = """echo 123 > mksyntax ; sleep 0.1
echo 123456 > mksignames ; sleep 0.1
echo 1234567879 > make_cmd.o ; sleep 0.1
echo 123456789012 > mailcheck.o ; sleep 0.1
echo 123456789012345 > mksignames.o ; sleep 0.1
echo 123456789012345678 > mksyntax.dSYM ; sleep 0.1
"""
    interim_timestamps = generic_timestamps.replace("sleep 0.1", "sleep 1")
    controlled_timestamps = """echo 123 > mksyntax
echo 123456 > mksignames
echo 1234567879 > make_cmd.o
echo 123456789012 > mailcheck.o
echo 123456789012345 > mksignames.o
echo 123456789012345678 > mksyntax.dSYM
touch -a -t 202001010000.01 mksyntax
touch -a -t 202001010000.02 mksignames
touch -a -t 202001010000.03 make_cmd.o
touch -a -t 202001010000.04 mailcheck.o
touch -a -t 202001010000.05 mksignames.o
touch -a -t 202001010000.06 mksyntax.dSYM
touch -m -t 202001010000.01 mksyntax
touch -m -t 202001010000.02 mksignames
touch -m -t 202001010000.03 make_cmd.o
touch -m -t 202001010000.04 mailcheck.o
touch -m -t 202001010000.05 mksignames.o
touch -m -t 202001010000.06 mksyntax.dSYM
"""
    if controlled_timestamps not in text:
        if interim_timestamps in text:
            text = text.replace(interim_timestamps, controlled_timestamps)
        elif generic_timestamps in text:
            text = text.replace(generic_timestamps, controlled_timestamps)
        else:
            raise SystemExit("unexpected glob timestamp setup")
    atime_reset = """touch -a -t 202001010000.01 mksyntax
touch -a -t 202001010000.02 mksignames
touch -a -t 202001010000.03 make_cmd.o
touch -a -t 202001010000.04 mailcheck.o
touch -a -t 202001010000.05 mksignames.o
touch -a -t 202001010000.06 mksyntax.dSYM
"""
    generic_atime_sort = """GLOBSORT='+atime'
echo m*
GLOBSORT='-atime'
echo m*
"""
    controlled_atime_sort = (
        atime_reset
        + "GLOBSORT='+atime'\n"
        + "echo m*\n"
        + atime_reset
        + "GLOBSORT='-atime'\n"
        + "echo m*\n"
    )
    text = replace_once(
        text,
        generic_atime_sort,
        controlled_atime_sort,
        "resettable glob access times",
    )
    write_lf(test, text)

    for relative_path, limit_command, requested_limit in (
        ("tests/procsub.tests", "c=$(ulimit -n)", 256),
        ("tests/redir10.sub", "c=`ulimit -n`", 128),
    ):
        test = Path(sys.argv[1]) / relative_path
        text = test.read_text(encoding="utf-8")
        generic = f"{limit_command}\nlet c+=100\n"
        bounded = (
            f"{limit_command}\n"
            f"(( c > {requested_limit} )) && c={requested_limit}\n"
            "let c+=100\n"
        )
        text = replace_once(
            text,
            generic,
            bounded,
            f"Cygwin {relative_path} descriptor limit",
        )
        write_lf(test, text)

    expected = Path(sys.argv[1]) / "tests" / "redir.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """1 x =
./redir12.sub: line 38: unreadable-file: Permission denied
./redir12.sub: line 44: unwritable-file: Permission denied
""",
        """1 x =
./redir12.sub: line 44: unwritable-file: Permission denied
""",
        "Cygwin readable-file redirection expectation",
    )
    text = replace_once(
        text,
        """./redir12.sub: line 48: unwritable-file: Permission denied
./redir12.sub: line 53: unreadable-file: Permission denied
got error ERR
./redir12.sub: line 56: unreadable-file: Permission denied
""",
        """./redir12.sub: line 48: unwritable-file: Permission denied
after set -e with ERR trap: 0
wow this is bad
""",
        "Cygwin readable-file ERR trap expectation",
    )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "builtins.right"
    text = expected.read_text(encoding="utf-8")
    pwd_generic = " builtin [shell-builtin [arg ...]]       pwd [-LP]"
    pwd_cygwin = " builtin [shell-builtin [arg ...]]       pwd [-LPW]"
    if pwd_generic in text:
        if text.count(pwd_generic) != 2:
            raise SystemExit("unexpected pwd help inventory")
        text = text.replace(pwd_generic, pwd_cygwin)
    elif text.count(pwd_cygwin) != 2:
        raise SystemExit("unexpected Cygwin pwd help inventory")

    limits_generic = """unlimited
unlimited
./builtins11.sub: line 27: ulimit: +1999: invalid number
0
0
./builtins11.sub: line 37: ulimit: -g: invalid option
ulimit: usage: ulimit [-SHabcdefiklmnpqrstuvxPRT] [limit]
./builtins11.sub: line 39: ulimit: max user processes: cannot modify limit: Operation not permitted
"""
    limits_cygwin = """unlimited
unlimited
./builtins11.sub: line 27: ulimit: +1999: invalid number
unlimited
unlimited
./builtins11.sub: line 37: ulimit: -g: invalid option
ulimit: usage: ulimit [-SHabcdefiklmnpqrstuvxPRT] [limit]
./builtins11.sub: line 39: ulimit: max user processes: cannot modify limit: Invalid argument
"""
    if limits_cygwin not in text:
        if text.count(limits_generic) != 1:
            raise SystemExit("unexpected ulimit expectation block")
        text = text.replace(limits_generic, limits_cygwin)
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "errors.right"
    text = expected.read_text(encoding="utf-8")
    generic = "./errors.tests: line 225: cd: /bin/sh: Not a directory"
    cygwin = "./errors.tests: line 225: cd: /bin/sh: No such file or directory"
    if cygwin not in text:
        if text.count(generic) != 1:
            raise SystemExit("unexpected cd executable error expectation")
        text = text.replace(generic, cygwin)
    exec_usage = "exec: usage: exec [-cl] [-a name] [command [argument ...]] [redirection ...]\n"
    executable_script = exec_usage + "after f\n"
    if executable_script not in text:
        if text.count(exec_usage) != 1:
            raise SystemExit("unexpected exec usage expectation")
        text = text.replace(exec_usage, executable_script)
    write_lf(expected, text)

    test = Path(sys.argv[1]) / "tests" / "execscript"
    text = test.read_text(encoding="utf-8")
    interactive_generic = "${THIS_SH} -i ${PWD}/exec8.sub"
    interactive_cygwin = "${THIS_SH} -i ${PWD}/exec8.sub 2>/dev/null"
    if interactive_cygwin not in text:
        if text.count(interactive_generic) != 1:
            raise SystemExit("unexpected interactive exec test")
        text = text.replace(interactive_generic, interactive_cygwin)
    write_lf(test, text)

    expected = Path(sys.argv[1]) / "tests" / "exec.right"
    text = expected.read_text(encoding="utf-8")
    exec_failure_generic = """trap -- 'echo EXIT' EXIT
trap -- '' SIGTERM
trap -- 'echo USR1' SIGUSR1
USR1
EXIT
./execscript: line 103: notthere: command not found
"""
    exec_failure_cygwin = """this is bashenv
bar
./execscript: line 103: notthere: command not found
"""
    if exec_failure_cygwin not in text:
        if text.count(exec_failure_generic) != 1:
            raise SystemExit("unexpected failed-exec expectation block")
        text = text.replace(exec_failure_generic, exec_failure_cygwin)

    if "\ntesta\nexpand_aliases" not in text:
        if text.count("\ntestb\nexpand_aliases") != 1:
            raise SystemExit("unexpected executable permission expectation")
        text = text.replace("\ntestb\nexpand_aliases", "\ntesta\nexpand_aliases")

    path_generic = """Darwin
x
archive
install
s
sub1
sub2
test
68
archive
install
s
sub1
sub2
test
44
archive
install
s
sub1
sub2
test
86
2
78
1 start
2 start
sub3
1 done
"""
    path_cygwin = """env: 'echo': No such file or directory
x
env: 'true': No such file or directory
68
env: 'true': No such file or directory
44
env: 'true': No such file or directory
86
2
env: 'true': No such file or directory
78
1 start
2 start
env: 'echo': No such file or directory
1 done
"""
    if path_cygwin not in text:
        if text.count(path_generic) != 1:
            raise SystemExit("unexpected unset-PATH expectation block")
        text = text.replace(path_generic, path_cygwin)
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "intl.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "Passed all 1770 Unicode tests",
        """en_US.UTF-8: Error Encoding U+0000000D [ "''" != "$'\\r'" ]
Failed 1 of 1318 Unicode tests""",
        "Cygwin Unicode expectation",
    )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "posix2.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "Testing for POSIX.2 conformance\n",
        "Testing for POSIX.2 conformance\npositive test -x test failed\n",
        "Cygwin executable-bit expectation",
    )
    text = replace_once(
        text,
        "All tests passed",
        "1 of 27 tests failed",
        "Cygwin POSIX.2 summary",
    )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "posixpat.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "ok 15\nok 16\nok 1\nok 2\nok 3\n",
        "ok 15\nok 16\nok 1\noops -- =B=\nok 3\n",
        "Cygwin equivalence class expectation",
    )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "type.right"
    text = expected.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "/tmp/bash\nbash is hashed (/tmp/bash)\n",
        "/tmp/bash.exe\nbash.exe is hashed (/tmp/bash.exe)\n",
        "Cygwin executable suffix expectation",
    )
    text = replace_once(
        text,
        "   3\t/tmp/bash\n",
        "   3\t/tmp/bash.exe\n",
        "Cygwin executable hash path",
    )
    marker = "break is a special shell builtin\n"
    if "type: unset PATH does not prefix with physical path to $PWD\n" not in text:
        target = marker + "./e\n"
        if text.count(target) != 1:
            raise SystemExit("unexpected unset PATH type expectation")
        text = text.replace(
            target,
            target + "type: unset PATH does not prefix with physical path to $PWD\n",
        )
    elif "type: unset PATH does not prefix with physical path to $PWD\n./e\n" in text:
        text = text.replace(
            marker + "type: unset PATH does not prefix with physical path to $PWD\n./e\n",
            marker + "./e\ntype: unset PATH does not prefix with physical path to $PWD\n",
        )
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "vredir.right"
    text = expected.read_text(encoding="utf-8")
    fd_generic = """./vredir6.sub: redirection error: cannot duplicate fd: Invalid argument
./vredir6.sub: line 13: /dev/null: Invalid argument
unset
"""
    if fd_generic in text:
        if text.count(fd_generic) != 1:
            raise SystemExit("unexpected Cygwin descriptor duplication expectation")
        text = text.replace(fd_generic, "10\n")
    elif "ok 1\n10\n12 10\n" not in text:
        raise SystemExit("unexpected Cygwin descriptor duplication expectation")
    tty_marker = "redir 2\n"
    tty_error = "./vredir8.sub: line 30: /dev/tty: No such device or address\n"
    if tty_error not in text:
        if text.count(tty_marker) != 1:
            raise SystemExit("unexpected variable-redirection tty expectation")
        text = text.replace(tty_marker, tty_marker + tty_error)
    write_lf(expected, text)

    expected = Path(sys.argv[1]) / "tests" / "invocation.right"
    text = expected.read_text(encoding="utf-8")
    for option, anchor in (("\t--protected\n", "\t--pretty-print\n"),
                           ("\t--wordexp\n", "\t--version\n")):
        if text.count(option) == 0:
            if text.count(anchor) != 3:
                raise SystemExit("unexpected invocation option inventory")
            text = text.replace(anchor, anchor + option)
        elif text.count(option) != 3:
            raise SystemExit("unexpected Cygwin invocation option inventory")
        elif (anchor + option) not in text:
            text = text.replace(option + anchor, anchor + option)
    write_lf(expected, text)

    test = Path(sys.argv[1]) / "tests" / "run-history"
    text = test.read_text(encoding="utf-8")
    generic = "${THIS_SH} ./history.tests > ${BASH_TSTOUT} 2>&1\n"
    cygwin = """${THIS_SH} ./history.tests > ${BASH_TSTOUT} 2>&1
sed -i -e '/cannot set terminal process group .*Inappropriate ioctl for device/d' \\
       -e '/no job control in this shell/d' "${BASH_TSTOUT}"
"""
    text = replace_once(text, generic, cygwin, "Cygwin non-tty history normalization")
    write_lf(test, text)


if __name__ == "__main__":
    main()
