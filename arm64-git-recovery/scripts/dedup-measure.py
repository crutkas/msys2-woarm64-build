import sys, zipfile, hashlib, collections
z = zipfile.ZipFile(sys.argv[1])
ml = "clangarm64"
groups = {
  "bin/*.exe": [n for n in z.namelist() if n.startswith(ml+"/bin/") and n.endswith(".exe")],
  "libexec/git-core/*.exe": [n for n in z.namelist() if n.startswith(ml+"/libexec/git-core/") and n.endswith(".exe")],
}
total_zip = sum(zi.file_size for zi in z.infolist())
print("uncompressed total of ALL entries: %d bytes (%.1f MB)" % (total_zip, total_zip/1e6))
grand_dup = 0
for label, names in groups.items():
    by_hash = collections.defaultdict(list)
    sizes = {}
    for n in names:
        b = z.read(n)
        h = hashlib.sha256(b).hexdigest()
        by_hash[h].append(n)
        sizes[n] = len(b)
    total = sum(sizes[n] for n in names)
    distinct = len(by_hash)
    # duplicate bytes = total - one-copy-per-distinct
    onecopy = sum(len(z.read(v[0])) for v in by_hash.values())
    dup = total - onecopy
    grand_dup += dup
    print("\n[%s]" % label)
    print("  files=%d  distinct-sha256=%d  total=%.1f MB  one-copy=%.1f MB  DUPLICATE=%.1f MB"
          % (len(names), distinct, total/1e6, onecopy/1e6, dup/1e6))
    # show the biggest hash clusters
    clusters = sorted(by_hash.items(), key=lambda kv: -len(kv[1]))[:5]
    for h, v in clusters:
        print("    %2d copies  %8d B each  %s  e.g. %s" % (len(v), len(z.read(v[0])), h[:12], v[0].split("/")[-1]))
print("\nGRAND DUPLICATE across git exe groups: %.1f MB" % (grand_dup/1e6))
