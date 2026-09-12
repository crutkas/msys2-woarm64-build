import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


spec = importlib.util.spec_from_file_location("native_nls", Path(__file__).with_name("qualify-official-nls.py"))
nls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nls)
root = Path(r"C:\ap11-accd-pcre2-mvp01")
prefix = Path(r"C:\ap11-accd-gettext01\projection-moved-c\mingwarm64")
fixture = root / "grep-fixture.txt"
report = {"scope": "Real current32c4 Git grep with selected63ca unversioned PCRE2, no Git rebuild",
          "git_sha256": nls.digest(prefix / "bin/git.exe"),
          "pcre2_sha256": nls.digest(prefix / "bin/libpcre2-8.dll"), "fixture_sha256": nls.digest(fixture),
          "runs": [], "status": "incomplete"}
assert report["pcre2_sha256"] == "631cd65ed9d1a33938e6cdb63dd3c2e866d1d9b2dc81c4cdfd813ccbf50c1bff"
env = {
    "SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
    "PATH": str(prefix / "bin") + ";" + os.environ["SystemRoot"] + r"\System32",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD", "HOME": str(root), "USERPROFILE": str(root),
    "TEMP": str(root), "TMP": str(root), "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": str(root / "empty.gitconfig"), "GIT_TERMINAL_PROMPT": "0",
    "GIT_EXEC_PATH": str(prefix / "libexec/git-core"), "LC_ALL": "C", "LANG": "C",
}
(root / "empty.gitconfig").touch(exist_ok=True)
report["environment"] = env
try:
    for name, pattern, expected_exit, expected in (
        ("lookbehind", r"(?<=native-)\d+", 0, b"native-123"),
        ("unicode-property", r"(*UTF)(*UCP)caf\p{L}", 0, "caf\u00e9".encode()),
        ("alternation", r"native-(?:12[3]|999)", 0, b"native-123"),
        ("nonmatch", r"pattern-that-is-not-present", 1, b""),
        ("invalid-pattern", "(", 128, None),
    ):
        command = [str(prefix / "bin/git.exe"), "-c", "core.pager=cat", "grep",
                   "--no-index", "-n", "-P", "-e", pattern, "--", fixture.name]
        process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        snapshot = []
        while process.poll() is None:
            try:
                snapshot = nls.modules(process.pid)
            except OSError as error:
                if error.winerror not in (24, 299):
                    raise
            if any(item["name"].lower() == "libpcre2-8.dll" for item in snapshot):
                break
            time.sleep(0.001)
        stdout, stderr = process.communicate(timeout=30)
        out = root / "evidence" / ("git-grep-02-" + name + ".stdout")
        err = root / "evidence" / ("git-grep-02-" + name + ".stderr")
        out.write_bytes(stdout)
        err.write_bytes(stderr)
        matched = (expected in stdout) if expected else (
            not stdout if expected == b"" else b"missing closing parenthesis" in stderr)
        report["runs"].append({"name": name, "command": command, "pid": process.pid, "raw_exit": process.returncode,
                               "expected_exit": expected_exit, "passed": process.returncode == expected_exit and matched,
                               "stdout": str(out), "stderr": str(err), "modules": snapshot})
        for item in snapshot:
            if item["name"].lower().startswith("msys-"):
                raise RuntimeError("Unexpected MSYS runtime in native Git grep")
            if item["name"].lower() == "libpcre2-8.dll" and item["sha256"] != report["pcre2_sha256"]:
                raise RuntimeError("Git grep loaded a different PCRE2")
    report["status"] = "passed" if all(item["passed"] for item in report["runs"]) else "failed"
finally:
    (root / "evidence/git-grep-02.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "runs": [{key: value for key, value in item.items()
                   if key != "modules"} for item in report["runs"]]}))
