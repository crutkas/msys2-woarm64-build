#!/bin/bash
# Verify this Windows ARM64 host can execute an ARM64 PE (the L169 requirement).
echo "host uname: $(uname -a)"
found=""
for e in /c/Users/crutkasLocal/arm64-loadtest/*.exe; do
  [ -f "$e" ] || continue
  found="$e"; break
done
if [ -n "$found" ]; then
  echo "arm64 exe under test: $found"
  out="$("$found" 2>&1 | head -3)"; rc=$?
  echo "exit=$rc"; echo "output: $out"
else
  echo "no arm64 exe in arm64-loadtest; checking PE machine of Git's own busybox if present"
fi
# Also: is Git-for-Windows' own git.exe arm64 or x86-64? (affects whether sh stack is emulated)
gx="/c/Program Files/Git/cmd/git.exe"
[ -f "$gx" ] || gx="/c/Program Files/Git/bin/git.exe"
if [ -f "$gx" ]; then
  m=$(python3 - "$gx" <<'PY' 2>/dev/null
import sys,struct
d=open(sys.argv[1],'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]
print(hex(struct.unpack_from('<H',d,pe+4)[0]))
PY
)
  echo "Git-for-Windows git.exe PE machine = ${m:-unknown} (0x8664=x64, 0xaa64=arm64)"
fi
