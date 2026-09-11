"""Bind the maintained negative-hook fixture through the published observer's base-contract API."""

import contextlib
import copy
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from artifact import ArtifactError, sha256

CASE = "msys-git-hook-negative-v1"
PHASE_SHA256 = "5107e3cdb1b0a9a784a37209fefb9f58f8bc9c71a91912da1c87e95e71db5af8"
HOOK_BYTES = b'#!/bin/sh\nprintf "negative-hook-executed\\n" > .git/negative-hook-observed\nexit 73\n'


def msys_drive_path(path):
    path = Path(path).resolve()
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ArtifactError("This fixture requires the admitted drive-letter cygdrive profile")
    return "/" + path.drive[0].lower() + "/" + path.relative_to(path.anchor).as_posix()


def make_binding(root, phase, behavior, work, helper_source_sha256):
    if sha256(phase) != PHASE_SHA256:
        raise ArtifactError("The maintained negative-hook phase source changed")
    expected_fstab = Path(__file__).parent / "payload/etc/fstab"
    if sha256(root / "etc/fstab") != sha256(expected_fstab):
        raise ArtifactError("The fixture's exact cygdrive profile changed")
    paths = {"phase": phase, "behavior": behavior, "adapter": Path(__file__),
             "helper": root / "usr/bin/msys-exit-contract.exe",
             "bash": root / "usr/bin/bash.exe", "sh": root / "usr/bin/sh.exe",
             "git": root / "mingwarm64/bin/git.exe", "runtime": root / "usr/bin/msys-2.0.dll"}
    assets = {name: {"path": str(path.resolve()), "sha256": sha256(path)} for name, path in paths.items()}
    argv = ["/usr/bin/msys-exit-contract.exe", "--spawn", CASE, "1", "/usr/bin/bash",
            phase.as_posix(), "/mingwarm64/bin/git.exe", msys_drive_path(work / "source")]
    contract = {"encoding": "msys-posix-wait-status-v1", "probe_source_sha256": PHASE_SHA256,
                "child_image_name": "bash.exe", "image_sha256": assets["bash"]["sha256"],
                "parent_image_name": "msys-exit-contract.exe",
                "parent_image_sha256": assets["helper"]["sha256"],
                "parent_raw_exit": 0, "raw_exit": 256, "portable_exit": 1}
    return {"schema": 2, "contracts": {CASE: contract},
            "fixture": {"assets": assets, "argv": argv, "helper_source_sha256": helper_source_sha256,
                        "hook_sha256": hashlib.sha256(HOOK_BYTES).hexdigest(),
                        "scope": "Controller-bound source/argv plus observed process generations and actual hook/HEAD evidence; not kernel command-line capture or a general exit decoder"}}


