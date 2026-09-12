#!/usr/bin/env python3
"""Derive an explicit MSYS application profile from the actual Cygwin driver."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--profile-mode", choices=("overlay", "default"), default="overlay")
    args = parser.parse_args()
    if args.profile_mode == "default" and args.output.name != "specs":
        parser.error("The default profile must use GCC's automatically loaded 'specs' filename")
    target = subprocess.check_output(
        [str(args.compiler), "-dumpmachine"], text=True
    ).strip()
    if target != "aarch64-pc-cygwin":
        parser.error(f"Unexpected compiler target: {target!r}")
    original = subprocess.check_output(
        [str(args.compiler), "-dumpspecs"], text=True
    )
    if not original.strip():
        parser.error("The compiler returned empty specs")
    specs = original
    replacements = {
        "lib": [("-lcygwin", "-lmsys-2.0", 1)],
        "link": [
            ("_cygwin_dll_entry", "_msys_dll_entry", 2),
            ("--dll-search-prefix=cyg", "--dll-search-prefix=msys-", 1),
        ],
    }
    for section in ("self_spec", "lib", "link"):
        pattern = rf"(?m)^(\*{section}:\n)([^\n]*)$"
        matches = list(re.finditer(pattern, specs))
        if len(matches) != 1:
            parser.error(f"Expected exactly one {section} spec")
        match = matches[0]
        body = match[2]
        for old, new, count in replacements.get(section, []):
            if body.count(old) != count:
                parser.error(f"Unexpected {section} spec: {old!r} count changed")
            body = body.replace(old, new)
        if section == "self_spec":
            body += " -D__MSYS__"
        specs = specs[:match.start(2)] + body + specs[match.end(2):]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(specs, encoding="utf-8", newline="\n")
    evidence = {
        "schemaVersion": 1,
        "target": target,
        "compiler": str(args.compiler),
        "compilerSha256": digest(args.compiler),
        "originalSpecsSha256": hashlib.sha256(original.encode()).hexdigest(),
        "specs": str(args.output),
        "specsSha256": digest(args.output),
        "scope": ("MSYS application profile; raw Cygwin compiler unchanged"
                  if args.profile_mode == "overlay"
                  else "Default MSYS application profile for the separately staged native compiler"),
        "profileMode": args.profile_mode,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
