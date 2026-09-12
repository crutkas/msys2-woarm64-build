import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


root = Path(r"C:\ap11-accd-gettext01")
projection = root / "projection-moved-c"
intl = projection / "mingwarm64/bin/libintl-8.dll"
official = root / "revoked-baseline-diagnostic-only/official-libintl-preserved.dll"
baseline = root / "revoked-baseline-diagnostic-only/mingwarm64/bin/libintl-8.dll"
assert digest(official) == "31db0d0e7780cf28dca1309a894cb775b2ab130c4ba777c546a206970ca47320"
assert digest(baseline) == "236ddf16e7f03e9fb720b747861d124423c042bc92a9ec62e58e096d820dea40"
assert digest(intl) == digest(official)
original = {str(path.relative_to(projection)): digest(path) for path in projection.rglob("*") if path.is_file()}
output = root / "clone-baseline-comparison"
output.mkdir()
env = {
    "SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
    "PATH": str(projection / "mingwarm64/bin") + ";" + os.environ["SystemRoot"] + r"\System32",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD", "HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
    "TEMP": str(root / "tmp"), "TMP": str(root / "tmp"), "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(root / "evidence/empty.gitconfig"),
    "GIT_TERMINAL_PROMPT": "0", "GIT_EXEC_PATH": str(projection / "mingwarm64/libexec/git-core"),
}
command = [str(projection / "mingwarm64/bin/git.exe"), "clone", "--bare",
           str(root / "consumer-behaviors-03/context/repo"), str(output / "destination")]
report = {"scope": "Intake-authorized causal diagnostic only; revoked DLL is never admissible or distributed",
          "non_gettext_files_before": original, "command": command, "environment": env, "runs": []}
try:
    for name, library in (("official", official), ("revoked-baseline", baseline), ("official-restored", official)):
        shutil.copyfile(library, intl)
        assert digest(intl) == digest(library)
        current = {str(path.relative_to(projection)): digest(path) for path in projection.rglob("*") if path.is_file()}
        changed = [path for path in original if current.get(path) != original[path]]
        if set(current) != set(original) or any(path.replace("\\", "/") != "mingwarm64/bin/libintl-8.dll" for path in changed):
            raise RuntimeError("Non-gettext input changed in A/B comparison")
        result = subprocess.run(command, env=env, cwd=root, capture_output=True, timeout=30)
        (output / (name + ".stdout")).write_bytes(result.stdout)
        (output / (name + ".stderr")).write_bytes(result.stderr)
        report["runs"].append({"name": name, "libintl_sha256": digest(intl), "raw_exit": result.returncode,
                               "stdout": str(output / (name + ".stdout")), "stderr": str(output / (name + ".stderr")),
                               "only_libintl_changed": True, "classification": "unexpected-failure" if result.returncode else "zero-exit"})
        if (output / "destination").exists():
            (output / "destination").rename(output / (name + "-destination-preserved"))
    shutil.copyfile(official, intl)
    no_local = command.copy()
    no_local.insert(3, "--no-local")
    result = subprocess.run(no_local, env=env, cwd=root, capture_output=True, timeout=30)
    (output / "official-no-local.stdout").write_bytes(result.stdout)
    (output / "official-no-local.stderr").write_bytes(result.stderr)
    report["runs"].append({"name": "official-no-local-distinct-path", "command": no_local,
                           "libintl_sha256": digest(intl), "raw_exit": result.returncode,
                           "scope": "Different transport path, not a fix or waiver for bare-local clone"})
finally:
    shutil.copyfile(official, intl)
    report["official_restored"] = digest(intl) == digest(official)
    final = {str(path.relative_to(projection)): digest(path) for path in projection.rglob("*") if path.is_file()}
    report["all_projection_bytes_restored"] = final == original
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"runs": report["runs"], "restored": report["all_projection_bytes_restored"]}))
