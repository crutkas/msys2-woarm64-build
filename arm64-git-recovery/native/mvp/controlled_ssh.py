"""Real loopback SSH public-key/host-key verification with private ephemeral test credentials."""

import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys

from artifact import ArtifactError, pe_identity, sha256, write_json


async def exercise(client, driver, output, bash=None, git=None):
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
    if git is not None:
        environment["PATH"] = str(git.parent) + os.pathsep + environment["PATH"]
        environment.update({"GIT_CONFIG_GLOBAL": str(output / "empty_config"), "GIT_CONFIG_NOSYSTEM": "1",
                            "MSYSTEM": "MINGWARM64", "MSYS": "winsymlinks:sys"})
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

    async def run_git(label, arguments, extra_environment=None):
        command = [str(git), *map(str, arguments)]
        if bash is not None:
            command = [str(bash), "--noprofile", "--norc", "-c", 'exec "$@"', "native-git-ssh-fixture", *command]
        process = await asyncio.create_subprocess_exec(
            *command, env={**environment, **(extra_environment or {})}, cwd=output,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 60)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        (output / f"{label}.stdout").write_bytes(stdout)
        (output / f"{label}.stderr").write_bytes(stderr)
        return process.returncode, stdout, stderr

    async def require_git(label, arguments):
        code, stdout, stderr = await run_git(label, arguments)
        if code:
            raise ArtifactError(f"Private Git SSH fixture preparation failed ({label}): {stderr.decode(errors='replace')}")
        return stdout.strip()

    source_repo, served_repo = output / "source repo", output / "served.git"
    if git is not None:
        await require_git("source-init", ["init", "--initial-branch=main", source_repo])
        await require_git("source-user", ["-C", source_repo, "config", "user.name", "Native SSH fixture"])
        await require_git("source-email", ["-C", source_repo, "config", "user.email", "native-ssh@example.invalid"])
        (source_repo / "payload.txt").write_text("native Git over encrypted SSH\n", encoding="utf-8")
        (source_repo / "binary.bin").write_bytes(secrets.token_bytes(131072))
        binary_sha256 = sha256(source_repo / "binary.bin")
        await require_git("source-add", ["-C", source_repo, "add", "payload.txt", "binary.bin"])
        await require_git("source-commit", ["-C", source_repo, "commit", "-m", "isolated native SSH fixture"])
        first_head = await require_git("source-head", ["-C", source_repo, "rev-parse", "HEAD"])
        await require_git("source-bare", ["clone", "--bare", source_repo, served_repo])

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
        if git is not None and process.command == "git-upload-pack '/mvp.git'":
            events.append({"event": "authenticated_git_upload_pack", "command": process.command,
                           "send_cipher": process.get_extra_info("send_cipher"),
                           "recv_cipher": process.get_extra_info("recv_cipher"),
                           "git_protocol": process.env.get("GIT_PROTOCOL")})
            server_environment = dict(environment)
            if "GIT_PROTOCOL" in process.env:
                server_environment["GIT_PROTOCOL"] = process.env["GIT_PROTOCOL"]
            child = await asyncio.create_subprocess_exec(
                str(git), "upload-pack", str(served_repo), env=server_environment, cwd=output,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            async def copy_input():
                while data := await process.stdin.read(65536):
                    child.stdin.write(data)
                    await child.stdin.drain()
                child.stdin.close()

            async def copy_output(reader, writer):
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()

            inbound = asyncio.create_task(copy_input())
            outbound = [asyncio.create_task(copy_output(child.stdout, process.stdout)),
                        asyncio.create_task(copy_output(child.stderr, process.stderr))]
            try:
                code = await asyncio.wait_for(child.wait(), 60)
                await asyncio.gather(*outbound)
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
                inbound.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await inbound
                for task in outbound:
                    if not task.done():
                        task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            process.exit(code)
            return
        if process.command != "prove " + nonce:
            events.append({"event": "rejected_command", "command": process.command})
            process.exit(91)
            return
        events.append({"event": "authenticated_command", "command": process.command,
                       "send_cipher": process.get_extra_info("send_cipher"),
                       "recv_cipher": process.get_extra_info("recv_cipher")})
        response = "native-ssh-ok:" + nonce + "\n"
        process.stdout.write(response.encode() if git is not None else response)
        process.exit(0)

    server = await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[server_key],
                                          process_factory=handle, encoding=None if git is not None else "utf-8",
                                          config=[])
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
        if git is not None:
            def transport(hosts):
                arguments = [client.as_posix(), "-F", (output / "empty_config").as_posix(),
                             "-i", key_file.as_posix(), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                             "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={hosts.as_posix()}",
                             "-o", f"GlobalKnownHostsFile={(output / 'empty_config').as_posix()}",
                             "-o", "ConnectTimeout=10", "-o", "ProxyCommand=none"]
                return {"GIT_SSH_COMMAND": shlex.join(arguments), "GIT_SSH_VARIANT": "ssh"}

            remote = f"ssh://mvp-fixture@127.0.0.1:{port}/mvp.git"
            clone = output / "encrypted clone"
            code, _, _ = await run_git("git-clone", ["clone", remote, clone], transport(known))
            if code:
                raise ArtifactError("Real Git clone over the native SSH client failed")
            clone_head = await require_git("clone-head", ["-C", clone, "rev-parse", "HEAD"])
            await require_git("clone-fsck", ["-C", clone, "fsck", "--full"])
            clone_binary_sha256 = sha256(clone / "binary.bin")
            cases.append({"name": "git-encrypted-clone", "raw_exit": code,
                          "passed": clone_head == first_head and clone_binary_sha256 == binary_sha256,
                          "expected_head": first_head.decode("ascii"), "observed_head": clone_head.decode("ascii"),
                          "binary_bytes": 131072, "expected_binary_sha256": binary_sha256,
                          "observed_binary_sha256": clone_binary_sha256})
            (source_repo / "payload.txt").write_text("second native SSH commit\n", encoding="utf-8")
            await require_git("source-second-commit", ["-C", source_repo, "commit", "-am", "isolated fetch update"])
            second_head = await require_git("source-second-head", ["-C", source_repo, "rev-parse", "HEAD"])
            await require_git("source-push", ["-C", source_repo, "push", served_repo, "HEAD:refs/heads/main"])
            code, _, _ = await run_git("git-fetch", ["-C", clone, "fetch", "origin"], transport(known))
            if code:
                raise ArtifactError("Real Git fetch over the native SSH client failed")
            fetched = await require_git("fetch-head", ["-C", clone, "rev-parse", "origin/main"])
            await require_git("fetch-fsck", ["-C", clone, "fsck", "--full"])
            cases.append({"name": "git-encrypted-fetch", "raw_exit": code, "passed": fetched == second_head != first_head,
                          "expected_head": second_head.decode("ascii"), "observed_head": fetched.decode("ascii")})
            code, _, stderr = await run_git("git-wrong-host-key", ["clone", remote, output / "rejected clone"],
                                           transport(wrong))
            cases.append({"name": "git-wrong-host-key", "raw_exit": code,
                          "passed": code != 0 and b"HOST IDENTIFICATION HAS CHANGED" in stderr})
    finally:
        server.close()
        await server.wait_closed()
        write_json(output / "server-events.json", events)
        write_json(output / "cases-observed.json", cases)
    return {"cases": cases, "events": events, "port": port,
            "passed": len(cases) == (5 if git is not None else 2) and all(row["passed"] for row in cases) and
                      any(row["event"] == "authenticated_command" for row in events)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--test-driver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--bash", type=Path, help="Optional actual native MSYS parent from the same extraction")
    parser.add_argument("--git", type=Path, help="Also clone and fetch through real encrypted SSH using this native Git")
    args = parser.parse_args()
    client, driver, output = args.client.resolve(), args.test_driver.resolve(), args.output.resolve()
    if output.exists() or pe_identity(client)["machine"] != "0xAA64":
        raise ArtifactError("A fresh SSH test root and actual ARM64 client are required")
    bash = args.bash.resolve() if args.bash else None
    if bash is not None and pe_identity(bash)["machine"] != "0xAA64":
        raise ArtifactError("SSH parent must be an actual native ARM64 Bash")
    git = args.git.resolve() if args.git else None
    if git is not None and pe_identity(git)["machine"] != "0xAA64":
        raise ArtifactError("The SSH transport Git must be an actual native ARM64 image")
    output.mkdir(parents=True)
    (output / "empty_config").write_bytes(b"")
    os.environ["MVP_POWERSHELL"] = str(args.pwsh)
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(output)
    report = {"schema": 1, "passed": False, "client_sha256": sha256(client), "client_path": str(client),
              "parent": {"path": str(bash), "sha256": sha256(bash)} if bash else "native Windows Python",
              "scope": "Real encrypted loopback SSH handshake/public-key authentication and strict host-key rejection; portable fixture only, no installed service or real credentials"}
    if git is not None:
        report["git"] = {"path": str(git), "sha256": sha256(git)}
        report["scope"] += "; actual Git upload-pack, encrypted clone/fetch, exact commits and fsck"
    try:
        report.update(asyncio.run(exercise(client, driver, output, bash, git)))
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"passed": report["passed"], "cases": report.get("cases", [])}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
