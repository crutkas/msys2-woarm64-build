"""Exercise native OpenSSL against a loopback TLS peer with independent certificate controls."""

import argparse
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import threading

from sources import ContractError, digest


def module_names(profile):
    if profile == "mingw":
        return ("libcrypto-3.dll", "libssl-3.dll")
    if profile == "msys":
        return ("msys-crypto-3.dll", "msys-ssl-3.dll", "msys-2.0.dll")
    raise ContractError("Unknown OpenSSL runtime profile")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("openssl", "output", "pwsh", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--profile", choices=("mingw", "msys"), default="mingw")
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A new private TLS fixture directory is required")
    args.output.mkdir(parents=True)
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    env["PATH"] = str(args.openssl.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    config = args.output / "empty-openssl.cnf"
    config.write_bytes(b"")
    env.update({"HOME": str(args.output), "USERPROFILE": str(args.output),
                "TMP": str(args.output), "TEMP": str(args.output),
                "OPENSSL_CONF": str(config),
                "OPENSSL_MODULES": str(args.openssl.parent.parent / "lib/ossl-modules")})
    names = module_names(args.profile)
    expected_dlls = {str((args.openssl.parent / name).resolve()): digest(args.openssl.parent / name)
                     for name in names}
    for name in ("server", "unrelated"):
        command = [args.openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                   "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                   "-keyout", args.output / f"{name}.key", "-out", args.output / f"{name}.crt"]
        generated = subprocess.run(list(map(str, command)), env=env, capture_output=True, timeout=30)
        (args.output / f"{name}-generation.stdout").write_bytes(generated.stdout)
        (args.output / f"{name}-generation.stderr").write_bytes(generated.stderr)
        if generated.returncode:
            raise ContractError("Native fixture certificate generation failed")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.output / "server.crt", args.output / "server.key")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(3)
    listener.settimeout(20)
    port = listener.getsockname()[1]
    ready, release, stopping = threading.Event(), threading.Event(), threading.Event()
    server_records, server_errors = [], []
    request, response = b"native-client-request", b"native-tls-response"

    def serve():
        for name in ("trusted", "untrusted", "wrong-host"):
            try:
                connection, _ = listener.accept()
                connection.settimeout(20)
                try:
                    stream = context.wrap_socket(connection, server_side=True)
                except ssl.SSLError as error:
                    connection.close()
                    server_records.append({"case": name, "handshake_rejected": str(error)})
                    if name == "trusted":
                        server_errors.append(str(error))
                    continue
                with stream:
                    received = b""
                    while len(received) < len(request):
                        block = stream.recv(4096)
                        if not block:
                            raise OSError("TLS peer closed before its request")
                        received += block
                    if received != request or name != "trusted":
                        raise OSError("Unexpected request or successful negative-case handshake")
                    server_records.append({"case": name, "protocol": stream.version(), "cipher": stream.cipher()})
                    ready.set()
                    if not release.wait(20):
                        raise TimeoutError("Native process observation did not release the TLS response")
                    stream.sendall(response)
                    stream.unwrap().close()
            except OSError as error:
                if not stopping.is_set():
                    server_errors.append(str(error))
                return

    thread = threading.Thread(target=serve)
    thread.start()
    records = []
    try:
        for name, ca, hostname in (("trusted", "server", "localhost"),
                                   ("untrusted", "unrelated", "localhost"),
                                   ("wrong-host", "server", "wrong.invalid")):
            command = [str(args.openssl), "s_client", "-quiet", "-connect", f"127.0.0.1:{port}",
                       "-servername", "localhost", "-verify_hostname", hostname, "-verify_return_error",
                       "-no-CApath", "-no-CAstore", "-CAfile", str(args.output / f"{ca}.crt")]
            process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                if name == "trusted":
                    process.stdin.write(request)
                    process.stdin.flush()
                    if not ready.wait(15):
                        raise ContractError("Native TLS handshake/request did not complete")
                    subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                                    "-ProcessId", str(process.pid),
                                    "-ReportPath", str(args.output / "process.json")], check=True)
                    module_list = ",".join(f"'{name}'" for name in names)
                    script = (
                        f"(Get-Process -Id {process.pid}).Modules | "
                        f"Where-Object {{$_.ModuleName -in {module_list}}} | "
                        "ForEach-Object {[ordered]@{path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                        "ConvertTo-Json -Compress")
                    observed = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", script],
                                              capture_output=True, check=True)
                    modules = json.loads(observed.stdout)
                    actual_dlls = {str(Path(row["path"]).resolve()): row["sha256"].lower() for row in modules}
                    (args.output / "modules.json").write_text(json.dumps(modules, indent=2) + "\n")
                    if actual_dlls != expected_dlls:
                        raise ContractError("Native TLS client loaded different OpenSSL DLLs")
                    release.set()
                stdout, stderr = process.communicate(timeout=25)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            (args.output / f"{name}.stdout").write_bytes(stdout)
            (args.output / f"{name}.stderr").write_bytes(stderr)
            passed = (process.returncode == 0 and stdout == response) if name == "trusted" else (
                process.returncode != 0 and stdout == b"" and
                (b"hostname mismatch" if name == "wrong-host" else b"self-signed certificate") in stderr)
            records.append({"case": name, "command": command, "exit": process.returncode, "passed": passed,
                            "stdout_sha256": digest(args.output / f"{name}.stdout")})
    finally:
        stopping.set()
        release.set()
        listener.close()
        thread.join(25)
        report = {"passed": len(records) == 3 and all(row["passed"] for row in records)
                            and len(server_records) == 3 and not server_errors and not thread.is_alive(),
                  "scope": "Loopback native TLS payload, explicit synthetic CA, unrelated-CA and hostname rejection; no global trust or real credentials",
                  "openssl_sha256": digest(args.openssl), "cases": records,
                  "runtime_profile": args.profile,
                  "expected_dlls": expected_dlls,
                  "server": server_records, "server_errors": server_errors}
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native TLS fixture failed; evidence preserved")
    print("Native TLS payload and both certificate rejection controls passed")


if __name__ == "__main__":
    main()
