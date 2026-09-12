"""Discriminating native reproductions of specific retained failing subcases."""

import json
from pathlib import Path

from inventory import ROOT, write
from replay import run


CASES = {
    "diagnostic-argv0": r"""
printf '== PATH lookup ==\n'
cut -b0 </dev/null 2>bare.err; printf 'exit=%s\n' "$?"; cat bare.err
printf '== explicit pathname ==\n'
/usr/bin/cut -b0 </dev/null 2>absolute.err; printf 'exit=%s\n' "$?"; cat absolute.err
""",
    "quoted-args": r"""
printf x > file1; printf y > file2
printf '== quoted multiply ==\n'; expr 2 '*' 3; printf 'exit=%s\n' "$?"
printf '== csplit empty regexp ==\n'; printf 'a\nb\n' > input
csplit input //; printf 'exit=%s\n' "$?"
printf '== literal slash argument ==\n'; printf '%s\n' //
""",
    "proc-byte-domain": r"""
printf '== same-runtime proc length ==\n'
cp /proc/version version.copy
wc -c version.copy
wc -c </proc/version; printf 'stdin_exit=%s\n' "$?"
n=$(wc -c <version.copy)
printf e > e
od -An -c -j "$n" /proc/version e; printf 'od_exit=%s\n' "$?"
printf '== simulated parent length 24 bytes shorter ==\n'
od -An -c -j "$((n-24))" /proc/version e; printf 'od_exit=%s\n' "$?"
printf '== null files0 list ==\n'
wc --files0-from=/dev/null; printf 'null_exit=%s\n' "$?"
""",
    "literal-high-byte-separator": r"""
d=$(printf '\200')
printf 'a\200x\n' > left
printf 'a\200y\n' > right
join -t "$d" left right > actual; r=$?
printf 'exit=%s\n' "$r"; od -An -tx1 actual
""",
    "readlink-sys-representation": r"""
mkdir d; printf data > d/file
ln -s d/file link; printf 'ln_file=%s\n' "$?"
readlink link; printf 'readlink=%s\n' "$?"
test -L link; printf 'test_symlink=%s\n' "$?"
rm link; printf 'remove_symlink=%s\n' "$?"
test -f d/file; printf 'target_retained=%s\n' "$?"
ln -s nowhere dangling; printf 'ln_dangling=%s\n' "$?"
rm -fv dangling; printf 'remove_dangling=%s\n' "$?"
ln -s . self; printf 'ln_dot=%s\n' "$?"
readlink self; printf 'readlink_dot=%s\n' "$?"
""",
    "xargs-env-budget": r"""
printf x | xargs echo; printf 'small_exit=%s\n' "$?"
filler=$(printf '%40000s' x); export filler
printf x | xargs echo; printf 'large_exit=%s\n' "$?"
""",
    "stdbuf-layout": r"""
stdbuf -oL true; printf 'stdbuf_exit=%s\n' "$?"
""",
    "mktemp-mode": r"""
umask 022
f=$(mktemp local.XXXXXX); r=$?
printf 'mktemp_exit=%s\n' "$r"; stat -c 'mode=%a' "$f"
""",
}


def main():
    results = []
    for name, command in CASES.items():
        for cohort in ("current-noacl", "historical-noacl"):
            if cohort == "historical-noacl" and name not in ("diagnostic-argv0", "quoted-args", "proc-byte-domain"):
                continue
            label = f"focused-{name}-{cohort}"
            result = run(cohort, label, command=command, timeout=35)
            results.append({"name": name, "cohort": cohort, "label": label,
                            "result": str(ROOT / "runs" / label / "result.json"),
                            "log": str(ROOT / "runs" / label / "target.log"),
                            "shell_raw": result["semantic_test_shell_raw_exit"]})
    result = run("current-acl", "focused-mktemp-mode-current-acl", command=CASES["mktemp-mode"], timeout=35)
    results.append({"name": "mktemp-mode", "cohort": "current-acl",
                    "result": str(ROOT / "runs/focused-mktemp-mode-current-acl/result.json"),
                    "shell_raw": result["semantic_test_shell_raw_exit"]})
    write(ROOT / "focused-replays.json", results)


if __name__ == "__main__":
    main()
