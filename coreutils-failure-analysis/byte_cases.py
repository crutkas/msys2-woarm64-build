"""Exact retained date/join/seq failing arguments, plus explicit byte-conversion controls."""

from inventory import ROOT, write
from replay import run


COMMAND = r"""
printf '== date original single byte B0 ==\n'
b=$(printf '\260'); date -d "$b" >date.out 2>date.err; printf 'date_exit=%s\n' "$?"; cat date.err
printf '== date foreign-boundary PUA representation ==\n'
b=$(printf '\357\202\260'); date -d "$b" >pua.out 2>pua.err; printf 'date_exit=%s\n' "$?"; cat pua.err
printf '== join exact original A7 separator ==\n'
b=$(printf '\247')
printf 'a\2471\nb\2471\n' >left
printf 'a\2472\247\nb\2472\247\n' >right
join -t "$b" left right >joined; printf 'join_exit=%s\n' "$?"; od -An -tx1 joined
printf '== join PUA-encoded separator ==\n'
b=$(printf '\357\202\247')
join -t "$b" left right; printf 'join_exit=%s\n' "$?"
printf '== seq negative zero ==\n'
seq 0 -0 0 >seq.out 2>seq.err; printf 'seq_exit=%s\n' "$?"; cat seq.err
"""


def main():
    results = []
    for cohort in ("current-noacl", "historical-noacl"):
        label = "exact-byte-subcases-" + cohort
        result = run(cohort, label, command=COMMAND, timeout=45)
        results.append({"cohort": cohort, "result": str(ROOT / "runs" / label / "result.json"),
                        "shell_raw": result["semantic_test_shell_raw_exit"]})
    write(ROOT / "byte-subcases.json", results)


if __name__ == "__main__":
    main()
