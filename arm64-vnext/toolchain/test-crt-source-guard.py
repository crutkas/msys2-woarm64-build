#!/usr/bin/env python3
"""Exercise the actual bootstrap CRT guard in a private pinned checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

RECIPE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="Read-only pinned mingw-woarm64 Git dependency")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    lock = json.loads((RECIPE / "source-lock.json").read_text(encoding="utf-8"))
    revision = lock["sources"]["mingw-woarm64"]["revision"]
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    checkout = out / "sources" / "mingw-woarm64"
    checkout.parent.mkdir()
    (out / "identities").mkdir()
    report = {"passed": False, "source": str(source), "revision": revision, "controls": []}

    def git(directory, *arguments):
        return subprocess.check_output(["git", "-C", str(directory), *arguments], env=env)

    def source_state():
        return {
            "head": git(source, "rev-parse", "HEAD").decode().strip(),
            "diff_sha256": digest(git(source, "diff", "--binary", "HEAD")),
            "untracked_sha256": digest(git(source, "ls-files", "--others", "--exclude-standard")),
        }

    before = source_state()
    if before["head"] != revision:
        raise ValueError("The dependency is not at the locked CRT revision")
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(source),
                    str(checkout)], env=env, check=True)
    subprocess.run(["git", "-C", str(checkout), "-c", "core.autocrlf=false",
                    "checkout", "--quiet", "--detach", revision], env=env, check=True)
    index = checkout / ".git" / "index"
    original_index = digest(index.read_bytes())
    bootstrap = (RECIPE / "bootstrap-cygwin.sh").read_text(encoding="utf-8")
    start = bootstrap.index("check_source() {")
    end = bootstrap.index("\nconfigure_build()", start)
    function = bootstrap[start:end]
    runner = out / "check-source.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'fail() { printf "ERROR: %s\\n" "$*" >&2; exit 1; }\n'
        + function + '\ncheck_source mingw-woarm64 "$TEST_REVISION"\n',
        encoding="utf-8", newline="\n")
    guard_env = dict(env, ROOT=str(out), RECIPE=str(RECIPE), TEST_REVISION=revision)

    def guard(name, expected_success):
        result = subprocess.run(["bash", str(runner)], env=guard_env, capture_output=True)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["controls"].append({"name": name, "exit": result.returncode,
                                   "expected_success": expected_success})
        if (result.returncode == 0) != expected_success:
            raise ValueError(f"Unexpected guard result: {name}: {result.stderr!r}")
        if not expected_success and b"Unexpected mingw-woarm64 source delta" not in result.stderr:
            raise ValueError(f"Failure did not come from the source-delta guard: {name}")

    try:
        template = checkout / "mingw-w64-crt" / "complex" / "cexp.def.h"
        header = checkout / "mingw-w64-headers" / "crt" / "_mingw.h.in"
        intrinsics = checkout / "mingw-w64-headers" / "include" / "psdk_inc" / "intrin-impl.h"
        interlocked = lock["sources"]["mingw-woarm64"]["patches"][-1]
        identity = interlocked["source_identity"]
        if digest(intrinsics.read_bytes()) != identity["before_sha256"]:
            raise ValueError("Pinned Interlocked header differs")
        pristine = template.read_bytes()
        pristine_header = header.read_bytes()
        guard("pristine-applies", True)
        patched = template.read_bytes()
        patched_header = header.read_bytes()
        if patched == pristine or b"* volatile sincos_fn)" not in patched:
            raise ValueError("The real CRT patch was not applied by the bootstrap guard")
        if patched_header != pristine_header.replace(
                b"#define __MINGW_FASTFAIL_INLINE static inline\n",
                b"#define __MINGW_FASTFAIL_INLINE static __inline__\n"):
            raise ValueError("The real C89 header patch was not applied by the bootstrap guard")
        if patched_header == pristine_header:
            raise ValueError("The C89 header source did not change")
        patched_intrinsics = intrinsics.read_bytes()
        if digest(patched_intrinsics) != identity["after_sha256"]:
            raise ValueError("The actual source guard did not apply the Interlocked ordering fix")
        guard("already-patched-resumes", True)
        if (template.read_bytes() != patched or header.read_bytes() != patched_header or
                intrinsics.read_bytes() != patched_intrinsics):
            raise ValueError("An accepted resume changed a MinGW template")
        git(checkout, "apply", "--reverse", str(RECIPE / interlocked["file"]))
        guard("two-patch-header-predecessor-resumes", True)
        if intrinsics.read_bytes() != patched_intrinsics:
            raise ValueError("Predecessor resume did not apply the exact Interlocked fix")
        intrinsic_drift = patched_intrinsics + b"\n/* private Interlocked header drift */\n"
        intrinsics.write_bytes(intrinsic_drift)
        guard("interlocked-header-drift-rejected", False)
        if intrinsics.read_bytes() != intrinsic_drift:
            raise ValueError("Rejected Interlocked header drift was not preserved")
        intrinsics.write_bytes(patched_intrinsics)
        header_tampered = patched_header + b"\n/* private header-drift control */\n"
        header.write_bytes(header_tampered)
        guard("header-drift-rejected", False)
        if header.read_bytes() != header_tampered:
            raise ValueError("Rejected header source changes were not preserved")
        header.write_bytes(patched_header)
        tampered = patched + b"\n/* private tracked-drift control */\n"
        template.write_bytes(tampered)
        guard("tracked-drift-rejected", False)
        if template.read_bytes() != tampered:
            raise ValueError("Rejected tracked source changes were not preserved")
        template.write_bytes(patched)
        marker = checkout / "unexpected-source-control"
        marker.write_bytes(b"private untracked-drift control\n")
        guard("untracked-drift-rejected", False)
        if marker.read_bytes() != b"private untracked-drift control\n" or template.read_bytes() != patched:
            raise ValueError("Rejected untracked source changes were not preserved")
        if digest(index.read_bytes()) != original_index:
            raise ValueError("The guard modified the checkout's real Git index")
        if source_state() != before:
            raise ValueError("The read-only original dependency changed during the controls")
        report.update({
            "passed": True, "guard_sha256": digest(function.encode()),
            "pristine_template_sha256": digest(pristine),
            "patched_template_sha256": digest(patched),
            "pristine_header_sha256": digest(pristine_header),
            "patched_header_sha256": digest(patched_header),
            "interlocked_header": identity,
            "original_dependency_unchanged": True, "real_index_unchanged": True,
        })
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"CRT source guard controls passed: {out / 'result.json'}")


if __name__ == "__main__":
    main()
