"""Deliver literal Tcl argv without leaking the foreign-shell conversion switch."""

import os
from pathlib import Path
import runpy

from native_job_runner import verify_driver
from sources import ContractError


if os.environ.get("WOARM64_NATIVE_ARG_CONVERSION") != "none":
    raise ContractError("Literal native MSYS Tcl argument delivery is required")
driver = Path(os.environ["WOARM64_NATIVE_DRIVER_ROOT"])
verify_driver(driver)
# The foreign shell has already delivered literal argv to native Python.
# Its conversion switch must not govern Tcl's later Windows-host tool execs.
os.environ.pop("MSYS2_ARG_CONV_EXCL", None)
runpy.run_path(str(driver / "native-target-exec.py"), run_name="__main__")
