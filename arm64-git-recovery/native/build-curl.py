"""Build the required native curl transport closure without silent optional-library loss."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def build(source, manifest, prefix, dependencies, output, cmake, ninja, perl, jobs,
          openssl_libdir="lib", pending_dependencies=()):
    source, manifest, prefix, dependencies, output, cmake, ninja, perl = map(lambda p: Path(p).resolve(),
        (source, manifest, prefix, dependencies, output, cmake, ninja, perl))
    if os.name != "nt" or output.exists() or not 1 <= jobs <= 8:
        raise ContractError("Requires Windows, new output and explicit 1-8 jobs")
    verify_tree(source, manifest)
    identity = json.loads(manifest.read_text())["source"]
    if identity["id"] != "curl" or identity["version"] != "8.22.0":
        raise ContractError("Expected locked curl 8.22.0")
    dependency_files = inventory(dependencies)
    for rel in ("include/openssl/ssl.h", "include/ares.h", "include/brotli/decode.h",
                "include/zstd.h", "include/nghttp2/nghttp2.h", "include/libssh2.h",
                "include/idn2.h", "include/libpsl.h", "include/zlib.h"):
        if rel not in dependency_files:
            raise ContractError(f"Required full transport dependency is missing: {rel}")
    if openssl_libdir not in ("lib", "lib64", "lib-arm64"):
        raise ContractError("OpenSSL library directory must be explicit")
    for name in ("libcrypto.dll.a", "libssl.dll.a"):
        if f"{openssl_libdir}/{name}" not in dependency_files:
            raise ContractError(f"Required OpenSSL import library missing: {openssl_libdir}/{name}")
    compiler = prefix / "bin/gcc.exe"
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("MSYS", "MINGW", "CMAKE", "PKG_CONFIG", "GCC_")) or name in (
                "CC", "CXX", "CFLAGS", "LDFLAGS", "CPPFLAGS", "COMPILER_PATH", "LIBRARY_PATH", "CPATH"):
            del env[name]
    env["PATH"] = os.pathsep.join(map(str, (
        prefix / "bin", dependencies / "bin", cmake.parent, ninja.parent,
        Path(os.environ["SystemRoot"]) / "System32")))
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
    support = support_identities(compiler, prefix, env)
    tools = {str(p): digest(p) for p in (compiler, prefix / "bin/ar.exe", prefix / "bin/windres.exe",
                                       cmake, ninja, perl)}
    output.mkdir(parents=True)
    copied, stage, directory = output / "source", output / "stage", output / "build"
    shutil.copytree(source, copied)
    options = {
        "CMAKE_BUILD_TYPE": "Release", "CMAKE_INSTALL_PREFIX": stage.as_posix(),
        "CMAKE_C_COMPILER": compiler.as_posix(), "CMAKE_MAKE_PROGRAM": ninja.as_posix(),
        "CMAKE_PREFIX_PATH": dependencies.as_posix(), "PERL_EXECUTABLE": perl.as_posix(),
        "CMAKE_RC_COMPILER": (prefix / "bin/windres.exe").as_posix(),
        "BUILD_SHARED_LIBS": "ON", "BUILD_STATIC_LIBS": "ON", "BUILD_CURL_EXE": "ON",
        "CMAKE_DLL_NAME_WITH_SOVERSION": "ON", "CURL_LIBCURL_SOVERSION": "ON",
        "CURL_USE_PKGCONFIG": "OFF", "CURL_USE_OPENSSL": "ON", "CURL_USE_SCHANNEL": "ON",
        "CURL_DEFAULT_SSL_BACKEND": "schannel", "CURL_WINDOWS_SSPI": "ON",
        "CURL_ENABLE_NTLM": "ON", "ENABLE_ARES": "ON", "CURL_ZLIB": "ON",
        "CURL_BROTLI": "ON", "CURL_ZSTD": "ON", "USE_NGHTTP2": "ON",
        "USE_LIBIDN2": "ON", "CURL_USE_LIBPSL": "ON", "CURL_USE_LIBSSH2": "ON",
        "BUILD_TESTING": "ON", "CURL_BUILD_EVERYTHING": "ON",
        "BUILD_LIBCURL_DOCS": "ON", "BUILD_MISC_DOCS": "ON", "ENABLE_CURL_MANUAL": "ON",
        "OPENSSL_ROOT_DIR": dependencies.as_posix(),
        "LIB_EAY": (dependencies / openssl_libdir / "libcrypto.dll.a").as_posix(),
        "SSL_EAY": (dependencies / openssl_libdir / "libssl.dll.a").as_posix()
    }
    report = {"schema": 1, "status": "failed", "source": identity, "options": options,
              "build_host": "windows-arm64-native", "documentation_driver": "bootstrap-perl",
              "dependencies": dependency_files, "tools": tools, "support_tools": support,
              "pending_dependency_qualification": list(pending_dependencies),
              "openssl_library_directory": openssl_libdir,
              "commands": []}

    def run(name, args):
        with (output / f"{name}.log").open("xb") as log:
            result = subprocess.run(list(map(str, args)), cwd=output, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        report["commands"].append({"name": name, "args": list(map(str, args)), "exit": result.returncode,
                                   "log_sha256": digest(output / f"{name}.log")})
        if result.returncode:
            raise ContractError(f"curl {name} failed; inspect {output / (name + '.log')}")

    try:
        run("configure", [cmake, "-S", copied, "-B", directory, "-G", "Ninja",
                          *[f"-D{k}={v}" for k, v in options.items()]])
        run("build", [cmake, "--build", directory, "--parallel", jobs])
        run("install", [cmake, "--install", directory])
        if not (stage / "bin/libcurl-4.dll").is_file():
            raise ContractError("Git for Windows lazy loading requires the actual ABI-versioned libcurl-4.dll")
        # Ship only actual dependency DLLs. Every copy is inventoried and later
        # raw-native-gated together with curl; never copy an emulated driver.
        for dll in (dependencies / "bin").glob("*.dll"):
            shutil.copyfile(dll, stage / "bin" / dll.name)
        executable = stage / "bin/curl.exe"
        run("features", [executable, "--version"])
        features = (output / "features.log").read_text()
        required = ("https", "sftp", "scp", "HTTP2", "SSL", "brotli", "zstd",
                    "AsynchDNS", "IDN", "PSL", "MultiSSL", "Schannel", "OpenSSL")
        missing = [feature for feature in required if feature.lower() not in features.lower()]
        if missing:
            raise ContractError(f"curl silently lost required transport features: {missing}")
        if inventory(dependencies) != dependency_files:
            raise ContractError("Dependencies changed while curl built")
        verify_support(support, compiler, prefix, env)
        verify_tree(source, manifest)
        if any(digest(path) != value for path, value in tools.items()):
            raise ContractError("Toolchain or build driver changed")
        report["files"] = inventory(stage)
        report["status"] = "native-curl-built-features-present-not-functionally-accepted"
        report["pending"] = ["HTTPS success/untrusted-CA controls", "SSH/SFTP route", "full Git integration",
                             "relocation of configured resources", "native Perl replay",
                             *[f"Dependency qualification: {name}" for name in pending_dependencies]]
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "manifest", "prefix", "dependencies", "output", "cmake", "ninja", "perl"):
        p.add_argument(f"--{key}", required=True, type=Path)
    p.add_argument("--jobs", required=True, type=int)
    p.add_argument("--openssl-libdir", choices=("lib", "lib64", "lib-arm64"), default="lib")
    p.add_argument("--pending-dependency", action="append", default=[],
                   help="Explicitly propagate a dependency qualification blocker; never a distribution acceptance")
    a = p.parse_args()
    build(a.source, a.manifest, a.prefix, a.dependencies, a.output, a.cmake, a.ninja, a.perl, a.jobs,
          a.openssl_libdir, a.pending_dependency)


if __name__ == "__main__":
    main()
