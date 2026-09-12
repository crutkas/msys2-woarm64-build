"""Offline native curl HTTPS success and certificate-rejection scenarios."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import threading

from sources import ContractError, digest


def test(curl, openssl, output, pwsh, process_gate, artifact_gate, libcurl_name="libcurl.dll"):
    curl, openssl, output = map(lambda p: Path(p).resolve(), (curl, openssl, output))
    if output.exists():
        raise ContractError("New HTTPS fixture directory required")
    output.mkdir(parents=True)
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (openssl.parent, curl.parent,
                                          Path(os.environ["SystemRoot"]) / "System32")))
    subprocess.run([str(pwsh), "-NoProfile", "-File", str(artifact_gate),
                    "-Root", str(curl.parent), "-ReportPath", str(output / "artifacts.json")], check=True)
    expected_dlls = {path.name.lower(): {"path": str(path.resolve()), "sha256": digest(path)}
                     for path in curl.parent.glob("*.dll")}
    payload = b"native-arm64-curl-https-fixture\n"
    config = output / "certificate.cnf"
    config.write_text("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
                      "[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\n"
                      "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,digitalSignature,keyEncipherment\n")
    generation = subprocess.run([str(openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                                  "-days", "1", "-config", str(config), "-keyout", str(output / "key.pem"),
                                  "-out", str(output / "cert.pem")], env=env, capture_output=True)
    (output / "certificate-generation.stdout").write_bytes(generation.stdout)
    (output / "certificate-generation.stderr").write_bytes(generation.stderr)
    if generation.returncode:
        raise ContractError("Native OpenSSL test-certificate generation failed")

    state = {}
    resets, server_errors = [], []

    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            self.case = state["case"]
            self.ready, self.release = state["ready"], state["release"]
            self.connection.settimeout(15)
            try:
                super().handle()
            except ConnectionResetError as error:
                resets.append({"case": self.case, "error": str(error)})
                if self.case[1] == "trusted":
                    server_errors.append(str(error))
            except TimeoutError as error:
                server_errors.append(str(error))

        def do_GET(self):
            if self.case[1] == "trusted":
                self.ready.set()
                if not self.release.wait(20):
                    raise TimeoutError("Native curl observation did not release the response")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = False

    server = Server(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(output / "cert.pem"), str(output / "key.pem"))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    records = []
    try:
        for backend in ("openssl", "schannel"):
            child = {**env, "CURL_SSL_BACKEND": backend}
            version = subprocess.run([str(curl), "-q", "--version"], env=child,
                                     capture_output=True, check=True)
            (output / f"{backend}-version.stdout").write_bytes(version.stdout)
            selected = re.sub(r"\([^)]*\)", "", version.stdout.decode().splitlines()[0])
            if ("OpenSSL/" if backend == "openssl" else "Schannel") not in selected:
                raise ContractError("Requested curl TLS backend was not selected")
            for name, hostname, trusted in (("trusted", "localhost", True),
                                             ("untrusted", "localhost", False),
                                             ("wrong-host", "127.0.0.1", True)):
                state.update({"case": [backend, name], "ready": threading.Event(), "release": threading.Event()})
                argv = [str(curl), "-q", "--silent", "--show-error", "--fail", "--noproxy", "*",
                        "--connect-timeout", "5", "--max-time", "30"]
                if trusted:
                    argv += ["--cacert", str(output / "cert.pem")]
                argv += [f"https://{hostname}:{server.server_port}/fixture"]
                process = subprocess.Popen(argv, env=child, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = b"", b""
                try:
                    if name == "trusted":
                        if not state["ready"].wait(10):
                            raise ContractError("Curl did not complete the native TLS request")
                        subprocess.run([str(pwsh), "-NoProfile", "-File", str(process_gate),
                                        "-ProcessId", str(process.pid),
                                        "-ReportPath", str(output / f"{backend}-process.json")], check=True)
                        script = (f"(Get-Process -Id {process.pid}).Modules | ForEach-Object {{"
                                  "[ordered]@{name=$_.ModuleName;path=$_.FileName;"
                                  "sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | ConvertTo-Json -Compress")
                        observed = subprocess.run([str(pwsh), "-NoProfile", "-Command", script],
                                                  capture_output=True, check=True)
                        modules = json.loads(observed.stdout)
                        (output / f"{backend}-modules.json").write_text(json.dumps(modules, indent=2) + "\n")
                        product_modules = {row["name"].lower(): {
                            "path": str(Path(row["path"]).resolve()), "sha256": row["sha256"].lower()}
                            for row in modules if row["name"].lower() in expected_dlls}
                        if libcurl_name not in product_modules or any(
                                row != expected_dlls[name] for name, row in product_modules.items()):
                            raise ContractError("Curl loaded a different native product DLL")
                        state["release"].set()
                    stdout, stderr = process.communicate(timeout=35)
                finally:
                    state["release"].set()
                    if process.poll() is None:
                        process.kill()
                        stdout, stderr = process.communicate()
                    (output / f"{backend}-{name}.stdout.bin").write_bytes(stdout)
                    (output / f"{backend}-{name}.stderr.bin").write_bytes(stderr)
                passed = ((process.returncode == 0 and stdout == payload and not stderr)
                          if name == "trusted" else (process.returncode == 60 and stdout == b""))
                records.append({"backend": backend, "case": name, "argv": argv, "exit": process.returncode,
                                "passed": passed, "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                                "stderr": stderr.decode("utf-8", errors="backslashreplace")})
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
        report = {"schema": 1, "passed": len(records) == 6 and all(row["passed"] for row in records) and not server_errors,
                  "scope": "Native selected TLS backends and exact product DLLs; synthetic CA; curlrc disabled; no global trust or real credentials",
                  "curl_sha256": digest(curl), "openssl_sha256": digest(openssl),
                  "cases": records, "expected_negative_connection_resets": resets, "server_errors": server_errors}
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native curl HTTPS scenario failed; complete evidence retained")
    print("Native curl: both TLS backends accepted trusted HTTPS and rejected CA/hostname controls")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("curl", "openssl", "output", "pwsh", "process-gate", "artifact-gate"):
        p.add_argument(f"--{key}", type=Path, required=True)
    p.add_argument("--libcurl-name", choices=("libcurl.dll", "libcurl-4.dll"), default="libcurl.dll")
    a = p.parse_args()
    test(a.curl, a.openssl, a.output, a.pwsh, a.process_gate, a.artifact_gate, a.libcurl_name)


if __name__ == "__main__":
    main()
