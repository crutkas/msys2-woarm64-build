"""Bounds-checked PE dependencies for private native utility qualification."""

import hashlib
from pathlib import Path
import struct


class PeError(ValueError):
    pass


class Image:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.data = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        if self.data[:2] != b"MZ":
            raise PeError(f"Missing MZ header: {self.path}")
        pe = self.unpack("<I", 60)[0]
        if pe < 64 or self.data[pe:pe + 4] != b"PE\0\0":
            raise PeError(f"Missing PE signature: {self.path}")
        self.machine, count = self.unpack("<HH", pe + 4)
        size = self.unpack("<H", pe + 20)[0]
        self.characteristics = self.unpack("<H", pe + 22)[0]
        optional = pe + 24
        self.magic = self.unpack("<H", optional)[0]
        if self.magic == 0x20B:
            self.pointer_size = 8
            self.image_base = self.unpack("<Q", optional + 24)[0]
            directory_offset, number_offset = 112, 108
        elif self.magic == 0x10B:
            self.pointer_size = 4
            self.image_base = self.unpack("<I", optional + 28)[0]
            directory_offset, number_offset = 96, 92
        else:
            raise PeError(f"Invalid optional header: {self.path}")
        self.size_headers = self.unpack("<I", optional + 60)[0]
        if not 0 < count <= 96 or optional + size > len(self.data):
            raise PeError("Invalid section count or optional header bounds")
        directories = self.unpack("<I", optional + number_offset)[0]
        if directory_offset + directories * 8 > size:
            raise PeError("Data directory table exceeds optional header")
        self.directories = [self.unpack("<II", optional + directory_offset + i * 8)
                            for i in range(directories)]
        self.sections = []
        for index in range(count):
            offset = optional + size + index * 40
            name = self.data[offset:offset + 8].split(b"\0")[0].decode("ascii")
            virtual_size, virtual, raw_size, raw = self.unpack("<IIII", offset + 8)
            if raw + raw_size > len(self.data):
                raise PeError("Section raw bytes exceed file")
            self.sections.append({"name": name, "rva": virtual, "virtual_size": virtual_size,
                                  "raw_size": raw_size, "raw": raw})

    def unpack(self, fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(self.data):
            raise PeError("PE structure exceeds file")
        return struct.unpack_from(fmt, self.data, offset)

    def offset(self, rva, size=1):
        if rva < 0 or size < 0:
            raise PeError("Negative RVA or read length")
        if rva + size <= self.size_headers and rva + size <= len(self.data):
            return rva
        matches = [section["raw"] + rva - section["rva"] for section in self.sections
                   if section["rva"] <= rva and rva + size <= section["rva"] + section["raw_size"]]
        if len(matches) != 1:
            raise PeError(f"Unmapped or ambiguous RVA {rva:#x}")
        return matches[0]

    def string(self, rva, limit=4096):
        offset = self.offset(rva)
        end = self.data.find(b"\0", offset, min(offset + limit, len(self.data)))
        if end < 0:
            raise PeError("Unterminated PE string")
        self.offset(rva, end - offset + 1)
        return self.data[offset:end].decode("ascii")

    def directory(self, index):
        return self.directories[index] if index < len(self.directories) else (0, 0)

    def thunks(self, rva):
        if not rva:
            return []
        items = []
        ordinal_flag = 1 << (self.pointer_size * 8 - 1)
        fmt = "<Q" if self.pointer_size == 8 else "<I"
        for index in range(65536):
            value = self.unpack(fmt, self.offset(rva + index * self.pointer_size, self.pointer_size))[0]
            if value == 0:
                return items
            items.append({"ordinal": value & 0xFFFF} if value & ordinal_flag else
                         {"name": self.string(value + 2)})
        raise PeError("Unterminated import thunk table")

    def imports(self):
        records = []
        for kind, index, descriptor_size in (("import", 1, 20), ("delay", 13, 32)):
            rva, size = self.directory(index)
            if not rva:
                continue
            if size < descriptor_size:
                raise PeError("Import directory is too small")
            terminated = False
            for offset in range(0, size - descriptor_size + 1, descriptor_size):
                words = self.unpack("<" + "I" * (descriptor_size // 4),
                                    self.offset(rva + offset, descriptor_size))
                if not any(words):
                    terminated = True
                    break
                if kind == "import":
                    lookup, _, _, name, address = words
                    names = self.thunks(lookup or address)
                else:
                    attributes, name, _, address, lookup, _, _, _ = words
                    if attributes & ~1:
                        raise PeError("Unsupported delay import attributes")
                    if not attributes & 1:
                        name -= self.image_base
                        lookup = lookup - self.image_base if lookup else 0
                        address = address - self.image_base if address else 0
                    names = self.thunks(lookup or address)
                module = self.string(name)
                if Path(module).name != module or "\\" in module or "/" in module or ":" in module:
                    raise PeError("Import module must be a leaf DLL name")
                records.append({"kind": kind, "module": module.lower(), "symbols": names})
            if not terminated:
                raise PeError("Import descriptors have no bounded terminator")
        return records

    def exports(self):
        rva, size = self.directory(0)
        if not rva:
            return {}
        if size < 40:
            raise PeError("Export directory is too small")
        offset = self.offset(rva, 40)
        base, functions, count, function_rva, name_rva, ordinal_rva = self.unpack("<IIIIII", offset + 16)
        if functions > len(self.data) // 4 or count > len(self.data) // 4:
            raise PeError("Invalid export count")
        values = {}
        for index in range(functions):
            target = self.unpack("<I", self.offset(function_rva + index * 4, 4))[0]
            if target:
                values[f"#{base + index}"] = self.string(target) if rva <= target < rva + size else None
        for index in range(count):
            name = self.string(self.unpack("<I", self.offset(name_rva + index * 4, 4))[0])
            ordinal = self.unpack("<H", self.offset(ordinal_rva + index * 2, 2))[0]
            if ordinal >= functions or f"#{base + ordinal}" not in values or name in values:
                raise PeError("Invalid or duplicate named export")
            values[name] = values[f"#{base + ordinal}"]
        return values

    def summary(self):
        return {"path": str(self.path), "sha256": self.sha256, "size": len(self.data),
                "machine": f"0x{self.machine:04X}", "optional_magic": f"0x{self.magic:03X}",
                "is_dll": bool(self.characteristics & 0x2000)}


def api_sets(schema_path):
    image = Image(schema_path)
    section = next((section for section in image.sections if section["name"] == ".apiset"), None)
    if section is None:
        raise PeError("System API schema lacks .apiset")
    data = image.data[section["raw"]:section["raw"] + section["raw_size"]]

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise PeError("API-set structure exceeds namespace")
        return struct.unpack_from(fmt, data, offset)

    version, size, _, count, entries, _, _ = unpack("<7I", 0)
    if version != 6 or size > len(data):
        raise PeError("Unqualified API-set namespace version or length")
    data = data[:size]

    def text(offset, length):
        if length % 2 or offset < 0 or offset + length > len(data):
            raise PeError("API-set string exceeds namespace")
        return data[offset:offset + length].decode("utf-16-le").lower()

    result = {}
    for index in range(count):
        _, name, length, _, values, value_count = unpack("<6I", entries + index * 24)
        contract = text(name, length) + ".dll"
        records = []
        for j in range(value_count):
            _, alias, alias_length, host, host_length = unpack("<5I", values + j * 20)
            records.append({"importer": text(alias, alias_length), "host": text(host, host_length)})
        result[contract] = records
    return result, image.summary()


def dependency_closure(images, private_bin, system32, expand_system_delay=True):
    private_bin, system32 = Path(private_bin).resolve(), Path(system32).resolve()
    contracts, schema = api_sets(system32 / "apisetschema.dll")
    parsed, exports, edges, failures, deferred = {}, {}, [], [], []
    api_resolutions = {}

    def operating_system_api_host(module):
        import ctypes as C
        from ctypes import wintypes as W
        if module in api_resolutions:
            return api_resolutions[module]["host"]
        kernel = C.WinDLL("kernel32", use_last_error=True)
        kernel.LoadLibraryExW.argtypes = [W.LPCWSTR, W.HANDLE, W.DWORD]
        kernel.LoadLibraryExW.restype = W.HMODULE
        kernel.GetModuleFileNameW.argtypes = [W.HMODULE, W.LPWSTR, W.DWORD]
        kernel.GetModuleFileNameW.restype = W.DWORD
        kernel.FreeLibrary.argtypes = [W.HMODULE]
        kernel.FreeLibrary.restype = W.BOOL
        # Ask the current OS, rather than guessing API-set version aliases.
        # DONT_RESOLVE_DLL_REFERENCES prevents running a new DLL entry point.
        handle = kernel.LoadLibraryExW(module, None, 0x801)
        if not handle:
            api_resolutions[module] = {"host": None, "error": C.get_last_error()}
            return None
        try:
            buffer = C.create_unicode_buffer(32768)
            size = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
            if not size or size >= len(buffer):
                raise C.WinError(C.get_last_error())
            path = Path(buffer.value).resolve()
            if path.parent != system32:
                raise PeError(f"API-set host escaped System32: {path}")
            api_resolutions[module] = {"host": str(path), "error": 0,
                                       "method": "LoadLibraryExW SYSTEM32|DONT_RESOLVE_DLL_REFERENCES"}
            return str(path)
        finally:
            if not kernel.FreeLibrary(handle):
                raise C.WinError(C.get_last_error())

    def parse(path):
        key = str(path).lower()
        if key not in parsed:
            image = Image(path)
            parsed[key] = image
            exports[key] = image.exports()
            private = image.path.is_relative_to(private_bin)
            allowed = (0xAA64,) if private else (0xAA64, 0xA64E)
            if image.machine not in allowed or image.magic != 0x20B:
                failures.append({"reason": "non-native-PE", **image.summary()})
        return parsed[key]

    def resolve(module, importer):
        private = private_bin / module
        if private.is_file():
            return [private], None
        system = system32 / module
        if system.is_file():
            return [system], None
        choices = contracts.get(module)
        if choices is None:
            if module.startswith(("api-ms-", "ext-ms-")):
                host = operating_system_api_host(module)
                return ([Path(host)], None) if host else ([], "unresolved-system-api-set")
            return [], "missing-import"
        selected = [row["host"] for row in choices if row["importer"] == importer.lower()]
        if not selected:
            selected = [row["host"] for row in choices if not row["importer"]]
        if not selected or any(not host for host in selected):
            return [], "api-set-without-applicable-host"
        return [system32 / host for host in dict.fromkeys(selected)], None

    pending = [(Path(path).resolve(), None, None) for path in images]
    visited = set()
    while pending:
        path, requested, origin = pending.pop()
        try:
            image = parse(path)
        except (OSError, PeError, UnicodeError) as error:
            failures.append({"reason": "invalid-image", "path": str(path), "error": str(error)})
            continue
        key = str(path).lower()
        if requested is not None:
            export = requested.get("name", f"#{requested.get('ordinal')}")
            table = exports[key]
            if export not in table:
                failures.append({"reason": "missing-imported-export", "path": str(path), "symbol": export, "origin": origin})
            elif table[export] is not None:
                forward = table[export]
                if "." not in forward:
                    failures.append({"reason": "invalid-export-forwarder", "path": str(path), "forwarder": forward})
                else:
                    module, symbol = forward.rsplit(".", 1)
                    module = module.lower() + ("" if module.lower().endswith(".dll") else ".dll")
                    targets, error = resolve(module, path.name)
                    edge = {"origin": str(path), "kind": "forwarder", "module": module, "symbol": symbol,
                            "targets": [str(target) for target in targets], "error": error}
                    edges.append(edge)
                    if error:
                        failures.append(edge)
                    else:
                        request = {"ordinal": int(symbol[1:])} if symbol.startswith("#") else {"name": symbol}
                        forward_key = (key, export, tuple(str(target).lower() for target in targets))
                        if forward_key not in visited:
                            visited.add(forward_key)
                            pending.extend((target, request, str(path)) for target in targets)
        if key in visited:
            continue
        visited.add(key)
        try:
            imports = image.imports()
        except (PeError, UnicodeError) as error:
            failures.append({"reason": "invalid-import-directory", "path": str(path), "error": str(error)})
            continue
        for entry in imports:
            if entry["kind"] == "delay" and image.path.is_relative_to(system32) and not expand_system_delay:
                deferred.append({"origin": str(path), **entry,
                                 "scope": "Optional OS feature dependency, not eager loader closure; retained without asserting resolution"})
                continue
            targets, error = resolve(entry["module"], path.name)
            edge = {"origin": str(path), "kind": entry["kind"], "module": entry["module"],
                    "symbols": entry["symbols"], "targets": [str(target) for target in targets], "error": error}
            edges.append(edge)
            if error:
                failures.append(edge)
            else:
                for target in targets:
                    pending.append((target, None, str(path)))
                    pending.extend((target, symbol, str(path)) for symbol in entry["symbols"])
    return {"schema": 1, "images": [image.summary() for image in parsed.values()],
            "api_schema": schema, "edges": edges, "failures": failures,
            "deferred_system_imports": deferred, "expand_system_delay": expand_system_delay,
            "os_api_resolutions": api_resolutions,
            "complete": not failures, "private_bin": str(private_bin), "system32": str(system32),
            "system_arm64x_policy": "System32 ARM64X is recorded separately from genuine shipped AA64; target Machine9 must still be AA64"}
