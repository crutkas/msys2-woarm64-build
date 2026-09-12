"""Seal the complete private native payload while preserving its package-link gate."""

import importlib
import json
from pathlib import Path

from package_posix import install_data
from readline_chain_inputs import ROOT, SEALS
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import write_json

build = importlib.import_module("build-readline-chain")


def main():
    root = ROOT / "ncurses-01"
    attempt = root / "check-06"
    observation = json.loads((attempt / "native-job.json").read_text())
    launch = json.loads((attempt / "launch.json").read_text())
    log = (attempt / "observed.log").read_text()
    if (observation["parent_raw_exit"] != 1 or observation["timed_out"]
            or not observation["observation_count_matches"] or observation["unrelayed_high_exits"]
            or observation["unobserved_process_ids"]):
        raise ContractError("Unexpected ncurses terminal package-link failure boundary")
    if not log.rstrip().endswith("ln: failed to create symbolic link 'terminfo/terminfo': No such file or directory"):
        raise ContractError("Only the observed duplicate package-link tail is handled")
    if ("1861 entries written" not in log or "make: Leaving directory" not in log
            or any(f"testing {name}" not in log for name in
                   ("color_name.h", "dump_window.h", "edit_field.h", "linedata.h", "parse_rgb.h",
                    "picsmap.h", "popup_msg.h", "test.priv.h", "widechars.h"))):
        raise ContractError("Full native terminfo and actual source-header checks were not completed")
    if launch["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Ncurses launch cohort differs")
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
    install_data(root / "source/COPYING", root / "stage/usr/share/licenses/ncurses/LICENSE")
    files = inventory(root / "stage")
    missing = [name for name in build.required_files("ncurses") if name not in files]
    if missing:
        raise ContractError(f"Incomplete native ncurses profile: {missing}")
    retained = launch["retained_partial_stage"]
    if any(files.get(name) != row for name, row in retained.items()):
        raise ContractError("An already-complete installed ncurses input changed")
    link = root / "stage/usr/lib/terminfo"
    if not link.is_dir() or link.is_symlink() or link.is_junction():
        raise ContractError("Unexpected upstream terminfo compatibility representation")
    link_gate = {
        "path": "usr/lib/terminfo", "required_target": "../share/terminfo",
        "actual": "directory materialized by unmodified upstream install using frozen bootstrap ln",
        "actual_files": inventory(link),
        "canonical_files": inventory(root / "stage/usr/share/terminfo"),
        "qualified_as_symlink": False,
        "remaining_gate": "Provider must create the genuine recipe symlink in package metadata; no privileged local workaround authorized",
    }
    report = {
        "schema": 1, "package": "ncurses", "status": "native-payload-upstream-checks-complete-package-link-gated",
        "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": build.RUNTIME_SHA,
        "upstream_checks_completed": True, "install_payload_complete": True,
        "actual_observer": {"path": str(attempt / "native-job.json"), "sha256": digest(attempt / "native-job.json"),
                            "result": observation},
        "actual_attempt_result": {"path": str(attempt / "result.json"), "sha256": digest(attempt / "result.json")},
        "package_link_gate": link_gate,
        "scope": "Private full-feature library/tool/header/manual/terminfo bytes; not package installation or shared admission",
    }
    write_json(root / "payload-closure.json", report)
    write_json(root / "stage.inventory.json", {
        "schema": 1, "package": "ncurses", "compiler_receipt_sha256": SEALS["compiler"],
        "runtime_sha256": build.RUNTIME_SHA, "files": files, "status": report["status"],
        "closure_result": str(root / "payload-closure.json"),
        "package_link_gate": {k: v for k, v in link_gate.items() if k not in ("actual_files", "canonical_files")},
    })
    print(json.dumps({"stage": str(root / "stage"), "files": len(files),
                      "manifest_sha256": digest(root / "stage.inventory.json"),
                      "status": report["status"]}), flush=True)


if __name__ == "__main__":
    main()
