import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct


def coff(data, header, pe=False):
    machine, nsections, _, symoff, nsyms, optional, _ = struct.unpack_from("<HHIIIHH", data, header)
    if machine != 0xaa64:
        raise ValueError("Expected raw AA64 COFF")
    strings = data[symoff + 18 * nsyms:] if symoff else b""

    def string(offset):
        return strings[offset:strings.index(0, offset)].decode("utf-8", "replace")

    sections = []
    for i in range(nsections):
        off = header + 20 + optional + 40 * i
        name = data[off:off + 8].rstrip(b"\0").decode("ascii")
        if name.startswith("/"):
            name = string(int(name[1:]))
        vsize, rva, size, raw, relocs, _, nrelocs, _, flags = struct.unpack_from("<IIIIIIHHI", data, off + 8)
        sections.append(dict(name=name, rva=rva, size=size, raw=raw, vsize=vsize,
                             relocations=relocs, nrelocs=nrelocs, flags=flags))
    symbols = []
    by_index = {}
    index, filename = 0, None
    while index < nsyms:
        off = symoff + index * 18
        name_bytes = data[off:off + 8]
        name = (string(struct.unpack_from("<I", name_bytes, 4)[0]) if name_bytes[:4] == b"\0" * 4
                else name_bytes.rstrip(b"\0").decode("utf-8", "replace"))
        value, section, kind, storage, aux = struct.unpack_from("<IhHBB", data, off + 8)
        if name == ".file":
            filename = data[off + 18:off + 18 * (aux + 1)].split(b"\0")[0].decode("utf-8", "replace")
        sym = dict(name=name, value=value, section=section, kind=kind, storage=storage,
                   file=filename, index=index)
        if 0 < section <= nsections:
            sym["rva"] = sections[section - 1]["rva"] + value
        symbols.append(sym)
        by_index[index] = sym
        index += 1 + aux
    return sections, symbols, by_index


def inspect(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Not a PE image")
    sections, symbols, _ = coff(data, pe + 4, pe=True)
    optional = pe + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x20b:
        raise ValueError("Not PE32+")

    def offset(rva, count=1):
        for section in sections:
            delta = rva - section["rva"]
            if 0 <= delta and delta + count <= section["size"]:
                return section["raw"] + delta
        raise ValueError(f"Unmapped RVA {rva:#x}")

    def string(rva):
        start = offset(rva)
        return data[start:data.index(0, start)].decode("ascii")

    iat = {}
    import_rva, import_size = struct.unpack_from("<II", data, optional + 120)
    for i in range(0, import_size, 20):
        lookup, _, _, dll, thunk = struct.unpack_from("<IIIII", data, offset(import_rva + i, 20))
        if not any((lookup, dll, thunk)):
            break
        name = string(dll)
        lookup = lookup or thunk
        for j in range(65536):
            value = struct.unpack_from("<Q", data, offset(lookup + j * 8, 8))[0]
            if not value:
                break
            symbol = "ordinal:" + str(value & 65535) if value >> 63 else string(value + 2)
            iat[thunk + j * 8] = dict(dll=name, symbol=symbol)
    names = {s["name"]: s for s in symbols}
    start = names["__RUNTIME_PSEUDO_RELOC_LIST__"]["rva"]
    end = names["__RUNTIME_PSEUDO_RELOC_LIST_END__"]["rva"]
    entries = []
    if end != start:
        version = struct.unpack_from("<III", data, offset(start, 12))
        if version != (0, 0, 1) or (end - start - 12) % 12:
            raise ValueError("Unexpected pseudo-reloc table protocol")
        for pos in range(start + 12, end, 12):
            sym, target, flags = struct.unpack_from("<III", data, offset(pos, 12))
            section = next(s for s in sections if s["rva"] <= target < s["rva"] + max(s["size"], s["vsize"]))
            functions = [s for s in symbols if s.get("rva", end + 1) <= target and
                         s["kind"] == 0x20 and s["section"] > 0 and
                         sections[s["section"] - 1] == section]
            nearest = max(functions, key=lambda s: s["rva"]) if functions else None
            word = struct.unpack_from("<I", data, offset(target, 4))[0]
            entries.append(dict(table_rva=hex(pos), sym_rva=hex(sym), target_rva=hex(target),
                                bits=flags & 255, flags=hex(flags), imported=iat.get(sym),
                                section=section["name"], word=hex(word),
                                instruction="ADRP" if word & 0x9f000000 == 0x90000000 else None,
                                function=nearest["name"] if nearest else None,
                                source_file=nearest["file"] if nearest else None,
                                function_offset=hex(target - nearest["rva"]) if nearest else None))
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(),
                table_start=hex(start), table_end=hex(end), count=len(entries),
                bits=dict(Counter(str(e["bits"]) for e in entries)),
                imported_counts=dict(Counter(str(e["imported"]) for e in entries)),
                entries=entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Do not overwrite diagnostic evidence")
    reports = [inspect(path.resolve(strict=True)) for path in args.images]
    args.output.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    for report in reports:
        print(json.dumps({k: v for k, v in report.items() if k != "entries"}))
        print(json.dumps(report["entries"][:6], indent=2))
