"""Reject Perl source generators that can execute a pathname as an empty predicate."""

from pathlib import Path
import re

from sources import ContractError


GUARDS = {
    "Configure": ': "${issymlink:?A tested symlink predicate is required; refusing to execute a pathname}"',
    "Makefile.SH": ': "${issymlink:?A tested symlink predicate is required; refusing to execute a source file}"',
}


def verify_guards(source):
    for name, guard in GUARDS.items():
        lines = (Path(source) / name).read_text().splitlines()
        uses = [index for index, line in enumerate(lines) if re.match(r"\s*if\s+\$issymlink\b", line)]
        if not uses or any(index == 0 or lines[index - 1].strip() != guard for index in uses):
            raise ContractError(f"Unsafe or missing symlink-predicate guard in {name}")
