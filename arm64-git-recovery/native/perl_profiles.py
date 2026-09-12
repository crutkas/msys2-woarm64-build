"""Keep strict Windows-native symlinks distinct from the explicitly selected supported MSYS profile."""

from sources import ContractError

STRICT_PROFILE = "nativestrict"
SYSTEM_PROFILE = "msys-system-symlink-bootstrap"
PROFILES = (STRICT_PROFILE, SYSTEM_PROFILE)


def profile_record(name):
    if name == STRICT_PROFILE:
        return {"profile": name, "MSYS": "winsymlinks:nativestrict",
                "NativeWindowsSymlinkQualification": "required, not inferred"}
    if name == SYSTEM_PROFILE:
        return {"profile": name, "MSYS": "winsymlinks:sys",
                "NativeWindowsSymlinkQualification": False,
                "SupportedMsysPosixSymlinkMode": "system-attribute file with native MSYS symlink semantics",
                "scope": "Explicit alternative bootstrap; original strict Windows-symlink qualification remains blocked"}
    raise ContractError("Unknown Perl symlink profile")


def require_system_environment(environment):
    if environment.get("MSYS") != "winsymlinks:sys" or environment.get("MSYSTEM") != "CYGWIN":
        raise ContractError("Alternative Perl requires explicit supported-system symlinks and the current native parent profile")
    if any(name in environment for name in ("MSYS2_ARG_CONV_EXCL", "MSYS2_ENV_CONV_EXCL", "BASH_ENV", "ENV")):
        raise ContractError("Native Perl parent may not inherit conversion exclusions or shell startup overrides")
