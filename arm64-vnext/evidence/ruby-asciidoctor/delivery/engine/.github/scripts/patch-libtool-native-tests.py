"""Instrument pinned libtool native test calls without changing expected results."""

import hashlib
import os
from pathlib import Path
import sys


PINS = {
    "testsuite.at": "0ce48f86f2472e9370496908f599f242f1af67b27d047e51603476ff2ac30ccd",
    "demo.at": "bb3d474eb46131b4a70c8b299a10f780b3ef74f46e9f9b73f8eebe14af08a32d",
    "depdemo.at": "8dbeb40ff1db995c28f5bcd04d16326cfc56c9a159f1ab4ae29e142c513e4898",
}

HELPER = r'''
lt_at_native_exec ()
{
  lt_at_native_file=[$]1
  shift
  if test -f "$lt_at_native_file$EXEEXT"; then
    lt_at_native_file=$lt_at_native_file$EXEEXT
  fi
  if test -n "$WOARM64_NATIVE_EXEC"; then
    "$CONFIG_SHELL" "$WOARM64_NATIVE_EXEC" "$lt_at_native_file" "[$]@"
  else
    "$lt_at_native_file" "[$]@"
  fi
}
'''


def replace_exact(text, old, new, count):
    if text.count(old) != count:
        raise ValueError(f"Pinned native test anchor count changed: {old!r}")
    return text.replace(old, new)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Pass the copied libtool source directory")
    root = Path(sys.argv[1]).resolve(strict=True)
    output = Path(os.environ["WOARM64_OUTPUT_ROOT"]).resolve(strict=True)
    if not root.is_relative_to(output / "build"):
        raise SystemExit("Only the fresh invocation's extracted source may be instrumented")
    texts = {}
    for name, expected in PINS.items():
        data = (root / "tests" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit(f"Pinned libtool test source changed: {name}")
        texts[name] = data.decode("utf-8")
    anchor = '. "$abs_top_srcdir/build-aux/extract-trace"\n'
    texts["testsuite.at"] = replace_exact(texts["testsuite.at"], anchor, anchor + HELPER, 1)
    texts["testsuite.at"] = replace_exact(
        texts["testsuite.at"], 'AT_CHECK([if "$lt_exe" $5; then',
        'AT_CHECK([if lt_at_native_exec "$lt_exe" $5; then', 1)
    texts["demo.at"] = replace_exact(texts["demo.at"], "./hell$EXEEXT", "lt_at_native_exec ./hell$EXEEXT", 2)
    texts["demo.at"] = replace_exact(texts["demo.at"], "LT_AT_CHECK([./hell", "LT_AT_CHECK([lt_at_native_exec ./hell", 2)
    texts["depdemo.at"] = replace_exact(texts["depdemo.at"], "./depdemo$EXEEXT", "lt_at_native_exec ./depdemo$EXEEXT", 4)
    texts["depdemo.at"] = replace_exact(texts["depdemo.at"], "LT_AT_CHECK([./depdemo", "LT_AT_CHECK([lt_at_native_exec ./depdemo", 1)
    for name, text in texts.items():
        (root / "tests" / name).write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    main()
