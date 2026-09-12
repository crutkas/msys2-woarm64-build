"""Add unchanged, single-target Tcl core coverage without replacing any accepted input."""

from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
import shutil
import tarfile

import qualify
from finalize import generation_state, reference
from package_provider import validate_archive
from qualify import ROOT, digest, import_tools, read_json, require, require_memory, verify_inputs, write_json


PROFILE = [
    "append", "appendComp", "binary", "concat", "dstring", "format", "scan", "split",
    "string", "stringComp", "stringObj", "utf", "join", "lindex", "linsert", "llength",
    "lrange", "lrepeat", "lreplace", "lsearch", "lset", "lsetComp", "lmap", "listObj",
]
OUTPUT = ROOT / "expanded-20260909-01"
PREVIOUS = ROOT / "handoff-03/result.json"
PREVIOUS_SHA = "3f727e23873e882916d985ecf423181c99a0d7e6de1892bc24e2dbe6bc49098e"
TOTAL_FIELDS = ("total", "passed", "skipped", "failed")


def verify_previous():
    sources = import_tools()
    require(digest(PREVIOUS) == PREVIOUS_SHA, "Accepted Tcl handoff changed")
    previous = read_json(PREVIOUS)
    provider = read_json(previous["provider"]["receipt"]["path"])
    require(digest(previous["provider"]["receipt"]["path"]) ==
            previous["provider"]["receipt"]["sha256"], "Accepted provider receipt changed")
    require(sources.inventory(provider["payload"]) == provider["files"], "Accepted provider payload changed")
    require(digest(previous["provider"]["archive"]["path"]) ==
            previous["provider"]["archive"]["sha256"], "Accepted provider archive changed")
    verify_inputs()
    return previous


def prepare():
    previous = verify_previous()
    require(not set(PROFILE) & set(previous["coverage"]["files"]), "New profile duplicates accepted coverage")
    require(len(PROFILE) == len(set(PROFILE)), "Repeated file in expanded profile")
    unchanged = read_json(ROOT / "inputs.json")["unchanged_upstream_test_files"]
    selected = {}
    for name in PROFILE:
        relative = "tests/" + name + ".test"
        path = ROOT / "source" / relative
        require(relative in unchanged and digest(path) == unchanged[relative],
                "Expanded tests must be byte-identical to pinned raw upstream")
        text = path.read_text(encoding="utf-8")
        require(not re.search(r"(^|[\[;])\s*(exec|socket|testthread|thread::|vwait)\b", text, re.MULTILINE),
                "Selected file needs further concurrency or external-fixture review")
        selected[name] = reference(path)
    OUTPUT.mkdir()
    for path in Path(__file__).parent.iterdir():
        if path.suffix in (".py", ".tcl"):
            shutil.copyfile(path, OUTPUT / path.name)
    write_json(OUTPUT / "selection.json", {
        "previous": reference(PREVIOUS), "files": selected, "jobs": 1,
        "grant": "General Chat e4b36628 fresh bounded grant 2026-09-09; bounded to NEW1 and "
                 "acknowledged by Git coordinator 0724b323, old grants not reused",
        "scope": "Whole unchanged Tcl string/list/format/scan/binary/UTF core files, fresh interpreters, sequential",
        "reviewed_boundaries": [
            "No selected script invokes an external process, socket, or thread worker",
            "binary-76.1 reads /dev/null; the Windows NUL counterpart retains its original platform constraint",
            "lrepeat-1.8 exceeds LIST_MAX and is rejected before allocation in tclCmdIL.c2642-2646",
            "lmap-7.7/7.8 retain the original one-million-element in-process regression cases",
            "Memory, Unicode, endian and LP64 constraints are not overridden; no CI skip inherited",
        ],
        "non_overlap": "No SQLite/runtime/compiler work and no pipeline-owned alias activation",
        "new_runtime_or_observer_adopted": False,
        "scripts": {path.name: reference(path) for path in OUTPUT.iterdir() if path.suffix in (".py", ".tcl")},
    })


def seal_report(rows, blocked):
    previous = verify_previous()
    totals, constraints = Counter(), Counter()
    states, observations = [], []
    for row in rows:
        totals.update({key: row["summary"][key] for key in TOTAL_FIELDS})
        constraints.update(reason for _, reason in row["skips"])
        launch = row["launch"]
        states.append(generation_state(launch["pid"], launch["creation_filetime"]))
        observations.append(row["observer_summary"])
    require(sum(constraints.values()) == totals["skipped"], "Expanded skip accounting differs")
    complete = not blocked and len(rows) == len(PROFILE)
    write_json(OUTPUT / "result.json", {
        "schema": 1, "status": "expanded-unchanged-core-passed" if complete else "expanded-core-gated",
        "selection": reference(OUTPUT / "selection.json"), "previous": reference(PREVIOUS),
        "totals": dict(totals), "constraint_skips": dict(constraints),
        "whole_files_run": [row["file"] for row in rows],
        "not_run": [name for name in PROFILE if name not in {row["file"] for row in rows}],
        "rows": rows, "blocker": blocked, "full_suite": False,
        "observations": observations, "drained_native_generations": states,
        "free_memory_after": require_memory(), "inputs_unchanged": True,
        "source_oracles_changed": False, "rebuilds": 0, "new_grant_returnable": 1,
    })
    if complete:
        seal_handoff(previous, rows, totals, constraints, states)


