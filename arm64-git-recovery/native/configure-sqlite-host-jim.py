"""Configure the identical MSYS target recipe using qualified Windows-host Jim."""

import argparse
import importlib.util
import json
from pathlib import Path
import re

from native_job_runner import run_observed
from sources import ContractError, digest, inventory, verify_tree
from sqlite_build_inputs import recipe

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
source, output, build = args.source.resolve(), args.output.resolve(), args.build.resolve()
if any(not p.is_relative_to(root) for p in (source, output, build)):
    raise ContractError("Private source/build/evidence paths required")
source_manifest = source.with_name(source.name + ".inventory.json")
verify_tree(source, source_manifest)
output.mkdir()
build.mkdir()
(output / "native-exits").mkdir()
jim = root / "host-jim-01/jimsh.exe"
proof = json.loads((root / "host-jim-01/result.json").read_text())
if proof["status"] != "host-only-native-arm64-jim-zero-nonzero-argv-passed" or digest(jim) != proof["exe_sha256"]:
    raise ContractError("Qualified exact host Jim required")
verify_tree(root / "prepared", root / "prepared.inventory.json")
launcher.prepare_views(root)
view = root / "tcl-config-hostwin"
if view.exists():
    verify_tree(view, root / "tcl-config-hostwin.inventory.json")
else:
    view.mkdir()
    text = (root / "tcl-config-windows/tclConfig.sh").read_text()
    path_fields = ("CC", "RANLIB", "PREFIX", "EXEC_PREFIX", "STUB_LIB_PATH", "BUILD_STUB_LIB_PATH",
                   "SRC_DIR", "PACKAGE_PATH")
    for field in path_fields:
        text, count = re.subn(rf"(?m)^(TCL_{field}='[^'\n]*)/c/", r"\1C:/", text)
        if count != 1:
            raise ContractError(f"Expected a private path in Tcl {field}")
    (view / "tclConfig.sh").write_text(text, newline="\n")
    launcher.write_json(root / "tcl-config-hostwin.inventory.json", {"scope": "Windows-host configure view, path-only",
                                                                  "files": inventory(view)})
env = launcher.environment(root, output, 1)
native = (root / "compiler/bin").as_posix()
env.update(CC=f"{native}/gcc.exe", CXX=f"{native}/g++.exe", CC_FOR_BUILD=f"{native}/gcc.exe",
           AR=f"{native}/ar.exe", RANLIB=f"{native}/ranlib.exe", CCACHE="none",
           WRAPPER=(source / "configure").as_posix(), MSYSTEM="CYGWIN",
           CFLAGS="-O2 -g -fstack-protector-strong -pipe -D_FORTIFY_SOURCE=2",
           CPPFLAGS=" ".join(recipe()["cppflags"]) +
           f" -I{root.as_posix()}/zlib/usr/include -I{root.as_posix()}/readline/usr/include -I{root.as_posix()}/ncurses/usr/include/ncursesw",
           LDFLAGS="-Wl,--no-insert-timestamp " + " ".join(f"-L{root.as_posix()}/{name}/usr/lib" for name in ("zlib", "readline", "ncurses", "tcl")),
           TCLLIBDIR="/usr/lib/sqlite3.53.4")
command = [jim, source / "autosetup/autosetup", *recipe()["configure"],
           f"--with-tcl={view.as_posix()}",
           f"--with-readline-cflags=-I{root.as_posix()}/readline/usr/include",
           f"--with-readline-ldflags=-L{root.as_posix()}/readline/usr/lib -lreadline -L{root.as_posix()}/ncurses/usr/lib -lncursesw"]
report = {"schema": 1, "status": "failed", "scope": "Same complete MSYS target configuration; host-only Jim change",
          "launcher": launcher.process_identity(), "command": list(map(str, command)), "build": str(build),
          "recipe": recipe(), "host_jim_sha256": digest(jim), "jobs": 1,
          "source_manifest_sha256": digest(source_manifest), "minimum_free_gib": launcher.require_memory()}
launcher.write_json(output / "launch.json", report)
print(json.dumps({"launch": report["launcher"], "command": report["command"], "log": str(output / "build.log")}), flush=True)
try:
    report["process"] = run_observed(command, cwd=build, env=env, log_path=output / "build.log",
                                     result_path=output / "native-job.json", relay_records=output / "native-exits",
                                     timeout=600, driver_prefix=root / "observer")
    if report["process"]["passed"]:
        report["status"] = "full-msys-sqlite-configure-native-windows-host-jim-passed"
        report["files"] = inventory(build)
finally:
    verify_tree(root / "prepared", root / "prepared.inventory.json")
    verify_tree(source, source_manifest)
    verify_tree(root / "host-compiler", root / "host-compiler.inventory.json")
    launcher.write_json(output / "result.json", report)
if report["status"] == "failed":
    raise SystemExit(1)
