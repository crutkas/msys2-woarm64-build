import zipfile, hashlib, sys, collections

t = sys.argv[1]
ml = "clangarm64"
z = zipfile.ZipFile(t)
names = z.namelist()

# distinct hashes across bin/*.exe
binexes = [n for n in names if n.startswith(ml+"/bin/") and n.endswith(".exe") and "/" not in n[len(ml+"/bin/"):]]
by = collections.defaultdict(list)
for n in binexes:
    by[hashlib.sha256(z.read(n)).hexdigest()].append(n)

print("=== FINAL MEASUREMENT (all from this file) ===")
print("total zip entries:", len(names))
print("bin/*.exe:", len(binexes), " distinct sha256:", len(by))
print()
print("duplicate groups (n>1):")
dup_bytes = 0
for h, ns in sorted(by.items(), key=lambda kv: -len(kv[1])):
    if len(ns) > 1:
        sz = z.getinfo(ns[0]).file_size
        dup_bytes += sz*(len(ns)-1)
        print("  %dx  %d B  %s  ::" % (len(ns), sz, h[:12]), ", ".join(sorted(x.split("/")[-1] for x in ns)))
print("duplicate bytes (extra copies):", dup_bytes, "(%.1f MB)" % (dup_bytes/1e6))
print()
# stubs
gcm = [n for n in binexes if "credential-manager" in n or "credential-helper-selector" in n]
print("credential stubs (153353 B non-functional):", [n.split("/")[-1] for n in gcm],
      "sizes:", [z.getinfo(n).file_size for n in gcm])
print("pipeline-stubs entries:", sum(1 for n in names if "pipeline-stubs" in n))
print(".stub entries:", sum(1 for n in names if n.endswith(".stub")))
print("GCM STUB-PLACEHOLDER doc present:", any("STUB-PLACEHOLDER" in n for n in names))
print()
# PE machine sweep
import struct
pe_all = [n for n in names if n.endswith(".exe") or n.endswith(".dll")]
bad = []
for n in pe_all:
    d = z.read(n)
    off = struct.unpack_from("<I", d, 0x3c)[0]
    mach = struct.unpack_from("<H", d, off+4)[0]
    if mach != 0xAA64:
        bad.append((n, hex(mach)))
print("PE files:", len(pe_all), " all 0xAA64:", not bad, (" exceptions: "+str(bad)) if bad else "")
# pins
print("git.exe pin:", hashlib.sha256(z.read(ml+"/bin/git.exe")).hexdigest())
print("ash.exe pin:", hashlib.sha256(z.read(ml+"/bin/ash.exe")).hexdigest())
# https helpers
req = ["git-remote-http","git-remote-https","git-http-fetch","git-http-push"]
print("HTTPS helpers present:", all(any(n.endswith("/"+r+".exe") for n in names) for r in req))
