import sys,zipfile,hashlib,collections
z=zipfile.ZipFile(sys.argv[1])
ml="clangarm64"
binx=[n for n in z.namelist() if n.startswith(ml+"/bin/") and n.endswith(".exe")]
libx=[n for n in z.namelist() if n.startswith(ml+"/libexec/git-core/") and n.endswith(".exe")]
print("upstream bin/*.exe:", len(binx), " libexec/git-core/*.exe:", len(libx))
for label,names in [("bin",binx),("libexec",libx)]:
    bh=collections.defaultdict(list)
    for n in names:
        bh[hashlib.sha256(z.read(n)).hexdigest()].append(n)
    tot=sum(z.getinfo(n).file_size for n in names)
    print("  %s: files=%d distinct=%d uncompressed=%.1f MB"%(label,len(names),len(bh),tot/1e6))
print("upstream TOTAL uncompressed: %.1f MB"%(sum(zi.file_size for zi in z.infolist())/1e6))
gnames=[n for n in z.namelist() if n.endswith("/git.exe")]
print("git.exe entries:", gnames)
# distinct sizes in libexec: how does upstream store builtins? show a few libexec sizes
for n in sorted(libx)[:6]:
    print("   libexec sample:", n.split("/")[-1], z.getinfo(n).file_size)
