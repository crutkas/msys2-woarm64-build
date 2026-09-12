"""Path-only views and full recipe contract for the native MSYS SQLite build."""

import json
from pathlib import Path
import re

from sources import ContractError


SPLITS = ("sqlite", "libsqlite", "libsqlite-devel", "sqlite-doc",
          "tcl-sqlite", "sqlite-extensions", "lemon")
TOOLS = ("sqlite3.exe", "sqlite3_analyzer.exe", "sqldiff.exe", "dbhash.exe", "rbu.exe")


def recipe():
    return json.loads(Path(__file__).with_name("ssh-recipes.json").read_text())[
        "transitive_recipe_requirements"]["sqlite-msys"]


def msys_path(path):
    path = Path(path).resolve()
    text = path.as_posix()
    if not re.fullmatch(r"[A-Za-z]:/[^'\"\n ]+", text):
        raise ContractError(f"Expected an unambiguous owned drive path: {text}")
    return "/" + text[0].lower() + text[2:]


def tcl_config_view(text, root):
    tcl = msys_path(root / "tcl" / "usr")
    compiler = msys_path(root / "compiler")
    tcl_cc = (root / "tcl" / "usr").as_posix()
    zlib_cc = (root / "zlib" / "usr").as_posix()
    replacements = {
        "TCL_CC": f"{compiler}/bin/gcc.exe",
        "TCL_RANLIB": f"{compiler}/bin/ranlib.exe",
        "TCL_PREFIX": tcl,
        "TCL_EXEC_PREFIX": tcl,
        "TCL_INCLUDE_SPEC": f"-I{tcl_cc}/include",
        "TCL_LIB_SPEC": f"-L{tcl_cc}/lib -ltcl8.6",
        "TCL_BUILD_LIB_SPEC": f"-L{tcl_cc}/lib -ltcl8.6",
        "TCL_STUB_LIB_SPEC": f"-L{tcl_cc}/lib -ltclstub8.6",
        "TCL_BUILD_STUB_LIB_SPEC": f"-L{tcl_cc}/lib -ltclstub8.6",
        "TCL_STUB_LIB_PATH": f"{tcl}/lib/libtclstub8.6.a",
        "TCL_BUILD_STUB_LIB_PATH": f"{tcl}/lib/libtclstub8.6.a",
        "TCL_SRC_DIR": msys_path(root / "tcl-source"),
        "TCL_PACKAGE_PATH": f"{{{tcl}/lib}} ",
    }
    for key in ("TCL_EXTRA_CFLAGS", "TCL_LD_FLAGS"):
        match = re.search(rf"(?m)^{key}='([^']*)'$", text)
        if not match:
            raise ContractError(f"Missing Tcl config field {key}")
        old = match[1]
        updated, count = re.subn(r"(?<=[IL])C:/[^ ]+/zlib-msys-01/stage/usr/(include|lib)",
                                 lambda m: zlib_cc + "/" + m[1], old)
        if count != 1:
            raise ContractError(f"Unexpected pinned Tcl zlib path in {key}")
        replacements[key] = updated
    for key, value in replacements.items():
        text, count = re.subn(rf"(?m)^{key}='[^']*'$", lambda _: f"{key}='{value}'", text)
        if count != 1:
            raise ContractError(f"Missing/ambiguous Tcl path field {key}")
    return text, replacements


def extension_makefile(text, root, build):
    replacements = {
        "@srcdir@": msys_path(root / "prepared" / "source" / "ext" / "misc"),
        "@top_srcdir@": msys_path(root / "prepared" / "source"),
        "@top_builddir@": msys_path(build),
        "@prefix@": "/usr", "@datadir@": "/usr/share",
        "@CC@": msys_path(root / "compiler" / "bin" / "gcc.exe"),
    }
    for key, value in replacements.items():
        if key not in text:
            raise ContractError(f"Missing extension substitution {key}")
        text = text.replace(key, value)
    return text
