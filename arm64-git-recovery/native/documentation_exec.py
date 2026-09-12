"""Preserve the exact Windows exit of the fixed, explicitly emulated documentation driver."""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from documentation_tools import verify_documentation_driver
from sources import ContractError, digest


def portable_exit(code):
    return code if 0 <= code <= 255 else 255


def main():
    if os.name != "nt" or sys.argv[1:] not in (["-q", "-"], ["--version"]):
        raise ContractError("This documentation relay accepts only the upstream stdin-config or version command")
    if digest(sys.executable) != os.environ["WOARM64_NATIVE_PYTHON_SHA256"]:
        raise ContractError("Documentation controller Python changed")
    prefix = Path(os.environ["WOARM64_DOCUMENTATION_DRIVER"])
    manifest = Path(os.environ["WOARM64_DOCUMENTATION_MANIFEST"])
    qualification = verify_documentation_driver(prefix, manifest)
    records = Path(os.environ["WOARM64_DOCUMENTATION_EXIT_DIR"])
    if not records.is_dir():
        raise ContractError("Explicit documentation exit-evidence directory is required")
    executable = prefix / "doxygen.exe"
    with subprocess.Popen([str(executable), *sys.argv[1:]]) as process:
        raw = process.wait()
        child_pid = process.pid
    code = portable_exit(raw)
    record = {"executable": str(executable), "sha256": digest(executable), "child_pid": child_pid,
              "raw_exit": raw, "portable_exit": code, "driver": qualification,
              "scope": "Fixed x64 documentation bootstrap only; not a native test observer or compiler proxy"}
    with (records / f"{os.getpid()}-{uuid.uuid4().hex}.json").open("x", encoding="utf-8") as out:
        json.dump(record, out, indent=2)
        out.write("\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