def seal_handoff(previous, rows, added, constraints, states):
    output = ROOT / "handoff-04"
    output.mkdir()
    coverage = read_json(previous["coverage"]["details"]["path"])
    all_rows = coverage["selected"] + [
        {"file": row["file"] + ".test", "source_sha256": row["source"]["sha256"],
         "summary": row["summary"], "skips": row["skips"], "result": row["result"],
         "launch": row["launch"], "observer": row["observer"],
         "observer_passed": True, "modules": row["modules"]}
        for row in rows
    ]
    cumulative = Counter(previous["coverage"]["totals"])
    cumulative.update(added)
    cumulative_constraints = Counter(previous["coverage"]["constraint_skips"])
    cumulative_constraints.update(constraints)
    selected = previous["coverage"]["files"] + PROFILE
    require(len(selected) == len(set(selected)), "Expanded cumulative coverage duplicates a file")
    remaining = sorted(path.name for path in (ROOT / "source/tests").glob("*.test") if path.stem not in selected)
    coverage.update(selected=all_rows, totals=dict(cumulative), skip_constraints=dict(cumulative_constraints),
                    unselected_core_files=remaining)
    write_json(output / "coverage.json", coverage)
    write_json(output / "drain.json", {
        "at_utc": datetime.now(timezone.utc).isoformat(), "previous": previous["drain"],
        "new_grant": 1, "observed_jobs": len(rows),
        "created_processes": sum(row["observer_summary"]["created"] for row in rows),
        "observed_processes": sum(row["observer_summary"]["observed"] for row in rows),
        "native_generations": states, "active_owned_generations": 0, "returnable_jobs": 1,
        "scope": "Each sealed observer completed with exactly one native target and no descendants",
    })
    archive = output / "maintained-native-tcl-qualification.tar.gz"
    maintained = {}
    with archive.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for path in sorted(OUTPUT.iterdir()):
                if path.suffix not in (".py", ".tcl"):
                    continue
                maintained[path.name] = reference(path)
                info = tarfile.TarInfo(path.name)
                info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
                with path.open("rb") as source:
                    tar.addfile(info, source)
    previous.update(
        supersedes=reference(PREVIOUS),
        revision_reason="Added 24 complete unchanged single-target Tcl core files without adopting new runtime bits",
        core_expansion=reference(OUTPUT / "result.json"), drain=reference(output / "drain.json"),
        jobs_returnable=1,
    )
    previous["coverage"].update(totals=dict(cumulative), files=selected,
                                constraint_skips=dict(cumulative_constraints),
                                details=reference(output / "coverage.json"),
                                unselected_core_file_count=len(remaining))
    previous["maintained_export"].update(archive=reference(archive), sources=maintained)
    previous["environment_boundary"] = {
        "scope": "No foreign execution in the added core profile; previously diagnosed environment "
                 "classifier and pipe behavior remain separate runtime/SQLite-owner gates",
        "new_runtime_adopted": False, "old_basic_raw256_collector_promoted": False,
    }
    require(digest(PREVIOUS) == PREVIOUS_SHA, "Sealing changed the previous handoff")
    provider = read_json(previous["provider"]["receipt"]["path"])
    validate_archive(previous["provider"]["archive"]["path"], provider["files"])
    write_json(output / "result.json", previous)
    print(json.dumps({"handoff": reference(output / "result.json"), "added": dict(added),
                      "cumulative": dict(cumulative), "new_grant_returnable": 1}), flush=True)


def execute():
    require(OUTPUT == Path(__file__).parent, "Run the expansion from its immutable private script snapshot")
    selection = read_json(OUTPUT / "selection.json")
    for row in selection["scripts"].values():
        require(digest(row["path"]) == row["sha256"], "Expansion script snapshot changed")
    rows, blocked = [], None
    for name in PROFILE:
        run_name = OUTPUT.name + "-" + name
        print(json.dumps({"starting": name, "argv_profile": "singleproc1-wholefile",
                          "log": str(ROOT / run_name / "run.log")}), flush=True)
        result = qualify.run(run_name, "suite", [name], jobs=1)
        path = ROOT / run_name
        observed = read_json(path / "native-job.json")
        require(observed["observation_count_matches"] and not observed["timed_out"] and
                observed["created_processes"] == observed["observed_processes"] == 2 and
                len(observed["native_target_exits"]) == 1,
                "The selected single-target execution did not match its reviewed process scope")
        require(len(result["summaries"]) == 1, "Expected one whole-file suite summary")
        launch = read_json(path / "launch.json")
        native = observed["native_target_exits"][0]
        require((launch["pid"], launch["creation_filetime"]) == (native["pid"], native["created"]),
                "Tcl launch and observation process generations differ")
        row = {
            "file": name, "source": selection["files"][name], "result": reference(path / "result.json"),
            "summary": result["summaries"][0], "skips": result["skipped_tests"],
            "launch": launch, "observer": reference(path / "native-job.json"),
            "modules": reference(path / "validated-modules.json"),
            "observer_summary": {"created": observed["created_processes"],
                                 "observed": observed["observed_processes"],
                                 "parent_raw_exit": observed["parent_raw_exit"],
                                 "native_raw_exit": native["raw_exit"], "passed": observed["passed"]},
        }
        rows.append(row)
        print(json.dumps({"completed": name, "pid": launch["pid"],
                          "birth": launch["creation_filetime"], "summary": row["summary"],
                          "observer_passed": observed["passed"]}), flush=True)
        if result["status"] != "passed":
            blocked = {"file": name, "failed_tests": result["failed_tests"], "file_errors": result["file_errors"],
                       "result": reference(path / "result.json")}
            break
    seal_report(rows, blocked)
    if blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    require(sys.argv[1:] in (["prepare"], ["execute"]), "Use prepare or execute")
    if sys.argv[1] == "prepare":
        prepare()
    else:
        execute()
