"""Exercise native gettext catalogs and the distinct envsubst text/variable-list modes."""

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess

from sources import ContractError, digest, inventory


def catalog(messages):
    pairs = sorted((key.encode("utf-8"), value.encode("utf-8")) for key, value in messages.items())
    count = len(pairs)
    original_offset = 28
    translated_offset = original_offset + count * 8
    strings_offset = translated_offset + count * 8
    originals, translations, strings = [], [], bytearray()
    for original, _ in pairs:
        originals.append((len(original), strings_offset + len(strings)))
        strings.extend(original + b"\0")
    for _, translated in pairs:
        translations.append((len(translated), strings_offset + len(strings)))
        strings.extend(translated + b"\0")
    return (struct.pack("<7I", 0x950412DE, 0, count, original_offset, translated_offset, 0, 0)
            + b"".join(struct.pack("<2I", *entry) for entry in originals + translations) + strings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A new private catalog fixture is required")
    before = inventory(args.stage)
    locale_dir = args.output / "locale tree"
    destination = locale_dir / "fr/LC_MESSAGES"
    destination.mkdir(parents=True)
    (destination / "native-fixture.mo").write_bytes(catalog({
        "": "Content-Type: text/plain; charset=UTF-8\nLanguage: fr\nPlural-Forms: nplurals=2; plural=(n != 1);\n",
        "hello": "bonjour-native",
        "one item\0many items": "un-article-native\0des-articles-native",
    }))
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    env.update({"PATH": str(args.stage / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "LC_ALL": "en_US.UTF-8", "LANGUAGE": "fr", "TEXTDOMAINDIR": str(locale_dir),
                "TEXTDOMAIN": "native-fixture", "NATIVE_FIXTURE_VALUE": "native-value"})
    cases = (
        ("catalog", "gettext.exe", ["-d", "native-fixture", "hello"], None, b"bonjour-native"),
        ("plural-one", "ngettext.exe", ["-d", "native-fixture", "one item", "many items", "1"], None, b"un-article-native"),
        ("plural-many", "ngettext.exe", ["-d", "native-fixture", "one item", "many items", "3"], None, b"des-articles-native"),
        ("envsubst-text", "envsubst.exe", [], b"$NATIVE_FIXTURE_VALUE\n", b"native-value\r\n"),
        ("envsubst-variable-list", "envsubst.exe", ["--variables", "$NATIVE_FIXTURE_VALUE"], None, b"NATIVE_FIXTURE_VALUE\n"),
    )
    records = []
    for name, program, options, data, expected in cases:
        command = [str(args.stage / "bin" / program), *options]
        result = subprocess.run(command, input=data, env=env, capture_output=True, timeout=15)
        (args.output / f"{name}.stdout").write_bytes(result.stdout)
        (args.output / f"{name}.stderr").write_bytes(result.stderr)
        records.append({"case": name, "exit": result.returncode,
                        "passed": result.returncode == 0 and result.stdout == expected and not result.stderr,
                        "stdout_hex": result.stdout.hex(), "expected_hex": expected.hex()})
    unchanged = inventory(args.stage) == before
    report = {"passed": unchanged and all(record["passed"] for record in records),
              "scope": "Real catalog/plural lookup, Windows text substitution, and patched LF-only variable listing",
              "catalog_sha256": digest(destination / "native-fixture.mo"), "stage_unchanged": unchanged, "cases": records}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native gettext behavior failed; raw results retained")
    print("Native gettext catalog/plurals and both envsubst output modes passed")


if __name__ == "__main__":
    main()
