"""Narrow input corrections for the pinned MSYS Tcl test makefiles."""

import re

from sources import ContractError


def forward_dltest_ldflags(text):
    pattern = r"(?m)^(?![^\n]*\$\{LDFLAGS\})(\t\$\{(?:SHLIB_LD|DLTEST_LD)\} -o [^\n]+) \$\{SHLIB_LD_LIBS\}$"
    matches = re.findall(pattern, text)
    if len(matches) != 14:
        if not matches and len(re.findall(
                r"(?m)^\t\$\{(?:SHLIB_LD|DLTEST_LD)\} -o [^\n]+ \$\{LDFLAGS\} \$\{SHLIB_LD_LIBS\}$", text)) == 14:
            return text
        raise ContractError("Expected exactly fourteen pinned Tcl dynamic-load test link recipes")
    return re.sub(pattern, lambda match: match[1] + " ${LDFLAGS} ${SHLIB_LD_LIBS}", text)
