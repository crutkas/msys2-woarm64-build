"""Exhaustive retained-failure ledger, with primary buckets and residual uncertainty."""

import json
from collections import Counter
from pathlib import Path
import re

from inventory import ROOT, digest, write

GROUPS = {
    "argv0-diagnostics": {
        "kind": "launch/harness interoperability",
        "tests": [
            "misc/help-version-getopt.sh", "rm/d-2.sh", "rm/d-3.sh", "rm/dir-no-w.sh",
            "rm/dir-nonrecur.sh", "rm/isatty.sh", "rm/empty-name.pl",
            "rm/interactive-always.sh", "rm/interactive-once.sh", "rm/r-4.sh", "rm/rm5.sh",
            "fmt/base.pl", "misc/env.sh", "misc/seq.pl", "misc/xstrtol.pl", "misc/cut.pl", "pr/pr-tests.pl",
        ],
        "mechanism": "Native utility receives an absolute argv[0] in the retained mixed launch. gnulib deliberately preserves path-qualified argv[0]; tests expect basename invocation. seq's first-only s/-0/0/ also edits the path component e138-01 instead of the negative-zero operand.",
        "evidence": ["focused-diagnostic-argv0-current-noacl", "focused-diagnostic-argv0-historical-noacl",
                     "historical-native-dir-nonrecur-01", "complete-help-version-getopt-02"],
        "confidence": "confirmed discrepancy and mechanism; Perl scripts not fully rerun",
        "not": "not an English translation error or incorrect cut/seq/pr data algorithm",
    },
    "permission-model": {
        "kind": "configuration plus genuine MSYS/Windows POSIX semantic gaps",
        "tests": [
            "rm/cycle.sh", "chmod/no-x.sh", "chgrp/basic.sh", "rm/fail-eacces.sh",
            "rm/inaccessible.sh", "rm/rm1.sh", "rm/rm2.sh", "rm/rm3.sh", "rm/unread2.sh",
            "rm/unreadable.pl", "chgrp/no-x.sh", "chgrp/posix-H.sh", "chgrp/recurse.sh", "misc/mktemp.pl",
        ],
        "mechanism": "noacl cannot encode Unix mode/group requirements (mktemp600 becomes644; directories remain755). Enabling ACL in a fresh private root fixes group/read/temporary-file semantics, but seven shell tests still expose unlinkat child deletion despite nonwritable parent or traversal despite nonsearchable parent. Direct runtime API fixture reproduces those boundaries without Coreutils.",
        "evidence": ["api-boundary-current-noacl", "api-boundary-current-acl",
                     "focused-mktemp-mode-current-noacl", "focused-mktemp-mode-current-acl",
                     "acl-unreadable-perl-mechanism-01", "upstream-tests-chgrp-basic-current-acl"],
        "confidence": "confirmed; residual layer localized to runtime/API permission semantics, not an ARM64 arithmetic/codegen defect",
        "not": "not reclassified as inapplicable: the POSIX behaviors remain genuinely unsupported/failing",
    },
    "runtime-views-and-pids": {
        "kind": "mixed launch/runtime namespace and file-descriptor interoperability",
        "tests": ["rm/dangling-symlink.sh", "rm/unread3.sh", "tail-2/inotify-hash-abuse2.sh",
                  "tail-2/pid.sh", "misc/od.pl", "misc/wc-proc.sh", "tail-2/overlay-headers.sh",
                  "misc/pwd-option.sh"],
        "mechanism": "Retained parent and native child disagree on symlink/root mapping, process IDs, /proc/version byte length or inherited special-file descriptors. Logs show /cygdrive paths remapped under host-bootstrap, kill($!) reporting ESRCH while tail remains alive, wrong proc skip length and wc EBADF. Coherent native-parent replays fix these without utility changes, including selected old-baa-runtime controls.",
        "evidence": ["historical-native-pwd-option-01", "historical-native-wc-proc-01",
                     "focused-proc-byte-domain-current-noacl", "focused-proc-byte-domain-historical-noacl",
                     "focused-readlink-sys-representation-current-noacl", "complete-inotify-hash-abuse2-02",
                     "upstream-tests-tail-2-overlay-headers-current-noacl", "upstream-tests-tail-2-pid-current-noacl"],
        "confidence": "confirmed boundary discrepancies; original parent PID/birth/callsite receipt does not exist, so exact legacy boundary implementation is not retroactively reconstructed",
        "not": "not proof that tail/od/wc need output normalization or that inotify must be skipped",
    },
    "invalid-byte-argument": {
        "kind": "argument-byte interoperability",
        "tests": ["misc/date.pl"],
        "mechanism": "The exact invalid B0 date argument is reported as EF82B0 (UTF-8 private-use U+F0B0) in the retained stderr. Same binary under coherent native old/current parents preserves B0 and produces the expected diagnostic; deliberately passing EF82B0 recreates the observed diagnostic. The secondary invalid-TZ mismatch is argv0-only.",
        "evidence": ["exact-byte-subcases-current-noacl", "exact-byte-subcases-historical-noacl"],
        "confidence": "byte-level discrepancy confirmed; not a date parser/calendar calculation error",
        "not": "not a message-catalog lookup or line-ending problem",
    },
    "compound-help-dependencies": {
        "kind": "several launch failures plus a missing support-file layout",
        "tests": ["misc/help-version.sh"],
        "mechanism": "Four named retained failures: csplit // converted to /; native kill cannot resolve parent's background PID; ln/readlink cannot represent the requested link; stdbuf cannot locate real libstdbuf.dll. Quoting/syslink/PID controls and installing the original real DLL in /usr/lib/coreutils remove these specific symptoms. The full fresh script remained bounded-incomplete; the new all-native harness also lacks gzip.",
        "evidence": ["focused-quoted-args-current-noacl", "focused-readlink-sys-representation-current-noacl",
                     "focused-stdbuf-layout-current-noacl", "focused-stdbuf-canonical-layout-01",
                     "complete-help-version-02"],
        "confidence": "all four retained failure mechanisms identified; no claim that the entire help-version script now passes",
        "not": "not one generic help/version implementation bug",
    },
    "residual-launch-proof-missing": {
        "kind": "known argv0 failures plus incompletely recorded secondary launch behavior",
        "tests": ["misc/join.pl", "misc/wc-files0-from.pl"],
        "mechanism": "join has seven argv0-only diagnostics plus one A7-separator status mismatch; wc has six argv0-only diagnostics plus /dev/null files0 status mismatch. Exact coherent-native subcases succeed; PUA-encoding the join separator reproduces exit1. Original offending argv/file-descriptor snapshots were not retained, so those secondary root causes remain unconfirmed rather than assigned a cosmetic pass.",
        "evidence": ["exact-byte-subcases-current-noacl", "exact-byte-subcases-historical-noacl",
                     "focused-proc-byte-domain-current-noacl", "focused-proc-byte-domain-historical-noacl"],
        "confidence": "two original secondary mechanisms remain unconfirmed; common diagnostic mechanism is confirmed",
        "not": "not evidence of a current join data algorithm failure or justification to waive the original failures",
    },
    "environment-size": {
        "kind": "suite environment/test dependency constraint",
        "tests": ["tail-2/inotify-hash-abuse.sh"],
        "mechanism": "xargs refuses exec because the inherited environment exceeds its available exec budget, before the tail assertions. Small-environment unchanged script exits0; explicit 40000-byte environment reproduces the exact xargs diagnostic and raw failure.",
        "evidence": ["focused-xargs-env-budget-current-noacl", "upstream-tests-tail-2-inotify-hash-abuse-current-noacl"],
        "confidence": "confirmed",
        "not": "not a tail/inotify defect and not a permission/locale assumption",
    },
    "unsupported-preload-test-api": {
        "kind": "test-harness facility not supplied by this target ABI",
        "tests": ["rm/rm-readdir-fail.sh"],
        "mechanism": "The injected readdir helper cannot compile: RTLD_NEXT is undefined in the target dlfcn.h. The test requires ELF-style next-definition lookup through dlsym plus LD_PRELOAD to inject readdir errors. Failure is at helper compilation, before any rm behavior is exercised. The direct native API diagnostic confirms the header capability remains absent.",
        "evidence": ["api-boundary-current-noacl", "api-boundary-current-acl"],
        "confidence": "confirmed setup limitation; test not run to its behavioral assertions",
        "not": "not an rm failure and not silently changed to SKIP/PASS; needs a target-appropriate real fault-injection facility",
    },
}


