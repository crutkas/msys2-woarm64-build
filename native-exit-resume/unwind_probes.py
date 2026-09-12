"""One-shot, byte-locked probes for the retained ARM64 libgcc alias hypothesis."""

import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path
import struct

FIXTURE_SHA = "0d9189f619a6d5b8b94e6c56769154273e8c274fc9743c0b2df597925ad6ece4"
NTDLL_SHA = "81f9d523d199ba1a8bb5fb6081b39e62cdb3289aa2346880c4db43edc6922f9b"
BREAK = struct.pack("<I", 0xD43E0000)
POINTS = (
    ("dispatcher-entry", "ntdll", 0x16C060),
    ("handler-entry", "fixture", 0xC270),
    ("phase2-call", "fixture", 0xC474),
    ("rtl-entry", "ntdll", 0x46330),
    ("after-capture", "ntdll", 0x46468),
    ("no-progress", "ntdll", 0x46764),
)


def instruction(path, rva):
    data = Path(path).read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("Expected PE image")
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", data, pe + 4)[0] != 0xAA64:
        raise ValueError("Expected ARM64 PE")
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    for number in range(sections):
        start = pe + 24 + optional + number * 40
        virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, start + 8)
        flags = struct.unpack_from("<I", data, start + 36)[0]
        if virtual <= rva < virtual + virtual_size:
            offset = rva - virtual
            if not flags & 0x20000000 or offset + 4 > raw_size or raw + offset + 4 > len(data):
                raise ValueError("Probe must be backed by executable section bytes")
            return data[raw + offset:raw + offset + 4]
    raise ValueError("Probe RVA is not in a PE section")


