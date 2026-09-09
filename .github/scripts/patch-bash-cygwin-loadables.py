"""Align Bash's Cygwin build metadata and expected option inventory."""

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


def write_lf(path: Path, text: str) -> None:
    with path.open("w", newline="\n") as stream:
        stream.write(text)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    path = Path(sys.argv[1]) / "support" / "shobj-conf"
    text = path.read_text()
    if NEW not in text:
        if text.count(OLD) != 1:
            raise SystemExit("unexpected Cygwin shared-object configuration")
        text = text.replace(OLD, NEW)
    write_lf(path, text)

    expected = Path(sys.argv[1]) / "tests" / "complete.right"
    text = expected.read_text()
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


if __name__ == "__main__":
    main()
