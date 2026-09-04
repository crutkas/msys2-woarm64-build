import sys, struct
for p in sys.argv[1:]:
    d = open(p, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3c)[0]
    sig = d[pe:pe+4]
    mach = struct.unpack_from("<H", d, pe+4)[0]
    magic = struct.unpack_from("<H", d, pe+24)[0]
    print("%s  Machine=0x%04X %s  Magic=0x%04X  sig=%r" % (
        p, mach, "AA64" if mach == 0xAA64 else "NOT-ARM64", magic, sig))
