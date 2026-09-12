"""Small raw COFF reader shared by assembler encoding regressions."""
import struct


def xdata(data):
    machine, count = struct.unpack_from("<HH", data)
    if machine != 0xAA64:
        raise ValueError("Expected an ARM64 COFF object")
    optional = struct.unpack_from("<H", data, 16)[0]
    for index in range(count):
        section = 20 + optional + 40 * index
        if data[section:section + 8].rstrip(b"\0") == b".xdata":
            size, start = struct.unpack_from("<II", data, section + 16)
            if start + size > len(data):
                raise ValueError("Truncated .xdata")
            return data[start:start + size]
    raise ValueError("Missing .xdata")
