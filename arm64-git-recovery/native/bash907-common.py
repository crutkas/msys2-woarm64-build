"""Exact private environment and current observer for Bash907 qualification."""

import importlib
import os
from pathlib import Path

from sources import ContractError, digest
from native_job_runner import run_observed

prepare = importlib.import_module("prepare-bash907")
ROOT = prepare.ROOT
HERE = Path(__file__).resolve().parent
combined = importlib.import_module("prepare-combined-terminal")
cpu_budget = importlib.import_module("build-bash-nls").cpu_budget
birth = importlib.import_module("build-readline-chain").current_birth
PYTHON_SHA = "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29"


def posix(path):
    path = Path(path).resolve()
    return "/" + path.drive[0].lower() + "/" + path.as_posix()[3:]


def environment(output, runtime):
    if not os.environ.get("PATHEXT") or digest(Path(__import__("sys").executable)) != PYTHON_SHA:
        raise ContractError("Native Python and real Windows PATHEXT are required")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update(PATH=str(runtime / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               HOME=posix(output / "home"), USERPROFILE=str(output / "home"),
               TMP=str(output / "temp"), TEMP=str(output / "temp"), TMPDIR=posix(output / "temp"),
               LC_ALL="C.UTF-8", LANG="C.UTF-8", MSYSTEM="CYGWIN", MSYS="winsymlinks:sys",
               TERM="xterm-256color", TERMINFO=posix(runtime / "usr/share/terminfo"),
               INPUTRC=posix(runtime / "etc/inputrc"),
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MAKEFLAGS="-j1",
               WOARM64_NATIVE_ARG_CONVERSION="none", WOARM64_NATIVE_TEST_ROOT=str(ROOT),
               WOARM64_NATIVE_PYTHON=__import__("sys").executable,
               WOARM64_NATIVE_PYTHON_SHA256=PYTHON_SHA,
               WOARM64_NATIVE_EXIT_DIR=str(output / "native-exits"))
    return env


def observed(command, output, runtime, timeout=120, cwd=None):
    output.mkdir(parents=True)
    for name in ("home", "temp", "native-exits"):
        (output / name).mkdir()
    return run_observed(command, cwd=cwd or output, env=environment(output, runtime),
                        log_path=output / "observed.log", result_path=output / "native-job.json",
                        relay_records=output / "native-exits", timeout=timeout,
                        driver_prefix=ROOT / "observer")
