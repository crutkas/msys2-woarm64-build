"""Replay only Perl's unchanged symlink selection and Makefile generator at the native compiler boundary."""

import argparse
import json
from pathlib import Path
import shutil

from bounded_process import run
from perl_profiles import SYSTEM_PROFILE, profile_record
from perl_safety import GUARDS, verify_guards
from perl_system_bootstrap import environment
from perl_system_inputs import require_separate_output, verify_cohort
from sources import ContractError, digest, verify_tree


def between(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ContractError("Pinned Perl generator boundary changed")
    first = text.index(start)
    last = text.index(end, first)
    return text[first:last]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cohort = verify_cohort(args.cohort)
    output = args.output.resolve()
    if output.exists():
        raise ContractError("A fresh upstream-fragment evidence root is required")
    source = Path(cohort["spec"]["source"]["root"])
    require_separate_output(output, [source, cohort["native_root"], cohort["compiler_root"]])
    manifest = Path(cohort["spec"]["source"]["path"])
    verify_tree(source, manifest)
    verify_guards(source)
    configure = (source / "Configure").read_text()
    makefile = (source / "Makefile.SH").read_text()
    # Configure deliberately repeats the heading for creation and detection.
    start = configure.index(": determine whether symbolic links are supported\n")
    end = configure.index(": Make symlinks util\n", start)
    configure_part = configure[start:end]
    if configure_part.count(": determine whether symbolic links are supported\n") != 2:
        raise ContractError("Expected both original Configure symlink probes")
    makefile_part = between(makefile, "for file in $mini_special; do\n    " + GUARDS["Makefile.SH"] + "\n",
                            "$spitshell >>$Makefile <<'!NO!SUBS!'\n\ncygwin.c:")
    expected_recipe = "\t\\$(LNS) ${file}.c ${file}mini.c"
    if expected_recipe not in makefile_part:
        raise ContractError("The original mini-source symlink recipe changed")
    native, compiler = Path(cohort["native_root"]), Path(cohort["compiler_root"])
    output.mkdir(parents=True)
    for name in ("temp", "home"):
        (output / name).mkdir()
    fixtures = Path(__file__).parent / "fixtures"
    for name in ("op.c", "perl.c", "universal.c"):
        shutil.copyfile(fixtures / "perl-system-link-control.c", output / name)
    shutil.copyfile(fixtures / "perl-system-link-control.h", output / "target.h")
    script = output / "upstream-fragments.sh"
    script.write_text("""#!/usr/bin/env bash
set -euo pipefail
exec 4>&1
touch=$(type -P touch) ln=$(type -P ln) rm=$(type -P rm) test=$(type -P test)
newsh=$(type -P sh) issymlink=''
""" + configure_part + """
: "${issymlink:?Upstream Configure failed to identify a genuine symlink predicate}"
printf 'CONFIGURE_LNS=%s\\nCONFIGURE_ISSYMLINK=%s\\n' "$lns" "$issymlink"
mini_special='op perl universal'
spitshell=cat Makefile=upstream-mini.mk DPERL_IS_MINIPERL=-DPERL_IS_MINIPERL DPERL_EXTERNAL_GLOB=''
""" + makefile_part + """
for name in op perl universal; do
    [[ ! -L $name.c ]] || exit 4
    $lns "$name.c" "${name}mini.c"
    $issymlink "${name}mini.c"
    cmp "$name.c" "${name}mini.c"
done
printf 'UPSTREAM_MINI_SOURCE_LINKS=PASS\\n'
""", encoding="utf-8", newline="\n")
    env = environment(native, compiler, output)
    report = {"schema": 1, **profile_record(SYSTEM_PROFILE), "status": "failed",
              "source_manifest_sha256": digest(manifest), "cohort_sha256": digest(args.cohort),
              "configure_sha256": digest(source / "Configure"), "makefile_sh_sha256": digest(source / "Makefile.SH"),
              "generated_fragment_script_sha256": digest(script), "scope": "Exact unchanged Configure symlink-selection and Makefile.SH mini-source fragment only; not a full Configure or Perl build"}
    try:
        with (output / "upstream-selection.log").open("xb") as log:
            report["selection"] = run([native / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix()],
                                       cwd=output, env=env, log=log, timeout=30)
        if not report["selection"]["passed"]:
            raise ContractError("The original Perl source-generator fragment failed")
        generated = (output / "upstream-mini.mk").read_text()
        if any(f"$(LNS) {name}.c {name}mini.c" not in generated for name in ("op", "perl", "universal")):
            raise ContractError("The unchanged Perl generator did not select the actual symlink recipes")
        native_compile = output / "native-parent-compile.sh"
        native_compile.write_text("#!/usr/bin/env bash\nset -euo pipefail\n"
                                  "gcc -O2 -g -fwrapv -c opmini.c -o opmini.o\n",
                                  encoding="utf-8", newline="\n")
        with (output / "native-parent-compile.log").open("xb") as log:
            report["native_parent_compile"] = run(
                [native / "usr/bin/bash.exe", "--noprofile", "--norc", native_compile.as_posix()],
                cwd=output, env=env, log=log, timeout=30)
        report["status"] = ("upstream-mini-source-link-compile-passed" if report["native_parent_compile"]["passed"]
                            else "blocked-upstream-mini-source-symlinks-native-compiler")
        report["generated_makefile_sha256"] = digest(output / "upstream-mini.mk")
        report["compile_log_sha256"] = digest(output / "native-parent-compile.log")
    finally:
        verify_cohort(args.cohort)
        verify_tree(source, manifest)
        report["inputs_unchanged"] = True
        with (output / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(report["status"])
    if not report["native_parent_compile"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
