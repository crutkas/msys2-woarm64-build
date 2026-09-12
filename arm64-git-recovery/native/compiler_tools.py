"""Record the support programs GCC will resolve, not just its driver binary."""

import os
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest


CRITICAL_SUPPORT = ("cc1", "collect2", "as", "ld")
RUNTIME_LINK_INPUTS = ("crt0.o", "libgcc.a", "libgcc_eh.a", "libgcc_s.dll.a")


def require_msys_jump_receipt(record):
    qualification = record.get("source_jump_buffer_qualification")
    pairing = record.get("source_runtime_pairing")
    if (not isinstance(qualification, dict) or
            tuple(qualification.get(name) for name in
                  ("JmpBufBytes", "SigjmpBufBytes", "SaveMaskOffset", "SignalMaskOffset")) != (256, 272, 256, 264) or
            qualification.get("ExistingConsumersRecompiled") is not False or
            not isinstance(pairing, dict) or
            any(name not in qualification for name in ("Header", "Consumer", "RuntimeReceipt")) or
            any(name not in pairing for name in ("SysrootManifest", "DllManifest"))):
        raise ContractError("A producer-qualified coherent MSYS jump-buffer SDK copy is required")


def require_msys_ucontext_receipt(record):
    require_msys_jump_receipt(record)
    qualification = record.get("source_ucontext_qualification")
    if (not isinstance(qualification, dict) or qualification.get("EntryStackAlignment") != 16 or
            qualification.get("CoroutineYields", 0) < 32 or
            qualification.get("BoundedChildCleanup") is not True or
            qualification.get("InvalidContextReturnsEINVAL") is not True):
        raise ContractError("A producer-qualified MSYS coroutine runtime is required")


def verify_msys_jmp_headers(compiler, env=None):
    # This rejects the known undersized header without executing target code;
    # it does not replace the producer's coherent headers/CRT/DLL receipt.
    source = Path(__file__).parent / "fixtures/msys-jmp-layout.c"
    command = [str(compiler), "-std=gnu11", "-Werror", "-fsyntax-only", str(source)]
    result = subprocess.run(command, env=env, capture_output=True, timeout=30)
    if result.returncode or result.stderr:
        raise ContractError("MSYS jump-buffer ABI prerequisite failed; require the coherent corrected SDK: " +
                            result.stderr.decode(errors="replace")[:2000])
    return {"command": command, "source_sha256": digest(source), "compiler_sha256": digest(compiler),
            "scope": "Compile-time header layout only; no target execution or whole-SDK qualification"}


def support_identities(compiler, prefix, env=None):
    prefix = Path(prefix).resolve()
    search_path = (os.environ if env is None else env).get("PATH", "")
    records = {}
    for name in CRITICAL_SUPPORT:
        result = subprocess.run([str(compiler), f"-print-prog-name={name}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, check=True)
        value = result.stdout.decode("utf-8").strip()
        if not value or "\n" in value or "\r" in value:
            raise ContractError(f"GCC did not identify support program {name}")
        path = Path(value)
        if not path.is_absolute():
            resolved = shutil.which(value, path=search_path)
            if not resolved:
                raise ContractError(f"GCC support program is not resolvable: {name}={value}")
            path = Path(resolved)
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(prefix):
            raise ContractError(f"GCC support program is outside the current prefix or missing: {name}={path}")
        records[name] = {"path": str(path), "sha256": digest(path)}
    return records


def verify_support(expected, compiler, prefix, env=None):
    if not isinstance(expected, dict) or set(expected) != set(CRITICAL_SUPPORT):
        raise ContractError("Complete cc1/collect2/as/ld support identities are required")
    actual = support_identities(compiler, prefix, env)
    if actual != expected:
        changed = [name for name in CRITICAL_SUPPORT if actual[name] != expected[name]]
        raise ContractError(f"Compiler support programs changed: {', '.join(changed)}")
    return actual


def runtime_link_identities(compiler, prefix, env=None):
    prefix = Path(prefix).resolve()
    records = {}
    for name in RUNTIME_LINK_INPUTS:
        result = subprocess.run([str(compiler), f"-print-file-name={name}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, check=True)
        value = result.stdout.decode("utf-8").strip()
        # GCC returns the unchanged name when an optional archive is unavailable.
        # Record that absence too: installing it later changes the link epoch.
        if value == name and name in ("libgcc_eh.a", "libgcc_s.dll.a"):
            records[name] = {"present": False}
            continue
        path = Path(value).resolve()
        if (not value or "\n" in value or "\r" in value
                or not Path(value).is_absolute()
                or not path.is_file() or not path.is_relative_to(prefix)):
            raise ContractError(f"Runtime link input is missing or outside the current prefix: {name}={value}")
        records[name] = {"present": True, "path": str(path), "sha256": digest(path)}
    return records


def verify_runtime_link_inputs(expected, compiler, prefix, env=None):
    if not isinstance(expected, dict) or set(expected) != set(RUNTIME_LINK_INPUTS):
        raise ContractError("Complete runtime crt0/libgcc link identities are required")
    actual = runtime_link_identities(compiler, prefix, env)
    if actual != expected:
        changed = [name for name in RUNTIME_LINK_INPUTS if actual[name] != expected[name]]
        raise ContractError(f"Runtime link inputs changed: {', '.join(changed)}")
    return actual
