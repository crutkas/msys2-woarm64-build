"""Preserve resolved upstream CTest commands/properties in a separate replay tree."""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from sources import ContractError, digest, inventory


def cases(discovery):
    if discovery.get("kind") != "ctestInfo" or discovery.get("version", {}).get("major") != 1:
        raise ContractError("Expected native CTest JSON-v1 discovery")
    tests = discovery.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ContractError("An empty CTest replay cannot qualify a library")
    names = set()
    for test in tests:
        name, command = test.get("name"), test.get("command")
        if not isinstance(name, str) or not name or name in names:
            raise ContractError("Missing or duplicate CTest name")
        names.add(name)
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
            raise ContractError("CTest replay requires every resolved original command")
        properties = test.get("properties", [])
        keys = [prop["name"] for prop in properties]
        if len(keys) != len(set(keys)) or "WORKING_DIRECTORY" not in keys:
            raise ContractError("CTest replay requires unique properties and the original working directory")
    return tests


def repair_cmocka_path(discovery, build):
    result = copy.deepcopy(discovery)
    old = str(Path(build) / "src" / "Release")
    replacement = str(Path(build) / "src")
    count = 0
    for test in cases(result):
        for prop in test["properties"]:
            if prop["name"] != "ENVIRONMENT":
                continue
            for index, setting in enumerate(prop["value"]):
                if not setting.startswith("PATH="):
                    continue
                entries = setting[5:].split(";")
                repaired = [replacement if entry == old else entry for entry in entries]
                if entries != repaired:
                    count += 1
                    prop["value"][index] = "PATH=" + ";".join(repaired)
    if not count:
        raise ContractError("The known single-config CMocka DLL path was not present")
    return result, count


def repair_cmocka_wrap_environment(discovery):
    result = copy.deepcopy(discovery)
    tests = {test["name"]: test for test in cases(result)}
    reference = tests.get("simple_test")
    target = tests.get("waiter_test_wrap")
    if reference is None or target is None:
        raise ContractError("CMocka environment repair requires the original simple/wrapped example pair")
    paths = [setting for prop in reference["properties"] if prop["name"] == "ENVIRONMENT"
             for setting in prop["value"] if setting.startswith("PATH=")]
    if len(paths) != 1 or paths[0] == "PATH=":
        raise ContractError("The passing CMocka helper must supply one explicit nonempty DLL search path")
    environments = [prop for prop in target["properties"] if prop["name"] == "ENVIRONMENT"]
    if len(environments) != 1 or environments[0]["value"] != ["PATH="]:
        raise ContractError("Expected the exact upstream out-of-scope DLL_PATH_ENV defect")
    environments[0]["value"] = paths
    return result


def bracket(value):
    if not isinstance(value, str) or "\0" in value:
        raise ContractError("CTest arguments must be strings without NUL")
    equals = ""
    while f"]{equals}]" in value + f"]{equals}":
        equals += "="
    # CMake discards the first newline after an opening bracket argument.
    return f"[{equals}[\n{value}]{equals}]"


