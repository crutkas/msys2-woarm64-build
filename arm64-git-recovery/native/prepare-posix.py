"""Apply the pinned POSIX package patch stacks without compiling or using makepkg."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

from sources import ContractError, digest, inventory, verify_tree


PACKAGES = {
    "make": ("make", "msys-upstream-recipes", "make", [
        "0001-fixes-building-with-gcc-15.patch"]),
    "bash": ("bash", "msys-recipes", "bash", [
        "0001-bash-4.4-cygwin.patch", "0002-bash-4.3-msysize.patch",
        "0005-bash-4.3-msys2-fix-lineendings.patch", "0006-bash-4.3-add-pwd-W-option.patch",
        "0007-fix-static-build.patch"]),
    "coreutils": ("coreutils", "msys-upstream-recipes", "coreutils", [
        "001-coreutils-8.30.patch", "002-coreutils-8.32-enable-stdbuf.patch",
        "003-coreutils-8.32-fix-test-cases.patch", "004-msystem-osname-cygwin.patch"]),
    "perl": ("perl-gfw", "msys-recipes", "perl", [
        "0002-perl.cygwin-hints.patch", "0003-perl.cygwin-Configure-libsearch.patch",
        "0004-perl.cygwin-Configure-libpth.patch", "0005-perl.cygwin-Win32.patch",
        "0006-perl-5.36.0-msys2.patch",
        "0007-Skip-a-regeneration-check-in-unrelated-git-repositor.patch"])
}

# These pinned upstream patches predate adjacent declarations in their pinned
# releases. Keep GNU patch's original bounded context tolerance only here.
REVIEWED_FUZZ = {
    ("bash", "0001-bash-4.4-cygwin.patch"): 2,
    ("coreutils", "001-coreutils-8.30.patch"): 2,
    ("perl", "0006-perl-5.36.0-msys2.patch"): 2
}


def prepare(package, sources, cache, output, regenerate=False):
    if regenerate and package not in ("bash", "coreutils"):
        raise ContractError("--regenerate is supported only for Bash and coreutils")
    source_id, recipe_id, recipe_directory, local_patches = PACKAGES[package]
    sources, cache, output = Path(sources), Path(cache), Path(output)
    report_path = output.with_name(output.name + ".prepare.json")
    if output.exists() or report_path.exists():
        raise ContractError("Preparation requires new output/report paths")
    if not shutil.which("patch"):
        raise ContractError("Missing host patch command; ask the bootstrap owner, do not install globally")
    for source in (source_id, recipe_id):
        verify_tree(sources / source, sources / f"{source}.inventory.json")
    recipe = sources / recipe_id / recipe_directory
    text = (recipe / "PKGBUILD").read_text(encoding="utf-8")
    checksum_arrays = re.findall(r"(?m)^sha256sums=\((.*?)\)", text, re.DOTALL)
    if len(checksum_arrays) != 1:
        raise ContractError("Expected exactly one literal sha256sums array")
    checksums = re.findall(r"'([0-9a-f]{64}|SKIP)'", checksum_arrays[0])
    patches = []
    if package == "bash":
        # This layout is pinned to the recovered 5.3.015 recipe; changes fail closed.
        if not re.search(r"(?m)^_patchlevel=015\b", text) or len(checksums) != 37:
            raise ContractError("Bash release patch checksum layout changed")
        cache.mkdir(parents=True, exist_ok=True)
        for number, expected in enumerate(checksums[7::2], 1):
            name = f"bash53-{number:03d}"
            url = f"https://ftp.gnu.org/gnu/bash/bash-5.3-patches/{name}"
            path = cache / name
            if not path.exists():
                with path.open("xb") as dest:
                    with urllib.request.urlopen(url, timeout=120) as response:
                        shutil.copyfileobj(response, dest)
            if path.is_symlink() or digest(path) != expected:
                raise ContractError(f"GNU patch checksum mismatch: {path}")
            patches.append((path, 0, {"url": url, "sha256": expected}))
    for name in local_patches:
        path = recipe / name
        expected = digest(path)
        if expected not in checksums:
            raise ContractError(f"Local patch not covered by recipe checksum: {name}")
        patches.append((path, 1, {"recipe": recipe_id, "path": f"{recipe_directory}/{name}",
                                  "sha256": expected}))
    if package == "bash":
        for name, scope in (
            ("bash-completion-requires-readline.patch",
             "Guard readline-only MSYS completion option; enabled-readline behavior unchanged"),
            ("bash-install-fail-closed.patch",
             "Propagate failures from every recursive staged installation command")
        ):
            path = Path(__file__).resolve().parent / "patches" / name
            patches.append((path, 1, {
                "recipe": "local-downstream-compatibility", "path": path.name,
                "sha256": digest(path), "scope": scope
            }))
    if package == "perl":
        path = Path(__file__).resolve().parent / "patches/perl-empty-symlink-predicate.patch"
        patches.append((path, 1, {
            "recipe": "local-downstream-safety", "path": path.name,
            "sha256": digest(path), "scope": "Abort before an empty symlink predicate can execute a pathname"
        }))
    shutil.copytree(sources / source_id, output, symlinks=True)
    transformations = []
    if package == "perl":
        # MSYS patch text mode normalizes these release files; WSL patch does not.
        for rel in ("cpan/Win32API-File/Makefile.PL", "cpan/Win32API-File/t/file.t"):
            path = output / rel
            data = path.read_bytes()
            if b"\r\n" not in data or b"\n" in data.replace(b"\r\n", b""):
                raise ContractError(f"Expected uniformly CRLF Perl release file: {rel}")
            before = digest(path)
            path.write_bytes(data.replace(b"\r\n", b"\n"))
            transformations.append({"path": rel, "operation": "CRLF-to-LF",
                                    "before_sha256": before, "after_sha256": digest(path)})
    applied = []
    generators = []
    log_path = output.with_name(output.name + ".patch.log")
    with log_path.open("x", encoding="utf-8", newline="\n") as log:
        for path, level, origin in patches:
            fuzz = REVIEWED_FUZZ.get((package, path.name), 0)
            result = subprocess.run(
                ["patch", "--batch", "--forward", f"--fuzz={fuzz}", f"-p{level}", "-i", str(path.resolve())],
                cwd=output, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            log.write(f"=== {path.name} ===\n{result.stdout}\n")
            log.flush()
            if result.returncode != 0:
                raise ContractError(f"Patch failed ({path.name}); retain failed source/log: {log_path}")
            applied.append({**origin, "maximum_fuzz": fuzz, "transcript": result.stdout})
        if package == "perl":
            from perl_safety import verify_guards
            verify_guards(output)
        if regenerate and package in ("bash", "coreutils"):
            command = ["autoconf"] if package == "bash" else ["autoreconf", "-fi"]
            if not shutil.which(command[0]):
                raise ContractError(f"Missing source generator {command[0]}; contact bootstrap owner")
            result = subprocess.run(command, cwd=output, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            log.write(f"=== {' '.join(command)} ===\n{result.stdout}\n")
            if result.returncode != 0:
                raise ContractError(f"Source regeneration failed; see {log_path}")
            generators.append({"command": command, "transcript": result.stdout})
    files = inventory(output)
    with report_path.open("x", encoding="utf-8", newline="\n") as dest:
        json.dump({
            "schema": 1, "package": package, "source_id": source_id, "recipe_id": recipe_id,
            "source_manifest_sha256": digest(sources / f"{source_id}.inventory.json"),
            "recipe_manifest_sha256": digest(sources / f"{recipe_id}.inventory.json"),
            "patches": applied, "transformations": transformations, "generators": generators, "files": files,
            "status": "source-prepared-not-built",
            "pending": ([] if regenerate else ["recipe-prepare-tail-and-regeneration"]) +
                       ["compile", "native-runtime-tests"]
        }, dest, indent=2, sort_keys=True)
        dest.write("\n")
    return {"package": package, "patches": len(applied), "files": len(files), "report": str(report_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=PACKAGES, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regenerate", action="store_true", help="Run Bash/coreutils source generators")
    args = parser.parse_args()
    print(json.dumps(prepare(args.package, args.sources, args.cache, args.output, args.regenerate)))


if __name__ == "__main__":
    main()
