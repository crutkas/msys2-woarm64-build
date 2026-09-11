#!/usr/bin/env python3
"""Fault-inject the actual configured cygwin make targets in a disposable copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Owned copy containing source, prefix and configured build/winsup/cygwin")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stale-generator", type=Path, required=True)
    parser.add_argument("--stale-tls-generator", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    build = root / "build/winsup/cygwin"
    source = root / "source/winsup/cygwin"
    guard = source / "scripts/guard-runtime-generation"
    if not guard.is_file() or str(root) not in (build / "Makefile").read_text():
        raise ValueError("Use the newly configured owned proposal, never a preserved producer tree")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    if not out.is_relative_to(root):
        raise ValueError("Evidence and injected fixtures must stay within the owned proposal")
    fixtures = out / "fixtures"
    fixtures.mkdir()
    env = dict(os.environ, PATH=str(root / "prefix/bin") + ":/usr/bin:/bin", SOURCE_DATE_EPOCH="1788224411")
    names = ("tlsoffsets", "msys.def", "sigfe.s", "sigfe.o",
             "tlsoffsets.generation.json", "sigfe.s.generation.json")
    report = {"schema": 1, "status": "failed", "makefile_sha256": sha(build / "Makefile"),
              "source_makefile_sha256": sha(source / "Makefile.am"), "guard_sha256": sha(guard),
              "stale_generator_sha256": sha(args.stale_generator), "cases": []}

    def inventory():
        return {name: sha(build / name) if (build / name).exists() else None for name in names}

    def make(name, expect_success, *options, preserve=None, target="sigfe.o"):
        command = ["make", "-C", str(build), "-j1", "V=1", target, *options]
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        with stdout.open("xb") as a, stderr.open("xb") as b:
            result = subprocess.run(command, env=env, stdout=a, stderr=b, timeout=90)
        after = inventory()
        report["cases"].append({"name": name, "command": command, "exit": result.returncode,
                                "expectedSuccess": expect_success, "outputs": after,
                                "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)})
        if (result.returncode == 0) != expect_success:
            raise ValueError(f"Unexpected actual make result: {name}: {stderr.read_text()[-2000:]}")
        if not expect_success and not stderr.stat().st_size:
            raise ValueError(f"Failure was not diagnosed: {name}")
        if preserve is not None and after != preserve:
            raise ValueError(f"Failed generation changed existing artifacts: {name}")

    def signal_fixture(name, action):
        path = fixtures / name
        path.write_text(
            "#!/usr/bin/env perl\nuse strict; use warnings;\n"
            "use Getopt::Long; my ($cpu, $out); my @original = @ARGV;\n"
            "GetOptions('cpu=s'=>\\$cpu,'output-def=s'=>\\$out) or die;\n"
            f"system($^X, {json.dumps(str(source / 'scripts/gendef'))}, @original) == 0 or die;\n"
            + action + "\n", encoding="utf-8", newline="\n")
        return "SIGNAL_GENERATOR=" + str(path)

    try:
        # Recompile the copied object with this configured build's own flags,
        # so the later clean-regeneration comparison has the same debug paths.
        if (build / "sigfe.o").exists():
            (out / "copied-sigfe.o").write_bytes((build / "sigfe.o").read_bytes())
            (build / "sigfe.o").unlink()
        make("initial-valid-generation", True)
        good = inventory()
        raw = (build / "sigfe.o").read_bytes()
        if struct.unpack_from("<H", raw)[0] != 0xaa64:
            raise ValueError("Successful actual make did not produce ARM64 COFF")
        times = {name: (build / name).stat().st_mtime_ns for name in names}
        make("unchanged-repeat", True, preserve=good)
        if {name: (build / name).stat().st_mtime_ns for name in names} != times:
            raise ValueError("Unchanged make rewrote/reassembled valid generated artifacts")
        saved = {name: (build / name).read_bytes() for name in names}

        make("real-stale-x86-generator", False,
             "SIGNAL_GENERATOR=" + str(args.stale_generator.resolve()), preserve=good)
        make("empty-assembly-after-zero-exit", False,
             signal_fixture("empty-signal", "open my $f, '>', 'sigfe.s' or die; close $f or die;"), preserve=good)
        make("generator-fails-after-writing", False,
             signal_fixture("failed-signal", "die \"injected late generator failure\\n\";"), preserve=good)
        make("missing-trampoline-label", False, signal_fixture("missing-label",
             "local $/; open my $f, '<', 'sigfe.s' or die; my $s=<$f>; close $f;\n"
             "$s =~ s/^_sigfe_malloc:/_removed_malloc:/m or die;\n"
             "open $f, '>', 'sigfe.s' or die; print $f $s; close $f or die;"), preserve=good)
        make("dropped-source-export-from-both", False, signal_fixture("dropped-export",
             "local $/; open my $f, '<', $out or die; my $s=<$f>; close $f;\n"
             "$s =~ s/^malloc\\s*=.*\\n//m or die;\n"
             "open $f, '>', $out or die; print $f $s; close $f or die;\n"
             "open $f, '<', 'sigfe.s' or die; $s=<$f>; close $f;\n"
             "$s =~ s/^_sigfe_malloc:/_removed_malloc:/m or die;\n"
             "open $f, '>', 'sigfe.s' or die; print $f $s; close $f or die;"), preserve=good)

        for name, data in (("zero-offsets", ".equ _cygtls.start_offset, 0\n"),
                           ("malformed-offsets", "not a TLS offset\n")):
            generator = fixtures / name
            generator.write_text("#!/usr/bin/env bash\nset -eu\nprintf '%s' "
                                 + "'" + data.replace("'", "'\\''") + "' > \"$2\"\n",
                                 encoding="utf-8", newline="\n")
            make(name, False, "GENTLS_OFFSETS=" + str(generator), preserve=good)
        make("compiler-failure", False, "CXXCOMPILE=false", preserve=good, target="tlsoffsets")
        if args.stale_tls_generator:
            make("real-long-only-tls-generator", False,
                 "GENTLS_OFFSETS=" + str(args.stale_tls_generator.resolve()), preserve=good)
            # The old script only accepts a basename (it constructs /tmp/$2.$$).
            # Adapt the output pathname, not its parser, to reproduce .word loss.
            adapter = fixtures / "historical-tls-basename"
            captured = fixtures / "historical-tls-output"
            adapter.write_text(
                "#!/usr/bin/env bash\nset -u\n"
                "saved=.historical-tls-$$\ntrap 'rm -f -- \"$saved\"' EXIT\nstatus=0\n"
                f"bash {shlex.quote(str(args.stale_tls_generator.resolve()))} \"$1\" \"$saved\" || status=$?\n"
                "if [[ -f $saved ]]; then\n"
                f"  cp -- \"$saved\" {shlex.quote(str(captured))}\n"
                "  mv -- \"$saved\" \"$2\"\nfi\nexit \"$status\"\n",
                encoding="utf-8", newline="\n")
            make("real-long-only-parser-with-relative-output", False,
                 "GENTLS_OFFSETS=" + str(adapter), preserve=good)
            if not captured.is_file():
                raise ValueError("Historical parser did not produce its invalid offset payload")
            report["historical_tls_payload"] = {
                "path": str(captured), "bytes": captured.stat().st_size, "sha256": sha(captured),
                "text": captured.read_text(),
                "scope": "Unmodified old parser; wrapper only adapts its basename-only output convention."}

        for name in ("sigfe.s", "tlsoffsets", "msys.def"):
            path = build / name
            try:
                path.write_bytes(b"")
                os.utime(path, ns=(path.stat().st_atime_ns, times[name] + 10_000_000_000))
                corrupt = inventory()
                make("reject-newer-corrupt-" + name.replace(".", "-"), False, preserve=corrupt)
            finally:
                path.write_bytes(saved[name])
                os.utime(path, ns=(path.stat().st_atime_ns, times[name]))

        # Drop all generated outputs/receipts only in this disposable copy;
        # normal make must regenerate both stages with the real compiler.
        for name in names:
            (build / name).unlink()
        make("clean-regeneration", True)
        regenerated = inventory()
        for name in ("tlsoffsets", "msys.def", "sigfe.s", "sigfe.o"):
            if regenerated[name] != good[name]:
                raise ValueError(f"Clean regeneration changes qualified bytes: {name}")
        report.update(status="actual-runtime-make-generation-guards-qualified",
                      casesPassed=len(report["cases"]), generated=regenerated,
                      limits="Host generation/actual make and ARM64 assembly only; no DLL rebuild or changed runtime ABI.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
