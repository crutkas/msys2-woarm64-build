"""Validate raw forensic evidence without granting any exit-domain admission."""

import hashlib
import struct

from resume import ROOT, digest, load


def generation(record):
    values = []
    for key, maximum, minimum in (("pid", 2 ** 32, 1), ("created", 2 ** 64, 1), ("raw_exit", 2 ** 32, 0)):
        value = record[key]
        if type(value) is not int or not minimum <= value < maximum:
            raise ValueError(f"Invalid lossless {key}")
        values.append(value)
    return tuple(values[:2]), values[2]


def generation_join(native, debug):
    observed, captured = {}, {}
    for record in native["native_target_exits"]:
        identity, raw = generation(record)
        if identity in observed:
            raise ValueError("Duplicate native process generation")
        observed[identity] = raw
    for record in debug["processes"]:
        identity, raw = generation(record)
        if identity in captured:
            raise ValueError("Duplicate debug process generation")
        if (record["debug_event_raw_exit"] != raw or record["event_matches_handle_exit"] is not True
                or record["encoding"] != "UNKNOWN" or record["role"] != "UNKNOWN"
                or record["decoded_status"] is not None or record["terminal_evidence"] is not None):
            raise ValueError("Mismatched raw exit or unqualified provenance")
        captured[identity] = raw
    if observed != captured:
        raise ValueError("Different process generations or raw exits")
    return observed


def check_case(name):
    directory = ROOT / "cases" / name
    result = load(directory / "result.json")
    native = load(directory / "native-job.json")
    if (digest(directory / "native-job.json") != result["native_job_sha256"]
            or not result["complete_observation"] or native["timed_out"]
            or not native["observation_count_matches"] or native["unobserved_processes"]
            or native["unresolved_processes"] or result["launch"]["active_at_boundary"] != 0
            or result["launch"]["timed_out"] or native["expected_probe_exits"] or native["runtime_exit_relays"]):
        raise ValueError(f"Incomplete raw case evidence: {name}")
    if result["mode"] != "ordinary":
        debug = load(directory / "debug/result.json")
        if digest(directory / "debug/result.json") != result["debug_sha256"] or debug["error"] is not None:
            raise ValueError("Debug receipt changed or failed")
        generation_join(native, debug)
        for process in debug["processes"]:
            if process["image"].get("mapped_file_sha256") != result["fixture_sha256"]:
                raise ValueError("A different fixture image was loaded")
            runtimes = [module for module in process["modules"]
                        if module.get("path", "").lower().endswith("\\msys-2.0.dll")]
            if len(runtimes) != 1 or runtimes[0].get("mapped_file_sha256") != result["runtime_sha256"]:
                raise ValueError("Loaded runtime differs from the explicit private cohort")
        for event in debug["events"]:
            if event["event"] == 1 and event["exception"]["code"] in (0x20474343, 0x21474343, 0x22474343):
                if event["continue_status"] != 0x80010001:
                    raise ValueError("An application unwind exception was swallowed")
    return result, native


def check_alias(name):
    result, native = check_case(name)
    if [record["raw_exit"] for record in native["native_target_exits"]] != [0xC00000FF]:
        raise ValueError("Probe run changed the original debugger failure")
    debug = load(ROOT / "cases" / name / "debug/result.json")
    probes = debug["unwind_probes"]
    if (not probes["all_instructions_restored"] or probes["memory_writes"] != 12
            or probes["context_writes"] != 6 or len(probes["points"]) != 6
            or not all(point["hit"] and point["restored"] for point in probes["points"])):
        raise ValueError("A source-bound probe was missed or not restored")
    samples = {sample["name"]: sample for sample in probes["samples"]}
    if len(samples) != 6 or not samples["rtl-entry"]["return_is_locked_phase2_call"]:
        raise ValueError("Missing exact handler-to-unwind callsite")
    for sample in samples.values():
        if not sample["resume_state"]["other_observed_registers_equal"]:
            raise ValueError("Probe resume modified other observed registers")
        if sample["instruction_restored"] != sample["callsite"]["original"]:
            raise ValueError("Original instruction was not restored")
        for context in sample["saved_contexts"].values():
            data = bytes.fromhex(context["bytes"])
            if len(data) != 912 or hashlib.sha256(data).hexdigest() != context["sha256"]:
                raise ValueError("Saved target CONTEXT bytes are incomplete")
            for field, offset in (("fp", 240), ("lr", 248), ("sp", 256), ("pc", 264)):
                if struct.unpack_from("<Q", data, offset)[0] != context[field]:
                    raise ValueError("Target CONTEXT parser disagrees with bytes")
    before = samples["dispatcher-entry"]["saved_contexts"]["dispatcher_frame"]
    after = samples["after-capture"]["saved_contexts"]["dispatcher_frame"]
    final = samples["no-progress"]["saved_contexts"]
    addresses = {context["address"] for context in final.values()}
    if len(addresses) != 1 or before["address"] not in addresses:
        raise ValueError("Incoming, scratch and dispatcher frame do not alias")
    no_progress = final["dispatcher_frame"]
    ntdll_base = samples["no-progress"]["callsite"]["address"] - 0x46764
    if (before["pc"] == after["pc"] or before["sp"] == after["sp"]
            or after["pc"] != ntdll_base + 0x46468
            or no_progress["pc"] != ntdll_base + 0x16C084
            or no_progress["pc"] != samples["no-progress"]["last_control_pc_x27"]
            or no_progress["sp"] != before["address"]):
        raise ValueError("The captured buffer does not show the expected overwrite and no-progress cycle")
    return {"case": name, "debug_sha256": result["debug_sha256"], "pointer": before["address"],
            "before": {key: before[key] for key in ("address", "pc", "sp", "lr")},
            "after_capture": {key: after[key] for key in ("pc", "sp", "lr")},
            "no_progress": {key: no_progress[key] for key in ("pc", "sp", "lr")},
            "raw_exit": 0xC00000FF, "all_instructions_restored": True}


def check_matrix(path):
    matrix = load(path)
    if len(matrix["controls"]) != 30 or matrix["producer_admission"]:
        raise ValueError("The complete private matrix is required")
    for control in matrix["controls"]:
        result, native = check_case(control["case"])
        if digest(ROOT / "cases" / control["case"] / "result.json") != control["result_sha256"]:
            raise ValueError("Matrix result identity changed")
        raw = sorted(record["raw_exit"] for record in native["native_target_exits"])
        if raw != control["expected_raw"] or raw != control["actual_raw"]:
            raise ValueError("Unexpected matrix exit")
        if result["mode"] == "debug":
            debug = load(ROOT / "cases" / control["case"] / "debug/result.json")
            if debug["memory_writes"] or debug["register_writes"] or debug["unwind_probes"] is not None:
                raise ValueError("Remedy matrix may not use debugger instrumentation")
    return matrix
