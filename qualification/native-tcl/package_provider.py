"""Export a Tcl provider with explicit relocatable metadata and real relative tar links."""

import argparse
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import sys
import tarfile

from qualify import INPUT, ROOT, digest, import_tools, msys, require, require_memory, verify_inputs, write_json


RECIPE = Path(r"\\wsl.localhost\Ubuntu\root\arm64-vnext-20260905\git\sources\msys-upstream-recipes\tcl\PKGBUILD")
RECIPE_SHA = "0b35e383fa1b668f8d764ccac4758890b17c77fcc0a002638fb2baefec642189"
BOOTSTRAP = INPUT / "tcl-bootstrap-01/msys64/msys64"
BOOTSTRAP_RECEIPT = INPUT / "tcl-bootstrap-01/host-generators-01.json"
BOOTSTRAP_SHA = "e087cd54f265eb5fbc2442878d0bf7063e1b770cdcd6c9c4a4db9868bdd551b1"
ALIASES = {
    "usr/bin/tclsh.exe": "tclsh8.6.exe",
    "usr/lib/libtcl.dll.a": "libtcl8.6.dll.a",
    "usr/lib/libtclstub.a": "libtclstub8.6.a",
    "usr/lib/tcl8.6/tclConfig.sh": "../tclConfig.sh",
}
CONFIGS = ["usr/lib/tclConfig.sh", "usr/lib/tclooConfig.sh",
           "usr/lib/itcl4.2.2/itclConfig.sh", "usr/lib/tdbc1.1.3/tdbcConfig.sh"]
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)=(.*)$", re.MULTILINE)
PREFIX = "${TCL_PROVIDER_PREFIX:?Set the exact installed Tcl usr prefix}"
ZLIB = "${TCL_PROVIDER_ZLIB_PREFIX:?Set the exact qualified zlib usr prefix}"


def assignments(text):
    result = {}
    for name, rhs in ASSIGNMENT.findall(text):
        require(name not in result, f"Duplicate metadata assignment: {name}")
        if rhs.startswith(("'", '"')):
            require(rhs.endswith(rhs[0]), f"Nonliteral assignment needs review: {name}")
            rhs = rhs[1:-1]
        result[name] = rhs
    return result


def relocate_config(text, original_zlib):
    originals = assignments(text)
    replacements = [
        ("/c/ag-e138920f/tcl-msys-02/build/pkgs/", PREFIX + "/lib/"),
        ("/c/ag-e138920f/tcl-msys-02/build", PREFIX + "/lib"),
        ("/c/ag-e138920f/tcl-msys-02/source/pkgs/tdbc1.1.3/library", PREFIX + "/lib/tdbc1.1.3"),
        ("/c/ag-e138920f/tcl-msys-02/source/pkgs/tdbc1.1.3/generic", PREFIX + "/include"),
        ("/c/ag-e138920f/tcl-msys-02/source/pkgs/tdbc1.1.3", PREFIX + "/include"),
        ("/c/ag-e138920f/tcl-msys-02/source/pkgs/itcl4.2.2/generic", PREFIX + "/include"),
        ("/c/ag-e138920f/tcl-msys-02/source/pkgs/itcl4.2.2", PREFIX + "/include"),
        ("/c/ag-e138920f/tcl-msys-02/source", PREFIX + "/include"),
        (original_zlib, ZLIB),
        ("/usr", PREFIX),
    ]
    changes = {}

    def replace(match):
        name, original = match.groups()
        value = originals[name]
        if name == "TCL_CC":
            value = "${TCL_PROVIDER_CC:?Set the exact qualified compiler executable}"
        elif name == "TCL_RANLIB":
            value = "${TCL_PROVIDER_RANLIB:?Set the exact qualified ranlib executable}"
        else:
            for old, new in replacements:
                value = value.replace(old, new)
        if value == originals[name]:
            return match[0]
        require('"' not in value and "`" not in value and "\\" not in value,
                f"Shell quoting requires review: {name}")
        changes[name] = {"before": originals[name], "after": value}
        return name + '="' + value + '"'

    relocated = ASSIGNMENT.sub(replace, text)
    after = assignments(relocated)
    require(set(after) == set(originals), "The metadata variable set changed")
    require(all(after[name] == value for name, value in originals.items() if name not in changes),
            "Non-path metadata changed")
    require(not any("ag-e138920f" in value or "/Users/" in value or value.startswith("/usr")
                    for value in after.values()), "Unqualified producer path remains")
    return relocated, changes


