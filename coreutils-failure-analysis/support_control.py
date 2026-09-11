"""Correct the real stdbuf support-file layout only in another owned native root."""

import json
from pathlib import Path

from inventory import ROOT, PRODUCER, copy, digest, write
from replay import run


def main():
    inputs = json.loads((ROOT / "replay-inputs.json").read_text())
    source_root = ROOT / "current-noacl"
    target = ROOT / "current-complete"
    target.mkdir(exist_ok=False)
    copies = []
    for row in inputs["copies"]:
        source = Path(row["copy"])
        if source.is_relative_to(source_root):
            copy(source, target / source.relative_to(source_root), copies, row["copied"])
    (target / "etc").mkdir(exist_ok=True)
    (target / "home").mkdir(exist_ok=True)
    (target / "tmp").mkdir(exist_ok=True)
    support = PRODUCER / "stage/coreutils/usr/lib/coreutils/libstdbuf.dll"
    copy(support, target / "usr/lib/coreutils/libstdbuf.dll", copies)
    data = support.read_bytes()
    pe = int.from_bytes(data[60:64], "little")
    if (data[:2] != b"MZ" or int.from_bytes(data[pe + 4:pe + 6], "little") != 0xAA64
            or not int.from_bytes(data[pe + 22:pe + 24], "little") & 0x2000):
        raise RuntimeError("Actual stdbuf support artifact is not a native ARM64 DLL")
    write(ROOT / "support-layout-inputs.json", {"copies": copies, "support_sha256": digest(support),
          "scope": "Original native DLL in its configured installed location; no stub, interposer, binary patch or old-tree mutation"})
    run("current-complete", "focused-stdbuf-canonical-layout-01", command="stdbuf -oL true; printf 'stdbuf_exit=%s\\n' \"$?\"", timeout=35)
    run("current-complete", "upstream-help-version-complete-01", test="tests/misc/help-version.sh", timeout=180)


if __name__ == "__main__":
    main()
