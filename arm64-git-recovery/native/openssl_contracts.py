"""Explicit data-model and producer-state boundaries for native OpenSSL consumers."""

from sources import ContractError


def validate_abi(target, macros):
    if target not in ("mingwarm64", "Cygwin-aarch64"):
        raise ContractError("Unknown OpenSSL ABI profile")
    required = {"__aarch64__": "1", "__SIZEOF_POINTER__": "8"}
    required.update({"__SIZEOF_LONG__": "8", "__MSYS__": "1"} if target == "Cygwin-aarch64"
                    else {"__SIZEOF_LONG__": "4", "__MINGW32__": "1"})
    if any(macros.get(name) != value for name, value in required.items()):
        raise ContractError(f"Actual compiler ABI does not match OpenSSL target {target}")


def require_msys_build(record):
    if record.get("status") == "native-msys-openssl-built-tests-deferred":
        return
    if (record.get("status") == "native-openssl-built-tests-deferred" and
            record.get("target_profile") == "Cygwin-aarch64"):
        validate_abi("Cygwin-aarch64", record.get("measured_abi_macros", {}))
        return
    raise ContractError("Expected an explicitly identified native MSYS OpenSSL build")
