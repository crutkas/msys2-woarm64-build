"""Real loopback SSH public-key/host-key verification with private ephemeral test credentials."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from artifact import ArtifactError, pe_identity, sha256, write_json


async def exercise(client, driver, output, bash=None):
    sys.path.insert(0, str(driver))
    import asyncssh
    for path in driver.rglob("*.pyd"):
        if pe_identity(path)["machine"] != "0xAA64":
            raise ArtifactError("SSH test server extension is not native ARM64")
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    key_file = output / "client-key"
    key_file.write_bytes(client_key.export_private_key("openssh"))
    environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "USERNAME", "USERDOMAIN", "PROGRAMDATA")
                   if name in os.environ}
    environment["PATH"] = str(client.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    environment["HOME"] = environment["USERPROFILE"] = str(output)
    # Restrict only the disposable key, never a real user's SSH/authentication configuration.
    acl_script = (
        "$ErrorActionPreference='Stop';$p=$env:MVP_SSH_PRIVATE_KEY;$id=[Security.Principal.WindowsIdentity]::GetCurrent().User;"
        "$acl=[Security.AccessControl.FileSecurity]::new();$acl.SetOwner($id);"
        "$acl.SetAccessRuleProtection($true,$false);"
        "$rule=[Security.AccessControl.FileSystemAccessRule]::new($id,'FullControl','Allow');"
        "$acl.AddAccessRule($rule);Set-Acl -LiteralPath $p -AclObject $acl"
    )
    pwsh = Path(os.environ["MVP_POWERSHELL"])
    acl = subprocess.run([pwsh, "-NoProfile", "-Command", acl_script],
                         env={**environment, "MVP_SSH_PRIVATE_KEY": str(key_file)}, capture_output=True, text=True, timeout=30)
    (output / "key-acl.stdout").write_text(acl.stdout)
    (output / "key-acl.stderr").write_text(acl.stderr)
    if acl.returncode:
        raise ArtifactError("Could not restrict the disposable SSH fixture key")
    nonce = secrets.token_hex(16)
    events = []

    class Server(asyncssh.SSHServer):
        def connection_made(self, conn):
            self.conn = conn
            events.append({"event": "connected", "peer": conn.get_extra_info("peername")})

        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            valid = username == "mvp-fixture" and key == client_key.convert_to_public()
            events.append({"event": "public_key_auth", "valid": valid})
            return valid

    async def handle(process):
        if process.command != "prove " + nonce:
            process.exit(91)
            return
        events.append({"event": "authenticated_command", "command": process.command,
                       "send_cipher": process.get_extra_info("send_cipher"),
                       "recv_cipher": process.get_extra_info("recv_cipher")})
        process.stdout.write("native-ssh-ok:" + nonce + "\n")
        process.exit(0)

    server = await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[server_key],
                                          process_factory=handle, encoding="utf-8")
    port = server.get_port()
    known = output / "known_hosts"
    known.write_bytes(f"[127.0.0.1]:{port} ".encode() + server_key.export_public_key("openssh"))
    wrong = output / "wrong_known_hosts"
    wrong.write_bytes(f"[127.0.0.1]:{port} ".encode() + asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh"))
    cases = []
    try:
        for label, hosts in (("correct-host-key", known), ("wrong-host-key", wrong)):
            command = [str(client), "-F", str(output / "empty_config"), "-p", str(port),
                       "-i", str(key_file), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                       "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={hosts}",
                       "-o", f"GlobalKnownHostsFile={output / 'empty_config'}",
                       "-o", "ConnectTimeout=10", "-o", "ProxyCommand=none",
                       "mvp-fixture@127.0.0.1", "prove", nonce]
            if bash is not None:
                command = [str(bash), "--noprofile", "--norc", "-c", 'exec "$@"', "native-ssh-fixture", *command]
            process = await asyncio.create_subprocess_exec(*command, env=environment, cwd=output,
                                                          stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise
            (output / f"{label}.stdout").write_bytes(stdout)
            (output / f"{label}.stderr").write_bytes(stderr)
            passed = (process.returncode == 0 and stdout == ("native-ssh-ok:" + nonce + "\n").encode()) if label == "correct-host-key" \
                else process.returncode != 0 and b"HOST IDENTIFICATION HAS CHANGED" in stderr
            cases.append({"name": label, "raw_exit": process.returncode, "pid": process.pid, "passed": passed,
                          "stdout_sha256": sha256(output / f"{label}.stdout"),
                          "stderr_sha256": sha256(output / f"{label}.stderr")})
    finally:
        server.close()
        await server.wait_closed()
    return {"cases": cases, "events": events, "port": port,
            "passed": len(cases) == 2 and all(row["passed"] for row in cases) and
                      any(row["event"] == "authenticated_command" for row in events)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--test-driver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--bash", type=Path, help="Optional actual native MSYS parent from the same extraction")
    args = parser.parse_args()
    client, driver, output = args.client.resolve(), args.test_driver.resolve(), args.output.resolve()
    if output.exists() or pe_identity(client)["machine"] != "0xAA64":
        raise ArtifactError("A fresh SSH test root and actual ARM64 client are required")
    bash = args.bash.resolve() if args.bash else None
    if bash is not None and pe_identity(bash)["machine"] != "0xAA64":
        raise ArtifactError("SSH parent must be an actual native ARM64 Bash")
    output.mkdir(parents=True)
    (output / "empty_config").write_bytes(b"")
    os.environ["MVP_POWERSHELL"] = str(args.pwsh)
    report = {"schema": 1, "passed": False, "client_sha256": sha256(client), "client_path": str(client),
              "parent": {"path": str(bash), "sha256": sha256(bash)} if bash else "native Windows Python",
              "scope": "Real encrypted loopback SSH handshake/public-key authentication and strict host-key rejection; portable fixture only, no installed service or real credentials"}
    try:
        report.update(asyncio.run(exercise(client, driver, output, bash)))
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"passed": report["passed"], "cases": report.get("cases", [])}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
