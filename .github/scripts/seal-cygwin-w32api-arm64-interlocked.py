#!/usr/bin/env python3
"""Seal two reproducible qualified Cygwin w32api header cohorts."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct

RECIPE = Path(__file__).resolve().parent
COMMON = runpy.run_path(str(RECIPE / "cygwin-w32api-common.py"))
NATIVE_OUTPUT = (
    b"native-msys-public-interlocked-ok: 32/64/pointer previous and stored values\n"
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def verify_ref(entry, root=None):
    path = Path(entry["path"]).resolve(strict=True)
    if root is not None and not path.is_relative_to(Path(root).resolve(strict=True)):
        raise ValueError(f"Referenced evidence is outside its run root: {path}")
    if COMMON["sha"](path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
        raise ValueError(f"Referenced evidence changed: {path}")
    return path


def copy_ref(entry, destination, root=None):
    source = verify_ref(entry, root)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return COMMON["ref"](destination)


def relative_ref(path, root):
    path = Path(path).resolve(strict=True)
    root = Path(root).resolve(strict=True)
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": COMMON["sha"](path),
        "bytes": path.stat().st_size,
    }


def require_pairwise_disjoint(paths):
    resolved = [Path(path).resolve(strict=True) for path in paths]
    for index, first in enumerate(resolved):
        for second in resolved[index + 1:]:
            if (
                first == second
                or first.is_relative_to(second)
                or second.is_relative_to(first)
            ):
                raise ValueError(f"Evidence roots overlap: {first} and {second}")


def require_output_disjoint(path, protected):
    path = Path(path).resolve()
    for item in protected:
        item = Path(item).resolve(strict=True)
        if path == item or path.is_relative_to(item) or item.is_relative_to(path):
            raise ValueError(f"Export path overlaps protected input: {item}")


def verify_exact_ref(entry, expected, root):
    path = verify_ref(entry, root)
    if path != Path(expected).resolve(strict=True):
        raise ValueError(f"Evidence reference does not match command output: {path}")
    return path


def function_body(text, function):
    start = text.index(function + ":")
    return text[start:text.index(".seh_endproc", start)]


def verify_baseline_ordering(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for function, helper in (
        ("exchange_public_32", "__aarch64_swp4_sync"),
        ("exchange_public_64", "__aarch64_swp8_sync"),
        ("exchange_public_pointer", "__aarch64_swp8_sync"),
    ):
        body = function_body(text, function)
        if helper not in body or "_acq_rel" in body:
            raise ValueError(f"Sealed baseline ordering differs in {function}")


def verify_outlined_ordering(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for function, helper in (
        ("exchange_public_32", "__aarch64_swp4_acq_rel"),
        ("exchange_public_64", "__aarch64_swp8_acq_rel"),
        ("exchange_public_pointer", "__aarch64_swp8_acq_rel"),
    ):
        if helper not in function_body(text, function):
            raise ValueError(f"Sealed release-capable exchange differs in {function}")
    if re.search(r"__aarch64_swp[48]_sync", text):
        raise ValueError("Sealed acquire-only exchange remains")


def verify_inline_ordering(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for function in (
        "exchange_public_32",
        "exchange_public_64",
        "exchange_public_pointer",
    ):
        body = function_body(text, function)
        if "ldaxr" not in body or "stlxr" not in body:
            raise ValueError(f"Sealed inline exchange differs in {function}")
        if re.search(r"\b(?:ldxr|stxr)\b", body):
            raise ValueError(f"Sealed relaxed inline exchange remains in {function}")


def require_header_trace(path, expected):
    trace = Path(path).read_text(
        encoding="utf-8", errors="replace"
    ).replace("/", "\\").casefold()
    for item in expected:
        if str(Path(item).resolve()).casefold() not in trace:
            raise ValueError(f"Sealed header trace did not select {item}")


def pe_machine(path):
    raw = Path(path).read_bytes()
    if len(raw) < 0x40:
        raise ValueError("Sealed native image is truncated")
    offset = struct.unpack_from("<I", raw, 0x3C)[0]
    if offset + 6 > len(raw) or raw[offset:offset + 4] != b"PE\0\0":
        raise ValueError("Sealed native image lacks a PE signature")
    return struct.unpack_from("<H", raw, offset + 4)[0]


@contextmanager
def environment(values):
    previous = dict(os.environ)
    allowed = {
        name: value
        for name, value in previous.items()
        if name.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE")
    }
    os.environ.clear()
    os.environ.update(allowed)
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def rerun_native_image(observer, image, recorded, proof, sdk, output):
    before = COMMON["ref"](image)
    if before != recorded["image"] or pe_machine(image) != 0xAA64:
        raise ValueError("Native rerun image differs from its recorded ARM64 PE")
    run_root = output
    relay = run_root / "relay-inputs"
    relay.mkdir(parents=True)
    log = run_root / "process.log"
    env = {
        "PATH": str(proof) + os.pathsep + str(sdk / "bin") + os.pathsep
        + str(Path(os.environ["SystemRoot"]) / "System32"),
        "TMP": str(run_root),
        "TEMP": str(run_root),
        "LC_ALL": "C",
        "LANG": "C",
    }
    with environment(env):
        result = observer([str(image)], proof, proof, relay, log, 30)
    after = COMMON["ref"](image)
    native = result.get("native_target_exits", [])
    if (
        before != after
        or not result.get("passed")
        or result.get("timed_out")
        or result.get("parent_raw_exit") != 0
        or not result.get("observation_count_matches")
        or result.get("created_processes") != 1
        or result.get("observed_processes") != 1
        or result.get("unobserved_processes")
        or result.get("unresolved_processes")
        or result.get("unrelayed_high_exits")
        or len(native) != 1
        or Path(native[0]["executable"]).resolve() != image
        or native[0].get("raw_exit") != 0
        or log.read_bytes().replace(b"\r\n", b"\n") != NATIVE_OUTPUT
    ):
        raise ValueError(f"Sealing-time native rerun failed: {image}")
    receipt = {
        "schema": 1,
        "command": [str(image)],
        "imageBefore": before,
        "imageAfter": after,
        "result": result,
        "log": COMMON["ref"](log),
    }
    receipt_path = run_root / "result.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return COMMON["ref"](receipt_path)


def expected_commands(stage, cohort, proof):
    sdk = Path(stage["sdk"]).resolve(strict=True)
    cc = sdk / "bin/gcc.exe"
    fixture = proof / "cygwin-public-interlocked-codegen.c"
    behavior = proof / "cygwin-public-interlocked-native.c"
    old = sdk / "aarch64-pc-cygwin/include/w32api"
    baseline = ["-I", old]
    patched = ["-isysroot", cohort]
    x64 = ["-U__aarch64__", "-U_ARM64_", "-D__x86_64__", "-D_AMD64_"]
    return {
        "target": [cc, "-dumpmachine"],
        "baseline-public-codegen": [
            cc, "-O2", "-S", *baseline, fixture, "-o", proof / "baseline.s",
        ],
        "patched-public-codegen": [
            cc, "-O2", "-S", *patched, fixture, "-o", proof / "patched.s",
        ],
        "patched-outlined-ordering": [
            cc, "-O2", "-S", "-moutline-atomics", *patched, fixture,
            "-o", proof / "patched-outlined.s",
        ],
        "patched-inline-ordering": [
            cc, "-O2", "-S", "-mno-outline-atomics", *patched, fixture,
            "-o", proof / "patched-inline.s",
        ],
        "baseline-header-trace": [
            cc, "-H", "-E", *baseline, fixture, "-o", proof / "baseline-trace.i",
        ],
        "patched-header-trace": [
            cc, "-H", "-E", *patched, fixture, "-o", proof / "patched-trace.i",
        ],
        "baseline-x64-branch": [
            cc, "-E", "-P", *x64, *baseline, fixture, "-o", proof / "baseline-x64.i",
        ],
        "patched-x64-branch": [
            cc, "-E", "-P", *x64, *patched, fixture, "-o", proof / "patched-x64.i",
        ],
        "outlined-build": [
            cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-moutline-atomics", *patched, behavior, "-o", proof / "outlined.exe",
        ],
        "outlined-native": [proof / "outlined.exe"],
        "inline-build": [
            cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-mno-outline-atomics", *patched, behavior, "-o", proof / "inline.exe",
        ],
        "inline-native": [proof / "inline.exe"],
    }


def verify_qualification_runs(stage, result, cohort, proof):
    expected = {
        name: list(map(str, command))
        for name, command in expected_commands(stage, cohort, proof).items()
    }
    runs = result.get("runs", [])
    by_name = {run.get("name"): run for run in runs}
    if len(by_name) != len(runs) or set(by_name) != set(expected):
        raise ValueError("Qualification run set is incomplete or duplicated")
    for name, command in expected.items():
        run = by_name[name]
        process = run.get("result", {})
        if run.get("command") != command:
            raise ValueError(f"Qualification command differs: {name}")
        if (
            not process.get("passed")
            or process.get("timed_out")
            or process.get("parent_raw_exit") != 0
            or not process.get("observation_count_matches")
            or process.get("created_processes", 0) <= 0
            or process.get("observed_processes") != process.get("created_processes")
            or process.get("unobserved_processes")
            or process.get("unresolved_processes")
            or process.get("unrelayed_high_exits")
            or len(process.get("native_target_exits", []))
            != process.get("created_processes")
            or any(record.get("raw_exit") != 0 for record in process["native_target_exits"])
        ):
            raise ValueError(f"Qualification process evidence is incomplete: {name}")
    pe = load(result["peIdentities"]["path"])
    for name in ("outlined", "inline"):
        run = by_name[name + "-native"]["result"]
        if (
            pe.get(name, {}).get("machine") != "0xAA64"
            or len(run["native_target_exits"]) != 1
            or Path(run["native_target_exits"][0]["executable"]).resolve()
            != Path(pe[name]["image"]["path"]).resolve()
            or run["native_target_exits"][0]["raw_exit"] != 0
        ):
            raise ValueError(f"Native run is not bound to its PE identity: {name}")
    return by_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root-a", "root-b", "proof-a", "proof-b", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--overlay-proof", required=True, type=Path)
    args = parser.parse_args()
    roots = [args.root_a.resolve(strict=True), args.root_b.resolve(strict=True)]
    proofs = [args.proof_a.resolve(strict=True), args.proof_b.resolve(strict=True)]
    if roots[0] == roots[1] or proofs[0] == proofs[1]:
        raise ValueError("Two distinct cohort and proof roots are required")
    stages = [load(root / "stage.json") for root in roots]
    manifests = [load(root / "manifest.json") for root in roots]
    results = [load(proof / "result.json") for proof in proofs]
    overlay_proof_root = args.overlay_proof.resolve(strict=True)
    overlay_proof = load(overlay_proof_root / "result.json")
    overlay_receipts = [
        load(Path(stage["sourceOverlayReceipt"]["path"])) for stage in stages
    ]
    overlay_roots = [Path(receipt["output"]).resolve(strict=True) for receipt in overlay_receipts]
    archives = [
        Path(receipt["sourceArchive"]["path"]).resolve(strict=True)
        for receipt in overlay_receipts
    ]
    source_roots = [
        Path(receipt["source"]).resolve(strict=True) for receipt in overlay_receipts
    ]
    if overlay_roots[0] == overlay_roots[1] or archives[0] == archives[1]:
        raise ValueError("Two distinct overlay and source-archive roots are required")
    require_pairwise_disjoint(roots + proofs + overlay_roots + [overlay_proof_root])
    if (
        overlay_proof.get("status") != "v12-cygwin-w32api-overlay-controls-qualified"
        or Path(overlay_proof.get("output", "")).resolve() != overlay_proof_root
    ):
        raise ValueError("Overlay lifecycle proof is incomplete or unbound")
    overlay_runs = overlay_proof.get("runs", [])
    overlay_by_case = {run.get("case"): run for run in overlay_runs}
    if (
        len(overlay_by_case) != len(overlay_runs)
        or set(overlay_by_case)
        != {"fresh", "idempotent", "tracked-drift", "untracked-drift"}
        or overlay_by_case["fresh"].get("exit") != 0
        or overlay_by_case["idempotent"].get("exit") != 0
        or overlay_by_case["tracked-drift"].get("exit") == 0
        or overlay_by_case["untracked-drift"].get("exit") == 0
    ):
        raise ValueError("Overlay lifecycle run set is incomplete")
    for name, path in (
        ("test", RECIPE / "test-cygwin-w32api-overlay.py"),
        ("prepare", RECIPE / "prepare-cygwin-w32api-arm64-overlay.py"),
        ("common", RECIPE / "cygwin-w32api-common.py"),
        ("sourceLock", RECIPE / "cygwin-w32api-source-lock.json"),
    ):
        if overlay_proof["recipeInputs"][name]["sha256"] != COMMON["sha"](path):
            raise ValueError(f"Overlay lifecycle recipe differs: {name}")
    for index in range(2):
        if results[index]["status"] != "v12-cygwin-public-interlocked-header-successor-qualified":
            raise ValueError("Public API qualification is incomplete")
        runs_by_name = verify_qualification_runs(
            stages[index], results[index], roots[index], proofs[index]
        )
        if Path(stages[index]["cohortRoot"]).resolve() != roots[index]:
            raise ValueError("Stage is not bound to its cohort root")
        if Path(stages[index]["include"]).resolve() != roots[index] / "include":
            raise ValueError("Stage include root differs")
        if Path(results[index]["output"]).resolve() != proofs[index]:
            raise ValueError("Qualification result is not bound to its proof root")
        if Path(results[index]["cohortRoot"]).resolve() != roots[index]:
            raise ValueError("Qualification result is not bound to its cohort root")
        if Path(results[index]["stage"]["path"]).resolve() != roots[index] / "stage.json":
            raise ValueError("Qualification stage path differs")
        if results[index]["stage"]["sha256"] != COMMON["sha"](roots[index] / "stage.json"):
            raise ValueError("Qualification used another header cohort")
        if Path(stages[index]["manifest"]["path"]).resolve() != roots[index] / "manifest.json":
            raise ValueError("Stage manifest path differs")
        verify_ref(stages[index]["manifest"], roots[index])
        if Path(stages[index]["sourceOverlayReceipt"]["path"]).resolve() != (
            overlay_roots[index].with_name(overlay_roots[index].name + ".source.json")
        ):
            raise ValueError("Stage overlay receipt is not bound to its overlay root")
        verify_ref(stages[index]["sourceOverlayReceipt"])
        if COMMON["inventory"](roots[index] / "include") != manifests[index]["files"]:
            raise ValueError("Qualified private header cohort changed")
        if Path(stages[index]["sourceOverlayReceipt"]["path"]).resolve() == Path(
            stages[1 - index]["sourceOverlayReceipt"]["path"]
        ).resolve():
            raise ValueError("Two distinct source-overlay receipts are required")
        if stages[index]["sourceLock"]["sha256"] != COMMON["sha"](
            RECIPE / "cygwin-w32api-source-lock.json"
        ):
            raise ValueError("Stage source lock differs from the sealing recipe")
        for name, path in (
            ("stage", RECIPE / "stage-cygwin-w32api-arm64-headers.py"),
            ("common", RECIPE / "cygwin-w32api-common.py"),
        ):
            if stages[index]["recipeInputs"][name]["sha256"] != COMMON["sha"](path):
                raise ValueError(f"Stage recipe differs: {name}")
        if results[index]["observer"]["sha256"] != COMMON["sha"](RECIPE / "native-job.py"):
            raise ValueError("Qualification observer differs")
        for name, path in (
            ("test", RECIPE / "test-cygwin-w32api-arm64-interlocked.py"),
            ("common", RECIPE / "cygwin-w32api-common.py"),
            ("nativeFixture", RECIPE / "cygwin-public-interlocked-native.c"),
            ("publicFixture", RECIPE / "cygwin-public-interlocked-codegen.c"),
            ("sourceLock", RECIPE / "cygwin-w32api-source-lock.json"),
        ):
            if results[index]["recipeInputs"][name]["sha256"] != COMMON["sha"](path):
                raise ValueError(f"Qualification recipe differs: {name}")
        if results[index]["publicFixtureSource"]["sha256"] != COMMON["sha"](
            RECIPE / "cygwin-public-interlocked-codegen.c"
        ):
            raise ValueError("Public fixture source differs")
        verify_ref(results[index]["publicFixture"], proofs[index])
        baseline_codegen = verify_exact_ref(
            results[index]["codegen"]["baseline"],
            proofs[index] / "baseline.s",
            proofs[index],
        )
        patched_codegen = verify_exact_ref(
            results[index]["codegen"]["patched"],
            proofs[index] / "patched.s",
            proofs[index],
        )
        outlined_codegen = verify_exact_ref(
            results[index]["codegen"]["patchedModes"]["outlined"],
            proofs[index] / "patched-outlined.s",
            proofs[index],
        )
        inline_codegen = verify_exact_ref(
            results[index]["codegen"]["patchedModes"]["inline"],
            proofs[index] / "patched-inline.s",
            proofs[index],
        )
        verify_baseline_ordering(baseline_codegen)
        verify_outlined_ordering(patched_codegen)
        verify_outlined_ordering(outlined_codegen)
        verify_inline_ordering(inline_codegen)
        target_log = verify_ref(runs_by_name["target"]["log"], proofs[index])
        if target_log.read_bytes().strip() != b"aarch64-pc-cygwin":
            raise ValueError("Sealed compiler target evidence differs")
        sdk = Path(stages[index]["sdk"]).resolve(strict=True)
        require_header_trace(
            verify_ref(runs_by_name["baseline-header-trace"]["log"], proofs[index]),
            (
                sdk / "aarch64-pc-cygwin/include/w32api/windows.h",
                sdk / "aarch64-pc-cygwin/include/w32api/psdk_inc/intrin-impl.h",
            ),
        )
        require_header_trace(
            verify_ref(runs_by_name["patched-header-trace"]["log"], proofs[index]),
            (
                roots[index] / "include/windows.h",
                roots[index] / "include/psdk_inc/intrin-impl.h",
            ),
        )
        for name in ("outlined-native", "inline-native"):
            native_log = verify_ref(runs_by_name[name]["log"], proofs[index])
            if native_log.read_bytes().replace(b"\r\n", b"\n") != NATIVE_OUTPUT:
                raise ValueError(f"Sealed native behavior output differs: {name}")
        baseline_x64 = re.sub(
            rb"\s+", b"", (proofs[index] / "baseline-x64.i").read_bytes()
        )
        patched_x64 = re.sub(
            rb"\s+", b"", (proofs[index] / "patched-x64.i").read_bytes()
        )
        if baseline_x64 != patched_x64:
            raise ValueError(f"Sealed x64 branch changed in proof: {proofs[index]}")
        verify_ref(results[index]["peIdentities"], proofs[index])
        verify_ref(results[index]["runtimeExecuted"], proofs[index])
        if (
            results[index]["runtimeSource"]["sha256"]
            != results[index]["runtimeExecuted"]["sha256"]
        ):
            raise ValueError("Executed runtime differs from its pinned source")
        for run in results[index]["runs"]:
            verify_ref(run["log"], proofs[index])
    if (
        manifests[0]["files"] != manifests[1]["files"]
        or manifests[0]["baselineFiles"] != manifests[1]["baselineFiles"]
        or manifests[0]["changedFiles"] != manifests[1]["changedFiles"]
    ):
        raise ValueError("Independent header cohorts are not byte-identical")
    if (
        overlay_receipts[0]["files"] != overlay_receipts[1]["files"]
        or overlay_receipts[0]["sourceArchive"]["sha256"]
        != overlay_receipts[1]["sourceArchive"]["sha256"]
    ):
        raise ValueError("Independent source overlays are not byte-identical")
    for overlay in overlay_receipts:
        overlay_root = Path(overlay["output"]).resolve(strict=True)
        if COMMON["inventory"](overlay_root) != overlay["files"]:
            raise ValueError("Prepared overlay changed")
        verify_ref(overlay["sourceArchive"])
        if overlay["sourceLock"]["sha256"] != COMMON["sha"](
            RECIPE / "cygwin-w32api-source-lock.json"
        ):
            raise ValueError("Prepared overlay source lock differs")
        for name, path in (
            ("prepare", RECIPE / "prepare-cygwin-w32api-arm64-overlay.py"),
            ("common", RECIPE / "cygwin-w32api-common.py"),
        ):
            if overlay["recipeInputs"][name]["sha256"] != COMMON["sha"](path):
                raise ValueError(f"Overlay preparation recipe differs: {name}")
        if len(overlay.get("patchEvidence", [])) != 2:
            raise ValueError("Overlay patch-application evidence is incomplete")
        for patch, evidence_entry in zip(
            load(RECIPE / "cygwin-w32api-source-lock.json")["patches"],
            overlay["patchEvidence"],
        ):
            if evidence_entry["canonicalPatch"]["sha256"] != patch["sha256"]:
                raise ValueError("Canonical applied patch differs")
            for entry in evidence_entry.values():
                verify_ref(entry)
    for first, second in zip(
        overlay_receipts[0]["patchEvidence"],
        overlay_receipts[1]["patchEvidence"],
    ):
        if {
            name: entry["sha256"] for name, entry in first.items()
        } != {
            name: entry["sha256"] for name, entry in second.items()
        }:
            raise ValueError("Independent patch-application evidence differs")
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Use a fresh immutable export path")
    require_output_disjoint(
        out,
        roots
        + proofs
        + overlay_roots
        + archives
        + source_roots
        + [overlay_proof_root, RECIPE]
        + [Path(stage["sdk"]).resolve(strict=True) for stage in stages],
    )
    out.mkdir(parents=True)
    cohort = out / "cohort"
    shutil.copytree(roots[0] / "include", cohort / "include")
    shutil.copy2(roots[0] / "manifest.json", cohort / "manifest.json")
    if (
        load(cohort / "manifest.json") != manifests[0]
        or COMMON["inventory"](cohort / "include") != manifests[0]["files"]
    ):
        raise ValueError("Exported header cohort differs from qualified input")
    evidence = out / "evidence"
    evidence.mkdir()
    runtime_evidence = evidence / "msys-2.0.dll"
    shutil.copy2(results[0]["runtimeExecuted"]["path"], runtime_evidence)
    if COMMON["sha"](runtime_evidence) != results[1]["runtimeExecuted"]["sha256"]:
        raise ValueError("Independent proofs did not execute the same runtime")
    sdk_evidence = evidence / "sdk"
    sdk_inventory_source = {
        "path": stages[0]["sdkFullInventory"]["path"],
        "sha256": stages[0]["sdkFullInventory"]["sha256"],
        "bytes": Path(stages[0]["sdkFullInventory"]["path"]).stat().st_size,
    }
    sdk_inventory_path = sdk_evidence / "full-inventory.json"
    copy_ref(
        sdk_inventory_source, sdk_evidence / "full-inventory.json"
    )
    source_evidence = evidence / "source"
    source_archive_path = source_evidence / "pinned-source.tar"
    copy_ref(overlay_receipts[0]["sourceArchive"], source_archive_path)
    patch_evidence = []
    for index, item in enumerate(overlay_receipts[0]["patchEvidence"], start=1):
        patch_dir = source_evidence / f"patch-{index}"
        retained = {}
        for name, entry in item.items():
            suffix = ".patch" if name == "canonicalPatch" else ".log"
            retained[name] = copy_ref(entry, patch_dir / (name + suffix))
        patch_evidence.append(retained)
    codegen_evidence = evidence / "codegen"
    codegen_evidence.mkdir()
    deterministic_codegen = {
        "baseline": results[0]["codegen"]["baseline"],
        "patched": results[0]["codegen"]["patched"],
        "outlined": results[0]["codegen"]["patchedModes"]["outlined"],
        "inline": results[0]["codegen"]["patchedModes"]["inline"],
    }
    comparison_codegen = {
        "baseline": results[1]["codegen"]["baseline"],
        "patched": results[1]["codegen"]["patched"],
        "outlined": results[1]["codegen"]["patchedModes"]["outlined"],
        "inline": results[1]["codegen"]["patchedModes"]["inline"],
    }
    retained_codegen = {}
    for name, entry in deterministic_codegen.items():
        if entry["sha256"] != comparison_codegen[name]["sha256"]:
            raise ValueError(f"Independent codegen differs: {name}")
        retained_codegen[name] = copy_ref(entry, codegen_evidence / (name + ".s"), proofs[0])
    for name in ("baseline-x64.i", "patched-x64.i"):
        first = proofs[0] / name
        second = proofs[1] / name
        if COMMON["sha"](first) != COMMON["sha"](second):
            raise ValueError(f"Independent preprocessing differs: {name}")
        copy_ref(
            {"path": str(first), "sha256": COMMON["sha"](first), "bytes": first.stat().st_size},
            codegen_evidence / name,
            proofs[0],
        )
    local = out / "local-evidence"
    local.mkdir()
    observer = runpy.run_path(str(RECIPE / "native-job.py"))["run"]
    sealing_native_reruns = {}
    for index, label in enumerate(("run-a", "run-b")):
        overlay_dir = local / ("overlay-" + label[-1])
        copy_ref(stages[index]["sourceOverlayReceipt"], overlay_dir / "receipt.json")
        run_dir = local / label
        copy_ref(
                {
                    "path": str(roots[index] / "stage.json"),
                    "sha256": COMMON["sha"](roots[index] / "stage.json"),
                    "bytes": (roots[index] / "stage.json").stat().st_size,
                },
                run_dir / "stage.json",
                roots[index],
            )
        copy_ref(
                {
                    "path": str(proofs[index] / "result.json"),
                    "sha256": COMMON["sha"](proofs[index] / "result.json"),
                    "bytes": (proofs[index] / "result.json").stat().st_size,
                },
                run_dir / "result.json",
                proofs[index],
            )
        copy_ref(results[index]["peIdentities"], run_dir / "pe-identities.json", proofs[index])
        copy_ref(results[index]["publicFixture"], run_dir / "public-fixture.c", proofs[index])
        for run in results[index]["runs"]:
            copy_ref(
                run["log"], run_dir / "logs" / (run["name"] + ".log"), proofs[index]
            )
        pe_identities = load(results[index]["peIdentities"]["path"])
        for name in ("outlined", "inline"):
            recorded = pe_identities[name]
            if recorded["machine"] != "0xAA64":
                raise ValueError("Recorded native image is not ARM64 PE")
            image = verify_ref(recorded["image"], proofs[index])
            if image != proofs[index] / (name + ".exe"):
                raise ValueError("Recorded native image path differs")
            if pe_machine(image) != 0xAA64:
                raise ValueError("Recorded native image bytes are not ARM64 PE")
            rerun_name = label + "-" + name
            sealing_native_reruns[rerun_name] = rerun_native_image(
                observer,
                image,
                recorded,
                proofs[index],
                Path(stages[index]["sdk"]).resolve(strict=True),
                local / "sealing-native-reruns" / rerun_name,
            )
            copy_ref(
                recorded["image"],
                run_dir / (name + ".exe"),
                proofs[index],
            )
        for name in (
            "baseline-x64.i",
            "patched-x64.i",
            "baseline-trace.i",
            "patched-trace.i",
        ):
            source = proofs[index] / name
            copy_ref(
                {
                    "path": str(source),
                    "sha256": COMMON["sha"](source),
                    "bytes": source.stat().st_size,
                },
                run_dir / "preprocessed" / name,
                proofs[index],
            )
    copy_ref(stages[0]["sdkProvenance"], local / "sdk" / "provenance.json")
    copy_ref(stages[0]["sdkToolReceipt"], local / "sdk" / "tool-receipt.json")
    copy_ref(
            {
                "path": str(overlay_proof_root / "result.json"),
                "sha256": COMMON["sha"](overlay_proof_root / "result.json"),
                "bytes": (overlay_proof_root / "result.json").stat().st_size,
            },
            local / "overlay-controls" / "result.json",
            overlay_proof_root,
        )
    for path in sorted(overlay_proof_root.glob("*.stdout")) + sorted(
        overlay_proof_root.glob("*.stderr")
    ):
        copy_ref(
            {
                "path": str(path),
                "sha256": COMMON["sha"](path),
                "bytes": path.stat().st_size,
            },
            local / "overlay-controls" / path.name,
            overlay_proof_root,
        )
    recipes = out / "recipes"
    recipes.mkdir()
    recipe_names = (
        "cygwin-w32api-source-lock.json",
        "cygwin-public-interlocked-codegen.c",
        "cygwin-w32api-arm64-abi.patch",
        "cygwin-w32api-arm64-interlocked-exchange-ordering.patch",
        "cygwin-w32api-common.py",
        "prepare-cygwin-w32api-arm64-overlay.py",
        "stage-cygwin-w32api-arm64-headers.py",
        "test-cygwin-w32api-arm64-interlocked.py",
        "test-cygwin-w32api-overlay.py",
        "test-cygwin-w32api-source-lock.py",
        "seal-cygwin-w32api-arm64-interlocked.py",
        "cygwin-public-interlocked-native.c",
        "native-job.py",
    )
    for name in recipe_names:
        shutil.copy2(RECIPE / name, recipes / name)
    expected_exit_contracts = RECIPE / "expected-exit-contracts.json"
    if expected_exit_contracts.is_file():
        shutil.copy2(expected_exit_contracts, recipes / expected_exit_contracts.name)
    local_manifest = {
        path.relative_to(local).as_posix(): {
            "sha256": COMMON["sha"](path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(
            (path for path in local.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(local).as_posix(),
        )
    }
    (local / "manifest.json").write_text(
        json.dumps({"schema": 1, "files": local_manifest}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    portable_patch_evidence = [
        {
            name: relative_ref(entry["path"], out)
            for name, entry in patch.items()
        }
        for patch in patch_evidence
    ]
    report = {
        "schema": 1,
        "status": "qualified-local-v12-cygwin-w32api-interlocked-successor",
        "target": "aarch64-pc-cygwin",
        "source": stages[0]["source"],
        "sourceLock": relative_ref(recipes / "cygwin-w32api-source-lock.json", out),
        "sourceArchive": relative_ref(source_archive_path, out),
        "sourcePatchEvidence": portable_patch_evidence,
        "sourceOverlaySummary": {
            "independentRuns": 2,
            "files": len(overlay_receipts[0]["files"]),
            "inventorySHA256": hashlib.sha256(
                json.dumps(
                    overlay_receipts[0]["files"],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        },
        "sdkFullInventory": {
            **relative_ref(sdk_inventory_path, out),
            "fileCount": stages[0]["sdkFullInventory"]["fileCount"],
        },
        "existingAbiOverlay": stages[0]["previousCygwinABIOverlay"],
        "cohort": "cohort",
        "include": "cohort/include",
        "header": relative_ref(cohort / "include/psdk_inc/intrin-impl.h", out),
        "manifest": relative_ref(cohort / "manifest.json", out),
        "files": len(manifests[0]["files"]),
        "changedFiles": manifests[0]["changedFiles"],
        "reproducibility": {
            "independentCohorts": 2,
            "independentQualificationRuns": 2,
            "runsPerQualification": [len(result["runs"]) for result in results],
            "overlayLifecycle": overlay_proof["status"],
            "observerCompleteness": all(
                run["result"]["observation_count_matches"]
                and not run["result"]["unobserved_processes"]
                and not run["result"]["unresolved_processes"]
                for result in results
                for run in result["runs"]
            ),
        },
        "localEvidence": {
            "directory": "local-evidence",
            "manifest": "local-evidence/manifest.json",
            "scope": (
                "Machine-local raw receipts, commands, traces, logs, and nonreproducible "
                "PE link outputs retained for audit but excluded from the reproducible manifest."
            ),
        },
        "publicFixture": relative_ref(recipes / "cygwin-public-interlocked-codegen.c", out),
        "publicFixtureProvenance": load(
            recipes / "cygwin-w32api-source-lock.json"
        )["public_probe"]["provenance"],
        "baselineCodegen": relative_ref(retained_codegen["baseline"]["path"], out),
        "patchedCodegen": {
            name: relative_ref(entry["path"], out)
            for name, entry in retained_codegen.items()
            if name != "baseline"
        },
        "x64Control": results[0]["x64Control"],
        "runtimeSourceIdentity": {
            "sha256": results[0]["runtimeSource"]["sha256"],
            "bytes": results[0]["runtimeSource"]["bytes"],
        },
        "runtimeExecuted": relative_ref(runtime_evidence, out),
        "observer": relative_ref(recipes / "native-job.py", out),
        "consumerSelection": {
            "options": ["-isysroot", "<export>/cohort"],
            "reason": results[0]["headerSelection"]["reason"],
        },
        "consumerBoundary": (
            "Use the exact measured -isysroot full header cohort with root06's native "
            "aarch64-pc-cygwin compiler, or install the locked overlay into a new complete "
            "SDK. Rebuild consumers under explicit new identities."
        ),
        "limits": (
            "Separate from the admitted 70d63 native MinGW provider. No root06/runtime907/"
            "compiler/Perl/OpenSSL mutation or rebuild, no forced ARM intrinsic macros, "
            "no weak-memory stress claim, and no x64 execution claim."
        ),
    }
    handoff = out / "handoff.json"
    handoff.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    export_manifest = {
        path.relative_to(out).as_posix(): {
            "sha256": COMMON["sha"](path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(
            (
                path
                for path in out.rglob("*")
                if path.is_file() and not path.is_relative_to(local)
            ),
            key=lambda path: path.relative_to(out).as_posix(),
        )
    }
    out.with_name(out.name + ".manifest.json").write_text(
        json.dumps({"schema": 1, "files": export_manifest}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(handoff)


if __name__ == "__main__":
    main()
