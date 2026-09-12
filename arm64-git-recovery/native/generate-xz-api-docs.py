"""Generate the real pinned XZ API documentation with a separate, exit-protected Windows bootstrap."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from bounded_process import run
from documentation_tools import verify_documentation_driver, verify_xz_documentation
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "source-manifest", "driver", "driver-manifest",
                 "bootstrap", "bootstrap-manifest", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt" or args.output.exists():
        raise ContractError("Windows and a fresh documentation output are required")
    verify_tree(args.source, args.source_manifest)
    source_record = json.loads(args.source_manifest.read_text())
    policy = source_record.get("build_policy")
    if (source_record.get("source", {}).get("id") != "xz" or
            source_record["source"]["version"] != "5.8.3" or
            not isinstance(policy, dict) or policy.get("windows_doxygen_paths") is not True):
        raise ContractError("Expected the pinned XZ source with its explicit Windows documentation-path support")
    driver = verify_documentation_driver(args.driver, args.driver_manifest)
    verify_tree(args.bootstrap, args.bootstrap_manifest)
    bootstrap = json.loads(args.bootstrap_manifest.read_text())
    if (bootstrap.get("status") != "private-emulated-build-input-copy" or
            Path(bootstrap["prefix"]).resolve() != args.bootstrap):
        raise ContractError("The XZ source helper requires the exact private bootstrap copy")
    scripts = Path(__file__).parent.resolve()
    immutable = {str(path): digest(path) for path in (
        args.source_manifest, args.driver_manifest, args.bootstrap_manifest,
        Path(__file__), scripts / "documentation_exec.py", scripts / "documentation_tools.py",
        scripts / "doc-driver/doxygen")}
    args.output.mkdir(parents=True)
    for name in ("doc", "temp", "home", "documentation-exits"):
        (args.output / name).mkdir()
    source = args.output / "source"
    shutil.copytree(args.source, source)
    verify_tree(source, args.source_manifest)
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (scripts / "doc-driver", args.driver,
                                                args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "WOARM64_WINDOWS_DOXYGEN": "1", "WOARM64_DOCUMENTATION_DRIVER": str(args.driver),
                "WOARM64_DOCUMENTATION_MANIFEST": str(args.driver_manifest),
                "WOARM64_DOCUMENTATION_EXIT_DIR": str(args.output / "documentation-exits"),
                "WOARM64_NATIVE_PYTHON": sys.executable, "WOARM64_NATIVE_PYTHON_SHA256": digest(sys.executable)})
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc",
               (source / "doxygen/update-doxygen").as_posix(), "api", source.as_posix(),
               (args.output / "doc").as_posix()]
    report = {"schema": 1, "status": "failed", "driver": driver,
              "source_manifest_sha256": digest(args.source_manifest), "input_identities": immutable,
              "scope": "Real XZ source API documentation only; explicitly emulated drivers, no target compilation or execution"}
    try:
        with (args.output / "generation.log").open("xb") as log:
            report["process"] = run(command, cwd=args.output, env=env, log=log, timeout=120)
        if not report["process"]["passed"]:
            raise ContractError("Actual XZ API documentation generation failed")
        records = sorted((args.output / "documentation-exits").glob("*.json"))
        if len(records) != 1 or json.loads(records[0].read_text())["raw_exit"] != 0:
            raise ContractError("Expected one faithfully captured successful Doxygen invocation")
        api = args.output / "doc/api"
        report["api_proof"] = verify_xz_documentation(api, source_record["source"]["version"])
        report.update({"status": "xz-api-documentation-generated-not-a-target-build",
                       "raw_exit_record_sha256": digest(records[0]), "files": inventory(api)})
    finally:
        try:
            if any(digest(path) != sha for path, sha in immutable.items()):
                raise ContractError("Documentation recipe inputs changed")
            verify_tree(source, args.source_manifest)
            verify_tree(args.source, args.source_manifest)
            verify_tree(args.bootstrap, args.bootstrap_manifest)
            verify_documentation_driver(args.driver, args.driver_manifest)
            report["inputs_unchanged"] = True
        except (ContractError, OSError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            with (args.output / "result.json").open("x", encoding="utf-8", newline="\n") as out:
                json.dump(report, out, indent=2)
                out.write("\n")
    print(report["status"])


if __name__ == "__main__":
    main()
