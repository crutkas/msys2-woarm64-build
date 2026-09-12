"""Analyze retained diff hunks without altering test outputs or verdicts."""

import json
from pathlib import Path
import re

from inventory import ROOT, write

PREFIX = re.compile(r"/cygdrive/c/ag-coreutils-e138(?:-)?01/coreutils-native-13/build/coreutils/src/")


def blocks(lines):
    found = []
    index = 0
    while index < len(lines):
        if re.match(r"^@@ -\d", lines[index]):
            start = index
            expected, actual = [], []
            index += 1
            while index < len(lines) and (lines[index][:1] in (" ", "+", "-") or lines[index].startswith("\\ No newline")):
                text = lines[index]
                if text.startswith("\\ No newline"):
                    index += 1
                    continue
                if text.startswith(("+ ", "--- ", "+++ ")):
                    break
                if text.startswith("-"):
                    expected.append(text[1:])
                elif text.startswith("+"):
                    actual.append(text[1:])
                else:
                    expected.append(text[1:])
                    actual.append(text[1:])
                index += 1
            found.append({"line": start + 1, "kind": "unified", "expected": expected, "actual": actual})
        elif re.match(r"^\*\*\* \d+(?:,\d+)? \*\*\*\*$", lines[index]):
            start = index
            expected, actual = [], []
            index += 1
            while index < len(lines) and not re.match(r"^--- \d+(?:,\d+)? ----$", lines[index]):
                if lines[index].startswith(("! ", "- ", "  ")):
                    expected.append(lines[index][2:])
                index += 1
            index += 1
            while index < len(lines) and lines[index].startswith(("! ", "+ ", "  ")):
                actual.append(lines[index][2:])
                index += 1
            found.append({"line": start + 1, "kind": "context", "expected": expected, "actual": actual})
        else:
            index += 1
    for block in found:
        block["same_after_diagnostic_prefix_removal"] = (
            any(PREFIX.search(text) for text in block["expected"] + block["actual"])
            and [PREFIX.sub("", text) for text in block["expected"]] == [PREFIX.sub("", text) for text in block["actual"]])
    return found


def main():
    inventory = json.loads((ROOT / "inventory.json").read_text())
    result = []
    for row in inventory["tests"]:
        lines = Path(row["log"]).read_text(errors="replace").splitlines()
        parsed = blocks(lines)
        failures = [{"line": i + 1, "text": line} for i, line in enumerate(lines)
                    if re.search(r"test .*mismatch|test .*failed|failed to|cannot |No such process|RTLD_NEXT|environment is too large", line)
                    and not line.startswith(("+ alias", "+ export"))]
        result.append({"test": row["test"], "status": row["status"], "diffs": parsed,
                       "prefix_only_diff_count": sum(block["same_after_diagnostic_prefix_removal"] for block in parsed),
                       "non_prefix_diff_count": sum(not block["same_after_diagnostic_prefix_removal"] for block in parsed),
                       "other_discrepancies": failures,
                       "original_test_outcome_unchanged": True})
    write(ROOT / "diagnostic-diff-analysis-v2.json", {"schema": 1, "tests": result,
          "scope": "Counterfactual string comparison localizes discrepancy only; never a test rerun, skip, pass, or output normalization"})
    for row in result:
        print(json.dumps({"test": row["test"], "prefix_hunks": row["prefix_only_diff_count"],
                          "other_hunks": row["non_prefix_diff_count"]}))


if __name__ == "__main__":
    main()