def main():
    original = json.loads((ROOT / "inventory.json").read_text())
    records = {row["test"]: row for row in original["tests"]}
    classified, groups = [], []
    seen = set()
    for name, group in GROUPS.items():
        rows = []
        for short in group["tests"]:
            test = "tests/" + short
            if test in seen or test not in records:
                raise RuntimeError(f"Duplicate or unknown retained test: {test}")
            seen.add(test)
            record = records[test]
            lines = Path(record["log"]).read_text(errors="replace").splitlines()
            witnesses = [{"line": index + 1, "text": line} for index, line in enumerate(lines)
                         if re.search(r"mismatch|set-up failure|Permission denied|No such process|Bad file descriptor|environment is too large|RTLD_NEXT|failed to find|Too many levels|^[-+!].*(/cygdrive|rm:|chmod:|chgrp:)", line)]
            replay_results = []
            for path in sorted((ROOT / "runs").glob("*/result.json")):
                replay = json.loads(path.read_text())
                if replay.get("test") == test:
                    replay_results.append({"path": str(path), "sha256": digest(path),
                                           "cohort": replay["cohort"],
                                           "test_shell_raw_exit": replay["semantic_test_shell_raw_exit"],
                                           "observer_gate_passed": replay["observer_gate_passed"],
                                           "timed_out": replay["native_job"]["timed_out"],
                                           "coverage": [replay["native_job"]["observed_processes"], replay["native_job"]["created_processes"]]})
            row = {"test": test, "original_status": record["status"], "primary_group": name,
                   "source": record["source"], "source_sha256": record["source_sha256"],
                   "retained_log": record["log"], "log_sha256": record["log_sha256"],
                   "witnesses": witnesses, "unchanged_script_replays": replay_results,
                   "full_perl_script_replayed": False if test.endswith(".pl") else None}
            if test == "tests/rm/rm3.sh":
                row["additional_mechanisms"] = ["foreign argv glob expands tr '?' to matching filename z",
                                              "symlink representation", "argv0 prefix"]
            if test == "tests/rm/inaccessible.sh":
                row["additional_mechanisms"] = ["retained absolute path remapped under host-bootstrap root"]
            if test == "tests/rm/fail-eacces.sh":
                row["additional_mechanisms"] = ["retained symbolic-link setup disagreement"]
            if test == "tests/misc/mktemp.pl":
                row["additional_mechanisms"] = ["two argv0-only diagnostics before mode600-vs644 termination"]
            if test == "tests/misc/seq.pl":
                row["additional_mechanisms"] = ["first-only test ERR_SUBST mutates e138-01 path rather than argument -0"]
            classified.append(row)
            rows.append(row)
        evidence = []
        for label in group["evidence"]:
            result = ROOT / "runs" / label / "result.json"
            evidence.append({"path": str(result), "sha256": digest(result),
                             "log": str(result.parent / "target.log"), "log_sha256": digest(result.parent / "target.log")})
        groups.append({"id": name, **{k: v for k, v in group.items() if k not in ("tests", "evidence")},
                       "counts": dict(Counter(row["original_status"] for row in rows)),
                       "tests": [row["test"] for row in rows], "evidence": evidence})
    if seen != set(records):
        raise RuntimeError(f"Unclassified retained tests: {set(records) - seen}")
    write(ROOT / "causes.json", {"schema": 1, "counts": original["counts"], "groups": groups,
          "tests": classified, "every_original_status_preserved": True,
          "primary_buckets_are_disjoint": True, "multiple_causes_recorded": True,
          "catalog_or_translation_root_causes_evidenced": 0,
          "line_ending_only_root_causes_evidenced": 0,
          "locale_scope": "Upstream lang-default and Perl scripts force C locale; official CLANGARM64 gettext is a different ABI/provider and not imported by these MSYS targets.",
          "unconfirmed_secondary_causes": ["join.pl 8-bit-t exact legacy argument", "wc-files0-from.pl empty-nonreg exact legacy fd/path"]})
    print(json.dumps({row["id"]: row["counts"] for row in groups}))


if __name__ == "__main__":
    main()
