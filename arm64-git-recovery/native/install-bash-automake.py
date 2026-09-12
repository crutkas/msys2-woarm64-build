"""Install exactly resolved, independently signature-checked Automake into the owned host copy."""

import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from bash_chain_inputs import ROOT, fresh
from readline_chain_inputs import sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, write_json

nls = importlib.import_module("build-bash-nls")
host_input = importlib.import_module("copy-bash-generators")
BASE = ROOT / "host-bootstrap-02"
HOST = BASE / "msys64"
FILE = "automake1.18-1.18.1-1-any.pkg.tar.zst"
PACKAGE_SHA = "c045d9eddf900dbacae06d9e0e19e250cc32d849def7d06b833253f85e3fc941"
URL = "https://mirror.msys2.org/msys/x86_64/" + FILE
KEYRING_SHA = "1257d4ccc536c53333445a618039af4c3ea3f56b96601de9af89151ea529c19a"


def main():
    output = BASE / "automake-install-03"
    fresh(output)
    print(json.dumps({"pid": os.getpid(), "creation_filetime": nls.terminal.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    verify_tree(HOST, BASE / "msys64.copy.json")
    before = inventory(HOST)
    config = (HOST / "etc/pacman.conf").read_text()
    if not re.search(r"(?m)^SigLevel\s*=\s*Required\s*$", config):
        raise ContractError("Required pacman package signature policy was not retained")
    keyring = HOST / "usr/share/pacman/keyrings/msys2.gpg"
    sealed(keyring, KEYRING_SHA)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "packages", "public-gpg-home"):
        (output / name).mkdir()
    write_json(output / "before.json", {"files": before, "directories": directory_names(HOST)})
    package = output / "packages" / FILE
    signature = package.with_name(package.name + ".sig")
    previous = BASE / "automake-install-01"
    previous_report = json.loads((previous / "result.json").read_text())
    for path, expected in ((package, PACKAGE_SHA), (signature, previous_report["signature_sha256"])):
        cached = previous / "packages" / path.name
        sealed(cached, expected)
        shutil.copyfile(cached, path)
        sealed(path, expected)
    sealed(package, PACKAGE_SHA)
    env = nls.environment(output, 1)
    env["PATH"] = str(HOST / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    report = {"schema": 1, "status": "verifying", "package": FILE, "package_sha256": PACKAGE_SHA,
              "signature_sha256": digest(signature), "keyring_sha256": KEYRING_SHA,
              "source_host_receipt_sha256": digest(BASE / "msys64.copy.json"),
              "signature_policy": "Required", "target_package_or_library_claim": False}
    commands = [
        ("dearmor", [HOST / "usr/bin/bash.exe", "--noprofile", "--norc", "-c",
                     'exec /usr/bin/gpg.exe --no-options --no-autostart --homedir "$(cygpath -u "$1")" --batch --dearmor --output "$(cygpath -u "$2")" /usr/share/pacman/keyrings/msys2.gpg',
                     "dearmor", output / "public-gpg-home", output / "public-keyring.gpg"]),
        ("verify", [HOST / "usr/bin/bash.exe", "--noprofile", "--norc", "-c",
                    'exec /usr/bin/gpgv.exe --status-fd=1 --keyring "$(cygpath -u "$1")" "$(cygpath -u "$2")" "$(cygpath -u "$3")"',
                    "verify", output / "public-keyring.gpg", signature, package]),
        ("install", [HOST / "usr/bin/bash.exe", "--noprofile", "--norc", "-c",
                     'exec /usr/bin/pacman.exe -S --needed --noconfirm --cachedir "$(cygpath -u "$1")" automake1.18',
                     "install", output / "packages"]),
        ("versions", [HOST / "usr/bin/bash.exe", "--noprofile", "--norc", "-c",
                      "/usr/bin/pacman.exe -Q automake1.18 && /usr/bin/aclocal-1.18 --version && /usr/bin/automake-1.18 --version"]),
    ]
    report["commands"] = [{"name": name, "argv": list(map(str, command))} for name, command in commands]
    write_json(output / "launch.json", report)
    try:
        with nls.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            for name, command in commands:
                observed = nls.run_observed(command, cwd=output, env=env, log_path=output / (name + ".log"),
                                            result_path=output / (name + ".native-job.json"),
                                            relay_records=output / "native-exits", timeout=600,
                                            driver_prefix=nls.terminal.OBSERVER)
                report[name] = observed
                if not observed["passed"]:
                    raise ContractError(f"Actual Automake {name} failed")
                if name == "verify":
                    valid = re.findall(r"(?m)^\[GNUPG:\] VALIDSIG ([0-9A-F]+) ", (output / "verify.log").read_text())
                    if len(valid) != 1:
                        raise ContractError("Expected one independent valid package signature")
                    report["signer"] = valid[0]
                    report["dearmored_public_keyring_sha256"] = digest(output / "public-keyring.gpg")
                if name == "versions" and not (output / "versions.log").read_text().startswith("automake1.18 1.18.1-1\n"):
                    raise ContractError("Installed Automake package version differs from the resolved pin")
        sealed(package, PACKAGE_SHA)
        after = inventory(HOST)
        changed = sorted(name for name in before if before[name] != after.get(name))
        if set(changed) - {"usr/share/info/dir", "var/log/pacman.log"}:
            raise ContractError(f"Unexpected retained host-file mutation: {changed}")
        report.update(status="owned-host-augmented-with-genuine-verified-automake",
                      changed_base_files=changed, added_files=len(after.keys() - before.keys()),
                      files=after, directories=directory_names(HOST),
                      prefix=str(HOST), parent_manifest_sha256=host_input.MANIFEST_SHA)
        verify_tree(host_input.SOURCE, host_input.MANIFEST)
        sealed(host_input.MANIFEST, host_input.MANIFEST_SHA)
        write_json(BASE / "host-generators-02.json", report)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "files": len(report["files"]),
                      "manifest_sha256": digest(BASE / "host-generators-02.json")}), flush=True)


if __name__ == "__main__":
    main()