def validate_archive(archive, files):
    records = {}
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            require(member.name not in records, "Duplicate tar member")
            if member.issym():
                require(ALIASES.get(member.name) == member.linkname, "Unexpected tar link")
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
                require(not PurePosixPath(member.linkname).is_absolute() and target in files,
                        "Archive alias escapes its provider or names a missing file")
                records[member.name] = {"type": "symlink", "target": member.linkname,
                                        "resolved": target, "target_sha256": files[target]["sha256"]}
            else:
                require(member.isfile() and member.name in files, "Unexpected archive member")
                import hashlib
                data = stream.extractfile(member)
                require(hashlib.file_digest(data, "sha256").hexdigest() == files[member.name]["sha256"],
                        f"Archive bytes changed: {member.name}")
                records[member.name] = {"type": "file", **files[member.name]}
    require(set(records) == set(files) | set(ALIASES), "Archive member closure differs")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    args = parser.parse_args()
    sources = import_tools()
    from native_job_runner import run_observed
    verify_inputs()
    require(digest(RECIPE) == RECIPE_SHA, "Pinned package recipe changed")
    require(digest(BOOTSTRAP_RECEIPT) == BOOTSTRAP_SHA, "Host metadata driver receipt changed")
    sources.verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
    output = ROOT / args.name
    output.mkdir()
    shutil.copyfile(Path(__file__), output / "package_provider.py")
    shutil.copyfile(Path(__file__).with_name("qualify.py"), output / "qualify.py")
    shutil.copyfile(RECIPE, output / "PKGBUILD")
    payload = output / "payload"
    shutil.copytree(ROOT / "runtime", payload)
    original_files = sources.inventory(ROOT / "runtime")
    original_zlib = assignments((payload / "usr/lib/tclConfig.sh").read_text())["TCL_LD_FLAGS"].strip()[2:]
    require(original_zlib.endswith("/lib"), "Expected the qualified build's explicit zlib lib path")
    original_zlib = original_zlib[:-4]
    zlib_prefix = Path(original_zlib)
    require((zlib_prefix / "include/zlib.h").is_file() and (zlib_prefix / "lib/libz.dll.a").is_file(),
            "The exact original zlib development files are required")
    changes, originals = {}, {}
    for relative in CONFIGS:
        path = payload / relative
        original = path.read_text(encoding="utf-8")
        updated, delta = relocate_config(original, original_zlib)
        originals[relative] = assignments(original)
        changes[relative] = delta
        path.write_text(updated, encoding="utf-8", newline="\n")
    pc = payload / "usr/lib/pkgconfig/tcl.pc"
    pc_original = pc.read_text(encoding="utf-8")
    pc_updated = pc_original.replace("prefix=/usr\n", "prefix=${pcfiledir}/../..\n", 1)
    pc_updated = pc_updated.replace("exec_prefix=/usr\n", "exec_prefix=${prefix}\n", 1)
    pc_updated = pc_updated.replace("libdir=/usr/lib\n", "libdir=${prefix}/lib\n", 1)
    require(pc_updated != pc_original, "Expected the original installed pkg-config prefix")
    require(pc_updated.split("includedir=", 1)[1] == pc_original.split("includedir=", 1)[1],
            "A non-path pkg-config field changed")
    pc.write_text(pc_updated, encoding="utf-8", newline="\n")
    files = sources.inventory(payload)
    changed = {p for p in files if files[p] != original_files[p]}
    require(set(files) == set(original_files) and
            changed == {"usr/lib/tclConfig.sh", "usr/lib/itcl4.2.2/itclConfig.sh",
                        "usr/lib/tdbc1.1.3/tdbcConfig.sh", "usr/lib/pkgconfig/tcl.pc"},
            "Only four path-bearing metadata files may change in the provider")
    for alias in ALIASES:
        require(alias not in files, "An archive alias would overwrite a real payload file")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update({
        "PATH": os.pathsep.join((str(BOOTSTRAP / "usr/bin"), str(Path(env["SystemRoot"]) / "System32"))),
        "HOME": msys(output), "USERPROFILE": str(output), "TMPDIR": msys(output),
        "TMP": msys(output), "TEMP": msys(output), "WOARM64_NATIVE_TEST_ROOT": str(ROOT),
        "WOARM64_NATIVE_ARG_CONVERSION": "none",
        "TCL_PROVIDER_PREFIX": (payload / "usr").as_posix(),
        "TCL_PROVIDER_ZLIB_PREFIX": zlib_prefix.as_posix(),
        "TCL_PROVIDER_CC": (INPUT / "tc-guard-01/bin/gcc.exe").as_posix(),
        "TCL_PROVIDER_RANLIB": (INPUT / "tc-guard-01/bin/ranlib.exe").as_posix(),
    })
    commands, evaluated = {}, {}
    for index, relative in enumerate(CONFIGS):
        script = output / f"metadata-{index}.sh"
        body = "set -euo pipefail\n. \"$1\"\n"
        for name in originals[relative]:
            body += f"printf '%s\\000%s\\000' '{name}' \"${{{name}}}\"\n"
        script.write_text(body, encoding="utf-8", newline="\n")
        relay = output / f"metadata-{index}-exits"
        relay.mkdir()
        argv = [BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc",
                msys(script), msys(payload / relative)]
        request = output / f"metadata-{index}.request.json"
        launch = output / f"metadata-{index}.launch.json"
        write_json(request, {"command": list(map(str, argv)), "record": str(launch),
                             "log": str(output / f"metadata-{index}.bin")})
        free_memory = require_memory()
        process = run_observed([sys.executable, "-B", output / "qualify.py", "host-launch", request],
                               cwd=output, env=env, log_path=output / f"metadata-{index}.bin",
                               result_path=output / f"metadata-{index}.native-job.json",
                               relay_records=relay, timeout=30, driver_prefix=ROOT / "observer")
        commands[relative] = {"argv": list(map(str, argv)), "process": process,
                              "launch": {"path": str(launch), "sha256": digest(launch)},
                              "free_memory_before": free_memory,
                              "script_sha256": digest(script),
                              "scope": "Explicit x64/emulated Bash evaluates metadata only; not native Bash admission"}
        require(process["passed"], "Explicit provider shell metadata did not evaluate")
        fields = (output / f"metadata-{index}.bin").read_bytes().decode().split("\0")
        require(fields[-1] == "" and len(fields) % 2 == 1, "Malformed metadata evaluation")
        values = dict(zip(fields[::2], fields[1::2]))
        require(set(values) == set(originals[relative]), "Evaluated metadata variable set differs")
        for name, original in originals[relative].items():
            if name in changes[relative]:
                expected = changes[relative][name]["after"]
                for variable, value in env.items():
                    expected = re.sub(r"\$\{" + variable + r":\?[^}]+\}", lambda _: value, expected)
            else:
                expected = original
            require(values[name] == expected, f"Metadata value or flags changed: {name}")
        evaluated[relative] = values
    # These path outputs must name the real private payload, not the host driver's /usr.
    for relative, values in evaluated.items():
        for name, value in values.items():
            if name.endswith(("_STUB_LIB_PATH", "_PREFIX", "_SRC_DIR", "_LIBRARY_PATH")):
                require(Path(value).exists(), f"Metadata path is not present: {name}={value}")
    archive = output / "tcl-native-msys-8.6.12-provider.tar.gz"
    with archive.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name in sorted(set(files) | set(ALIASES)):
                info = tarfile.TarInfo(name)
                info.mtime = 0
                if name in ALIASES:
                    info.type, info.linkname, info.mode = tarfile.SYMTYPE, ALIASES[name], 0o777
                    tar.addfile(info)
                else:
                    info.size = files[name]["size"]
                    info.mode = 0o755 if Path(name).suffix in (".exe", ".dll") else 0o644
                    with (payload / name).open("rb") as data:
                        tar.addfile(info, data)
    members = validate_archive(archive, files)
    require(sources.inventory(payload) == files, "Metadata execution changed the provider")
    verify_inputs()
    sources.verify_tree(BOOTSTRAP, BOOTSTRAP_RECEIPT)
    require(digest(RECIPE) == RECIPE_SHA, "Read-only recipe changed during export")
    write_json(output / "result.json", {
        "schema": 1, "status": "relocatable-provider-candidate-not-full-admission",
        "package": "tcl-msys", "version": "8.6.12", "target": "aarch64-pc-cygwin",
        "scope": "Aggregate Tcl/runtime/devel/doc view; all native/library/header/document bytes unchanged",
        "input_runtime": str(ROOT / "runtime"), "recipe": {"path": str(RECIPE), "sha256": RECIPE_SHA},
        "payload": str(payload), "files": files, "metadata_changes": changes,
        "metadata_evaluations": evaluated, "metadata_commands": commands,
        "metadata_environment": {k: v for k, v in env.items() if k.startswith("TCL_PROVIDER_")},
        "metadata_contract": "Set all four TCL_PROVIDER_* values explicitly when sourcing Tcl configs. "
                             "Compiler and zlib paths use Windows C:/ syntax; the private runtime uses approved /c paths. "
                             "Installed header paths replace unavailable original source/build paths. "
                             "The pkg-config prefix resolves relative to pcfiledir.",
        "pkg_config_execution": "Not run: pkg-config/pkgconf is not present in the approved driver. "
                                "Only the three path assignments changed; all other pc fields are identical.",
        "archive": {"path": str(archive), "sha256": digest(archive), "members": members},
        "aliases": {name: members[name] for name in ALIASES},
        "alias_scope": "Real relative POSIX tar SYMTYPE entries with verified in-archive targets. "
                       "No NTFS symlinks, copy-labelled links, machine settings or extraction/alias-launch claim.",
        "scope_gates": ["Full upstream suite not run", "Expected-negative raw256 observer classification pending",
                        "External database connectors/accounts not exercised",
                        "SQLite binding supplied and qualified by the separate SQLite child",
                        "Pipeline archive extraction/alias activation remains its own admission gate"],
        "inputs_unchanged": True,
    })
    print(json.dumps({"result": str(output / "result.json"), "archive": str(archive),
                      "files": len(files), "real_relative_archive_links": len(ALIASES)}))


if __name__ == "__main__":
    main()
