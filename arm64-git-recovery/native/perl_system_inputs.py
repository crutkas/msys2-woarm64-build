"""Bind the supported-symlink Perl profile to current native compiler, runtime and utility receipts."""

import json
from pathlib import Path
import shutil

from compiler_tools import require_msys_ucontext_receipt
from perl_safety import verify_guards
from sources import ContractError, digest, inventory, verify_tree


def bound_json(item):
    path = Path(item["path"]).resolve()
    if digest(path) != item["sha256"]:
        raise ContractError(f"Published Perl input receipt changed: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_separate_output(output, roots):
    output = Path(output).resolve()
    for root in roots:
        root = Path(root).resolve()
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise ContractError("Perl output must not overlap a published input or source tree")


def check_inputs(spec):
    compiler = bound_json(spec["compiler"])
    compiler_root = Path(compiler["prefix"])
    if (compiler.get("status") != "byte-identical-relocated-input-not-new-qualification" or
            compiler.get("source_status") != "qualified-native-msys-protected-cpp-frontend-delta" or
            compiler.get("source_target") != {"DataModel": "LP64", "ThreadModel": "posix",
                                               "Triple": "aarch64-pc-cygwin", "Profile": "MSYS"}):
        raise ContractError("Alternative Perl requires the current protected C/C++ MSYS compiler cohort")
    require_msys_ucontext_receipt(compiler)
    verify_tree(compiler_root, spec["compiler"]["path"])
    runtime = bound_json(spec["runtime"])
    if (runtime.get("status") != "coherent-runtime-execvp-errno-qualified" or
            runtime.get("validation", {}).get("public_headers_unchanged") != 268 or
            runtime["validation"].get("newlib_objects_and_archives_unchanged") != 1136 or
            runtime["validation"].get("foreign_environment_matrix", {}).get("failures") != 0):
        raise ContractError("Expected the qualified current execvp/runtime cohort, not an isolated DLL")
    for name in ("runtime", "import_library", "crt0"):
        record = runtime["binaries"][name]
        if digest(record["path"]) != record["sha256"]:
            raise ContractError(f"Current Perl runtime component changed: {name}")
    for name in ("foreign_environment_matrix", "core_controls"):
        proof = runtime["validation"][name]
        if digest(proof["result"]) != proof["sha256"]:
            raise ContractError("Current runtime qualification changed")
    utilities = bound_json(spec["utilities"])
    admission = bound_json(spec["utility_admission"])
    native_root = Path(admission["stage"])
    if (admission.get("status") != "native-bash-test-utilities-qualified" or
            admission["manifest_sha256"] != spec["utilities"]["sha256"] or
            admission["runtime_handoff_sha256"] != spec["runtime"]["sha256"] or
            utilities["runtime_sha256"] != runtime["binaries"]["runtime"]["sha256"]):
        raise ContractError("Native Perl shell and complete runtime cohort are not paired")
    verify_tree(native_root, spec["utilities"]["path"])
    if digest(admission["smoke_result"]) != admission["smoke_result_sha256"]:
        raise ContractError("Native utility admission evidence changed")
    prepared = bound_json(spec["source"])
    source = Path(spec["source"]["root"])
    verify_tree(source, spec["source"]["path"])
    verify_guards(source)
    origin = bound_json(spec["source_origin"])
    recipe = bound_json(spec["recipe_origin"])
    if (prepared.get("source_id") != "perl-gfw" or prepared.get("recipe_id") != "msys-recipes" or
            prepared.get("status") != "source-prepared-not-built" or
            prepared.get("source_manifest_sha256") != spec["source_origin"]["sha256"] or
            prepared.get("recipe_manifest_sha256") != spec["recipe_origin"]["sha256"] or
            origin.get("source", {}).get("version") != "5.38.2" or
            origin["source"].get("sha256") != "d91115e90b896520e83d4de6b52f8254ef2b70a8d545ffab33200ea9f1cf29e8" or
            recipe.get("source", {}).get("id") != "msys-recipes"):
        raise ContractError("The alternative profile must retain the exact preserved Perl 5.38.2 source/recipe pins")
    dependencies = []
    for item in spec.get("dependencies", []):
        record = bound_json(item)
        verify_tree(item["root"], item["path"])
        dependencies.append({"input": item, "record": record})
    return {"compiler": compiler, "runtime": runtime, "utilities": utilities,
            "utility_admission": admission, "prepared": prepared, "source_origin": origin,
            "dependencies": dependencies}


def copy_cohort(spec, output):
    before = check_inputs(spec)
    output = Path(output)
    require_separate_output(output, [before["compiler"]["prefix"], before["utility_admission"]["stage"],
                                    spec["source"]["root"],
                                    *[row["input"]["root"] for row in before["dependencies"]]])
    if output.exists():
        raise ContractError("Perl input copies require a new owned cohort root")
    output.mkdir(parents=True)
    compiler, native = output / "toolchain", output / "native"
    shutil.copytree(before["compiler"]["prefix"], compiler)
    shutil.copytree(before["utility_admission"]["stage"], native)
    if inventory(compiler) != before["compiler"]["files"] or inventory(native) != before["utilities"]["files"]:
        raise ContractError("Published compiler or native utility input changed while copying")
    overlay = []
    mapping = {"runtime": ["bin/msys-2.0.dll"],
               "import_library": ["aarch64-pc-cygwin/lib/libmsys-2.0.a"],
               "crt0": ["aarch64-pc-cygwin/lib/crt0.o"]}
    for kind, names in mapping.items():
        item = before["runtime"]["binaries"][kind]
        for name in names:
            destination = compiler / name
            old = digest(destination)
            shutil.copyfile(item["path"], destination)
            if digest(destination) != item["sha256"]:
                raise ContractError("Runtime SDK overlay changed in transit")
            overlay.append({"path": name, "old_sha256": old, "sha256": item["sha256"],
                            "source": item["path"], "kind": kind})
    for directory in ("etc", "tmp", "var/tmp", "home"):
        (native / directory).mkdir(parents=True, exist_ok=True)
    for dependency in before["dependencies"]:
        item = dependency["input"]
        selected = item.get("selected_files")
        if not isinstance(selected, list) or not selected or len(selected) != len(set(selected)):
            raise ContractError("Perl dependency copies require an explicit nonempty file selection, not a whole-prefix overlay")
        for name in selected:
            row = dependency["record"]["files"].get(name)
            if row is None:
                raise ContractError(f"Selected Perl dependency file is not in its original inventory: {name}")
            if "sha256" not in row or not name.startswith("usr/"):
                raise ContractError("Perl development inputs must be regular files in an explicit usr layout")
            destination = native / name
            if destination.exists() and digest(destination) != row["sha256"]:
                raise ContractError(f"Conflicting native Perl input: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(item["root"]) / name, destination)
    if check_inputs(spec) != before:
        raise ContractError("Published Perl inputs changed during owned cohort preparation")
    result = {"schema": 1, "status": "current-perl-system-symlink-input-copy-not-runtime-requalification",
              "compiler_root": str(compiler.resolve()), "native_root": str(native.resolve()),
              "spec": spec, "runtime_overlay": overlay,
              "runtime_sha256": before["runtime"]["binaries"]["runtime"]["sha256"],
              "compiler_files": inventory(compiler), "native_files": inventory(native),
              "limitations": ["Inherited library and C++ receipt scope is preserved",
                              "Original strict Windows-native symlink qualification remains blocked"]}
    with output.with_name(output.name + ".json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


def verify_cohort(path):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("status") != "current-perl-system-symlink-input-copy-not-runtime-requalification":
        raise ContractError("Expected the current native Perl alternative-profile input copy")
    if (inventory(record["compiler_root"]) != record["compiler_files"] or
            inventory(record["native_root"]) != record["native_files"]):
        raise ContractError("Owned native Perl build inputs changed")
    return record
