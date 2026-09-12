"""Private adoption of sealed SSH sources, or read-only OpenSSH feature checks."""

import argparse
import json
from pathlib import Path

from sources import digest, load_lock
from ssh_build_inputs import adopt_source, contract, prerequisite_closure, validate_openssh_configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    adopt = commands.add_parser("adopt")
    adopt.add_argument("--package", required=True, choices=contract()["profiles"])
    for name in ("source", "manifest", "output"):
        adopt.add_argument(f"--{name}", type=Path, required=True)
    adopt.add_argument("--manifest-sha256", required=True)
    adopt.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    check = commands.add_parser("check-openssh-config")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--makefile", type=Path, required=True)
    closure = commands.add_parser("closure")
    closure.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    args = parser.parse_args()
    if args.operation == "adopt":
        result = adopt_source(args.package, args.source, args.manifest, args.manifest_sha256,
                              args.output, args.lock)
        print(json.dumps({"status": result["status"], "files": result["copied_files"],
                          "receipt": str(args.output / "adoption.json")}, indent=2))
    elif args.operation == "check-openssh-config":
        result = validate_openssh_configuration(args.config.read_text(encoding="utf-8"),
                                                args.makefile.read_text(encoding="utf-8"))
        result.update(config_sha256=digest(args.config), makefile_sha256=digest(args.makefile))
        print(json.dumps(result, indent=2))
    else:
        result = prerequisite_closure(load_lock(args.lock))
        result.update(source_lock_sha256=digest(args.lock))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
