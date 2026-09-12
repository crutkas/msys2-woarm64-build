"""Bootstrap native MSYS Perl using a C-qualified, not fully C++-qualified, native SDK."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from compiler_tools import support_identities, verify_support
from perl_safety import verify_guards
from perl_profiles import PROFILES, STRICT_PROFILE, SYSTEM_PROFILE
from sources import ContractError, digest, inventory, verify_tree


def main():
    profile_parser = argparse.ArgumentParser(add_help=False)
    profile_parser.add_argument("--profile", choices=PROFILES, default=STRICT_PROFILE)
    selected, remaining = profile_parser.parse_known_args()
    if selected.profile == SYSTEM_PROFILE:
        from perl_system_bootstrap import main as build_system_profile
        build_system_profile(remaining)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.epilog = "Default profile: nativestrict. Explicit alternative: --profile msys-system-symlink-bootstrap --help."
    for name in ("source", "manifest", "handoff", "native-root", "msys", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 11), required=True)
    args = parser.parse_args(remaining)
    if os.name != "nt" or args.output.exists() or digest(args.handoff) != args.handoff_sha256:
        raise ContractError("Need Windows, a new output, and the exact scoped native-toolchain receipt")
    if not args.msys.resolve().is_relative_to(args.output.parent.resolve()):
        raise ContractError("Perl requires a private bootstrap copy under its own artifact parent, not another lane's prefix")
    handoff = json.loads(args.handoff.read_text())
    if (handoff["Status"] != "c-qualified" or handoff["Target"] != "aarch64-pc-cygwin/MSYS"
            or handoff["FullCppQualified"] is not False or handoff["Immutable"] is not True):
        raise ContractError("Expected the explicit C-only bootstrap cohort; not a full package admission")
    prefix = Path(handoff["Prefix"])
    expected = {row["Path"].replace("\\", "/"): row["SHA256"] for row in handoff["Files"]}
    actual = inventory(prefix)
    if {name: row["sha256"] for name, row in actual.items()} != expected:
        raise ContractError("Native toolchain complete file-set or hash mismatch")
    proof = handoff["Proof"]
    if digest(proof["Path"]) != proof["SHA256"]:
        raise ContractError("Native toolchain execution proof changed")
    verify_tree(args.source, args.manifest)
    verify_guards(args.source)
    bootstrap_files = inventory(args.msys)
    native_files = inventory(args.native_root)
    if native_files["usr/bin/msys-2.0.dll"]["sha256"] != expected["bin/msys-2.0.dll"]:
        raise ContractError("Native shell root and compiler target runtime differ")
    args.output.mkdir(parents=True)
    toolchain = args.output / "toolchain"
    shutil.copytree(prefix, toolchain)
    if inventory(toolchain) != actual:
        raise ContractError("Relocated native toolchain copy differs")
    shutil.copytree(args.source, args.output / "source")
    scripts = Path(__file__).parent.resolve()
    env = {name: os.environ[name] for name in (
        "SystemRoot", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT",
        "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS") if name in os.environ}
    env["HOME"] = env["USERPROFILE"] = str(args.output / "home")
    (args.output / "home").mkdir()
    env["PATH"] = os.pathsep.join(map(str, (args.native_root / "usr/bin", toolchain / "bin",
                                           args.msys / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    compiler = toolchain / "bin/gcc.exe"
    support = support_identities(compiler, toolchain, env)
    recipe = scripts / "build-native-perl.sh"
    patch = scripts / "patches/perl-msys-external-toolchain.patch"
    guard_patch = scripts / "patches/perl-empty-symlink-predicate.patch"
    arch_guard = scripts / "perl-native-arch-guard.sh"
    command = [args.msys / "usr/bin/bash.exe", "--noprofile", "--norc", recipe.as_posix(),
               args.output, toolchain, args.native_root, args.msys, patch, str(args.jobs)]
    report = {"status": "failed", "command": list(map(str, command)),
              "toolchain_handoff_sha256": digest(args.handoff), "support": support,
              "source_manifest_sha256": digest(args.manifest),
              "native_root": native_files, "patch_sha256": digest(patch),
              "private_bootstrap": bootstrap_files,
              "symlink_guard_sha256": digest(guard_patch),
              "architecture_guard_sha256": digest(arch_guard),
              "environment_policy": "minimal Windows variables; private HOME; no inherited credentials",
              "recipe_sha256": digest(recipe), "jobs": args.jobs,
              "scope": "C-only native Windows MSYS compiler bootstrap; initial Configure and utility fallback are emulated",
              "limitations": ["Not full MSYS C++ qualification", "Full dependency and distribution integration pending"]}
    try:
        with (args.output / "build.log").open("xb") as log:
            result = subprocess.run(list(map(str, command)), env=env, stdout=log, stderr=subprocess.STDOUT)
        report["exit"] = result.returncode
        if result.returncode:
            raise ContractError(f"Native Perl bootstrap failed; inspect {args.output / 'build.log'}")
        verify_tree(args.source, args.manifest)
        verify_support(support, compiler, toolchain, env)
        if (inventory(toolchain) != actual or inventory(args.native_root) != native_files
                or inventory(args.msys) != bootstrap_files):
            raise ContractError("Build inputs changed")
        report["files"] = inventory(args.output / "stage")
        report["status"] = "native-msys-perl-built-tested-bootstrap-drivers"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
