#!/usr/bin/env python3
"""Seal the generated signal object and the independently qualified myfault fix."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

RECIPE = Path(__file__).resolve().parent
FIXED = "5aa7993031eca7d44a6dd59b32cb670dbe161efc8827825e9070542172a82280"


def ref(path):
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("epoch", "native-proof", "signal-object", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--captures", type=Path, nargs=3, required=True)
    parser.add_argument("--controls", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    epoch = args.epoch.resolve(strict=True)
    build = epoch / "build/winsup/cygwin"
    replay, native, assembly = load(epoch / "result.json"), load(args.native_proof), load(args.signal_object)
    if replay["status"] != "private-runtime-myfault-relink-complete-not-native-qualified":
        raise ValueError("Recorded one-object runtime link is incomplete")
    if replay["changed_members"] != ["exceptions.o"]:
        raise ValueError("Unexpected runtime archive changes")
    if (ref(RECIPE / "runtime-arm64-myfault-context.patch")["sha256"] != replay["patch_sha256"]
            or ref(epoch / "source/winsup/cygwin/exceptions.cc")["sha256"] != replay["source_after"]):
        raise ValueError("Source patch changed after the actual build")
    if ref(build / "new-msys-2.0.dll")["sha256"] != FIXED:
        raise ValueError("Runtime is not the qualified corrective cohort")
    if (native["status"] != "native-arm64-signal-register-and-myfault-qualified"
            or len(native["existing_regressions"]) != 4
            or any(not row["process"]["passed"] for row in native["runs"])):
        raise ValueError("Native signal/jump/fault coverage is incomplete")
    if native["raw_pe"]["msys-2.0.dll"]["sha256"] != FIXED:
        raise ValueError("Native proof tested another runtime")
    if assembly["status"] != "native-arm64-signal-object-qualified-for-link" or len(assembly["defined_symbols"]) != 990:
        raise ValueError("Signal export coverage is incomplete")
    captured = {}
    fixtures = set()
    for path in args.captures:
        record = load(path)
        mode = record["mode"]
        observation = record["observer"]
        exits = observation["native_target_exits"]
        if (not record["process"]["passed"] or not observation["passed"]
                or not observation["observation_count_matches"]
                or observation["unobserved_processes"] or observation["unresolved_processes"]
                or len(exits) != 1 or exits[0]["raw_exit"] != 0):
            raise ValueError("Native observer did not qualify one exact successful target generation")
        if record["inputs"]["msys-2.0.dll"]["sha256"] != FIXED:
            raise ValueError("Captured runtime differs")
        fixtures.add(record["inputs"]["myfault.exe"]["sha256"])
        case = path.parent / "case"
        stdout = case / ("fixture.log" if mode == "ordinary" else "debug/stdout.bin")
        if stdout.read_bytes().replace(b"\r\n", b"\n") != b"arm64-myfault-efault-ok: 8 protected-page faults\n":
            raise ValueError("No exact protected-page EFAULT success output")
        if mode != "ordinary":
            debug = load(case / "debug/result.json")
            observed = {(r["pid"], r["created"]): r["raw_exit"] for r in exits}
            events = {(r["pid"], r["created"]): r["raw_exit"] for r in debug["processes"]}
            faults = [e for e in debug["events"] if e.get("exception", {}).get("code") == 0xc0000005]
            if (debug["error"] is not None or len(debug["processes"]) != 1 or events != observed
                    or debug["memory_writes"] or debug["register_writes"] or debug["unwind_probes"] is not None
                    or debug["context_reads_enabled"] != (mode == "debug")
                    or len(faults) != 8 or any(e["continue_status"] != 0x80010001 for e in faults)
                    or not all(p["event_matches_handle_exit"] and p["machine"] == 0xaa64 for p in debug["processes"])):
                raise ValueError("Debugger generation, forwarding or zero-write evidence differs")
            mapped = [e["module"] for e in debug["events"] if "module" in e
                      and Path(e["module"].get("path", "")).name.lower() == "msys-2.0.dll"]
            if len(mapped) != 1 or mapped[0]["mapped_file_sha256"] != FIXED:
                raise ValueError("Debugger did not map the exact fixed DLL")
        if mode in captured:
            raise ValueError("Duplicate capture mode")
        captured[mode] = ref(path)
    if set(captured) != {"ordinary", "debug", "no-context"} or len(fixtures) != 1:
        raise ValueError("Missing matched same-binary launch mode")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    for name in ("usr/bin", "sdk", "source", "recipes", "evidence"):
        (out / name).mkdir(parents=True)
    for source, destination in (
            (build / "new-msys-2.0.dll", out / "usr/bin/msys-2.0.dll"),
            (build / "libmsys-2.0.a", out / "sdk/libmsys-2.0.a"), (build / "crt0.o", out / "sdk/crt0.o"),
            (epoch / "source/winsup/cygwin/exceptions.cc", out / "source/exceptions.cc"),
            (epoch / "source/winsup/cygwin/scripts/gendef", out / "source/gendef"),
            (epoch / "source/winsup/cygwin/local_includes/signal-frame-arm64.h", out / "source/signal-frame-arm64.h"),
            (epoch / "source/winsup/CYGWIN_LICENSE", out / "CYGWIN_LICENSE"),
            (RECIPE / "runtime-arm64-myfault-context.patch", out / "source/runtime-arm64-myfault-context.patch"),
            (build / "sigfe.s", out / "source/sigfe.s"), (build / "tlsoffsets", out / "source/tlsoffsets"),
            (epoch / "result.json", out / "evidence/relink.json"),
            (args.native_proof, out / "evidence/native.json"), (args.signal_object, out / "evidence/native-signal-object.json")):
        shutil.copy2(source, destination)
    for name in ("generate-runtime-signals.py", "assemble-runtime-signals.py", "replay-runtime-myfault.py",
                 "test-runtime-signals.py", "capture-runtime-myfault.py", "seal-runtime-signals.py",
                 "prepare-msys-runtime-debug.py", "test-msys-ucontext.py", "native-loaded-modules.py",
                 "run-msys-library-stage.py"):
        shutil.copy2(RECIPE / name, out / "recipes" / name)
    for path in (RECIPE / "probes").glob("signal-*-arm64.*"):
        shutil.copy2(path, out / "recipes" / path.name)
    report = {
        "schema": 1, "status": "arm64-signal-and-myfault-scoped-runtime-qualified",
        "source": {"repository": "https://github.com/crutkas/msys2-runtime.git",
                   "baseCommit": "d890a845e992638a6f09560efacc26d15b3ffe6a",
                   "baseRuntimeSha256": "72c1696053ec6f0735d9cab4d38c2f7710a2d70dd8f7bc17e55bfa93e955852e",
                   "exceptionsBefore": replay["source_before"], "exceptionsAfter": replay["source_after"],
                   "patch": ref(out / "source/runtime-arm64-myfault-context.patch")},
        "runtime": ref(out / "usr/bin/msys-2.0.dll"),
        "importLibrary": ref(out / "sdk/libmsys-2.0.a"), "crt0": ref(out / "sdk/crt0.o"),
        "tlsOffsets": ref(out / "source/tlsoffsets"), "gendef": ref(out / "source/gendef"),
        "signalFrame": ref(out / "source/signal-frame-arm64.h"),
        "generation": {"existingArm64ImplementationReused": True, "requiredExportTrampolines": 980,
                       "actualNativeObject": assembly["object"], "nativeObjectReceipt": ref(args.signal_object),
                       "nativeObjectSubstitutedIntoRuntime": False,
                       "runtimeSignalObject": replay["outputs"]["sigfe.o"],
                       "scope": "Existing coherent full-port ARM64 signal object remains unchanged; independent native assembly proves current native binutils/export closure."},
        "validation": {"nativeProcess": True, "architecture": "arm64", "nativeProof": ref(args.native_proof),
                       "asynchronousRegisterDeliveries": 16, "protectedPageEFAULTRecoveriesPerLaunch": 8,
                       "captures": captured, "existingRegressions": native["existing_regressions"],
                       "relink": ref(epoch / "result.json"), "changedArchiveMembers": replay["changed_members"],
                       "runtimeBuildHost": "aarch64 Linux cross bootstrap; final probes and assembler run natively on Windows ARM64"},
        "preservedControls": [ref(path) for path in args.controls],
        "ownership": "Trampoline generation/fault personality only. No autoload, export deletion, gentls_offsets or build-reproducibility source edits.",
        "limits": "Scoped native runtime qualification, not a full Git distribution or broad exit-domain collector admission. Reproducibility/link owners integrate into a new successor; old cohorts remain immutable."
    }
    (out / "handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = {p.relative_to(out).as_posix(): {**ref(p), "size": p.stat().st_size}
             for p in out.rglob("*") if p.is_file()}
    out.with_name(out.name + ".manifest.json").write_text(json.dumps({"schema": 1, "files": files}, indent=2) + "\n",
                                                        encoding="utf-8", newline="\n")
    print(out / "handoff.json")


if __name__ == "__main__":
    main()
