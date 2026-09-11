"""Audit actual extracted PEs and distinguish bundled libraries from genuine Windows system imports."""

import argparse
import os
from pathlib import Path

from artifact import ArtifactError, inventory, pe_identity, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    files = inventory(root)
    folded = {name.casefold(): name for name in files}
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    bindings, failures = [], []
    system_cache = {}
    for name, row in files.items():
        if not row["machine"]:
            continue
        if row["machine"] != "0xAA64" or row.get("managed"):
            failures.append({"file": name, "reason": "non-native ARM64 PE", "machine": row["machine"]})
        for dll in row["imports"] + row["delay_imports"]:
            directories = [Path(name).parent.as_posix(), "mingwarm64/bin", "usr/bin"]
            candidates = [folded.get((directory + "/" + dll).casefold()) for directory in directories]
            candidates = list(dict.fromkeys(value for value in candidates if value is not None))
            if candidates:
                target = candidates[0]
                bindings.append({"file": name, "import": dll, "kind": "payload", "path": target,
                                 "sha256": files[target]["sha256"], "machine": files[target]["machine"]})
            elif dll.startswith(("api-ms-win-", "ext-ms-win-")):
                bindings.append({"file": name, "import": dll, "kind": "Windows API-set contract"})
            elif (system32 / dll).is_file():
                if dll not in system_cache:
                    actual = system32 / dll
                    identity = pe_identity(actual)
                    system_cache[dll] = {"path": str(actual), "sha256": sha256(actual), "machine": identity["machine"]}
                bindings.append({"file": name, "import": dll, "kind": "Windows system DLL", **system_cache[dll]})
            else:
                failures.append({"file": name, "reason": "unresolved DLL", "import": dll})
    report = {"schema": 1, "scope": "Actual PE headers, normal/delay DLL dependency resolution in extraction/System32; live module/child attestation remains separately required",
              "payload_files": len(files), "payload_pe_count": sum(bool(row["machine"]) for row in files.values()),
              "passed": not failures, "failures": failures, "bindings": bindings,
              "payload_sha256": {name: row["sha256"] for name, row in files.items()}}
    write_json(args.output, report)
    print(f"PEs={report['payload_pe_count']} files={len(files)} unresolved/non-native={len(failures)}")
    for item in failures:
        print(item)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
