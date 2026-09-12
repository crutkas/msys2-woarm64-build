"""Regenerate a fresh libiconv source using approved real host tools and pinned macros."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from bash_chain_inputs import ROOT, HERE, PREPARED, fresh
from readline_chain_inputs import sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

nls = importlib.import_module("build-bash-nls")
host_copy = importlib.import_module("copy-bash-generators")
HOST = ROOT / "host-bootstrap-02/msys64"
HOST_MANIFEST = ROOT / "host-bootstrap-02/host-generators-02.json"
GENERATOR = ROOT / "host-bootstrap-02/msys-libtool"
GENERATOR_MANIFEST = ROOT / "host-bootstrap-02/msys-libtool.copy.json"


def main():
    output = ROOT / "libiconv-regenerated-02"
    source = ROOT / "sources/libiconv/source"
    manifest = source.with_name("source.prepare.json")
    fresh(output)
    print(json.dumps({"pid": os.getpid(), "creation_filetime": nls.terminal.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    sealed(manifest, PREPARED["libiconv"][1])
    verify_tree(source, manifest)
    verify_tree(HOST, HOST_MANIFEST)
    host = json.loads(HOST_MANIFEST.read_text())
    if (host["status"] != "owned-host-augmented-with-genuine-verified-automake"
            or host["signature_policy"] != "Required" or not host["verify"]["passed"] or not host["install"]["passed"]):
        raise ContractError("Qualified real host generator augmentation is required")
    sealed(GENERATOR_MANIFEST, host_copy.LIBTOOL_SHA)
    verify_tree(GENERATOR, GENERATOR_MANIFEST)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    shutil.copytree(source, output / "source", symlinks=True)
    before = inventory(output / "source")
    write_json(output / "source-before.json", {"files": before})
    script = HERE / "regenerate-bash-iconv.sh"
    patch = HERE / "patches/libiconv-1.19-nested-macro-path.patch"
    for file in (script, patch, HERE / "regenerate-bash-iconv.py"):
        shutil.copyfile(file, output / "recipes" / file.name)
    command = [HOST / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), output, GENERATOR]
    env = nls.environment(output, 1)
    env["PATH"] = str(HOST / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    report = {"schema": 1, "status": "launched", "pid": os.getpid(),
              "creation_filetime": nls.terminal.current_birth(), "command": list(map(str, command)),
              "source_preparation_sha256": PREPARED["libiconv"][1],
              "host_manifest_sha256": digest(HOST_MANIFEST), "generator_manifest_sha256": host_copy.LIBTOOL_SHA,
              "patch_sha256": digest(patch), "jobs": 1, "minimum_free_gib": require_memory(),
              "scope": "Actual nested/top-level pinned m4/autoreconf generation only; no target compiler/runtime build or feature removal"}
    write_json(output / "launch.json", report)
    try:
        with nls.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            report["process"] = nls.run_observed(command, cwd=output, env=env,
                                                 log_path=output / "observed.log", result_path=output / "native-job.json",
                                                 relay_records=output / "native-exits", timeout=1800,
                                                 driver_prefix=nls.terminal.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Actual source regeneration failed")
        for relative in ("configure", "libcharset/configure"):
            path = output / "source" / relative
            nls.validate_generated_configure(path.read_text(), str(path))
        for relative in ("m4/libtool.m4", "libcharset/m4/libtool.m4"):
            if digest(output / "source" / relative) != digest(GENERATOR / "generator-data/m4/libtool.m4"):
                raise ContractError("MSYS-aware libtool macro identity was not retained")
        after = inventory(output / "source")
        report["changed_files"] = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        original = json.loads(manifest.read_text())
        write_json(output / "source.prepare.json", {
            **{key: value for key, value in original.items() if key != "files"},
            "files": after, "source_generation_delta": {
                "base_manifest_sha256": PREPARED["libiconv"][1], "host_manifest_sha256": digest(HOST_MANIFEST),
                "libtool_manifest_sha256": host_copy.LIBTOOL_SHA, "patch_sha256": digest(patch),
                "process": report["process"], "changed_files": report["changed_files"],
                "unexpanded_relocatable_macro": False,
            },
        })
        report.update(status="libiconv-source-actually-regenerated-with-complete-macro-closure",
                      preparation_sha256=digest(output / "source.prepare.json"))
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(source, manifest)
        verify_tree(HOST, HOST_MANIFEST)
        verify_tree(GENERATOR, GENERATOR_MANIFEST)
        verify_tree(host_copy.SOURCE, host_copy.MANIFEST)
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "manifest_sha256": report["preparation_sha256"]}), flush=True)


if __name__ == "__main__":
    main()
