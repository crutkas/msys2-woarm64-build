"""Build native libssh2 with OpenSSL/zlib and its offline upstream test suite."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "prefix", "openssl", "openssl-receipt", "zlib",
                 "cmake", "ninja", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 11), required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Native Windows and a fresh build output are required")
    verify_tree(args.source, args.manifest)
    source = json.loads(args.manifest.read_text())["source"]
    if source["id"] != "libssh2" or source["version"] != "1.11.1":
        raise ContractError("Expected pinned libssh2 1.11.1")
    openssl_receipt = json.loads(args.openssl_receipt.read_text())
    if openssl_receipt["files"] != inventory(args.openssl):
        raise ContractError("OpenSSL candidate payload differs from its receipt")
    crypto = args.openssl / openssl_receipt["library_directory"] / "libcrypto.dll.a"
    if not crypto.is_file() or not (args.zlib / "include/zlib.h").is_file():
        raise ContractError("Real OpenSSL and zlib development inputs are required")
    dependencies = {"openssl": inventory(args.openssl), "zlib": inventory(args.zlib)}
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("MSYS", "MINGW", "CMAKE", "PKG_CONFIG", "GCC_")) or key in (
                "CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
                "CPATH", "COMPILER_PATH", "LIBRARY_PATH"):
            del env[key]
    env["PATH"] = os.pathsep.join(map(str, (
        args.prefix / "bin", args.openssl / "bin", args.zlib / "bin",
        args.cmake.parent, args.ninja.parent, Path(os.environ["SystemRoot"]) / "System32")))
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    ctest = args.cmake.with_name("ctest.exe")
    tools = {str(path): digest(path) for path in (compiler, args.cmake, ctest, args.ninja,
                                                args.prefix / "bin/ar.exe", args.prefix / "bin/windres.exe")}
    args.output.mkdir(parents=True)
    copied, build, stage = (args.output / name for name in ("source", "build", "stage"))
    shutil.copytree(args.source, copied)
    options = {
        "CMAKE_BUILD_TYPE": "Release", "CMAKE_C_COMPILER": compiler.as_posix(),
        "CMAKE_MAKE_PROGRAM": args.ninja.as_posix(), "CMAKE_INSTALL_PREFIX": stage.as_posix(),
        "CMAKE_INSTALL_LIBDIR": "lib", "CMAKE_RC_COMPILER": (args.prefix / "bin/windres.exe").as_posix(),
        "CMAKE_PREFIX_PATH": f"{args.openssl.as_posix()};{args.zlib.as_posix()}",
        "BUILD_STATIC_LIBS": "ON", "BUILD_SHARED_LIBS": "ON", "BUILD_EXAMPLES": "ON",
        "BUILD_TESTING": "ON", "CRYPTO_BACKEND": "OpenSSL", "ENABLE_ZLIB_COMPRESSION": "ON",
        "OPENSSL_INCLUDE_DIR": (args.openssl / "include").as_posix(),
        "LIB_EAY": crypto.as_posix(),
        "SSL_EAY": (crypto.parent / "libssl.dll.a").as_posix(),
        "OPENSSL_ROOT_DIR": args.openssl.as_posix(), "OPENSSL_USE_STATIC_LIBS": "OFF",
        "RUN_DOCKER_TESTS": "OFF", "RUN_SSHD_TESTS": "OFF",
    }
    report = {"status": "failed", "source": source, "options": options, "tools": tools,
              "support": support, "dependencies": dependencies, "commands": [],
              "scope": "Native static/shared libssh2 with offline upstream tests; SSH service fixtures pending",
              "openssl_candidate_status": openssl_receipt["status"],
              "openssl_receipt_sha256": digest(args.openssl_receipt),
              "pending": ["Live SSH/SFTP fixture", "OpenSSL full acceptance", "Full Git integration"]}

    def execute(name, command):
        with (args.output / f"{name}.log").open("xb") as log:
            result = subprocess.run(list(map(str, command)), env=env, cwd=args.output,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        report["commands"].append({"name": name, "argv": list(map(str, command)),
                                   "exit": result.returncode, "log_sha256": digest(args.output / f"{name}.log")})
        if result.returncode:
            raise ContractError(f"libssh2 {name} failed; evidence retained")

    try:
        execute("configure", [args.cmake, "-S", copied, "-B", build, "-G", "Ninja",
                              *[f"-D{key}={value}" for key, value in options.items()]])
        execute("build", [args.cmake, "--build", build, "--parallel", str(args.jobs)])
        execute("tests", [ctest, "--test-dir", build, "--parallel", str(args.jobs), "--timeout", "60",
                          "--output-on-failure", "--output-junit", args.output / "tests.xml"])
        spec = importlib.util.spec_from_file_location(
            "native_cmake_results", Path(__file__).with_name("build-native-cmake.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report["passed_tests"] = module.ctest_results(args.output / "tests.xml")
        execute("install", [args.cmake, "--install", build])
        license_dir = stage / "share/licenses/libssh2"
        license_dir.mkdir(parents=True)
        shutil.copyfile(copied / "COPYING", license_dir / "COPYING")
        verify_tree(args.source, args.manifest)
        verify_support(support, compiler, args.prefix, env)
        if (dependencies != {"openssl": inventory(args.openssl), "zlib": inventory(args.zlib)}
                or any(digest(path) != value for path, value in tools.items())):
            raise ContractError("Dependency or tool changed")
        report["files"] = inventory(stage)
        report["status"] = "native-libssh2-built-offline-tested-service-fixtures-pending"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
