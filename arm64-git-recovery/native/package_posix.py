"""Apply the explicit POSIX package installation tail to a private stage."""

import argparse
import json
import os
from pathlib import Path
import shutil

from sources import ContractError, digest


def terminfo_windows_paths(files):
    result, folded = {}, {}
    for name, sha in sorted(files.items()):
        parts = Path(name).parts
        if len(parts) != 2 or len(parts[0]) != 1 or not parts[1]:
            raise ContractError("Unexpected host terminfo tree shape")
        destination = f"{ord(parts[0]):02x}/{parts[1]}"
        existing = folded.get(destination.casefold())
        if existing:
            if result[existing]["sha256"] != sha:
                raise ContractError("Case-colliding terminal entries have different contents")
            result[existing]["aliases"].append(name)
        else:
            folded[destination.casefold()] = destination
            result[destination] = {"source": name, "sha256": sha, "aliases": []}
    return result


def normalize_ncurses_terminfo(stage):
    root = stage / "usr/share/terminfo"
    files = {path.relative_to(root).as_posix(): digest(path) for path in root.rglob("*") if path.is_file()}
    if not files:
        raise ContractError("ncurses installation omitted terminfo")
    if all(len(Path(name).parts[0]) == 2 for name in files):
        return
    mapped = terminfo_windows_paths(files)
    evidence = stage.with_name(stage.name + ".host-terminfo")
    if evidence.exists():
        raise ContractError("Host terminfo preservation path already exists")
    root.rename(evidence)
    root.mkdir()
    for name, row in mapped.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(evidence / row["source"], destination)
        if digest(destination) != row["sha256"]:
            raise ContractError("Terminal database changed during Windows layout conversion")
    print(json.dumps({"operation": "host-terminfo-to-target-disable-mixed-case-layout",
                      "preserved_host_tree": str(evidence), "entries": len(mapped),
                      "byte_identical_case_aliases": sum(len(row["aliases"]) for row in mapped.values())}))
    evidence.with_name(evidence.name + ".json").write_text(json.dumps(mapped, indent=2) + "\n")


def install_data(source, destination):
    if not source.is_file() or source.stat().st_size == 0:
        raise ContractError(f"Missing package data: {source}")
    if destination.exists():
        if not destination.is_file() or digest(destination) != digest(source):
            raise ContractError(f"Conflicting package data: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def finish(package, source, stage, build=None):
    source, stage = Path(source), Path(stage)
    if package not in ("make", "bash", "coreutils", "sed", "grep", "gawk", "findutils", "ncurses", "nano") or not stage.is_dir():
        raise ContractError("Expected a supported package and existing private stage")
    if package == "coreutils":
        old = stage / "usr/lib/coreutils/libstdbuf.so.exe"
        new = stage / "usr/lib/coreutils/libstdbuf.dll"
        if old.is_file():
            if new.exists():
                raise ContractError("Conflicting stdbuf module destinations")
            old.rename(new)
        elif not new.is_file():
            raise ContractError("Missing coreutils stdbuf module")
        install_data(source / "src/dircolors.hin", stage / "etc/DIR_COLORS")
    if package == "sed":
        charset_alias = stage / "usr/lib/charset.alias"
        if charset_alias.exists():
            charset_alias.unlink()
    if package == "ncurses":
        normalize_ncurses_terminfo(stage)
        alias = stage / "usr/share/man/man3/WINDOW.3ncurses"
        primary = stage / "usr/share/man/man3/window.3ncurses"
        canonical = stage / "usr/share/man/man3/curses_variables.3ncurses"
        if alias.is_symlink() and primary.is_file():
            if alias.resolve() != canonical.resolve() or not canonical.is_file():
                raise ContractError("Unexpected colliding ncurses manual alias")
            print(json.dumps({"operation": "remove-case-colliding-manual-alias",
                              "path": alias.relative_to(stage).as_posix(),
                              "content_retained_at": canonical.relative_to(stage).as_posix(),
                              "sha256": digest(canonical)}))
            alias.unlink()
    if package == "gawk":
        executable = stage / "usr/bin/gawk.exe"
        alias = stage / "usr/bin/awk.exe"
        if alias.is_symlink():
            if alias.resolve() != executable.resolve():
                raise ContractError("Unexpected awk alias target")
            alias.unlink()
            shutil.copyfile(executable, alias)
        if not alias.is_file() or digest(alias) != digest(executable):
            raise ContractError("Expected byte-identical native awk alias")
        for path in (stage / "usr/lib/gawk").glob("*.dll.a"):
            path.unlink()
        bug_script = stage / "usr/bin/gawkbug"
        if bug_script.is_file():
            lines = bug_script.read_text().splitlines(keepends=True)
            bug_script.write_text("".join(line.replace("cygwin", "msys") if line.startswith(("MACHTYPE=", "OS="))
                                           else line for line in lines))
    if package == "nano":
        if build is None:
            raise ContractError("Nano requires its explicit configured build directory for sample.nanorc")
        install_data(Path(build) / "doc/sample.nanorc", stage / "etc/nanorc")
        alias = stage / "usr/bin/rnano"
        executable = stage / "usr/bin/nano.exe"
        if alias.is_symlink():
            if os.readlink(alias) not in ("nano", "nano.exe") or not executable.is_file():
                raise ContractError("Unexpected restricted-nano alias target")
            alias.unlink()
            install_data(executable, stage / "usr/bin/rnano.exe")
    install_data(source / "COPYING", stage / f"usr/share/licenses/{package}/COPYING")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=("make", "bash", "coreutils", "sed", "grep", "gawk", "findutils", "ncurses", "nano"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--build", type=Path)
    args = parser.parse_args()
    finish(args.package, args.source, args.stage, args.build)


if __name__ == "__main__":
    main()
