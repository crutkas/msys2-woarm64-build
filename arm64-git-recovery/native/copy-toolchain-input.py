"""Make a byte-identical, space-free toolchain input for libtool's verbose-link parser."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory, relative_path, verify_tree


def verify_cohort_delta(base, successor, replacements, additions):
    changed = {name for name in base.keys() & successor.keys() if base[name] != successor[name]}
    if (base.keys() - successor.keys() or changed != set(replacements) or
            successor.keys() - base.keys() != set(additions)):
        raise ContractError("Compiler delta changed files outside its explicit qualified boundary")


def cmocka_base(handoff, source, expected, receipt):
    if receipt is None:
        raise ContractError("The CMocka compiler delta requires its original coherent MSYS copy receipt")
    base = json.loads(Path(receipt).read_text(encoding="utf-8"))
    original = Path(base["prefix"])
    verify_tree(original, receipt)
    cohort = json.loads(Path(handoff["stagedPrefix"]["inventory"]).read_text(encoding="utf-8"))
    if (base.get("status") != "byte-identical-relocated-input-not-new-qualification" or
            base.get("source_target", {}).get("Triple") != "aarch64-pc-cygwin" or
            Path(cohort["oldPrefix"]).resolve() != original.resolve()):
        raise ContractError("CMocka successor does not identify this coherent MSYS predecessor")
    replacements = {
        "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe",
        "bin/aarch64-pc-cygwin-gcc.exe", "bin/aarch64-pc-cygwin-gcc-15.0.1.exe",
        "bin/aarch64-pc-cygwin-cpp.exe"}
    if {name.replace("\\", "/") for name in handoff["stagedPrefix"]["replaced"]} != replacements:
        raise ContractError("Unexpected CMocka compiler replacement scope")
    proof_root = "share/toolchain/cmocka-gcc-producer/"
    proof_hashes = {proof_root + name: sha for name, sha in handoff["source"]["patchIdentities"].items()}
    proof_hashes[proof_root + "source-lock.json"] = handoff["source"]["sourceLockFileSha256"]
    if set(proof_hashes) != {proof_root + name for name in (
            "gcc-arm64-seh-prepost-index-save.patch", "gcc-arm64-seh-sp-direct-save.patch",
            "gcc-arm64-seh-stackalloc-reg.patch", "gcc-emutls-returns-twice-safe-insert.patch",
            "source-lock.json")}:
        raise ContractError("Unexpected CMocka compiler provenance files")
    verify_cohort_delta({name: row["sha256"] for name, row in base["files"].items()},
                        expected, replacements, proof_hashes)
    for name, sha in proof_hashes.items():
        if expected.get(name) != sha or digest(source / name) != sha:
            raise ContractError("CMocka compiler source proof changed")
    verify_jump_qualification(source, base["source_jump_buffer_qualification"], base["source_runtime_pairing"])
    verify_ucontext_qualification(source, base["source_ucontext_qualification"])
    return base


def protected_delta_base(handoff, source, expected, receipt, frontend):
    if (receipt is None or digest(receipt) != handoff["base_receipt_sha256"]
            or digest(handoff["base_receipt"]["path"]) != handoff["base_receipt"]["sha256"]
            or handoff["base_receipt"]["sha256"] != handoff["base_receipt_sha256"]):
        raise ContractError("Protected-guard delta requires its exact immediate predecessor receipt")
    base = json.loads(Path(receipt).read_text(encoding="utf-8"))
    verify_tree(base["prefix"], receipt)
    compiler = "libexec/gcc/aarch64-pc-cygwin/15.0.1/" + frontend
    if (base.get("status") != "byte-identical-relocated-input-not-new-qualification"
            or base.get("source_target") != handoff["source_target"]
            or handoff["source_target"].get("Triple") != "aarch64-pc-cygwin"
            or Path(base["prefix"]).resolve() != Path(handoff["base_prefix"]).resolve()
            or handoff.get("full_cpp_qualified") is not False
            or handoff["changed_files"] != [compiler]):
        raise ContractError("Protected-guard successor must retain its exact single-frontend MSYS boundary")
    verify_cohort_delta({name: row["sha256"] for name, row in base["files"].items()},
                        expected, {compiler}, set())
    change = handoff["changes"][compiler]
    if change["before"] != base["files"][compiler] or change["after"] != handoff["files"][compiler]:
        raise ContractError("Protected-guard before/after identities disagree with their full inventories")
    verify_jump_qualification(source, base["source_jump_buffer_qualification"], base["source_runtime_pairing"])
    verify_ucontext_qualification(source, base["source_ucontext_qualification"])
    return base


def guard_base(handoff, source, expected, receipt):
    base = protected_delta_base(handoff, source, expected, receipt, "cc1.exe")
    negative = handoff["qualification"]["canary_failure"]
    if negative.get("observed_exit") != 1536 or negative.get("remaining") != 0 or negative.get("expected_nonzero") is not True:
        raise ContractError("Protected-guard intake requires the real bounded stack-smash negative control")
    for name in ("raw_pe", "native_cc1", "ordinary_extern", "native_guard", "static_diagnosis"):
        proof = handoff["qualification"][name]
        if digest(proof["path"]) != proof["sha256"]:
            raise ContractError("Protected-guard qualification evidence changed")
    for name in ("patch", "lock", "guard_controls"):
        proof = handoff["source"][name]
        if digest(proof["path"]) != proof["sha256"]:
            raise ContractError("Protected-guard producer source evidence changed")
    return base


def cpp_base(handoff, source, expected, receipt):
    base = protected_delta_base(handoff, source, expected, receipt, "cc1plus.exe")
    cc1 = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe"
    if (base.get("source_status") != "qualified-native-msys-stack-guard-c-compiler-delta"
            or handoff["retained_cc1_sha256"] != base["files"][cc1]["sha256"]):
        raise ContractError("C++ delta must retain the exact qualified protected C frontend")
    proof = handoff["qualification"]
    regressions = {
        "DLL static C++ constructor/dlopen/dlsym/dlclose",
        "pthread-backed std::thread, mutex, TLS isolation and exception catch",
        "filesystem path operation and LP64 formatting",
        "hosted iostream/ctype classic table and all256character classifications",
    }
    if (proof.get("normal_guard_raw_exit") != 0 or proof.get("real_canary_failure_raw_exits") != [1536, 1536]
            or proof.get("new_pseudo_bits") != {"64": 1} or proof.get("owned_command_groups") != 17
            or proof.get("matrix_runs") != 7 or set(proof.get("all_protected_cpp_regressions", [])) != regressions
            or proof["policy"].get("all_native_jobs_drained") is not True
            or proof["policy"].get("inheritance_negative_control_exit") != 37):
        raise ContractError("C++ frontend requires all named positive, negative and retained matrix qualifications")
    for item in [proof[name] for name in ("native_result", "retained_native_matrix", "raw_pe")] + [
            proof["policy"]["helper"], proof["policy"]["bounded_runner"],
            handoff["source"]["source_lock"], handoff["source"]["guard_patch"]]:
        if digest(item["path"]) != item["sha256"]:
            raise ContractError("Protected C++ qualification or source evidence changed")
    return base


def verify_jump_qualification(source, qualification, pairing):
    layout = ("JmpBufBytes", "SigjmpBufBytes", "SaveMaskOffset", "SignalMaskOffset")
    if (tuple(qualification.get(name) for name in layout) != (256, 272, 256, 264) or
            qualification.get("ExistingConsumersRecompiled") is not False):
        raise ContractError("Unexpected MSYS public jump-buffer qualification")
    for proof in ([qualification[name] for name in ("Header", "Consumer", "RuntimeReceipt")] +
                  [pairing[name] for name in ("SysrootManifest", "DllManifest")]):
        path = proof["Path"].replace("\\", "/")
        relative_path(path)
        if digest(source / path) != proof["SHA256"]:
            raise ContractError("MSYS jump-buffer or runtime pairing evidence changed")


def verify_ucontext_qualification(source, qualification):
    if (qualification.get("EntryStackAlignment") != 16 or
            qualification.get("ArgumentCounts") != [0, 1, 8, 9, 12] or
            qualification.get("CoroutineYields", 0) < 32 or
            qualification.get("BoundedChildCleanup") is not True or
            qualification.get("InvalidContextReturnsEINVAL") is not True):
        raise ContractError("Unexpected native MSYS context qualification")
    for name in ("Header", "Consumer", "RuntimeReceipt"):
        proof = qualification[name]
        path = proof["Path"].replace("\\", "/")
        relative_path(path)
        if digest(source / path) != proof["SHA256"]:
            raise ContractError("Native MSYS context qualification changed")


def published_input(handoff):
    if handoff.get("schema") == 1 and handoff.get("status") in (
            "qualified-native-msys-stack-guard-c-compiler-delta", "qualified-native-msys-protected-cpp-frontend-delta"):
        source, status = Path(handoff["prefix"]), handoff["status"]
        if len(handoff["files"]) != handoff["file_count"]:
            raise ContractError("Protected-guard complete file count differs")
        rows = [(name, row["sha256"]) for name, row in handoff["files"].items()]
    elif handoff.get("Immutable") is True:
        rows = [(row["Path"].replace("\\", "/"), row["SHA256"]) for row in handoff["Files"]]
        source, status = Path(handoff["Prefix"]), handoff["Status"]
    elif handoff.get("SchemaVersion") == 1 and handoff.get("Status") == "qualified":
        if (handoff.get("Host") != {"Runtime": "UCRT", "Triple": "aarch64-w64-mingw32", "Machine": "0xAA64"}
                or handoff.get("Target") != {"DataModel": "LP64", "Triple": "aarch64-pc-cygwin",
                                              "Profile": "MSYS", "ThreadModel": "posix"}):
            raise ContractError("Unexpected native MSYS SDK host or target profile")
        source, status = Path(handoff["Prefix"]), handoff["Status"]
        qualification = handoff["AssemblerQualification"]
        if qualification.get("ExistingLibrariesRebuilt") is not False:
            raise ContractError("Expected explicit assembler-delta qualification, not rebuilt-library claims")
        for name in ("RawEncoding", "NativeBoundaries", "SourceLock", "Patch"):
            proof = qualification[name]
            path = proof["Path"].replace("\\", "/")
            relative_path(path)
            if digest(source / path) != proof["SHA256"]:
                raise ContractError("Native MSYS assembler qualification input changed")
        acceptance = handoff["Acceptance"]
        if (digest(acceptance["Path"]) != acceptance["SHA256"] or
                digest(acceptance["ToolIdentitiesPath"]) != acceptance["ToolIdentitiesSHA256"]):
            raise ContractError("Native MSYS SDK acceptance receipt changed")
        if "JumpBufferQualification" in handoff:
            verify_jump_qualification(source, handoff["JumpBufferQualification"], handoff["RuntimePairing"])
        if "UcontextQualification" in handoff:
            verify_ucontext_qualification(source, handoff["UcontextQualification"])
        rows = [(row["Path"].replace("\\", "/"), row["SHA256"]) for row in handoff["Files"]]
    elif handoff.get("schema") == 1 and handoff.get("status") == "ready-for-private-pipeline-qualification":
        item = handoff["inventory"]
        if digest(item["path"]) != item["sha256"]:
            raise ContractError("Published compiler inventory changed")
        data = json.loads(Path(item["path"]).read_text())
        source, status = Path(handoff["prefix"]), handoff["status"]
        if Path(data["prefix"]).resolve() != source.resolve() or data["fileCount"] != item["fileCount"]:
            raise ContractError("Compiler inventory identifies a different prefix")
        rows = [(row["relativePath"].replace("\\", "/"), row["sha256"]) for row in data["files"]]
        if len(rows) != data["fileCount"]:
            raise ContractError("Compiler inventory count differs")
    elif handoff.get("schema") == 1 and "binaryCohort" in handoff:
        cohort = handoff["binaryCohort"]
        regressions = handoff["targetedRegressions"]
        if (not regressions["passed"] or digest(regressions["result"]) != regressions["resultSha256"]
                or digest(cohort["inventory"]) != cohort["inventorySha256"]):
            raise ContractError("Producer regression or inventory receipt changed")
        data = json.loads(Path(cohort["inventory"]).read_text())
        if not isinstance(data, list) or len(data) != cohort["fileCount"]:
            raise ContractError("Invalid producer cohort file set")
        rows = [(row["relativePath"].replace("\\", "/"), row["sha256"]) for row in data]
        source = Path(cohort["windowsPrefix"])
        status = "producer-targeted-regressions-passed"
    elif handoff.get("schema") == 1 and handoff.get("status") == "producer-fix-validated-for-tcl-main-direct-sp-seh":
        cohort = handoff["binary"]
        for name in ("compileAndFrontier", "directSpRtlVirtualUnwind", "targetedRegressions"):
            proof = handoff["validation"][name]
            if digest(proof["path"]) != proof["sha256"]:
                raise ContractError("Producer validation receipt changed")
        if digest(cohort["inventory"]) != cohort["inventorySha256"]:
            raise ContractError("Producer inventory changed")
        data = json.loads(Path(cohort["inventory"]).read_text())
        if (not isinstance(data, dict) or data.get("fileCount") != cohort["fileCount"] or
                Path(data["prefix"]).resolve() != Path(cohort["prefix"]).resolve() or
                len(data["files"]) != cohort["fileCount"]):
            raise ContractError("Invalid producer cohort file set")
        rows = [(row["relativePath"].replace("\\", "/"), row["sha256"]) for row in data["files"]]
        source, status = Path(cohort["prefix"]), handoff["status"]
    elif handoff.get("schema") == 1 and handoff.get("status") == "fp-unwind-gas-enum-order-fix-validated":
        cohort = handoff["binary"]
        for name in ("fixedDirectiveMatrix", "nativeFpBoundaries", "compilerGeneratedD8Replay", "fixedPrefixFrontierRegressions"):
            proof = handoff["validation"][name]
            if digest(proof["path"]) != proof["sha256"]:
                raise ContractError("FP producer validation receipt changed")
        if digest(cohort["inventory"]) != cohort["inventorySha256"]:
            raise ContractError("FP producer inventory changed")
        data = json.loads(Path(cohort["inventory"]).read_text())
        source, status = Path(cohort["successorPrefix"]), handoff["status"]
        if (not isinstance(data, dict) or data.get("fileCount") != cohort["fileCount"] or
                Path(data["prefix"]).resolve() != source.resolve() or len(data["files"]) != cohort["fileCount"]):
            raise ContractError("Invalid FP producer cohort file set")
        rows = [(row["relativePath"].replace("\\", "/"), row["sha256"]) for row in data["files"]]
    elif handoff.get("schema") == 1 and handoff.get("status") == "crt-cexp-recursion-fix-validated":
        cohort = handoff["binary"]
        for name in ("patchedCohort", "patchedDoubleProbe", "patchedFamilyProbe"):
            proof = handoff["validation"][name]
            if digest(proof["path"]) != proof["sha256"]:
                raise ContractError("CRT producer validation receipt changed")
        if digest(cohort["inventory"]) != cohort["inventorySha256"]:
            raise ContractError("CRT producer inventory changed")
        data = json.loads(Path(cohort["inventory"]).read_text())
        source, status = Path(cohort["successorPrefix"]), handoff["status"]
        if (not isinstance(data, dict) or data.get("fileCount") != cohort["fileCount"] or
                Path(data["prefix"]).resolve() != source.resolve() or len(data["files"]) != cohort["fileCount"]):
            raise ContractError("Invalid CRT producer cohort file set")
        rows = [(row["relativePath"].replace("\\", "/"), row["sha256"]) for row in data["files"]]
    elif handoff.get("schema") == 1 and handoff.get("status") == "qualified-cmocka-native-msys-gcc-producer-fix":
        cohort = handoff["stagedPrefix"]
        proof = handoff["validation"]["exactCmockaReplay"]
        if (digest(cohort["inventory"]) != cohort["inventorySha256"] or
                digest(proof["path"]) != proof["sha256"] or proof["exitCode"] != 0):
            raise ContractError("CMocka producer inventory or replay changed")
        replay = json.loads(Path(proof["path"]).read_text(encoding="utf-8"))
        if (replay.get("status") != "success" or replay.get("exitCode") != 0 or
                replay.get("workaround") != "none" or
                replay["input"]["sha256"] != handoff["originalRepro"]["preprocessedSha256"] or
                any(flag not in replay["argv"] for flag in handoff["originalRepro"]["originalFlags"]) or
                digest(replay["input"]["path"]) != replay["input"]["sha256"] or
                digest(replay["object"]["path"]) != proof["objectSha256"]):
            raise ContractError("CMocka compiler replay did not retain its exact source/flags/output boundary")
        data = json.loads(Path(cohort["inventory"]).read_text(encoding="utf-8"))
        source, status = Path(cohort["path"]), handoff["status"]
        if (Path(data["newPrefix"]).resolve() != source.resolve() or
                data["fileCount"] != cohort["fileCount"] or len(data["files"]) != cohort["fileCount"]):
            raise ContractError("CMocka compiler inventory identifies a different prefix")
        rows = [(row["relative"].replace("\\", "/"), row["sha256"]) for row in data["files"]]
    else:
        raise ContractError("Unsupported published compiler input; no qualification is inferred")
    expected = {}
    folded = set()
    for path, sha in rows:
        relative_path(path)
        if path.casefold() in folded:
            raise ContractError("Duplicate compiler inventory entry")
        folded.add(path.casefold())
        expected[path] = sha
    if not expected:
        raise ContractError("Empty compiler input")
    return source, status, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-receipt", type=Path, help="Required coherent immediate predecessor for a scoped frontend delta")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or " " in str(output) or digest(args.handoff) != args.sha256:
        raise ContractError("Require a new space-free path and the exact published handoff hash")
    handoff = json.loads(args.handoff.read_text())
    source, status, expected = published_input(handoff)
    if output.is_relative_to(source.resolve()) or source.resolve().is_relative_to(output):
        raise ContractError("Compiler snapshot source and destination must be disjoint")
    base = None
    if status == "qualified-cmocka-native-msys-gcc-producer-fix":
        base = cmocka_base(handoff, source, expected, args.base_receipt)
    elif status == "qualified-native-msys-stack-guard-c-compiler-delta":
        base = guard_base(handoff, source, expected, args.base_receipt)
    elif status == "qualified-native-msys-protected-cpp-frontend-delta":
        base = cpp_base(handoff, source, expected, args.base_receipt)
    elif args.base_receipt is not None:
        raise ContractError("A predecessor receipt is supported only for an explicit qualified frontend delta")
    before = inventory(source)
    if {name: row["sha256"] for name, row in before.items()} != expected:
        raise ContractError("Published toolchain complete file set or hashes differ")
    if status in ("qualified-native-msys-stack-guard-c-compiler-delta", "qualified-native-msys-protected-cpp-frontend-delta"):
        if before != handoff["files"]:
            raise ContractError("Protected frontend payload sizes or identities disagree with the sealed inventory")
    shutil.copytree(source, output)
    if inventory(output) != before or inventory(source) != before:
        raise ContractError("Toolchain bytes changed while copying")
    receipt = {"schema": 1, "status": "byte-identical-relocated-input-not-new-qualification",
               "source_prefix": str(source), "prefix": str(output),
               "source_handoff_sha256": args.sha256, "source_status": status,
               "source_target": handoff.get("Target"),
               "source_assembler_qualification": handoff.get("AssemblerQualification"),
               "source_jump_buffer_qualification": handoff.get("JumpBufferQualification"),
               "source_ucontext_qualification": handoff.get("UcontextQualification"),
               "source_runtime_pairing": handoff.get("RuntimePairing"),
               "source_components": handoff.get("Components"),
               "source_epoch_sha256": handoff.get("EpochSHA256"),
               "full_cpp_qualified": False,
               "purpose": "Avoid libtool splitting compiler-emitted predependency paths at spaces",
               "files": before}
    if base is not None:
        for name in ("source_target", "source_assembler_qualification", "source_jump_buffer_qualification",
                     "source_ucontext_qualification", "source_runtime_pairing", "source_components"):
            receipt[name] = base[name]
        receipt["retained_runtime_epoch_sha256"] = base["source_epoch_sha256"]
        guard_delta = status == "qualified-native-msys-stack-guard-c-compiler-delta"
        if status == "qualified-native-msys-protected-cpp-frontend-delta":
            receipt["source_cpp_frontend_delta"] = {
                "base_receipt": {"path": str(args.base_receipt.resolve()), "sha256": digest(args.base_receipt)},
                "producer_source_lock_sha256": handoff["source"]["canonical_sha256"],
                "changed_files": handoff["changed_files"], "qualification": handoff["qualification"],
                "scope": "Protected C++ frontend and named regressions only; not whole-SDK or package admission"}
            receipt["retained_c_compiler_receipt"] = receipt["source_cpp_frontend_delta"]["base_receipt"]
            receipt["source_epoch_sha256"] = handoff["epoch_sha256"]
            verify_base = cpp_base
        else:
            receipt["source_compiler_delta"] = {
                "base_receipt_sha256": digest(args.base_receipt),
                "producer_source_lock_sha256": handoff["source"]["canonical_lock_sha256"] if guard_delta
                                              else handoff["source"]["sourceLockCanonicalSha256"],
                "changed_files": handoff["changed_files"] if guard_delta else handoff["stagedPrefix"]["replaced"],
                "scope": "C compiler frontier only; C++ compiler and all target runtime/header/library bytes retained"}
            verify_base = guard_base if guard_delta else cmocka_base
        if verify_base(handoff, source, expected, args.base_receipt) != base:
            raise ContractError("Coherent compiler predecessor changed during copy")
    output.with_name(output.name + ".copy.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Copied {len(before)} identical toolchain files; consumer qualification is still required")


if __name__ == "__main__":
    main()
