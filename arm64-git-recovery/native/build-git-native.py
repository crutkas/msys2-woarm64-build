"""Build the pinned full Git feature set with native GCC and isolated bootstrap orchestration."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "recipes", "recipe-manifest", "prefix", "dependencies",
                 "bootstrap", "bootstrap-receipt", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Requires native Windows and a new build output")
    if not args.bootstrap.resolve().is_relative_to(args.output.parent.resolve()):
        raise ContractError("Git build must use a build-owned bootstrap copy")
    verify_tree(args.source, args.manifest)
    source_record = json.loads(args.manifest.read_text())
    if (source_record["source"]["version"] != "2.55.0.windows.5"
            or source_record.get("export_scope") != "full-source-file-contents"):
        raise ContractError("Expected the complete pinned Git source export")
    verify_tree(args.recipes, args.recipe_manifest)
    bootstrap_receipt = json.loads(args.bootstrap_receipt.read_text())
    bootstrap_files = inventory(args.bootstrap)
    if bootstrap_receipt["files"] != bootstrap_files:
        raise ContractError("Private bootstrap copy changed")
    dependency_files = inventory(args.dependencies)
    for path in ("include/curl/curl.h", "include/pcre2.h", "include/expat.h", "include/libintl.h",
                 "bin/libcurl-4.dll", "lib/libcurl.dll.a"):
        if path not in dependency_files:
            raise ContractError(f"Required Git dependency missing: {path}")
    env = {name: os.environ[name] for name in (
        "SystemRoot", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "PATHEXT", "TMP", "TEMP") if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.prefix / "bin", args.dependencies / "bin",
                                                 args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output.with_name(args.output.name + ".launch-home")),
                "USERPROFILE": str(args.output.with_name(args.output.name + ".launch-home")),
                "MSYS2_PATH_TYPE": "minimal", "CHERE_INVOKING": "1"})
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    tools = {str(path): digest(path) for path in (compiler, args.prefix / "bin/ar.exe",
                                                args.prefix / "bin/windres.exe", args.bootstrap / "usr/bin/bash.exe",
                                                args.bootstrap / "usr/bin/make.exe", args.bootstrap / "usr/bin/perl.exe")}
    script = Path(__file__).with_suffix(".sh").resolve()
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
               args.source, args.recipes, args.prefix, args.dependencies, args.output, str(args.jobs)]
    report = {"status": "failed", "source": source_record["source"],
              "source_manifest_sha256": digest(args.manifest), "recipe_manifest_sha256": digest(args.recipe_manifest),
              "bootstrap_receipt_sha256": digest(args.bootstrap_receipt), "tools": tools, "support": support,
              "dependencies": dependency_files, "command": list(map(str, command)), "recipe_sha256": digest(script),
              "build_host": "windows-arm64-native-compiler", "orchestration": "isolated-x64-MSYS-bootstrap",
              "feature_policy": "Full core/HTTP/Perl/Tcl script targets retained; upstream C fallback for optional Rust",
              "pending": ["Native full runtime/package assembly", "Git functional acceptance",
                          "Native Perl/Tcl/editor/SSH runtime closure", "nghttp2 upstream-test compiler repair",
                          "OpenSSL complete-suite closure"]}
    try:
        for name, root in (("compiler", args.prefix), ("dependencies", args.dependencies)):
            gate = args.output.with_name(args.output.name + f".{name}-native.json")
            subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                            "-Root", str(root), "-ReportPath", str(gate)], env=env, check=True)
            if json.loads(gate.read_text()).get("Passed") is not True:
                raise ContractError("Native build input gate failed")
        with args.output.with_name(args.output.name + ".launch.log").open("xb") as log:
            result = subprocess.run(list(map(str, command)), env=env, stdout=log, stderr=subprocess.STDOUT)
        report["exit"] = result.returncode
        if result.returncode:
            raise ContractError(f"Git build failed; inspect {args.output / 'build.log'}")
        runtime_copies = {}
        for dll in (args.dependencies / "bin").glob("*.dll"):
            destination = args.output / "stage/clangarm64/bin" / dll.name
            if destination.exists() and digest(destination) != digest(dll):
                raise ContractError(f"Conflicting Git runtime DLL: {dll.name}")
            shutil.copyfile(dll, destination)
            runtime_copies[dll.name] = {"source": str(dll), "sha256": digest(dll)}
        report["runtime_dll_copies"] = runtime_copies
        verify_tree(args.source, args.manifest)
        verify_tree(args.recipes, args.recipe_manifest)
        verify_support(support, compiler, args.prefix, env)
        if (inventory(args.dependencies) != dependency_files or inventory(args.bootstrap) != bootstrap_files
                or any(digest(path) != value for path, value in tools.items())):
            raise ContractError("Git build input changed")
        report["files"] = inventory(args.output / "stage")
        for path in ("clangarm64/bin/git.exe", "clangarm64/libexec/git-core/git-remote-http.exe",
                     "clangarm64/libexec/git-core/git-send-email", "cmd/git.exe", "git-bash.exe"):
            if path not in report["files"]:
                raise ContractError(f"Git installation omitted a required feature: {path}")
        output_gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(args.output / "stage"), "-ReportPath", str(output_gate)], env=env, check=True)
        if json.loads(output_gate.read_text()).get("Passed") is not True:
            raise ContractError("Git output native PE gate failed")
        report["status"] = "native-full-feature-git-built-not-distribution-accepted"
    finally:
        args.output.with_name(args.output.name + ".result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
