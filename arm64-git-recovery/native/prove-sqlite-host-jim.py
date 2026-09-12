"""Qualify the pinned upstream Jim as a native Windows host-only configure tool."""

import importlib.util
import json
from pathlib import Path
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, verify_tree

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
output = root / "host-jim-01"
output.mkdir()
(output / "native-exits").mkdir()
verify_tree(root / "host-compiler", root / "host-compiler.inventory.json")
env = launcher.environment(root, output, 1)
compiler = root / "host-compiler/bin/gcc.exe"
source = root / "prepared/source/autosetup/jimsh0.c"
exe = output / "jimsh.exe"
report = {"schema": 1, "status": "failed", "scope": "Host-only native ARM64 MinGW Jim; not target SQLite/Tcl/lemon",
          "launcher": launcher.process_identity(), "source_sha256": digest(source), "steps": []}
launcher.write_json(output / "launch.json", report)
print(json.dumps(report["launcher"]), flush=True)
try:
    command = [compiler, "-O1", source, "-o", exe]
    report["steps"].append({"command": list(map(str, command)), "process": run_observed(
        command, cwd=output, env=env, log_path=output / "compile.log", result_path=output / "compile.native-job.json",
        relay_records=output / "native-exits", timeout=180, driver_prefix=root / "observer")})
    if not report["steps"][-1]["process"]["passed"]:
        raise ContractError("Host Jim compilation failed")
    from pe_exports import export_names
    import struct
    data = exe.read_bytes()
    offset = struct.unpack_from("<I", data, 60)[0]
    if (data[:2], data[offset:offset + 4], struct.unpack_from("<H", data, offset + 4)[0],
            struct.unpack_from("<H", data, offset + 24)[0]) != (b"MZ", b"PE\0\0", 0xAA64, 0x20B):
        raise ContractError("Host Jim is not ordinary ARM64 PE32+")
    report["exe_sha256"] = digest(exe)
    for name, code, expected in (("zero", 'puts "host-jim-zero"; exit 0\n', 0),
                                 ("nonzero", 'puts stderr "host-jim-nonzero"; exit 7\n', 7),
                                 ("argv", 'if {$argv ne [list {space value} {/usr} {C:/owned/path}]} {exit 9}; puts "host-jim-argv"; exit 0\n', 0)):
        fixture = output / f"{name}.tcl"
        fixture.write_text(code, newline="\n")
        command = [exe, fixture, *(["space value", "/usr", "C:/owned/path"] if name == "argv" else [])]
        process = run_observed(command, cwd=output, env=env, log_path=output / f"{name}.log",
                               result_path=output / f"{name}.native-job.json", relay_records=output / "native-exits",
                               timeout=30, driver_prefix=root / "observer")
        record = json.loads((output / f"{name}.native-job.json").read_text())
        report["steps"].append({"name": name, "command": list(map(str, command)), "expected_exit": expected,
                                "process": process})
        if process["exit"] != expected or record["unrelayed_high_exits"] or not record["observation_count_matches"]:
            raise ContractError(f"Host Jim {name} exit/argv/coverage failed")
    report["status"] = "host-only-native-arm64-jim-zero-nonzero-argv-passed"
finally:
    verify_tree(root / "host-compiler", root / "host-compiler.inventory.json")
    launcher.write_json(output / "result.json", report)
