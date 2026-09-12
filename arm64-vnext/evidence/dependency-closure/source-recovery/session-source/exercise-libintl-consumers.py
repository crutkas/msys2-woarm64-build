import argparse
import ctypes as c
import gettext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


spec = importlib.util.spec_from_file_location("native_nls", Path(__file__).with_name("qualify-official-nls.py"))
nls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    prefix = args.root / "mingwarm64"
    context = args.output / "context"
    context.mkdir()
    (context / "empty.gitconfig").touch()
    (context / "home").mkdir()
    (context / "tmp").mkdir()
    env = {
        "SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
        "PATH": str(prefix / "bin") + ";" + os.environ["SystemRoot"] + r"\System32",
        "PATHEXT": ".COM;.EXE;.BAT;.CMD", "HOME": str(context / "home"),
        "USERPROFILE": str(context / "home"), "TEMP": str(context / "tmp"), "TMP": str(context / "tmp"),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(context / "empty.gitconfig"),
        "GIT_TERMINAL_PROMPT": "0", "GIT_EXEC_PATH": str(prefix / "libexec/git-core"),
        "GIT_AUTHOR_NAME": "Native qualification", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Native qualification", "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "LANGUAGE": "fr", "LC_ALL": "fr_FR.UTF-8", "LANG": "fr_FR.UTF-8",
    }
    report = {"status": "incomplete", "root": str(args.root), "environment": env,
              "scope": "Actual local protocol/API/error paths, not remote HTTPS/IMAP/WebDAV service qualification",
              "known_unresolved_failure": "Separate native local clone --bare crashed 0xC0000005 in both French and C; this run exercises other roles and does not resolve or waive that failure.",
              "runs": [], "consumer_results": [], "api": {}}
    git = prefix / "bin/git.exe"
    repo = context / "repo"
    bare = context / "repo.git"

    def run(name, executable, arguments, input_bytes=b"", expected=0, predicate=None, extra_env=None, cwd=None):
        values = dict(env)
        values.update(extra_env or {})
        command = [str(executable), *map(str, arguments)]
        process = subprocess.Popen(command, cwd=cwd or context, env=values, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        loaded = []
        snapshot_error = None
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            try:
                loaded = nls.modules(process.pid)
            except OSError as error:
                snapshot_error = {"winerror": error.winerror, "message": str(error)}
                if process.poll() is not None:
                    break
                if error.winerror not in (24, 299):
                    raise
            if any(item["name"].lower() == "libintl-8.dll" for item in loaded):
                break
            time.sleep(0.001)
        stdout, stderr = process.communicate(input_bytes, timeout=30)
        (args.output / (name + ".stdout")).write_bytes(stdout)
        (args.output / (name + ".stderr")).write_bytes(stderr)
        record = {"name": name, "command": command, "pid": process.pid,
                  "executable_sha256": nls.digest(executable), "raw_exit": process.returncode,
                  "expected_exit": expected, "stdout": str(args.output / (name + ".stdout")),
                  "stderr": str(args.output / (name + ".stderr")),
                  "input_sha256": hashlib.sha256(input_bytes).hexdigest(), "modules": loaded,
                  "module_snapshot_error": snapshot_error,
                  "passed": process.returncode == expected and (predicate(stdout, stderr) if predicate else True)}
        for module in loaded:
            if module["name"].lower() == "libintl-8.dll":
                if Path(module["path"]).resolve() != (prefix / "bin/libintl-8.dll").resolve():
                    raise RuntimeError("Consumer loaded a libintl outside the projection")
                if module["sha256"] != "31db0d0e7780cf28dca1309a894cb775b2ab130c4ba777c546a206970ca47320":
                    raise RuntimeError("Consumer loaded different libintl bytes")
            if module["name"].lower().startswith("msys-"):
                raise RuntimeError("MSYS appeared in a MinGW consumer")
        report["runs"].append(record)
        return record, stdout, stderr

    def setup(name, arguments, input_bytes=b""):
        record, stdout, _ = run(name, git, arguments, input_bytes)
        if not record["passed"]:
            raise RuntimeError(f"Native fixture setup failed: {name}")
        return stdout.strip()

    def consumer(relative, role, arguments, input_bytes=b"", expected=0, predicate=None, extra_env=None, cwd=None):
        name = relative.replace("/", "_").replace(".exe", "")
        record, _, _ = run(name, args.root.joinpath(*relative.split("/")), arguments, input_bytes,
                           expected, predicate, extra_env, cwd)
        report["consumer_results"].append({"path": relative, "role": role, "record": name,
                                           "passed": record["passed"], "raw_exit": record["raw_exit"],
                                           "expected_exit": expected})

    try:
        setup("setup-init", ["init", "-b", "main", repo])
        blob = setup("setup-blob", ["-C", repo, "hash-object", "-w", "--stdin"], b"native libintl qualification\n").decode()
        tree = setup("setup-tree", ["-C", repo, "mktree"], f"100644 blob {blob}\treadme.txt\n".encode()).decode()
        commit = setup("setup-commit", ["-C", repo, "commit-tree", tree, "-m", "Native qualification fixture"]).decode()
        setup("setup-ref", ["-C", repo, "update-ref", "refs/heads/main", commit])
        setup("setup-reset", ["-C", repo, "reset", "--hard", commit])
        setup("setup-bare-init", ["init", "--bare", bare])
        bare_blob = setup("setup-bare-blob", ["--git-dir", bare, "hash-object", "-w", "--stdin"],
                          b"native libintl qualification\n").decode()
        bare_tree = setup("setup-bare-tree", ["--git-dir", bare, "mktree"],
                          f"100644 blob {bare_blob}\treadme.txt\n".encode()).decode()
        commit = setup("setup-bare-commit", ["--git-dir", bare, "commit-tree", bare_tree,
                                           "-m", "Native qualification fixture"]).decode()
        setup("setup-bare-ref", ["--git-dir", bare, "update-ref", "refs/heads/main", commit])
        setup("setup-bare-head", ["--git-dir", bare, "symbolic-ref", "HEAD", "refs/heads/main"])
        with (prefix / "share/locale/fr/LC_MESSAGES/git.mo").open("rb") as stream:
            oracle = gettext.GNUTranslations(stream)
        french_branch = (oracle.gettext("On branch ") + "main").encode("utf-8")
        report["git_catalog"] = {"sha256": nls.digest(prefix / "share/locale/fr/LC_MESSAGES/git.mo"),
                                 "expected_branch": french_branch.decode()}
        for relative in ("mingwarm64/bin/git.exe", "mingwarm64/libexec/git-core/git.exe"):
            consumer(relative, "Real repository status and package-owned French catalog", ["-C", repo, "status"],
                     predicate=lambda out, err: french_branch in out and b"readme.txt" not in out)
        for relative in ("mingwarm64/bin/scalar.exe", "mingwarm64/libexec/git-core/scalar.exe"):
            consumer(relative, "Read actual empty private Scalar repository configuration", ["list"])
        for stem in ("git-receive-pack", "git-upload-pack"):
            consumer("mingwarm64/bin/" + stem + ".exe", "Real Git wire-protocol reference advertisement",
                     ["--advertise-refs", bare], predicate=lambda out, err: commit.encode() in out)
        packet = b"argument HEAD\n"
        archive_request = f"{len(packet) + 4:04x}".encode() + packet + b"0000"
        consumer("mingwarm64/bin/git-upload-archive.exe", "Actual upload-archive request for committed tree",
                 [bare], archive_request, predicate=lambda out, err: b"ACK" in out and len(out) > 100)
        for relative in ("mingwarm64/bin/git-shell.exe", "mingwarm64/libexec/git-core/git-shell.exe"):
            consumer(relative, "Restricted-shell dispatch to actual Git upload-pack",
                     ["-c", "git-upload-pack '" + bare.as_posix() + "'"], b"0000",
                     predicate=lambda out, err: commit.encode() in out)
        request = ("git-upload-pack /repo.git\0host=localhost\0").encode()
        request = f"{len(request) + 4:04x}".encode() + request + b"0000"
        consumer("mingwarm64/libexec/git-core/git-daemon.exe", "Actual inetd packet dispatch to upload-pack",
                 ["--inetd", "--export-all", "--base-path=" + str(context)], request,
                 predicate=lambda out, err: commit.encode() in out)
        consumer("mingwarm64/libexec/git-core/git-http-backend.exe", "Actual smart-HTTP CGI reference response",
                 [], extra_env={"REQUEST_METHOD": "GET", "PATH_INFO": "/repo.git/info/refs",
                                "QUERY_STRING": "service=git-upload-pack", "GIT_PROJECT_ROOT": str(context),
                                "GIT_HTTP_EXPORT_ALL": "1", "SERVER_PROTOCOL": "HTTP/1.1"},
                 predicate=lambda out, err: b"application/x-git-upload-pack-advertisement" in out and commit.encode() in out)
        for protocol in ("ftp", "ftps", "http", "https"):
            consumer("mingwarm64/libexec/git-core/git-remote-" + protocol + ".exe",
                     "Actual remote-helper capability protocol; no remote transfer claimed",
                     ["origin", protocol + "://example.invalid/repo"], b"capabilities\n\n",
                     predicate=lambda out, err: b"fetch" in out and b"option" in out)
        consumer("mingwarm64/libexec/git-core/git-sh-i18n--envsubst.exe",
                 "Actual restricted environment substitution", ["$QUALIFICATION_WORD"],
                 b"$QUALIFICATION_WORD\n", predicate=lambda out, err: out == b"native-libintl\n",
                 extra_env={"QUALIFICATION_WORD": "native-libintl"})
        consumer("mingwarm64/libexec/git-core/git-http-fetch.exe",
                 "Actual missing-arguments rejection; no HTTP fetch service claimed", [], expected=129,
                 predicate=lambda out, err: bool(err))
        consumer("mingwarm64/libexec/git-core/git-http-push.exe",
                 "Actual missing-arguments rejection; no WebDAV service claimed", [], expected=129,
                 predicate=lambda out, err: bool(err))
        consumer("mingwarm64/libexec/git-core/git-imap-send.exe",
                 "Actual absent IMAP account configuration rejection; no remote IMAP claim",
                 [], b"From: Test <test@example.invalid>\n\nlocal-only\n", expected=1,
                 predicate=lambda out, err: bool(err), cwd=repo)

        intl = c.CDLL(str(prefix / "bin/libintl-8.dll"))
        intl.libintl_setlocale.argtypes = [c.c_int, c.c_char_p]
        intl.libintl_setlocale.restype = c.c_char_p
        if not intl.libintl_setlocale(0, b""):
            raise RuntimeError("Native locale selection failed")
        idn = c.CDLL(str(prefix / "bin/libidn2-0.dll"))
        idn.idn2_lookup_u8.argtypes = [c.c_char_p, c.POINTER(c.c_void_p), c.c_int]
        idn.idn2_lookup_u8.restype = c.c_int
        idn.idn2_free.argtypes = [c.c_void_p]
        address = c.c_void_p()
        code = idn.idn2_lookup_u8("b\u00fccher.example".encode(), c.byref(address), 0)
        converted = c.string_at(address).decode() if address.value else None
        if address.value:
            idn.idn2_free(address)
        report["api"]["idn2"] = {"return": code, "actual": converted, "expected": "xn--bcher-kva.example"}
        report["consumer_results"].append({"path": "mingwarm64/bin/libidn2-0.dll", "role": "Real UTF-8 IDNA lookup",
                                           "passed": code == 0 and converted == "xn--bcher-kva.example", "api_return": code})
        class Regex(c.Structure):
            _fields_ = [("re_nsub", c.c_size_t), ("value", c.c_void_p)]
        class Match(c.Structure):
            _fields_ = [("start", c.c_int), ("end", c.c_int)]
        tre = c.CDLL(str(prefix / "bin/libtre-5.dll"))
        tre.tre_regcomp.argtypes = [c.POINTER(Regex), c.c_char_p, c.c_int]
        tre.tre_regexec.argtypes = [c.POINTER(Regex), c.c_char_p, c.c_size_t, c.POINTER(Match), c.c_int]
        tre.tre_regfree.argtypes = [c.POINTER(Regex)]
        expression = Regex()
        compiled = tre.tre_regcomp(c.byref(expression), b"^(native)-([0-9]+)$", 1)
        if compiled != 0:
            raise RuntimeError(f"libtre regex compilation returned {compiled}")
        try:
            match = (Match * 3)()
            matched = tre.tre_regexec(c.byref(expression), b"native-123", 3, match, 0)
            offsets = [[item.start, item.end] for item in match]
            no_match = tre.tre_regexec(c.byref(expression), b"wrong", 0, None, 0)
        finally:
            tre.tre_regfree(c.byref(expression))
        passed = matched == 0 and offsets == [[0, 10], [0, 6], [7, 10]] and no_match == 1
        report["api"]["tre"] = {"compile": compiled, "match": matched, "offsets": offsets, "no_match": no_match}
        report["consumer_results"].append({"path": "mingwarm64/bin/libtre-5.dll",
                                           "role": "Actual ERE capture offsets and nonmatch", "passed": passed})
        report["api"]["modules"] = nls.modules(os.getpid())
        for module in report["api"]["modules"]:
            if module["name"].lower() in ("libintl-8.dll", "libiconv-2.dll", "libtre-5.dll", "libidn2-0.dll"):
                if Path(module["path"]).resolve() != (prefix / "bin" / module["name"]).resolve():
                    raise RuntimeError("C API test loaded a dependency from outside the projection")
            if module["name"].lower().startswith("msys-"):
                raise RuntimeError("Unexpected MSYS runtime in C APIs")
        report["passed_count"] = sum(item["passed"] for item in report["consumer_results"])
        report["consumer_count"] = len(report["consumer_results"])
        report["status"] = "all-listed-local-behaviors-passed" if report["consumer_count"] == 21 and report["passed_count"] == 21 else "failed-or-partial"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "count": report.get("consumer_count"),
                      "passed": report.get("passed_count"), "results": report["consumer_results"]}))


if __name__ == "__main__":
    main()
