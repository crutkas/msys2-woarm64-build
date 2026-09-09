"""Validate and seal a native ARM64 utility stage for the Bash test harness."""

import argparse
import json
from pathlib import Path
import struct
import sys


MAINTAINED = Path(r"C:\ag-native-e138-01\maintained")
REQUIRED = (
    "awk", "basename", "cat", "chmod", "cmp", "cp", "cut", "date", "diff",
    "dirname", "echo", "env", "expr", "false", "find", "grep", "head",
    "hexdump", "id", "ln", "locale", "ls", "mkdir", "mkfifo", "mktemp", "mv", "od",
    "pcregrep", "printenv", "printf", "pwd", "readlink", "rm", "rmdir", "sed",
    "sleep", "sort", "tail", "tee", "test", "touch", "tr", "true", "wc",
    "xargs",
)


def pe_machine(path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not PE: {path}")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE signature: {path}")
    return struct.unpack_from("<H", data, pe + 4)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--smoke-result", required=True, type=Path)
    args = parser.parse_args()
    stage = args.stage.resolve()
    runtime_sha256 = args.runtime_sha256.lower()
    if len(runtime_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in runtime_sha256):
        parser.error("The runtime SHA-256 must contain 64 hexadecimal characters")
    sys.path.insert(0, str(MAINTAINED))
    sources = __import__("sources")
    smoke_result = args.smoke_result.resolve()
    smoke = json.loads(smoke_result.read_text())
    if not smoke.get("passed"):
        parser.error("The native utility smoke observer did not pass")
    stage_suffix = str(stage).replace("\\", "/").split(":/", 1)[-1].lower()
    smoke_root = smoke["native_target_root"].replace("\\", "/").lower()
    if not smoke_root.endswith(f"/{stage_suffix}"):
        parser.error("The native utility smoke result targets a different stage")
    runtime = stage / "usr/bin/msys-2.0.dll"
    if sources.digest(runtime) != runtime_sha256:
        parser.error("The native environment runtime differs")
    identities = {}
    for name in REQUIRED:
        executable = stage / f"usr/bin/{name}.exe"
        if pe_machine(executable) != 0xAA64:
            parser.error(f"Non-ARM64 utility: {name}")
        identities[name] = sources.digest(executable)
    for executable in (stage / "usr/bin").glob("*.exe"):
        if pe_machine(executable) != 0xAA64:
            parser.error(f"Non-ARM64 executable in stage: {executable.name}")
    manifest = {
        "schema": 1,
        "package": "native-bash-test-utilities",
        "status": "native-provider-stage-smoke-tested-full-package-checks-pending",
        "runtime_sha256": runtime_sha256,
        "smoke_result": str(smoke_result),
        "smoke_result_sha256": sources.digest(smoke_result),
        "required_executables": identities,
        "files": sources.inventory(stage),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    sources.verify_tree(stage, args.manifest)
    print(json.dumps({
        "manifest": str(args.manifest),
        "manifest_sha256": sources.digest(args.manifest),
        "files": len(manifest["files"]),
        "required_executables": len(identities),
    }))


if __name__ == "__main__":
    main()