@contextlib.contextmanager
def locked_inputs(paths):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    handles = []
    try:
        for path in paths:
            handle = create(str(path), 0x80000000, 1, None, 3, 0x80, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            if not close(handle):
                raise ctypes.WinError(ctypes.get_last_error())


def check_inputs(binding):
    for role, item in binding["fixture"]["assets"].items():
        if sha256(item["path"]) != item["sha256"]:
            raise ArtifactError(f"Hook fixture input changed: {role}")


def identity(record):
    return record["pid"], record["created"]


def parent_identity(record):
    return record.get("parent_pid"), record.get("parent_created")


def check_causality(observation, binding, argv, proof, hook_sha256):
    if argv != binding["fixture"]["argv"]:
        raise ArtifactError("The actual helper argv differs from the bound fixture")
    if (len(proof) != 3 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", proof[0])
            or proof[0] != proof[1] or proof[2] != "negative-hook-executed"):
        raise ArtifactError("The expected hook did not run with an unchanged HEAD")
    if hook_sha256 != hashlib.sha256(HOOK_BYTES).hexdigest():
        raise ArtifactError("The executed hook source differs from the maintained fixture")
    qualified = [row for row in observation["expected_probe_exits"] if row["expected_exit_contract"] == CASE]
    if len(qualified) != 1 or qualified[0]["raw_exit"] != 256 or qualified[0]["portable_exit"] != 1:
        raise ArtifactError("The exact negative phase has no unique generation-bound contract")
    phase = qualified[0]
    records = observation["native_target_exits"]
    parents = [row for row in records if identity(row) == parent_identity(phase)]
    if len(parents) != 1 or parents[0]["raw_exit"] != 0:
        raise ArtifactError("The qualified helper did not confirm normal POSIX exit 1")
    git_path = Path(binding["fixture"]["assets"]["git"]["path"])
    children = [row for row in records if parent_identity(row) == identity(phase)
                and Path(row["executable"]).resolve() == git_path]
    if len(children) != 1 or children[0]["raw_exit"] != 1:
        raise ArtifactError("The phase has no exact native Git child exiting 1")
    git = children[0]
    sh_path = Path(binding["fixture"]["assets"]["sh"]["path"])
    hooks = [row for row in records if parent_identity(row) == identity(git)
             and Path(row["executable"]).resolve() == sh_path]
    if len(hooks) != 1 or hooks[0]["raw_exit"] != 73:
        raise ArtifactError("The Git child has no exact native hook process exiting 73")
    return {"phase": phase, "git": git, "hook": hooks[0], "head_before": proof[0],
            "head_after": proof[1], "hook_sha256": hook_sha256, "argv": argv}


def read_causality(work):
    data = (work / "negative-hook-argv.bin").read_bytes()
    if not data.endswith(b"\0"):
        raise ArtifactError("The fixture argv capture is incomplete")
    return (data[:-1].decode("utf-8").split("\0"),
            (work / "negative-hook-proof.txt").read_text().splitlines(),
            sha256(work / "negative-hook-source.sh"))


def require_exact_delta(module, records, relays, contracts, target):
    without_hook = {name: value for name, value in contracts.items() if name != CASE}
    before = {identity(row) for row in module.unprotected_native_exits(
        copy.deepcopy(records), copy.deepcopy(relays), without_hook)}
    after = {identity(row) for row in module.unprotected_native_exits(
        copy.deepcopy(records), copy.deepcopy(relays), contracts)}
    if before - after != {target} or after - before:
        raise ArtifactError("The hook contract protects a generation other than its exact validated phase")
    return {"newly_protected_generations": [{"pid": target[0], "created": target[1]}],
            "unprotected_without_hook": len(before), "unprotected_with_hook": len(after)}


def refusal_controls(driver, observation, binding, relays, contracts, causality):
    """Challenge the unchanged published matcher using copies of the fresh captured records."""
    spec = importlib.util.spec_from_file_location("published_mvp_native_job", driver / "native-job.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = observation["native_target_exits"]
    target = identity(causality["phase"])
    delta = require_exact_delta(module, records, relays, contracts, target)
    results = []

    def rejected(name, changed_records=None, changed_relays=None, changed_contracts=None, rejected_id=None):
        unprotected = module.unprotected_native_exits(
            copy.deepcopy(records if changed_records is None else changed_records),
            copy.deepcopy(relays if changed_relays is None else changed_relays),
            copy.deepcopy(contracts if changed_contracts is None else changed_contracts))
        passed = (rejected_id or target) in {identity(row) for row in unprotected}
        results.append({"name": name, "passed": passed})
        if not passed:
            raise ArtifactError(f"Published observer refusal control failed: {name}")

    rejected("uncontracted-negative-phase", changed_contracts={})
    for key, value in (("probe_source_sha256", "0" * 64), ("image_sha256", "0" * 64),
                       ("parent_image_sha256", "0" * 64), ("parent_raw_exit", 1),
                       ("portable_exit", 7), ("raw_exit", 65536)):
        changed = copy.deepcopy(contracts)
        changed[CASE][key] = value
        rejected("mismatched-contract-" + key, changed_contracts=changed)
    changed = copy.deepcopy(relays)
    moved = changed.pop(target)
    changed[(target[0], target[1] + 1)] = moved
    rejected("stale-child-generation", changed_relays=changed)
    changed = copy.deepcopy(relays)
    for row in changed[target]:
        row["parent_created"] += 1
    rejected("stale-parent-generation", changed_relays=changed)
    changed = copy.deepcopy(relays)
    for row in changed[target]:
        row["probe_source_sha256"] = binding["fixture"]["helper_source_sha256"]
    rejected("old-helper-source-token-is-not-new-phase-proof", changed_relays=changed)
    for raw in (1536, 65536, 0xC0000005, 0xC0000409):
        changed = copy.deepcopy(records)
        next(row for row in changed if identity(row) == target)["raw_exit"] = raw
        rejected(f"unexpected-raw-{raw}", changed_records=changed)
    changed = copy.deepcopy(records)
    other = copy.deepcopy(next(row for row in records if identity(row) == target))
    other["pid"] = max(row["pid"] for row in records) + 1
    other["created"] += 1
    changed.append(other)
    rejected("unrelated-bash-256-generation", changed_records=changed, rejected_id=identity(other))
    descendant = copy.deepcopy(other)
    descendant["parent_pid"], descendant["parent_created"] = target
    try:
        require_exact_delta(module, records + [descendant], relays, contracts, target)
    except ArtifactError:
        results.append({"name": "inherited-descendant-256-allowance-rejected", "passed": True})
    else:
        raise ArtifactError("An uncontracted high-exit descendant inherited the hook's protection")
    changed = copy.deepcopy(records)
    next(row for row in changed if identity(row) == target)["executable"] = causality["git"]["executable"]
    rejected("foreign-git-image-raw-256", changed_records=changed)
    argv, proof, hook_sha = causality["argv"], [causality["head_before"], causality["head_after"],
                                             "negative-hook-executed"], causality["hook_sha256"]
    bad_graph = copy.deepcopy(observation)
    next(row for row in bad_graph["native_target_exits"] if identity(row) == identity(causality["hook"]))["raw_exit"] = 0
    checks = [
        ("changed-argv", observation, argv[:-1] + ["different-repo"], proof, hook_sha),
        ("changed-head", observation, argv, [proof[0], "0" * 40, proof[2]], hook_sha),
        ("missing-marker", observation, argv, [proof[0], proof[1], "missing"], hook_sha),
        ("changed-hook-source", observation, argv, proof, "0" * 64),
        ("wrong-hook-terminal-code", bad_graph, argv, proof, hook_sha),
    ]
    for name, observed, arguments, observed_proof, observed_hook in checks:
        try:
            check_causality(observed, binding, arguments, observed_proof, observed_hook)
        except ArtifactError:
            results.append({"name": name, "passed": True})
        else:
            raise ArtifactError(f"Fixture causality refusal control failed: {name}")
    return {"exact_delta": delta, "cases": results}
