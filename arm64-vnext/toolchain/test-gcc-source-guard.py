#!/usr/bin/env python3
"""Exercise the actual GCC source guard in a new pinned private checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess

RECIPE = Path(__file__).resolve().parent
load_lock = runpy.run_path(str(RECIPE / "source-lock.py"))["load_lock"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="Read-only pinned GCC Git dependency")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--producer-direct-sp", type=Path,
                        help="Optional frozen CMocka producer's LF direct-SP patch")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    lock = load_lock(RECIPE)
    revision = lock["sources"]["gcc"]["revision"]
    patches = lock["sources"]["gcc"]["patches"]
    if [p["file"] for p in patches[-2:]] != [
            "gcc-arm64-pe-salted-guard.patch", "libgcc-arm64-unwind-context.patch"]:
        raise ValueError("Expected the guarded compiler and unwind-context patch successors")
    if args.producer_direct_sp:
        args.producer_direct_sp = args.producer_direct_sp.resolve(strict=True)
        if digest(args.producer_direct_sp.read_bytes()) != (
                "cfccc4de9849a50b5687b0a50a945abcd34dbf96dfe82d3f8ea4918761f2772c"):
            raise ValueError("Unexpected CMocka producer direct-SP patch identity")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    checkout = out / "sources" / "gcc"
    checkout.parent.mkdir()
    (out / "identities").mkdir()
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    report = {"passed": False, "source": str(source), "revision": revision,
              "source_lock_sha256": digest(json.dumps(
                  lock, sort_keys=True, separators=(",", ":")).encode()),
              "gcc_patch_count": len(patches), "controls": []}

    def git(directory, *arguments, index=None):
        git_env = dict(env)
        if index is not None:
            git_env["GIT_INDEX_FILE"] = str(index)
        return subprocess.check_output(["git", "-C", str(directory), *arguments], env=git_env)

    def source_state():
        return {
            "head": git(source, "rev-parse", "HEAD").decode().strip(),
            "diff_sha256": digest(git(source, "diff", "--binary", "HEAD")),
            "untracked_sha256": digest(git(source, "ls-files", "--others", "--exclude-standard")),
        }

    before = source_state()
    if before["head"] != revision:
        raise ValueError("Dependency is not at the pinned GCC revision")
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                    str(source), str(checkout)], env=env, check=True)
    git(checkout, "-c", "core.autocrlf=false", "checkout", "--quiet", "--detach", revision)
    index = checkout / ".git" / "index"
    original_index = digest(index.read_bytes())
    bootstrap = (RECIPE / "bootstrap-cygwin.sh").read_text(encoding="utf-8")
    start = bootstrap.index("check_source() {")
    function = bootstrap[start:bootstrap.index("\nconfigure_build()", start)]
    runner = out / "check-source.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'fail() { printf "ERROR: %s\\n" "$*" >&2; exit 1; }\n'
        + function + '\ncheck_source gcc "$TEST_REVISION"\n', encoding="utf-8", newline="\n")
    guard_env = dict(env, ROOT=str(out), RECIPE=str(RECIPE), TEST_REVISION=revision)

    def guard(name, expected_success):
        result = subprocess.run(["bash", str(runner)], env=guard_env, capture_output=True)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["controls"].append({"name": name, "exit": result.returncode,
                                   "expected_success": expected_success})
        if (result.returncode == 0) != expected_success:
            raise ValueError(f"Unexpected source-guard result: {name}: {result.stderr!r}")
        if not expected_success and b"Unexpected gcc source delta" not in result.stderr:
            raise ValueError(f"Failure did not come from the source-delta guard: {name}")

    try:
        emutls = checkout / "gcc" / "tree-emutls.cc"
        aarch64 = checkout / "gcc" / "config" / "aarch64" / "aarch64.cc"
        unwind = checkout / "libgcc" / "unwind-seh.c"
        pristine = emutls.read_bytes()
        guard("pristine-applies", True)
        patched = emutls.read_bytes()
        if patched == pristine or b"fixup_returns_twice_call (node," not in patched:
            raise ValueError("The actual guard did not apply the emutls fix")
        patched_aarch64 = aarch64.read_bytes()
        if b"legitimize_pe_coff_symbol (unsalted_base, false)" not in patched_aarch64:
            raise ValueError("The actual guard did not apply the salted guard fix")
        patched_unwind = unwind.read_bytes()
        if digest(patched_unwind) != "acfad2dc93fb97eca6e054a3d1654d5cba40eb89d3881bdf9440605e0999f2b8":
            raise ValueError("The actual guard did not apply the exact unwind context fix")
        expected_index = out / "identities" / "gcc-expected.index"
        expected_tree = git(checkout, "write-tree", index=expected_index).decode().strip()
        guard("already-patched-resumes", True)
        if emutls.read_bytes() != patched:
            raise ValueError("An accepted resume changed the compiler source")
        git(checkout, "apply", "--reverse", str(RECIPE / patches[-1]["file"]))
        guard("twenty-one-patch-predecessor-resumes", True)
        if unwind.read_bytes() != patched_unwind:
            raise ValueError("Unwind predecessor resume differs")
        for patch in reversed(patches[-2:]):
            git(checkout, "apply", "--reverse", str(RECIPE / patch["file"]))
        if digest(aarch64.read_bytes()) != "8cf5d5d6b540bc5bb696c319e18f9e07a38f47924f19c88af7adb6cd209c945c":
            raise ValueError("The exact f54 aarch64 source predecessor was not restored")
        guard("twenty-patch-predecessor-resumes", True)
        if (emutls.read_bytes() != patched or aarch64.read_bytes() != patched_aarch64
                or unwind.read_bytes() != patched_unwind):
            raise ValueError("Predecessor resume did not apply the final guard fix")
        unwind_tamper = patched_unwind + b"\n/* private unwind-context drift control */\n"
        unwind.write_bytes(unwind_tamper)
        guard("unwind-context-drift-rejected", False)
        if unwind.read_bytes() != unwind_tamper:
            raise ValueError("Rejected unwind changes were not preserved")
        unwind.write_bytes(patched_unwind)
        guarded_tamper = patched_aarch64 + b"\n/* private stack-guard drift control */\n"
        aarch64.write_bytes(guarded_tamper)
        guard("stack-guard-drift-rejected", False)
        if aarch64.read_bytes() != guarded_tamper:
            raise ValueError("Rejected stack-guard changes were not preserved")
        aarch64.write_bytes(patched_aarch64)
        tampered = patched + b"\n/* private tracked-drift control */\n"
        emutls.write_bytes(tampered)
        guard("tracked-drift-rejected", False)
        if emutls.read_bytes() != tampered:
            raise ValueError("Rejected tracked source changes were not preserved")
        emutls.write_bytes(patched)
        marker = checkout / "unexpected-source-control"
        marker.write_bytes(b"private untracked-drift control\n")
        guard("untracked-drift-rejected", False)
        if marker.read_bytes() != b"private untracked-drift control\n" or emutls.read_bytes() != patched:
            raise ValueError("Rejected untracked source changes were not preserved")
        def variant_tree(name, direct_sp):
            variant_index = out / "identities" / (name + ".index")
            git(checkout, "read-tree", revision, index=variant_index)
            for entry in patches:
                patch = (direct_sp if entry["file"] == "gcc-arm64-seh-sp-direct-save-portable.patch"
                         else RECIPE / entry["file"])
                git(checkout, "apply", "--cached", str(patch), index=variant_index)
            return git(checkout, "write-tree", index=variant_index).decode().strip()

        if args.producer_direct_sp:
            producer_tree = variant_tree("producer-variant", args.producer_direct_sp)
            if producer_tree != expected_tree:
                raise ValueError("Producer direct-SP patch changes the resulting GCC tree")
            report["producer_variant_tree_sha1"] = producer_tree
        legacy = (RECIPE / "gcc-arm64-seh-sp-direct-save.patch").read_bytes()
        if digest(legacy) != "88fe85505db8a692f21993e80e432d52ac712b75875b698dc6217a69ef9ce6bc":
            raise ValueError("The original direct-SP provenance artifact was changed")
        normalized_legacy = out / "legacy-direct-sp-lf.patch"
        normalized_legacy.write_bytes(legacy.replace(b"\r\n", b"\n"))
        legacy_tree = variant_tree("normalized-legacy", normalized_legacy)
        if legacy_tree != expected_tree:
            raise ValueError("The portable direct-SP patch changes source semantics")
        report["normalized_legacy_tree_sha1"] = legacy_tree
        if digest(index.read_bytes()) != original_index or source_state() != before:
            raise ValueError("The guard changed the real index or read-only dependency")
        report.update({
            "passed": True, "guard_sha256": digest(function.encode()),
            "expected_tree_sha1": expected_tree,
            "pristine_emutls_sha256": digest(pristine),
            "patched_emutls_sha256": digest(patched),
            "patched_aarch64_sha256": digest(patched_aarch64),
            "patched_winnt_sha256": digest((checkout / "gcc" / "config" / "mingw" / "winnt.cc").read_bytes()),
            "original_dependency_unchanged": True, "real_index_unchanged": True,
        })
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"GCC source guard controls passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
