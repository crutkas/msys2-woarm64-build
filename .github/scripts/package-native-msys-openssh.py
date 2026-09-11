"""Create a deterministic, dependency-deduplicated native MSYS OpenSSH packet."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile


OWNED_FILES = (
    "etc/ssh/ssh_config",
    "usr/bin/findssl.sh",
    "usr/bin/scp.exe",
    "usr/bin/sftp.exe",
    "usr/bin/ssh-add.exe",
    "usr/bin/ssh-agent.exe",
    "usr/bin/ssh-copy-id",
    "usr/bin/ssh-keygen.exe",
    "usr/bin/ssh-keyscan.exe",
    "usr/bin/ssh.exe",
    "usr/lib/ssh/ssh-keysign.exe",
    "usr/lib/ssh/ssh-pkcs11-helper.exe",
    "usr/share/licenses/openssh/LICENCE",
    "usr/share/man/man1/scp.1",
    "usr/share/man/man1/sftp.1",
    "usr/share/man/man1/ssh-add.1",
    "usr/share/man/man1/ssh-agent.1",
    "usr/share/man/man1/ssh-copy-id.1",
    "usr/share/man/man1/ssh-keygen.1",
    "usr/share/man/man1/ssh-keyscan.1",
    "usr/share/man/man1/ssh.1",
    "usr/share/man/man5/ssh_config.5",
    "usr/share/man/man8/ssh-keysign.8",
    "usr/share/man/man8/ssh-pkcs11-helper.8",
)
SOURCE_FILES = {
    "usr/bin/findssl.sh": "contrib/findssl.sh",
    "usr/bin/ssh-copy-id": "contrib/ssh-copy-id",
    "usr/share/licenses/openssh/LICENCE": "LICENCE",
    "usr/share/man/man1/scp.1": "scp.1",
    "usr/share/man/man1/sftp.1": "sftp.1",
    "usr/share/man/man1/ssh-add.1": "ssh-add.1",
    "usr/share/man/man1/ssh-agent.1": "ssh-agent.1",
    "usr/share/man/man1/ssh-copy-id.1": "contrib/ssh-copy-id.1",
    "usr/share/man/man1/ssh-keygen.1": "ssh-keygen.1",
    "usr/share/man/man1/ssh-keyscan.1": "ssh-keyscan.1",
    "usr/share/man/man1/ssh.1": "ssh.1",
    "usr/share/man/man5/ssh_config.5": "ssh_config.5",
    "usr/share/man/man8/ssh-keysign.8": "ssh-keysign.8",
    "usr/share/man/man8/ssh-pkcs11-helper.8": "ssh-pkcs11-helper.8",
}
DEPENDENCIES = (
    ("msys2-runtime", "msys-2.0.dll", "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"),
    ("openssl-msys", "msys-crypto-3.dll", "1f849092ae4f5aa3df1b0a7360c626a7e841c9060e8413220df4e862160c4cb4"),
    ("openssl-msys", "msys-ssl-3.dll", "5db603a6df4757055b5e6947cd6051956da311644ae5e9010cdaaf786693b374"),
    ("zlib-msys", "msys-z.dll", "edb3e9e04c03df58e2f45a416e73c966e4580fedc8b1a60b7630d3cf7815e9d4"),
    ("libxcrypt-msys", "msys-crypt-2.dll", "ce687271a36f2281ee65991b6cb18efbc3eb3bb45b4f9169a31d3d7d23d45dbe"),
)
FORBIDDEN = (
    b".copilot",
    b"session-state",
    b"c:/users",
    b"c:\\users",
    b"/mnt/c/users",
    b"/root/arm64-vnext",
    b"/c/ap13-dcb",
    b"c:/ap13-dcb",
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pe_machine(path):
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError(f"not a PE image: {path}")
        offset = struct.unpack_from("<I", header, 60)[0]
        stream.seek(offset)
        pe = stream.read(26)
    if pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 24)[0] != 0x20B:
        raise ValueError(f"not an ordinary PE32+ image: {path}")
    return struct.unpack_from("<H", pe, 4)[0]


def imports(path, objdump):
    result = subprocess.run(
        [str(objdump), "-p", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        {
            line.split("DLL Name:", 1)[1].strip()
            for line in result.stdout.splitlines()
            if "DLL Name:" in line
        },
        key=str.lower,
    )


def copy_owned(stage, source, payload):
    for relative in OWNED_FILES:
        origin = source / SOURCE_FILES[relative] if relative in SOURCE_FILES else stage / relative
        if not origin.is_file():
            raise FileNotFoundError(f"required OpenSSH-owned file is missing: {origin}")
        target = payload / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)


def deterministic_zip(payload, archive):
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(payload.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(payload).as_posix()
            info = zipfile.ZipInfo(relative, (2026, 9, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if relative.startswith("usr/bin/") or "/ssh-" in relative else 0o644) << 16
            output.writestr(info, path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--openssl-suite-result", type=Path, required=True)
    parser.add_argument("--openssl-native-job", type=Path, required=True)
    parser.add_argument("--openssl-qualification", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--configure-log", type=Path, required=True)
    parser.add_argument("--install-log", type=Path, required=True)
    parser.add_argument("--basic-controls", type=Path, required=True)
    parser.add_argument("--controlled-ssh", type=Path, required=True)
    parser.add_argument("--bash-parent-control", type=Path, required=True)
    parser.add_argument("--bash-preflight", type=Path, required=True)
    parser.add_argument("--agent-control", type=Path, required=True)
    parser.add_argument("--extraction-control", type=Path, required=True)
    parser.add_argument("--controlled-fixture", type=Path, required=True)
    parser.add_argument("--controlled-fixture-patch", type=Path, required=True)
    args = parser.parse_args()
    stage, source, output = args.stage.resolve(), args.source.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")

    suite = json.loads(args.openssl_suite_result.read_text(encoding="utf-8"))
    native_job = json.loads(args.openssl_native_job.read_text(encoding="utf-8"))
    openssl_qualification = json.loads(args.openssl_qualification.read_text(encoding="utf-8"))
    if not (
        suite.get("passed")
        and suite.get("test_count") == 4535
        and suite.get("inputs_unchanged")
        and suite.get("bootstrap_unchanged")
        and native_job.get("passed")
        and native_job.get("observation_count_matches")
        and not native_job.get("unobserved_process_ids")
        and not native_job.get("unrelayed_high_exits")
        and openssl_qualification.get("passed")
        and not openssl_qualification.get("forbidden_marker_errors")
    ):
        raise SystemExit("the exact OpenSSL dependency suite is not fully qualified")
    basic = json.loads(args.basic_controls.read_text(encoding="utf-8"))
    controlled = json.loads(args.controlled_ssh.read_text(encoding="utf-8"))
    bash_controlled = json.loads(args.bash_parent_control.read_text(encoding="utf-8"))
    bash_preflight = json.loads(args.bash_preflight.read_text(encoding="utf-8"))
    agent = json.loads(args.agent_control.read_text(encoding="utf-8"))
    extraction = json.loads(args.extraction_control.read_text(encoding="utf-8"))
    if not (
        basic.get("version_exit") == 0
        and basic.get("keygen_exit") == 0
        and basic.get("fingerprint_exit") == 0
        and basic.get("ssh_sha256") == "9a6eb24cc5667ceadbe73877c97e075587ccec2c34b26fa862e5f7b1ca37d051"
        and controlled.get("passed")
        and [case.get("raw_exit") for case in controlled.get("cases", [])] == [0, 255]
        and bash_controlled.get("passed")
        and [case.get("raw_exit") for case in bash_controlled.get("cases", [])] == [0, 255]
        and bash_preflight.get("exit") == 0
        and agent.get("passed")
        and extraction.get("passed")
    ):
        raise SystemExit("the moved OpenSSH functional controls are incomplete")

    payload = output / "payload"
    provenance = output / "provenance"
    provenance.mkdir(parents=True)
    copy_owned(stage, source, payload)

    files = []
    for path in sorted(payload.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(payload).as_posix()
        row = {"path": relative, "size": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix.lower() in (".exe", ".dll"):
            if pe_machine(path) != 0xAA64:
                raise SystemExit(f"non-ARM64 payload image: {relative}")
            lowered = path.read_bytes().lower()
            hits = [marker.decode(errors="replace") for marker in FORBIDDEN if marker in lowered]
            if hits:
                raise SystemExit(f"forbidden producer marker in {relative}: {hits}")
            row["machine"] = "0xAA64"
            row["imports"] = imports(path, args.objdump)
        files.append(row)

    dependency_names = {dll.lower() for _, dll, _ in DEPENDENCIES}
    payload_names = {Path(row["path"]).name.lower() for row in files}
    duplicates = sorted(dependency_names & payload_names)
    if duplicates:
        raise SystemExit(f"dependency-owned files were duplicated: {duplicates}")

    copied_evidence = {}
    for name, path in (
        ("source-manifest.json", args.source_manifest),
        ("openssl-suite-result.json", args.openssl_suite_result),
        ("openssl-native-job.json", args.openssl_native_job),
        ("openssl-qualification.json", args.openssl_qualification),
        ("configure.log", args.configure_log),
        ("build.log", args.build_log),
        ("install.log", args.install_log),
        ("basic-controls.json", args.basic_controls),
        ("controlled-ssh-result.json", args.controlled_ssh),
        ("bash-parent-control.json", args.bash_parent_control),
        ("bash-preflight.json", args.bash_preflight),
        ("ssh-agent-lifecycle.json", args.agent_control),
        ("extraction-result.json", args.extraction_control),
        ("controlled_ssh.py", args.controlled_fixture),
        ("controlled-ssh-msys-unquoted-paths.patch", args.controlled_fixture_patch),
    ):
        target = provenance / name
        shutil.copy2(path, target)
        copied_evidence[name] = {"path": f"provenance/{name}", "sha256": sha256(target)}

    archive = output / "openssh-native-msys-client-10.5p1-2-aarch64.zip"
    deterministic_zip(payload, archive)
    handoff = {
        "schema": 1,
        "status": "candidate-exported-verified-pending-independent-intake",
        "package": "openssh-native-msys-client",
        "version": "10.5p1-2",
        "scope": "Native ARM64 MSYS OpenSSH client-only payload; dependency-owned runtime and libraries are intentionally deduplicated.",
        "source": {
            "name": "OpenSSH Portable",
            "version": "10.5p1",
            "prepared_manifest_sha256": sha256(args.source_manifest),
        },
        "archive": {
            "path": archive.name,
            "sha256": sha256(archive),
            "files": len(files),
        },
        "files": files,
        "dependencies": [
            {"name": name, "file": dll, "sha256": digest}
            for name, dll, digest in DEPENDENCIES
        ],
        "openssl_suite": {
            "result_sha256": sha256(args.openssl_suite_result),
            "native_job_sha256": sha256(args.openssl_native_job),
            "tests": suite["test_count"],
            "created_processes": native_job["created_processes"],
            "observed_processes": native_job["observed_processes"],
            "unrelayed_high_exits": native_job["unrelayed_high_exits"],
            "shipping_dependency_qualification_sha256": sha256(args.openssl_qualification),
        },
        "features": {
            "client_only": True,
            "openssl": True,
            "zlib": True,
            "pkcs11": True,
            "gssapi": False,
            "kerberos_heimdal": False,
            "libedit": False,
            "fido_security_key": False,
            "stack_protector": False,
            "hardening": False,
            "sandbox": "none",
        },
        "limitations": [
            "Kerberos/GSSAPI/Heimdal are disabled because no complete sealed compatible provider is available.",
            "libedit is disabled because no coherent sealed wide-character ncurses/libedit provider is available.",
            "FIDO/security-key support is disabled because no current-runtime-sealed libfido2 provider is available.",
            "Stack protection and OpenSSH hardening are disabled because GCC 15.0.1 emits unsupported ARM64 PE/SEH frame instructions for affected OpenSSH functions.",
            "This is a client-only limited-MVP candidate and is not a full OpenSSH server provider.",
            "The native Bash parent proof uses a candidate-only substitution of runtime 907afa09 into the sealed d70 Bash payload; it is functional evidence, not a Bash-provider compatibility claim.",
        ],
        "validation": {
            "version": basic["version"],
            "version_exit": basic["version_exit"],
            "keygen_exit": basic["keygen_exit"],
            "fingerprint_exit": basic["fingerprint_exit"],
            "fingerprint": basic["fingerprint"],
            "direct_encrypted_loopback": controlled["passed"],
            "direct_cases": controlled["cases"],
            "bash_parent_encrypted_loopback": bash_controlled["passed"],
            "bash_parent": bash_controlled["parent"],
            "bash_parent_compatibility": bash_preflight["compatibility"],
            "agent_lifecycle": agent["passed"],
            "moved_extraction": extraction["passed"],
            "archive_manifest_errors": extraction["manifest_errors"],
            "real_credentials_or_global_settings_used": False,
        },
        "evidence": copied_evidence,
    }
    (output / "handoff.json").write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"handoff": str(output / "handoff.json"), "sha256": sha256(output / "handoff.json")}))


if __name__ == "__main__":
    main()
