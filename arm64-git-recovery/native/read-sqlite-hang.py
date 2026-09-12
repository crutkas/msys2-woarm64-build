"""Read owned ARM64 minidump PCs/frame chains without attaching to a process."""

import argparse
import json
from pathlib import Path
import struct
import subprocess

from sources import ContractError, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dump", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(r"C:\ag-sqlite-e138-01")
if not args.dump.resolve().is_relative_to(root) or not args.output.resolve().is_relative_to(root) or args.output.exists():
    raise ContractError("Owned input and fresh output required")
data = args.dump.read_bytes()
if data[:4] != b"MDMP":
    raise ContractError("Not a minidump")
count, directory = struct.unpack_from("<II", data, 8)
streams = {kind: (size, rva) for kind, size, rva in
           (struct.unpack_from("<III", data, directory + 12 * i) for i in range(count))}
modules = []
rva = streams[4][1]
for i in range(struct.unpack_from("<I", data, rva)[0]):
    row = rva + 4 + i * 108
    base, size, _, _, name = struct.unpack_from("<QIIII", data, row)
    length = struct.unpack_from("<I", data, name)[0]
    modules.append({"base": base, "size": size, "path": data[name + 4:name + 4 + length].decode("utf-16le")})


def address_info(address):
    module = next((m for m in modules if m["base"] <= address < m["base"] + m["size"]), None)
    record = {"address": hex(address)}
    if module:
        record.update(module=module["path"], rva=hex(address - module["base"]))
        path = Path(module["path"])
        if path.is_relative_to(root) and path.is_file():
            with path.open("rb") as stream:
                header = stream.read(64)
                pe = struct.unpack_from("<I", header, 60)[0]
                stream.seek(pe + 48)
                preferred_base = struct.unpack("<Q", stream.read(8))[0]
            result = subprocess.run([str(root / "compiler/bin/addr2line.exe"), "-f", "-C", "-e", str(path),
                                     hex(preferred_base + address - module["base"])],
                                    capture_output=True, text=True, check=True, timeout=30)
            record["symbol"] = result.stdout.strip()
    return record


threads = []
rva = streams[3][1]
for i in range(struct.unpack_from("<I", data, rva)[0]):
    row = rva + 4 + i * 48
    tid = struct.unpack_from("<I", data, row)[0]
    stack_base, stack_size, stack_rva, context_size, context_rva = struct.unpack_from("<QIIII", data, row + 24)
    if context_size < 272:
        raise ContractError("Missing native ARM64 thread context")
    flags = struct.unpack_from("<I", data, context_rva)[0]
    if flags & 0x00400000 == 0:
        raise ContractError("Unexpected context architecture")
    fp, lr, sp, pc = struct.unpack_from("<QQQQ", data, context_rva + 240)
    record = {"tid": tid, "pc": address_info(pc), "lr": address_info(lr), "sp": hex(sp), "frames": []}
    seen = set()
    while fp not in seen and stack_base <= fp and fp + 16 <= stack_base + stack_size and len(seen) < 12:
        seen.add(fp)
        parent, caller = struct.unpack_from("<QQ", data, stack_rva + fp - stack_base)
        record["frames"].append(address_info(caller))
        fp = parent
    threads.append(record)
report = {"dump_sha256": digest(args.dump), "scope": "Offline frame-pointer evidence, not a complete unwind",
          "threads": threads}
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
