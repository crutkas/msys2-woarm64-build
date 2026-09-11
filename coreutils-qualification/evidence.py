"""Recheck recorded qualification evidence; do not convert expected failures to passes."""

from pathlib import Path
import tarfile

from qualify import ROOT, RUNTIME_SHA, digest, load
from pe_closure import Image
from debug_tree import job


def check_positive(case_name):
    case = ROOT / "cases" / case_name
    record = load(case / "result.json")
    native = load(case / "native-job.json")
    capture = load(case / "debug/result.json")
    if (record["status"] != "positive-control-passed" or not record["complete_observation"]
            or record["mapped_failures"] or not record["target_executed"]
            or not all(row["passed"] for row in record["checks"])
            or digest(case / "native-job.json") != record["native_job_sha256"]
            or digest(case / "debug/result.json") != record["capture_sha256"]
            or native["timed_out"] or native["unobserved_processes"] or native["unresolved_processes"]
            or not native["observation_count_matches"] or capture["error"]
            or capture["memory_writes"] or capture["register_writes"]):
        raise ValueError(f"Case lacks complete positive evidence: {case_name}")
    expected = {(row["pid"], row["created"]): row["raw_exit"] for row in native["native_target_exits"]}
    actual = {(row["pid"], row["created"]): row["raw_exit"] for row in capture["processes"]}
    if len(expected) != len(native["native_target_exits"]) or len(actual) != len(capture["processes"]) or expected != actual:
        raise ValueError("Generation join is incomplete or ambiguous")
    if not expected or any(raw != 0 for raw in expected.values()):
        raise ValueError("A nonzero raw exit cannot pass a positive control")
    private_bin = ROOT / ("moved" if case_name.startswith("moved-") else "private") / "usr/bin"
    system32 = Path(record["environment"]["SystemRoot"]) / "System32"
    if record["environment"]["PATH"].split(";") != [str(private_bin), str(system32)]:
        raise ValueError("PATH was not restricted to the exact two directories")
    if record["environment"]["MSYS"] != "winsymlinks:sys" or record["environment"]["LC_ALL"] != "C":
        raise ValueError("Declared execution scope differs")
    for process in capture["processes"]:
        if process["machine"] != 0xAA64 or not process["event_matches_handle_exit"]:
            raise ValueError("Target native machine or raw evidence differs")
        runtimes = []
        for row in [process["image"], *process["modules"]]:
            path = Path(job.normalise_windows_path(row.get("path", ""))).resolve()
            if not (path.is_relative_to(private_bin) or path.parent == system32):
                raise ValueError(f"Mapped image escaped the private/System32 closure: {path}")
            image = Image(path)
            if image.machine != 0xAA64 or image.sha256 != row["mapped_file_sha256"]:
                raise ValueError("Mapped-file identity or architecture changed")
            if path.name.lower() == "msys-2.0.dll":
                runtimes.append(path)
                if image.sha256 != RUNTIME_SHA or path != private_bin / "msys-2.0.dll":
                    raise ValueError("A different runtime was loaded")
        if not runtimes:
            raise ValueError("Exact runtime907 not observed")
    return record


def check_package(record):
    if digest(record["archive"]) != record["sha256"] or digest(record["inventory"]) != record["inventory_sha256"]:
        raise ValueError("Package or inventory changed")
    inventory = load(record["inventory"])
    ownership = load(record["ownership"])
    if digest(record["ownership"]) != record["ownership_sha256"]:
        raise ValueError("Ownership changed")
    seen = set()
    with tarfile.open(record["archive"], "r:zst") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.name in seen:
                raise ValueError("Package contains non-files or duplicates")
            seen.add(member.name)
            data = archive.extractfile(member).read()
            import hashlib
            if hashlib.sha256(data).hexdigest() != inventory[member.name]["sha256"]:
                raise ValueError("Package member identity mismatch")
            if member.name == ".PKGINFO":
                if b"provides =" in data or b"pkgname = coreutils\n" in data:
                    raise ValueError("Limited projection claims full-provider identity")
            elif ownership[member.name]["sha256"] != inventory[member.name]["sha256"]:
                raise ValueError("File ownership is missing or inconsistent")
    if seen != set(inventory):
        raise ValueError("Package inventory is not exact")
    if any(Path(name).suffix.lower() == ".dll" for name in seen):
        raise ValueError("Utility package must not carry copied runtime dependencies")
    return inventory
