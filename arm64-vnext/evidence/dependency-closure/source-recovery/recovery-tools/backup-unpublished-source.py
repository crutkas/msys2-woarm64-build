"""Archive raw current source and local-only source blobs from this session's checkpoints."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


SESSION = "accd408a-aaf0-40b4-bc67-83995f29feec"
ROOT = Path.cwd()
OUTPUT = ROOT / "arm64-vnext/evidence/dependency-closure/source-recovery"
SESSION_FILES = Path(r"C:\Users\crutkasLocal\.copilot\session-state") / SESSION / "files"


def git(*args, data=None, env=None):
    return subprocess.run(["git", "-c", "core.longpaths=true", "-c", "core.autocrlf=false",
                           *args], input=data, capture_output=True, env=env, check=True).stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def entries(tree):
    result = {}
    for line in git("ls-tree", "-rz", tree).split(b"\0"):
        if not line:
            continue
        meta, name = line.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = name.decode("utf-8")
        if kind == "blob" and not name.startswith("arm64-vnext/evidence/"):
            result[name] = (mode, oid)
    return result


def index_environment(name):
    path = SESSION_FILES / name
    if path.exists():
        raise RuntimeError("Temporary recovery index must be new")
    return {**os.environ, "GIT_INDEX_FILE": str(path)}, path


def current():
    base = git("rev-parse", "HEAD").decode().strip()
    patch_path = OUTPUT / "current-working-tree.patch"
    if patch_path.exists():
        raise RuntimeError("Existing source recovery patch cannot be replaced")
    original = entries(base)
    names = set(git("ls-files", "-z").decode().split("\0"))
    names |= set(git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0"))
    names = sorted(name for name in names if name and not name.startswith("arm64-vnext/evidence/"))
    files, changes = [], []
    env, index = index_environment("source-current.index")
    git("read-tree", base, env=env)
    try:
        for name in names:
            path = ROOT.joinpath(*name.split("/"))
            previous = original.get(name)
            if not path.exists():
                if previous:
                    changes.append(f"0 {'0' * 40}\t{name}\0".encode())
                    files.append({"path": name, "state": "deleted", "base_blob": previous[1]})
                continue
            data = path.read_bytes()
            if data.startswith(b"MZ") or b"\0" in data or len(data) >= 5 * 1024 * 1024:
                raise RuntimeError(f"Non-source or large source needs explicit handling: {name}")
            oid = git("hash-object", "-w", "--no-filters", "--stdin", data=data).decode().strip()
            mode = previous[0] if previous else "100644"
            if previous == (mode, oid):
                continue
            changes.append(f"{mode} {oid}\t{name}\0".encode())
            files.append({"path": name, "state": "modified" if previous else "untracked",
                          "original_path": str(path), "sha256": sha(data), "bytes": len(data),
                          "mode": mode, "blob": oid, "base_blob": previous[1] if previous else None})
        git("update-index", "-z", "--index-info", data=b"".join(changes), env=env)
        patch = git("diff", "--cached", "--binary", "--full-index", "--no-ext-diff",
                    "--no-textconv", "--no-renames", base, "--", env=env)
        patch_path.write_bytes(patch)
        verification, verification_path = index_environment("source-verify.index")
        try:
            git("read-tree", base, env=verification)
            git("apply", "--cached", "--binary", "--whitespace=nowarn", str(patch_path), env=verification)
            tree = git("write-tree", env=verification).decode().strip()
            restored = entries(tree)
            for item in files:
                if item["state"] == "deleted":
                    if item["path"] in restored:
                        raise RuntimeError("Deleted file unexpectedly restored")
                else:
                    blob = restored[item["path"]][1]
                    if sha(git("cat-file", "blob", blob)) != item["sha256"]:
                        raise RuntimeError(f"Recovery patch does not recover exact bytes: {item['path']}")
        finally:
            verification_path.unlink(missing_ok=True)
    finally:
        index.unlink(missing_ok=True)
    session = []
    directory = OUTPUT / "session-source"
    directory.mkdir()
    for path in sorted(SESSION_FILES.iterdir()):
        if path.is_file() and path.suffix in (".py", ".ps1", ".sh", ".patch") and path.name != Path(__file__).name:
            data = path.read_bytes()
            (directory / path.name).write_bytes(data)
            session.append({"path": "session-source/" + path.name, "original_path": str(path),
                            "sha256": sha(data), "bytes": len(data),
                            "state": "Historical session script; qualification only where bound by sealed receipts"})
    inventory = {"schema": 1, "base_commit": base, "branch": git("branch", "--show-current").decode().strip(),
                 "state": "recovery-only source snapshot; no blanket correctness or fresh build claim",
                 "patch": {"path": patch_path.name, "sha256": sha(patch), "bytes": len(patch)},
                 "patch_replay_exact_blob_verification": True, "files": files, "session_source": session,
                 "staged_diff_bytes": len(git("diff", "--cached", "--binary")),
                 "local_only_head_commits": git("rev-list", "HEAD", "--not", "--remotes").decode().splitlines(),
                 "stash_entries": git("stash", "list", "--format=%gd %H %gs").decode().splitlines(),
                 "worktree_head_reflog": git("reflog", "show", "HEAD", "--format=%H %gs").decode().splitlines()}
    json_write(OUTPUT / "source-inventory.json", inventory)
    print(json.dumps({"current_source_files": len(files), "session_scripts": len(session), "patch": inventory["patch"]}))


def checkpoints():
    inventory = json.loads((OUTPUT / "source-inventory.json").read_text())
    refs = git("for-each-ref", "--format=%(refname) %(objectname)", f"refs/copilot/checkpoints/{SESSION}").decode().splitlines()
    remote_objects = {line.split(" ", 1)[0] for line in git("rev-list", "--objects", "--remotes").decode().splitlines()}
    current_objects = {item["blob"]: item["path"] for item in inventory["files"] if "blob" in item}
    seen, snapshots = {}, []
    directory = OUTPUT / "checkpoint-source"
    directory.mkdir()
    for line in refs:
        ref, commit = line.split(" ", 1)
        local = []
        for name, (mode, oid) in entries(commit).items():
            if oid in remote_objects:
                continue
            if oid in current_objects:
                local.append({"path": name, "mode": mode, "blob": oid,
                              "recovery": "current-working-tree.patch", "current_path": current_objects[oid]})
                continue
            if oid not in seen:
                data = git("cat-file", "blob", oid)
                if len(data) >= 5 * 1024 * 1024 or data.startswith(b"MZ") or b"\0" in data:
                    raise RuntimeError(f"Checkpoint includes non-source requiring explicit handling: {ref} {name}")
                target = directory / (oid + ".source")
                target.write_bytes(data)
                seen[oid] = {"path": "checkpoint-source/" + target.name, "sha256": sha(data),
                             "bytes": len(data), "state": "UNQUALIFIED intermediate checkpoint source; preserve only, not a recommended fix"}
            local.append({"path": name, "mode": mode, "blob": oid, "recovery": seen[oid]["path"],
                          "sha256": seen[oid]["sha256"]})
        snapshots.append({"ref": ref, "commit": commit, "local_only_source": local})
    report = {"schema": 1, "session": SESSION, "scope": "Only this session checkpoint refs; other sessions and arbitrary dangling objects not enumerated",
              "remote_tracking_refs_at_capture": git("for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes").decode().splitlines(),
              "checkpoint_refs": len(refs), "additional_unique_source_blobs": len(seen),
              "blobs": seen, "snapshots": snapshots}
    json_write(OUTPUT / "checkpoint-recovery.json", report)
    print(json.dumps({"checkpoint_refs": len(refs), "additional_unique_source_blobs": len(seen),
                      "additional_bytes": sum(item["bytes"] for item in seen.values())}))


parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("current", "checkpoints"))
args = parser.parse_args()
{"current": current, "checkpoints": checkpoints}[args.phase]()
