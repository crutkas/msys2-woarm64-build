"""Complete the Tcl development payload using its real installed libraries and headers."""

import argparse
import json
from pathlib import Path
import re
import shutil

from sources import ContractError, digest, inventory, verify_tree


def finalize_tcl(source: Path, stage: Path):
    shutil.copyfile(stage / "bin/tclsh86.exe", stage / "bin/tclsh.exe")
    private_headers = stage / "include/tcl8.6/tcl-private"
    for folder in ("generic", "win"):
        for path in (source / folder).rglob("*.h"):
            destination = private_headers / folder / path.relative_to(source / folder)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    relocate_tcl_metadata(stage)
    licenses = stage / "share/licenses/tcl"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "license.terms", licenses / "license.terms")


def relocate_tcl_metadata(stage: Path):
    config = stage / "lib/tclConfig.sh"
    private_headers = stage / "include/tcl8.6/tcl-private"
    replacements = {
        "TCL_PREFIX": stage.as_posix(),
        "TCL_EXEC_PREFIX": stage.as_posix(),
        "TCL_PACKAGE_PATH": f"{stage.as_posix()}/lib",
        "TCL_BUILD_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltcl86",
        "TCL_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltcl86",
        "TCL_SRC_DIR": private_headers.as_posix(),
        "TCL_INCLUDE_SPEC": f"-I{stage.as_posix()}/include",
        "TCL_BUILD_STUB_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltclstub86",
        "TCL_STUB_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltclstub86",
        "TCL_STUB_LIB_PATH": f"{stage.as_posix()}/lib/libtclstub86.a",
        "TCL_BUILD_STUB_LIB_PATH": f"{stage.as_posix()}/lib/libtclstub86.a",
    }
    content = config.read_text()
    for name, value in replacements.items():
        content, count = re.subn(rf"(?m)^{name}='[^']*'$", f"{name}='{value}'", content)
        if count != 1:
            raise ContractError(f"Unexpected installed Tcl development metadata: {name}")
    config.write_text(content, newline="\n")
    pc = stage / "lib/pkgconfig/tcl.pc"
    content = pc.read_text()
    for name, value in (("prefix", "${pcfiledir}/../.."), ("exec_prefix", "${prefix}"),
                        ("libdir", "${exec_prefix}/lib")):
        content, count = re.subn(rf"(?m)^{name}=.*$", f"{name}={value}", content)
        if count != 1:
            raise ContractError(f"Unexpected Tcl pkg-config metadata: {name}")
    pc.write_text(content, newline="\n")


def finalize_tk(source: Path, stage: Path):
    private_headers = stage / "include/tk8.6/tk-private"
    for folder in ("generic", "win"):
        headers = sorted((source / folder).rglob("*.h"))
        if not headers:
            raise ContractError(f"Missing real Tk private headers: {folder}")
        for path in headers:
            destination = private_headers / folder / path.relative_to(source / folder)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    relocate_tk_metadata(stage)


def relocate_tk_metadata(stage: Path):
    config = stage / "lib/tkConfig.sh"
    replacements = {
        "TK_PREFIX": stage.as_posix(),
        "TK_EXEC_PREFIX": stage.as_posix(),
        "TK_BUILD_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltk86",
        "TK_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltk86",
        "TK_SRC_DIR": (stage / "include/tk8.6/tk-private").as_posix(),
        "TK_BUILD_STUB_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltkstub86",
        "TK_STUB_LIB_SPEC": f"-L{stage.as_posix()}/lib -ltkstub86",
        "TK_BUILD_STUB_LIB_PATH": f"{stage.as_posix()}/lib/libtkstub86.a",
        "TK_STUB_LIB_PATH": f"{stage.as_posix()}/lib/libtkstub86.a",
    }
    content = config.read_text()
    for name, value in replacements.items():
        content, count = re.subn(rf"(?m)^{name}='[^']*'$", f"{name}='{value}'", content)
        if count != 1:
            raise ContractError(f"Unexpected installed Tk development metadata: {name}")
    config.write_text(content, newline="\n")
    pc = stage / "lib/pkgconfig/tk.pc"
    content = pc.read_text()
    for name, value in (("prefix", "${pcfiledir}/../.."), ("exec_prefix", "${prefix}"),
                        ("libdir", "${exec_prefix}/lib")):
        content, count = re.subn(rf"(?m)^{name}=.*$", f"{name}={value}", content)
        if count != 1:
            raise ContractError(f"Unexpected Tk pkg-config metadata: {name}")
    pc.write_text(content, newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "manifest", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Tcl metadata restaging requires fresh output")
    verify_tree(args.input, args.manifest)
    original = inventory(args.input)
    stage = args.output / "stage"
    shutil.copytree(args.input, stage)
    if inventory(stage) != original:
        raise ContractError("Tcl stage copy differs")
    relocate_tcl_metadata(stage)
    files = inventory(stage)
    changed = sorted(name for name in files.keys() | original.keys() if files.get(name) != original.get(name))
    if changed != ["lib/pkgconfig/tcl.pc", "lib/tclConfig.sh"]:
        raise ContractError(f"Unexpected Tcl restaging changes: {changed}")
    verify_tree(args.input, args.manifest)
    report = {"schema": 1, "status": "native-tcl-development-metadata-restaged",
              "input_stage": str(args.input), "input_receipt_sha256": digest(args.manifest),
              "recipe_sha256": digest(__file__), "changed_files": changed, "files": files,
              "pending": ["Relocated native interpreter and loaded-module closure", "Complete Tcl suite"]}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Restaged {len(files)} files; executable and library bytes unchanged")


if __name__ == "__main__":
    main()