class UnwindProbes:
    def __init__(self, api, process, tid, thread, abi):
        self.api, self.process, self.tid, self.thread, self.abi = api, process, tid, thread, abi
        self.handle = process["handle"]
        self.points, self.samples, self.pointers = {}, [], {}
        self.writes = 0
        self.context_writes = 0
        self.protect = api.bind("VirtualProtectEx", [W.HANDLE, W.LPVOID, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)])
        self.write = api.bind("WriteProcessMemory", [W.HANDLE, W.LPVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)])
        self.flush = api.bind("FlushInstructionCache", [W.HANDLE, W.LPVOID, C.c_size_t])
        self.set_context = api.bind("SetThreadContext", [W.HANDLE, W.LPVOID])
        if abi != {"debug_event_size": 176, "debug_data": 16, "context_size": 912, "context_flags": 0,
                   "context_pc": 264, "context_sp": 256, "context_x": 8, "startup_size": 104}:
            raise RuntimeError("Exact previously compiled ARM64 CONTEXT ABI required")
        if process["machine"] != 0xAA64 or process["image"]["mapped_file_sha256"] != FIXTURE_SHA:
            raise RuntimeError("Only exact owned exception fixture is eligible for probes")
        dll = next((module for module in process["modules"]
                    if module.get("mapped_file_sha256") == NTDLL_SHA), None)
        if dll is None:
            raise RuntimeError("Exact source-diagnosed ntdll mapping not present")
        if any(instruction(dll["path"], rva) != BREAK for rva in (0x17CED0, 0x161CC4)):
            raise RuntimeError("Trap opcode must match both locked Windows debug-break callsites")
        modules = {"fixture": process["image"], "ntdll": dll}
        for name, module_name, rva in POINTS:
            module = modules[module_name]
            address = module["base"] + rva
            original = instruction(module["path"], rva)
            if self.read(address, 4) != original or original == BREAK:
                raise RuntimeError("Mapped callsite does not match locked instruction bytes")
            self.points[address] = {"name": name, "address": address, "rva": rva, "module": module_name,
                                    "mapped_sha256": module["mapped_file_sha256"],
                                    "original": original.hex(), "installed": False, "restored": False,
                                    "hit": False}
        self.ntdll_base = dll["base"]
        self.fixture_base = process["image"]["base"]

    def read(self, address, size):
        record = self.api.memory(self.handle, address, size)
        if not record["success"] or record["read"] != size:
            raise RuntimeError(f"Required bounded probe read failed: {record}")
        return bytes.fromhex(record["bytes"])

    def replace(self, address, expected, replacement):
        if self.read(address, len(expected)) != expected:
            raise RuntimeError("Callsite changed before controlled replacement")
        previous, restored = W.DWORD(), W.DWORD()
        self.api.check(self.protect(self.handle, address, len(replacement), 0x40, C.byref(previous)))
        try:
            data, written = C.create_string_buffer(replacement), C.c_size_t()
            self.api.check(self.write(self.handle, address, data, len(replacement), C.byref(written)))
            self.writes += 1
            if written.value != len(replacement):
                raise RuntimeError("Partial instruction write")
            self.api.check(self.flush(self.handle, address, len(replacement)))
        finally:
            self.api.check(self.protect(self.handle, address, len(replacement), previous, C.byref(restored)))
        if self.read(address, len(replacement)) != replacement:
            raise RuntimeError("Instruction replacement did not read back exactly")

    def install(self):
        try:
            for point in self.points.values():
                self.replace(point["address"], bytes.fromhex(point["original"]), BREAK)
                point["installed"] = True
        except (OSError, RuntimeError):
            self.restore_all()
            raise

    def restore(self, point):
        if point["installed"] and not point["restored"]:
            self.replace(point["address"], BREAK, bytes.fromhex(point["original"]))
            point["restored"] = True

    def restore_all(self):
        for point in self.points.values():
            self.restore(point)

    def saved_context(self, address):
        if not address or address % 16:
            raise RuntimeError(f"Unaligned or absent target CONTEXT pointer: {address:#x}")
        data = self.read(address, self.abi["context_size"])
        return {"address": address, "size": len(data), "bytes": data.hex(),
                "sha256": hashlib.sha256(data).hexdigest(), "flags": struct.unpack_from("<I", data)[0],
                "fp": struct.unpack_from("<Q", data, 240)[0], "lr": struct.unpack_from("<Q", data, 248)[0],
                "sp": struct.unpack_from("<Q", data, 256)[0], "pc": struct.unpack_from("<Q", data, 264)[0]}

    def rewind(self, address):
        buffer = C.create_string_buffer(self.abi["context_size"] + 15)
        pointer = (C.addressof(buffer) + 15) & ~15
        C.c_uint32.from_address(pointer).value = 0x00400003
        self.api.check(self.api.get_context(self.thread, pointer))
        pc = C.c_uint64.from_address(pointer + 264)
        if pc.value not in (address, address + 4):
            raise RuntimeError("Unexpected PC for own one-shot ARM64 breakpoint")
        before = self.api.context(self.thread, self.abi)
        pc.value = address
        C.c_uint32.from_address(pointer).value = 0x00400001
        self.api.check(self.set_context(self.thread, pointer))
        self.context_writes += 1
        after = self.api.context(self.thread, self.abi)
        if (not before["success"] or not after["success"] or after["pc"] != address
                or before["sp"] != after["sp"] or before["registers"] != after["registers"]):
            raise RuntimeError("Restoring original instruction PC changed other observed thread state")
        return {"pc_before": before["pc"], "pc_after": after["pc"], "other_observed_registers_equal": True}

    def handle_event(self, event, row):
        exception = event.data.exception
        point = self.points.get(exception.record.address)
        if point is None or not point["installed"] or point["restored"]:
            return False
        if exception.record.code != 0x80000003 or not exception.first_chance:
            self.restore_all()
            row["unexpected_probe_exception"] = True
            return False
        if event.tid != self.tid or event.pid != self.process["pid"]:
            raise RuntimeError("Own probe hit by an unexpected process/thread generation")
        context = row["context"]
        if not context.get("success"):
            raise RuntimeError("Actual callsite register evidence is required")
        name = point["name"]
        registers = context["registers"]
        sample = {"name": name, "pid": event.pid, "created": self.process["created"],
                  "tid": event.tid, "thread_created": row["thread_created"], "context": context,
                  "callsite": dict(point), "saved_contexts": {}}
        if name == "dispatcher-entry":
            self.pointers["dispatcher_frame"] = context["sp"]
        elif name == "handler-entry":
            self.pointers["handler_incoming_x2"] = registers["x2"]
            sample["dispatcher_context_x3"] = registers["x3"]
        elif name in ("phase2-call", "rtl-entry"):
            self.pointers[name + "_scratch_x4"] = registers["x4"]
            sample["return_lr"] = registers["x30"]
            if name == "rtl-entry":
                sample["return_is_locked_phase2_call"] = registers["x30"] == self.fixture_base + 0xC478
        elif name in ("after-capture", "no-progress"):
            self.pointers[name + "_scratch_x19"] = registers["x19"]
            sample["last_control_pc_x27"] = registers["x27"]
        for key, pointer in self.pointers.items():
            sample["saved_contexts"][key] = self.saved_context(pointer)
        self.restore(point)
        point["hit"] = True
        sample["instruction_restored"] = self.read(point["address"], 4).hex()
        sample["resume_state"] = self.rewind(point["address"])
        self.samples.append(sample)
        row["owned_one_shot_probe"] = name
        return True

    def result(self):
        return {"schema": 1, "scope": "Owned same-binary source-bound context observation, not an exit-domain proof",
                "source_diagnosis_sha256": "78fb4e93fc540f9d3f12103b1f03442662446787bb56842408a4c299456c9eee",
                "break_instruction": BREAK.hex(), "break_source_ntdll_rvas": [0x17CED0, 0x161CC4],
                "memory_writes": self.writes, "context_writes": self.context_writes,
                "points": list(self.points.values()), "samples": self.samples,
                "all_instructions_restored": all(not p["installed"] or p["restored"] for p in self.points.values())}
