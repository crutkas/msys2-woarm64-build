"""Run a sealed Bash continuation recipe with the recovered native observer."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import sys


MAINTAINED = Path(r"C:\ag-native-e138-01\maintained")
OBSERVER = Path(r"C:\ag-native-e138-01\native-test-driver-06")
ALLOWED_RECIPES = {
    "assemble-bash-sdk.py",
    "build-bash-nls.py",
    "build-full-bash.py",
    "check-full-bash.py",
    "test-bash-nls.py",
}


class RecipeOverlay:
    def __truediv__(self, name):
        overlays = {
            "build-bash-nls.sh": "build-bash-nls-recovery.sh",
            "build-full-bash.sh": "build-full-bash-recovery-v3.sh",
            "check-full-bash.sh": "check-full-bash-recovery.sh",
        }
        if str(name) in overlays:
            return Path(__file__).with_name(overlays[str(name)])
        return MAINTAINED / name


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", choices=sorted(ALLOWED_RECIPES))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    recipe = MAINTAINED / args.recipe
    manifest = OBSERVER.with_name(OBSERVER.name + ".manifest.json")
    if not recipe.is_file() or not manifest.is_file():
        parser.error("The maintained recipe and recovered observer must be staged first")

    sys.path.insert(0, str(MAINTAINED))
    inputs = importlib.import_module("readline_chain_inputs")
    inputs.SEALS["observer"] = digest(manifest)
    terminal = importlib.import_module("build-readline-chain")
    terminal.OBSERVER = OBSERVER
    inputs.HERE = RecipeOverlay()

    if args.recipe == "build-full-bash.py":
        build_parser = argparse.ArgumentParser(description="Run the recovered full Bash build")
        build_parser.add_argument("--output", required=True)
        build_parser.add_argument("--sdk", required=True)
        build_parser.add_argument("--jobs", required=True, type=int, choices=range(1, 7))
        importlib.import_module("build-full-bash").main(build_parser.parse_args(args.arguments))
        return

    if args.recipe == "check-full-bash.py":
        check_parser = argparse.ArgumentParser(description="Run Bash tests with native utility providers")
        check_parser.add_argument("--build", required=True)
        check_parser.add_argument("--sdk", required=True)
        check_parser.add_argument("--output", required=True)
        check_parser.add_argument("--utilities-stage", required=True, type=Path)
        check_parser.add_argument("--utilities-manifest", required=True, type=Path)
        check_parser.add_argument("--runtime", required=True, type=Path)
        check_parser.add_argument("--runtime-sha256", required=True)
        check_args = check_parser.parse_args(args.arguments)
        utilities = check_args.utilities_stage.resolve()
        manifest = check_args.utilities_manifest.resolve()
        runtime = check_args.runtime.resolve()
        runtime_sha256 = check_args.runtime_sha256.lower()
        if len(runtime_sha256) != 64 or any(
                character not in "0123456789abcdef" for character in runtime_sha256):
            check_parser.error("The runtime SHA-256 must contain 64 hexadecimal characters")
        sources = importlib.import_module("sources")
        sources.verify_tree(utilities, manifest)
        if digest(runtime) != runtime_sha256:
            check_parser.error("The sealed native environment runtime differs")
        check = importlib.import_module("check-full-bash")
        original_environment = check.nls.environment

        def recovery_environment(output, jobs):
            environment = original_environment(output, jobs)
            environment.update({
                "NATIVE_BASH_TEST_UTILITIES": str(utilities),
                "NATIVE_BASH_TEST_RUNTIME": str(runtime),
                "NATIVE_BASH_TEST_RUNTIME_SHA256": runtime_sha256,
            })
            return environment

        check.nls.environment = recovery_environment
        result_path = check.ROOT / check_args.output / "result.json"
        try:
            check.main(check_args)
        finally:
            if result_path.is_file():
                result = json.loads(result_path.read_text())
                helper_root = check.ROOT / check_args.build / "source/tests"
                result["recovery_native_test_providers"] = {
                    "utilities_stage": str(utilities),
                    "utilities_manifest": str(manifest),
                    "utilities_manifest_sha256": digest(manifest),
                    "runtime": str(runtime),
                    "runtime_sha256": runtime_sha256,
                    "helpers": {
                        name: digest(helper_root / name)
                        for name in ("printenv.exe", "recho.exe", "xcase.exe", "zecho.exe")
                    },
                    "native_helper_patch_sha256": digest(
                        Path(__file__).with_name("bash-5.3-native-test-helpers.patch")),
                    "case_timeout_patch_sha256": digest(
                        Path(__file__).with_name("bash-5.3-bound-case-timeouts.patch")),
                    "host_utilities_excluded_from_test_path": True,
                    "msys_policy": "winsymlinks:sys",
                }
                result_path.write_text(json.dumps(result, indent=2) + "\n")
        return

    sys.argv = [str(recipe), *args.arguments]
    runpy.run_path(str(recipe), run_name="__main__")


if __name__ == "__main__":
    main()
