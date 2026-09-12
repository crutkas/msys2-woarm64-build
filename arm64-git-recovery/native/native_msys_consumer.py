"""Qualify installed MSYS library APIs with a held process and exact relocated DLL identities."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from bounded_process import run
from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree

PROFILES = {
    "zlib-msys": {
        "fixture": "native-msys-zlib-consumer.c", "binary": "native-zlib-consumer.exe",
        "dlls": ["msys-z.dll"], "imports": ["libz.dll.a"], "marker": b"native-zlib-consumer-passed",
        "scope": "Native MSYS LP64 zlib buffer compression/decompression, corrupt-data rejection and real gzip file roundtrip",
    },
    "libxcrypt": {
        "fixture": "native-crypt-consumer.c", "binary": "native-crypt-consumer.exe",
        "dlls": ["msys-crypt-2.dll"], "imports": ["libcrypt.dll.a"],
        "marker": b"native-crypt-consumer-passed",
        "scope": "Synthetic upstream bcrypt known answer, mismatch, EINVAL, salt and hash roundtrip; no OS credential or authentication operation",
    },
    "libiconv-bootstrap": {
        "fixture": "native-iconv-consumer.c", "binary": "native-iconv-consumer.exe",
        # Both DLLs export locale_charset; select the standalone charset API explicitly.
        "dlls": ["msys-iconv-2.dll", "msys-charset-1.dll"], "imports": ["libcharset.dll.a", "libiconv.dll.a"],
        "marker": b"native-iconv-consumer-passed",
        "scope": "UTF-8/UTF-16LE exact roundtrip, invalid sequence/encoding rejection and locale charset API; CLI NLS remains explicitly disabled",
    },
}


def main(default_package=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PROFILES, default=default_package, required=default_package is None)
    for name in ("stage", "manifest", "prefix", "compiler-receipt", "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    profile = PROFILES[args.package]
    if args.output.exists():
        raise ContractError("A fresh installed library consumer directory is required")
    verify_tree(args.stage, args.manifest)
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(producer)
    build = json.loads(args.manifest.read_text())
    if (build.get("status") != "native-msys-library-built-checked-bootstrap-driver" or
            build.get("package") != args.package or
            build["compiler_receipt_sha256"] != digest(args.compiler_receipt) or
            Path(producer["prefix"]).resolve() != args.prefix.resolve()):
        raise ContractError("Crypt stage and admitted SDK are not the same build epoch")
    original = inventory(args.stage)
    payload = args.output / "relocated"
    shutil.copytree(args.stage, payload)
    binary_dir = payload / "usr/bin"
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", binary_dir / "msys-2.0.dll")
    fixture = Path(__file__).parent / "fixtures" / profile["fixture"]
    binary = binary_dir / profile["binary"]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": str(args.prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(args.output), "USERPROFILE": str(args.output),
                "TMP": str(args.output), "TEMP": str(args.output)})
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    report = {"passed": False, "package": args.package, "stage_manifest_sha256": digest(args.manifest),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "fixture_sha256": digest(fixture), "support": support,
              "scope": profile["scope"], "build_limitations": build.get("limitations", [])}
    expected_dlls = {name: digest(binary_dir / name) for name in (*profile["dlls"], "msys-2.0.dll")}

    def observe(pid):
        ready = args.output / "ready"
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not ready.exists() or ready.read_text().strip() != str(pid):
            observed = ready.read_text().strip() if ready.exists() else "not ready"
            raise ContractError(f"Installed library native-PID handshake differs: expected {pid}, got {observed}")
        path = args.output / "native-process.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                        "-ProcessId", str(pid), "-ReportPath", str(path)], check=True)
        identity = json.loads(path.read_text())
        if identity.get("Passed") is not True or Path(identity["Processes"][0]["ImagePath"]).resolve() != binary.resolve():
            raise ContractError("Crypt fixture is not the relocated native executable")
        command = (f"(Get-Process -Id {pid}).Modules | ForEach-Object {{"
                   "[ordered]@{name=$_.ModuleName;path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                   "ConvertTo-Json -Compress")
        result = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", command], capture_output=True, check=True)
        modules = json.loads(result.stdout)
        (args.output / "loaded-modules.json").write_text(json.dumps(modules, indent=2) + "\n")
        loaded = {row["name"].lower(): row for row in modules}
        for name, sha in expected_dlls.items():
            row = loaded.get(name)
            if (row is None or Path(row["path"]).resolve() != (binary_dir / name).resolve() or
                    row["sha256"].lower() != sha):
                raise ContractError("Native consumer loaded an unexpected library/runtime")
        (args.output / "continue").write_bytes(b"go\n")

    try:
        command = [compiler, "-O2", "-g", "-I" + str(payload / "usr/include"), fixture,
                   *[payload / "usr/lib" / name for name in profile["imports"]], "-o", binary]
        report["compile_command"] = list(map(str, command))
        with (args.output / "compile.log").open("xb") as log:
            report["compile"] = run(command, cwd=args.output, env=env, log=log, timeout=120)
        if not report["compile"]["passed"]:
            raise ContractError("Installed native crypt consumer compilation failed")
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(payload), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Installed crypt consumer PE gate failed")
        before_run = inventory(payload)
        runtime_env = {**env, "PATH": str(binary_dir) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")}
        with (args.output / "run.log").open("xb") as log:
            report["process"] = run([binary, args.output], cwd=args.output, env=runtime_env, log=log, timeout=45, on_started=observe)
        if (not report["process"]["passed"] or profile["marker"] not in (args.output / "run.log").read_bytes()
                or inventory(payload) != before_run):
            raise ContractError("Installed native crypt behavior or input integrity failed")
        verify_tree(args.stage, args.manifest)
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(support, compiler, args.prefix, env)
        if inventory(args.stage) != original:
            raise ContractError("Installed crypt source stage changed")
        report.update({"passed": True, "dlls": expected_dlls, "consumer_sha256": digest(binary)})
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Installed native {args.package} API and exact relocated runtime/library closure passed")


if __name__ == "__main__":
    main()
