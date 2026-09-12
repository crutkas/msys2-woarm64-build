"""Validate the runtime owner's normal-link/native-run receipt before bootstrap."""

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import subprocess

from sources import ContractError, digest
from compiler_tools import verify_runtime_link_inputs, verify_support


def checked_file(record):
    path = Path(record["path"])
    if not path.is_file() or path.is_symlink() or digest(path) != record["sha256"]:
        raise ContractError(f"Readiness input missing or changed: {path}")
    return path.resolve()


def verify(receipt_path, prefix):
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("schema") != 1 or receipt.get("target") != "aarch64-pc-cygwin":
        raise ContractError("Expected schema-1 aarch64-pc-cygwin readiness receipt")
    prefix = Path(prefix).resolve()
    expected = {
        "compiler": prefix / "bin/msys2-gcc",
        "base_compiler": prefix / "bin/aarch64-pc-cygwin-gcc",
        "installed_runtime_dll": prefix / "bin/msys-2.0.dll",
        "import_library": prefix / "aarch64-pc-cygwin/lib/libmsys-2.0.a",
    }
    files = {}
    for name in (*expected, "runtime_dll", "specs", "source", "executable"):
        files[name] = checked_file(receipt[name])
        if name in expected and files[name] != expected[name].resolve():
            raise ContractError(f"Readiness {name} does not belong to the current prefix")
    if not files["specs"].is_relative_to(prefix):
        raise ContractError("MSYS specs overlay must belong to the current prefix")
    if receipt["runtime_dll"]["sha256"] != receipt["installed_runtime_dll"]["sha256"]:
        raise ContractError("Staged runtime DLL differs from the current installed runtime")
    verify_support(receipt.get("support_tools"), files["compiler"], prefix)
    verify_runtime_link_inputs(receipt.get("runtime_link_inputs"), files["compiler"], prefix)
    link = receipt["link"]
    if (type(link.get("exit_code")) is not int or link["exit_code"] != 0
            or link.get("default_runtime_link") is not True):
        raise ContractError("A successful normal compiler link is required")
    argv = link.get("argv", [])
    allowed_flags = {"-D__MSYS__", "-g", "-O0", "-O1", "-O2", "-O3", "-Os"}
    operands = [arg for arg in argv if arg not in allowed_flags]
    # No explicit runtime libraries, alternate specs, crt objects or linker
    # overrides may substitute for a working installed compiler interface.
    required = [str(files["compiler"]), str(files["source"]), "-o", str(files["executable"])]
    if operands != required:
        raise ContractError("Hello must use the compiler's default link interface, without overrides")
    specs = subprocess.run([str(files["compiler"]), "-dumpspecs"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True).stdout
    if not specs or hashlib.sha256(specs).hexdigest() != receipt.get("default_specs_sha256"):
        raise ContractError("Compiler default specs changed since the normal-link proof")
    run = receipt["run"]
    if type(run.get("exit_code")) is not int or run["exit_code"] != 0:
        raise ContractError("Successful native runtime hello execution is required")
    process_path = checked_file(run["native_process_report"])
    process = json.loads(process_path.read_text(encoding="utf-8"))
    if (process.get("Passed") is not True or process.get("RequestedCount") != 1
            or process.get("MeasuredCount") != 1 or len(process.get("Processes", [])) != 1):
        raise ContractError("Missing complete native-process proof")
    identity = process["Processes"][0]
    image = run["windows_image_path"]
    if (type(run.get("process_id")) is not int or run["process_id"] <= 0
            or identity.get("ProcessId") != run["process_id"]
            or not run.get("created_utc") or identity.get("CreatedUtc") != run["created_utc"]
            or not PureWindowsPath(image).is_absolute()
            or identity.get("ImagePath", "").casefold() != image.casefold()
            or identity.get("NativeArm64Process") is not True
            or identity.get("ProcessMachine") != "0xAA64"
            or identity.get("Wow64ProcessMachine") != "0x0000"
            or identity.get("NativeMachine") != "0xAA64"):
        raise ContractError("Runtime hello lacks matching native ProcessMachineTypeInfo evidence")
    artifact_path = checked_file(run["artifact_report"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if (artifact.get("Passed") is not True or not artifact.get("CandidateCount")
            or artifact.get("ParsedCount") != artifact["CandidateCount"]
            or len(artifact.get("Files", [])) != artifact["CandidateCount"]):
        raise ContractError("Missing complete native artifact proof")
    measured = artifact["Files"]
    executable = [row for row in measured if row.get("Path", "").casefold() == image.casefold()]
    if (len(executable) != 1 or executable[0].get("SHA256", "").lower() != receipt["executable"]["sha256"]
            or executable[0].get("NativeArm64Header") is not True):
        raise ContractError("Native run image is not the hash-bound linked executable")
    runtime_image = run.get("windows_runtime_dll_path", "")
    if not PureWindowsPath(runtime_image).is_absolute():
        raise ContractError("Exact staged Windows runtime DLL path is required")
    runtime = [row for row in measured
               if row.get("Path", "").casefold() == runtime_image.casefold()
               and row.get("SHA256", "").lower() == receipt["runtime_dll"]["sha256"]
               and row.get("NativeArm64Header") is True]
    if len(runtime) != 1:
        raise ContractError("Native artifact evidence omits or mismatches the exact staged runtime DLL")
    return digest(receipt_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args()
    print(f"Runtime normal-link/native-run receipt verified: {verify(args.receipt, args.prefix)}")


if __name__ == "__main__":
    main()
