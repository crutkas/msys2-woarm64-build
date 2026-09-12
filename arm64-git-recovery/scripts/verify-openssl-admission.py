"""Independently verify and optionally execute a native ARM64 OpenSSL admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tarfile
from typing import Any
import uuid


class AdmissionError(RuntimeError):
    pass


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise AdmissionError(f"{label} is missing: {path}")
    actual = digest(path)
    if actual != expected.casefold():
        raise AdmissionError(
            f"{label} hash mismatch: expected {expected.casefold()}, got {actual}"
        )


def archive_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise AdmissionError(f"Unsafe package path: {value}")
    return path.as_posix()


def parse_pkginfo(data: bytes) -> dict[str, str]:
    values = {}
    for line in data.decode("utf-8", errors="strict").splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            values.setdefault(key, value)
    if "pkgname" not in values or "pkgver" not in values:
        raise AdmissionError("Package archive has incomplete .PKGINFO")
    return values


def verify_archive(admission: dict) -> tuple[int, dict[str, dict[str, Any]]]:
    package = admission["Package"]
    archive = Path(package["Archive"]["Path"])
    require_hash(archive, package["Archive"]["SHA256"], "OpenSSL package")
    if archive.stat().st_size != package["Archive"]["Length"]:
        raise AdmissionError("OpenSSL package length changed")

    manifest_path = Path(package["Manifest"]["Path"])
    require_hash(manifest_path, package["Manifest"]["SHA256"], "Package file manifest")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, list):
        raise AdmissionError("Package file manifest is not a list")
    expected = {}
    for item in manifest:
        rel = archive_path(item["Path"])
        if rel in expected:
            raise AdmissionError(f"Package file manifest repeats path: {rel}")
        expected[rel] = {
            "length": item["Length"],
            "sha256": item["SHA256"].casefold(),
        }

    actual = {}
    pkginfo = None
    with tarfile.open(archive, "r:*") as package_archive:
        for member in package_archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise AdmissionError(f"Unsupported package link entry: {member.name}")
            rel = archive_path(member.name)
            stream = package_archive.extractfile(member)
            if stream is None:
                raise AdmissionError(f"Package entry cannot be read: {rel}")
            data = stream.read()
            actual[rel] = {"length": len(data), "sha256": digest_bytes(data)}
            if rel == ".PKGINFO":
                pkginfo = parse_pkginfo(data)

    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        added = sorted(set(actual) - set(expected))
        changed = sorted(
            rel for rel in set(actual) & set(expected) if actual[rel] != expected[rel]
        )
        raise AdmissionError(
            f"Package manifest mismatch: missing={missing[:5]}, "
            f"added={added[:5]}, changed={changed[:5]}"
        )
    if len(actual) != package["PayloadFiles"]:
        raise AdmissionError("Package payload count changed")
    if pkginfo is None:
        raise AdmissionError("Package archive has no .PKGINFO")
    if pkginfo["pkgname"] != package["Name"] or pkginfo["pkgver"] != package["Version"]:
        raise AdmissionError("Package identity does not match admission")
    return len(actual), actual


def extract_package(
    admission: dict,
    destination: Path,
    expected: dict[str, dict[str, Any]],
) -> Path:
    if destination.exists():
        raise AdmissionError(f"Fresh extraction root already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f"{destination.name}.tmp-{uuid.uuid4().hex}"
    )
    temporary.mkdir()
    try:
        archive = Path(admission["Package"]["Archive"]["Path"])
        extracted = set()
        with tarfile.open(archive, "r:*") as package_archive:
            for member in package_archive.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise AdmissionError(
                        f"Unsupported package link entry: {member.name}"
                    )
                rel = archive_path(member.name)
                record = expected.get(rel)
                if record is None:
                    raise AdmissionError(
                        f"Package extraction found undeclared entry: {rel}"
                    )
                stream = package_archive.extractfile(member)
                if stream is None:
                    raise AdmissionError(f"Package entry cannot be read: {rel}")
                data = stream.read()
                if (
                    len(data) != record["length"]
                    or digest_bytes(data) != record["sha256"]
                ):
                    raise AdmissionError(
                        f"Package entry changed during extraction: {rel}"
                    )
                target = temporary.joinpath(*PurePosixPath(rel).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(data)
                extracted.add(rel)
        if extracted != set(expected):
            raise AdmissionError("Fresh extraction did not materialize every package entry")
        temporary.replace(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def pe_identity(path: Path) -> tuple[str, str]:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise AdmissionError(f"Not a PE image: {path}")
        offset = struct.unpack_from("<I", header, 60)[0]
        if offset < 64 or offset + 26 > path.stat().st_size:
            raise AdmissionError(f"PE header is out of bounds: {path}")
        stream.seek(offset)
        pe = stream.read(26)
    if pe[:4] != b"PE\0\0":
        raise AdmissionError(f"Invalid PE signature: {path}")
    return (
        f"0x{struct.unpack_from('<H', pe, 4)[0]:04X}",
        f"0x{struct.unpack_from('<H', pe, 24)[0]:03X}",
    )


def verify_pe_identities(admission: dict) -> int:
    evidence = admission["NativeReadback"]["PeIdentities"]
    path = Path(evidence["Path"])
    require_hash(path, evidence["SHA256"], "PE identity receipt")
    identities = read_json(path)
    if len(identities) != evidence["Executables"] + evidence["Dlls"]:
        raise AdmissionError("PE identity count changed")
    executables = 0
    dlls = 0
    for item in identities:
        image = Path(item["File"])
        require_hash(image, item["SHA256"], f"Admitted PE {image.name}")
        machine, optional = pe_identity(image)
        if machine != "0xAA64" or optional != "0x20B":
            raise AdmissionError(f"Admitted PE is not ARM64 PE32+: {image}")
        if machine != item["Machine"] or optional != item["OptionalMagic"]:
            raise AdmissionError(f"PE identity receipt changed: {image}")
        if item["IsDll"]:
            dlls += 1
        else:
            executables += 1
    if executables != evidence["Executables"] or dlls != evidence["Dlls"]:
        raise AdmissionError("PE executable/DLL classification changed")
    return len(identities)


def resolve_source_archive(admission: dict) -> Path:
    admission_path = Path(admission["_path"])
    source_root = admission_path.parent.parent / "sources"
    if not source_root.is_dir():
        raise AdmissionError(f"OpenSSL source directory is missing: {source_root}")
    expected = admission["Source"]["ArchiveSHA256"].casefold()
    matches = [
        path
        for path in source_root.iterdir()
        if path.is_file() and not path.name.casefold().endswith((".asc", ".sig"))
        and digest(path) == expected
    ]
    if len(matches) != 1:
        raise AdmissionError(
            f"Expected one hash-bound OpenSSL source archive, found {len(matches)}"
        )
    return matches[0]


def gpg_argument_path(path: Path, gpgv: Path) -> str:
    resolved = path.resolve()
    if os.name == "nt" and gpgv.suffix.casefold() == ".exe":
        drive = resolved.drive.rstrip(":").casefold()
        remainder = resolved.as_posix().split(":/", 1)[1]
        return f"/{drive}/{remainder}"
    return str(resolved)


def locate_gpgv(explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.resolve()
    else:
        discovered = shutil.which("gpgv")
        if discovered:
            path = Path(discovered).resolve()
        elif os.name == "nt":
            path = (
                Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                / "Git"
                / "usr"
                / "bin"
                / "gpgv.exe"
            ).resolve()
        else:
            raise AdmissionError("gpgv is required for fresh source verification")
    if not path.is_file():
        raise AdmissionError(f"gpgv is missing: {path}")
    return path


def verify_detached_signature(
    admission: dict, source_archive: Path, explicit_gpgv: Path | None
) -> dict:
    gpgv = locate_gpgv(explicit_gpgv)
    signature = Path(f"{source_archive}.asc")
    keyring = Path(admission["_path"]).parent.parent / "gnupg" / "pubring.kbx"
    if not signature.is_file():
        raise AdmissionError(f"OpenSSL detached signature is missing: {signature}")
    if not keyring.is_file():
        raise AdmissionError(f"OpenSSL verification keyring is missing: {keyring}")
    command = [
        str(gpgv),
        "--status-fd=1",
        "--keyring",
        gpg_argument_path(keyring, gpgv),
        gpg_argument_path(signature, gpgv),
        gpg_argument_path(source_archive, gpgv),
    ]
    completed = subprocess.run(
        command, capture_output=True, timeout=30, check=False
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    identity = admission["Source"]["Signature"]
    required = (
        f"[GNUPG:] GOODSIG {identity['SigningSubkey'][-16:]}",
        f"[GNUPG:] VALIDSIG {identity['SigningSubkey']}",
        identity["PrimaryFingerprint"],
    )
    if completed.returncode != 0 or any(value not in stdout for value in required):
        raise AdmissionError(
            f"Fresh OpenSSL detached-signature verification failed: "
            f"exit={completed.returncode}, stderr={stderr.strip()}"
        )
    return {
        "status": "valid",
        "gpgv": str(gpgv),
        "gpgv_sha256": digest(gpgv),
        "keyring": str(keyring),
        "keyring_sha256": digest(keyring),
        "signature": str(signature),
        "signature_sha256": digest(signature),
        "raw_exit": completed.returncode,
        "signing_subkey": identity["SigningSubkey"],
        "primary_fingerprint": identity["PrimaryFingerprint"],
        "status_output": stdout,
    }


def verify_evidence(admission: dict) -> Path:
    source_archive = resolve_source_archive(admission)
    require_hash(
        Path(admission["Package"]["Recipe"]["Path"]),
        admission["Package"]["Recipe"]["SHA256"],
        "Prepared OpenSSL recipe",
    )
    source_signature = admission["Source"]["Signature"]
    signature_path = Path(source_signature["Path"])
    require_hash(signature_path, source_signature["SHA256"], "Source signature receipt")
    signature_text = signature_path.read_text(encoding="utf-8", errors="replace")
    if (
        f"[GNUPG:] GOODSIG {source_signature['SigningSubkey'][-16:]}" not in signature_text
        or f"[GNUPG:] VALIDSIG {source_signature['SigningSubkey']}" not in signature_text
        or source_signature["PrimaryFingerprint"] not in signature_text
    ):
        raise AdmissionError("Source signature receipt lost GOODSIG/VALIDSIG identity")

    qualification = admission["Qualification"]
    build_log = Path(qualification["BuildLog"]["Path"])
    require_hash(build_log, qualification["BuildLog"]["SHA256"], "Full test build log")
    build_text = build_log.read_text(encoding="utf-8", errors="replace")
    required = (
        "82-test_ocsp_cert_chain.t ................ ok",
        "All tests successful.",
        f"Files={qualification['Files']}, Tests={qualification['Tests']}",
        f"Result: {qualification['Result']}",
    )
    if any(value not in build_text for value in required):
        raise AdmissionError("Full test build log lost required success evidence")
    if qualification["FeaturesDisabledForRecovery"] or qualification["AssertionsRemoved"]:
        raise AdmissionError("Admission disables features or removes assertions")

    readback = admission["NativeReadback"]
    for key in ("ImportEvidence", "VersionLog", "ProviderLog", "DigestLog"):
        item = readback[key]
        require_hash(Path(item["Path"]), item["SHA256"], key)
    version_text = Path(readback["VersionLog"]["Path"]).read_text(
        encoding="utf-8", errors="replace"
    )
    provider_text = Path(readback["ProviderLog"]["Path"]).read_text(
        encoding="utf-8", errors="replace"
    )
    digest_text = Path(readback["DigestLog"]["Path"]).read_text(
        encoding="utf-8", errors="replace"
    )
    if readback["Version"] not in version_text or "platform: mingwarm64" not in version_text:
        raise AdmissionError("Native version receipt changed")
    for provider in ("default", "legacy"):
        if provider not in provider_text or "status: active" not in provider_text:
            raise AdmissionError(f"Native provider receipt lost {provider}")
    if readback["DigestSHA256"] not in digest_text:
        raise AdmissionError("Native digest receipt changed")
    return source_archive


def run_native(admission: dict, output: Path, prefix: Path | None = None) -> dict:
    prefix = prefix or Path(admission["Package"]["ExtractedPrefix"])
    executable = prefix / "mingwarm64" / "bin" / "openssl.exe"
    require_hash(
        executable,
        next(
            item["SHA256"]
            for item in read_json(Path(admission["NativeReadback"]["PeIdentities"]["Path"]))
            if Path(item["File"]).name.casefold() == "openssl.exe"
        ),
        "Native OpenSSL executable",
    )
    environment = os.environ.copy()
    bin_dir = executable.parent
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment.get('PATH', '')}"
    environment["OPENSSL_MODULES"] = str(
        prefix / "mingwarm64" / "lib" / "ossl-modules"
    )
    commands = [
        ("version", ["version", "-a"], None),
        (
            "providers",
            ["list", "-providers", "-provider", "default", "-provider", "legacy"],
            None,
        ),
        ("digest", ["dgst", "-sha256"], b"native-arm64-openssl-3.6.4"),
    ]
    results = []
    for name, arguments, stdin in commands:
        completed = subprocess.run(
            [str(executable), *arguments],
            input=stdin,
            capture_output=True,
            env=environment,
            timeout=30,
            check=False,
        )
        results.append({
            "name": name,
            "arguments": arguments,
            "raw_exit": completed.returncode,
            "stdout": completed.stdout.decode("utf-8", errors="replace"),
            "stderr": completed.stderr.decode("utf-8", errors="replace"),
        })
        if completed.returncode != 0:
            raise AdmissionError(
                f"Native OpenSSL {name} failed with exit {completed.returncode}"
            )
    version = results[0]["stdout"]
    providers = results[1]["stdout"]
    expected_digest = digest_bytes(b"native-arm64-openssl-3.6.4")
    if admission["NativeReadback"]["Version"] not in version or "platform: mingwarm64" not in version:
        raise AdmissionError("Fresh native OpenSSL version output is incompatible")
    if not all(value in providers for value in ("default", "legacy", "status: active")):
        raise AdmissionError("Fresh native provider activation failed")
    if expected_digest not in results[2]["stdout"]:
        raise AdmissionError("Fresh native SHA-256 result is incorrect")
    receipt = {
        "schema": 1,
        "status": "verified-native-arm64-openssl-admission",
        "admission": {
            "path": str(Path(admission["_path"])),
            "sha256": admission["_sha256"],
        },
        "executable": {
            "path": str(executable),
            "sha256": digest(executable),
            "machine": "0xAA64",
            "optional_magic": "0x20B",
        },
        "execution_root": str(prefix),
        "fresh_package_extraction": (
            prefix.resolve() != Path(admission["Package"]["ExtractedPrefix"]).resolve()
        ),
        "commands": results,
        "expected_digest": expected_digest,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def verify(
    admission_path: Path,
    execute: bool,
    output: Path | None,
    gpgv: Path | None = None,
    extract_root: Path | None = None,
) -> dict:
    admission = read_json(admission_path)
    admission["_path"] = str(admission_path.resolve())
    admission["_sha256"] = digest(admission_path)
    if admission.get("Status") != "admitted-native-mingwarm64-openssl":
        raise AdmissionError("OpenSSL admission status is not admitted")
    if admission.get("IntegrationInstalled") is not False:
        raise AdmissionError("OpenSSL admission unexpectedly claims shared installation")
    payload_files, package_files = verify_archive(admission)
    source_archive = verify_evidence(admission)
    signature_verification = verify_detached_signature(
        admission, source_archive, gpgv
    )
    pe_files = verify_pe_identities(admission)
    result = {
        "status": "verified",
        "verifier_sha256": digest(Path(__file__).resolve()),
        "admission_sha256": admission["_sha256"],
        "source_archive": str(source_archive),
        "source_archive_sha256": admission["Source"]["ArchiveSHA256"].casefold(),
        "source_signature_verification": signature_verification,
        "package_archive": admission["Package"]["Archive"]["Path"],
        "package_archive_sha256": admission["Package"]["Archive"]["SHA256"].casefold(),
        "payload_files": payload_files,
        "pe_files": pe_files,
        "qualification": {
            "files": admission["Qualification"]["Files"],
            "tests": admission["Qualification"]["Tests"],
            "result": admission["Qualification"]["Result"],
            "features_disabled_for_recovery": admission["Qualification"][
                "FeaturesDisabledForRecovery"
            ],
            "assertions_removed": admission["Qualification"]["AssertionsRemoved"],
        },
        "fresh_execution": False,
        "fresh_package_extraction": False,
    }
    execution_root = None
    if extract_root is not None:
        execution_root = extract_package(admission, extract_root, package_files)
        result["fresh_package_extraction"] = True
        result["extraction_root"] = str(execution_root)
        result["extracted_files"] = payload_files
    if execute:
        if output is None:
            raise AdmissionError("--output is required with --execute")
        run_native(admission, output, execution_root)
        result["fresh_execution"] = True
        result["execution_receipt"] = str(output)
        result["execution_receipt_sha256"] = digest(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--gpgv", type=Path)
    parser.add_argument("--extract-root", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify(
            arguments.admission,
            arguments.execute,
            arguments.output,
            arguments.gpgv,
            arguments.extract_root,
        )
    except (AdmissionError, KeyError, OSError, ValueError, tarfile.TarError) as exc:
        raise SystemExit(f"OpenSSL admission verification failed: {exc}") from exc
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        with arguments.report.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
