import sys, zipfile, hashlib, os

ours_path = sys.argv[1]
up_path = sys.argv[2]
ml = "clangarm64"

def bin_exes(zpath):
    z = zipfile.ZipFile(zpath)
    names = z.namelist()
    out = {}
    for n in names:
        # match <ml>/bin/*.exe  (basename only, one level under bin)
        if n.startswith(ml + "/bin/") and n.endswith(".exe"):
            rest = n[len(ml + "/bin/"):]
            if "/" not in rest:
                out[rest] = hashlib.sha256(z.read(n)).hexdigest()
    return out, z, names

ours, zo, ournames = bin_exes(ours_path)
up, zu, upnames = bin_exes(up_path)

print("=== bin/*.exe counts ===")
print("ours:", len(ours), " upstream:", len(up))

oset, uset = set(ours), set(up)

print("\n=== IN UPSTREAM, NOT IN OURS (the 8 to classify) ===")
git_sha_ours = ours.get("git.exe")
for n in sorted(uset - oset):
    print("  MISSING-FROM-OURS:", n)

print("\n=== IN OURS, NOT IN UPSTREAM ===")
for n in sorted(oset - uset):
    print("  OURS-EXTRA:", n)

print("\n=== the 11 non-builtin survivors: present by NAME in OUR final zip? ===")
survivors = ["git-daemon","git-http-backend","git-http-fetch","git-http-push",
             "git-remote-http","git-remote-https","git-remote-ftp","git-remote-ftps",
             "git-imap-send","git-sh-i18n--envsubst","git-shell"]
# they may be in bin/ (after libexec fold) OR libexec/git-core/
allnames = ournames
for s in survivors:
    hits = [n for n in allnames if n.endswith("/" + s + ".exe") or n.endswith("/bin/" + s + ".exe")]
    status = "PRESENT" if hits else "*** ABSENT ***"
    where = hits[0] if hits else ""
    print("  %-26s %s  %s" % (s, status, where))
