import sys,zipfile,struct
z=zipfile.ZipFile(sys.argv[1])
bad=[]; exe=0; dll=0; checked=0
for n in z.namelist():
    if n.endswith(".exe") or n.endswith(".dll"):
        b=z.read(n)
        if b[:2]!=b"MZ": bad.append((n,"not MZ")); continue
        pe=struct.unpack_from("<i",b,0x3c)[0]
        if b[pe:pe+4]!=b"PE\0\0": bad.append((n,"no PE")); continue
        mach=struct.unpack_from("<H",b,pe+4)[0]
        checked+=1
        if n.endswith(".exe"): exe+=1
        else: dll+=1
        if mach!=0xAA64: bad.append((n,"0x%04X"%mach))
print("checked PE files: %d  (exe=%d dll=%d)"%(checked,exe,dll))
if bad:
    print("NON-ARM64 or malformed:")
    for n,w in bad[:40]: print("  ",w,n)
else:
    print("ALL PE files are 0xAA64 (native ARM64) - ZERO exceptions")
for n in z.namelist():
    if n.endswith("busybox.exe") or n.endswith("ash.exe"):
        b=z.read(n); pe=struct.unpack_from("<i",b,0x3c)[0]; mach=struct.unpack_from("<H",b,pe+4)[0]
        print("  shell: %s  0x%04X"%(n,mach))
