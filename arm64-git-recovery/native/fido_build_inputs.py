"""Prepare genuine pkgconf metadata over existing MSYS library inputs without installing them."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from cmake_test_replay import verify_build_files
from compiler_tools import require_msys_ucontext_receipt
from sources import ContractError, digest, inventory, verify_tree


def read_bound(item):
    path = Path(item["path"]).resolve()
    if digest(path) != item["sha256"]:
        raise ContractError("FIDO input receipt identity changed")
    return path, json.loads(path.read_text(encoding="utf-8"))


def retained_abi(current_path, prior_path):
    current = json.loads(Path(current_path).read_text(encoding="utf-8"))
    prior = json.loads(Path(prior_path).read_text(encoding="utf-8"))
    for record, path in ((current, current_path), (prior, prior_path)):
        require_msys_ucontext_receipt(record)
        verify_tree(record["prefix"], path)
    changed = {"libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe", "bin/aarch64-pc-cygwin-gcc.exe",
               "bin/aarch64-pc-cygwin-gcc-15.0.1.exe", "bin/aarch64-pc-cygwin-cpp.exe"}
    delta = current.get("source_compiler_delta", {})
    if (delta.get("base_receipt_sha256") != digest(prior_path) or
            {name.replace("\\", "/") for name in delta.get("changed_files", [])} != changed):
        raise ContractError("Only the explicit predecessor of the qualified CMocka compiler delta is accepted")
    for field in ("source_target", "source_jump_buffer_qualification", "source_ucontext_qualification", "source_runtime_pairing"):
        if current.get(field) != prior.get(field):
            raise ContractError("Retained MSYS runtime/header qualification differs")
    if any(current["files"].get(name) != row for name, row in prior["files"].items() if name not in changed):
        raise ContractError("A retained MSYS input changed outside the declared compiler delta")
    return {"current_sha256": digest(current_path), "predecessor_sha256": digest(prior_path),
            "scope": "Exact retained ABI payload across the declared C-compiler-only delta; no new library test qualification"}


def rewrite_pc(text, variables, extra_includes=()):
    for name, value in variables.items():
        if not isinstance(value, str) or re.search(r"[\s;]", value):
            raise ContractError("Build-only pkgconf paths must be explicit whitespace-free Windows paths")
        pattern = rf"(?m)^{re.escape(name)}=.*$"
        if len(re.findall(pattern, text)) != 1:
            raise ContractError(f"Expected one original pkgconf variable: {name}")
        text = re.sub(pattern, lambda _: f"{name}={value}", text)
    if extra_includes:
        if len(re.findall(r"(?m)^Cflags:.*$", text)) != 1:
            raise ContractError("Expected one original pkgconf Cflags line")
        for value in extra_includes:
            if re.search(r"[\s;]", value):
                raise ContractError("Additional native header paths must be explicit and whitespace-free")
        text = re.sub(r"(?m)^Cflags:.*$", lambda match: match[0] + "".join(f" -I{value}" for value in extra_includes), text)
    return text


def describe_inputs(spec):
    current_path, current = read_bound(spec["compiler"])
    prior_path, prior = read_bound(spec["predecessor"])
    abi = retained_abi(current_path, prior_path)
    pkg_path, pkg = read_bound(spec["pkgconf"])
    pkg_root = pkg_path.parent / "stage"
    if pkg.get("status") != "native-pkgconf-built-upstream-and-independent-controls-passed":
        raise ContractError("An actual qualified native pkgconf build is required")
    verify_tree(pkg_root, pkg_path)
    cbor_path, cbor = read_bound(spec["libcbor"])
    cbor_source_manifest, _ = read_bound(spec["libcbor_source"])
    cbor_root = cbor_path.parent
    if (cbor.get("status") != "native-msys-cmake-built-not-tested" or cbor.get("package") != "libcbor" or
            cbor.get("inputs_unchanged") is not True or cbor.get("compiler_receipt_sha256") != digest(current_path) or
            cbor.get("source_manifest_sha256") != digest(cbor_source_manifest)):
        raise ContractError("FIDO compilation requires the exact build-only CBOR/current-compiler input")
    verify_build_files(cbor_root / "build", cbor["compiled_files"])
    verify_tree(cbor_root / "source", cbor_source_manifest)
    crypto_path, crypto = read_bound(spec["libcrypto"])
    crypto_root = Path(spec["libcrypto"]["root"]).resolve()
    if (crypto.get("status") != "native-openssl-built-tests-deferred" or
            crypto.get("target_profile") != "Cygwin-aarch64" or crypto.get("compiler_receipt_sha256") != digest(prior_path)):
        raise ContractError("FIDO libcrypto must be the actual retained-cohort MSYS OpenSSL build")
    verify_tree(crypto_root, crypto_path)
    zlib_path, zlib = read_bound(spec["zlib"])
    zlib_root = Path(spec["zlib"]["root"]).resolve()
    if (zlib.get("status") != "native-msys-library-built-checked-bootstrap-driver" or
            zlib.get("package") != "zlib-msys" or zlib.get("compiler_receipt_sha256") != digest(prior_path)):
        raise ContractError("FIDO zlib must be the actual retained-cohort MSYS library")
    verify_tree(zlib_root, zlib_path)
    modules = {
        "libcbor": {"version": "0.14.0", "pc": cbor_root / "build/src/libcbor.pc",
                    "includes": [cbor_root / "source/src", cbor_root / "build", cbor_root / "build/src"],
                    "libdir": cbor_root / "build/src", "import": cbor_root / "build/src/libcbor.dll.a",
                    "dll": cbor_root / "build/src/msys-cbor-0.14.dll", "status": cbor["status"]},
        "libcrypto": {"version": "3.6.4", "pc": crypto_root / "lib/pkgconfig/libcrypto.pc",
                      "includes": [crypto_root / "include"], "libdir": crypto_root / "lib",
                      "import": crypto_root / "lib/libcrypto.dll.a", "dll": crypto_root / "bin/msys-crypto-3.dll",
                      "status": crypto["status"]},
        "zlib": {"version": "1.3.2", "pc": zlib_root / "usr/lib/pkgconfig/zlib.pc",
                 "includes": [zlib_root / "usr/include"], "libdir": zlib_root / "usr/lib",
                 "import": zlib_root / "usr/lib/libz.dll.a", "dll": zlib_root / "usr/bin/msys-z.dll",
                 "status": zlib["status"]},
    }
    result = {"abi": abi, "compiler_receipt_sha256": digest(current_path),
              "pkgconf": {"root": str(pkg_root), "receipt": str(pkg_path), "sha256": digest(pkg_path),
                          "executable": str(pkg_root / "bin/pkgconf.exe")}, "modules": {}}
    for name, row in modules.items():
        if any(not row[field].is_file() for field in ("pc", "import", "dll")):
            raise ContractError("A real FIDO dependency input is missing")
        text = row["pc"].read_text(encoding="utf-8")
        if not re.search(rf"(?m)^Version:\s*{re.escape(row['version'])}\s*$", text):
            raise ContractError("FIDO pkgconf metadata version differs from its pinned library")
        result["modules"][name] = {
            **{key: value for key, value in row.items() if key in ("version", "status")},
            "pc": str(row["pc"]), "pc_sha256": digest(row["pc"]),
            "includes": [str(path) for path in row["includes"]], "libdir": str(row["libdir"]),
            "import": {"path": str(row["import"]), "sha256": digest(row["import"])},
            "dll": {"path": str(row["dll"]), "sha256": digest(row["dll"])},
        }
    return result


def build_settings(inputs, prefix):
    prefix = Path(prefix)
    flags = {"PKG_CONFIG_EXECUTABLE": Path(inputs["pkgconf"]["executable"]).as_posix(),
             "PKG_CONFIG_ARGN": "--dont-define-prefix",
             "CMAKE_REQUIRED_INCLUDES": ";".join(Path(path).as_posix() for row in inputs["modules"].values() for path in row["includes"])}
    environment = {"PKG_CONFIG_LIBDIR": str(prefix / "pkgconfig"),
                   "PKG_CONFIG_PATH": "", "PKG_CONFIG_SYSROOT_DIR": ""}
    return flags, environment


def verify_inputs(manifest, compiler_receipt):
    manifest = Path(manifest)
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if (record.get("status") != "fido-build-only-inputs-ready" or
            record["inputs"]["compiler_receipt_sha256"] != digest(compiler_receipt)):
        raise ContractError("FIDO inputs are for the exact build-only/current-compiler boundary")
    verify_tree(record["prefix"], manifest)
    if describe_inputs(record["spec"]) != record["inputs"]:
        raise ContractError("FIDO dependency inputs changed after metadata preparation")
    flags, environment = build_settings(record["inputs"], record["prefix"])
    if record["cmake_flags"] != flags or record["environment"] != environment:
        raise ContractError("FIDO metadata contains a compiler/environment override outside its exact dependency scope")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = output.with_name(output.name + ".manifest.json")
    if os.name != "nt" or output.exists() or manifest.exists():
        raise ContractError("Windows and a fresh build-only metadata directory are required")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    inputs = describe_inputs(spec)
    pcdir = output / "pkgconfig"
    pcdir.mkdir(parents=True)
    rewrites = {}
    for name, row in inputs["modules"].items():
        original = Path(row["pc"]).read_text(encoding="utf-8")
        variables = {"libdir": Path(row["libdir"]).as_posix(),
                     "includedir": Path(row["includes"][0]).as_posix()}
        if name == "zlib":
            variables["sharedlibdir"] = variables["libdir"]
        text = rewrite_pc(original, variables, [Path(path).as_posix() for path in row["includes"][1:]])
        target = pcdir / f"{name}.pc"
        target.write_text(text, encoding="utf-8", newline="\n")
        rewrites[name] = {"original_sha256": row["pc_sha256"], "sha256": digest(target), "variables": variables}
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    env.update({"PATH": str(Path(inputs["pkgconf"]["executable"]).parent) + os.pathsep +
                        str(Path(os.environ["SystemRoot"]) / "System32"),
                "PKG_CONFIG_LIBDIR": str(pcdir), "PKG_CONFIG_PATH": "", "PKG_CONFIG_SYSROOT_DIR": ""})
    queries = []
    for name, row in inputs["modules"].items():
        for option, expected in (("--modversion", row["version"]), ("--variable=libdir", Path(row["libdir"]).as_posix()),
                                 ("--variable=includedir", Path(row["includes"][0]).as_posix())):
            command = [inputs["pkgconf"]["executable"], "--dont-define-prefix", option, name]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            queries.append({"command": command, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode or result.stdout.strip().replace("\\", "/") != expected:
                raise ContractError("Actual native pkgconf did not resolve the intended build-only dependency")
    if describe_inputs(spec) != inputs:
        raise ContractError("Dependency input changed during metadata preparation")
    flags, environment = build_settings(inputs, output)
    record = {"schema": 1, "status": "fido-build-only-inputs-ready", "prefix": str(output), "spec": spec,
              "inputs": inputs, "rewrites": rewrites, "queries": queries, "files": inventory(output),
              "scope": "Metadata-only views of existing real headers/imports/DLLs; no dependency staging, installation, execution, or admission",
              "cmake_flags": flags, "environment": environment}
    with manifest.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(record, out, indent=2)
        out.write("\n")
    print("Actual native pkgconf resolved all three unchanged MSYS dependency inputs; no payload installed")


if __name__ == "__main__":
    main()