def property_value(value):
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ";".join(item.replace(";", r"\;") for item in value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ContractError("Unsupported CTest property value; no property may be dropped")


def render(discovery):
    output = []
    for test in cases(discovery):
        name = bracket(test["name"])
        output.append("add_test(" + " ".join([name, *map(bracket, test["command"])]) + ")")
        for prop in test["properties"]:
            output.append(f"set_tests_properties({name} PROPERTIES "
                          f"{bracket(prop['name'])} {bracket(property_value(prop['value']))})")
    return "\n".join(output) + "\n"


def semantics(discovery):
    return {test["name"]: {"command": test["command"],
                           "properties": {prop["name"]: prop["value"] for prop in test["properties"]}}
            for test in cases(discovery)}


def test_results(path):
    tests = list(ET.parse(path).getroot().iter("testcase"))
    if not tests:
        raise ContractError("An empty CTest result does not qualify a native library")
    if any(test.find("failure") is not None or test.find("error") is not None for test in tests):
        raise ContractError("Native CMake dependency has failing upstream cases")
    skipped = [test.attrib.get("name") for test in tests if test.find("skipped") is not None]
    if skipped:
        raise ContractError(f"Unreviewed CTest skips require explicit investigation: {skipped}")
    return [test.attrib["name"] for test in tests]


def verify_build_files(build, expected, allowed_new=()):
    actual = inventory(build)
    changed = [name for name, row in expected.items() if actual.get(name) != row]
    extra = [name for name in actual.keys() - expected.keys()
             if not name.startswith("Testing/") and name not in allowed_new]
    if changed or extra:
        raise ContractError(f"Compiled CMake inputs changed: {sorted(changed + extra)[:20]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build-result", "ctest", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Exact original build-only result identity")
    args = parser.parse_args()
    result_path, ctest, output = (path.resolve() for path in (args.build_result, args.ctest, args.output))
    report_path = output.with_name(output.name + ".prepare.json")
    if os.name != "nt" or output.exists() or report_path.exists() or digest(result_path) != args.sha256:
        raise ContractError("Windows, fresh replay paths and the exact build-only result are required")
    original = json.loads(result_path.read_text(encoding="utf-8"))
    if (original.get("status") != "native-msys-cmake-built-not-tested" or
            original.get("package") != "cmocka" or original.get("inputs_unchanged") is not True or
            original["tools"].get(str(ctest)) != digest(ctest)):
        raise ContractError("Expected the successful CMocka build-only boundary and its original native CTest")
    build = result_path.parent / "build"
    if output.is_relative_to(build) or build.is_relative_to(output):
        raise ContractError("Test replay metadata must not overwrite the compiled input tree")
    verify_build_files(build, original["compiled_files"])
    if not (build / "src/msys-cmocka-0.dll").is_file():
        raise ContractError("The real single-config CMocka DLL is missing")
    output.mkdir(parents=True)
    for name in ("temp", "home"):
        (output / name).mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": str(ctest.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(output / "home"), "USERPROFILE": str(output / "home"),
                "TMP": str(output / "temp"), "TEMP": str(output / "temp"), "TMPDIR": str(output / "temp")})

    def discover(root, label):
        command = [str(ctest), "--test-dir", str(root), "--show-only=json-v1"]
        result = subprocess.run(command, env=env, capture_output=True, timeout=30)
        path = output / f"{label}.json"
        path.write_bytes(result.stdout)
        (output / f"{label}.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise ContractError("Native CTest metadata discovery failed; evidence retained")
        return json.loads(result.stdout), digest(path)

    source, source_sha = discover(build, "original-discovery")
    for test in cases(source):
        target = Path(test["command"][0]).resolve()
        if not target.is_relative_to(build) or target.suffix.lower() != ".exe" or not target.is_file():
            raise ContractError("CMocka replay may run only the actual original compiled target commands")
    repaired, count = repair_cmocka_path(source, build)
    (output / "CTestTestfile.cmake").write_text(render(repaired), encoding="utf-8", newline="\n")
    replay, replay_sha = discover(output, "replay-discovery")
    if semantics(replay) != semantics(repaired):
        raise ContractError("CTest replay changed an upstream command or property beyond the explicit DLL path repair")
    verify_build_files(build, original["compiled_files"])
    if digest(result_path) != args.sha256 or original["tools"][str(ctest)] != digest(ctest):
        raise ContractError("CMake build evidence or native CTest changed during replay preparation")
    record = {"schema": 1, "status": "cmocka-test-replay-prepared-not-executed",
              "build_result": {"path": str(result_path), "sha256": args.sha256},
              "build_root": str(build), "ctest": {"path": str(ctest), "sha256": digest(ctest)},
              "original_discovery_sha256": source_sha, "replay_discovery_sha256": replay_sha,
              "upstream_test_count": len(cases(source)), "repaired_path_count": count,
              "commands_and_other_properties_unchanged": True, "compiled_inputs_unchanged": True,
              "script_sha256": digest(__file__), "files": inventory(output),
              "scope": "Native CTest metadata roundtrip only; no target test execution, compilation or installation"}
    with report_path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(record, out, indent=2)
        out.write("\n")
    print(f"Prepared {record['upstream_test_count']} unchanged upstream commands; repaired {count} DLL paths; no tests executed")


if __name__ == "__main__":
    main()
