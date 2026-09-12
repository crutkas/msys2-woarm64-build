"""Copy verified bootstrap tools into a build-owned root, excluding root launchers and private state."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or digest(args.handoff) != args.sha256:
        raise ContractError("Require a new private copy and the exact bootstrap recovery receipt")
    handoff = json.loads(args.handoff.read_text())
    result = handoff["Result"]
    if (handoff["Status"] != "new-isolated-bootstrap-restored-verified" or
            any(result[name] != 0 for name in ("DllMissing", "DllDifferences", "DllUnowned", "BaselineGaps", "HashDrift"))):
        raise ContractError("Bootstrap recovery was not fully verified")
    source = Path(handoff["NewPrefix"])
    before = inventory(source / "usr")
    if any("symlink" in row for row in before.values()):
        raise ContractError("Explicit resolution is required for native filesystem links in bootstrap input")
    shutil.copytree(source / "usr", args.output / "usr")
    (args.output / "etc").mkdir()
    config = {}
    for name in ("fstab", "nsswitch.conf"):
        path = source / "etc" / name
        if path.is_file():
            config[name] = digest(path)
            shutil.copyfile(path, args.output / "etc" / name)
    for name in ("tmp", "var/tmp", "home"):
        (args.output / name).mkdir(parents=True, exist_ok=True)
    if inventory(args.output / "usr") != before or inventory(source / "usr") != before:
        raise ContractError("Bootstrap tool bytes changed while copying")
    if any(digest(source / "etc" / name) != sha or digest(args.output / "etc" / name) != sha
           for name, sha in config.items()):
        raise ContractError("Bootstrap configuration changed")
    report = {"schema": 1, "status": "private-emulated-build-input-copy",
              "source_handoff_sha256": args.sha256, "source_prefix": str(source),
              "prefix": str(args.output.resolve()), "files": inventory(args.output),
              "scope": "usr tools plus fstab/nsswitch only; no root launchers, package-manager private state, user homes or credentials",
              "architecture": handoff["BootstrapArchitecture"]}
    args.output.with_name(args.output.name + ".copy.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Copied {len(before)} bootstrap tool files into a private build root")


if __name__ == "__main__":
    main()
