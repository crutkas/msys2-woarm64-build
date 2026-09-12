"""Create a new complete assembly snapshot with a hash-bound, uniformly replaced runtime cohort."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory


def linux_path(path):
    value = Path(path).resolve().as_posix()
    if len(value) < 3 or value[1:3] != ":/":
        raise ContractError("Expected a local Windows path for WSL receipt verification")
    return "/mnt/" + value[0].lower() + "/" + value[3:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("assembly", "snapshot", "runtime-handoff", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("snapshot-sha256", "runtime-handoff-sha256", "old-runtime-sha256"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A new assembly root is required")
    if digest(args.snapshot) != args.snapshot_sha256 or digest(args.runtime_handoff) != args.runtime_handoff_sha256:
        raise ContractError("Published assembly/runtime handoff changed")
    snapshot = json.loads(args.snapshot.read_text())
    if Path(snapshot["currentAssembly"]).resolve() != args.assembly.resolve():
        raise ContractError("Assembly snapshot identifies a different input root")
    runtime = json.loads(args.runtime_handoff.read_text())
    if (any(runtime["result"][name] != "aarch64" for name in
            ("current_import_machine", "current_export_machine", "legacy_export_machine", "native_uname_m"))
            or runtime["result"]["real_perl_guard_exit"] != 0):
        raise ContractError("Runtime handoff has not passed the required machine-reporting boundary")
    for name in ("staged_runtime", "readiness", "fixed_results", "core_regressions", "perl_guard"):
        row = runtime[name]
        if digest(row["path"]) != row["sha256"]:
            raise ContractError(f"Runtime evidence changed: {name}")
    if runtime["staged_runtime"]["sha256"] != runtime["runtime"]["sha256"]:
        raise ContractError("Staged runtime differs from the built cohort")
    verifier = Path(__file__).with_name("runtime_readiness.py")
    subprocess.run(["wsl.exe", "-d", "Ubuntu", "--exec", "python3", "-B", linux_path(verifier),
                    "--receipt", linux_path(runtime["readiness"]["path"]), "--prefix", runtime["prefix"]], check=True)
    source = args.assembly / "ship"
    before = inventory(source)
    if any("symlink" in row for row in before.values()):
        raise ContractError("Assembly links require explicit resolution before copying")
    runtime_paths = [rel for rel in before if Path(rel).name.lower() == "msys-2.0.dll"]
    if not runtime_paths or any(before[rel]["sha256"] != args.old_runtime_sha256 for rel in runtime_paths):
        raise ContractError("Assembly has an unknown or mixed baseline runtime cohort")
    for required in ("git-stage/usr/bin/msys-2.0.dll", "posix-root/payload/usr/bin/msys-2.0.dll"):
        if required not in runtime_paths:
            raise ContractError("Missing a required native runtime root")
    for rel in ("git-stage/usr/bin/uname.exe", "posix-root/payload/usr/bin/uname.exe"):
        if before[rel]["sha256"] != runtime["unchanged_input_uname_sha256"]:
            raise ContractError("New runtime was not exercised with the assembly's unchanged uname")
    shutil.copytree(source, args.output / "ship")
    if inventory(args.output / "ship") != before:
        raise ContractError("Fresh assembly copy differs")
    changed = []
    for rel in runtime_paths:
        destination = args.output / "ship" / rel
        shutil.copyfile(runtime["staged_runtime"]["path"], destination)
        if digest(destination) != runtime["runtime"]["sha256"]:
            raise ContractError("Runtime snapshot copy differs")
        changed.append({"path": rel, "old_sha256": before[rel]["sha256"], "new_sha256": digest(destination)})
    after = inventory(args.output / "ship")
    if (set(after) != set(before) or inventory(source) != before or
            any(after[rel] != row for rel, row in before.items() if rel not in runtime_paths)):
        raise ContractError("Unrelated assembly bytes or frozen inputs changed")
    evidence = args.output / "cohort-inputs"
    evidence.mkdir()
    shutil.copyfile(args.runtime_handoff, evidence / "runtime-handoff.json")
    shutil.copyfile(runtime["readiness"]["path"], evidence / "runtime-readiness.json")
    report = {"schema": 1, "status": "new-coherent-runtime-assembly-not-functionally-accepted",
              "baseline_assembly": str(args.assembly), "baseline_snapshot_sha256": args.snapshot_sha256,
              "runtime_handoff_sha256": args.runtime_handoff_sha256, "runtime_prefix": runtime["prefix"],
              "runtime_readiness_sha256": runtime["readiness"]["sha256"], "changed_runtime_files": changed,
              "baseline_files": before, "files": after,
              "scope": "Fresh complete shipping copy; every runtime occurrence is one producer epoch; original gd04 untouched",
              "pending": ["Native same-root shell/Git/module execution", "Actual Perl prerequisites",
                          "Missing native Perl/SSH/Tcl/editor and complete package admission"]}
    (args.output / "assembly.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Created fresh {len(after)}-file assembly with {len(changed)} coherent runtime copies")


if __name__ == "__main__":
    main()
